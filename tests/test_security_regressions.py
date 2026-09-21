import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" if (ROOT / "scripts").exists() else ROOT / "engine/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


normalizer = load("normalize_findings")
evaluator = load("evaluate_policy")


class SecurityRegressionTests(unittest.TestCase):
    policy = {"blockOn": ["CRITICAL"], "requireReviewOn": ["HIGH", "UNKNOWN"],
              "allowOn": ["MEDIUM", "LOW", "INFO"]}

    def test_unknown_severity_is_not_informative(self):
        for value in ("UNKNOWN", None, "", "unexpected", 4):
            with self.subTest(value=value):
                severity = normalizer.normalized_severity(value)
                self.assertEqual(severity, "UNKNOWN")
                findings = [{"id": "unknown-1", "severity": severity}]
                self.assertEqual(normalizer.summarize(findings)["bySeverity"]["UNKNOWN"], 1)
                decision = evaluator.evaluate(findings, self.policy, {"status": "SUCCESS"})
                self.assertEqual(decision["status"], "REVIEW_REQUIRED")
                self.assertEqual(decision["reviewFindingIds"], ["unknown-1"])

    def test_known_severities_keep_their_meaning(self):
        for value, expected in (("ERROR", "HIGH"), ("WARNING", "MEDIUM"), ("INFO", "INFO")):
            self.assertEqual(normalizer.normalized_severity(value), expected)

    def test_invalid_policy_always_writes_an_error_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, data in (("findings", {"findings": [{"id": "high", "severity": "HIGH"}]}),
                               ("status", {"status": "SUCCESS"})):
                (root / (name + ".json")).write_text(json.dumps(data), encoding="utf-8")
            for policy in ({}, [], {"blockOn": None}, {**self.policy, "allowOn": ["TYPO"]}):
                with self.subTest(policy=policy):
                    (root / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
                    output = root / "decision.json"
                    result = subprocess.run([
                        sys.executable, str(SCRIPTS / "evaluate_policy.py"),
                        "--findings", str(root / "findings.json"), "--policy", str(root / "policy.json"),
                        "--analysis-status", str(root / "status.json"), "--output", str(output),
                        "--require-approved",
                    ], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 4, result.stderr)
                    decision = json.loads(output.read_text(encoding="utf-8"))
                    self.assertEqual(decision["status"], "ANALYSIS_ERROR")
                    self.assertTrue(decision["analysisErrors"])

    def test_analyzer_error_precedes_critical_findings(self):
        decision = evaluator.evaluate([{"id": "critical", "severity": "CRITICAL"}],
                                      self.policy, {"status": "ERROR", "errors": ["Missing"]})
        self.assertEqual(decision["status"], "ANALYSIS_ERROR")

    def test_invalid_findings_are_not_approved(self):
        for findings in (None, "invalid", [None]):
            self.assertEqual(evaluator.evaluate(findings, self.policy, {"status": "SUCCESS"})["status"],
                             "ANALYSIS_ERROR")


if __name__ == "__main__":
    unittest.main()

