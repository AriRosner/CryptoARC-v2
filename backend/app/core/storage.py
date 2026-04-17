from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.core.models import BacktestRun, BotMode, BotSettings, ExperimentRun, LiveExecutionRequest, PriceObservation, SettingsVersion, SourceEvent, StrategyDecisionRecord, StrategyPreset, TokenSignal, TokenStatus, TradeEvent, TradeLabel, TradeRecord, TradeSession


class Storage:
    SCHEMA_VERSION = 3

    def __init__(self, path: str = "data/cryptoarc.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tokens (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    detected_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS source_events (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    received_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    token_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    opened_at TEXT,
                    closed_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS price_observations (
                    id TEXT PRIMARY KEY,
                    mint TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_decisions (
                    id TEXT PRIMARY KEY,
                    token_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_sessions (
                    id TEXT PRIMARY KEY,
                    token_id TEXT NOT NULL,
                    mint TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    opened_at TEXT,
                    closed_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS settings_versions (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            for table in ("experiment_runs", "trade_labels", "strategy_presets"):
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS live_execution_requests (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (self.SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )

    def schema_status(self) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute("SELECT version, applied_at FROM schema_migrations ORDER BY version").fetchall()
        current = max([int(row["version"]) for row in rows], default=0)
        return {
            "current_version": current,
            "expected_version": self.SCHEMA_VERSION,
            "ok": current >= self.SCHEMA_VERSION,
            "migrations": [{"version": int(row["version"]), "applied_at": row["applied_at"]} for row in rows],
        }

    def backup(self) -> dict[str, str]:
        if not self.path.exists():
            return {"status": "missing", "path": ""}
        backup_path = self.path.with_suffix(f".backup-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{self.path.suffix}")
        backup_path.write_bytes(self.path.read_bytes())
        return {"status": "created", "path": str(backup_path)}
    def load_settings(self) -> BotSettings:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM settings WHERE id = 1").fetchone()
        if not row:
            return BotSettings()
        payload = json.loads(row["payload"])
        allowed = set(asdict(BotSettings()).keys())
        normalized = {key: value for key, value in payload.items() if key in allowed}
        if "mode" in normalized:
            normalized["mode"] = BotMode(normalized["mode"])
        defaults = asdict(BotSettings())
        defaults.update(normalized)
        return BotSettings(**defaults)

    def has_settings(self) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT 1 FROM settings WHERE id = 1").fetchone()
        return row is not None

    def save_settings(self, settings: BotSettings) -> None:
        payload = json.dumps(asdict(settings))
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO settings (id, payload) VALUES (1, ?)",
                (payload,),
            )

    def load_settings_versions(self, limit: int = 50) -> list[SettingsVersion]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM settings_versions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._settings_version_from_payload(json.loads(row["payload"])) for row in rows]

    def count_settings_versions(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM settings_versions").fetchone()
        return int(row["count"] if row else 0)

    def count_experiment_runs(self) -> int:
        return self._count_table("experiment_runs")

    def count_trade_labels(self) -> int:
        return self._count_table("trade_labels")

    def count_strategy_presets(self) -> int:
        return self._count_table("strategy_presets")

    def count_live_execution_requests(self) -> int:
        return self._count_table("live_execution_requests")

    def _count_table(self, table: str) -> int:
        with self._connect() as connection:
            row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"] if row else 0)

    def save_settings_version(self, version: SettingsVersion) -> None:
        payload = json.dumps(version.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO settings_versions (id, payload, created_at) VALUES (?, ?, ?)",
                (version.id, payload, version.created_at.isoformat()),
            )

    def load_experiment_runs(self, limit: int = 50) -> list[ExperimentRun]:
        return [self._experiment_from_payload(payload) for payload in self._load_payloads("experiment_runs", limit)]

    def save_experiment_run(self, run: ExperimentRun) -> None:
        self._save_payload("experiment_runs", run.id, run.to_dict(), run.created_at)

    def load_trade_labels(self, limit: int = 500) -> list[TradeLabel]:
        return [self._trade_label_from_payload(payload) for payload in self._load_payloads("trade_labels", limit)]

    def save_trade_label(self, label: TradeLabel) -> None:
        self._save_payload("trade_labels", label.id, label.to_dict(), label.created_at)

    def load_strategy_presets(self, limit: int = 50) -> list[StrategyPreset]:
        return [self._strategy_preset_from_payload(payload) for payload in self._load_payloads("strategy_presets", limit)]

    def save_strategy_preset(self, preset: StrategyPreset) -> None:
        self._save_payload("strategy_presets", preset.id, preset.to_dict(), preset.created_at)

    def load_live_execution_requests(self, limit: int = 100) -> list[LiveExecutionRequest]:
        return [self._live_execution_request_from_payload(payload) for payload in self._load_payloads("live_execution_requests", limit)]

    def save_live_execution_request(self, request: LiveExecutionRequest) -> None:
        self._save_payload("live_execution_requests", request.id, request.to_dict(), request.created_at)

    def _load_payloads(self, table: str, limit: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(f"SELECT payload FROM {table} ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def _save_payload(self, table: str, item_id: str, payload: dict[str, Any], created_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                f"INSERT OR REPLACE INTO {table} (id, payload, created_at) VALUES (?, ?, ?)",
                (item_id, json.dumps(payload), created_at.isoformat()),
            )

    def load_tokens(self, limit: int = 80) -> list[TokenSignal]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM tokens ORDER BY detected_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._token_from_payload(json.loads(row["payload"])) for row in rows]

    def load_all_tokens(self, limit: int = 5000) -> list[TokenSignal]:
        return self.load_tokens(limit)

    def count_tokens(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM tokens").fetchone()
        return int(row["count"] if row else 0)

    def save_token(self, token: TokenSignal) -> None:
        payload = json.dumps(token.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO tokens (id, payload, detected_at) VALUES (?, ?, ?)",
                (token.id, payload, token.detected_at.isoformat()),
            )

    def load_events(self, limit: int = 30) -> list[TradeEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._event_from_payload(json.loads(row["payload"])) for row in rows]

    def load_all_events(self, limit: int = 5000) -> list[TradeEvent]:
        return self.load_events(limit)

    def count_events(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM events").fetchone()
        return int(row["count"] if row else 0)

    def save_event(self, event: TradeEvent) -> None:
        payload = json.dumps(event.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO events (id, payload, created_at) VALUES (?, ?, ?)",
                (event.id, payload, event.created_at.isoformat()),
            )

    def load_source_events(self, limit: int = 200) -> list[SourceEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM source_events ORDER BY received_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._source_event_from_payload(json.loads(row["payload"])) for row in rows]

    def count_source_events(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM source_events").fetchone()
        return int(row["count"] if row else 0)

    def save_source_event(self, event: SourceEvent) -> None:
        payload = json.dumps(event.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO source_events (id, source, payload, received_at) VALUES (?, ?, ?, ?)",
                (event.id, event.source, payload, event.received_at.isoformat()),
            )

    def load_backtest_runs(self, limit: int = 20) -> list[BacktestRun]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM backtest_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._backtest_from_payload(json.loads(row["payload"])) for row in rows]

    def count_backtest_runs(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM backtest_runs").fetchone()
        return int(row["count"] if row else 0)

    def load_trades(self, limit: int = 500) -> list[TradeRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM trades ORDER BY COALESCE(closed_at, opened_at) DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._trade_from_payload(json.loads(row["payload"])) for row in rows]

    def count_trades(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM trades").fetchone()
        return int(row["count"] if row else 0)

    def load_price_observations(self, limit: int = 1000, mint: str | None = None) -> list[PriceObservation]:
        with self._connect() as connection:
            if mint:
                rows = connection.execute(
                    "SELECT payload FROM price_observations WHERE mint = ? ORDER BY observed_at ASC LIMIT ?",
                    (mint, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload FROM price_observations ORDER BY observed_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._price_observation_from_payload(json.loads(row["payload"])) for row in rows]

    def save_price_observation(self, observation: PriceObservation) -> None:
        payload = json.dumps(observation.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO price_observations (id, mint, payload, observed_at) VALUES (?, ?, ?, ?)",
                (observation.id, observation.mint, payload, observation.observed_at.isoformat()),
            )

    def count_price_observations(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM price_observations").fetchone()
        return int(row["count"] if row else 0)

    def load_strategy_decisions(self, limit: int = 300) -> list[StrategyDecisionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM strategy_decisions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._strategy_decision_from_payload(json.loads(row["payload"])) for row in rows]

    def save_strategy_decision(self, decision: StrategyDecisionRecord) -> None:
        payload = json.dumps(decision.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO strategy_decisions (id, token_id, payload, created_at) VALUES (?, ?, ?, ?)",
                (decision.id, decision.token_id, payload, decision.created_at.isoformat()),
            )

    def count_strategy_decisions(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM strategy_decisions").fetchone()
        return int(row["count"] if row else 0)

    def load_trade_sessions(self, limit: int = 300) -> list[TradeSession]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM trade_sessions ORDER BY COALESCE(closed_at, opened_at) DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._trade_session_from_payload(json.loads(row["payload"])) for row in rows]

    def save_trade_session(self, session: TradeSession) -> None:
        payload = json.dumps(session.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO trade_sessions (id, token_id, mint, payload, opened_at, closed_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session.id,
                    session.token_id,
                    session.mint,
                    payload,
                    session.opened_at.isoformat() if session.opened_at else None,
                    session.closed_at.isoformat() if session.closed_at else None,
                ),
            )

    def count_trade_sessions(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM trade_sessions").fetchone()
        return int(row["count"] if row else 0)

    def save_backtest_run(self, run: BacktestRun) -> None:
        payload = json.dumps(run.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO backtest_runs (id, payload, created_at) VALUES (?, ?, ?)",
                (run.id, payload, run.created_at.isoformat()),
            )

    def save_trade(self, trade: TradeRecord) -> None:
        payload = json.dumps(trade.to_dict())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO trades (id, token_id, payload, opened_at, closed_at) VALUES (?, ?, ?, ?, ?)",
                (
                    trade.id,
                    trade.token_id,
                    payload,
                    trade.opened_at.isoformat() if trade.opened_at else None,
                    trade.closed_at.isoformat() if trade.closed_at else None,
                ),
            )

    def clear_tokens(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM tokens")

    def clear_events(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM events")

    def clear_source_events(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM source_events")

    def clear_backtests(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM backtest_runs")

    def clear_trades(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM trades")

    def clear_price_observations(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM price_observations")

    def clear_strategy_decisions(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM strategy_decisions")

    def clear_trade_sessions(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM trade_sessions")

    def clear_settings_versions(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM settings_versions")

    def clear_experiment_runs(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM experiment_runs")

    def clear_trade_labels(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM trade_labels")

    def clear_strategy_presets(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM strategy_presets")

    def clear_live_execution_requests(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM live_execution_requests")

    def _token_from_payload(self, payload: dict[str, Any]) -> TokenSignal:
        payload["detected_at"] = datetime.fromisoformat(payload["detected_at"])
        payload["opened_at"] = datetime.fromisoformat(payload["opened_at"]) if payload.get("opened_at") else None
        payload["closed_at"] = datetime.fromisoformat(payload["closed_at"]) if payload.get("closed_at") else None
        payload["last_observed_trade_at"] = datetime.fromisoformat(payload["last_observed_trade_at"]) if payload.get("last_observed_trade_at") else None
        payload["status"] = TokenStatus(payload["status"])
        allowed = set(TokenSignal.__dataclass_fields__.keys())
        return TokenSignal(**{key: value for key, value in payload.items() if key in allowed})

    def _event_from_payload(self, payload: dict[str, Any]) -> TradeEvent:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        return TradeEvent(**payload)

    def _source_event_from_payload(self, payload: dict[str, Any]) -> SourceEvent:
        payload["received_at"] = datetime.fromisoformat(payload["received_at"])
        return SourceEvent(**payload)

    def _backtest_from_payload(self, payload: dict[str, Any]) -> BacktestRun:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        return BacktestRun(**payload)

    def _trade_from_payload(self, payload: dict[str, Any]) -> TradeRecord:
        payload["opened_at"] = datetime.fromisoformat(payload["opened_at"]) if payload.get("opened_at") else None
        payload["closed_at"] = datetime.fromisoformat(payload["closed_at"]) if payload.get("closed_at") else None
        return TradeRecord(**payload)

    def _price_observation_from_payload(self, payload: dict[str, Any]) -> PriceObservation:
        payload["observed_at"] = datetime.fromisoformat(payload["observed_at"])
        allowed = set(PriceObservation.__dataclass_fields__.keys())
        return PriceObservation(**{key: value for key, value in payload.items() if key in allowed})

    def _settings_version_from_payload(self, payload: dict[str, Any]) -> SettingsVersion:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        allowed = set(SettingsVersion.__dataclass_fields__.keys())
        return SettingsVersion(**{key: value for key, value in payload.items() if key in allowed})

    def _experiment_from_payload(self, payload: dict[str, Any]) -> ExperimentRun:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        allowed = set(ExperimentRun.__dataclass_fields__.keys())
        return ExperimentRun(**{key: value for key, value in payload.items() if key in allowed})

    def _trade_label_from_payload(self, payload: dict[str, Any]) -> TradeLabel:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        allowed = set(TradeLabel.__dataclass_fields__.keys())
        return TradeLabel(**{key: value for key, value in payload.items() if key in allowed})

    def _strategy_preset_from_payload(self, payload: dict[str, Any]) -> StrategyPreset:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        allowed = set(StrategyPreset.__dataclass_fields__.keys())
        return StrategyPreset(**{key: value for key, value in payload.items() if key in allowed})

    def _live_execution_request_from_payload(self, payload: dict[str, Any]) -> LiveExecutionRequest:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["reviewed_at"] = datetime.fromisoformat(payload["reviewed_at"]) if payload.get("reviewed_at") else None
        allowed = set(LiveExecutionRequest.__dataclass_fields__.keys())
        return LiveExecutionRequest(**{key: value for key, value in payload.items() if key in allowed})

    def _strategy_decision_from_payload(self, payload: dict[str, Any]) -> StrategyDecisionRecord:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        allowed = set(StrategyDecisionRecord.__dataclass_fields__.keys())
        return StrategyDecisionRecord(**{key: value for key, value in payload.items() if key in allowed})

    def _trade_session_from_payload(self, payload: dict[str, Any]) -> TradeSession:
        payload["opened_at"] = datetime.fromisoformat(payload["opened_at"]) if payload.get("opened_at") else None
        payload["closed_at"] = datetime.fromisoformat(payload["closed_at"]) if payload.get("closed_at") else None
        allowed = set(TradeSession.__dataclass_fields__.keys())
        return TradeSession(**{key: value for key, value in payload.items() if key in allowed})
