from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from app.core.models import BacktestRun, BotMode, BotSettings, SourceEvent, TokenSignal, TokenStatus, TradeEvent, TradeRecord


class Storage:
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

    def load_tokens(self, limit: int = 80) -> list[TokenSignal]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM tokens ORDER BY detected_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._token_from_payload(json.loads(row["payload"])) for row in rows]

    def load_all_tokens(self, limit: int = 5000) -> list[TokenSignal]:
        return self.load_tokens(limit)

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

    def load_trades(self, limit: int = 500) -> list[TradeRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM trades ORDER BY COALESCE(closed_at, opened_at) DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._trade_from_payload(json.loads(row["payload"])) for row in rows]

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

    def _token_from_payload(self, payload: dict[str, Any]) -> TokenSignal:
        payload["detected_at"] = datetime.fromisoformat(payload["detected_at"])
        payload["opened_at"] = datetime.fromisoformat(payload["opened_at"]) if payload.get("opened_at") else None
        payload["closed_at"] = datetime.fromisoformat(payload["closed_at"]) if payload.get("closed_at") else None
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
