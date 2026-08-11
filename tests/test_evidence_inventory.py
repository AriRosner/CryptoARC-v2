from __future__ import annotations

import copy
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import AuthManager
from app.core.evidence_inventory import EvidenceInventory
from app.core.state import BotState


ROOT = Path(__file__).resolve().parents[1]


class EvidenceInventoryTests(unittest.TestCase):
    def representative_reports(self) -> dict[str, object]:
        return {
            "readiness": {
                "status": "warning",
                "recommended_actions": ["collect paper evidence"],
                "strategy_promotion": {
                    "status": "blocked",
                    "strategy_fingerprint": "sha256:strategy-v1",
                    "blockers": ["drawdown exceeds target"],
                },
                "execution_readiness": {
                    "status": "collecting_quotes",
                    "blockers": ["five recent shadow quotes required"],
                },
            },
            "live": {
                "env_live_enabled": False,
                "blockers": ["LIVE_TRADING_ENABLED is false"],
                "pre_run_backup": {"state": "stale", "age_seconds": 90_000},
                "signer": {"mode": "local_signer_daemon", "status": "offline"},
            },
            "evidence_mode": {
                "status": "clear",
                "modes": [
                    {"mode": "paper", "samples": 30},
                    {"mode": "shadow", "samples": 7, "evaluated": 5},
                ],
                "contamination_warnings": [],
            },
            "pilot": {
                "ready": False,
                "status": "blocked",
                "signer_mode": "local_signer_daemon",
                "blockers": ["manual-live proof required"],
            },
            "post_run": {
                "ready": False,
                "status": "missing_evidence",
                "action_items": ["No live audits were found for this timeframe."],
            },
            "source_adapters": [
                {
                    "name": "pumpportal",
                    "status": "available",
                    "capabilities": ["launches", "trades", "raw_events"],
                }
            ],
            "source": {
                "access_state": "not_configured",
                "observations": [
                    {"id": "fixture", "accepted": True, "fixture_only": True},
                    {"id": "genuine", "accepted": True, "fixture_only": False},
                    {"id": "rejected", "accepted": False, "fixture_only": False},
                ],
            },
            "active_strategy": {"id": "sniper", "version": "v1"},
        }

    def test_inventory_keeps_fixture_rows_out_of_genuine_evidence(self) -> None:
        report = EvidenceInventory.build(
            repo_head="abc",
            origin_main="base",
            merge_base="base",
            dirty=False,
            reports=self.representative_reports(),
        )

        self.assertEqual(report["evidence"]["genuine_source_observations"], 1)
        self.assertEqual(report["evidence"]["fixture_source_observations"], 1)
        self.assertEqual(report["evidence"]["rejected_source_observations"], 1)
        self.assertIn("genuine source soak", report["deferred_physical_evidence"])

    def test_inventory_summarizes_code_evidence_and_blockers_without_mutating_inputs(self) -> None:
        reports = self.representative_reports()
        original = copy.deepcopy(reports)

        report = EvidenceInventory.build(
            repo_head="abc",
            origin_main="base",
            merge_base="base",
            dirty=False,
            reports=reports,
        )

        self.assertEqual(reports, original)
        self.assertEqual(
            report["code_state"],
            {
                "head": "abc",
                "origin_main": "base",
                "merge_base": "base",
                "dirty": False,
                "origin_main_is_ancestor": True,
                "exact_main_state_captured": True,
            },
        )
        self.assertEqual(report["active_strategy"]["id"], "sniper")
        self.assertEqual(report["active_strategy"]["version"], "v1")
        self.assertEqual(report["active_strategy"]["fingerprint"], "sha256:strategy-v1")
        self.assertEqual(report["source_access"]["state"], "not_configured")
        self.assertEqual(report["evidence"]["shadow_samples"], 7)
        self.assertEqual(report["evidence"]["evaluated_shadow_samples"], 5)
        self.assertEqual(report["operations"]["backup_age_hours"], 25.0)
        self.assertEqual(report["operations"]["signer_mode"], "local_signer_daemon")
        self.assertFalse(report["machine_verifiable_readiness"]["ready"])
        self.assertIn("drawdown exceeds target", report["machine_verifiable_readiness"]["blockers"])
        self.assertIn("manual-live proof required", report["machine_verifiable_readiness"]["blockers"])
        self.assertFalse(report["authority"]["live_trading_enabled"])
        self.assertFalse(report["authority"]["authority_changed"])

    def test_inventory_fails_closed_when_reports_or_git_state_are_missing(self) -> None:
        report = EvidenceInventory.build(
            repo_head="",
            origin_main="",
            merge_base="",
            dirty=None,
            reports={},
        )

        self.assertFalse(report["code_state"]["exact_main_state_captured"])
        self.assertFalse(report["machine_verifiable_readiness"]["ready"])
        self.assertEqual(report["source_access"]["state"], "unknown")
        self.assertEqual(report["evidence"]["genuine_source_observations"], 0)
        self.assertIn("exact Git state was not supplied", report["machine_verifiable_readiness"]["blockers"])

    def test_bot_state_composes_existing_reports_into_inventory(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            reports = self.representative_reports()
            with (
                patch.object(state, "readiness_status", return_value=reports["readiness"]),
                patch.object(state, "live_status", return_value=reports["live"]),
                patch.object(state, "evidence_mode_separation_report", return_value=reports["evidence_mode"]),
                patch.object(state, "pilot_readiness_report", return_value=reports["pilot"]),
                patch.object(state, "post_run_review_report", return_value=reports["post_run"]),
                patch.object(state, "source_adapters", return_value=reports["source_adapters"]),
            ):
                report = state.evidence_inventory_report(
                    repo_state={"head": "abc", "origin_main": "base", "merge_base": "base", "dirty": False},
                    env_live_enabled=False,
                    signer_mode="local_signer_daemon",
                    local_auth_enabled=True,
                )

        self.assertEqual(report["code_state"]["head"], "abc")
        self.assertEqual(report["active_strategy"]["fingerprint"], "sha256:strategy-v1")
        self.assertEqual(report["evidence"]["evaluated_shadow_samples"], 5)

    def test_authenticated_endpoint_is_read_only_and_fails_closed_without_git_capture(self) -> None:
        from app import main as main_app

        with TemporaryDirectory() as directory:
            previous_state = main_app.state
            previous_auth = main_app.auth
            main_app.state = BotState(database_path=str(Path(directory) / "test.db"))
            main_app.auth = AuthManager(password="desktop-pass")
            token = main_app.auth.login("desktop-pass")
            try:
                client = TestClient(main_app.app)
                denied = client.get("/api/reports/evidence-inventory")
                allowed = client.get(
                    "/api/reports/evidence-inventory",
                    headers={"Authorization": f"Bearer {token}"},
                )
            finally:
                main_app.state = previous_state
                main_app.auth = previous_auth

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 200)
        payload = allowed.json()
        self.assertEqual(payload["artifact_type"], "cryptoarc_evidence_inventory")
        self.assertFalse(payload["code_state"]["exact_main_state_captured"])
        self.assertFalse(payload["authority"]["live_trading_enabled"])
        self.assertFalse(payload["authority"]["authority_changed"])

    def test_capture_script_and_runbook_preserve_no_runtime_boundary(self) -> None:
        script = (ROOT / "scripts" / "capture-evidence-inventory.ps1").read_text(encoding="utf-8")
        runbook = (ROOT / "docs" / "manual" / "16-evidence-campaign.md").read_text(encoding="utf-8")

        self.assertIn("[string]$BaseRef = 'origin/main'", script)
        self.assertIn("[string]$OutputPath", script)
        self.assertIn("git -C $root status --porcelain", script)
        self.assertIn("git -C $root merge-base HEAD $BaseRef", script)
        self.assertIn("exact_main_state_captured", script)
        self.assertNotIn("start-dev.ps1", script)
        self.assertNotIn("Invoke-RestMethod", script)
        self.assertNotIn("LIVE_TRADING_ENABLED=true", script)
        for marker in (
            "Genuine source soak: DEFERRED",
            "Shadow campaign: DEFERRED",
            "Production rehearsal: DEFERRED",
            "Manual-live proof: DEFERRED",
            "Autonomous-live pilot: DEFERRED",
        ):
            self.assertIn(marker, runbook)

    def test_capture_script_recognizes_a_linked_git_worktree(self) -> None:
        with TemporaryDirectory() as directory:
            fixture_root = Path(directory)
            repository = fixture_root / "repository"
            linked_worktree = fixture_root / "linked"
            scripts = repository / "scripts"
            scripts.mkdir(parents=True)
            shutil.copy2(
                ROOT / "scripts" / "capture-evidence-inventory.ps1",
                scripts / "capture-evidence-inventory.ps1",
            )
            for command in (
                ["git", "init", "-q", str(repository)],
                ["git", "-C", str(repository), "config", "user.email", "fixture@example.invalid"],
                ["git", "-C", str(repository), "config", "user.name", "Fixture"],
                ["git", "-C", str(repository), "add", "scripts/capture-evidence-inventory.ps1"],
                ["git", "-C", str(repository), "commit", "-q", "-m", "fixture"],
                ["git", "-C", str(repository), "worktree", "add", "-q", "-b", "linked-fixture", str(linked_worktree)],
            ):
                subprocess.run(command, check=True, capture_output=True, text=True)

            script = linked_worktree / "scripts" / "capture-evidence-inventory.ps1"
            clean_output = fixture_root / "clean.json"
            clean = subprocess.run(
                ["powershell.exe", "-NoProfile", "-File", str(script), "-BaseRef", "HEAD", "-OutputPath", str(clean_output)],
                cwd=linked_worktree,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertTrue(clean_output.exists())

            (linked_worktree / "dirty-marker.txt").write_text("dirty", encoding="utf-8")
            dirty = subprocess.run(
                ["powershell.exe", "-NoProfile", "-File", str(script), "-BaseRef", "HEAD", "-OutputPath", str(fixture_root / "must-not-write.json")],
                cwd=linked_worktree,
                capture_output=True,
                text=True,
                check=False,
            )

            output = f"{dirty.stdout}\n{dirty.stderr}"
            self.assertNotEqual(dirty.returncode, 0)
            self.assertIn("requires a clean worktree", output)
            self.assertNotIn("Not a Git worktree", output)


if __name__ == "__main__":
    unittest.main()
