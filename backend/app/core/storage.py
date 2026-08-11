from __future__ import annotations

import base64
import hmac
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable, Iterator

from app.core.models import AcceptedMarketObservation, BacktestRun, BotMode, BotSettings, CandidateValidation, ExperimentRun, LiveExecutionAudit, LiveExecutionIntent, LiveExecutionRequest, LiveLedgerPosition, LiveSession, MobileActionReceipt, MobileDestinationAuthorization, MobilePushRegistration, PriceObservation, SentinelVerdict, SettingsVersion, ShadowComparison, ShadowCostBreakdown, SourceEvent, StrategyCandidate, StrategyDecisionRecord, StrategyPreset, TokenSignal, TokenStatus, TradeEvent, TradeGrade, TradeGradeCorrection, TradeLabel, TradeRecord, TradeReviewJob, TradeRevision, TradeSession
from app.core.strategy_contract import SniperStrategyVersion
from app.core.model_classifier import ModelClassification
from app.core.pilot_risk import PilotRiskPolicy


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
    ("accepted_market_observations", "accepted_market_observations"),
    ("shadow_market_evidence_bindings", "shadow_market_evidence_bindings"),
    ("pending_shadow_audit_captures", "pending_shadow_audit_captures"),
    ("source_access_evidence", "source_access_evidence"),
    ("sniper_strategy_versions", "sniper_strategy_versions"),
    ("shadow_economic_comparisons", "shadow_economic_comparisons"),
    ("sentinel_verdicts", "sentinel_verdicts"),
    ("trade_review_jobs", "trade_review_jobs"),
    ("trade_grades", "trade_grades"),
    ("trade_grade_corrections", "trade_grade_corrections"),
    ("model_classifications", "model_classifications"),
    ("strategy_candidates", "strategy_candidates"),
    ("candidate_validations", "candidate_validations"),
    ("strategy_promotions", "strategy_promotions"),
    ("pilot_risk_policies", "pilot_risk_policies"),
    ("pilot_loss_ledger", "pilot_loss_ledger"),
    ("production_rehearsal_reports", "production_rehearsal_reports"),
    ("production_rehearsal_evidence", "production_rehearsal_evidence"),
    ("manual_live_proof_reports", "manual_live_proof_reports"),
    ("autonomous_pilot_windows", "autonomous_pilot_windows"),
    ("post_pilot_reviews", "post_pilot_reviews"),
    ("pilot_operator_decisions", "pilot_operator_decisions"),
)
DATA_SUMMARY_COUNTS_SQL = "SELECT " + ", ".join(
    f"(SELECT COUNT(*) FROM {table}) AS {key}" for key, table in DATA_SUMMARY_COUNT_TABLES
)


