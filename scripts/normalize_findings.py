#!/usr/bin/env python3
"""Normaliza resultados de Semgrep, Dependency-Check y Trivy.

No utiliza dependencias externas para poder ejecutarse en GitHub Actions o
localmente. Los ficheros ausentes se ignoran, lo que permite ejecutar cada
analizador de forma independiente.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SEVERITY_MAP = {
    "ERROR": "HIGH",
    "WARNING": "MEDIUM",
    "WARN": "MEDIUM",
    "NOTE": "LOW",
    "UNKNOWN": "INFO",
}


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_severity(value: str | None) -> str:
    value = (value or "UNKNOWN").upper()
    if value in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}:
        return value
    return SEVERITY_MAP.get(value, "INFO")


def semgrep_findings(data: dict[str, Any], commit: str) -> list[dict[str, Any]]:
    findings = []
    for result in data.get("results", []):
        extra = result.get("extra", {})
        metadata = extra.get("metadata", {})
        findings.append({
            "id": result.get("check_id", "semgrep-unknown"),
            "tool": "semgrep",
            "category": "SAST",
            "severity": normalized_severity(extra.get("severity")),
            "component": None,
            "version": None,
            "file": result.get("path"),
            "line": result.get("start", {}).get("line"),
            "description": extra.get("message"),
            "cwe": metadata.get("cwe"),
            "references": metadata.get("references", []),
            "commit": commit,
        })
    return findings


def dependency_check_findings(data: dict[str, Any], commit: str) -> list[dict[str, Any]]:
    findings = []
    for dependency in data.get("dependencies", []):
        for vulnerability in dependency.get("vulnerabilities", []) or []:
            findings.append({
                "id": vulnerability.get("name", "dependency-check-unknown"),
                "tool": "dependency-check",
                "category": "SCA",
                "severity": normalized_severity(vulnerability.get("severity")),
                "component": dependency.get("fileName"),
                "version": None,
                "file": dependency.get("filePath"),
                "line": None,
                "description": vulnerability.get("description"),
                "cwe": vulnerability.get("cwes", []),
                "references": [r.get("url") for r in vulnerability.get("references", []) if r.get("url")],
                "commit": commit,
            })
    return findings


def trivy_findings(data: dict[str, Any], commit: str) -> list[dict[str, Any]]:
    findings = []
    for result in data.get("Results", []) or []:
        for vulnerability in result.get("Vulnerabilities", []) or []:
            findings.append({
                "id": vulnerability.get("VulnerabilityID", "trivy-unknown"),
                "tool": "trivy",
                "category": "CONTAINER",
                "severity": normalized_severity(vulnerability.get("Severity")),
                "component": vulnerability.get("PkgName"),
                "version": vulnerability.get("InstalledVersion"),
                "fixedVersion": vulnerability.get("FixedVersion"),
                "file": result.get("Target"),
                "line": None,
                "description": vulnerability.get("Title") or vulnerability.get("Description"),
                "cwe": vulnerability.get("CweIDs", []),
                "references": vulnerability.get("References", []),
                "commit": commit,
            })
    return findings


def deduplicate(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for finding in findings:
        key = (
            finding.get("id"),
            finding.get("category"),
            finding.get("component"),
            finding.get("file"),
            finding.get("line"),
        )
        unique.setdefault(key, finding)
    return list(unique.values())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semgrep", type=Path, default=Path("reports/sast/semgrep.json"))
    parser.add_argument("--dependency-check", type=Path,
                        default=Path("reports/sca/dependency-check-report.json"))
    parser.add_argument("--trivy", type=Path, default=Path("reports/container/trivy.json"))
    parser.add_argument("--commit", default="local")
    parser.add_argument("--output", type=Path, default=Path("reports/normalized/findings.json"))
    args = parser.parse_args()

    findings = []
    findings.extend(semgrep_findings(load(args.semgrep), args.commit))
    findings.extend(dependency_check_findings(load(args.dependency_check), args.commit))
    findings.extend(trivy_findings(load(args.trivy), args.commit))
    findings = deduplicate(findings)

    counts = {level: 0 for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")}
    for finding in findings:
        counts[finding["severity"]] += 1

    document = {
        "schemaVersion": "1.0",
        "commit": args.commit,
        "summary": {"total": len(findings), "bySeverity": counts},
        "findings": findings,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(document["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
