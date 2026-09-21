#!/usr/bin/env python3
"""Comprueba que todos los analizadores obligatorios generaron un informe válido.

Encontrar vulnerabilidades no es un error técnico. En cambio, un informe
ausente, vacío o con un JSON inválido impide tomar una decisión de seguridad
fiable y debe producir un estado ANALYSIS_ERROR.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPORTS = {
    "sast": ("Semgrep", "results"),
    "sca": ("Trivy SCA", "Results"),
    "container": ("Trivy", "Results"),
}


def validate_json_report(path: Path, required_key: str) -> tuple[str, str | None]:
    if not path.is_file():
        return "MISSING", "No se ha generado el informe."
    if path.stat().st_size == 0:
        return "INVALID", "El informe está vacío."

    try:
        document: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return "INVALID", f"No contiene un JSON válido: {error}"

    if not isinstance(document, dict):
        return "INVALID", "La raíz del informe no es un objeto JSON."
    if required_key not in document:
        return "INVALID", f"Falta el campo obligatorio '{required_key}'."
    if not isinstance(document[required_key], list):
        return "INVALID", f"El campo '{required_key}' no es una lista."
    return "SUCCESS", None


def build_status(
    paths: dict[str, Path],
    not_applicable: set[str] | None = None,
) -> dict[str, Any]:
    analyzers: dict[str, Any] = {}
    errors: list[str] = []
    not_applicable = not_applicable or set()

    for key, path in paths.items():
        display_name, required_key = REPORTS[key]
        if key in not_applicable:
            analyzers[key] = {
                "name": display_name,
                "status": "NOT_APPLICABLE",
                "report": path.as_posix(),
                "message": "No se ha encontrado un Dockerfile en el proyecto.",
            }
            continue
        status, message = validate_json_report(path, required_key)
        analyzers[key] = {
            "name": display_name,
            "status": status,
            "report": path.as_posix(),
        }
        if message:
            analyzers[key]["message"] = message
            errors.append(f"{display_name}: {message}")

    return {
        "schemaVersion": "1.0",
        "status": "SUCCESS" if not errors else "ERROR",
        "analyzers": analyzers,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sast", type=Path, default=Path("reports/sast/semgrep.json"))
    parser.add_argument(
        "--sca",
        type=Path,
        default=Path("reports/sca/trivy-sca.json"),
    )
    parser.add_argument(
        "--container",
        type=Path,
        default=Path("reports/container/trivy.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/normalized/analyzer-status.json"),
    )
    parser.add_argument(
        "--container-status",
        type=Path,
        default=Path("reports/container/status.json"),
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Devuelve un código de error si algún informe no es válido.",
    )
    args = parser.parse_args()

    not_applicable: set[str] = set()
    if args.container_status.is_file():
        try:
            marker = json.loads(args.container_status.read_text(encoding="utf-8"))
            if marker.get("status") == "NOT_APPLICABLE":
                not_applicable.add("container")
        except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
            pass

    result = build_status({
        "sast": args.sast,
        "sca": args.sca,
        "container": args.container,
    }, not_applicable)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))

    if args.enforce and result["status"] != "SUCCESS":
        sys.exit(3)


if __name__ == "__main__":
    main()
