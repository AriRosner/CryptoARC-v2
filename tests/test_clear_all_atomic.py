import json
import sqlite3
import unittest
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.models import BacktestRun, LiveExecutionAudit, TokenSignal, TradeEvent, utc_now
from app.core.state import BotState


class ClearAllAtomicTests(unittest.TestCase):
    CLEARED_TABLES = (
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
    PRESERVED_TABLES = (
        "settings",
        "backup_restore_history",
        "mobile_pairing_requests",
        "mobile_devices",
    )

    def make_seeded_state(self, directory: str) -> BotState:
        state = BotState(database_path=str(Path(directory) / "test.db"))
        state.settings.kill_switch_enabled = True
        state.settings.live_active_backend_armed = False
        state.settings.score_threshold = 77
        state.storage.save_settings(state.settings)

        now = utc_now()
        token = TokenSignal(
            id="tok_atomic",
            symbol="ARC",
            name="Atomic Clear",
            mint="mint_atomic",
            creator="creator_atomic",
            detected_at=now,
        )
        event = TradeEvent(
            id="evt_atomic",
            created_at=now,
            level="info",
            message="seed event",
        )
        run = BacktestRun(
            id="bt_atomic",
            created_at=now,
            profile="balanced",
            risk_tolerance="medium",
            tokens_replayed=1,
            paper_buys=1,
            skips=0,
            wins=1,
            losses=0,
            win_rate_pct=100,
            estimated_pnl_sol=0.01,
            max_drawdown_sol=0.0,
            profit_factor=1.0,
        )
        state.storage.save_token(token)
        state.storage.save_event(event)
        state.storage.save_backtest_run(run)
        state.tokens.appendleft(token)
        state.events.appendleft(event)
        state.backtest_runs.appendleft(run)
        state.creator_history = Counter({token.creator: 1})
        state.stats.total_trades = 9
        state.stats.successful_trades = 7
        state.stats.total_pnl_sol = 1.25

        timestamp = now.isoformat()
        payload = json.dumps({"id": "seed", "created_at": timestamp})
        with sqlite3.connect(state.storage.path) as connection:
            connection.execute(
                "INSERT INTO source_events (id, source, payload, received_at) VALUES (?, ?, ?, ?)",
                ("src_atomic", "test", payload, timestamp),
            )
            connection.execute(
                "INSERT INTO trades (id, token_id, payload, opened_at, closed_at) VALUES (?, ?, ?, ?, ?)",
                ("trade_atomic", token.id, payload, timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO price_observations (id, mint, payload, observed_at) VALUES (?, ?, ?, ?)",
                ("price_atomic", token.mint, payload, timestamp),
            )
            connection.execute(
                "INSERT INTO strategy_decisions (id, token_id, payload, created_at) VALUES (?, ?, ?, ?)",
                ("decision_atomic", token.id, payload, timestamp),
            )
            connection.execute(
                "INSERT INTO trade_sessions (id, token_id, mint, payload, opened_at, closed_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("session_atomic", token.id, token.mint, payload, timestamp, timestamp),
            )
            for table in (
                "experiment_runs",
                "trade_labels",
                "strategy_presets",
                "live_execution_requests",
                "live_sessions",
                "live_intents",
                "live_ledger_positions",
            ):
                connection.execute(
                    f"INSERT INTO {table} (id, payload, created_at) VALUES (?, ?, ?)",
                    (f"{table}_atomic", payload, timestamp),
                )
            connection.execute(
                "INSERT INTO source_soak_history (id, payload, created_at, status, ready) VALUES (?, ?, ?, ?, ?)",
                ("soak_atomic", payload, timestamp, "ready", 1),
            )
            connection.execute(
                "INSERT INTO backup_restore_history (id, payload, created_at) VALUES (?, ?, ?)",
                ("backup_atomic", payload, timestamp),
            )
            connection.execute(
                "INSERT INTO mobile_pairing_requests (id, payload, created_at, expires_at, claimed_at) VALUES (?, ?, ?, ?, ?)",
                ("pair_atomic", payload, timestamp, timestamp, None),
            )
            connection.execute(
                "INSERT INTO mobile_devices (id, payload, created_at, last_seen_at, revoked_at) VALUES (?, ?, ?, ?, ?)",
                ("device_atomic", payload, timestamp, timestamp, None),
            )

        state.storage.save_live_execution_audit(
            LiveExecutionAudit(
                id="audit_atomic",
                created_at=now,
                updated_at=now,
                action="sell",
                mint=token.mint,
                amount="1",
                status="reconciled",
                signer_mode="browser_wallet",
                wallet_public_key="wallet_atomic",
                reconciliation_status="matched",
            )
        )
        return state

    def table_snapshot(self, state: BotState) -> dict[str, list[tuple[object, ...]]]:
        tables = self.CLEARED_TABLES + self.PRESERVED_TABLES
        with sqlite3.connect(state.storage.path) as connection:
            return {
                table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()]
                for table in tables
            }

    def test_clear_all_rolls_back_persistent_and_in_memory_state_on_mid_transaction_failure(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            state = self.make_seeded_state(directory)
            persistent_before = self.table_snapshot(state)
            memory_before = {
                "tokens": [token.id for token in state.tokens],
                "events": [event.id for event in state.events],
                "backtests": [run.id for run in state.backtest_runs],
                "creators": deepcopy(state.creator_history),
                "settings": asdict(state.settings),
                "stats": state.stats.to_dict(),
                "settings_version_id": state.current_settings_version_id,
            }
            with sqlite3.connect(state.storage.path) as connection:
                connection.execute(
                    """
                    CREATE TRIGGER fail_clear_all
                    BEFORE DELETE ON strategy_decisions
                    BEGIN
                        SELECT RAISE(ABORT, 'forced clear-all failure');
                    END
                    """
                )

            with self.assertRaisesRegex(sqlite3.IntegrityError, "forced clear-all failure"):
                state.clear_data("all")

            self.assertEqual(self.table_snapshot(state), persistent_before)
            self.assertEqual([token.id for token in state.tokens], memory_before["tokens"])
            self.assertEqual([event.id for event in state.events], memory_before["events"])
            self.assertEqual([run.id for run in state.backtest_runs], memory_before["backtests"])
            self.assertEqual(state.creator_history, memory_before["creators"])
            self.assertEqual(asdict(state.settings), memory_before["settings"])
            self.assertEqual(state.stats.to_dict(), memory_before["stats"])
            self.assertEqual(state.current_settings_version_id, memory_before["settings_version_id"])

    def test_clear_all_clears_exact_tables_and_preserves_safe_settings_semantics(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            state = self.make_seeded_state(directory)
            settings_before = asdict(state.settings)
            preserved_before = self.table_snapshot(state)

            summary = state.clear_data("all")

            rows_after = self.table_snapshot(state)
            for table in self.CLEARED_TABLES:
                expected_count = 1 if table in {"events", "settings_versions"} else 0
                self.assertEqual(len(rows_after[table]), expected_count, table)
            for table in self.PRESERVED_TABLES:
                self.assertEqual(rows_after[table], preserved_before[table], table)

            self.assertEqual(summary["events"], 1)
            self.assertEqual(summary["settings_versions"], 1)
            self.assertEqual(summary["backup_restore_history"], 1)
            for key, count in summary.items():
                if key not in {"events", "settings_versions", "backup_restore_history"}:
                    self.assertEqual(count, 0, key)

            reset_version = state.storage.load_settings_versions(1)[0]
            self.assertEqual(reset_version.id, state.current_settings_version_id)
            self.assertEqual(reset_version.label, "reset")
            self.assertEqual(reset_version.settings, settings_before)
            self.assertEqual(asdict(state.settings), settings_before)
            self.assertTrue(state.settings.kill_switch_enabled)
            self.assertFalse(state.settings.live_active_backend_armed)
            self.assertEqual(list(state.tokens), [])
            self.assertEqual([event.message for event in state.events], ["Data cleared: all"])
            self.assertEqual(list(state.backtest_runs), [])
            self.assertEqual(state.creator_history, Counter())
            self.assertEqual(state.stats.total_trades, 0)
            self.assertEqual(state.stats.total_pnl_sol, 0.0)


if __name__ == "__main__":
    unittest.main()
