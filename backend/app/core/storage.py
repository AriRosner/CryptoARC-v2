from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable, Iterator

from app.core.models import BacktestRun, BotMode, BotSettings, ExperimentRun, LiveExecutionAudit, LiveExecutionIntent, LiveExecutionRequest, LiveLedgerPosition, LiveSession, PriceObservation, SettingsVersion, SourceEvent, StrategyDecisionRecord, StrategyPreset, TokenSignal, TokenStatus, TradeEvent, TradeLabel, TradeRecord, TradeSession


DATA_SUMMARY_COUNT_TABLES = (
    ("tokens", "tokens"),
    ("events", "events"),
    ("source_events", "source_events"),
    ("backtests", "backtest_runs"),
    ("trades", "trades"),
    ("price_observations", "price_observations"),
    ("strategy_decisions", "strategy_decisions"),
    ("trade_sessions", "trade_sessions"),
    ("settings_versions", "settings_versions"),
    ("experiments", "experiment_runs"),
    ("trade_labels", "trade_labels"),
    ("strategy_presets", "strategy_presets"),
    ("live_execution_requests", "live_execution_requests"),
    ("live_sessions", "live_sessions"),
    ("live_execution_audits", "live_execution_audits"),
    ("live_intents", "live_intents"),
    ("live_ledger_positions", "live_ledger_positions"),
    ("backup_restore_history", "backup_restore_history"),
    ("source_soak_history", "source_soak_history"),
)
DATA_SUMMARY_COUNTS_SQL = "SELECT " + ", ".join(
    f"(SELECT COUNT(*) FROM {table}) AS {key}" for key, table in DATA_SUMMARY_COUNT_TABLES
)