class Storage:
    SCHEMA_VERSION = 25
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
        "accepted_market_observations",
        "shadow_market_evidence_bindings",
        "pending_shadow_audit_captures",
        "source_access_evidence",
        "sniper_strategy_versions",
        "shadow_economic_comparisons",
        "sentinel_verdicts",
        "trade_review_jobs",
        "trade_grades",
        "trade_grade_corrections",
        "model_classifications",
        "model_classification_budget",
        "strategy_candidates",
        "candidate_validations",
        "strategy_promotions",
        "active_strategy_selection",
        "strategy_validation_campaigns",
        "pilot_risk_policies",
        "pilot_loss_ledger",
        "production_rehearsal_reports",
        "production_rehearsal_evidence",
        "manual_live_proof_reports",
        "autonomous_pilot_windows",
        "post_pilot_reviews",
        "pilot_operator_decisions",
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
        "accepted_market_observations",
        "shadow_market_evidence_bindings",
        "pending_shadow_audit_captures",
        "source_access_evidence",
        "sniper_strategy_versions",
        "shadow_economic_comparisons",
        "sentinel_verdicts",
        "trade_review_jobs",
        "trade_grades",
        "trade_grade_corrections",
        "model_classifications",
        "model_classification_budget",
        "strategy_candidates",
        "candidate_validations",
        "strategy_promotions",
        "active_strategy_selection",
        "strategy_validation_campaigns",
        "pilot_risk_policies",
        "pilot_loss_ledger",
        "production_rehearsal_reports",
        "production_rehearsal_evidence",
        "manual_live_proof_reports",
        "autonomous_pilot_windows",
        "post_pilot_reviews",
        "pilot_operator_decisions",
        "mobile_pairing_requests",
        "mobile_devices",
        "mobile_action_receipts",
        "mobile_destination_authorizations",
        "mobile_push_registrations",
        "mobile_alert_acknowledgements",
        "mobile_notification_deliveries",
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
        connection = sqlite3.connect(self.path, timeout=0.05)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 50")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @contextmanager
    def read_connection(self) -> Iterator[sqlite3.Connection]:
        """Short, bounded read-only connection for dashboards and observability."""
        connection = sqlite3.connect(self.path, timeout=0.05)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 50")
        connection.execute("PRAGMA query_only = ON")
        try:
            yield connection
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = NORMAL")
                self._prepare_schema_migration_table(connection)
                self._apply_migrations(connection)
                self._ensure_mobile_notification_schema(connection)
                self._ensure_model_classifier_schema(connection)
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
            (10, "010_mobile_command_center", "scoped mobile command center persistence", self._migration_010_mobile_command_center),
            (11, "011_mobile_guarded_execution_claims", "durable guarded execution audit claims", self._migration_011_mobile_guarded_execution_claims),
            (12, "012_genuine_source_evidence", "accepted market observations and source access evidence", self._migration_012_genuine_source_evidence),
            (13, "013_sniper_strategy_versions", "immutable versioned sniper strategy contracts", self._migration_013_sniper_strategy_versions),
            (14, "014_shadow_economic_comparisons", "all-cost versioned shadow comparisons", self._migration_014_shadow_economic_comparisons),
            (15, "015_sentinel_verdicts", "immutable expiring market sentinel verdicts", self._migration_015_sentinel_verdicts),
            (16, "016_trade_grading", "durable deterministic trade grading queue", self._migration_016_trade_grading),
            (17, "017_strategy_candidates", "immutable strategy candidates and gated promotion", self._migration_017_strategy_candidates),
            (18, "018_pilot_risk", "immutable micro-pilot risk policy and cumulative loss ledger", self._migration_018_pilot_risk),
            (19, "019_production_rehearsal", "append-only production gate rehearsal reports", self._migration_019_production_rehearsal),
            (20, "020_manual_live_proof", "append-only manual live proof qualification reports", self._migration_020_manual_live_proof),
            (21, "021_autonomous_pilot", "append-only attended autonomous pilot window evaluations", self._migration_021_autonomous_pilot),
            (22, "022_post_pilot_review", "append-only post-pilot reviews and operator decisions", self._migration_022_post_pilot_review),
            (23, "023_production_rehearsal_evidence", "append-only scoped production rehearsal evidence", self._migration_023_production_rehearsal_evidence),
            (24, "024_shadow_market_evidence_bindings", "append-only shadow audit bindings to accepted market observations", self._migration_024_shadow_market_evidence_bindings),
            (25, "025_pending_shadow_audit_captures", "indexed pending shadow audit capture registry", self._migration_025_pending_shadow_audit_captures),
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

    def _migration_010_mobile_command_center(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mobile_action_receipts (
                id TEXT PRIMARY KEY,
                idempotency_key_hash TEXT NOT NULL UNIQUE,
                device_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mobile_destination_authorizations (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mobile_push_registrations (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                token_ciphertext TEXT NOT NULL,
                token_fingerprint TEXT NOT NULL UNIQUE,
                platform TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revoked_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mobile_alert_acknowledgements (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                acknowledged_at TEXT NOT NULL,
                UNIQUE(device_id, event_id)
            )
            """
        )

    def _ensure_mobile_notification_schema(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """Keep the Task 7 delivery ledger available on existing v11 databases."""
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mobile_notification_deliveries (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                registration_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                status TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                lease_expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(event_id, device_id, channel)
            )
            """
        )
        columns = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA table_info(mobile_notification_deliveries)"
            ).fetchall()
        }
        if "attempt_id" not in columns:
            connection.execute(
                "ALTER TABLE mobile_notification_deliveries ADD COLUMN attempt_id TEXT"
            )
            connection.execute(
                "UPDATE mobile_notification_deliveries SET attempt_id = id WHERE attempt_id IS NULL OR attempt_id = ''"
            )
        if "lease_expires_at" not in columns:
            connection.execute(
                "ALTER TABLE mobile_notification_deliveries ADD COLUMN lease_expires_at TEXT"
            )
            connection.execute(
                "UPDATE mobile_notification_deliveries SET lease_expires_at = updated_at WHERE lease_expires_at IS NULL OR lease_expires_at = ''"
            )

    def _migration_011_mobile_guarded_execution_claims(self, connection: sqlite3.Connection) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA table_info(mobile_action_receipts)"
            ).fetchall()
        }
        unique_execution_audit = any(
            int(index[2])
            and str(index[3]) == "u"
            and tuple(
                str(row[2])
                for row in connection.execute(
                    f"PRAGMA index_info({index[1]})"
                ).fetchall()
            )
            == ("execution_audit_id",)
            for index in connection.execute(
                "PRAGMA index_list(mobile_action_receipts)"
            ).fetchall()
        )
        if "execution_audit_id" not in columns or not unique_execution_audit:
            connection.execute(
                "ALTER TABLE mobile_action_receipts RENAME TO mobile_action_receipts_010"
            )
            connection.execute(
                """
                CREATE TABLE mobile_action_receipts (
                    id TEXT PRIMARY KEY,
                    idempotency_key_hash TEXT NOT NULL UNIQUE,
                    device_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    execution_audit_id TEXT UNIQUE
                )
                """
            )
            source_execution_audit = (
                "execution_audit_id"
                if "execution_audit_id" in columns
                else "NULL"
            )
            connection.execute(
                f"""
                INSERT INTO mobile_action_receipts (
                    id, idempotency_key_hash, device_id, action_type,
                    entity_id, payload, status, created_at, updated_at,
                    execution_audit_id
                )
                SELECT
                    id, idempotency_key_hash, device_id, action_type,
                    entity_id, payload, status, created_at, updated_at,
                    {source_execution_audit}
                FROM mobile_action_receipts_010
                """
            )
            connection.execute("DROP TABLE mobile_action_receipts_010")

    def _migration_012_genuine_source_evidence(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS accepted_market_observations (
                record_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                received_at TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                fixture_only INTEGER NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE(source, source_event_id, observed_at)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_accepted_market_observations_strategy ON accepted_market_observations(strategy_id, strategy_version, observed_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_accepted_market_observations_genuine ON accepted_market_observations(fixture_only, observed_at DESC)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_access_evidence (
                record_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                access_state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_source_access_evidence_source ON source_access_evidence(source, created_at DESC)"
        )

    def _migration_013_sniper_strategy_versions(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sniper_strategy_versions (
                strategy_id TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE,
                canonical_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(strategy_id, strategy_version)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sniper_strategy_versions_created_at ON sniper_strategy_versions(created_at DESC)"
        )

    def _migration_014_shadow_economic_comparisons(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_economic_comparisons (
                record_id TEXT PRIMARY KEY,
                strategy_version TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                evidence_mode TEXT NOT NULL,
                fixture_only INTEGER NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_shadow_economic_strategy ON shadow_economic_comparisons(strategy_version, completed_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_shadow_economic_mode ON shadow_economic_comparisons(evidence_mode, fixture_only, completed_at DESC)"
        )

    def _migration_015_sentinel_verdicts(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sentinel_verdicts (
                verdict_id TEXT PRIMARY KEY,
                strategy_version TEXT NOT NULL,
                input_version TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE(strategy_version, input_version, created_at)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sentinel_verdicts_current ON sentinel_verdicts(created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sentinel_verdicts_identity ON sentinel_verdicts(strategy_version, input_version, created_at DESC)"
        )

    def _migration_016_trade_grading(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_review_jobs (
                job_id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL UNIQUE,
                trade_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                claim_id TEXT NOT NULL DEFAULT '',
                lease_owner TEXT NOT NULL DEFAULT '',
                lease_until TEXT,
                last_error TEXT NOT NULL DEFAULT '',
                revision_payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_trade_review_jobs_claim ON trade_review_jobs(status, lease_until, created_at)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_grades (
                grade_id TEXT PRIMARY KEY,
                trade_id TEXT NOT NULL,
                revision_id TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_trade_grades_trade ON trade_grades(trade_id, created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_trade_grades_mode ON trade_grades(mode, created_at DESC)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_grade_corrections (
                correction_id TEXT PRIMARY KEY,
                grade_id TEXT NOT NULL,
                trade_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_trade_grade_corrections_trade ON trade_grade_corrections(trade_id, created_at ASC)"
        )
        self._ensure_model_classifier_schema(connection)

    def _ensure_model_classifier_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS model_classification_budget (
                budget_day TEXT PRIMARY KEY,
                tokens INTEGER NOT NULL,
                cost REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS model_classifications (
                job_id TEXT PRIMARY KEY,
                trade_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(trade_id, revision_id)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_model_classifications_trade ON model_classifications(trade_id, created_at DESC)"
        )

    def _migration_017_strategy_candidates(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_candidates (
                candidate_id TEXT PRIMARY KEY,
                base_strategy_version TEXT NOT NULL,
                proposed_strategy_version TEXT NOT NULL UNIQUE,
                fingerprint TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS candidate_validations (
                validation_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                accepted INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_candidate_validations_latest ON candidate_validations(candidate_id, created_at DESC)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_promotions (
                promotion_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                validation_id TEXT NOT NULL,
                operator_intent_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS active_strategy_selection (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                candidate_id TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                promotion_id TEXT NOT NULL,
                operator_intent_id TEXT NOT NULL,
                selected_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_validation_campaigns (
                campaign_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    def _migration_018_pilot_risk(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pilot_risk_policies (
                policy_id TEXT PRIMARY KEY,
                policy_version TEXT NOT NULL,
                reference_observation_id TEXT NOT NULL,
                settings_version TEXT NOT NULL,
                operator_intent_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pilot_risk_policies_created ON pilot_risk_policies(created_at DESC)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pilot_loss_ledger (
                loss_id TEXT PRIMARY KEY,
                policy_id TEXT NOT NULL,
                loss_sol TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pilot_loss_policy ON pilot_loss_ledger(policy_id, created_at ASC)")

    def _migration_019_production_rehearsal(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS production_rehearsal_reports (
                report_id TEXT PRIMARY KEY,
                ready INTEGER NOT NULL,
                fixture_only INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_production_rehearsal_created ON production_rehearsal_reports(created_at DESC)"
        )

    def _migration_020_manual_live_proof(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS manual_live_proof_reports (
                proof_id TEXT PRIMARY KEY,
                qualified INTEGER NOT NULL,
                wallet_public_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_manual_live_proof_created ON manual_live_proof_reports(created_at DESC)")

    def _migration_021_autonomous_pilot(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS autonomous_pilot_windows (
                window_id TEXT PRIMARY KEY,
                eligible INTEGER NOT NULL,
                opened INTEGER NOT NULL,
                wallet_public_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_pilot_created ON autonomous_pilot_windows(created_at DESC)")

    def _migration_022_post_pilot_review(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS post_pilot_reviews (
                review_id TEXT PRIMARY KEY,
                window_id TEXT NOT NULL,
                clear INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_post_pilot_reviews_created ON post_pilot_reviews(created_at DESC)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pilot_operator_decisions (
                decision_id TEXT PRIMARY KEY,
                review_id TEXT NOT NULL UNIQUE,
                decision TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pilot_decisions_created ON pilot_operator_decisions(created_at DESC)")

    def _migration_023_production_rehearsal_evidence(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS production_rehearsal_evidence (
                evidence_id TEXT PRIMARY KEY,
                gate_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_production_rehearsal_evidence_gate ON production_rehearsal_evidence(gate_id, observed_at DESC)"
        )

    def _migration_024_shadow_market_evidence_bindings(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_market_evidence_bindings (
                binding_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                market_observation_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                evidence_mode TEXT NOT NULL CHECK (evidence_mode = 'shadow'),
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE(audit_id, market_observation_id)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_shadow_market_evidence_audit ON shadow_market_evidence_bindings(audit_id, created_at ASC)"
        )

    def _migration_025_pending_shadow_audit_captures(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_shadow_audit_captures (
                audit_id TEXT PRIMARY KEY,
                mint TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                quoted_at TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                closed_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pending_shadow_capture_lookup
            ON pending_shadow_audit_captures(mint, strategy_id, strategy_version, status, quoted_at)
            """
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
            revoked_mobile = staged_storage.revoke_all_mobile_credentials_and_push_registrations(
                datetime.now(timezone.utc).isoformat()
            )
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
            return {
                **preview,
                "status": "restored",
                "backup_path": backup_path,
                "mobile_credentials_revoked": True,
                "mobile_devices_revoked": revoked_mobile["devices"],
                "mobile_push_registrations_revoked": revoked_mobile["registrations"],
            }
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

    def save_accepted_market_observation(self, observation: AcceptedMarketObservation) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO accepted_market_observations (
                    record_id, source, source_event_id, observed_at, received_at,
                    strategy_id, strategy_version, fixture_only, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.record_id,
                    observation.source,
                    observation.source_event_id,
                    observation.observed_at.isoformat(),
                    observation.received_at.isoformat(),
                    observation.strategy_id,
                    observation.strategy_version,
                    1 if observation.fixture_only else 0,
                    json.dumps(observation.to_dict()),
                ),
            )
        return cursor.rowcount == 1

    def load_accepted_market_observations(
        self,
        limit: int = 500,
        *,
        strategy_id: str = "",
        strategy_version: str = "",
    ) -> list[AcceptedMarketObservation]:
        bounded_limit = max(1, min(5000, int(limit)))
        clauses: list[str] = []
        values: list[Any] = []
        if strategy_id:
            clauses.append("strategy_id = ?")
            values.append(strategy_id)
        if strategy_version:
            clauses.append("strategy_version = ?")
            values.append(strategy_version)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(bounded_limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM accepted_market_observations{where} ORDER BY observed_at DESC LIMIT ?",
                tuple(values),
            ).fetchall()
        return [self._accepted_market_observation_from_payload(json.loads(row["payload"])) for row in rows]

    def save_shadow_market_evidence_binding(
        self,
        *,
        audit_id: str,
        market_observation_id: str,
        strategy_id: str,
        strategy_version: str,
        role: str,
        created_at: datetime,
    ) -> bool:
        binding_id = f"shadow_binding_{audit_id}_{market_observation_id}"
        payload = {
            "binding_id": binding_id,
            "audit_id": audit_id,
            "market_observation_id": market_observation_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "evidence_mode": "shadow",
            "role": role,
            "created_at": created_at.isoformat(),
        }
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO shadow_market_evidence_bindings (
                    binding_id, audit_id, market_observation_id, strategy_id,
                    strategy_version, evidence_mode, role, created_at, payload
                ) VALUES (?, ?, ?, ?, ?, 'shadow', ?, ?, ?)
                """,
                (
                    binding_id,
                    audit_id,
                    market_observation_id,
                    strategy_id,
                    strategy_version,
                    role,
                    created_at.isoformat(),
                    json.dumps(payload),
                ),
            )
        return cursor.rowcount == 1

    def load_shadow_market_evidence_bindings(self, audit_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload
                FROM shadow_market_evidence_bindings
                WHERE audit_id = ? AND evidence_mode = 'shadow'
                ORDER BY created_at ASC
                """,
                (audit_id,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def save_pending_shadow_audit_capture(
        self,
        *,
        audit_id: str,
        mint: str,
        strategy_id: str,
        strategy_version: str,
        quoted_at: datetime,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO pending_shadow_audit_captures (
                    audit_id, mint, strategy_id, strategy_version, quoted_at,
                    status, created_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL)
                """,
                (
                    audit_id,
                    mint,
                    strategy_id,
                    strategy_version,
                    quoted_at.isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def save_shadow_quote_audit_capture(
        self,
        audit: LiveExecutionAudit,
        entry_observation: AcceptedMarketObservation | None,
    ) -> None:
        comparison = audit.shadow_comparison if isinstance(audit.shadow_comparison, dict) else {}
        strategy_id = str(comparison.get("strategy_id") or "")
        strategy_version = str(comparison.get("strategy_version") or "")
        if not bool(audit.quote.get("shadow_only")) or not strategy_id or not strategy_version:
            raise ValueError("shadow audit capture requires a versioned shadow-only audit")
        if entry_observation is not None and (
            entry_observation.mint != audit.mint
            or entry_observation.strategy_id != strategy_id
            or entry_observation.strategy_version != strategy_version
            or entry_observation.fixture_only
            or entry_observation.conflict_state != "clear"
            or entry_observation.access_state != "ready"
        ):
            raise ValueError("shadow entry evidence does not match the audit identity")
        created_at = datetime.now(timezone.utc)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO pending_shadow_audit_captures (
                    audit_id, mint, strategy_id, strategy_version, quoted_at,
                    status, created_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL)
                """,
                (
                    audit.id,
                    audit.mint,
                    strategy_id,
                    strategy_version,
                    audit.created_at.isoformat(),
                    created_at.isoformat(),
                ),
            )
            if entry_observation is not None:
                binding_id = f"shadow_binding_{audit.id}_{entry_observation.record_id}"
                payload = {
                    "binding_id": binding_id,
                    "audit_id": audit.id,
                    "market_observation_id": entry_observation.record_id,
                    "strategy_id": strategy_id,
                    "strategy_version": strategy_version,
                    "evidence_mode": "shadow",
                    "role": "entry",
                    "created_at": created_at.isoformat(),
                }
                connection.execute(
                    """
                    INSERT OR IGNORE INTO shadow_market_evidence_bindings (
                        binding_id, audit_id, market_observation_id, strategy_id,
                        strategy_version, evidence_mode, role, created_at, payload
                    ) VALUES (?, ?, ?, ?, ?, 'shadow', 'entry', ?, ?)
                    """,
                    (
                        binding_id,
                        audit.id,
                        entry_observation.record_id,
                        strategy_id,
                        strategy_version,
                        created_at.isoformat(),
                        json.dumps(payload),
                    ),
                )
            connection.execute(
                """
                INSERT OR REPLACE INTO live_execution_audits (id, payload, created_at)
                VALUES (?, ?, ?)
                """,
                (audit.id, json.dumps(audit.to_dict()), audit.created_at.isoformat()),
            )

    def bind_accepted_market_observation_to_pending_shadows(
        self,
        observation: AcceptedMarketObservation,
    ) -> int:
        if observation.fixture_only or observation.conflict_state != "clear" or observation.access_state != "ready":
            return 0
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT audit_id
                FROM pending_shadow_audit_captures
                WHERE mint = ?
                  AND strategy_id = ?
                  AND strategy_version = ?
                  AND status = 'pending'
                  AND quoted_at < ?
                """,
                (
                    observation.mint,
                    observation.strategy_id,
                    observation.strategy_version,
                    observation.observed_at.isoformat(),
                ),
            ).fetchall()
            inserted = 0
            for row in rows:
                audit_id = str(row["audit_id"])
                binding_id = f"shadow_binding_{audit_id}_{observation.record_id}"
                payload = {
                    "binding_id": binding_id,
                    "audit_id": audit_id,
                    "market_observation_id": observation.record_id,
                    "strategy_id": observation.strategy_id,
                    "strategy_version": observation.strategy_version,
                    "evidence_mode": "shadow",
                    "role": "path",
                    "created_at": created_at,
                }
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO shadow_market_evidence_bindings (
                        binding_id, audit_id, market_observation_id, strategy_id,
                        strategy_version, evidence_mode, role, created_at, payload
                    ) VALUES (?, ?, ?, ?, ?, 'shadow', 'path', ?, ?)
                    """,
                    (
                        binding_id,
                        audit_id,
                        observation.record_id,
                        observation.strategy_id,
                        observation.strategy_version,
                        created_at,
                        json.dumps(payload),
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def close_pending_shadow_audit_capture(self, audit_id: str, *, closed_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE pending_shadow_audit_captures
                SET status = 'closed', closed_at = ?
                WHERE audit_id = ? AND status = 'pending'
                """,
                (closed_at.isoformat(), audit_id),
            )

    def count_pending_shadow_audit_captures(self, audit_id: str = "") -> int:
        with self._connect() as connection:
            if audit_id:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM pending_shadow_audit_captures WHERE audit_id = ?",
                    (audit_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM pending_shadow_audit_captures"
                ).fetchone()
        return int(row["count"] if row else 0)

    def save_source_access_evidence(self, payload: dict[str, Any]) -> None:
        created_at = str(payload.get("created_at") or datetime.now(timezone.utc).isoformat())
        record_id = str(payload.get("record_id") or f"source_access_{uuid.uuid4().hex}")
        source = str(payload.get("source") or "unknown")
        access_state = str(payload.get("access_state") or "unknown")
        stored = {**payload, "record_id": record_id, "created_at": created_at}
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO source_access_evidence (record_id, source, access_state, created_at, payload) VALUES (?, ?, ?, ?, ?)",
                (record_id, source, access_state, created_at, json.dumps(stored)),
            )

    def load_source_access_evidence(self, limit: int = 100, *, source: str = "") -> list[dict[str, Any]]:
        bounded_limit = max(1, min(1000, int(limit)))
        with self._connect() as connection:
            if source:
                rows = connection.execute(
                    "SELECT payload FROM source_access_evidence WHERE source = ? ORDER BY created_at DESC LIMIT ?",
                    (source, bounded_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload FROM source_access_evidence ORDER BY created_at DESC LIMIT ?",
                    (bounded_limit,),
                ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def save_sniper_strategy_version(self, strategy: SniperStrategyVersion) -> bool:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT canonical_json FROM sniper_strategy_versions WHERE strategy_id = ? AND strategy_version = ?",
                (strategy.strategy_id, strategy.strategy_version),
            ).fetchone()
            if existing:
                if str(existing["canonical_json"]) != strategy.canonical_json():
                    raise ValueError("strategy version already exists with different content")
                return False
            connection.execute(
                "INSERT INTO sniper_strategy_versions (strategy_id, strategy_version, fingerprint, canonical_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    strategy.strategy_id,
                    strategy.strategy_version,
                    strategy.fingerprint(),
                    strategy.canonical_json(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return True

    def load_sniper_strategy_versions(self, limit: int = 50) -> list[SniperStrategyVersion]:
        bounded_limit = max(1, min(500, int(limit)))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT canonical_json FROM sniper_strategy_versions ORDER BY created_at DESC LIMIT ?",
                (bounded_limit,),
            ).fetchall()
        return [SniperStrategyVersion.from_dict(json.loads(row["canonical_json"])) for row in rows]

    def save_shadow_comparison(self, comparison: ShadowComparison) -> bool:
        serialized = json.dumps(comparison.to_dict(), sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM shadow_economic_comparisons WHERE record_id = ?",
                (comparison.record_id,),
            ).fetchone()
            if existing:
                if json.dumps(json.loads(existing["payload"]), sort_keys=True) != serialized:
                    raise ValueError("shadow comparison record already exists with different content")
                return False
            connection.execute(
                """
                INSERT OR REPLACE INTO shadow_economic_comparisons (
                    record_id, strategy_version, completed_at, evidence_mode, fixture_only, payload
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    comparison.record_id,
                    comparison.strategy_version,
                    comparison.completed_at.isoformat(),
                    comparison.evidence_mode,
                    1 if comparison.fixture_only else 0,
                    serialized,
                ),
            )
        return True

    def load_shadow_comparisons(self, limit: int = 500, *, strategy_version: str = "") -> list[ShadowComparison]:
        bounded_limit = max(1, min(5000, int(limit)))
        with self._connect() as connection:
            if strategy_version:
                rows = connection.execute(
                    "SELECT payload FROM shadow_economic_comparisons WHERE strategy_version = ? ORDER BY completed_at ASC LIMIT ?",
                    (strategy_version, bounded_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload FROM shadow_economic_comparisons ORDER BY completed_at ASC LIMIT ?",
                    (bounded_limit,),
                ).fetchall()
        return [self._shadow_comparison_from_payload(json.loads(row["payload"])) for row in rows]

    def publish_sentinel_verdict(
        self,
        verdict: SentinelVerdict,
        *,
        active_strategy_version: str,
        current_input_version: str,
    ) -> bool:
        """Publish only while the caller's immutable read snapshot is still current."""
        if verdict.strategy_version != active_strategy_version or verdict.input_version != current_input_version:
            return False
        serialized = json.dumps(verdict.to_dict(), sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM sentinel_verdicts WHERE verdict_id = ?",
                (verdict.verdict_id,),
            ).fetchone()
            if existing:
                if json.dumps(json.loads(existing["payload"]), sort_keys=True) != serialized:
                    raise ValueError("sentinel verdict already exists with different content")
                return False
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO sentinel_verdicts (
                    verdict_id, strategy_version, input_version, status,
                    created_at, expires_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    verdict.verdict_id,
                    verdict.strategy_version,
                    verdict.input_version,
                    verdict.status,
                    verdict.created_at.isoformat(),
                    verdict.expires_at.isoformat(),
                    serialized,
                ),
            )
        return cursor.rowcount == 1

    def load_current_sentinel_verdict(self) -> SentinelVerdict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM sentinel_verdicts ORDER BY created_at DESC, verdict_id DESC LIMIT 1"
            ).fetchone()
        return self._sentinel_verdict_from_payload(json.loads(row["payload"])) if row else None

    def load_sentinel_history(self, limit: int = 100) -> list[SentinelVerdict]:
        bounded_limit = max(1, min(100, int(limit)))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM sentinel_verdicts ORDER BY created_at DESC, verdict_id DESC LIMIT ?",
                (bounded_limit,),
            ).fetchall()
        return [self._sentinel_verdict_from_payload(json.loads(row["payload"])) for row in rows]

    def enqueue_trade_review(self, revision: TradeRevision, *, max_pending: int = 10000) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        job_id = f"review_{uuid.uuid5(uuid.NAMESPACE_URL, revision.revision_id).hex}"
        with self._connect() as connection:
            pending = connection.execute(
                "SELECT COUNT(*) AS count FROM trade_review_jobs WHERE status IN ('queued', 'processing')"
            ).fetchone()
            if int(pending["count"] if pending else 0) >= max(1, max_pending):
                return False
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO trade_review_jobs (
                    job_id, revision_id, trade_id, mode, status, revision_payload,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)
                """,
                (job_id, revision.revision_id, revision.trade_id, revision.mode, json.dumps(revision.to_dict(), sort_keys=True), now, now),
            )
        return cursor.rowcount == 1

    def trade_review_queue_stats(self) -> dict[str, int]:
        with self.read_connection() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM trade_review_jobs GROUP BY status"
            ).fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        return {
            "queued": counts.get("queued", 0),
            "processing": counts.get("processing", 0),
            "dead_letter": counts.get("dead_letter", 0),
            "completed": counts.get("completed", 0),
        }

    def claim_trade_review(
        self,
        lease_owner: str,
        lease_until: datetime,
        *,
        now: datetime | None = None,
    ) -> TradeReviewJob | None:
        claimed_at = now or datetime.now(timezone.utc)
        claim_id = f"claim_{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM trade_review_jobs
                WHERE status = 'queued'
                   OR (status = 'processing' AND lease_until IS NOT NULL AND lease_until <= ?)
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (claimed_at.isoformat(),),
            ).fetchone()
            if row is None:
                return None
            cursor = connection.execute(
                """
                UPDATE trade_review_jobs
                SET status = 'processing', attempts = attempts + 1, claim_id = ?,
                    lease_owner = ?, lease_until = ?, updated_at = ?
                WHERE job_id = ? AND (
                    status = 'queued'
                    OR (status = 'processing' AND lease_until IS NOT NULL AND lease_until <= ?)
                )
                """,
                (claim_id, lease_owner, lease_until.isoformat(), claimed_at.isoformat(), row["job_id"], claimed_at.isoformat()),
            )
            if cursor.rowcount != 1:
                return None
            claimed = connection.execute("SELECT * FROM trade_review_jobs WHERE job_id = ?", (row["job_id"],)).fetchone()
        return self._trade_review_job_from_row(claimed)

    def finish_trade_review(
        self,
        job_id: str,
        claim_id: str,
        expected_revision: str,
        result: TradeGrade,
    ) -> bool:
        serialized = json.dumps(result.to_dict(), sort_keys=True)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revision_id, trade_id, mode FROM trade_review_jobs WHERE job_id = ? AND status = 'processing' AND claim_id = ?",
                (job_id, claim_id),
            ).fetchone()
            if row is None or str(row["revision_id"]) != expected_revision:
                return False
            if result.revision_id != expected_revision or result.trade_id != str(row["trade_id"]) or result.mode != str(row["mode"]):
                return False
            connection.execute(
                "INSERT OR IGNORE INTO trade_grades (grade_id, trade_id, revision_id, mode, created_at, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (result.grade_id, result.trade_id, result.revision_id, result.mode, result.created_at.isoformat(), serialized),
            )
            cursor = connection.execute(
                "UPDATE trade_review_jobs SET status = 'completed', lease_until = NULL, updated_at = ? WHERE job_id = ? AND claim_id = ?",
                (now, job_id, claim_id),
            )
        return cursor.rowcount == 1

    def fail_trade_review(
        self,
        job_id: str,
        claim_id: str,
        error: str,
        *,
        max_attempts: int = 3,
    ) -> str:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT attempts FROM trade_review_jobs WHERE job_id = ? AND status = 'processing' AND claim_id = ?",
                (job_id, claim_id),
            ).fetchone()
            if row is None:
                return "stale_claim"
            status = "dead_letter" if int(row["attempts"]) >= max(1, max_attempts) else "queued"
            connection.execute(
                "UPDATE trade_review_jobs SET status = ?, claim_id = '', lease_owner = '', lease_until = NULL, last_error = ?, updated_at = ? WHERE job_id = ? AND claim_id = ?",
                (status, error[:1000], now, job_id, claim_id),
            )
        return status

    def load_trade_grades(self, trade_id: str = "", *, mode: str = "", limit: int = 500) -> list[TradeGrade]:
        clauses: list[str] = []
        values: list[Any] = []
        if trade_id:
            clauses.append("trade_id = ?")
            values.append(trade_id)
        if mode:
            clauses.append("mode = ?")
            values.append(mode)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, min(5000, limit)))
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM trade_grades{where} ORDER BY created_at DESC LIMIT ?",
                tuple(values),
            ).fetchall()
        return [self._trade_grade_from_payload(json.loads(row["payload"])) for row in rows]

    def append_trade_grade_correction(self, correction: TradeGradeCorrection) -> bool:
        serialized = json.dumps(correction.to_dict(), sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM trade_grade_corrections WHERE correction_id = ?", (correction.correction_id,)
            ).fetchone()
            if existing:
                if json.dumps(json.loads(existing["payload"]), sort_keys=True) != serialized:
                    raise ValueError("trade grade correction already exists with different content")
                return False
            connection.execute(
                "INSERT INTO trade_grade_corrections (correction_id, grade_id, trade_id, created_at, payload) VALUES (?, ?, ?, ?, ?)",
                (correction.correction_id, correction.grade_id, correction.trade_id, correction.created_at.isoformat(), serialized),
            )
        return True

    def load_trade_grade_corrections(self, trade_id: str, limit: int = 500) -> list[TradeGradeCorrection]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM trade_grade_corrections WHERE trade_id = ? ORDER BY created_at ASC LIMIT ?",
                (trade_id, max(1, min(5000, limit))),
            ).fetchall()
        return [self._trade_grade_correction_from_payload(json.loads(row["payload"])) for row in rows]

    def reserve_model_classification_budget(
        self,
        budget_day: str,
        *,
        tokens: int,
        cost: float,
        token_limit: int,
        cost_limit: float,
    ) -> bool:
        if tokens < 0 or cost < 0 or not budget_day:
            return False
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT tokens, cost FROM model_classification_budget WHERE budget_day = ?",
                (budget_day,),
            ).fetchone()
            used_tokens = int(row["tokens"] if row else 0)
            used_cost = float(row["cost"] if row else 0.0)
            if used_tokens + tokens > max(0, token_limit) or used_cost + cost > max(0.0, cost_limit):
                return False
            connection.execute(
                """
                INSERT INTO model_classification_budget (budget_day, tokens, cost, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(budget_day) DO UPDATE SET tokens = excluded.tokens, cost = excluded.cost, updated_at = excluded.updated_at
                """,
                (budget_day, used_tokens + tokens, used_cost + cost, now),
            )
        return True

    def model_classification_budget(self, budget_day: str) -> dict[str, int | float]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT tokens, cost FROM model_classification_budget WHERE budget_day = ?", (budget_day,)
            ).fetchone()
        return {"tokens": int(row["tokens"]), "cost": float(row["cost"])} if row else {"tokens": 0, "cost": 0.0}

    def save_model_classification(self, classification: ModelClassification) -> bool:
        payload = asdict(classification)
        serialized = json.dumps(payload, sort_keys=True)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM model_classifications WHERE job_id = ?", (classification.job_id,)
            ).fetchone()
            if existing:
                if json.dumps(json.loads(existing["payload"]), sort_keys=True) != serialized:
                    raise ValueError("model classification already exists with different content")
                return False
            cursor = connection.execute(
                "INSERT OR IGNORE INTO model_classifications (job_id, trade_id, revision_id, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (classification.job_id, classification.trade_id, classification.revision_id, serialized, now),
            )
        return cursor.rowcount == 1

    def load_model_classifications(self, trade_id: str = "", limit: int = 500) -> list[ModelClassification]:
        bounded = max(1, min(5000, limit))
        with self._connect() as connection:
            if trade_id:
                rows = connection.execute(
                    "SELECT payload FROM model_classifications WHERE trade_id = ? ORDER BY created_at DESC LIMIT ?",
                    (trade_id, bounded),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload FROM model_classifications ORDER BY created_at DESC LIMIT ?", (bounded,)
                ).fetchall()
        return [ModelClassification(**json.loads(row["payload"])) for row in rows]

    def save_strategy_candidate(self, candidate: StrategyCandidate) -> bool:
        serialized = json.dumps(candidate.to_dict(), sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM strategy_candidates WHERE candidate_id = ?", (candidate.candidate_id,)
            ).fetchone()
            if existing:
                if json.dumps(json.loads(existing["payload"]), sort_keys=True) != serialized:
                    raise ValueError("strategy candidate already exists with different content")
                return False
            connection.execute(
                "INSERT INTO strategy_candidates (candidate_id, base_strategy_version, proposed_strategy_version, fingerprint, created_at, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (candidate.candidate_id, candidate.base_strategy_version, candidate.proposed_strategy_version, candidate.fingerprint, candidate.created_at.isoformat(), serialized),
            )
        return True

    def load_strategy_candidate(self, candidate_id: str) -> StrategyCandidate | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM strategy_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return self._strategy_candidate_from_payload(json.loads(row["payload"])) if row else None

    def load_strategy_candidates(self, limit: int = 100) -> list[StrategyCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM strategy_candidates ORDER BY created_at DESC LIMIT ?", (max(1, min(500, limit)),)
            ).fetchall()
        return [self._strategy_candidate_from_payload(json.loads(row["payload"])) for row in rows]

    def save_candidate_validation(self, validation: CandidateValidation) -> bool:
        serialized = json.dumps(validation.to_dict(), sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM candidate_validations WHERE validation_id = ?", (validation.validation_id,)
            ).fetchone()
            if existing:
                if json.dumps(json.loads(existing["payload"]), sort_keys=True) != serialized:
                    raise ValueError("candidate validation already exists with different content")
                return False
            connection.execute(
                "INSERT INTO candidate_validations (validation_id, candidate_id, accepted, created_at, payload) VALUES (?, ?, ?, ?, ?)",
                (validation.validation_id, validation.candidate_id, 1 if validation.accepted else 0, validation.created_at.isoformat(), serialized),
            )
        return True

    def load_latest_candidate_validation(self, candidate_id: str) -> CandidateValidation | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM candidate_validations WHERE candidate_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (candidate_id,),
            ).fetchone()
        return self._candidate_validation_from_payload(json.loads(row["payload"])) if row else None

    def load_active_strategy_selection(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM active_strategy_selection WHERE id = 1").fetchone()
        return json.loads(row["payload"]) if row else None

    def promote_strategy_candidate(
        self,
        candidate: StrategyCandidate,
        validation: CandidateValidation,
        promotion_id: str,
        operator_intent_id: str,
        now: datetime,
    ) -> bool:
        payload = {
            "promotion_id": promotion_id,
            "candidate_id": candidate.candidate_id,
            "strategy_version": candidate.proposed_strategy_version,
            "validation_id": validation.validation_id,
            "operator_intent_id": operator_intent_id,
            "selected_at": now.isoformat(),
            "validation_campaign_status": "required",
            "sentinel_status": "invalidated",
        }
        serialized = json.dumps(payload, sort_keys=True)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            latest = connection.execute(
                "SELECT validation_id, accepted FROM candidate_validations WHERE candidate_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (candidate.candidate_id,),
            ).fetchone()
            if latest is None or str(latest["validation_id"]) != validation.validation_id or not bool(latest["accepted"]):
                return False
            existing = connection.execute("SELECT payload FROM strategy_promotions WHERE promotion_id = ?", (promotion_id,)).fetchone()
            if existing:
                return json.dumps(json.loads(existing["payload"]), sort_keys=True) == serialized
            connection.execute(
                "INSERT INTO strategy_promotions (promotion_id, candidate_id, validation_id, operator_intent_id, created_at, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (promotion_id, candidate.candidate_id, validation.validation_id, operator_intent_id, now.isoformat(), serialized),
            )
            connection.execute(
                "INSERT OR REPLACE INTO active_strategy_selection (id, candidate_id, strategy_version, promotion_id, operator_intent_id, selected_at, payload) VALUES (1, ?, ?, ?, ?, ?, ?)",
                (candidate.candidate_id, candidate.proposed_strategy_version, promotion_id, operator_intent_id, now.isoformat(), serialized),
            )
            connection.execute(
                "INSERT OR IGNORE INTO strategy_validation_campaigns (campaign_id, candidate_id, strategy_version, status, created_at) VALUES (?, ?, ?, 'required', ?)",
                (f"campaign_{promotion_id}", candidate.candidate_id, candidate.proposed_strategy_version, now.isoformat()),
            )
        return True

    def save_pilot_risk_policy(self, policy: PilotRiskPolicy) -> bool:
        serialized = json.dumps(policy.to_dict(), sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM pilot_risk_policies WHERE policy_id = ?", (policy.policy_id,)
            ).fetchone()
            if existing:
                if json.dumps(json.loads(existing["payload"]), sort_keys=True) != serialized:
                    raise ValueError("pilot risk policy already exists with different content")
                return False
            connection.execute(
                "INSERT INTO pilot_risk_policies (policy_id, policy_version, reference_observation_id, settings_version, operator_intent_id, created_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (policy.policy_id, policy.policy_version, policy.reference_observation_id, policy.settings_version, policy.operator_intent_id, policy.created_at.isoformat(), serialized),
            )
        return True

    def load_latest_pilot_risk_policy(self) -> PilotRiskPolicy | None:
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT payload FROM pilot_risk_policies ORDER BY created_at DESC, policy_id DESC LIMIT 1"
            ).fetchone()
        return PilotRiskPolicy.from_dict(json.loads(row["payload"])) if row else None

    def load_pilot_risk_policy(self, policy_id: str) -> PilotRiskPolicy | None:
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT payload FROM pilot_risk_policies WHERE policy_id = ?",
                (policy_id,),
            ).fetchone()
        return PilotRiskPolicy.from_dict(json.loads(row["payload"])) if row else None

    def append_pilot_outcome(
        self,
        policy_id: str,
        window_id: str,
        outcome_id: str,
        pnl_sol: Decimal,
        created_at: datetime,
    ) -> bool:
        amount = Decimal(pnl_sol)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("pilot outcome timestamp must be timezone-aware")
        loss = max(Decimal("0"), -amount)
        payload = {
            "loss_id": outcome_id,
            "outcome_id": outcome_id,
            "policy_id": policy_id,
            "window_id": window_id,
            "pnl_sol": str(amount),
            "loss_sol": str(loss),
            "created_at": created_at.astimezone(timezone.utc).isoformat(),
        }
        serialized = json.dumps(payload, sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute("SELECT payload FROM pilot_loss_ledger WHERE loss_id = ?", (outcome_id,)).fetchone()
            if existing:
                if json.dumps(json.loads(existing["payload"]), sort_keys=True) != serialized:
                    raise ValueError("pilot outcome already exists with different content")
                return False
            connection.execute(
                "INSERT INTO pilot_loss_ledger (loss_id, policy_id, loss_sol, created_at, payload) VALUES (?, ?, ?, ?, ?)",
                (outcome_id, policy_id, str(loss), payload["created_at"], serialized),
            )
        return True

    def append_pilot_loss(self, policy_id: str, loss_id: str, loss_sol: Decimal, created_at: datetime) -> bool:
        amount = Decimal(loss_sol)
        if amount <= 0:
            raise ValueError("pilot loss ledger accepts positive loss magnitudes only")
        return self.append_pilot_outcome(policy_id, "legacy-unscoped", loss_id, -amount, created_at)

    def pilot_loss_ledger(self, policy_id: str) -> dict[str, Any]:
        with self.read_connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM pilot_loss_ledger WHERE policy_id = ? ORDER BY created_at ASC, loss_id ASC",
                (policy_id,),
            ).fetchall()
        entries = [json.loads(row["payload"]) for row in rows]
        cumulative = sum((Decimal(str(item.get("loss_sol") or "0")) for item in entries), Decimal("0"))
        return {"policy_id": policy_id, "cumulative_loss_sol": str(cumulative), "entries": entries}

    def save_production_rehearsal_report(self, report: dict[str, Any]) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat()
        report_id = f"production_rehearsal_{uuid.uuid4().hex}"
        payload = {**report, "report_id": report_id, "created_at": created_at}
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO production_rehearsal_reports (report_id, ready, fixture_only, created_at, payload) VALUES (?, ?, ?, ?, ?)",
                (report_id, int(bool(report.get("ready"))), int(bool(report.get("fixture_only", True))), created_at, json.dumps(payload, sort_keys=True)),
            )
        return payload

    def append_production_rehearsal_evidence(self, evidence: dict[str, Any]) -> bool:
        evidence_id = str(evidence.get("evidence_id") or "").strip()
        gate_id = str(evidence.get("gate_id") or "").strip()
        if not evidence_id or not gate_id:
            raise ValueError("production rehearsal evidence ID and gate ID are required")
        observed_at = datetime.fromisoformat(str(evidence.get("observed_at") or ""))
        expires_at = datetime.fromisoformat(str(evidence.get("expires_at") or ""))
        if (
            observed_at.tzinfo is None
            or observed_at.utcoffset() is None
            or expires_at.tzinfo is None
            or expires_at.utcoffset() is None
            or expires_at <= observed_at
        ):
            raise ValueError("production rehearsal evidence requires an aware bounded validity window")
        payload = {
            "evidence_id": evidence_id,
            "gate_id": gate_id,
            "scope": str(evidence.get("scope") or ""),
            "passed": evidence.get("passed") is True,
            "fixture_only": evidence.get("fixture_only") is not False,
            "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
            "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        }
        serialized = json.dumps(payload, sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM production_rehearsal_evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
            if existing:
                if json.dumps(json.loads(existing["payload"]), sort_keys=True) != serialized:
                    raise ValueError("production rehearsal evidence already exists with different content")
                return False
            connection.execute(
                "INSERT INTO production_rehearsal_evidence (evidence_id, gate_id, observed_at, expires_at, payload) VALUES (?, ?, ?, ?, ?)",
                (evidence_id, gate_id, payload["observed_at"], payload["expires_at"], serialized),
            )
        return True

    def load_production_rehearsal_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT payload FROM production_rehearsal_evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def load_latest_production_rehearsal_report(self) -> dict[str, Any] | None:
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT payload FROM production_rehearsal_reports ORDER BY created_at DESC, report_id DESC LIMIT 1"
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def save_manual_live_proof_report(self, report: dict[str, Any]) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat()
        proof_id = f"manual_live_proof_{uuid.uuid4().hex}"
        payload = {**report, "proof_id": proof_id, "created_at": created_at}
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO manual_live_proof_reports (proof_id, qualified, wallet_public_key, created_at, payload) VALUES (?, ?, ?, ?, ?)",
                (proof_id, int(bool(report.get("qualified"))), str(report.get("wallet_public_key") or ""), created_at, json.dumps(payload, sort_keys=True)),
            )
        return payload

    def load_latest_manual_live_proof_report(self) -> dict[str, Any] | None:
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT payload FROM manual_live_proof_reports ORDER BY created_at DESC, proof_id DESC LIMIT 1"
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def save_autonomous_pilot_window(self, window: dict[str, Any]) -> dict[str, Any]:
        window_id = str(window.get("window_id") or "").strip()
        if not window_id:
            raise ValueError("autonomous pilot window ID is required")
        created_at = datetime.now(timezone.utc).isoformat()
        payload = {**window, "recorded_at": created_at}
        serialized = json.dumps(payload, sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute("SELECT payload FROM autonomous_pilot_windows WHERE window_id = ?", (window_id,)).fetchone()
            if existing:
                existing_payload = json.loads(existing["payload"])
                comparable = {key: value for key, value in existing_payload.items() if key != "recorded_at"}
                if json.dumps(comparable, sort_keys=True) != json.dumps(window, sort_keys=True):
                    raise ValueError("autonomous pilot window already exists with different content")
                return existing_payload
            connection.execute(
                "INSERT INTO autonomous_pilot_windows (window_id, eligible, opened, wallet_public_key, created_at, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (window_id, int(bool(window.get("eligible"))), int(bool(window.get("opened"))), str(window.get("wallet_public_key") or ""), created_at, serialized),
            )
        return payload

    def load_latest_autonomous_pilot_window(self) -> dict[str, Any] | None:
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT payload FROM autonomous_pilot_windows ORDER BY created_at DESC, window_id DESC LIMIT 1"
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def load_autonomous_pilot_window(self, window_id: str) -> dict[str, Any] | None:
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT payload FROM autonomous_pilot_windows WHERE window_id = ?",
                (window_id,),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def stop_autonomous_pilot_window(
        self,
        window_id: str,
        settings: BotSettings,
        blockers: list[str],
        stopped_at: datetime,
    ) -> dict[str, Any]:
        if stopped_at.tzinfo is None or stopped_at.utcoffset() is None:
            raise ValueError("pilot stop timestamp must be timezone-aware")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM autonomous_pilot_windows WHERE window_id = ?",
                (window_id,),
            ).fetchone()
            if row is None:
                raise ValueError("autonomous pilot window was not found")
            payload = json.loads(row["payload"])
            payload.update(
                {
                    "status": "CLOSED",
                    "active": False,
                    "stop_blockers": list(dict.fromkeys(str(item) for item in blockers if item)),
                    "stopped_at": stopped_at.astimezone(timezone.utc).isoformat(),
                    "automatic_restart_allowed": False,
                    "requires_post_run_review": True,
                }
            )
            connection.execute(
                "UPDATE autonomous_pilot_windows SET payload = ? WHERE window_id = ?",
                (json.dumps(payload, sort_keys=True), window_id),
            )
            connection.execute(
                "INSERT OR REPLACE INTO settings (id, payload) VALUES (1, ?)",
                (json.dumps(asdict(settings)),),
            )
        return payload

    def save_post_pilot_review(self, review: dict[str, Any]) -> dict[str, Any]:
        review_id = str(review.get("review_id") or "").strip()
        if not review_id:
            raise ValueError("post-pilot review ID is required")
        created_at = datetime.now(timezone.utc).isoformat()
        payload = {**review, "created_at": created_at}
        serialized = json.dumps(payload, sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute("SELECT payload FROM post_pilot_reviews WHERE review_id = ?", (review_id,)).fetchone()
            if existing:
                existing_payload = json.loads(existing["payload"])
                comparable = {key: value for key, value in existing_payload.items() if key != "created_at"}
                if json.dumps(comparable, sort_keys=True) != json.dumps(review, sort_keys=True):
                    raise ValueError("post-pilot review already exists with different content")
                return existing_payload
            connection.execute(
                "INSERT INTO post_pilot_reviews (review_id, window_id, clear, created_at, payload) VALUES (?, ?, ?, ?, ?)",
                (review_id, str(review.get("window_id") or ""), int(bool(review.get("clear"))), created_at, serialized),
            )
        return payload

    def load_post_pilot_review(self, review_id: str = "") -> dict[str, Any] | None:
        with self.read_connection() as connection:
            if review_id:
                row = connection.execute("SELECT payload FROM post_pilot_reviews WHERE review_id = ?", (review_id,)).fetchone()
            else:
                row = connection.execute("SELECT payload FROM post_pilot_reviews ORDER BY created_at DESC, review_id DESC LIMIT 1").fetchone()
        return json.loads(row["payload"]) if row else None

    def save_pilot_operator_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        decision_id = str(decision.get("decision_id") or "").strip()
        review_id = str(decision.get("review_id") or "").strip()
        if not decision_id or not review_id:
            raise ValueError("pilot decision and review IDs are required")
        serialized = json.dumps(decision, sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute("SELECT payload FROM pilot_operator_decisions WHERE review_id = ?", (review_id,)).fetchone()
            if existing:
                existing_payload = json.loads(existing["payload"])
                if json.dumps(existing_payload, sort_keys=True) != serialized:
                    raise ValueError("post-pilot review already has a different operator decision")
                return existing_payload
            connection.execute(
                "INSERT INTO pilot_operator_decisions (decision_id, review_id, decision, created_at, payload) VALUES (?, ?, ?, ?, ?)",
                (decision_id, review_id, str(decision.get("decision") or ""), str(decision.get("created_at") or datetime.now(timezone.utc).isoformat()), serialized),
            )
        return decision

    def load_pilot_operator_decision(self, review_id: str) -> dict[str, Any] | None:
        with self.read_connection() as connection:
            row = connection.execute("SELECT payload FROM pilot_operator_decisions WHERE review_id = ?", (review_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

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

    def claim_mobile_pairing_request(
        self,
        *,
        pairing_id: str,
        presented_code_hash: str,
        device: dict[str, Any],
        claimed_at: str,
        default_max_failed_attempts: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate and consume a one-time pairing request in one write transaction."""
        rejection = ""
        claimed_pairing: dict[str, Any] | None = None
        claimed_device: dict[str, Any] | None = None
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload, expires_at, claimed_at FROM mobile_pairing_requests WHERE id = ?",
                (pairing_id,),
            ).fetchone()
            if not row:
                rejection = "Invalid or expired mobile pairing code"
            else:
                pairing = json.loads(row["payload"])
                existing_claimed_at = str(row["claimed_at"] or pairing.get("claimed_at") or "")
                try:
                    expires_at = datetime.fromisoformat(
                        str(row["expires_at"] or pairing.get("expires_at") or "").replace("Z", "+00:00")
                    )
                    now = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
                except ValueError:
                    expires_at = datetime.min.replace(tzinfo=timezone.utc)
                    now = datetime.max.replace(tzinfo=timezone.utc)
                failed_attempts = int(pairing.get("failed_attempts") or 0)
                max_failed_attempts = int(
                    pairing.get("max_failed_attempts") or default_max_failed_attempts
                )
                if existing_claimed_at:
                    rejection = "Mobile pairing code has already been claimed"
                elif expires_at <= now:
                    rejection = "Mobile pairing code has expired"
                elif failed_attempts >= max_failed_attempts:
                    rejection = "Mobile pairing code has too many failed attempts"
                elif not hmac.compare_digest(
                    presented_code_hash,
                    str(pairing.get("code_hash") or ""),
                ):
                    pairing["failed_attempts"] = failed_attempts + 1
                    connection.execute(
                        "UPDATE mobile_pairing_requests SET payload = ? WHERE id = ?",
                        (json.dumps(pairing), pairing_id),
                    )
                    rejection = "Invalid or expired mobile pairing code"
                else:
                    claimed_device = dict(device)
                    claimed_device["scopes"] = list(pairing.get("scopes") or [])
                    pairing["claimed_at"] = claimed_at
                    pairing["claimed_device_id"] = str(claimed_device["id"])
                    cursor = connection.execute(
                        """
                        UPDATE mobile_pairing_requests
                        SET payload = ?, claimed_at = ?
                        WHERE id = ? AND (claimed_at IS NULL OR claimed_at = '')
                        """,
                        (json.dumps(pairing), claimed_at, pairing_id),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("Mobile pairing claim lost its conditional update")
                    connection.execute(
                        """
                        INSERT INTO mobile_devices (id, payload, created_at, last_seen_at, revoked_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            str(claimed_device["id"]),
                            json.dumps(claimed_device),
                            str(claimed_device.get("created_at") or claimed_at),
                            str(claimed_device.get("last_seen_at") or ""),
                            str(claimed_device.get("revoked_at") or ""),
                        ),
                    )
                    claimed_pairing = pairing

        if rejection:
            raise ValueError(rejection)
        if claimed_pairing is None or claimed_device is None:
            raise RuntimeError("Mobile pairing claim did not produce a device")
        return claimed_pairing, claimed_device

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

    def revoke_mobile_device_and_push_registrations(
        self,
        device_id: str,
        revoked_at: str,
    ) -> tuple[dict[str, Any], bool] | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload, revoked_at FROM mobile_devices WHERE id = ?",
                (device_id,),
            ).fetchone()
            if not row:
                return None
            payload = json.loads(row["payload"])
            existing_revoked_at = str(
                row["revoked_at"] or payload.get("revoked_at") or ""
            )
            newly_revoked = not existing_revoked_at
            effective_revoked_at = existing_revoked_at or revoked_at
            payload["revoked_at"] = effective_revoked_at
            connection.execute(
                "UPDATE mobile_devices SET payload = ?, revoked_at = ? WHERE id = ?",
                (json.dumps(payload), effective_revoked_at, device_id),
            )
            connection.execute(
                """
                UPDATE mobile_push_registrations
                SET revoked_at = ?, updated_at = ?
                WHERE device_id = ? AND (revoked_at IS NULL OR revoked_at = '')
                """,
                (revoked_at, revoked_at, device_id),
            )
            return payload, newly_revoked

    def save_mobile_push_registration(
        self,
        registration: MobilePushRegistration,
    ) -> MobilePushRegistration:
        payload = registration.to_dict()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE mobile_push_registrations
                SET revoked_at = ?, updated_at = ?
                WHERE device_id = ?
                  AND token_fingerprint != ?
                  AND (revoked_at IS NULL OR revoked_at = '')
                """,
                (
                    payload["updated_at"],
                    payload["updated_at"],
                    payload["device_id"],
                    payload["token_fingerprint"],
                ),
            )
            connection.execute(
                """
                INSERT INTO mobile_push_registrations (
                    id, device_id, token_ciphertext, token_fingerprint, platform,
                    created_at, updated_at, revoked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(token_fingerprint) DO UPDATE SET
                    device_id = excluded.device_id,
                    token_ciphertext = excluded.token_ciphertext,
                    platform = excluded.platform,
                    updated_at = excluded.updated_at,
                    revoked_at = excluded.revoked_at
                """,
                (
                    payload["id"],
                    payload["device_id"],
                    payload["token_ciphertext"],
                    payload["token_fingerprint"],
                    payload["platform"],
                    payload["created_at"],
                    payload["updated_at"],
                    payload["revoked_at"],
                ),
            )
            row = connection.execute(
                """
                SELECT id, device_id, token_ciphertext, token_fingerprint, platform,
                       created_at, updated_at, revoked_at
                FROM mobile_push_registrations
                WHERE token_fingerprint = ?
                """,
                (payload["token_fingerprint"],),
            ).fetchone()
        if not row:
            raise RuntimeError("Mobile push registration persistence failed")
        return MobilePushRegistration(
            id=str(row["id"]),
            device_id=str(row["device_id"]),
            token_ciphertext=str(row["token_ciphertext"]),
            token_fingerprint=str(row["token_fingerprint"]),
            platform=str(row["platform"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
            revoked_at=(
                datetime.fromisoformat(str(row["revoked_at"]))
                if str(row["revoked_at"] or "")
                else None
            ),
        )

    def load_mobile_push_registrations(self, include_revoked: bool = False, limit: int = 200) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(1000, int(limit or 200)))
        where_clause = "" if include_revoked else "WHERE revoked_at IS NULL OR revoked_at = ''"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, device_id, token_ciphertext, token_fingerprint, platform,
                       created_at, updated_at, revoked_at
                FROM mobile_push_registrations
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def revoke_mobile_push_registrations(
        self,
        *,
        device_id: str,
        revoked_at: str,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE mobile_push_registrations
                SET revoked_at = ?, updated_at = ?
                WHERE device_id = ? AND (revoked_at IS NULL OR revoked_at = '')
                """,
                (revoked_at, revoked_at, device_id),
            )
        return int(cursor.rowcount)

    def revoke_all_mobile_credentials_and_push_registrations(
        self,
        revoked_at: str,
    ) -> dict[str, int]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT id, payload, revoked_at FROM mobile_devices"
            ).fetchall()
            revoked_devices = 0
            for row in rows:
                payload = json.loads(row["payload"])
                if str(row["revoked_at"] or payload.get("revoked_at") or ""):
                    continue
                payload["revoked_at"] = revoked_at
                connection.execute(
                    "UPDATE mobile_devices SET payload = ?, revoked_at = ? WHERE id = ?",
                    (json.dumps(payload), revoked_at, row["id"]),
                )
                revoked_devices += 1
            cursor = connection.execute(
                """
                UPDATE mobile_push_registrations
                SET revoked_at = ?, updated_at = ?
                WHERE revoked_at IS NULL OR revoked_at = ''
                """,
                (revoked_at, revoked_at),
            )
        return {"devices": revoked_devices, "registrations": int(cursor.rowcount)}

    def reserve_mobile_notification_delivery(
        self,
        *,
        delivery_id: str,
        attempt_id: str,
        event_id: str,
        device_id: str,
        channel: str,
        registration_id: str,
        attempted_at: str,
        lease_seconds: int,
    ) -> str | None:
        attempted = datetime.fromisoformat(attempted_at.replace("Z", "+00:00"))
        if attempted.tzinfo is None:
            attempted = attempted.replace(tzinfo=timezone.utc)
        lease_expires_at = (
            attempted + timedelta(seconds=max(1, int(lease_seconds)))
        ).isoformat()
        with self._connect() as connection:
            connection.execute("PRAGMA busy_timeout = 500")
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, lease_expires_at
                FROM mobile_notification_deliveries
                WHERE event_id = ? AND device_id = ? AND channel = ?
                """,
                (event_id, device_id, channel),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO mobile_notification_deliveries (
                        id, event_id, device_id, channel, registration_id,
                        attempt_id, status, attempted_at, lease_expires_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                    """,
                    (
                        delivery_id,
                        event_id,
                        device_id,
                        channel,
                        registration_id,
                        attempt_id,
                        attempted_at,
                        lease_expires_at,
                        attempted_at,
                    ),
                )
                return attempt_id
            status = str(row["status"] or "")
            current_lease = str(row["lease_expires_at"] or "")
            reclaimable = status == "failed" or (
                status == "pending" and current_lease <= attempted_at
            )
            if not reclaimable:
                return None
            connection.execute(
                """
                UPDATE mobile_notification_deliveries
                SET registration_id = ?, attempt_id = ?, status = 'pending',
                    attempted_at = ?, lease_expires_at = ?, updated_at = ?
                WHERE event_id = ? AND device_id = ? AND channel = ?
                """,
                (
                    registration_id,
                    attempt_id,
                    attempted_at,
                    lease_expires_at,
                    attempted_at,
                    event_id,
                    device_id,
                    channel,
                ),
            )
            return attempt_id

    def finish_mobile_notification_delivery(
        self,
        *,
        attempt_id: str,
        status: str,
        updated_at: str,
    ) -> bool:
        if status not in {"sent", "failed"}:
            raise ValueError("Mobile notification delivery status is invalid")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE mobile_notification_deliveries
                SET status = ?, updated_at = ?
                WHERE attempt_id = ? AND status = 'pending'
                """,
                (status, updated_at, attempt_id),
            )
        return int(cursor.rowcount) == 1

    def acknowledge_mobile_alert(
        self,
        *,
        acknowledgement_id: str,
        device_id: str,
        event_id: str,
        acknowledged_at: str,
    ) -> dict[str, str]:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO mobile_alert_acknowledgements (
                    id, device_id, event_id, acknowledged_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    acknowledgement_id,
                    device_id,
                    event_id,
                    acknowledged_at,
                ),
            )
            row = connection.execute(
                """
                SELECT id, device_id, event_id, acknowledged_at
                FROM mobile_alert_acknowledgements
                WHERE device_id = ? AND event_id = ?
                """,
                (device_id, event_id),
            ).fetchone()
        if not row:
            raise RuntimeError("Mobile alert acknowledgement persistence failed")
        return {str(key): str(row[key]) for key in row.keys()}

    def load_mobile_alert_acknowledgements(
        self,
        *,
        device_id: str,
        limit: int = 500,
    ) -> list[dict[str, str]]:
        bounded_limit = max(1, min(1000, int(limit or 500)))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, device_id, event_id, acknowledged_at
                FROM mobile_alert_acknowledgements
                WHERE device_id = ?
                ORDER BY acknowledged_at DESC
                LIMIT ?
                """,
                (device_id, bounded_limit),
            ).fetchall()
        return [
            {str(key): str(row[key]) for key in row.keys()}
            for row in rows
        ]

    def create_mobile_destination_authorization(
        self,
        authorization: MobileDestinationAuthorization,
    ) -> MobileDestinationAuthorization:
        payload = authorization.to_dict()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO mobile_destination_authorizations (
                        id, payload, created_at, expires_at, used_at
                    )
                    VALUES (?, ?, ?, ?, NULL)
                    """,
                    (
                        authorization.id,
                        json.dumps(payload["payload"]),
                        payload["created_at"],
                        payload["expires_at"],
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Mobile destination authorization already exists") from exc
        return authorization

    def attach_mobile_destination_preview(
        self,
        authorization_id: str,
        preview: dict[str, Any],
    ) -> MobileDestinationAuthorization:
        """Attach a preview only while the authorization is still unused."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, payload, created_at, expires_at, used_at
                FROM mobile_destination_authorizations
                WHERE id = ?
                """,
                (authorization_id,),
            ).fetchone()
            if not row:
                raise LookupError("Mobile destination authorization not found")
            authorization = self._mobile_destination_authorization_from_row(row)
            now = datetime.now(timezone.utc)
            if authorization.used_at:
                raise ValueError("Destination authorization is already used")
            if authorization.expires_at <= now:
                raise ValueError("Destination authorization expired")
            authorization.payload["preview"] = dict(preview)
            cursor = connection.execute(
                """
                UPDATE mobile_destination_authorizations
                SET payload = ?
                WHERE id = ? AND used_at IS NULL AND expires_at > ?
                """,
                (
                    json.dumps(authorization.payload),
                    authorization_id,
                    now.isoformat(),
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "Destination authorization changed before preview could be attached"
                )
        return authorization

    def load_mobile_destination_authorization(
        self,
        authorization_id: str,
    ) -> MobileDestinationAuthorization | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, payload, created_at, expires_at, used_at
                FROM mobile_destination_authorizations
                WHERE id = ?
                """,
                (authorization_id,),
            ).fetchone()
        return self._mobile_destination_authorization_from_row(row) if row else None

    def load_mobile_destination_authorizations(
        self,
        *,
        device_id: str = "",
        limit: int = 100,
    ) -> list[MobileDestinationAuthorization]:
        bounded_limit = max(1, min(int(limit or 100), 500))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, payload, created_at, expires_at, used_at
                FROM mobile_destination_authorizations
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        authorizations = [
            self._mobile_destination_authorization_from_row(row) for row in rows
        ]
        if device_id:
            authorizations = [
                authorization
                for authorization in authorizations
                if str(authorization.payload.get("device_id") or "") == device_id
            ]
        return authorizations

    @staticmethod
    def _mobile_destination_authorization_from_row(
        row: sqlite3.Row,
    ) -> MobileDestinationAuthorization:
        return MobileDestinationAuthorization(
            id=str(row["id"]),
            payload=json.loads(str(row["payload"]) or "{}"),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            expires_at=datetime.fromisoformat(str(row["expires_at"])),
            used_at=(
                datetime.fromisoformat(str(row["used_at"]))
                if row["used_at"]
                else None
            ),
        )

    def reserve_mobile_action_receipt(
        self,
        receipt: MobileActionReceipt,
    ) -> tuple[MobileActionReceipt, bool]:
        """Atomically reserve an idempotency key before a financial side effect."""
        payload = receipt.to_dict()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT id, idempotency_key_hash, device_id, action_type, entity_id,
                       payload, status, created_at, updated_at, execution_audit_id
                FROM mobile_action_receipts
                WHERE idempotency_key_hash = ?
                """,
                (receipt.idempotency_key_hash,),
            ).fetchone()
            if existing:
                return self._mobile_action_receipt_from_row(existing), False
            connection.execute(
                """
                INSERT INTO mobile_action_receipts (
                    id, idempotency_key_hash, device_id, action_type, entity_id,
                    payload, status, created_at, updated_at, execution_audit_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.id,
                    receipt.idempotency_key_hash,
                    receipt.device_id,
                    receipt.action_type,
                    receipt.entity_id,
                    json.dumps(payload["payload"]),
                    receipt.status,
                    payload["created_at"],
                    payload["updated_at"],
                    receipt.execution_audit_id or None,
                ),
            )
        return receipt, True

    def reserve_mobile_treasury_action(
        self,
        receipt: MobileActionReceipt,
        *,
        authorization_id: str,
        preview_id: str,
        action: str,
        address: str,
        asset: str,
        amount: str,
        token_accounts: list[str],
        source_wallet_public_key: str,
        profit_sweep_policy: dict[str, Any],
    ) -> tuple[MobileActionReceipt, bool]:
        """Consume one exact preview while durably reserving its side effect."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._mobile_action_receipt_by_key(
                connection,
                receipt.idempotency_key_hash,
            )
            if existing:
                return existing, False
            row = connection.execute(
                """
                SELECT id, payload, created_at, expires_at, used_at
                FROM mobile_destination_authorizations
                WHERE id = ?
                """,
                (authorization_id,),
            ).fetchone()
            if not row:
                raise LookupError("Mobile destination authorization not found")
            authorization = self._mobile_destination_authorization_from_row(row)
            now = datetime.now(timezone.utc)
            if authorization.used_at:
                raise ValueError("Destination authorization is already used")
            if authorization.expires_at <= now:
                raise ValueError("Destination authorization expired")
            preview = authorization.payload.get("preview")
            if not isinstance(preview, dict) or not preview_id:
                raise ValueError("Treasury preview is missing")
            if str(preview.get("preview_id") or "") != preview_id:
                raise ValueError("Treasury preview does not match preview binding")
            try:
                preview_expires_at = datetime.fromisoformat(
                    str(preview.get("expires_at") or "")
                )
            except ValueError as exc:
                raise ValueError("Treasury preview expiry is invalid") from exc
            if preview_expires_at <= now:
                raise ValueError("Treasury preview expired")
            bindings = {
                "device": (
                    str(preview.get("device_id") or ""),
                    receipt.device_id,
                ),
                "action": (str(preview.get("action") or ""), action),
                "address": (str(preview.get("address") or ""), address),
                "asset": (str(preview.get("asset") or ""), asset),
                "amount": (str(preview.get("amount") or ""), amount),
                "authorization": (
                    str(preview.get("authorization_id") or ""),
                    authorization_id,
                ),
                "source wallet": (
                    str(preview.get("source_wallet_public_key") or ""),
                    source_wallet_public_key,
                ),
            }
            for label, (expected, actual) in bindings.items():
                if expected != actual:
                    raise ValueError(
                        f"Treasury preview {label} binding does not match"
                    )
            if list(preview.get("token_accounts") or []) != list(token_accounts):
                raise ValueError(
                    "Treasury preview token account binding does not match"
                )
            if str(authorization.payload.get("action") or "") != action:
                raise ValueError(
                    "Destination authorization action binding does not match"
                )
            if action == "profit_sweep":
                self._claim_mobile_profit_sweep_capacity(
                    connection,
                    receipt,
                    source_wallet_public_key=source_wallet_public_key,
                    policy=profit_sweep_policy,
                )
            authorization.payload["preview"] = {
                **preview,
                "used_at": now.isoformat(),
            }
            authorization.used_at = now
            payload = receipt.to_dict()
            cursor = connection.execute(
                """
                UPDATE mobile_destination_authorizations
                SET payload = ?, used_at = ?
                WHERE id = ? AND used_at IS NULL
                """,
                (
                    json.dumps(authorization.payload),
                    now.isoformat(),
                    authorization_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "Destination authorization changed before it could be consumed"
                )
            self._insert_mobile_action_receipt(connection, receipt)
        return receipt, True

    @classmethod
    def _claim_mobile_profit_sweep_capacity(
        cls,
        connection: sqlite3.Connection,
        receipt: MobileActionReceipt,
        *,
        source_wallet_public_key: str,
        policy: dict[str, Any],
    ) -> None:
        max_per_day = max(0, int(policy.get("max_per_day") or 0))
        cooldown_seconds = max(
            0,
            int(policy.get("cooldown_seconds") or 0),
        )
        rows = connection.execute(
            """
            SELECT id, idempotency_key_hash, device_id, action_type, entity_id,
                   payload, status, created_at, updated_at, execution_audit_id
            FROM mobile_action_receipts
            WHERE action_type = 'profit_sweep'
              AND status IN (
                  'pending', 'submitting', 'verifying', 'review_required',
                  'confirmed', 'reconciled'
              )
            ORDER BY created_at DESC
            """
        ).fetchall()
        now = receipt.created_at
        matching = [
            existing
            for existing in (
                cls._mobile_action_receipt_from_row(row) for row in rows
            )
            if str(
                existing.payload.get("source_wallet_public_key") or ""
            )
            == source_wallet_public_key
        ]
        recent = [
            existing
            for existing in matching
            if (now - existing.created_at).total_seconds() < 86400
        ]
        if max_per_day > 0 and len(recent) >= max_per_day:
            raise ValueError("daily sweep cap reached")
        if matching and cooldown_seconds > 0:
            last_claim = max(
                matching,
                key=lambda existing: existing.created_at,
            )
            age_seconds = (now - last_claim.created_at).total_seconds()
            if age_seconds < cooldown_seconds:
                raise ValueError("profit sweep cooldown active")
        receipt.payload["profit_sweep_policy_claim"] = {
            "action": "profit_sweep",
            "source_wallet_public_key": source_wallet_public_key,
            "claim_day": now.date().isoformat(),
            "max_per_day": max_per_day,
            "cooldown_seconds": cooldown_seconds,
            "claimed_at": now.isoformat(),
        }

    def load_pending_mobile_treasury_receipts(
        self,
        *,
        wallet_public_key: str,
        asset: str,
        exclude_action_id: str = "",
    ) -> list[MobileActionReceipt]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, idempotency_key_hash, device_id, action_type, entity_id,
                       payload, status, created_at, updated_at, execution_audit_id
                FROM mobile_action_receipts
                WHERE action_type IN (
                    'withdrawal', 'profit_sweep', 'rent_recovery'
                )
                  AND status IN (
                      'pending', 'verifying', 'review_required'
                  )
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            receipt
            for receipt in (
                self._mobile_action_receipt_from_row(row) for row in rows
            )
            if receipt.id != exclude_action_id
            and str(receipt.payload.get("source_wallet_public_key") or "")
            == wallet_public_key
            and str(receipt.payload.get("asset") or "") == asset
        ]

    def load_mobile_action_receipts(
        self,
        *,
        device_id: str = "",
        limit: int = 200,
    ) -> list[MobileActionReceipt]:
        bounded_limit = max(1, min(int(limit or 200), 1000))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, idempotency_key_hash, device_id, action_type, entity_id,
                       payload, status, created_at, updated_at, execution_audit_id
                FROM mobile_action_receipts
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        receipts = [self._mobile_action_receipt_from_row(row) for row in rows]
        if device_id:
            receipts = [
                receipt for receipt in receipts if receipt.device_id == device_id
            ]
        return receipts

    def apply_mobile_trade_rejection(
        self,
        receipt: MobileActionReceipt,
        *,
        expected_version: int,
        reason: str,
    ) -> tuple[MobileActionReceipt, bool]:
        """Atomically reject a version-bound intent and write its terminal receipt."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._mobile_action_receipt_by_key(
                connection,
                receipt.idempotency_key_hash,
            )
            if existing:
                return existing, False
            row = connection.execute(
                "SELECT payload FROM live_intents WHERE id = ?",
                (receipt.entity_id,),
            ).fetchone()
            if not row:
                raise LookupError("Mobile trade intent not found")
            intent = json.loads(str(row["payload"]))
            if int(intent.get("version") or 1) != int(expected_version):
                raise ValueError("Trade intent version conflict")
            if str(intent.get("status") or "") in {
                "submitted",
                "executed",
                "confirmed",
                "reconciled",
            }:
                raise ValueError("Submitted trade intent cannot be rejected")
            now = datetime.now(timezone.utc)
            intent["status"] = "cancelled"
            intent["reason"] = f"Rejected from paired mobile device: {reason}"
            intent["last_mobile_action_id"] = receipt.id
            intent["updated_at"] = now.isoformat()
            intent["version"] = int(intent.get("version") or 1) + 1
            receipt.status = "cancelled"
            receipt.updated_at = now
            receipt.payload["operator_message"] = "Trade intent rejected"
            connection.execute(
                "UPDATE live_intents SET payload = ? WHERE id = ?",
                (json.dumps(intent), receipt.entity_id),
            )
            self._insert_mobile_action_receipt(connection, receipt)
        return receipt, True

    def apply_mobile_position_exit_adjustment(
        self,
        receipt: MobileActionReceipt,
        *,
        expected_version: int,
        stop_pct: float,
        target_pct: float,
    ) -> tuple[MobileActionReceipt, bool]:
        """Atomically adjust a version-bound position and write its terminal receipt."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._mobile_action_receipt_by_key(
                connection,
                receipt.idempotency_key_hash,
            )
            if existing:
                return existing, False
            row = connection.execute(
                "SELECT payload FROM live_ledger_positions WHERE id = ?",
                (receipt.entity_id,),
            ).fetchone()
            if not row:
                raise LookupError("Mobile live position not found")
            position = json.loads(str(row["payload"]))
            if int(position.get("version") or 1) != int(expected_version):
                raise ValueError("Position version conflict")
            if (
                str(position.get("status") or "") != "open"
                or float(position.get("token_balance") or 0) <= 0
            ):
                raise ValueError(
                    "Only an open live position can change exit controls"
                )
            if not (0 < float(stop_pct) <= 100) or not (
                0 < float(target_pct) <= 100
            ):
                raise ValueError("Exit controls are outside backend bounds")
            now = datetime.now(timezone.utc)
            position["stop_pct"] = round(float(stop_pct), 4)
            position["target_pct"] = round(float(target_pct), 4)
            position["last_mobile_action_id"] = receipt.id
            position["version"] = int(position.get("version") or 1) + 1
            position["updated_at"] = now.isoformat()
            receipt.status = "confirmed"
            receipt.updated_at = now
            receipt.payload["operator_message"] = "Exit controls updated"
            connection.execute(
                "UPDATE live_ledger_positions SET payload = ? WHERE id = ?",
                (json.dumps(position), receipt.entity_id),
            )
            self._insert_mobile_action_receipt(connection, receipt)
        return receipt, True

    def reconcile_mobile_local_action(
        self,
        action_id: str,
    ) -> MobileActionReceipt:
        """Apply or terminally classify a durable local action exactly once."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, idempotency_key_hash, device_id, action_type, entity_id,
                       payload, status, created_at, updated_at, execution_audit_id
                FROM mobile_action_receipts
                WHERE id = ?
                """,
                (action_id,),
            ).fetchone()
            if not row:
                raise LookupError(f"Mobile action receipt not found: {action_id}")
            receipt = self._mobile_action_receipt_from_row(row)
            if receipt.status != "pending":
                return receipt
            now = datetime.now(timezone.utc)
            expected_version = int(
                receipt.payload.get("expected_version") or 0
            )
            if receipt.action_type == "trade_reject":
                entity_row = connection.execute(
                    "SELECT payload FROM live_intents WHERE id = ?",
                    (receipt.entity_id,),
                ).fetchone()
                entity = (
                    json.loads(str(entity_row["payload"]))
                    if entity_row
                    else None
                )
                reason = str(receipt.payload.get("reason") or "")
                expected_reason = (
                    f"Rejected from paired mobile device: {reason}"
                )
                already_applied = bool(
                    entity
                    and (
                        str(entity.get("last_mobile_action_id") or "")
                        == receipt.id
                        or (
                            str(entity.get("status") or "") == "cancelled"
                            and str(entity.get("reason") or "")
                            == expected_reason
                            and int(entity.get("version") or 0)
                            >= expected_version + 1
                        )
                    )
                )
                if already_applied:
                    receipt.status = "cancelled"
                    receipt.payload["operator_message"] = "Trade intent rejected"
                elif (
                    entity
                    and int(entity.get("version") or 1) == expected_version
                    and str(entity.get("status") or "")
                    not in {
                        "submitted",
                        "executed",
                        "confirmed",
                        "reconciled",
                    }
                ):
                    entity["status"] = "cancelled"
                    entity["reason"] = expected_reason
                    entity["last_mobile_action_id"] = receipt.id
                    entity["version"] = expected_version + 1
                    entity["updated_at"] = now.isoformat()
                    connection.execute(
                        "UPDATE live_intents SET payload = ? WHERE id = ?",
                        (json.dumps(entity), receipt.entity_id),
                    )
                    receipt.status = "cancelled"
                    receipt.payload["operator_message"] = "Trade intent rejected"
                else:
                    receipt.status = "review_required"
                    receipt.payload["operator_message"] = (
                        "Trade intent changed before rejection recovery; review required"
                    )
            elif receipt.action_type == "position_adjust_exit":
                entity_row = connection.execute(
                    "SELECT payload FROM live_ledger_positions WHERE id = ?",
                    (receipt.entity_id,),
                ).fetchone()
                entity = (
                    json.loads(str(entity_row["payload"]))
                    if entity_row
                    else None
                )
                stop_pct = float(receipt.payload.get("stop_pct") or 0)
                target_pct = float(receipt.payload.get("target_pct") or 0)
                already_applied = bool(
                    entity
                    and (
                        str(entity.get("last_mobile_action_id") or "")
                        == receipt.id
                        or (
                            int(entity.get("version") or 0)
                            >= expected_version + 1
                            and abs(
                                float(entity.get("stop_pct") or 0)
                                - stop_pct
                            )
                            <= 1e-12
                            and abs(
                                float(entity.get("target_pct") or 0)
                                - target_pct
                            )
                            <= 1e-12
                        )
                    )
                )
                if already_applied:
                    receipt.status = "confirmed"
                    receipt.payload["operator_message"] = "Exit controls updated"
                elif (
                    entity
                    and int(entity.get("version") or 1) == expected_version
                    and str(entity.get("status") or "") == "open"
                    and float(entity.get("token_balance") or 0) > 0
                    and 0 < stop_pct <= 100
                    and 0 < target_pct <= 100
                ):
                    entity["stop_pct"] = round(stop_pct, 4)
                    entity["target_pct"] = round(target_pct, 4)
                    entity["last_mobile_action_id"] = receipt.id
                    entity["version"] = expected_version + 1
                    entity["updated_at"] = now.isoformat()
                    connection.execute(
                        """
                        UPDATE live_ledger_positions
                        SET payload = ?
                        WHERE id = ?
                        """,
                        (json.dumps(entity), receipt.entity_id),
                    )
                    receipt.status = "confirmed"
                    receipt.payload["operator_message"] = "Exit controls updated"
                else:
                    receipt.status = "review_required"
                    receipt.payload["operator_message"] = (
                        "Position changed before exit recovery; review required"
                    )
            else:
                receipt.status = "review_required"
                receipt.payload["operator_message"] = (
                    "Unknown local action requires review"
                )
            receipt.updated_at = now
            self._update_mobile_action_receipt(connection, receipt)
        return receipt

    @classmethod
    def _mobile_action_receipt_by_key(
        cls,
        connection: sqlite3.Connection,
        idempotency_key_hash: str,
    ) -> MobileActionReceipt | None:
        row = connection.execute(
            """
            SELECT id, idempotency_key_hash, device_id, action_type, entity_id,
                   payload, status, created_at, updated_at, execution_audit_id
            FROM mobile_action_receipts
            WHERE idempotency_key_hash = ?
            """,
            (idempotency_key_hash,),
        ).fetchone()
        return cls._mobile_action_receipt_from_row(row) if row else None

    @staticmethod
    def _insert_mobile_action_receipt(
        connection: sqlite3.Connection,
        receipt: MobileActionReceipt,
    ) -> None:
        payload = receipt.to_dict()
        connection.execute(
            """
            INSERT INTO mobile_action_receipts (
                id, idempotency_key_hash, device_id, action_type, entity_id,
                payload, status, created_at, updated_at, execution_audit_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt.id,
                receipt.idempotency_key_hash,
                receipt.device_id,
                receipt.action_type,
                receipt.entity_id,
                json.dumps(payload["payload"]),
                receipt.status,
                payload["created_at"],
                payload["updated_at"],
                receipt.execution_audit_id or None,
            ),
        )

    @staticmethod
    def _update_mobile_action_receipt(
        connection: sqlite3.Connection,
        receipt: MobileActionReceipt,
    ) -> None:
        payload = receipt.to_dict()
        connection.execute(
            """
            UPDATE mobile_action_receipts
            SET payload = ?, status = ?, updated_at = ?,
                execution_audit_id = ?
            WHERE id = ?
            """,
            (
                json.dumps(payload["payload"]),
                receipt.status,
                payload["updated_at"],
                receipt.execution_audit_id or None,
                receipt.id,
            ),
        )

    def reserve_mobile_execution_action(
        self,
        receipt: MobileActionReceipt,
        *,
        audit_id: str,
        intent_id: str,
        expected_intent_version: int,
        guarded_authorization: dict[str, Any],
        position_binding: dict[str, Any] | None = None,
    ) -> tuple[MobileActionReceipt, bool]:
        """Atomically bind one guarded action to one prepared audit."""
        receipt.execution_audit_id = audit_id
        payload = receipt.to_dict()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT id, idempotency_key_hash, device_id, action_type, entity_id,
                       payload, status, created_at, updated_at, execution_audit_id
                FROM mobile_action_receipts
                WHERE idempotency_key_hash = ?
                """,
                (receipt.idempotency_key_hash,),
            ).fetchone()
            if existing:
                return self._mobile_action_receipt_from_row(existing), False
            claimed = connection.execute(
                """
                SELECT id
                FROM mobile_action_receipts
                WHERE execution_audit_id = ?
                """,
                (audit_id,),
            ).fetchone()
            if claimed:
                raise ValueError("Prepared execution audit is already claimed")

            audit_row = connection.execute(
                "SELECT payload FROM live_execution_audits WHERE id = ?",
                (audit_id,),
            ).fetchone()
            intent_row = connection.execute(
                "SELECT payload FROM live_intents WHERE id = ?",
                (intent_id,),
            ).fetchone()
            if not audit_row or not intent_row:
                raise LookupError("Prepared execution audit or intent not found")
            audit_payload = json.loads(str(audit_row["payload"]))
            intent_payload = json.loads(str(intent_row["payload"]))
            if (
                str(audit_payload.get("intent_id") or "") != intent_id
                or str(audit_payload.get("status") or "") != "simulated"
                or str(audit_payload.get("final_status") or "") != "simulated"
                or str(audit_payload.get("guarded_action_id") or "")
            ):
                raise ValueError(
                    "Prepared execution audit is not exactly simulated or is already claimed"
                )
            if (
                str(intent_payload.get("status") or "") != "simulated"
                or int(intent_payload.get("version") or 1)
                != int(expected_intent_version)
            ):
                raise ValueError(
                    "Prepared intent is not exactly simulated or has a version conflict"
                )

            if position_binding:
                position_id = str(position_binding.get("position_id") or "")
                position_row = connection.execute(
                    "SELECT payload FROM live_ledger_positions WHERE id = ?",
                    (position_id,),
                ).fetchone()
                if not position_row:
                    raise LookupError("Mobile live position not found")
                position_payload = json.loads(str(position_row["payload"]))
                expected_position_version = int(
                    position_binding.get("position_version") or 0
                )
                expected_balance = float(
                    position_binding.get("token_balance") or 0
                )
                if (
                    int(position_payload.get("version") or 1)
                    != expected_position_version
                    or str(position_payload.get("status") or "") != "open"
                    or float(position_payload.get("token_balance") or 0) <= 0
                    or str(position_payload.get("reconciliation_status") or "")
                    == "needs_review"
                ):
                    raise ValueError(
                        "position changed before the guarded close claim"
                    )
                if abs(
                    float(position_payload.get("token_balance") or 0)
                    - expected_balance
                ) > 1e-12:
                    raise ValueError(
                        "position balance changed before the guarded close claim"
                    )
                if (
                    audit_payload.get("action") != "sell"
                    or str(audit_payload.get("amount") or "") != "100%"
                    or intent_payload.get("action") != "sell"
                    or str(intent_payload.get("amount") or "") != "100%"
                    or not bool(intent_payload.get("generated_from_position"))
                    or str(intent_payload.get("generated_position_id") or "")
                    != position_id
                    or int(
                        intent_payload.get("generated_position_version") or 0
                    )
                    != expected_position_version
                    or abs(
                        float(
                            intent_payload.get(
                                "generated_position_token_balance"
                            )
                            or 0
                        )
                        - expected_balance
                    )
                    > 1e-12
                    or str(intent_payload.get("mint") or "")
                    != str(position_payload.get("mint") or "")
                    or str(intent_payload.get("wallet_public_key") or "")
                    != str(position_payload.get("wallet_public_key") or "")
                ):
                    raise ValueError(
                        "Prepared close is not the exact canonical full-position intent"
                    )

            now = datetime.now(timezone.utc).isoformat()
            authorization = dict(guarded_authorization)
            audit_payload["guarded_action_id"] = receipt.id
            audit_payload["guarded_authorization"] = authorization
            audit_payload["dispatch_started_at"] = None
            audit_payload["status"] = "submitting"
            audit_payload["final_status"] = "submitting"
            audit_payload["updated_at"] = now
            request = audit_payload.get("request")
            if not isinstance(request, dict):
                request = {}
            request["mobile_authorization"] = authorization
            audit_payload["request"] = request
            intent_payload["last_mobile_action_id"] = receipt.id
            intent_payload["status"] = "submitting"
            intent_payload["version"] = int(
                intent_payload.get("version") or 1
            ) + 1
            intent_payload["updated_at"] = now
            connection.execute(
                "UPDATE live_execution_audits SET payload = ? WHERE id = ?",
                (json.dumps(audit_payload), audit_id),
            )
            connection.execute(
                "UPDATE live_intents SET payload = ? WHERE id = ?",
                (json.dumps(intent_payload), intent_id),
            )
            try:
                connection.execute(
                    """
                    INSERT INTO mobile_action_receipts (
                        id, idempotency_key_hash, device_id, action_type,
                        entity_id, payload, status, created_at, updated_at,
                        execution_audit_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt.id,
                        receipt.idempotency_key_hash,
                        receipt.device_id,
                        receipt.action_type,
                        receipt.entity_id,
                        json.dumps(payload["payload"]),
                        receipt.status,
                        payload["created_at"],
                        payload["updated_at"],
                        audit_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "Prepared execution audit is already claimed"
                ) from exc
        return receipt, True

    def begin_mobile_execution_dispatch(
        self,
        *,
        audit_id: str,
        action_id: str,
    ) -> LiveExecutionAudit | None:
        """Durably mark the only permitted dispatch before invoking a signer."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM live_execution_audits WHERE id = ?",
                (audit_id,),
            ).fetchone()
            if not row:
                raise LookupError(f"Live execution audit not found: {audit_id}")
            payload = json.loads(str(row["payload"]))
            if str(payload.get("guarded_action_id") or "") != action_id:
                raise ValueError(
                    "Guarded execution action does not own this audit"
                )
            if payload.get("dispatch_started_at"):
                return None
            if (
                str(payload.get("status") or "") != "submitting"
                or str(payload.get("final_status") or "") != "submitting"
            ):
                raise ValueError(
                    "Guarded execution audit is not in claimed submitting state"
                )
            now = datetime.now(timezone.utc)
            payload["dispatch_started_at"] = now.isoformat()
            payload["updated_at"] = now.isoformat()
            connection.execute(
                "UPDATE live_execution_audits SET payload = ? WHERE id = ?",
                (json.dumps(payload), audit_id),
            )
        return self._live_execution_audit_from_payload(payload)

    def save_mobile_action_receipt(
        self,
        receipt: MobileActionReceipt,
    ) -> MobileActionReceipt:
        payload = receipt.to_dict()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE mobile_action_receipts
                SET payload = ?, status = ?, updated_at = ?,
                    execution_audit_id = COALESCE(execution_audit_id, ?)
                WHERE id = ?
                  AND (
                      ? IS NULL
                      OR execution_audit_id IS NULL
                      OR execution_audit_id = ?
                  )
                """,
                (
                    json.dumps(payload["payload"]),
                    receipt.status,
                    payload["updated_at"],
                    receipt.execution_audit_id or None,
                    receipt.id,
                    receipt.execution_audit_id or None,
                    receipt.execution_audit_id or None,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError(
                    "Mobile action receipt was not found or its execution "
                    f"audit binding changed: {receipt.id}"
                )
        return receipt

    def bind_mobile_treasury_execution_audit(
        self,
        receipt_id: str,
        audit: LiveExecutionAudit,
    ) -> MobileActionReceipt:
        if (
            str(audit.request.get("mobile_action_id") or "") != receipt_id
            or audit.action not in {"profit_sweep", "rent_recovery"}
        ):
            raise ValueError("Treasury audit does not match its receipt")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, idempotency_key_hash, device_id, action_type, entity_id,
                       payload, status, created_at, updated_at, execution_audit_id
                FROM mobile_action_receipts
                WHERE id = ?
                """,
                (receipt_id,),
            ).fetchone()
            if not row:
                raise LookupError(
                    f"Mobile action receipt not found: {receipt_id}"
                )
            receipt = self._mobile_action_receipt_from_row(row)
            if (
                receipt.action_type != audit.action
                or str(
                    receipt.payload.get("source_wallet_public_key") or ""
                )
                != audit.wallet_public_key
            ):
                raise ValueError(
                    "Treasury audit action or source wallet binding does not match"
                )
            if (
                receipt.execution_audit_id
                and receipt.execution_audit_id != audit.id
            ):
                raise ValueError(
                    "Treasury receipt already has another execution audit"
                )
            claimed = connection.execute(
                """
                SELECT id
                FROM mobile_action_receipts
                WHERE execution_audit_id = ? AND id != ?
                """,
                (audit.id, receipt_id),
            ).fetchone()
            if claimed:
                raise ValueError(
                    "Treasury execution audit is already bound to another receipt"
                )
            connection.execute(
                """
                INSERT INTO live_execution_audits (id, payload, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    audit.id,
                    json.dumps(audit.to_dict()),
                    audit.created_at.isoformat(),
                ),
            )
            receipt.execution_audit_id = audit.id
            receipt.updated_at = audit.updated_at
            self._update_mobile_action_receipt(connection, receipt)
        return receipt

    def finalize_mobile_treasury_reconciliation(
        self,
        receipt: MobileActionReceipt,
        *,
        terminal_status: str,
        confirmation: dict[str, Any],
    ) -> MobileActionReceipt:
        if terminal_status not in {"confirmed", "failed"}:
            raise ValueError("Treasury audit terminal status is invalid")
        if not receipt.execution_audit_id:
            raise ValueError("Treasury receipt is missing its execution audit")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            receipt_row = connection.execute(
                """
                SELECT id, execution_audit_id
                FROM mobile_action_receipts
                WHERE id = ?
                """,
                (receipt.id,),
            ).fetchone()
            if not receipt_row:
                raise LookupError(
                    f"Mobile action receipt not found: {receipt.id}"
                )
            if str(receipt_row["execution_audit_id"] or "") != (
                receipt.execution_audit_id
            ):
                raise ValueError(
                    "Treasury receipt execution audit binding changed"
                )
            audit_row = connection.execute(
                "SELECT payload FROM live_execution_audits WHERE id = ?",
                (receipt.execution_audit_id,),
            ).fetchone()
            if not audit_row:
                raise LookupError(
                    "Treasury execution audit binding was not found"
                )
            audit = self._live_execution_audit_from_payload(
                json.loads(str(audit_row["payload"]))
            )
            if (
                audit.action != receipt.action_type
                or str(audit.request.get("mobile_action_id") or "")
                != receipt.id
            ):
                raise ValueError(
                    "Treasury execution audit binding does not match receipt"
                )
            receipt_signature = str(
                receipt.payload.get("transaction_signature") or ""
            )
            if (
                not receipt_signature
                or audit.transaction_signature != receipt_signature
            ):
                raise ValueError(
                    "Treasury execution audit signature does not match receipt"
                )
            now = receipt.updated_at
            audit.status = terminal_status
            audit.final_status = terminal_status
            audit.confirmation = dict(confirmation)
            audit.confirmation_status = str(
                confirmation.get("confirmation_status")
                or confirmation.get("status")
                or terminal_status
            )
            audit.confirmation_checked_at = now
            audit.reconciliation_status = "matched"
            audit.reconciliation = {
                "source": "mobile_treasury_receipt",
                "mobile_action_id": receipt.id,
                "receipt_status": receipt.status,
                "transaction_signature": receipt_signature,
            }
            audit.updated_at = now
            audit.recommended_action = (
                "Treasury signature confirmed and matched to the mobile receipt."
                if terminal_status == "confirmed"
                else "Treasury failure confirmed on chain; review before retrying."
            )
            if terminal_status == "failed":
                error = str(confirmation.get("err") or "on-chain failure")
                if error not in audit.errors:
                    audit.errors.append(error)
            connection.execute(
                "UPDATE live_execution_audits SET payload = ? WHERE id = ?",
                (json.dumps(audit.to_dict()), audit.id),
            )
            self._update_mobile_action_receipt(connection, receipt)
        return receipt

    def load_mobile_action_receipt(
        self,
        action_id: str,
    ) -> MobileActionReceipt | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, idempotency_key_hash, device_id, action_type, entity_id,
                       payload, status, created_at, updated_at, execution_audit_id
                FROM mobile_action_receipts
                WHERE id = ?
                """,
                (action_id,),
            ).fetchone()
        return self._mobile_action_receipt_from_row(row) if row else None

    def load_mobile_action_receipt_by_key_hash(
        self,
        idempotency_key_hash: str,
    ) -> MobileActionReceipt | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, idempotency_key_hash, device_id, action_type, entity_id,
                       payload, status, created_at, updated_at, execution_audit_id
                FROM mobile_action_receipts
                WHERE idempotency_key_hash = ?
                """,
                (idempotency_key_hash,),
            ).fetchone()
        return self._mobile_action_receipt_from_row(row) if row else None

    @staticmethod
    def _mobile_action_receipt_from_row(row: sqlite3.Row) -> MobileActionReceipt:
        return MobileActionReceipt(
            id=str(row["id"]),
            idempotency_key_hash=str(row["idempotency_key_hash"]),
            device_id=str(row["device_id"]),
            action_type=str(row["action_type"]),
            entity_id=str(row["entity_id"]),
            payload=json.loads(str(row["payload"]) or "{}"),
            status=str(row["status"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
            execution_audit_id=str(row["execution_audit_id"] or ""),
        )

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
            "mobile_action_receipts": self.count_mobile_action_receipts(),
            "mobile_destination_authorizations": (
                self.count_mobile_destination_authorizations()
            ),
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

    def load_settings_version(self, version_id: str) -> SettingsVersion | None:
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT payload FROM settings_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        return self._settings_version_from_payload(json.loads(row["payload"])) if row else None

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

    def count_mobile_action_receipts(self) -> int:
        return self._count_table_if_exists("mobile_action_receipts")

    def count_mobile_destination_authorizations(self) -> int:
        return self._count_table_if_exists(
            "mobile_destination_authorizations"
        )

    def count_mobile_push_registrations(self) -> int:
        return self._count_table("mobile_push_registrations")

    def count_mobile_notification_deliveries(self) -> int:
        return self._count_table("mobile_notification_deliveries")

    def _count_table(self, table: str) -> int:
        with self._connect() as connection:
            row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"] if row else 0)

    def _count_table_if_exists(self, table: str) -> int:
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            if not exists:
                return 0
            row = connection.execute(
                f"SELECT COUNT(*) AS count FROM {table}"
            ).fetchone()
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

    def load_live_execution_audits(
        self,
        limit: int | None = 100,
    ) -> list[LiveExecutionAudit]:
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

    def _load_payloads(
        self,
        table: str,
        limit: int | None,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if limit is None:
                rows = connection.execute(
                    f"SELECT payload FROM {table} ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    f"SELECT payload FROM {table} ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
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
        if trade.closed_at and trade.pnl_sol is not None:
            try:
                self.enqueue_trade_review(self._trade_revision_from_trade(trade))
            except Exception:
                # The authoritative trade commit must never depend on low-priority grading.
                pass

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

    def _trade_revision_from_trade(self, trade: TradeRecord) -> TradeRevision:
        completed_at = trade.closed_at or datetime.now(timezone.utc)
        decision_at = trade.opened_at or completed_at
        serialized = json.dumps(trade.to_dict(), sort_keys=True, separators=(",", ":"))
        revision_hash = uuid.uuid5(uuid.NAMESPACE_URL, serialized).hex
        mode = trade.mode if trade.mode in {"paper", "shadow", "manual_live", "autonomous_live"} else "paper"
        return TradeRevision(
            revision_id=f"{trade.id}:{revision_hash}",
            trade_id=trade.id,
            mode=mode,
            strategy_version=trade.settings_version_id or trade.strategy_profile or "unversioned",
            rules_version="trade-grader-v1",
            data_schema_version=self.SCHEMA_VERSION,
            completed_at=completed_at,
            decision_at=decision_at,
            evidence_ids=tuple(
                value for value in (f"trade:{trade.id}", f"settings:{trade.settings_version_id}" if trade.settings_version_id else "") if value
            ),
            ex_ante_facts={
                "signal_score": None,
                "entry_compliant": trade.entry_price is not None and trade.amount_sol is not None,
                "risk_clear": trade.lifecycle_status == "closed",
                "source_confidence": trade.source_price_confidence,
                "latency_ms": None,
                "slippage_pct": trade.slippage_paid_pct,
                "entry_reason": trade.entry_reason,
            },
            ex_post_facts={
                "pnl_sol": trade.pnl_sol,
                "exit_compliant": bool(trade.exit_reason),
                "exit_reason": trade.exit_reason,
                "hold_duration_seconds": trade.hold_duration_seconds,
                "total_cost_sol": sum(
                    float(value or 0.0)
                    for value in (
                        trade.entry_fee_sol,
                        trade.exit_fee_sol,
                        trade.entry_provider_fee_sol,
                        trade.exit_provider_fee_sol,
                        trade.entry_network_fee_sol,
                        trade.exit_network_fee_sol,
                        trade.entry_priority_fee_sol,
                        trade.exit_priority_fee_sol,
                        trade.entry_slippage_cost_sol,
                        trade.entry_price_impact_cost_sol,
                    )
                ),
            },
        )

    def _price_observation_from_payload(self, payload: dict[str, Any]) -> PriceObservation:
        payload["observed_at"] = datetime.fromisoformat(payload["observed_at"])
        allowed = set(PriceObservation.__dataclass_fields__.keys())
        return PriceObservation(**{key: value for key, value in payload.items() if key in allowed})

    def _accepted_market_observation_from_payload(self, payload: dict[str, Any]) -> AcceptedMarketObservation:
        for field_name in ("created_at", "observed_at", "received_at"):
            payload[field_name] = datetime.fromisoformat(payload[field_name])
        allowed = set(AcceptedMarketObservation.__dataclass_fields__.keys())
        return AcceptedMarketObservation(**{key: value for key, value in payload.items() if key in allowed})

    def _shadow_comparison_from_payload(self, payload: dict[str, Any]) -> ShadowComparison:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["completed_at"] = datetime.fromisoformat(payload["completed_at"])
        payload["source_evidence_ids"] = tuple(payload.get("source_evidence_ids") or ())
        payload["costs"] = ShadowCostBreakdown(**dict(payload.get("costs") or {}))
        allowed = set(ShadowComparison.__dataclass_fields__.keys())
        return ShadowComparison(**{key: value for key, value in payload.items() if key in allowed})

    def _sentinel_verdict_from_payload(self, payload: dict[str, Any]) -> SentinelVerdict:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["expires_at"] = datetime.fromisoformat(payload["expires_at"])
        for field_name in ("blockers", "warnings", "reasons"):
            payload[field_name] = tuple(payload.get(field_name) or ())
        allowed = set(SentinelVerdict.__dataclass_fields__.keys())
        return SentinelVerdict(**{key: value for key, value in payload.items() if key in allowed})

    def _trade_revision_from_payload(self, payload: dict[str, Any]) -> TradeRevision:
        payload["completed_at"] = datetime.fromisoformat(payload["completed_at"])
        payload["decision_at"] = datetime.fromisoformat(payload["decision_at"])
        payload["evidence_ids"] = tuple(payload.get("evidence_ids") or ())
        allowed = set(TradeRevision.__dataclass_fields__.keys())
        return TradeRevision(**{key: value for key, value in payload.items() if key in allowed})

    def _trade_review_job_from_row(self, row: sqlite3.Row) -> TradeReviewJob:
        return TradeReviewJob(
            job_id=str(row["job_id"]),
            status=str(row["status"]),
            attempts=int(row["attempts"]),
            claim_id=str(row["claim_id"]),
            lease_owner=str(row["lease_owner"]),
            lease_until=datetime.fromisoformat(row["lease_until"]) if row["lease_until"] else None,
            revision=self._trade_revision_from_payload(json.loads(row["revision_payload"])),
            last_error=str(row["last_error"]),
        )

    def _trade_grade_from_payload(self, payload: dict[str, Any]) -> TradeGrade:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["evidence_ids"] = tuple(payload.get("evidence_ids") or ())
        payload["reasons"] = tuple(payload.get("reasons") or ())
        allowed = set(TradeGrade.__dataclass_fields__.keys())
        return TradeGrade(**{key: value for key, value in payload.items() if key in allowed})

    def _trade_grade_correction_from_payload(self, payload: dict[str, Any]) -> TradeGradeCorrection:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        allowed = set(TradeGradeCorrection.__dataclass_fields__.keys())
        return TradeGradeCorrection(**{key: value for key, value in payload.items() if key in allowed})

    def _strategy_candidate_from_payload(self, payload: dict[str, Any]) -> StrategyCandidate:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["evidence_ids"] = tuple(payload.get("evidence_ids") or ())
        allowed = set(StrategyCandidate.__dataclass_fields__.keys())
        return StrategyCandidate(**{key: value for key, value in payload.items() if key in allowed})

    def _candidate_validation_from_payload(self, payload: dict[str, Any]) -> CandidateValidation:
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["blockers"] = tuple(payload.get("blockers") or ())
        allowed = set(CandidateValidation.__dataclass_fields__.keys())
        return CandidateValidation(**{key: value for key, value in payload.items() if key in allowed})

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
        payload["dispatch_started_at"] = datetime.fromisoformat(payload["dispatch_started_at"]) if payload.get("dispatch_started_at") else None
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
