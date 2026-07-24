from collections import deque
from dataclasses import asdict
from datetime import timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.core.models import BotMode, SettingsVersion, TokenSignal, TokenStatus, TradeRecord, utc_now
from app.core.state import BotState


class StrategyPromotionCohortTests(unittest.TestCase):
    def make_state(self, directory: str) -> BotState:
        return BotState(database_path=str(Path(directory) / "test.db"))

    def save_settings_version(self, state: BotState, version_id: str, **changes: object) -> str:
        settings = asdict(state.settings)
        settings.update(changes)
        state.storage.save_settings_version(
            SettingsVersion(
                id=version_id,
                created_at=utc_now(),
                settings=settings,
                label="test",
                changed_keys=sorted(changes),
            )
        )
        return version_id

    def make_trades(
        self,
        settings_version_id: str,
        pnls: list[float],
        *,
        start_offset: int = 0,
        mode: str = "paper",
        base_time=None,
    ) -> list[TradeRecord]:
        now = base_time or (utc_now() - timedelta(minutes=5))
        return [
            TradeRecord(
                id=f"trade_{settings_version_id}_{index}",
                token_id=f"token_{settings_version_id}_{index}",
                mode=mode,
                strategy_profile="balanced",
                entry_price=1.0,
                exit_price=1.0 + pnl,
                amount_sol=0.1,
                pnl_sol=pnl,
                entry_reason="test",
                exit_reason="test",
                opened_at=now + timedelta(seconds=start_offset + index),
                closed_at=now + timedelta(seconds=start_offset + index + 1),
                settings_version_id=settings_version_id,
            )
            for index, pnl in enumerate(pnls)
        ]

    def make_backtest_candidates(self, pnls: list[float]) -> list[TokenSignal]:
        return [
            TokenSignal(
                id=f"token_{index}",
                symbol=f"T{index}",
                name=f"Token {index}",
                mint=f"mint_{index}",
                creator=f"creator_{index}",
                detected_at=utc_now() + timedelta(seconds=index),
                status=TokenStatus.PAPER_SOLD,
                score=100,
                pnl_sol=pnl,
                buy_velocity=1.0,
                sell_pressure=0.0,
                metadata_score=1.0,
                initial_buy_sol=1.0,
            )
            for index, pnl in enumerate(pnls)
        ]

    def promotion(self, state: BotState, trades: list[TradeRecord]) -> dict[str, object]:
        return state._strategy_promotion_status(
            closed=trades,
            source_events=100,
            replay_confidence=100,
            source={"trust_state": "trusted"},
            price={"acceptance_rate": 1.0},
            performance={"pnl_sol": sum(trade.pnl_sol or 0.0 for trade in trades)},
            profit_factor=99.0,
            out_of_sample={
                "validate": {
                    "tokens_replayed": 10,
                    "estimated_pnl_sol": 0.1,
                    "profit_factor": 2.0,
                },
                "collapse_warning": False,
            },
            source_soak={"hard_required": False, "ready": False, "status": "not_configured"},
        )

    def test_promotion_combines_versions_that_only_change_live_ui_or_operator_controls(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            alternate_id = self.save_settings_version(
                state,
                "set_live_ui_only",
                live_max_trade_sol=0.02,
                compact_table_mode=True,
                kill_switch_enabled=True,
            )
            trades = [
                *self.make_trades(state.current_settings_version_id, [0.01] * 15),
                *self.make_trades(alternate_id, [0.01] * 15, start_offset=20),
            ]

            promotion = self.promotion(state, trades)
            closed_gate = next(gate for gate in promotion["gates"] if gate["id"] == "closed_trades")

            self.assertRegex(str(promotion.get("strategy_fingerprint", "")), r"^[0-9a-f]{16}$")
            self.assertEqual(set(promotion["matching_settings_version_ids"]), {state.current_settings_version_id, alternate_id})
            self.assertEqual(closed_gate["value"], 30)
            self.assertEqual(closed_gate["status"], "pass")

    def test_promotion_excludes_trades_from_a_different_paper_strategy(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            different_strategy_id = self.save_settings_version(
                state,
                "set_different_stop",
                stop_loss_pct=state.settings.stop_loss_pct + 1.0,
            )
            trades = [
                *self.make_trades(state.current_settings_version_id, [0.01] * 29),
                *self.make_trades(different_strategy_id, [0.01] * 30, start_offset=40),
            ]

            promotion = self.promotion(state, trades)
            closed_gate = next(gate for gate in promotion["gates"] if gate["id"] == "closed_trades")

            self.assertEqual(promotion.get("matching_closed_trades"), 29)
            self.assertEqual(closed_gate["value"], 29)
            self.assertEqual(closed_gate["status"], "fail")

    def test_promotion_uses_cohort_drawdown_and_reports_all_history_drawdown(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            different_strategy_id = self.save_settings_version(
                state,
                "set_old_strategy",
                trade_size_sol=state.settings.trade_size_sol + 0.01,
            )
            trades = [
                *self.make_trades(different_strategy_id, [1.0, -0.5]),
                *self.make_trades(state.current_settings_version_id, [0.01] * 30, start_offset=10),
            ]

            promotion = self.promotion(state, trades)
            drawdown_gate = next(gate for gate in promotion["gates"] if gate["id"] == "drawdown")

            self.assertEqual(drawdown_gate["value"], 0.0)
            self.assertEqual(promotion["all_history_drawdown_sol"], 0.5)
            self.assertEqual(promotion["all_history_closed_trades"], 32)

    def test_backtest_drawdown_is_peak_to_trough_not_distance_below_zero(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            state.settings.entry_confirmation_enabled = False
            state.settings.score_threshold = 0
            candidates = self.make_backtest_candidates([1.0, -0.4, 0.1])

            run = state._run_backtest(candidates, replay_source="drawdown_regression", persist=False)

            self.assertEqual(run.paper_buys, 3)
            self.assertEqual(run.max_drawdown_sol, 0.4)

    def test_recovery_does_not_relabel_versionless_legacy_position_as_current_strategy(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            token = TokenSignal(
                id="legacy_open",
                symbol="LEG",
                name="Legacy",
                mint="legacy_mint",
                creator="legacy_creator",
                detected_at=utc_now() - timedelta(hours=1),
                status=TokenStatus.PAPER_BOUGHT,
                amount_sol=0.1,
                pnl_sol=0.01,
                entry_price=1.0,
                current_price=1.1,
                opened_at=utc_now() - timedelta(minutes=30),
                settings_version_id="",
            )
            state.storage.save_token(token)
            state.tokens.appendleft(token)

            result = state.recover_open_paper_positions("legacy recovery")
            trade = next(item for item in state.storage.load_trades(10) if item.token_id == token.id)

            self.assertEqual(result["closed_positions"], 1)
            self.assertEqual(trade.settings_version_id, "")
            token.settings_version_id = "legacy_unknown"
            self.assertEqual(state.trade_from_token(token).settings_version_id, "legacy_unknown")

    def test_promotion_rejects_non_paper_records_even_when_fingerprint_matches(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            version_id = state.current_settings_version_id
            trades = [
                *self.make_trades(version_id, [0.01] * 29),
                *self.make_trades(version_id, [-1.0], mode="live", start_offset=40),
                *self.make_trades(version_id, [2.0], mode="import", start_offset=50),
            ]

            promotion = self.promotion(state, trades)
            closed_gate = next(gate for gate in promotion["gates"] if gate["id"] == "closed_trades")

            self.assertEqual(closed_gate["value"], 29)
            self.assertEqual(closed_gate["status"], "fail")
            self.assertEqual(promotion["recent_matching_closed_trades"], 29)
            self.assertEqual(promotion["matching_closed_trades"], 29)
            self.assertEqual(promotion["cohort_performance"]["pnl_sol"], 0.29)
            self.assertEqual(promotion["all_matching_strategy_drawdown_sol"], 0.0)

    def test_promotion_requires_thirty_matching_paper_trades_within_168_hours(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            version_id = state.current_settings_version_id
            stale = self.make_trades(
                version_id,
                [0.01] * 30,
                base_time=utc_now() - timedelta(days=8),
            )
            recent = self.make_trades(
                version_id,
                [0.01] * 29,
                base_time=utc_now() - timedelta(hours=1),
            )

            promotion = self.promotion(state, [*stale, *recent])
            closed_gate = next(gate for gate in promotion["gates"] if gate["id"] == "closed_trades")

            self.assertEqual(promotion.get("strategy_evidence_window_hours"), 168)
            self.assertEqual(promotion["matching_closed_trades"], 59)
            self.assertEqual(promotion["recent_matching_closed_trades"], 29)
            self.assertEqual(promotion["recent_oldest_closed_at"], min(trade.closed_at for trade in recent).isoformat())
            self.assertEqual(promotion["recent_newest_closed_at"], max(trade.closed_at for trade in recent).isoformat())
            self.assertEqual(closed_gate["value"], 29)
            self.assertEqual(closed_gate["status"], "fail")

    def test_future_dated_matching_paper_trades_cannot_satisfy_recent_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            version_id = state.current_settings_version_id
            recent = self.make_trades(version_id, [0.01] * 29)
            future = self.make_trades(
                version_id,
                [1.0, -2.0, *([0.01] * 28)],
                base_time=utc_now() + timedelta(days=1),
            )

            promotion = self.promotion(state, [*recent, *future])
            closed_gate = next(gate for gate in promotion["gates"] if gate["id"] == "closed_trades")
            drawdown_gate = next(gate for gate in promotion["gates"] if gate["id"] == "drawdown")

            self.assertEqual(promotion["recent_matching_closed_trades"], 29)
            self.assertEqual(promotion.get("excluded_future_timestamp_trades"), 30)
            self.assertEqual(promotion.get("excluded_ambiguous_timestamp_trades"), 0)
            self.assertEqual(promotion["cohort_performance"]["pnl_sol"], 0.29)
            self.assertEqual(drawdown_gate["value"], 0.0)
            self.assertEqual(closed_gate["value"], 29)
            self.assertEqual(closed_gate["status"], "fail")

    def test_recent_evidence_accepts_aware_offsets_and_excludes_naive_timestamps(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            version_id = state.current_settings_version_id
            utc_recent = self.make_trades(version_id, [0.01] * 29)
            offset_time = (utc_now() - timedelta(hours=1)).astimezone(timezone(timedelta(hours=5, minutes=30)))
            offset_recent = self.make_trades(version_id, [0.01], base_time=offset_time, start_offset=1)
            naive_time = (utc_now() - timedelta(hours=1)).replace(tzinfo=None)
            naive_legacy = self.make_trades(version_id, [-5.0], base_time=naive_time, start_offset=2)

            try:
                promotion = self.promotion(state, [*utc_recent, *offset_recent, *naive_legacy])
            except TypeError as exc:
                self.fail(f"mixed legacy timestamps must not crash promotion evidence: {exc}")
            closed_gate = next(gate for gate in promotion["gates"] if gate["id"] == "closed_trades")
            drawdown_gate = next(gate for gate in promotion["gates"] if gate["id"] == "drawdown")

            self.assertEqual(promotion["recent_matching_closed_trades"], 30)
            self.assertEqual(promotion.get("excluded_ambiguous_timestamp_trades"), 1)
            self.assertEqual(promotion.get("excluded_future_timestamp_trades"), 0)
            self.assertEqual(promotion["cohort_performance"]["pnl_sol"], 0.3)
            self.assertEqual(drawdown_gate["value"], 0.0)
            self.assertEqual(closed_gate["status"], "pass")
            self.assertIsInstance(promotion["all_history_drawdown_sol"], float)

    def test_all_backtest_paths_share_peak_to_trough_drawdown_with_initial_loss(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            state.settings.entry_confirmation_enabled = False
            state.settings.score_threshold = 0
            candidates = self.make_backtest_candidates([-0.2, 0.5, -0.4])
            state.tokens = deque(candidates, maxlen=80)

            helper = getattr(state, "_peak_to_trough_drawdown_sol", None)
            self.assertIsNotNone(helper)
            if helper is None:
                return
            self.assertEqual(helper([-0.2, 0.5, -0.4]), 0.4)

            replay = state.replay_backtest(limit=3)
            internal = state._run_backtest(candidates, replay_source="shared_drawdown", persist=False)
            comparison = state.compare_strategies(limit=3)

            self.assertEqual(replay.max_drawdown_sol, 0.4)
            self.assertEqual(internal.max_drawdown_sol, 0.4)
            self.assertEqual(comparison.max_drawdown_sol, 0.4)
            self.assertTrue(comparison.comparison)
            self.assertTrue(all(row["max_drawdown_sol"] == 0.4 for row in comparison.comparison))

    def test_fingerprint_classifies_every_setting_field_and_exposes_schema(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            expected_ignored = {
                "mode",
                "require_live_confirmation",
                "detect_new_tokens",
                "auto_refresh",
                "backtest_replay_limit",
                "raw_replay_limit",
                "enable_trade_toasts",
                "compact_table_mode",
                "kill_switch_enabled",
                "solana_rpc_url",
                "watch_wallet_address",
                "manual_live_enabled",
                "manual_live_max_sol",
                "autonomous_live_enabled",
                "live_trading_enabled",
                "live_max_trade_sol",
                "live_daily_loss_cap_sol",
                "live_wallet_exposure_cap_sol",
                "live_max_open_positions",
                "live_max_slippage_pct",
                "live_priority_fee_cap_sol",
                "live_session_acknowledged",
                "live_signer_mode",
                "live_active_backend_armed",
                "live_active_wallet_public_key",
                "live_hot_wallet_enabled",
                "live_hot_wallet_public_key",
                "live_hot_wallet_label",
                "profit_sweep_enabled",
                "profit_sweep_mode",
                "profit_sweep_threshold_sol",
                "profit_sweep_amount_sol",
                "profit_sweep_percentage",
                "profit_sweep_min_profit_sol",
                "profit_sweep_destination_wallet",
                "profit_sweep_min_reserve_sol",
                "profit_sweep_cooldown_seconds",
                "profit_sweep_max_per_day",
            }
            base = asdict(state.settings)
            baseline = state._paper_strategy_fingerprint(base)
            valid_strings = {
                "launch_source": "mock",
                "strategy_profile": "conservative",
                "trading_speed": "fast",
                "risk_tolerance": "low",
            }

            self.assertEqual(set(state.PAPER_STRATEGY_IGNORED_SETTING_KEYS), expected_ignored)
            for key, value in base.items():
                mutated = dict(base)
                if isinstance(value, bool):
                    mutated[key] = not value
                elif isinstance(value, int):
                    mutated[key] = value + 1
                elif isinstance(value, float):
                    mutated[key] = value + 0.125
                elif key == "mode":
                    mutated[key] = BotMode.PREVIEW
                else:
                    mutated[key] = valid_strings.get(key, f"{value}_changed")
                candidate = state._paper_strategy_fingerprint(mutated)
                if key in expected_ignored:
                    self.assertEqual(candidate, baseline, key)
                else:
                    self.assertNotEqual(candidate, baseline, key)

            promotion = self.promotion(
                state,
                self.make_trades(state.current_settings_version_id, [0.01] * 30),
            )
            self.assertEqual(promotion.get("strategy_fingerprint_schema"), "paper-strategy-v1")


if __name__ == "__main__":
    unittest.main()
