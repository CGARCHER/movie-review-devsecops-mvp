"""API local para actualizar informes y solicitar remediaciones educativas."""

from __future__ import annotations

import json
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
    "https://ai-api.cgarcher.dev/api/v1/remediations",
)
AI_API_TOKEN_FILE = Path(
    os.getenv("AI_API_TOKEN_FILE", "/run/secrets/ai_api_token")
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
    """Localiza únicamente ficheros de código permitidos para la remediación."""
    category = str(finding.get("category", "")).upper()
    if category == "SCA":
        relative_path = Path("pom.xml")
    elif category == "CONTAINER":
        is_maven_dependency = (
            finding.get("packageType") == "jar"
            or ":" in str(finding.get("component") or "")
        )
        relative_path = Path("pom.xml" if is_maven_dependency else "Dockerfile")
    elif category == "SAST":
        file_value = str(finding.get("file") or "").replace("\\", "/")
        relative_path = Path(file_value)
        if relative_path.suffix != ".java" or not file_value.startswith("src/"):
            return None
    else:
        return None

    root = source_root.resolve()
    candidate = (root / relative_path).resolve()
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


def read_ai_token(token_file: Path = AI_API_TOKEN_FILE) -> str:
    token = os.getenv("AI_API_TOKEN", "").strip()
    if token:
        return token

    try:
        token = token_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RequestError("El token de la API de IA no está configurado.") from error
    if not token:
        raise RequestError("El token de la API de IA está vacío.")
    return token


def call_ai_api(payload: dict[str, Any]) -> dict[str, Any]:
    if not AI_API_URL.startswith("https://"):
        raise RequestError("La API de IA debe utilizar HTTPS.")

    request = urllib.request.Request(
        AI_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {read_ai_token()}",
            "Content-Type": "application/json",
            "User-Agent": "movie-review-security-dashboard/1.0",
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
            self.send_json(
                502,
                {"error": "No se ha podido actualizar el informe.", "detail": output},
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
