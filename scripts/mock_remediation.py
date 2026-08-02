#!/usr/bin/env python3
"""Genera un informe didactico determinista sin llamar a una API externa."""

import argparse
import json
from pathlib import Path


def recommendation(finding: dict) -> tuple[str, str]:
    """Devuelve un código estable y una recomendación didáctica."""
    category = finding.get("category")
    if category == "SAST":
        return (
            "RES-SAST-001",
            "Evitar que la entrada del usuario llegue al destino peligroso; "
            "usar una API segura y validar mediante pruebas.",
        )
    if category == "SCA":
        return (
            "RES-SCA-001",
            "Actualizar o excluir la dependencia afectada, revisar el arbol de "
            "Maven y repetir el analisis.",
        )
    if category == "CONTAINER":
        fixed = finding.get("fixedVersion")
        suffix = f" La version corregida indicada es {fixed}." if fixed else ""
        return (
            "RES-CONTAINER-001",
            "Actualizar la imagen base o el paquete y reconstruir la imagen "
            "desde cero." + suffix,
        )
    return (
        "RES-GENERAL-001",
        "Revisar manualmente el hallazgo y contrastarlo con la fuente oficial.",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("reports/normalized/findings.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/ai/remediation.md"))
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    lines = ["# Informe de remediacion (modo simulado)", "",
             "> Estas recomendaciones deben ser revisadas por una persona antes de aplicarse.", ""]
    for finding in data.get("findings", []):
        response_code, proposal = recommendation(finding)
        lines.extend([
            f"## {finding['id']} — {finding['severity']}",
            "",
            f"- **Codigo de respuesta:** {response_code}",
            f"- **Herramienta:** {finding['tool']}",
            f"- **Categoria:** {finding['category']}",
            f"- **Ubicacion/componente:** {finding.get('file') or finding.get('component') or 'No disponible'}",
            f"- **Explicacion:** {finding.get('description') or 'No disponible'}",
            f"- **Propuesta:** {proposal}",
            "- **Validacion:** repetir pruebas y analisis de seguridad tras aplicar el cambio.",
            "",
        ])
    if not data.get("findings"):
        lines.append("No se han recibido hallazgos para explicar.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
