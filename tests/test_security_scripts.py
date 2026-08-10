import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import evaluate_policy  # noqa: E402
import mock_remediation  # noqa: E402
import normalize_findings  # noqa: E402
import report_api  # noqa: E402
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


class ReportApiTest(unittest.TestCase):
    def create_downloaded_report(self, directory: Path) -> Path:
        run_name = "commit-run-123"
        run_directory = directory / "runs" / run_name
        normalized = run_directory / "normalized"
        normalized.mkdir(parents=True)
        (directory / "LATEST").write_text(run_name, encoding="utf-8")
        (normalized / "findings.json").write_text(
            json.dumps({
                "findings": [
                    {
                        "id": "CVE-2021-44228",
                        "severity": "CRITICAL",
                        "tool": "dependency-check",
                        "category": "SCA",
                        "component": "log4j-core",
                        "description": "Vulnerabilidad de prueba del cliente.",
                        "fixedVersion": "2.17.1",
                    }
                ]
            }),
            encoding="utf-8",
        )
        return run_directory

    def test_selected_finding_is_loaded_from_downloaded_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            report_root = Path(temporary)
            run_directory = self.create_downloaded_report(report_root)
            finding, selected_run = report_api.selected_finding(
                0,
                "CVE-2021-44228",
                report_root,
            )

        self.assertEqual("CVE-2021-44228", finding["id"])
        self.assertEqual(run_directory, selected_run)

    def test_selected_finding_rejects_an_identifier_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            report_root = Path(temporary)
            self.create_downloaded_report(report_root)
            with self.assertRaises(report_api.RequestError):
                report_api.selected_finding(0, "CVE-OTHER", report_root)

    def test_remediation_payload_uses_only_normalized_fields(self):
        payload = report_api.remediation_payload({
            "id": "CVE-2021-44228",
            "severity": "CRITICAL",
            "tool": "dependency-check",
            "category": "SCA",
            "component": "log4j-core",
            "description": "Descripción recibida del analizador.",
            "fixedVersion": "2.17.1",
            "references": ["https://example.invalid"],
        })

        self.assertEqual("CVE-2021-44228", payload["id"])
        self.assertEqual("2.17.1", payload["fixedVersion"])
        self.assertNotIn("references", payload)

    def test_dashboard_server_serves_the_interface(self):
        with tempfile.TemporaryDirectory() as temporary:
            dashboard_root = Path(temporary)
            (dashboard_root / "index.html").write_text(
                "<h1>Security Dashboard</h1>",
                encoding="utf-8",
            )
            previous_root = report_api.DASHBOARD_ROOT
            report_api.DASHBOARD_ROOT = dashboard_root
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                report_api.ReportHandler,
            )
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{server.server_port}/",
                    timeout=2,
                ) as response:
                    body = response.read().decode("utf-8")
                    content_policy = response.headers["Content-Security-Policy"]
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                report_api.DASHBOARD_ROOT = previous_root

        self.assertIn("Security Dashboard", body)
        self.assertIn("default-src 'self'", content_policy)


if __name__ == "__main__":
    unittest.main()
