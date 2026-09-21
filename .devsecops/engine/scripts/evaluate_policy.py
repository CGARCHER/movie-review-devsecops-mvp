#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        return document if isinstance(document, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def evaluate(findings: list[dict], policy: dict, analysis_status: dict) -> dict:
    # No se evalúan hallazgos con una política incompleta.
    levels = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"}
    fields = ("blockOn", "requireReviewOn", "allowOn")
    valid_policy = isinstance(policy, dict) and all(
        isinstance(policy.get(field), list)
        and all(isinstance(level, str) and level in levels for level in policy[field])
        for field in fields
    )
    if not isinstance(analysis_status, dict):
        analysis_status = {"status": "ERROR", "errors": ["El estado de los analizadores no es válido."]}
    reported_errors = analysis_status.get("errors", [])
    errors = (
        reported_errors.copy()
        if isinstance(reported_errors, list) and all(isinstance(item, str) for item in reported_errors)
        else ["El estado de los analizadores no es válido."]
    )
    if not valid_policy:
        errors.append("La política de seguridad no existe o no es válida.")
    if not isinstance(findings, list) or not all(isinstance(item, dict) for item in findings):
        errors.append("El informe normalizado no existe o no es válido.")
    if errors or analysis_status.get("status") != "SUCCESS":
        return {
            "status": "ANALYSIS_ERROR",
            "blockingFindingIds": [],
            "reviewFindingIds": [],
            "analysisErrors": list(dict.fromkeys(errors)),
        }

    blocking = [item for item in findings if item.get("severity") in policy["blockOn"]]
    # Una severidad desconocida o no cubierta por la política requiere revisión.
    review = [
        item for item in findings
        if item.get("severity") not in policy["blockOn"]
        and (
            item.get("severity") in policy["requireReviewOn"]
            or item.get("severity") not in policy["allowOn"]
            or item.get("severity") == "UNKNOWN"
        )
    ]
    if blocking:
        status = "BLOCKED"
    elif review:
        status = "REVIEW_REQUIRED"
    else:
        status = "APPROVED"

    blocking_ids = list(dict.fromkeys(item.get("id") for item in blocking if item.get("id")))
    review_ids = list(dict.fromkeys(item.get("id") for item in review if item.get("id")))

    return {
        "status": status,
        "blockingFindingIds": blocking_ids,
        "reviewFindingIds": review_ids,
        "analysisErrors": analysis_status.get("errors", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--findings", type=Path, default=Path("reports/normalized/findings.json"))
    parser.add_argument("--policy", type=Path, default=Path("security/policy.json"))
    parser.add_argument(
        "--analysis-status",
        type=Path,
        default=Path("reports/normalized/analyzer-status.json"),
    )
    parser.add_argument("--output", type=Path, default=Path("reports/normalized/decision.json"))
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument(
        "--require-approved",
        action="store_true",
        help="Devuelve error para cualquier estado diferente de APPROVED.",
    )
    args = parser.parse_args()

    findings_document = load_json(args.findings)
    policy = load_json(args.policy)
    analysis_status = load_json(args.analysis_status)

    # evaluate comprueba los datos y produce una decisión incluso si son inválidos.
    decision = evaluate(
        findings_document.get("findings"),
        policy,
        analysis_status,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(decision, ensure_ascii=False))

    if args.require_approved and decision["status"] != "APPROVED":
        sys.exit(4)
    if args.enforce and decision["status"] in {"BLOCKED", "ANALYSIS_ERROR"}:
        sys.exit(2)


if __name__ == "__main__":
    main()
