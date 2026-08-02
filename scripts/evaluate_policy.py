#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def evaluate(findings: list[dict], policy: dict, analysis_status: dict) -> dict:
    analyzer_error = analysis_status.get("status") != "SUCCESS"
    blocking = [item for item in findings if item.get("severity") in policy["blockOn"]]
    review = [item for item in findings if item.get("severity") in policy["requireReviewOn"]]

    if analyzer_error:
        status = "ANALYSIS_ERROR"
    elif blocking:
        status = "BLOCKED"
    elif review:
        status = "REVIEW_REQUIRED"
    else:
        status = "APPROVED"

    return {
        "status": status,
        "blockingFindingIds": [item.get("id") for item in blocking],
        "reviewFindingIds": [item.get("id") for item in review],
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

    if not isinstance(findings_document.get("findings"), list):
        analysis_status = {
            "status": "ERROR",
            "errors": ["El informe normalizado no existe o no es válido."],
        }
    required_policy_fields = ("blockOn", "requireReviewOn", "allowOn")
    if not all(isinstance(policy.get(field), list) for field in required_policy_fields):
        analysis_status = {
            "status": "ERROR",
            "errors": ["La política de seguridad no existe o no es válida."],
        }

    decision = evaluate(
        findings_document.get("findings", []),
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
