#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--findings", type=Path, default=Path("reports/normalized/findings.json"))
    parser.add_argument("--policy", type=Path, default=Path("security/policy.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/normalized/decision.json"))
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    findings = json.loads(args.findings.read_text(encoding="utf-8")).get("findings", [])
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    blocking = [item for item in findings if item.get("severity") in policy["blockOn"]]
    review = [item for item in findings if item.get("severity") in policy["requireReviewOn"]]
    status = "BLOCKED" if blocking else "REVIEW_REQUIRED" if review else "APPROVED"
    decision = {
        "status": status,
        "blockingFindingIds": [item.get("id") for item in blocking],
        "reviewFindingIds": [item.get("id") for item in review]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(decision, ensure_ascii=False))
    if args.enforce and blocking:
        sys.exit(2)


if __name__ == "__main__":
    main()