class Storage:
    SCHEMA_VERSION = 9
    BACKUP_FORMAT_VERSION = 1
    CLEAR_ALL_TABLES = (
        "tokens",
        "events",
        "source_events",
        "backtest_runs",
        "trades",
        "price_observations",
        "strategy_decisions",
        "trade_sessions",
        "settings_versions",
        "experiment_runs",
        "trade_labels",
        "strategy_presets",
        "live_execution_requests",
        "live_sessions",
        "live_execution_audits",
        "live_intents",
        "live_ledger_positions",
        "source_soak_history",
    )
    BACKUP_TABLES = (
        "settings",
        "tokens",
        "events",
        "source_events",
        "backtest_runs",
        "trades",
        "price_observations",
        "strategy_decisions",
        "trade_sessions",
        "settings_versions",
        "experiment_runs",
        "trade_labels",
        "strategy_presets",
        "live_execution_requests",
        "live_sessions",
        "live_execution_audits",
        "live_intents",
        "live_ledger_positions",
        "backup_restore_history",
        "source_soak_history",
        "mobile_pairing_requests",
        "mobile_devices",
    )

    def __init__(self, path: str = "data/cryptoarc.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migration_status: dict[str, Any] = {
            "status": "pending",
            "startup_error": "",
            "startup_completed_at": None,
        }
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
        try:
            with self._connect() as connection:
                self._prepare_schema_migration_table(connection)
                self._apply_migrations(connection)
            self._migration_status = {
                "status": "ok",
                "startup_error": "",
                "startup_completed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            self._migration_status = {
                "status": "failed",
                "startup_error": f"{exc.__class__.__name__}: {exc}",
                "startup_completed_at": datetime.now(timezone.utc).isoformat(),
            }
            raise

    def _prepare_schema_migration_table(self, connection: sqlite3.Connection) -> None:
        table_exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        if not table_exists:
            self._create_schema_migration_table(connection)
            return
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(schema_migrations)").fetchall()
        }
        if "migration_id" in columns:
            return
        legacy_rows = connection.execute(
            "SELECT version, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        connection.execute("ALTER TABLE schema_migrations RENAME TO schema_migrations_legacy")
        self._create_schema_migration_table(connection)
        max_legacy_version = max([int(row["version"]) for row in legacy_rows], default=0)
        applied_at_by_version = {int(row["version"]): row["applied_at"] for row in legacy_rows}
        for version, migration_id, description, _ in self._migrations():
            if version > max_legacy_version:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (migration_id, version, description, applied_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    migration_id,
                    version,
                    description,
                    applied_at_by_version.get(version) or datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _create_schema_migration_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )

    def _apply_migrations(self, connection: sqlite3.Connection) -> None:
        applied_ids = {
            str(row["migration_id"])
            for row in connection.execute("SELECT migration_id FROM schema_migrations").fetchall()
        }
        for version, migration_id, description, migration_fn in self._migrations():
            if migration_id in applied_ids:
                continue
            migration_fn(connection)
            connection.execute(
                """
                INSERT INTO schema_migrations (migration_id, version, description, applied_at)
                VALUES (?, ?, ?, ?)
                """,
                (migration_id, version, description, datetime.now(timezone.utc).isoformat()),
            )

    def _migrations(self) -> list[tuple[int, str, str, Any]]:
        return [
            (1, "001_initial_core", "initial core storage tables", self._migration_001_initial_core),
            (2, "002_research_tables", "research and replay tables", self._migration_002_research_tables),
            (3, "003_experiments_presets", "experiments, labels, and presets", self._migration_003_experiments_presets),
            (4, "004_live_manual_tables", "manual live workflow tables", self._migration_004_live_manual_tables),
            (5, "005_indexes", "timestamp and lookup indexes", self._migration_005_indexes),
            (6, "006_backup_restore_history", "backup and restore history tracking", self._migration_006_backup_restore_history),
            (7, "007_foundation_indexes", "foundation release supporting indexes", self._migration_007_foundation_indexes),
            (8, "008_source_soak_history", "durable hybrid source soak snapshots", self._migration_008_source_soak_history),
            (9, "009_mobile_companion", "mobile companion pairing and devices", self._migration_009_mobile_companion),
        ]

    def _migration_001_initial_core(self, connection: sqlite3.Connection) -> None:
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

    def _migration_002_research_tables(self, connection: sqlite3.Connection) -> None:
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

    def _migration_003_experiments_presets(self, connection: sqlite3.Connection) -> None:
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

    def _migration_004_live_manual_tables(self, connection: sqlite3.Connection) -> None:
        for table in ("live_execution_requests", "live_sessions", "live_execution_audits", "live_intents", "live_ledger_positions"):
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _migration_005_indexes(self, connection: sqlite3.Connection) -> None:
        statements = [
            "CREATE INDEX IF NOT EXISTS idx_tokens_detected_at ON tokens(detected_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_source_events_received_at ON source_events(received_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_trades_closed_at ON trades(closed_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_price_observations_mint_observed_at ON price_observations(mint, observed_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_strategy_decisions_token_created_at ON strategy_decisions(token_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_trade_sessions_token_closed_at ON trade_sessions(token_id, closed_at DESC)",
        ]
        for statement in statements:
            connection.execute(statement)

    def _migration_006_backup_restore_history(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS backup_restore_history (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    def _migration_007_foundation_indexes(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_backup_restore_history_created_at ON backup_restore_history(created_at DESC)"
        )

    def _migration_008_source_soak_history(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_soak_history (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                ready INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_source_soak_history_created_at ON source_soak_history(created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_source_soak_history_status ON source_soak_history(status, created_at DESC)"
        )

    def _migration_009_mobile_companion(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mobile_pairing_requests (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                claimed_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mobile_devices (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT,
                revoked_at TEXT
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_mobile_pairing_requests_expires_at ON mobile_pairing_requests(expires_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_mobile_pairing_requests_claimed_at ON mobile_pairing_requests(claimed_at, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_mobile_devices_last_seen_at ON mobile_devices(last_seen_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_mobile_devices_revoked_at ON mobile_devices(revoked_at, created_at DESC)"
        )

    def schema_status(self) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT migration_id, version, description, applied_at FROM schema_migrations ORDER BY version"
            ).fetchall()
        current = max([int(row["version"]) for row in rows], default=0)
        return {
            "current_version": current,
            "expected_version": self.SCHEMA_VERSION,
            "ok": current >= self.SCHEMA_VERSION and self._migration_status.get("status") == "ok",
            "status": self._migration_status.get("status", "unknown"),
            "startup_error": self._migration_status.get("startup_error", ""),
            "startup_completed_at": self._migration_status.get("startup_completed_at"),
            "migrations": [
                {
                    "migration_id": str(row["migration_id"]),
                    "version": int(row["version"]),
                    "description": row["description"],
                    "applied_at": row["applied_at"],
                }
                for row in rows
            ],
        }

    def backup(self) -> dict[str, str]:
        if not self.path.exists():
            return {"status": "missing", "path": ""}
        backup_path = self.path.with_suffix(f".backup-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{self.path.suffix}")
        backup_path.write_bytes(self.path.read_bytes())
        self.save_backup_restore_history(
            {
                "id": f"backup_copy_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "action": "backup_copy",
                "status": "created",
                "path": str(backup_path),
                "operator_action": "Keep this local SQLite snapshot for manual rollback.",
            }
        )
        return {"status": "created", "path": str(backup_path)}

    def create_backup_artifact(self) -> dict[str, Any]:
        if not self.path.exists():
            raise FileNotFoundError("Database file does not exist")
        summary = self._summary_counts()
        artifact = {
            "artifact_type": "cryptoarc_local_backup",
            "format_version": self.BACKUP_FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database_name": self.path.name,
            "schema": self.schema_status(),
            "summary": summary,
            "database_base64": base64.b64encode(self.path.read_bytes()).decode("ascii"),
        }
        self.save_backup_restore_history(
            {
                "id": f"backup_artifact_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "created_at": artifact["created_at"],
                "action": "backup_artifact",
                "status": "created",
                "summary": summary,
                "operator_action": "Store the artifact safely before trying a restore.",
            }
        )
        return artifact

    def preview_restore_artifact(self, artifact: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        if artifact.get("artifact_type") != "cryptoarc_local_backup":
            raise ValueError("Unsupported restore artifact type")
        if int(artifact.get("format_version") or 0) != self.BACKUP_FORMAT_VERSION:
            raise ValueError("Unsupported restore artifact format version")
        encoded = str(artifact.get("database_base64") or "")
        if not encoded.strip():
            raise ValueError("Restore artifact is missing database payload")
        try:
            decoded = base64.b64decode(encoded.encode("ascii"), validate=True)
        except Exception as exc:
            raise ValueError("Restore artifact payload is not valid base64") from exc
        inspection = self._inspect_sqlite_payload(decoded)
        schema = artifact.get("schema") if isinstance(artifact.get("schema"), dict) else {}
        artifact_version = int(schema.get("current_version") or inspection.get("schema_version") or 0)
        if artifact_version > self.SCHEMA_VERSION:
            raise ValueError("Restore artifact was created by a newer schema version")
        metadata_summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
        actual_summary = inspection.get("table_counts", {})
        current_summary = (
            self._summary_counts()
            if self.path.exists()
            else {key: 0 for key in actual_summary}
        )
        table_deltas = {
            key: {
                "current": int(current_summary.get(key, 0) or 0),
                "artifact": int(actual_summary.get(key, 0) or 0),
                "delta": int(actual_summary.get(key, 0) or 0) - int(current_summary.get(key, 0) or 0),
            }
            for key in sorted(set(current_summary) | set(actual_summary))
        }
        changed_tables = [key for key, value in table_deltas.items() if int(value["delta"]) != 0]
        if str(artifact.get("database_name") or "") != self.path.name:
            warnings.append("Artifact database name differs from the current local database path.")
        if artifact_version < self.SCHEMA_VERSION:
            warnings.append("Artifact will be migrated forward after restore.")
        if schema and int(schema.get("current_version") or 0) != int(inspection.get("schema_version") or 0):
            warnings.append("Artifact metadata schema version differs from the embedded database and was ignored.")
        if metadata_summary and metadata_summary != actual_summary:
            warnings.append("Artifact metadata summary differs from the embedded database counts.")
        warnings.append("Restore replaces the local SQLite state. A safety backup copy will be created first.")
        risk_level = "low"
        if str(inspection.get("integrity_check") or "").lower() != "ok":
            risk_level = "blocked"
        elif artifact_version < self.SCHEMA_VERSION or changed_tables:
            risk_level = "review"
        return {
            "compatible": True,
            "artifact_type": artifact["artifact_type"],
            "format_version": int(artifact["format_version"]),
            "created_at": artifact.get("created_at"),
            "database_name": artifact.get("database_name"),
            "schema_version": artifact_version,
            "current_schema_version": self.SCHEMA_VERSION,
            "summary": actual_summary,
            "current_summary": current_summary,
            "table_deltas": table_deltas,
            "changed_tables": changed_tables,
            "risk_level": risk_level,
            "recommended_actions": [
                "Download a fresh backup artifact before confirming restore.",
                "Review changed table counts and restore warnings.",
                "After restore, verify readiness, source health, wallet state, and unresolved live audits before trading.",
            ],
            "warnings": warnings,
            "payload_bytes": len(decoded),
            "integrity_check": str(inspection.get("integrity_check") or "unknown"),
            "detected_tables": inspection.get("tables", []),
        }

    def restore_backup_artifact(
        self,
        artifact: dict[str, Any],
        post_swap_validator: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        original_exists = self.path.exists()
        preview = self.preview_restore_artifact(artifact)
        decoded = base64.b64decode(str(artifact["database_base64"]).encode("ascii"))
        original_migration_status = dict(self._migration_status)
        safety_path: Path | None = None
        swapped = False
        with NamedTemporaryFile(
            prefix=f".{self.path.stem}.restore-",
            suffix=f"-{uuid.uuid4().hex}{self.path.suffix}",
            dir=self.path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(decoded)
        try:
            staged_storage = Storage(str(temp_path))
            staged_settings = staged_storage.load_settings()
            staged_settings.live_active_backend_armed = False
            staged_settings.kill_switch_enabled = True
            staged_storage.save_settings(staged_settings)
            persisted_settings = staged_storage.load_settings()
            if persisted_settings.live_active_backend_armed or not persisted_settings.kill_switch_enabled:
                raise ValueError("Restore staging failed to persist fail-closed live settings")
            self._inspect_sqlite_file(temp_path)
            staged_schema = staged_storage.schema_status()
            if not staged_schema.get("ok"):
                raise ValueError("Restore staging failed schema migration validation")

            safety_path = self._create_restore_safety_backup() if original_exists else None
            temp_path.replace(self.path)
            swapped = True
            self._ensure_schema()
            self._inspect_sqlite_file(self.path)
            restored_settings = self.load_settings()
            if restored_settings.live_active_backend_armed or not restored_settings.kill_switch_enabled:
                raise ValueError("Restored database did not retain fail-closed live settings")
            if post_swap_validator is not None:
                post_swap_validator()

            backup_path = str(safety_path or "")
            history_entry = {
                "id": f"restore_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "action": "restore",
                "status": "restored",
                "artifact_created_at": preview.get("created_at"),
                "artifact_database_name": preview.get("database_name"),
                "backup_path": backup_path,
                "operator_action": "Review migration, runtime, and wallet state after restore before trading.",
            }
            self.save_backup_restore_history(history_entry)
            return {**preview, "status": "restored", "backup_path": backup_path}
        except Exception as exc:
            if swapped:
                try:
                    if original_exists:
                        if safety_path is None or not safety_path.exists():
                            raise FileNotFoundError("Restore safety backup is unavailable")
                        safety_path.replace(self.path)
                    else:
                        self.path.unlink(missing_ok=True)
                    self._migration_status = original_migration_status
                except Exception as rollback_exc:
                    raise RuntimeError(
                        f"Restore failed and atomic safety rollback failed: {rollback_exc.__class__.__name__}: {rollback_exc}"
                    ) from exc
            raise
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _create_restore_safety_backup(self) -> Path:
        backup_path: Path | None = None
        try:
            with NamedTemporaryFile(
                prefix=f"{self.path.stem}.backup-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-",
                suffix=self.path.suffix,
                dir=self.path.parent,
                delete=False,
            ) as destination:
                backup_path = Path(destination.name)
                with self.path.open("rb") as source:
                    shutil.copyfileobj(source, destination)
                destination.flush()
                os.fsync(destination.fileno())
            if backup_path.read_bytes() != self.path.read_bytes():
                raise OSError("Restore safety backup does not exactly match the original database")
            return backup_path
        except Exception:
            if backup_path is not None:
                backup_path.unlink(missing_ok=True)
            raise

    def load_backup_restore_history(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM backup_restore_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def save_backup_restore_history(self, payload: dict[str, Any]) -> None:
        created_at = str(payload.get("created_at") or datetime.now(timezone.utc).isoformat())
        item_id = str(payload.get("id") or f"backup_restore_{created_at}")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO backup_restore_history (id, payload, created_at)
                VALUES (?, ?, ?)
                """,
                (item_id, json.dumps(payload), created_at),
            )

    def load_source_soak_history(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM source_soak_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def save_source_soak_snapshot(self, payload: dict[str, Any]) -> None:
        created_at = str(payload.get("created_at") or payload.get("generated_at") or datetime.now(timezone.utc).isoformat())
        item_id = str(payload.get("id") or f"source_soak_{created_at}")
        status = str(payload.get("status") or "unknown")
        ready = 1 if bool(payload.get("ready")) else 0
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO source_soak_history (id, payload, created_at, status, ready)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item_id, json.dumps(payload), created_at, status, ready),
            )

    def save_mobile_pairing_request(self, payload: dict[str, Any]) -> None:
        item_id = str(payload["id"])
        created_at = str(payload.get("created_at") or datetime.now(timezone.utc).isoformat())
        expires_at = str(payload.get("expires_at") or created_at)
        claimed_at = str(payload.get("claimed_at") or "")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO mobile_pairing_requests (id, payload, created_at, expires_at, claimed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item_id, json.dumps(payload), created_at, expires_at, claimed_at),
            )

    def load_mobile_pairing_request(self, pairing_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM mobile_pairing_requests WHERE id = ?",
                (pairing_id,),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def load_mobile_pairing_requests(self, include_claimed: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(500, int(limit or 50)))
        where_clause = "" if include_claimed else "WHERE claimed_at IS NULL OR claimed_at = ''"
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM mobile_pairing_requests {where_clause} ORDER BY created_at DESC LIMIT ?",
                (bounded_limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def save_mobile_device(self, payload: dict[str, Any]) -> None:
        item_id = str(payload["id"])
        created_at = str(payload.get("created_at") or datetime.now(timezone.utc).isoformat())
        last_seen_at = str(payload.get("last_seen_at") or "")
        revoked_at = str(payload.get("revoked_at") or "")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO mobile_devices (id, payload, created_at, last_seen_at, revoked_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item_id, json.dumps(payload), created_at, last_seen_at, revoked_at),
            )

    def load_mobile_device(self, device_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM mobile_devices WHERE id = ?",
                (device_id,),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def load_mobile_devices(self, include_revoked: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(1000, int(limit or 50)))
        where_clause = "" if include_revoked else "WHERE revoked_at IS NULL OR revoked_at = ''"
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM mobile_devices {where_clause} ORDER BY COALESCE(last_seen_at, created_at) DESC LIMIT ?",
                (bounded_limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def load_mobile_device_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM mobile_devices").fetchall()
        for row in rows:
            payload = json.loads(row["payload"])
            if str(payload.get("token_hash") or "") == token_hash:
                return payload
        return None

    def touch_active_mobile_device_by_token_hash(self, token_hash: str, last_seen_at: str) -> dict[str, Any] | None:
        """Atomically update the last-seen time for a currently active device."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT id, payload, revoked_at FROM mobile_devices").fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                if str(payload.get("token_hash") or "") != token_hash:
                    continue
                if str(row["revoked_at"] or "") or str(payload.get("revoked_at") or ""):
                    return None
                payload["last_seen_at"] = last_seen_at
                connection.execute(
                    "UPDATE mobile_devices SET payload = ?, last_seen_at = ? WHERE id = ?",
                    (json.dumps(payload), last_seen_at, row["id"]),
                )
                return payload
        return None

    def backup_restore_status(self) -> dict[str, Any]:
        history = self.load_backup_restore_history(10)
        latest_backup = next((item for item in history if str(item.get("action", "")).startswith("backup")), None)
        latest_restore = next((item for item in history if item.get("action") == "restore"), None)
        latest_failed_restore = next((item for item in history if item.get("action") == "restore" and item.get("status") == "failed"), None)
        database_exists = self.path.exists()
        database_size_bytes = self.path.stat().st_size if database_exists else 0
        recommended_action = "Create a backup artifact before upgrades or restore operations."
        if latest_failed_restore:
            recommended_action = "Inspect the failed restore entry and keep the latest safety backup before retrying."
        elif latest_restore:
            recommended_action = "Review runtime readiness, source health, and wallet state after the latest restore."
        return {
            "history": history,
            "latest_backup": latest_backup,
            "latest_restore": latest_restore,
            "latest_failed_restore": latest_failed_restore,
            "database_exists": database_exists,
            "database_path": str(self.path),
            "database_size_bytes": database_size_bytes,
            "history_count": self.count_backup_restore_history(),
            "recommended_action": recommended_action,
        }

    def _inspect_sqlite_payload(self, payload: bytes) -> dict[str, Any]:
        with NamedTemporaryFile(prefix="cryptoarc-restore-preview-", suffix=".db", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
        try:
            return self._inspect_sqlite_file(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _inspect_sqlite_file(self, path: Path) -> dict[str, Any]:
        try:
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise ValueError("Restore artifact database could not be opened") from exc
        try:
            row = connection.execute("PRAGMA quick_check").fetchone()
            integrity_check = str(row[0] if row else "unknown")
            if integrity_check.lower() != "ok":
                raise ValueError("Restore artifact database failed SQLite integrity checks")
            tables = [
                str(item["name"])
                for item in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            ]
            required_tables = {"schema_migrations", "settings", "tokens", "events", "trades"}
            missing_tables = sorted(required_tables - set(tables))
            if missing_tables:
                raise ValueError(f"Restore artifact database is missing required tables: {', '.join(missing_tables)}")
            schema_rows = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
            schema_version = max([int(item["version"]) for item in schema_rows], default=0)
            table_counts: dict[str, int] = {}
            for table in self.BACKUP_TABLES:
                if table not in tables:
                    continue
                count_row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
                table_counts[table] = int(count_row["count"] if count_row else 0)
            return {
                "integrity_check": integrity_check,
                "schema_version": schema_version,
                "tables": tables,
                "table_counts": table_counts,
            }
        except sqlite3.Error as exc:
            raise ValueError("Restore artifact database is not a valid SQLite backup") from exc
        finally:
            connection.close()

    def _summary_counts(self) -> dict[str, int]:
        return {
            "tokens": self.count_tokens(),
            "events": self.count_events(),
            "source_events": self.count_source_events(),
            "backtests": self.count_backtest_runs(),
            "trades": self.count_trades(),
            "price_observations": self.count_price_observations(),
            "strategy_decisions": self.count_strategy_decisions(),
            "trade_sessions": self.count_trade_sessions(),
            "settings_versions": self.count_settings_versions(),
            "experiments": self.count_experiment_runs(),
            "trade_labels": self.count_trade_labels(),
            "strategy_presets": self.count_strategy_presets(),
            "live_execution_requests": self.count_live_execution_requests(),
            "live_sessions": self.count_live_sessions(),
            "live_execution_audits": self.count_live_execution_audits(),
            "live_intents": self.count_live_intents(),
            "live_ledger_positions": self.count_live_ledger_positions(),
            "source_soak_history": self.count_source_soak_history(),
            "mobile_pairing_requests": self.count_mobile_pairing_requests(),
            "mobile_devices": self.count_mobile_devices(),
        }

    def data_summary_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            row = connection.execute(DATA_SUMMARY_COUNTS_SQL).fetchone()
        return {key: int(row[key] if row else 0) for key, _ in DATA_SUMMARY_COUNT_TABLES}

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

    def count_live_sessions(self) -> int:
        return self._count_table("live_sessions")

    def count_live_execution_audits(self) -> int:
        return self._count_table("live_execution_audits")

    def count_live_intents(self) -> int:
        return self._count_table("live_intents")

    def count_live_ledger_positions(self) -> int:
        return self._count_table("live_ledger_positions")

    def count_backup_restore_history(self) -> int:
        return self._count_table("backup_restore_history")

    def count_source_soak_history(self) -> int:
        return self._count_table("source_soak_history")

    def count_mobile_pairing_requests(self) -> int:
        return self._count_table("mobile_pairing_requests")

    def count_mobile_devices(self) -> int:
        return self._count_table("mobile_devices")

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

    def load_live_execution_request(self, request_id: str) -> LiveExecutionRequest | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM live_execution_requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            return None
        return self._live_execution_request_from_payload(json.loads(row["payload"]))

    def save_live_execution_request(self, request: LiveExecutionRequest) -> None:
        self._save_payload("live_execution_requests", request.id, request.to_dict(), request.created_at)

    def load_live_sessions(self, limit: int = 50) -> list[LiveSession]:
        return [self._live_session_from_payload(payload) for payload in self._load_payloads("live_sessions", limit)]

    def save_live_session(self, session: LiveSession) -> None:
        self._save_payload("live_sessions", session.id, session.to_dict(), session.created_at)

    def load_live_execution_audits(self, limit: int = 100) -> list[LiveExecutionAudit]:
        return [self._live_execution_audit_from_payload(payload) for payload in self._load_payloads("live_execution_audits", limit)]

    def load_live_execution_audit(self, audit_id: str) -> LiveExecutionAudit | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM live_execution_audits WHERE id = ?", (audit_id,)).fetchone()
        if not row:
            return None
        return self._live_execution_audit_from_payload(json.loads(row["payload"]))

    def save_live_execution_audit(self, audit: LiveExecutionAudit) -> None:
        self._save_payload("live_execution_audits", audit.id, audit.to_dict(), audit.created_at)

    def load_live_intents(self, limit: int = 100) -> list[LiveExecutionIntent]:
        return [self._live_intent_from_payload(payload) for payload in self._load_payloads("live_intents", limit)]

    def load_live_intent(self, intent_id: str) -> LiveExecutionIntent | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM live_intents WHERE id = ?", (intent_id,)).fetchone()
        if not row:
            return None
        return self._live_intent_from_payload(json.loads(row["payload"]))

    def save_live_intent(self, intent: LiveExecutionIntent) -> None:
        self._save_payload("live_intents", intent.id, intent.to_dict(), intent.created_at)

    def load_live_ledger_positions(self, limit: int = 100) -> list[LiveLedgerPosition]:
        return [self._live_ledger_position_from_payload(payload) for payload in self._load_payloads("live_ledger_positions", limit)]

    def load_live_ledger_position(self, position_id: str) -> LiveLedgerPosition | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM live_ledger_positions WHERE id = ?", (position_id,)).fetchone()
        if not row:
            return None
        return self._live_ledger_position_from_payload(json.loads(row["payload"]))

    def save_live_ledger_position(self, position: LiveLedgerPosition) -> None:
        self._save_payload("live_ledger_positions", position.id, position.to_dict(), position.created_at)

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

    def load_price_observations_newest_first(self, limit: int = 1000, mint: str | None = None) -> list[PriceObservation]:
        with self._connect() as connection:
            if mint:
                rows = connection.execute(
                    "SELECT payload FROM price_observations WHERE mint = ? ORDER BY observed_at DESC LIMIT ?",
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

    def clear_all_data(self, reset_settings_version: SettingsVersion) -> None:
        payload = json.dumps(reset_settings_version.to_dict())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for table in self.CLEAR_ALL_TABLES:
                    connection.execute(f"DELETE FROM {table}")
                connection.execute(
                    "INSERT INTO settings_versions (id, payload, created_at) VALUES (?, ?, ?)",
                    (
                        reset_settings_version.id,
                        payload,
                        reset_settings_version.created_at.isoformat(),
                    ),
                )
            except Exception:
                connection.rollback()
                raise

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

    def clear_live_sessions(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM live_sessions")

    def clear_live_execution_audits(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM live_execution_audits")

    def clear_live_intents(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM live_intents")

    def clear_live_ledger_positions(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM live_ledger_positions")

    def clear_backup_restore_history(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM backup_restore_history")

    def clear_source_soak_history(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM source_soak_history")

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
        allowed = set(TradeEvent.__dataclass_fields__.keys())
        return TradeEvent(**{key: value for key, value in payload.items() if key in allowed})

    def _source_event_from_payload(self, payload: dict[str, Any]) -> SourceEvent:
        payload["received_at"] = datetime.fromisoformat(payload["received_at"])
        allowed = set(SourceEvent.__dataclass_fields__.keys())
        return SourceEvent(**{key: value for key, value in payload.items() if key in allowed})

    def _backtest_from_payload(self, payload: dict[str, Any]) -> BacktestRun:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        allowed = set(BacktestRun.__dataclass_fields__.keys())
        return BacktestRun(**{key: value for key, value in payload.items() if key in allowed})

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

    def _live_session_from_payload(self, payload: dict[str, Any]) -> LiveSession:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["acknowledged_at"] = datetime.fromisoformat(payload["acknowledged_at"]) if payload.get("acknowledged_at") else None
        payload["closed_at"] = datetime.fromisoformat(payload["closed_at"]) if payload.get("closed_at") else None
        allowed = set(LiveSession.__dataclass_fields__.keys())
        return LiveSession(**{key: value for key, value in payload.items() if key in allowed})

    def _live_execution_audit_from_payload(self, payload: dict[str, Any]) -> LiveExecutionAudit:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["updated_at"] = datetime.fromisoformat(payload["updated_at"])
        payload["confirmation_checked_at"] = datetime.fromisoformat(payload["confirmation_checked_at"]) if payload.get("confirmation_checked_at") else None
        allowed = set(LiveExecutionAudit.__dataclass_fields__.keys())
        return LiveExecutionAudit(**{key: value for key, value in payload.items() if key in allowed})

    def _live_intent_from_payload(self, payload: dict[str, Any]) -> LiveExecutionIntent:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["updated_at"] = datetime.fromisoformat(payload.get("updated_at") or payload["created_at"])
        payload["expires_at"] = datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None
        allowed = set(LiveExecutionIntent.__dataclass_fields__.keys())
        return LiveExecutionIntent(**{key: value for key, value in payload.items() if key in allowed})

    def _live_ledger_position_from_payload(self, payload: dict[str, Any]) -> LiveLedgerPosition:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["updated_at"] = datetime.fromisoformat(payload.get("updated_at") or payload["created_at"])
        payload["mark_price_at"] = datetime.fromisoformat(payload["mark_price_at"]) if payload.get("mark_price_at") else None
        payload["balance_verified_at"] = datetime.fromisoformat(payload["balance_verified_at"]) if payload.get("balance_verified_at") else None
        allowed = set(LiveLedgerPosition.__dataclass_fields__.keys())
        return LiveLedgerPosition(**{key: value for key, value in payload.items() if key in allowed})

    def _strategy_decision_from_payload(self, payload: dict[str, Any]) -> StrategyDecisionRecord:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        allowed = set(StrategyDecisionRecord.__dataclass_fields__.keys())
        return StrategyDecisionRecord(**{key: value for key, value in payload.items() if key in allowed})

    def _trade_session_from_payload(self, payload: dict[str, Any]) -> TradeSession:
        payload["opened_at"] = datetime.fromisoformat(payload["opened_at"]) if payload.get("opened_at") else None
        payload["closed_at"] = datetime.fromisoformat(payload["closed_at"]) if payload.get("closed_at") else None
        allowed = set(TradeSession.__dataclass_fields__.keys())
        return TradeSession(**{key: value for key, value in payload.items() if key in allowed})
