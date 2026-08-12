import json
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class ShadowCampaignBackupTests(unittest.TestCase):
    def test_cli_creates_independently_validated_online_backup(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "campaign.db"
            backup = root / "backup.db"
            evidence = root / "backup.json"
            connection = sqlite3.connect(source)
            connection.executescript(
                """
                CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE settings (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE source_events (id TEXT PRIMARY KEY);
                INSERT INTO schema_migrations VALUES (25, 'current');
                INSERT INTO settings VALUES (1, '{"mode":"paper","kill_switch_enabled":true,"live_active_backend_armed":false,"live_session_acknowledged":false}');
                INSERT INTO source_events VALUES ('evt_1');
                """
            )
            connection.commit()
            connection.close()

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/test-shadow-campaign-backup.py",
                    "--database",
                    str(source),
                    "--backup",
                    str(backup),
                    "--evidence",
                    str(evidence),
                ],
                cwd=Path(__file__).parents[1],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            artifact = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertTrue(artifact["passed"])
            self.assertEqual(artifact["integrity_check"], "ok")
            self.assertEqual(artifact["source_events"], 1)
            self.assertEqual(artifact["schema_version"], 25)
            self.assertTrue(artifact["safety"]["paper_fail_closed"])

    def test_cli_refuses_to_overwrite_existing_backup(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "campaign.db"
            backup = root / "backup.db"
            sqlite3.connect(source).close()
            backup.write_bytes(b"preserve")

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/test-shadow-campaign-backup.py",
                    "--database",
                    str(source),
                    "--backup",
                    str(backup),
                    "--evidence",
                    str(root / "backup.json"),
                ],
                cwd=Path(__file__).parents[1],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(backup.read_bytes(), b"preserve")

    def test_cli_rejects_evidence_path_that_aliases_source_or_backup(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "campaign.db"
            sqlite3.connect(source).close()
            original = source.read_bytes()

            source_alias = subprocess.run(
                [
                    sys.executable,
                    "scripts/test-shadow-campaign-backup.py",
                    "--database",
                    str(source),
                    "--backup",
                    str(root / "backup.db"),
                    "--evidence",
                    str(source),
                ],
                cwd=Path(__file__).parents[1],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(source_alias.returncode, 0)
            self.assertEqual(source.read_bytes(), original)

            backup = root / "second-backup.db"
            backup_alias = subprocess.run(
                [
                    sys.executable,
                    "scripts/test-shadow-campaign-backup.py",
                    "--database",
                    str(source),
                    "--backup",
                    str(backup),
                    "--evidence",
                    str(backup),
                ],
                cwd=Path(__file__).parents[1],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(backup_alias.returncode, 0)
            self.assertFalse(backup.exists())


if __name__ == "__main__":
    unittest.main()
