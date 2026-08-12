from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def analyze_database(
    database_path: str | Path,
    *,
    strategy_version: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    path = Path(database_path).resolve()
    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = _tables(connection)
        audits: list[tuple[str, str, datetime]] = []
        versions: dict[str, int] = defaultdict(int)
        for row in connection.execute("SELECT id, created_at, payload FROM live_execution_audits"):
            payload = json.loads(row["payload"])
            comparison = payload.get("shadow_comparison") or {}
            if not payload.get("quote", {}).get("shadow_only"):
                continue
            version = str(comparison.get("strategy_version") or "")
            versions[version] += 1
            audits.append((str(row["id"]), version, datetime.fromisoformat(row["created_at"])))

        selected_version = strategy_version or (
            max(versions, key=versions.get) if versions else ""
        )
        selected = [row for row in audits if not selected_version or row[1] == selected_version]
        bindings: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if "shadow_market_evidence_bindings" in tables:
            for row in connection.execute("SELECT audit_id, payload FROM shadow_market_evidence_bindings"):
                bindings[str(row["audit_id"])].append(json.loads(row["payload"]))
        entry_covered = sum(
            1 for audit_id, _, _ in selected if any(item.get("role") == "entry" for item in bindings[audit_id])
        )
        followup_covered = sum(
            1 for audit_id, _, _ in selected if any(item.get("role") == "path" for item in bindings[audit_id])
        )
        economic_samples = 0
        if "shadow_economic_comparisons" in tables:
            for row in connection.execute("SELECT payload FROM shadow_economic_comparisons"):
                payload = json.loads(row["payload"])
                if not selected_version or payload.get("strategy_version") == selected_version:
                    economic_samples += 1
        started_at = min((created for _, _, created in selected), default=None)
        current = now or datetime.now(timezone.utc)
        elapsed_days = max(
            ((current - started_at).total_seconds() / 86400) if started_at else 0.0,
            0.0,
        )
        samples_per_day = economic_samples / elapsed_days if elapsed_days > 0 else 0.0
        lifecycle = None
        if "shadow_tracking_candidates" in tables:
            lifecycle = {
                str(row["state"]): int(row["count"])
                for row in connection.execute(
                    "SELECT state, COUNT(*) AS count FROM shadow_tracking_candidates GROUP BY state"
                )
            }
        subscription_cap = None
        if "settings" in tables:
            row = connection.execute("SELECT payload FROM settings LIMIT 1").fetchone()
            if row:
                subscription_cap = json.loads(row["payload"]).get("max_trade_subscriptions")
        return {
            "database": str(path),
            "read_only": True,
            "strategy_version": selected_version,
            "candidates": len(selected),
            "entry_covered": entry_covered,
            "followup_covered": followup_covered,
            "economic_samples": economic_samples,
            "elapsed_days": round(elapsed_days, 4),
            "projected_samples_per_day": round(samples_per_day, 3),
            "projected_seven_day_samples": round(samples_per_day * 7, 1),
            "candidate_lifecycle": lifecycle,
            "configured_subscription_cap": subscription_cap,
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze genuine shadow candidate coverage read-only.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--strategy-version", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = analyze_database(args.database, strategy_version=args.strategy_version)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
