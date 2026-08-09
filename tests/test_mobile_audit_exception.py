from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit-mobile.ps1"
POLICY = ROOT / "scripts" / "mobile-audit-exception.json"
DECISION = ROOT / "docs" / "security" / "mobile-image-size-risk-acceptance.md"


def current_audit() -> dict[str, object]:
    cascade = [
        "@expo/cli",
        "@expo/metro",
        "@expo/metro-config",
        "@react-native/community-cli-plugin",
        "expo",
        "image-size",
        "metro",
        "metro-config",
        "metro-transform-worker",
        "react-native",
    ]
    vulnerabilities: dict[str, object] = {}
    for name in cascade:
        vulnerabilities[name] = {
            "name": name,
            "severity": "high",
            "isDirect": name in {"expo", "react-native"},
            "via": ["image-size"],
            "nodes": [f"node_modules/{name}"],
            "fixAvailable": True,
        }
    vulnerabilities["image-size"] = {
        "name": "image-size",
        "severity": "high",
        "isDirect": False,
        "via": [
            {
                "name": "image-size",
                "url": "https://github.com/advisories/GHSA-w3rx-r6r6-pgpr",
                "severity": "high",
            },
            {
                "name": "image-size",
                "url": "https://github.com/advisories/GHSA-5p2g-fcmc-qvqq",
                "severity": "high",
            },
        ],
        "nodes": ["node_modules/image-size"],
        "fixAvailable": {
            "name": "expo",
            "version": "53.0.27",
            "isSemVerMajor": True,
        },
    }
    return {
        "auditReportVersion": 2,
        "vulnerabilities": vulnerabilities,
        "metadata": {
            "vulnerabilities": {
                "info": 0,
                "low": 0,
                "moderate": 0,
                "high": 10,
                "critical": 0,
                "total": 10,
            }
        },
    }


class MobileAuditExceptionTests(unittest.TestCase):
    def run_policy(
        self,
        audit: dict[str, object],
        as_of: str,
        *,
        allow_fixture: bool = True,
    ) -> tuple[int, dict[str, object]]:
        self.assertTrue(SCRIPT.exists(), "mobile audit policy script is missing")
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(powershell, "PowerShell is required for the mobile audit policy")
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.json"
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            environment = os.environ.copy()
            if allow_fixture:
                environment["CRYPTOARC_AUDIT_FIXTURE_TEST"] = "true"
            else:
                environment.pop("CRYPTOARC_AUDIT_FIXTURE_TEST", None)
            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPT),
                    "-Json",
                    "-Strict",
                    "-AuditJsonPath",
                    str(audit_path),
                    "-AsOfUtc",
                    as_of,
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
        output = result.stdout.strip()
        report = json.loads(output) if output else {}
        return result.returncode, report

    def test_exception_contract_is_explicit_and_time_bounded(self) -> None:
        self.assertTrue(SCRIPT.exists())
        self.assertTrue(POLICY.exists())
        policy = json.loads(POLICY.read_text(encoding="utf-8"))

        self.assertEqual(policy["package"], "image-size")
        self.assertEqual(policy["installed_version"], "1.2.1")
        self.assertEqual(policy.get("known_latest_compatible_version"), "1.2.1")
        self.assertEqual(policy["known_latest_version"], "2.0.2")
        self.assertEqual(
            set(policy["advisories"]),
            {"GHSA-w3rx-r6r6-pgpr", "GHSA-5p2g-fcmc-qvqq"},
        )
        self.assertEqual(policy["expires_at"], "2026-11-07T23:59:59Z")

    def test_risk_acceptance_documents_boundary_and_removal_criteria(self) -> None:
        self.assertTrue(DECISION.exists())
        decision = DECISION.read_text(encoding="utf-8")

        self.assertIn("build-time availability", decision)
        self.assertIn("not a mobile runtime dependency", decision)
        self.assertIn("2026-11-07T23:59:59Z", decision)
        self.assertIn("GHSA-w3rx-r6r6-pgpr", decision)
        self.assertIn("GHSA-5p2g-fcmc-qvqq", decision)
        self.assertIn("Remove the exception", decision)

    def test_exact_known_audit_is_review_not_blocked(self) -> None:
        code, report = self.run_policy(current_audit(), "2026-08-09T12:00:00Z")

        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "review")
        self.assertTrue(report["exception"]["active"])
        self.assertEqual(report["blockers"], [])

    def test_unexpected_advisory_fails_closed(self) -> None:
        audit = current_audit()
        vulnerabilities = audit["vulnerabilities"]
        assert isinstance(vulnerabilities, dict)
        vulnerabilities["unexpected-package"] = {
            "name": "unexpected-package",
            "severity": "critical",
            "isDirect": False,
            "via": [],
            "nodes": ["node_modules/unexpected-package"],
            "fixAvailable": False,
        }
        counts = audit["metadata"]["vulnerabilities"]
        assert isinstance(counts, dict)
        counts.update({"high": 10, "critical": 1, "total": 11})

        code, report = self.run_policy(audit, "2026-08-09T12:00:00Z")

        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(report["blockers"])

    def test_expired_exception_fails_closed(self) -> None:
        code, report = self.run_policy(current_audit(), "2026-11-08T00:00:00Z")

        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("expired", " ".join(report["blockers"]).lower())

    def test_fixture_input_requires_explicit_test_mode(self) -> None:
        code, report = self.run_policy(
            current_audit(),
            "2026-08-09T12:00:00Z",
            allow_fixture=False,
        )

        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("test-only", " ".join(report["blockers"]).lower())


if __name__ == "__main__":
    unittest.main()
