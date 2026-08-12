from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and independently validate a SQLite campaign backup.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    source_path = Path(args.database).resolve()
    backup_path = Path(args.backup).resolve()
    evidence_path = Path(args.evidence).resolve()
    if len({source_path, backup_path, evidence_path}) != 3:
        parser.error("database, backup, and evidence paths must be distinct")
    if backup_path.exists():
        parser.error(f"backup already exists: {backup_path}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target, pages=4096, sleep=0.01)
    finally:
        target.close()
        source.close()

    validation = sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True)
    try:
        integrity = str(validation.execute("PRAGMA integrity_check").fetchone()[0])
        quick_check = str(validation.execute("PRAGMA quick_check").fetchone()[0])
        schema_version = (
            int(validation.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0)
            if table_exists(validation, "schema_migrations")
            else 0
        )
        source_events = (
            int(validation.execute("SELECT COUNT(*) FROM source_events").fetchone()[0])
            if table_exists(validation, "source_events")
            else 0
        )
        settings: dict[str, object] = {}
        if table_exists(validation, "settings"):
            row = validation.execute("SELECT payload FROM settings WHERE id = 1").fetchone()
            if row:
                settings = json.loads(str(row[0]))
    finally:
        validation.close()

    paper_fail_closed = (
        settings.get("mode") == "paper"
        and settings.get("kill_switch_enabled") is True
        and settings.get("live_active_backend_armed") is not True
        and settings.get("live_session_acknowledged") is not True
    )
    artifact = {
        "artifact_type": "cryptoarc_shadow_campaign_backup_validation",
        "format_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database": str(source_path),
        "backup": str(backup_path),
        "backup_bytes": backup_path.stat().st_size,
        "integrity_check": integrity,
        "quick_check": quick_check,
        "schema_version": schema_version,
        "source_events": source_events,
        "safety": {
            "mode": settings.get("mode", "unknown"),
            "kill_switch_enabled": settings.get("kill_switch_enabled"),
            "live_active_backend_armed": settings.get("live_active_backend_armed", False),
            "live_session_acknowledged": settings.get("live_session_acknowledged", False),
            "paper_fail_closed": paper_fail_closed,
        },
        "passed": integrity == "ok" and quick_check == "ok" and paper_fail_closed,
    }
    evidence_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(evidence_path))
    return 0 if artifact["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
