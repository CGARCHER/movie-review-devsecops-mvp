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
import project_profile  # noqa: E402
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
                "sca": self.create_report(directory, "sca.json", {"Results": []}),
                "container": self.create_report(directory, "trivy.json", {"Results": []}),
            })

        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual([], result["errors"])

    def test_missing_report_produces_analysis_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = validate_reports.build_status({
                "sast": directory / "missing-sast.json",
                "sca": self.create_report(directory, "sca.json", {"Results": []}),
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

    def test_container_can_be_not_applicable_without_failing_the_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = validate_reports.build_status({
                "sast": self.create_report(directory, "sast.json", {"results": []}),
                "sca": self.create_report(directory, "sca.json", {"Results": []}),
                "container": directory / "missing-container.json",
            }, {"container"})

        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual("NOT_APPLICABLE", result["analyzers"]["container"]["status"])


class NormalizeFindingsTest(unittest.TestCase):
    def test_summary_distinguishes_instances_and_unique_issues(self):
        findings = [
            {
                "id": "CVE-TEST-1",
                "category": "SCA",
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

    def test_same_issue_from_sca_and_container_is_unique(self):
        base = {
            "id": "CVE-TEST-2",
            "component": "org.example:library",
            "version": "1.0",
            "fixedVersion": "1.1",
            "severity": "CRITICAL",
        }
        summary = normalize_findings.summarize([
            {**base, "category": "SCA", "file": "Java"},
            {**base, "category": "CONTAINER", "file": "app.jar"},
        ])

        self.assertEqual(2, summary["total"])
        self.assertEqual(1, summary["uniqueIssues"])
        self.assertEqual(1, summary["uniqueBySeverity"]["CRITICAL"])

    def test_trivy_keeps_the_package_type(self):
        findings = normalize_findings.trivy_findings({
            "Results": [{
                "Type": "jar",
                "Vulnerabilities": [{
                    "VulnerabilityID": "CVE-TEST",
                    "PkgName": "org.example:library",
                }],
            }],
        }, "commit")

        self.assertEqual("jar", findings[0]["packageType"])

    def test_trivy_can_normalize_sca_findings(self):
        findings = normalize_findings.trivy_findings({
            "Results": [{
                "Type": "jar",
                "Vulnerabilities": [{
                    "VulnerabilityID": "CVE-TEST",
                    "PkgName": "org.example:library",
                }],
            }],
        }, "commit", category="SCA", tool="trivy-sca")

        self.assertEqual("SCA", findings[0]["category"])
        self.assertEqual("trivy-sca", findings[0]["tool"])


class EvaluatePolicyTest(unittest.TestCase):
    policy = {
        "blockOn": ["CRITICAL"],
        "requireReviewOn": ["HIGH"],
        "allowOn": ["MEDIUM", "LOW", "INFO"],
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

    def test_decision_lists_each_vulnerability_id_once(self):
        decision = evaluate_policy.evaluate(
            [
                {"id": "CVE-DUPLICATE", "severity": "CRITICAL", "category": "SCA"},
                {"id": "CVE-DUPLICATE", "severity": "CRITICAL", "category": "CONTAINER"},
            ],
            self.policy,
            self.analysis_success,
        )

        self.assertEqual(["CVE-DUPLICATE"], decision["blockingFindingIds"])


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


class ProjectProfileTest(unittest.TestCase):
    def test_detects_maven_project_in_repository_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "pom.xml").write_text(
                "<project><artifactId>spring-boot-starter-web</artifactId>"
                "<properties><java.version>21</java.version></properties></project>",
                encoding="utf-8",
            )
            (root / "Dockerfile").write_text(
                "FROM eclipse-temurin:21-jre", encoding="utf-8"
            )
            profile = project_profile.build_profile(root, "auto", "auto")

        self.assertEqual("maven", profile["buildSystem"])
        self.assertEqual("21", profile["javaVersion"])
        self.assertEqual("pom.xml", profile["buildFile"])
        self.assertTrue(profile["containerScan"])

    def test_detects_gradle_project_in_subdirectory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = root / "service"
            module.mkdir()
            (module / "build.gradle.kts").write_text(
                'plugins { id("org.springframework.boot") version "3.5.0" }\n'
                "java { toolchain { languageVersion = JavaLanguageVersion.of(17) } }",
                encoding="utf-8",
            )
            wrapper = module / "gradle/wrapper"
            wrapper.mkdir(parents=True)
            (wrapper / "gradle-wrapper.properties").write_text(
                "distributionUrl=https://services.gradle.org/distributions/gradle-8.2-bin.zip",
                encoding="utf-8",
            )
            profile = project_profile.build_profile(root, "auto", "auto")

        self.assertEqual("gradle", profile["buildSystem"])
        self.assertEqual("service", profile["projectRoot"])
        self.assertEqual("service/build.gradle.kts", profile["buildFile"])
        self.assertEqual("2.3.1", profile["cycloneDxGradleVersion"])
        self.assertFalse(profile["containerScan"])


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
                        "tool": "trivy-sca",
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
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            (source_root / "pom.xml").write_text(
                "<version>2.14.1</version>",
                encoding="utf-8",
            )
            payload = report_api.remediation_payload({
                "id": "CVE-2021-44228",
                "severity": "CRITICAL",
                "tool": "trivy-sca",
                "category": "SCA",
                "component": "log4j-core",
                "version": "2.14.1",
                "description": "Descripción recibida del analizador.",
                "fixedVersion": "2.17.1",
                "references": ["https://example.invalid"],
            }, source_root)

        self.assertEqual("CVE-2021-44228", payload["id"])
        self.assertEqual("2.17.1", payload["fixedVersion"])
        self.assertEqual("pom.xml", payload["affectedFile"])
        self.assertIn("2.14.1", payload["sourceContext"])
        self.assertNotIn("references", payload)

    def test_sast_context_rejects_paths_outside_src(self):
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            payload = report_api.remediation_payload({
                "id": "java-test",
                "severity": "HIGH",
                "tool": "semgrep",
                "category": "SAST",
                "file": "../.env",
                "description": "Hallazgo de prueba.",
            }, source_root)

        self.assertIsNone(payload["affectedFile"])
        self.assertIsNone(payload["sourceContext"])

    def test_container_java_dependency_uses_pom(self):
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            (source_root / "pom.xml").write_text("<project/>", encoding="utf-8")
            payload = report_api.remediation_payload({
                "id": "CVE-TEST",
                "severity": "LOW",
                "tool": "trivy",
                "category": "CONTAINER",
                "packageType": "jar",
                "component": "org.springframework:spring-webmvc",
                "description": "Hallazgo de prueba.",
            }, source_root)

        self.assertEqual("pom.xml", payload["affectedFile"])

    def test_sca_context_supports_gradle_projects(self):
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            (source_root / "build.gradle.kts").write_text(
                'plugins { id("org.springframework.boot") version "3.5.0" }',
                encoding="utf-8",
            )
            payload = report_api.remediation_payload({
                "id": "CVE-TEST",
                "severity": "HIGH",
                "tool": "trivy-sca",
                "category": "SCA",
                "component": "org.springframework:spring-webmvc",
                "description": "Hallazgo de prueba.",
            }, source_root)

        self.assertEqual("build.gradle.kts", payload["affectedFile"])

    def test_local_patch_uses_real_pom_lines_and_shows_the_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            (source_root / "pom.xml").write_text(
                "<project>\n  <properties>\n"
                "    <library.version>1.0.0</library.version>\n"
                "  </properties>\n</project>\n",
                encoding="utf-8",
            )
            result = report_api.local_patch_proposal(
                {"patchProposal": {"available": False}},
                {
                    "category": "SCA",
                    "component": "org.example:library",
                    "version": "1.0.0",
                    "fixedVersion": "1.1.0",
                },
                source_root,
            )

        patch = result["patchProposal"]["content"]
        self.assertIn("@@ -1,5 +1,5 @@", patch)
        self.assertIn("-    <library.version>1.0.0</library.version>", patch)
        self.assertIn("+    <library.version>1.1.0</library.version>", patch)

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
