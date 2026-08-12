from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SENSITIVE_KEY_PARTS = (
    "api_key",
    "secret",
    "private_key",
    "seed",
    "mnemonic",
    "access_token",
    "auth_token",
    "bearer_token",
    "refresh_token",
    "password",
)


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def redact_sensitive_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if any(part in str(key).lower() for part in SENSITIVE_KEY_PARTS)
                else redact_sensitive_values(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_values(item) for item in value]
    return value


def read_database_snapshot(database_path: str | Path) -> tuple[dict[str, int], dict[str, object]]:
    path = Path(database_path).resolve()
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        count_tables = (
            "source_events",
            "price_observations",
            "tokens",
            "trades",
            "live_execution_audits",
            "shadow_economic_comparisons",
        )
        counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in count_tables
            if table in tables
        }
        settings: dict[str, object] = {}
        if "settings" in tables:
            row = connection.execute("SELECT payload FROM settings WHERE id = 1").fetchone()
            if row:
                settings = json.loads(str(row[0]))
        safety = {
            "mode": str(settings.get("mode") or "unknown"),
            "kill_switch_enabled": bool(settings.get("kill_switch_enabled", False)),
            "live_active_backend_armed": bool(settings.get("live_active_backend_armed", False)),
            "live_session_acknowledged": bool(settings.get("live_session_acknowledged", False)),
        }
        return counts, safety
    finally:
        connection.close()


def _finding(finding_id: str, severity: str, message: str) -> dict[str, str]:
    return {"id": finding_id, "severity": severity, "message": message}


def build_campaign_evidence(
    *,
    status: dict[str, object],
    database_counts: dict[str, int],
    database_safety: dict[str, object],
    code_head: str,
    observed_at: datetime,
    previous_status: dict[str, object] | None = None,
) -> dict[str, object]:
    observed_at = observed_at.astimezone(timezone.utc)
    status_time = _parse_time(status.get("generated_at"))
    status_counts = status.get("data_counts") if isinstance(status.get("data_counts"), dict) else {}
    previous_counts = (
        previous_status.get("data_counts")
        if isinstance(previous_status, dict) and isinstance(previous_status.get("data_counts"), dict)
        else {}
    )
    anomalies: list[dict[str, str]] = []
    if str(status.get("code_head") or "") != code_head:
        anomalies.append(_finding("code_head_drift", "error", "Monitor code head differs from the inspected checkout."))
    status_age_seconds = (observed_at - status_time).total_seconds() if status_time is not None else None
    if status_age_seconds is None or status_age_seconds > 300 or status_age_seconds < -30:
        anomalies.append(_finding("monitor_stale", "error", "Monitor status is more than five minutes old or has no valid timestamp."))
    for name, value in sorted(status_counts.items()):
        if name in database_counts and int(database_counts[name]) < int(value or 0):
            anomalies.append(_finding("database_count_behind_status", "error", f"Database {name} count is behind the monitor status."))
            break
    for name, value in sorted(status_counts.items()):
        if name in previous_counts and int(value or 0) < int(previous_counts[name] or 0):
            anomalies.append(_finding(f"{name}_regressed", "error", f"Monitor {name} count moved backward."))

    progress = status.get("economic_progress") if isinstance(status.get("economic_progress"), dict) else {}
    sample_count = int(progress.get("sample_count", 0) or 0)
    calendar_days = int(progress.get("calendar_days", 0) or 0)
    regime_count = len(progress.get("regimes", [])) if isinstance(progress.get("regimes"), list) else 0
    authority_unchanged = (
        status.get("mode") == "paper"
        and status.get("live_trading_enabled") is False
        and status.get("live_execution_available") is False
        and database_safety.get("mode") == "paper"
        and database_safety.get("kill_switch_enabled") is True
        and database_safety.get("live_active_backend_armed") is not True
        and database_safety.get("live_session_acknowledged") is not True
    )
    return redact_sensitive_values(
        {
            "artifact_type": "cryptoarc_shadow_campaign_evidence",
            "format_version": 1,
            "observed_at": observed_at.isoformat(),
            "code": {"head": code_head, "matches_monitor": str(status.get("code_head") or "") == code_head},
            "safety": {
                "authority_unchanged": authority_unchanged,
                "status": {
                    "mode": status.get("mode"),
                    "live_trading_enabled": status.get("live_trading_enabled"),
                    "live_execution_available": status.get("live_execution_available"),
                },
                "database": database_safety,
            },
            "database": {"counts": database_counts},
            "monitor": status,
            "readiness": {
                "sample_count": sample_count,
                "required_samples": 100,
                "calendar_days": calendar_days,
                "required_calendar_days": 7,
                "regime_count": regime_count,
                "multiple_regimes_required": True,
                "economic_gate_ready": bool(status.get("economic_ready")) and sample_count >= 100 and calendar_days >= 7 and regime_count >= 2,
            },
            "anomalies": sorted(anomalies, key=lambda item: item["id"]),
        }
    )


def render_markdown(artifact: dict[str, object]) -> str:
    readiness = artifact["readiness"]
    anomalies = artifact["anomalies"]
    safety = artifact["safety"]
    lines = [
        "# CryptoARC Shadow Campaign Evidence",
        "",
        f"Observed: {artifact['observed_at']}",
        f"Authority unchanged: {safety['authority_unchanged']}",
        f"Economic samples: {readiness['sample_count']} / {readiness['required_samples']}",
        f"Calendar days: {readiness['calendar_days']} / {readiness['required_calendar_days']}",
        f"Economic gate ready: {readiness['economic_gate_ready']}",
        "",
        "## Anomalies",
        "",
    ]
    lines.extend(
        [f"- [{item['severity']}] {item['id']}: {item['message']}" for item in anomalies]
        or ["- None detected."]
    )
    return "\n".join(lines) + "\n"
