import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import evaluate_policy  # noqa: E402
import mock_remediation  # noqa: E402
import normalize_findings  # noqa: E402
import validate_reports  # noqa: E402


class ValidateReportsTest(unittest.TestCase):
    def create_report(self, directory: Path, name: str, content: dict) -> Path:
        path = directory / name
        path.write_text(json.dumps(content), encoding="utf-8")
        return path

    def test_all_required_reports_are_valid(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = validate_reports.build_status({
                "sast": self.create_report(directory, "sast.json", {"results": []}),
                "sca": self.create_report(directory, "sca.json", {"dependencies": []}),
                "container": self.create_report(directory, "trivy.json", {"Results": []}),
            })

        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual([], result["errors"])

    def test_missing_report_produces_analysis_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = validate_reports.build_status({
                "sast": directory / "missing-sast.json",
                "sca": self.create_report(directory, "sca.json", {"dependencies": []}),
                "container": self.create_report(directory, "trivy.json", {"Results": []}),
            })

        self.assertEqual("ERROR", result["status"])
        self.assertEqual("MISSING", result["analyzers"]["sast"]["status"])

    def test_wrong_schema_is_invalid(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = self.create_report(directory, "sast.json", {"unexpected": []})
            status, message = validate_reports.validate_json_report(path, "results")

        self.assertEqual("INVALID", status)
        self.assertIn("results", message)


class NormalizeFindingsTest(unittest.TestCase):
    def test_summary_distinguishes_instances_and_unique_issues(self):
        findings = [
            {
                "id": "CVE-TEST-1",
                "category": "CONTAINER",
                "component": "libexample",
                "version": "1.0",
                "fixedVersion": "1.1",
                "file": "layer-a",
                "severity": "HIGH",
            },
            {
                "id": "CVE-TEST-1",
                "category": "CONTAINER",
                "component": "libexample",
                "version": "1.0",
                "fixedVersion": "1.1",
                "file": "layer-b",
                "severity": "HIGH",
            },
        ]

        summary = normalize_findings.summarize(findings)

        self.assertEqual(2, summary["total"])
        self.assertEqual(1, summary["uniqueIssues"])
        self.assertEqual(1, summary["affectedComponents"])
        self.assertEqual(2, summary["bySeverity"]["HIGH"])
        self.assertEqual(1, summary["uniqueBySeverity"]["HIGH"])

    def test_dependency_version_is_read_from_package_url(self):
        dependency = {
            "packages": [
                {"id": "pkg:maven/org.example/example@1.2.3?type=jar"},
            ],
        }

        self.assertEqual(
            "1.2.3",
            normalize_findings.dependency_version(dependency),
        )


class EvaluatePolicyTest(unittest.TestCase):
    policy = {
        "blockOn": ["CRITICAL"],
        "requireReviewOn": ["HIGH"],
    }
    analysis_success = {"status": "SUCCESS", "errors": []}

    def test_critical_finding_is_blocked(self):
        decision = evaluate_policy.evaluate(
            [{"id": "critical-1", "severity": "CRITICAL"}],
            self.policy,
            self.analysis_success,
        )
        self.assertEqual("BLOCKED", decision["status"])

    def test_high_finding_requires_review(self):
        decision = evaluate_policy.evaluate(
            [{"id": "high-1", "severity": "HIGH"}],
            self.policy,
            self.analysis_success,
        )
        self.assertEqual("REVIEW_REQUIRED", decision["status"])

    def test_medium_finding_is_approved(self):
        decision = evaluate_policy.evaluate(
            [{"id": "medium-1", "severity": "MEDIUM"}],
            self.policy,
            self.analysis_success,
        )
        self.assertEqual("APPROVED", decision["status"])

    def test_analyzer_error_has_priority_over_findings(self):
        decision = evaluate_policy.evaluate(
            [],
            self.policy,
            {"status": "ERROR", "errors": ["Trivy: informe ausente"]},
        )
        self.assertEqual("ANALYSIS_ERROR", decision["status"])
        self.assertEqual(
            ["Trivy: informe ausente"],
            decision["analysisErrors"],
        )


class MockRemediationTest(unittest.TestCase):
    def test_each_category_has_a_stable_response_code(self):
        cases = {
            "SAST": "RES-SAST-001",
            "SCA": "RES-SCA-001",
            "CONTAINER": "RES-CONTAINER-001",
            "OTHER": "RES-GENERAL-001",
        }

        for category, expected_code in cases.items():
            with self.subTest(category=category):
                code, proposal = mock_remediation.recommendation(
                    {"category": category}
                )
                self.assertEqual(expected_code, code)
                self.assertTrue(proposal)


if __name__ == "__main__":
    unittest.main()
