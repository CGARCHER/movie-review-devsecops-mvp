#!/usr/bin/env python3
"""Genera un informe didactico determinista sin llamar a una API externa."""

import argparse
import json
from pathlib import Path


def recommendation(finding: dict) -> str:
    category = finding.get("category")
    if category == "SAST":
        return "Evitar que la entrada del usuario llegue al destino peligroso; usar una API segura y validar mediante pruebas."
    if category == "SCA":
        return "Actualizar o excluir la dependencia afectada, revisar el arbol de Maven y repetir el analisis."
    if category == "CONTAINER":
        fixed = finding.get("fixedVersion")
        suffix = f" La version corregida indicada es {fixed}." if fixed else ""
        return "Actualizar la imagen base o el paquete y reconstruir la imagen desde cero." + suffix
    return "Revisar manualmente el hallazgo y contrastarlo con la fuente oficial."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("reports/normalized/findings.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/ai/remediation.md"))
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    lines = ["# Informe de remediacion (modo simulado)", "",
             "> Estas recomendaciones deben ser revisadas por una persona antes de aplicarse.", ""]
    for finding in data.get("findings", []):
        lines.extend([
            f"## {finding['id']} — {finding['severity']}",
            "",
            f"- **Herramienta:** {finding['tool']}",
            f"- **Categoria:** {finding['category']}",
            f"- **Ubicacion/componente:** {finding.get('file') or finding.get('component') or 'No disponible'}",
            f"- **Explicacion:** {finding.get('description') or 'No disponible'}",
            f"- **Propuesta:** {recommendation(finding)}",
            "- **Validacion:** repetir pruebas y analisis de seguridad tras aplicar el cambio.",
            "",
        ])
    if not data.get("findings"):
        lines.append("No se han recibido hallazgos para explicar.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
