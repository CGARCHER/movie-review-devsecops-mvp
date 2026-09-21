"""API local para actualizar informes y solicitar remediaciones educativas."""

from __future__ import annotations

import json
import difflib
import mimetypes
import os
import re
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


DASHBOARD_CONFIG_FILE = Path(
    os.getenv("DASHBOARD_CONFIG_FILE", "/run/secrets/dashboard.env")
)
ALLOWED_CONFIG_KEYS = {
    "GITHUB_REPOSITORY",
    "GITHUB_WORKFLOW_FILE",
    "GITHUB_BRANCH",
    "AI_API_URL",
    "GH_TOKEN",
    "AI_API_TOKEN",
}


def load_dashboard_config(path: Path = DASHBOARD_CONFIG_FILE) -> None:
    """Carga únicamente las claves conocidas del fichero local del panel."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in ALLOWED_CONFIG_KEYS:
            os.environ.setdefault(key, value.strip())


load_dashboard_config()

REPORT_ROOT = Path(os.getenv("REPORT_ROOT", "/workspace/reports"))
SOURCE_ROOT = Path(os.getenv("SOURCE_ROOT", "/workspace/source"))
AI_REMEDIATION_ENABLED = os.getenv(
    "AI_REMEDIATION_ENABLED", "false"
).lower() == "true"
DASHBOARD_ROOT = Path(
    os.getenv("DASHBOARD_ROOT", "/usr/local/share/security-dashboard")
)
AI_API_URL = os.getenv(
    "AI_API_URL",
    "",
)

REQUEST_HEADER = "X-Dashboard-Request"
MAX_REQUEST_SIZE = 1024
UPDATE_LOCK = threading.Lock()
REMEDIATION_LOCK = threading.Lock()
LATEST_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
MAX_SOURCE_CONTEXT = 8000


class RequestError(Exception):
    """Error controlado que puede mostrarse al usuario del dashboard."""


def download_report() -> subprocess.CompletedProcess[str]:
    """Descarga el último informe mediante el cliente de GitHub incluido."""
    return subprocess.run(
        ["/usr/local/bin/security-report"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RequestError(f"No se puede leer {path.name}.") from error
    if not isinstance(document, dict):
        raise RequestError(f"El fichero {path.name} no contiene un objeto JSON.")
    return document


def latest_run_directory(report_root: Path = REPORT_ROOT) -> Path:
    latest_file = report_root / "LATEST"
    try:
        latest = latest_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RequestError("No se ha encontrado un informe descargado.") from error

    if not LATEST_PATTERN.fullmatch(latest):
        raise RequestError("El identificador del último informe no es válido.")

    run_directory = report_root / "runs" / latest
    if not run_directory.is_dir():
        raise RequestError("No se encuentra el directorio del último informe.")
    return run_directory


def selected_finding(
    finding_index: int,
    finding_id: str,
    report_root: Path = REPORT_ROOT,
) -> tuple[dict[str, Any], Path]:
    """Comprueba que el hallazgo solicitado pertenece al último informe descargado."""
    run_directory = latest_run_directory(report_root)
    document = read_json(run_directory / "normalized" / "findings.json")
    findings = document.get("findings")
    if not isinstance(findings, list):
        raise RequestError("El informe no contiene una lista de hallazgos válida.")
    if finding_index < 0 or finding_index >= len(findings):
        raise RequestError("El hallazgo seleccionado no existe.")

    finding = findings[finding_index]
    if not isinstance(finding, dict) or finding.get("id") != finding_id:
        raise RequestError("El hallazgo no coincide con el informe descargado.")
    return finding, run_directory


def source_file_for_finding(finding: dict[str, Any], source_root: Path) -> Path | None:
    """Localiza un fichero relevante sin asumir Maven ni una ruta concreta."""
    category = str(finding.get("category", "")).upper()
    root = source_root.resolve()

    def unique_file(names: tuple[str, ...]) -> Path | None:
        direct = [root / name for name in names if (root / name).is_file()]
        if len(direct) == 1:
            return direct[0]
        found = sorted(
            path
            for name in names
            for path in root.rglob(name)
            if not any(
                part in {".git", "build", "reports", "target"}
                for part in path.parts
            )
        )
        return found[0] if len(found) == 1 else None

    if category == "SCA":
        candidate = unique_file(("pom.xml", "build.gradle", "build.gradle.kts"))
    elif category == "CONTAINER":
        is_maven_dependency = (
            finding.get("packageType") == "jar"
            or ":" in str(finding.get("component") or "")
        )
        candidate = (
            unique_file(("pom.xml", "build.gradle", "build.gradle.kts"))
            if is_maven_dependency
            else unique_file(("Dockerfile",))
        )
    elif category == "SAST":
        file_value = str(finding.get("file") or "").replace("\\", "/")
        relative_path = Path(file_value)
        if relative_path.is_absolute() or relative_path.suffix not in {".java", ".kt"}:
            return None
        candidate = (root / relative_path).resolve()
    else:
        return None

    if candidate is None:
        return None
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def source_context(finding: dict[str, Any], source_root: Path) -> tuple[str | None, str | None]:
    """Lee el fichero afectado sin permitir acceso al resto del equipo."""
    source_file = source_file_for_finding(finding, source_root)
    if source_file is None:
        return None, None

    try:
        content = source_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, None

    line = finding.get("line")
    if isinstance(line, int) and line > 0:
        lines = content.splitlines()
        first = max(0, line - 5)
        last = min(len(lines), line + 4)
        content = "\n".join(lines[first:last])

    relative_path = source_file.relative_to(source_root.resolve()).as_posix()
    return relative_path, content[:MAX_SOURCE_CONTEXT]


def remediation_payload(
    finding: dict[str, Any],
    source_root: Path = SOURCE_ROOT,
) -> dict[str, Any]:
    """Envía a la IA solo el hallazgo y el contexto necesarios para orientarlo."""
    description = finding.get("description")
    if not isinstance(description, str) or not description.strip():
        description = "El analizador no proporcionó una descripción del hallazgo."

    affected_file, context = source_context(finding, source_root)
    return {
        "id": str(finding.get("id", "")),
        "severity": str(finding.get("severity", "UNKNOWN")),
        "tool": str(finding.get("tool", "unknown")),
        "category": str(finding.get("category", "OTHER")),
        "component": finding.get("component") or finding.get("file"),
        "description": description,
        "currentVersion": finding.get("version"),
        "fixedVersion": finding.get("fixedVersion"),
        "affectedFile": affected_file,
        "line": finding.get("line"),
        "sourceContext": context,
    }


def read_ai_token() -> str:
    token = os.getenv("AI_API_TOKEN", "").strip()
    if not token:
        raise RequestError("El token de la API de IA no está configurado.")
    return token


def call_ai_api(payload: dict[str, Any]) -> dict[str, Any]:
    """Consulta la API mediante HTTPS y valida la estructura de su respuesta."""
    if not AI_API_URL.startswith("https://"):
        raise RequestError("La API de IA debe utilizar HTTPS.")

    request = urllib.request.Request(
        AI_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {read_ai_token()}",
            "Content-Type": "application/json",
            "User-Agent": "devsecops-learning-dashboard/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RequestError(
            f"La API de IA ha rechazado la petición (HTTP {error.code})."
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RequestError("No se ha podido conectar con la API de IA.") from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RequestError("La API de IA no ha devuelto un JSON válido.") from error

    required = (
        "findingId",
        "model",
        "explanation",
        "recommendation",
        "validation",
        "learningNote",
    )
    if not isinstance(result, dict) or any(
        not isinstance(result.get(field), str) or not result[field].strip()
        for field in required
    ):
        raise RequestError("La respuesta de la API de IA está incompleta.")
    if result["findingId"] != payload["id"]:
        raise RequestError("La respuesta de la API de IA no corresponde al hallazgo.")

    patch = result.get("patchProposal")
    if isinstance(patch, dict) and patch.get("available") is True:
        if not payload.get("affectedFile") or patch.get("file") != payload["affectedFile"]:
            raise RequestError("El parche no corresponde al fichero analizado.")
        content = patch.get("content")
        if not isinstance(content, str) or "--- " not in content or "+++ " not in content:
            raise RequestError("La propuesta no contiene una diferencia válida.")
    return result


def local_patch_proposal(
    result: dict[str, Any],
    finding: dict[str, Any],
    source_root: Path = SOURCE_ROOT,
) -> dict[str, Any]:
    """Completa una propuesta ausente utilizando el fichero real como base."""
    current_patch = result.get("patchProposal")
    if isinstance(current_patch, dict) and current_patch.get("available") is True:
        return result

    source_file = source_file_for_finding(finding, source_root)
    fixed_version = str(finding.get("fixedVersion") or "").split(",")[0].strip()
    if source_file is None or not fixed_version:
        return result
    try:
        original = source_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return result

    updated = _updated_source(original, source_file, finding, fixed_version)

    if updated == original:
        return result

    relative = source_file.relative_to(source_root.resolve()).as_posix()
    patch = _unified_diff(original, updated, relative)
    enriched = dict(result)
    enriched["patchProposal"] = {
        "available": True,
        "file": relative,
        "content": patch,
        "generatedFromSource": True,
    }
    return enriched


def _updated_source(
    original: str,
    source_file: Path,
    finding: dict[str, Any],
    fixed_version: str,
) -> str:
    """Aplica únicamente sustituciones que pueden deducirse sin ambigüedad."""
    current_version = str(finding.get("version") or "").strip()
    if current_version and current_version in original:
        return original.replace(current_version, fixed_version, 1)

    component = str(finding.get("component") or "")
    if source_file.name.lower() == "pom.xml":
        return _updated_pom(original, component, fixed_version)
    if source_file.name == "Dockerfile":
        return _updated_dockerfile(original, component, fixed_version)

    # En Gradle no se crea una declaración nueva porque puede utilizar Groovy
    # o Kotlin y depender de plugins distintos.
    return original


def _updated_pom(original: str, component: str, fixed_version: str) -> str:
    """Añade una propiedad conocida de Spring solo cuando no existe."""
    artifact = component.split(":")[-1].lower()
    if "tomcat" in artifact:
        property_name = "tomcat.version"
    elif component.startswith("org.springframework:"):
        property_name = "spring-framework.version"
    else:
        return original

    if f"<{property_name}>" in original or "</properties>" not in original:
        return original

    property_line = f"        <{property_name}>{fixed_version}</{property_name}>\n"
    return original.replace(
        "    </properties>", property_line + "    </properties>", 1
    )


def _updated_dockerfile(original: str, component: str, fixed_version: str) -> str:
    """Propone la instalación de un paquete Alpine en la etapa final."""
    if not re.fullmatch(r"[A-Za-z0-9+_.-]+", component):
        return original
    if "apk " not in original.lower() and "alpine" not in original.lower():
        return original

    lines = original.splitlines(keepends=True)
    final_from = max(
        (
            index
            for index, line in enumerate(lines)
            if line.lstrip().upper().startswith("FROM ")
        ),
        default=-1,
    )
    for index in range(final_from + 1, len(lines)):
        line = lines[index]
        if line.lstrip().upper().startswith("RUN "):
            command = line.rstrip("\r\n")
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            package = f"'{component}>={fixed_version}'"
            lines[index] = command.replace(
                "RUN ", f"RUN apk add --no-cache {package} && ", 1
            ) + newline
            return "".join(lines)
    return original


def _unified_diff(original: str, updated: str, relative: str) -> str:
    """Construye la diferencia que se mostrará para revisión manual."""
    return "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=relative,
        tofile=relative,
        n=3,
    ))


def remediation_markdown(result: dict[str, Any]) -> str:
    return "\n".join([
        "# Remediación asistida por IA",
        "",
        "> La propuesta debe ser revisada por una persona antes de aplicarse.",
        "",
        f"## {result['findingId']}",
        "",
        f"- **Modelo:** {result['model']}",
        f"- **Explicación:** {result['explanation']}",
        f"- **Recomendación:** {result['recommendation']}",
        f"- **Validación manual:** {result['validation']}",
        f"- **Nota didáctica:** {result['learningNote']}",
        "",
    ])


def save_remediation(result: dict[str, Any], run_directory: Path) -> None:
    """Guarda la respuesta para poder revisarla sin repetir la consulta a la IA."""
    ai_directory = run_directory / "ai"
    detail_directory = ai_directory / "remediations"
    detail_directory.mkdir(parents=True, exist_ok=True)

    safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", result["findingId"])[:120]
    stored_result = {
        **result,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
    (detail_directory / f"{safe_id}.json").write_text(
        json.dumps(stored_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ai_directory / "remediation.md").write_text(
        remediation_markdown(result),
        encoding="utf-8",
    )


class ReportHandler(BaseHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src 'self'; style-src 'self'; "
            "script-src 'self'; img-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        super().end_headers()

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, root: Path, relative_path: str) -> None:
        root = root.resolve()
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            self.send_json(404, {"error": "Fichero no encontrado."})
            return

        if not candidate.is_file():
            self.send_json(404, {"error": "Fichero no encontrado."})
            return

        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_request_json(self) -> dict[str, Any]:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise RequestError("El tamaño de la petición no es válido.") from error
        if content_length <= 0 or content_length > MAX_REQUEST_SIZE:
            raise RequestError("La petición está vacía o es demasiado grande.")
        try:
            document = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RequestError("La petición no contiene un JSON válido.") from error
        if not isinstance(document, dict):
            raise RequestError("La petición debe contener un objeto JSON.")
        return document

    def do_GET(self) -> None:
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        if path == "/health":
            self.send_json(200, {"status": "ok"})
            return
        if path == "/api/config":
            self.send_json(200, {"remediationEnabled": AI_REMEDIATION_ENABLED})
            return
        if path.startswith("/reports/"):
            self.send_file(REPORT_ROOT, path.removeprefix("/reports/"))
            return
        static_files = {
            "/": "index.html",
            "/index.html": "index.html",
            "/app.js": "app.js",
            "/styles.css": "styles.css",
        }
        if path in static_files:
            self.send_file(DASHBOARD_ROOT, static_files[path])
            return
        self.send_json(404, {"error": "Ruta no encontrada."})

    def do_POST(self) -> None:
        if self.headers.get(REQUEST_HEADER) != "1":
            self.send_json(403, {"error": "Petición no autorizada."})
            return

        if self.path == "/api/update":
            self.update_report()
            return
        if self.path == "/api/remediation":
            self.create_remediation()
            return
        self.send_json(404, {"error": "Ruta no encontrada."})

    def update_report(self) -> None:
        if not UPDATE_LOCK.acquire(blocking=False):
            self.send_json(409, {"error": "Ya hay una actualización en curso."})
            return

        try:
            result = download_report()
        except subprocess.TimeoutExpired:
            self.send_json(504, {"error": "La descarga ha superado el tiempo máximo."})
            return
        finally:
            UPDATE_LOCK.release()

        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            error_message = "No se ha podido actualizar el informe."
            if "no se ha encontrado ninguna ejecucion terminada" in output.lower():
                branch = os.getenv("GITHUB_BRANCH", "").strip()
                error_message = (
                    f"Todavia no existe un analisis terminado para la rama {branch}."
                    if branch
                    else "Todavia no existe ningun analisis terminado."
                )
            self.send_json(
                404 if "ninguna ejecucion terminada" in output.lower() else 502,
                {"error": error_message, "detail": output},
            )
            return
        self.send_json(
            200,
            {"message": "Informe actualizado correctamente.", "detail": output},
        )

    def create_remediation(self) -> None:
        if not AI_REMEDIATION_ENABLED:
            self.send_json(403, {"error": "La remediación solo está disponible en local."})
            return

        if not REMEDIATION_LOCK.acquire(blocking=False):
            self.send_json(409, {"error": "Ya hay una remediación en curso."})
            return

        try:
            request_data = self.read_request_json()
            finding_index = request_data.get("findingIndex")
            finding_id = request_data.get("findingId")
            if not isinstance(finding_index, int) or not isinstance(finding_id, str):
                raise RequestError("Debe seleccionarse un hallazgo válido.")

            finding, run_directory = selected_finding(finding_index, finding_id)
            result = call_ai_api(remediation_payload(finding))
            result = local_patch_proposal(result, finding)
            save_remediation(result, run_directory)
        except RequestError as error:
            self.send_json(400, {"error": str(error)})
            return
        finally:
            REMEDIATION_LOCK.release()

        self.send_json(200, result)

    def log_message(self, message_format: str, *args: Any) -> None:
        print(f"{self.client_address[0]} - {message_format % args}", flush=True)


if __name__ == "__main__":
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        initial_download = download_report()
        initial_output = (initial_download.stdout + initial_download.stderr).strip()
        if initial_download.returncode == 0:
            print("Informe inicial descargado correctamente.", flush=True)
        else:
            print(f"No se ha podido descargar el informe inicial: {initial_output}", flush=True)
    except subprocess.TimeoutExpired:
        print("La descarga inicial ha superado el tiempo máximo.", flush=True)

    server = ThreadingHTTPServer(("0.0.0.0", 8080), ReportHandler)
    print("Security Dashboard disponible en el puerto 8080.", flush=True)
    server.serve_forever()
