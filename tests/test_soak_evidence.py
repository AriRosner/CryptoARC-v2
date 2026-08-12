import json
import sqlite3
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


class SoakEvidenceTests(unittest.TestCase):
    def test_build_campaign_evidence_is_deterministic_and_flags_anomalies(self) -> None:
        from app.core.soak_evidence import build_campaign_evidence

        observed_at = datetime(2026, 8, 12, 18, 30, tzinfo=timezone.utc)
        status = {
            "generated_at": (observed_at - timedelta(minutes=7)).isoformat(),
            "code_head": "expected",
            "mode": "paper",
            "live_trading_enabled": False,
            "live_execution_available": False,
            "source_trust": "trusted",
            "source_status": "connected",
            "data_counts": {"source_events": 120, "price_observations": 4},
            "economic_progress": {"sample_count": 4, "calendar_days": 1, "regimes": ["normal"]},
            "economic_ready": False,
        }
        previous = {
            **status,
            "generated_at": (observed_at - timedelta(minutes=8)).isoformat(),
            "data_counts": {"source_events": 121, "price_observations": 4},
        }

        first = build_campaign_evidence(
            status=status,
            database_counts={"source_events": 100, "price_observations": 4},
            database_safety={"mode": "paper", "kill_switch_enabled": True},
            code_head="different",
            observed_at=observed_at,
            previous_status=previous,
        )
        second = build_campaign_evidence(
            status=status,
            database_counts={"source_events": 100, "price_observations": 4},
            database_safety={"mode": "paper", "kill_switch_enabled": True},
            code_head="different",
            observed_at=observed_at,
            previous_status=previous,
        )

        self.assertEqual(first, second)
        finding_ids = {item["id"] for item in first["anomalies"]}
        self.assertEqual(
            finding_ids,
            {"code_head_drift", "database_count_behind_status", "monitor_stale", "source_events_regressed"},
        )
        self.assertFalse(first["readiness"]["economic_gate_ready"])
        self.assertEqual(first["readiness"]["required_samples"], 100)
        self.assertEqual(first["readiness"]["required_calendar_days"], 7)

    def test_redact_sensitive_values_recursively(self) -> None:
        from app.core.soak_evidence import redact_sensitive_values

        payload = {
            "api_key": "secret",
            "nested": {"private_key": "secret", "public_key": "safe"},
            "items": [{"token": "secret"}],
        }

        redacted = redact_sensitive_values(payload)

        self.assertEqual(redacted["api_key"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["private_key"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["public_key"], "safe")
        self.assertEqual(redacted["items"][0]["token"], "[REDACTED]")

    def test_cli_reads_database_without_writing_and_emits_json_and_markdown(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "campaign.db"
            status_path = root / "status.json"
            output = root / "output"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE settings (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE source_events (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                INSERT INTO settings VALUES (1, '{"mode":"paper","kill_switch_enabled":true}');
                INSERT INTO source_events VALUES ('evt_1', '{}');
                """
            )
            connection.commit()
            connection.close()
            status_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-08-12T18:30:00+00:00",
                        "code_head": "abc123",
                        "mode": "paper",
                        "live_trading_enabled": False,
                        "live_execution_available": False,
                        "data_counts": {"source_events": 1},
                        "economic_progress": {"sample_count": 0, "calendar_days": 0, "regimes": []},
                        "economic_ready": False,
                    }
                ),
                encoding="utf-8",
            )
            before = database.stat().st_mtime_ns

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/export-shadow-campaign-evidence.py",
                    "--database",
                    str(database),
                    "--status",
                    str(status_path),
                    "--output-dir",
                    str(output),
                    "--code-head",
                    "abc123",
                    "--observed-at",
                    "2026-08-12T18:30:00+00:00",
                ],
                cwd=Path(__file__).parents[1],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(database.stat().st_mtime_ns, before)
            self.assertTrue((output / "shadow-campaign-evidence.json").is_file())
            self.assertTrue((output / "shadow-campaign-evidence.md").is_file())
            artifact = json.loads((output / "shadow-campaign-evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(artifact["database"]["counts"]["source_events"], 1)
            self.assertTrue(artifact["safety"]["authority_unchanged"])


if __name__ == "__main__":
    unittest.main()
