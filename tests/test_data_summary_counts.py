import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from app.core.state import BotState
from app.core.storage import Storage


LEGACY_COUNT_METHODS = {
    "tokens": "count_tokens",
    "events": "count_events",
    "source_events": "count_source_events",
    "backtests": "count_backtest_runs",
    "trades": "count_trades",
    "price_observations": "count_price_observations",
    "strategy_decisions": "count_strategy_decisions",
    "trade_sessions": "count_trade_sessions",
    "settings_versions": "count_settings_versions",
    "experiments": "count_experiment_runs",
    "trade_labels": "count_trade_labels",
    "strategy_presets": "count_strategy_presets",
    "live_execution_requests": "count_live_execution_requests",
    "live_sessions": "count_live_sessions",
    "live_execution_audits": "count_live_execution_audits",
    "live_intents": "count_live_intents",
    "live_ledger_positions": "count_live_ledger_positions",
    "backup_restore_history": "count_backup_restore_history",
    "source_soak_history": "count_source_soak_history",
}


class DataSummaryCountsTests(unittest.TestCase):
    def _seed_summary_tables(self, storage: Storage) -> dict[str, int]:
        table_for_key = {
            "tokens": "tokens",
            "events": "events",
            "source_events": "source_events",
            "backtests": "backtest_runs",
            "trades": "trades",
            "price_observations": "price_observations",
            "strategy_decisions": "strategy_decisions",
            "trade_sessions": "trade_sessions",
            "settings_versions": "settings_versions",
            "experiments": "experiment_runs",
            "trade_labels": "trade_labels",
            "strategy_presets": "strategy_presets",
            "live_execution_requests": "live_execution_requests",
            "live_sessions": "live_sessions",
            "live_execution_audits": "live_execution_audits",
            "live_intents": "live_intents",
            "live_ledger_positions": "live_ledger_positions",
            "backup_restore_history": "backup_restore_history",
            "source_soak_history": "source_soak_history",
        }
        expected = {key: index for index, key in enumerate(LEGACY_COUNT_METHODS, start=1)}
        timestamp = "2026-07-20T00:00:00+00:00"

        with storage._connect() as connection:
            for key, count in expected.items():
                table = table_for_key[key]
                for index in range(count):
                    item_id = f"{key}-{index}"
                    if table == "tokens":
                        connection.execute(
                            "INSERT INTO tokens (id, payload, detected_at) VALUES (?, ?, ?)",
                            (item_id, "{}", timestamp),
                        )
                    elif table == "events":
                        connection.execute(
                            "INSERT INTO events (id, payload, created_at) VALUES (?, ?, ?)",
                            (item_id, "{}", timestamp),
                        )
                    elif table == "source_events":
                        connection.execute(
                            "INSERT INTO source_events (id, source, payload, received_at) VALUES (?, ?, ?, ?)",
                            (item_id, "test", "{}", timestamp),
                        )
                    elif table == "trades":
                        connection.execute(
                            "INSERT INTO trades (id, token_id, payload, opened_at, closed_at) VALUES (?, ?, ?, ?, ?)",
                            (item_id, "token-test", "{}", timestamp, timestamp),
                        )
                    elif table == "price_observations":
                        connection.execute(
                            "INSERT INTO price_observations (id, mint, payload, observed_at) VALUES (?, ?, ?, ?)",
                            (item_id, "mint-test", "{}", timestamp),
                        )
                    elif table == "strategy_decisions":
                        connection.execute(
                            "INSERT INTO strategy_decisions (id, token_id, payload, created_at) VALUES (?, ?, ?, ?)",
                            (item_id, "token-test", "{}", timestamp),
                        )
                    elif table == "trade_sessions":
                        connection.execute(
                            "INSERT INTO trade_sessions (id, token_id, mint, payload, opened_at, closed_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (item_id, "token-test", "mint-test", "{}", timestamp, timestamp),
                        )
                    elif table == "source_soak_history":
                        connection.execute(
                            "INSERT INTO source_soak_history (id, payload, created_at, status, ready) VALUES (?, ?, ?, ?, ?)",
                            (item_id, "{}", timestamp, "ready", 1),
                        )
                    else:
                        connection.execute(
                            f"INSERT INTO {table} (id, payload, created_at) VALUES (?, ?, ?)",
                            (item_id, "{}", timestamp),
                        )
        return expected

    def test_data_summary_counts_matches_legacy_counts_with_seeded_rows(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "summary.db"))
            expected = self._seed_summary_tables(storage)

            legacy = {key: getattr(storage, method)() for key, method in LEGACY_COUNT_METHODS.items()}

            self.assertEqual(legacy, expected)
            self.assertEqual(storage.data_summary_counts(), legacy)

    def test_data_summary_counts_uses_one_connection_lifecycle(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "summary.db"))
            self._seed_summary_tables(storage)

            with patch.object(storage, "_connect", wraps=storage._connect) as connect:
                counts = storage.data_summary_counts()

            self.assertEqual(counts["source_soak_history"], 19)
            self.assertEqual(connect.call_count, 1)

    def test_bot_state_data_summary_delegates_once(self) -> None:
        expected = {key: index for index, key in enumerate(LEGACY_COUNT_METHODS, start=1)}
        state = object.__new__(BotState)
        state.storage = Mock()
        state.storage.data_summary_counts.return_value = expected

        self.assertEqual(state.data_summary(), expected)
        state.storage.data_summary_counts.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
