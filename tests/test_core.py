import ast
import base64
import inspect
import json
import sqlite3
import unittest
from collections import deque
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

from app.core.alerts import AlertRouter
from app.core.models import BacktestRun, BotMode, BotSettings, BotStats, BotStatus, ExperimentRun, LiveExecutionAudit, LiveExecutionIntent, LiveExecutionRequest, LiveLedgerPosition, PriceObservation, SourceEvent, StrategyDecisionRecord, StrategyPreset, TokenSignal, TokenStatus, TradeEvent, TradeLabel, TradeRecord, TradeSession, new_id, utc_now
from app.core.paper_trader import PaperTrader
from app.core.price_pipeline import PricePipeline, numeric as price_pipeline_numeric
from app.core.risk import RiskEngine
from app.core.scoring import ScoringEngine
from app.core import sources as sources_module
from app.core.sources import LaunchEvent, PumpPortalLaunchSource, normalize_pumpportal_new_token, normalize_pumpportal_trade, solana_logs_subscribe_payload
from app.core.storage import Storage
from app.core.state import BotState
from app.core.integrity import DataIntegrityAnalyzer


class CoreLogicTests(unittest.TestCase):
    def make_token(self) -> TokenSignal:
        return TokenSignal(
            id="tok_test",
            symbol="ARC",
            name="Arc Test",
            mint="mint_test",
            creator="creator_test",
            detected_at=utc_now(),
            age_seconds=5,
            buy_velocity=0.9,
            sell_pressure=0.1,
            metadata_score=0.9,
            current_price=0.00001,
        )

    def seed_readiness_dataset(self, state: BotState, pnl_sol: float = 0.01, source_connected: bool = True) -> None:
        now = utc_now()
        state.source_status.status = "connected" if source_connected else "offline"
        state.source_status.last_event_at = now
        state.source_status.raw_events_seen = 100
        state.source_status.normalized_events = 100 if source_connected else 10
        for index in range(30):
            token = self.make_token()
            token.id = f"tok_ready_{index}"
            token.mint = f"MintReady{index}"
            token.symbol = f"ARC{index}"
            token.score = 88
            token.status = TokenStatus.PAPER_SOLD
            token.pnl_sol = pnl_sol
            token.exit_reason = "take profit" if pnl_sol >= 0 else "stop loss"
            state.storage.save_token(token)
            state.storage.save_trade(
                TradeRecord(
                    id=f"trd_ready_{index}",
                    token_id=token.id,
                    mode="paper",
                    strategy_profile="balanced",
                    entry_price=0.00001,
                    exit_price=0.00002,
                    amount_sol=0.1,
                    pnl_sol=pnl_sol,
                    entry_reason="test",
                    exit_reason=token.exit_reason,
                    opened_at=now,
                    closed_at=now,
                    source_price_confidence=0.9,
                    settings_version_id=state.current_settings_version_id,
                )
            )
            state.storage.save_strategy_decision(
                StrategyDecisionRecord(
                    id=f"dec_ready_{index}",
                    token_id=token.id,
                    mint=token.mint,
                    created_at=now,
                    engine_version="strategy-v3",
                    profile="balanced",
                    score=88,
                    allowed=True,
                    action="paper_buy",
                    reason="test",
                    risk_reason="passed",
                )
            )
            state.storage.save_price_observation(
                PriceObservation(
                    id=f"px_ready_{index}",
                    source="pumpportal",
                    mint=token.mint,
                    observed_at=now,
                    price=0.00002,
                    price_source="direct",
                    confidence=0.9,
                    accepted=True,
                    token_id=token.id,
                )
            )
        for index in range(100):
            state.storage.save_source_event(
                SourceEvent(
                    id=f"src_ready_{index}",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"mint": f"MintReady{index % 30}"},
                    normalized_token_id=f"tok_ready_{index % 30}" if source_connected else None,
                    status="normalized" if source_connected else "raw",
                )
            )

    def test_scoring_rewards_good_launch_profile(self) -> None:
        token = self.make_token()
        result = ScoringEngine().score(token)
        self.assertGreaterEqual(result.score, 80)
        self.assertIn("strong early buy velocity", result.reason)

    def test_risk_rejects_low_score(self) -> None:
        token = self.make_token()
        token.score = 20
        decision = RiskEngine().evaluate(token, BotSettings(), BotStats(), open_positions=0)
        self.assertFalse(decision.allowed)
        self.assertIn("below entry threshold", decision.reason)

    def test_risk_rejects_creator_concentration(self) -> None:
        token = self.make_token()
        token.score = 95
        token.creator_hold_pct = 25
        decision = RiskEngine().evaluate(token, BotSettings(max_creator_hold_pct=10), BotStats(), open_positions=0)
        self.assertFalse(decision.allowed)
        self.assertIn("creator hold", decision.reason)

    def test_risk_rejects_custom_quality_filters(self) -> None:
        token = self.make_token()
        token.score = 95
        token.buy_velocity = 0.2
        decision = RiskEngine().evaluate(token, BotSettings(min_buy_velocity=0.5), BotStats(), open_positions=0)
        self.assertFalse(decision.allowed)
        self.assertIn("buy velocity", decision.reason)

    def test_entry_confirmation_gate_rejects_thin_unconfirmed_launch(self) -> None:
        token = self.make_token()
        token.score = 95
        token.buy_velocity = 0.3
        token.sell_pressure = 0.1
        token.metadata_score = 0.9
        token.initial_buy_sol = 0.05
        token.price_confidence = 0.0
        token.observed_price_updates = 0

        decision = RiskEngine().evaluate(token, BotSettings(), BotStats(), open_positions=0)

        self.assertFalse(decision.allowed)
        self.assertIn("entry confirmation", decision.reason)

    def test_entry_confirmation_gate_allows_confirmed_launch_evidence(self) -> None:
        token = self.make_token()
        token.score = 95
        token.buy_velocity = 0.78
        token.sell_pressure = 0.1
        token.metadata_score = 0.8
        token.initial_buy_sol = 0.6
        token.price_confidence = 0.75

        decision = RiskEngine().evaluate(token, BotSettings(), BotStats(), open_positions=0)

        self.assertTrue(decision.allowed)

    def test_entry_confirmation_gate_can_be_disabled_for_experiments(self) -> None:
        token = self.make_token()
        token.score = 95
        token.buy_velocity = 0.3
        token.sell_pressure = 0.1
        token.metadata_score = 0.9

        decision = RiskEngine().evaluate(
            token,
            BotSettings(entry_confirmation_enabled=False),
            BotStats(),
            open_positions=0,
        )

        self.assertTrue(decision.allowed)

    def test_integrity_info_penalty_stays_light_for_rejected_prices(self) -> None:
        token = self.make_token()
        trade = TradeRecord(
            id="trade_integrity",
            token_id=token.id,
            mode="paper",
            strategy_profile="balanced",
            entry_price=0.00001,
            exit_price=0.00002,
            amount_sol=0.1,
            pnl_sol=0.01,
            entry_reason="test",
            exit_reason="take profit",
            opened_at=utc_now(),
            closed_at=utc_now(),
            lifecycle_status="closed",
        )
        observations = [
            PriceObservation(
                id=f"px_{index}",
                source="pumpportal",
                mint=token.mint,
                observed_at=utc_now(),
                price=0.00001,
                price_source="direct",
                confidence=0.2,
                accepted=False,
                token_id=token.id,
            )
            for index in range(13)
        ]
        decision = StrategyDecisionRecord(
            id="decision_integrity",
            token_id=token.id,
            mint=token.mint,
            created_at=utc_now(),
            engine_version="strategy-v3",
            profile="balanced",
            score=88,
            allowed=True,
            action="paper_buy",
            reason="test",
            risk_reason="passed",
        )
        report = DataIntegrityAnalyzer().report([token], [trade], observations, [], [decision])
        self.assertEqual(report["score"], 95)

    def test_integrity_ignores_duplicate_untraded_source_candidates_and_status_errors(self) -> None:
        token = self.make_token()
        token.status = TokenStatus.PAPER_SOLD
        duplicate_candidate = self.make_token()
        duplicate_candidate.id = "tok_duplicate_candidate"
        duplicate_candidate.symbol = "DUP"
        duplicate_candidate.mint = token.mint
        trade = TradeRecord(
            id="trade_duplicate_integrity",
            token_id=token.id,
            mode="paper",
            strategy_profile="balanced",
            entry_price=0.00001,
            exit_price=0.00002,
            amount_sol=0.1,
            pnl_sol=0.01,
            entry_reason="test",
            exit_reason="take profit",
            opened_at=utc_now(),
            closed_at=utc_now(),
            lifecycle_status="closed",
        )
        decision = StrategyDecisionRecord(
            id="decision_duplicate_integrity",
            token_id=token.id,
            mint=token.mint,
            created_at=utc_now(),
            engine_version="strategy-v3",
            profile="balanced",
            score=88,
            allowed=True,
            action="paper_buy",
            reason="test",
            risk_reason="passed",
        )
        observation = PriceObservation(
            id="px_duplicate_integrity",
            source="pumpportal",
            mint=token.mint,
            observed_at=utc_now(),
            price=0.00002,
            price_source="direct",
            confidence=0.9,
            accepted=True,
            token_id=token.id,
        )
        status_error = SourceEvent(
            id="src_min_balance",
            source="pumpportal",
            received_at=utc_now(),
            raw_payload={"errors": "Minimum balance not met for PumpSwap websocket data."},
            normalized_token_id=None,
            status="raw",
        )
        quote_mint_reject = SourceEvent(
            id="src_quote_mint_reject",
            source="pumpportal",
            received_at=utc_now(),
            raw_payload={"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "txType": "create"},
            normalized_token_id=None,
            status="raw",
        )

        report = DataIntegrityAnalyzer().report([token, duplicate_candidate], [trade], [observation], [status_error, quote_mint_reject], [decision])

        self.assertEqual(report["score"], 100)
        self.assertEqual(report["issues"], [])

    def test_pumpportal_parser_rejects_known_quote_mint_launch_candidates(self) -> None:
        token = normalize_pumpportal_new_token(
            {
                "signature": "sig_test",
                "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "traderPublicKey": "trader_test",
                "txType": "create",
                "initialBuy": 1.0,
                "solAmount": 1.0,
                "bondingCurveKey": "curve_test",
                "marketCapSol": 100,
                "pool": "pumpswap",
            },
            utc_now(),
        )

        self.assertIsNone(token)

    def test_paper_trade_closes_at_take_profit(self) -> None:
        token = self.make_token()
        settings = BotSettings(trade_size_sol=0.1, take_profit_pct=50, stop_loss_pct=30, paper_fee_bps=0, paper_price_impact_pct=0)
        trader = PaperTrader()
        trader.buy(token, settings)
        closed = trader.tick(token, settings, price_delta_pct=52)
        self.assertTrue(closed)
        self.assertEqual(token.status, TokenStatus.PAPER_SOLD)
        self.assertAlmostEqual(token.pnl_sol or 0, 0.05197)
        self.assertEqual(token.exit_reason, "take profit")

    def test_losing_sell_event_is_warning_not_danger(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.status = TokenStatus.MONITORING
            token.entry_price = 0.00001
            token.current_price = 0.00001
            token.amount_sol = 0.1
            token.opened_at = utc_now()
            state.tokens.append(token)
            def close_with_loss(token_arg, settings_arg, delta_pct):
                token_arg.status = TokenStatus.PAPER_SOLD
                token_arg.exit_reason = "stop loss"
                token_arg.closed_at = utc_now()
                token_arg.pnl_sol = -0.01
                return True
            state.paper.tick = close_with_loss  # type: ignore[method-assign]

            state.tick()

            sell_event = next(event for event in state.storage.load_all_events(20) if "Paper sold" in event.message)
            self.assertEqual(sell_event.level, "warning")

    def test_recover_open_paper_positions_closes_accounting_debt(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.status = TokenStatus.MONITORING
            token.entry_price = 0.00001
            token.current_price = 0.000011
            token.amount_sol = 0.1
            token.opened_at = utc_now() - timedelta(minutes=15)
            token.pnl_sol = 0.0095
            state.tokens.appendleft(token)
            state.storage.save_token(token)
            state.storage.save_trade(state.trade_from_token(token))
            state.storage.save_trade_session(state.session_from_token(token, "opened"))

            result = state.recover_open_paper_positions("operator stopped run")

            self.assertEqual(result["closed_positions"], 1)
            recovered = state.storage.load_trades(10)[0]
            self.assertEqual(recovered.lifecycle_status, "closed")
            self.assertEqual(recovered.exit_reason, "paper recovery: operator stopped run")
            self.assertIsNotNone(recovered.closed_at)
            self.assertAlmostEqual(recovered.pnl_sol or 0, 0.0095)
            session = state.storage.load_trade_sessions(10)[0]
            self.assertEqual(session.status, "closed")
            self.assertIsNotNone(session.closed_at)
            self.assertEqual(state.open_position_count(), 0)
            self.assertTrue(any("Recovered 1 open paper position" in event.message for event in state.storage.load_all_events(10)))

    def test_tick_keeps_storage_open_positions_from_becoming_orphaned_when_deque_is_crowded(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.settings.max_position_ticks = 1
            active = self.make_token()
            active.id = "tok_active_evicted"
            active.mint = "mint_active_evicted"
            active.symbol = "ACTIVE"
            active.status = TokenStatus.MONITORING
            active.entry_price = 0.00001
            active.current_price = 0.00001
            active.amount_sol = 0.1
            active.opened_at = utc_now() - timedelta(minutes=5)
            active.pnl_sol = 0.0
            state.storage.save_token(active)
            state.storage.save_trade(state.trade_from_token(active))
            state.storage.save_trade_session(state.session_from_token(active, "opened"))

            state.tokens.clear()
            for index in range(100):
                crowded = self.make_token()
                crowded.id = f"tok_crowded_{index}"
                crowded.mint = f"mint_crowded_{index}"
                crowded.detected_at = utc_now() + timedelta(seconds=index)
                crowded.status = TokenStatus.SKIPPED
                state.tokens.appendleft(crowded)
                state.storage.save_token(crowded)

            self.assertFalse(any(token.id == active.id for token in state.tokens))

            state.tick()

            closed = next(token for token in state.storage.load_all_tokens(5000) if token.id == active.id)
            self.assertEqual(closed.status, TokenStatus.PAPER_SOLD)
            self.assertEqual(closed.exit_reason, "max position ticks")
            self.assertIsNotNone(closed.closed_at)
            trade = next(trade for trade in state.storage.load_trades(5000) if trade.token_id == active.id)
            self.assertEqual(trade.lifecycle_status, "closed")
            self.assertEqual(trade.exit_reason, "max position ticks")
            self.assertEqual(state.open_position_count(), 0)

    def test_observed_trade_updates_storage_open_position_missing_from_deque(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            active = self.make_token()
            active.id = "tok_trade_update_evicted"
            active.mint = "mint_trade_update_evicted"
            active.symbol = "UPDATE"
            active.status = TokenStatus.MONITORING
            active.entry_price = 0.00001
            active.current_price = 0.00001
            active.amount_sol = 0.1
            active.opened_at = utc_now() - timedelta(minutes=5)
            active.pnl_sol = 0.0
            state.storage.save_token(active)
            state.storage.save_trade(state.trade_from_token(active))
            state.storage.save_trade_session(state.session_from_token(active, "opened"))
            state.tokens.clear()

            event = LaunchEvent(
                source="pumpportal",
                received_at=utc_now(),
                raw_payload={"txType": "buy", "mint": active.mint, "marketCapSol": 20.0},
                token=None,
                message="token trade buy",
                kind="trade",
                mint=active.mint,
                trade_side="buy",
            )

            state.apply_observed_trade(event)

            updated = next(token for token in state.storage.load_all_tokens(5000) if token.id == active.id)
            self.assertGreater(updated.observed_price_updates, 0)
            self.assertEqual(updated.last_observed_trade_at, event.received_at)
            self.assertTrue(any(token.id == active.id for token in state.tokens))

    def test_paper_trade_can_delay_fill_and_charge_fees(self) -> None:
        token = self.make_token()
        settings = BotSettings(paper_fill_delay_ticks=1, paper_fee_bps=50, paper_price_impact_pct=0.2, paper_priority_fee_sol=0.0001)
        trader = PaperTrader()
        trader.buy(token, settings)

        self.assertEqual(token.status, TokenStatus.BUYING)
        self.assertEqual(token.fill_delay_ticks_remaining, 1)
        self.assertFalse(trader.tick(token, settings, price_delta_pct=10))
        self.assertEqual(token.status, TokenStatus.PAPER_BOUGHT)
        self.assertGreater(token.fee_paid_sol, 0)
        self.assertGreater(token.price_impact_pct, 0)
        self.assertAlmostEqual(token.entry_provider_fee_sol, 0.0005)
        self.assertAlmostEqual(token.entry_network_fee_sol, 0.000005)
        self.assertAlmostEqual(token.entry_priority_fee_sol, 0.0001)
        self.assertAlmostEqual(token.fee_paid_sol, 0.000605)
        self.assertGreater(token.entry_slippage_cost_sol, 0)
        self.assertGreater(token.entry_price_impact_cost_sol, 0)
        trader.close(token, settings, "test close")
        self.assertAlmostEqual(token.exit_provider_fee_sol, 0.0005)
        self.assertAlmostEqual(token.exit_network_fee_sol, 0.000005)
        self.assertAlmostEqual(token.exit_priority_fee_sol, 0.0001)
        self.assertAlmostEqual(token.exit_fee_sol, 0.000605)
        self.assertAlmostEqual(token.total_fees_sol, 0.00121)

    def test_paper_exit_provider_fee_scales_with_exit_notional(self) -> None:
        token = self.make_token()
        settings = BotSettings(trade_size_sol=0.1, paper_fee_bps=50, paper_price_impact_pct=0, paper_priority_fee_sol=0.00001)
        trader = PaperTrader()
        trader.buy(token, settings)
        token.current_price = (token.entry_price or 0.00001) * 2

        trader.close(token, settings, "take profit")

        self.assertAlmostEqual(token.entry_provider_fee_sol, 0.0005)
        self.assertAlmostEqual(token.exit_provider_fee_sol, 0.001)
        self.assertAlmostEqual(token.exit_fee_sol, 0.001015)
        self.assertAlmostEqual(token.total_fees_sol, 0.00153)

    def test_stats_classify_fee_only_trade_as_scratch(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.status = TokenStatus.PAPER_SOLD
            token.pnl_sol = -0.0005
            state.tokens.appendleft(token)

            state.recalculate_stats()

            self.assertEqual(state.stats.scratch_trades, 1)
            self.assertEqual(state.stats.losing_trades, 0)
            self.assertEqual(state.stats.win_rate_pct, 0)

    def test_storage_round_trip_settings_and_token(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "test.db"))
            settings = BotSettings(score_threshold=70, max_open_positions=5)
            token = self.make_token()
            token.score = 88
            token.score_breakdown = ["clean metadata"]

            storage.save_settings(settings)
            storage.save_token(token)

            self.assertEqual(storage.load_settings().score_threshold, 70)
            loaded = storage.load_tokens()[0]
            self.assertEqual(loaded.id, token.id)
            self.assertEqual(loaded.score_breakdown, ["clean metadata"])

    def test_storage_initializes_via_migration_runner(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "test.db"))

            schema = storage.schema_status()

            self.assertEqual(schema["status"], "ok")
            self.assertEqual(schema["current_version"], storage.SCHEMA_VERSION)
            self.assertTrue(schema["migrations"])

    def test_storage_upgrades_legacy_schema_marker(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
            connection.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (5, ?)", (utc_now().isoformat(),))
            connection.execute("CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL)")
            connection.commit()
            connection.close()

            storage = Storage(str(path))

            schema = storage.schema_status()
            self.assertEqual(schema["current_version"], storage.SCHEMA_VERSION)
            self.assertTrue(any(item["migration_id"] == "006_backup_restore_history" for item in schema["migrations"]))

    def test_restore_artifact_preview_rejects_invalid_payload(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "test.db"))

            with self.assertRaises(ValueError):
                storage.preview_restore_artifact({"artifact_type": "cryptoarc_local_backup", "format_version": 1, "database_base64": "not-valid-base64"})

    def test_restore_artifact_preview_rejects_non_sqlite_payload(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "test.db"))
            artifact = {
                "artifact_type": "cryptoarc_local_backup",
                "format_version": 1,
                "database_base64": "bm90IGEgc3FsaXRlIGRhdGFiYXNl",
            }

            with self.assertRaises(ValueError):
                storage.preview_restore_artifact(artifact)

    def test_restore_artifact_replaces_local_state_and_records_history(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            state = BotState(database_path=str(path))
            token = self.make_token()
            state.storage.save_token(token)
            artifact = state.storage.create_backup_artifact()
            state.storage.clear_tokens()
            state.settings.kill_switch_enabled = True

            result = state.confirm_restore_artifact(artifact)

            self.assertEqual(result["status"], "restored")
            restored_ids = [item.id for item in state.storage.load_tokens()]
            self.assertIn(token.id, restored_ids)
            self.assertTrue(state.storage.load_backup_restore_history())

    def test_restore_artifact_preview_reports_table_deltas_and_actions(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            state = BotState(database_path=str(path))
            token = self.make_token()
            state.storage.save_token(token)
            artifact = state.storage.create_backup_artifact()
            state.storage.clear_tokens()

            preview = state.storage.preview_restore_artifact(artifact)

            self.assertEqual(preview["risk_level"], "review")
            self.assertEqual(preview["table_deltas"]["tokens"]["current"], 0)
            self.assertEqual(preview["table_deltas"]["tokens"]["artifact"], 1)
            self.assertIn("tokens", preview["changed_tables"])
            self.assertTrue(preview["recommended_actions"])
            self.assertEqual(preview["integrity_check"], "ok")

    def test_backup_restore_export_contains_recovery_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            state.storage.save_token(token)
            state.backup_artifact()
            history = state.storage.load_backup_restore_history()

            export = state.backup_restore_export(str(history[0]["id"]))

            self.assertEqual(export["artifact_type"], "cryptoarc_backup_restore_evidence")
            self.assertEqual(export["selected_entry"]["id"], history[0]["id"])
            self.assertIn("schema", export)
            self.assertIn("data_summary", export)
            self.assertIn("live_recovery", export)
            self.assertTrue(export["operator_events"])
            self.assertIn("privacy_note", export)

    def test_restore_smoke_test_creates_safe_audit_report(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            state.storage.save_token(token)

            report = state.restore_smoke_test()

            self.assertEqual(report["artifact_type"], "cryptoarc_restore_smoke_test")
            self.assertEqual(report["status"], "pass")
            self.assertTrue(report["passed"])
            self.assertEqual(report["integrity_check"], "ok")
            self.assertEqual(report["risk_level"], "low")
            self.assertIn("privacy_note", report)
            self.assertNotIn("database_base64", json.dumps(report))
            history = state.storage.load_backup_restore_history()
            self.assertTrue(any(item.get("action") == "backup_artifact" for item in history))
            events = state.storage.load_all_events(10)
            self.assertTrue(any(event.subsystem == "backup_restore" and "Restore smoke test completed" in event.message for event in events))

    def test_monitor_pnl_summary_filters_by_timeframe(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            recent = TradeRecord(
                id="trade_recent",
                token_id="tok_recent",
                mode="paper",
                strategy_profile="balanced",
                entry_price=0.00001,
                exit_price=0.00002,
                amount_sol=0.1,
                pnl_sol=0.02,
                entry_reason="test",
                exit_reason="tp",
                opened_at=now,
                closed_at=now,
                entry_fee_sol=0.00025,
                exit_fee_sol=0.00025,
                lifecycle_status="closed",
            )
            old = TradeRecord(
                id="trade_old",
                token_id="tok_old",
                mode="paper",
                strategy_profile="balanced",
                entry_price=0.00001,
                exit_price=0.000009,
                amount_sol=0.1,
                pnl_sol=-0.01,
                entry_reason="test",
                exit_reason="sl",
                opened_at=now.replace(year=2025),
                closed_at=now.replace(year=2025),
                entry_fee_sol=0.00025,
                exit_fee_sol=0.00025,
                lifecycle_status="closed",
            )
            state.storage.save_trade(recent)
            state.storage.save_trade(old)

            summary_recent = state.monitor_pnl_summary("5m")
            summary_all = state.monitor_pnl_summary("all")

            self.assertEqual(summary_recent["closed_trade_count"], 1)
            self.assertAlmostEqual(float(summary_recent["pnl_sol"]), 0.02)
            self.assertAlmostEqual(float(summary_recent["entry_fees_sol"]), 0.00025)
            self.assertAlmostEqual(float(summary_recent["exit_fees_sol"]), 0.00025)
            self.assertAlmostEqual(float(summary_recent["total_fees_sol"]), 0.0005)
            self.assertEqual(summary_all["closed_trade_count"], 2)
            self.assertAlmostEqual(float(summary_all["pnl_sol"]), 0.01)
            self.assertAlmostEqual(float(summary_all["total_fees_sol"]), 0.001)

    def test_fresh_state_defaults_to_pumpportal_source(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            self.assertEqual(state.settings.launch_source, "pumpportal")
            self.assertEqual(state.source_status.source, "pumpportal")

    def test_local_signer_daemon_status_reports_contract_only_defaults(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            status = state.signer_status("local_signer_daemon", "")

            self.assertEqual(status["mode"], "local_signer_daemon")
            self.assertEqual(status["transport"], "localhost_http")
            self.assertFalse(status["connected"])
            self.assertFalse(status["healthy"])
            self.assertFalse(status["auth_configured"])

    def test_local_signer_daemon_status_blocks_readiness_without_auth(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"connected":true,"healthy":true,"can_sign":true,"can_unattended_sign":true,"supports_auto_buy":true,"supports_auto_sell":true,"wallet_public_key":"WalletSigner"}'

        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"), signer_daemon_auth_token="")
            with patch("app.core.state.urllib.request.urlopen", return_value=FakeResponse()):
                status = state.signer_status("local_signer_daemon", "")

            self.assertFalse(status["healthy"])
            self.assertFalse(status["can_sign"])
            self.assertFalse(status["auth_configured"])
            self.assertIn("auth token", status["disabled_reason"].lower())

    def test_local_signer_daemon_rejects_legacy_healthy_payload_without_ready_to_submit(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"connected":true,"healthy":true,"can_sign":true,"can_unattended_sign":true,"supports_auto_buy":true,"supports_auto_sell":true,"wallet_public_key":"WalletSigner"}'

        with TemporaryDirectory() as directory:
            state = BotState(
                database_path=str(Path(directory) / "test.db"),
                signer_daemon_auth_token="s" * 32,
            )
            with patch("app.core.state.urllib.request.urlopen", return_value=FakeResponse()):
                status = state.signer_status("local_signer_daemon", "")

            self.assertFalse(status["ready_to_submit"])
            self.assertFalse(status["healthy"])
            self.assertFalse(status["can_sign"])
            self.assertFalse(status["can_unattended_sign"])
            self.assertIn("ready_to_submit", status["disabled_reason"])

            blockers = state._live_execution_blockers(
                True,
                "sell",
                "WalletSigner",
                "local_signer_daemon",
                signer={
                    "connected": True,
                    "healthy": True,
                    "can_sign": True,
                    "can_unattended_sign": True,
                    "supports_auto_buy": True,
                    "supports_auto_sell": True,
                },
                caps={
                    "max_trade_sol": 0.001,
                    "daily_loss_cap_sol": 0.005,
                    "wallet_exposure_cap_sol": 0.01,
                    "max_open_positions": 1,
                    "max_slippage_pct": 1,
                    "priority_fee_cap_sol": 0.00001,
                },
                wallet_metrics={"cost_basis_sol": 0.0, "realized_pnl_sol": 0.0, "unrealized_pnl_sol": 0.0, "open_positions": 0.0},
            )

            self.assertTrue(any("ready_to_submit" in blocker for blocker in blockers))

    def test_local_signer_daemon_execute_rejects_remote_endpoint_before_network(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"), signer_daemon_url="https://signer.example.invalid")
            audit = LiveExecutionAudit(
                id="liveaudit_remote_signer",
                created_at=utc_now(),
                updated_at=utc_now(),
                action="buy",
                mint="MintRemoteSigner",
                amount="0.001",
                status="ready",
                signer_mode="local_signer_daemon",
                wallet_public_key="WalletRemoteSigner",
                quote={"unsigned_transaction_base64": "dHgi"},
            )

            with patch("app.core.state.urllib.request.urlopen", side_effect=AssertionError("remote signer network call")):
                with self.assertRaisesRegex(ValueError, "localhost-only"):
                    state._execute_backend_audit(audit)

    def test_local_signer_daemon_execute_sends_amount_context(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"signature":"sig"}'

        captured: dict[str, object] = {}

        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            captured["timeout"] = timeout
            captured["data"] = json.loads(getattr(request, "data").decode("utf-8"))
            return FakeResponse()

        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"), signer_daemon_url="http://127.0.0.1:8799")
            audit = LiveExecutionAudit(
                id="liveaudit_local_signer_amount",
                created_at=utc_now(),
                updated_at=utc_now(),
                action="buy",
                mint="MintLocalSigner",
                amount="0.001",
                status="ready",
                signer_mode="local_signer_daemon",
                wallet_public_key="WalletLocalSigner",
                quote={"unsigned_transaction_base64": "dHgi"},
            )

            with patch("app.core.state.urllib.request.urlopen", side_effect=fake_urlopen):
                result = state._execute_backend_audit(audit)

            self.assertEqual(result["signature"], "sig")
            self.assertEqual(captured["data"]["amount"], "0.001")
            self.assertEqual(captured["data"]["amount_sol"], 0.001)
            self.assertNotIn("rpc_url", captured["data"])

    def test_storage_round_trip_source_event_and_backtest(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "test.db"))
            source_event = SourceEvent(
                id=new_id("src"),
                source="mock",
                received_at=utc_now(),
                raw_payload={"mint": "mint_test"},
                normalized_token_id="tok_test",
                status="normalized",
            )
            backtest = BacktestRun(
                id=new_id("bt"),
                created_at=utc_now(),
                profile="balanced",
                risk_tolerance="medium",
                tokens_replayed=1,
                paper_buys=1,
                skips=0,
                wins=1,
                losses=0,
                win_rate_pct=100,
                estimated_pnl_sol=0.01,
                max_drawdown_sol=0,
                profit_factor=0,
                pnl_curve=[0, 0.01],
                trades=[{"symbol": "ARC", "decision": "buy"}],
            )

            storage.save_source_event(source_event)
            storage.save_backtest_run(backtest)

            self.assertEqual(storage.load_source_events()[0].raw_payload["mint"], "mint_test")
            self.assertEqual(storage.load_backtest_runs()[0].estimated_pnl_sol, 0.01)

    def test_storage_round_trip_research_records(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "test.db"))
            now = utc_now()
            storage.save_price_observation(PriceObservation(id="px_test", source="mock", mint="mint_test", observed_at=now, price=0.00003, price_source="direct", confidence=0.9, accepted=True, token_id="tok_test"))
            storage.save_strategy_decision(StrategyDecisionRecord(id="dec_test", token_id="tok_test", mint="mint_test", created_at=now, engine_version="strategy-v2", profile="balanced", score=80, allowed=True, action="paper_buy", reason="ok", risk_reason="passed"))
            storage.save_trade_session(TradeSession(id="ses_test", token_id="tok_test", mint="mint_test", symbol="ARC", strategy_profile="balanced", status="opened", opened_at=now))

            self.assertEqual(storage.count_price_observations(), 1)
            self.assertEqual(storage.load_price_observations()[0].token_id, "tok_test")
            self.assertEqual(storage.count_strategy_decisions(), 1)
            self.assertEqual(storage.count_trade_sessions(), 1)

    def test_pumpportal_new_token_normalization(self) -> None:
        payload = {
            "txType": "create",
            "mint": "Mint111111111111111111111111111111111111111",
            "name": "Arc Token",
            "symbol": "ARC",
            "uri": "https://example.com/metadata.json",
            "traderPublicKey": "Creator1111111111111111111111111111111111",
            "bondingCurveKey": "Curve111111111111111111111111111111111111",
            "initialBuy": 1.5,
            "marketCapSol": 42,
            "creatorHoldPct": 7.5,
        }

        token = normalize_pumpportal_new_token(payload, utc_now())

        self.assertIsNotNone(token)
        assert token is not None
        self.assertEqual(token.symbol, "ARC")
        self.assertEqual(token.mint, payload["mint"])
        self.assertGreaterEqual(token.metadata_score, 0.9)
        self.assertGreater(token.buy_velocity, 0.0)
        self.assertEqual(token.creator_hold_pct, 7.5)

    def test_pumpportal_new_token_prefers_market_cap_price_over_virtual_ratio(self) -> None:
        token = normalize_pumpportal_new_token(
            {
                "txType": "create",
                "mint": "Mint111",
                "symbol": "ARC",
                "name": "Arc Token",
                "marketCapSol": 30,
                "vSolInBondingCurve": 30,
                "vTokensInBondingCurve": 1_000_000_000,
            },
            utc_now(),
        )

        self.assertIsNotNone(token)
        assert token is not None
        self.assertAlmostEqual(token.current_price or 0, 0.00003)

    def test_pumpportal_normalization_rejects_missing_mint(self) -> None:
        token = normalize_pumpportal_new_token({"txType": "create", "symbol": "ARC"}, utc_now())
        self.assertIsNone(token)

    def test_pumpportal_trade_normalization_updates_observed_price(self) -> None:
        event = normalize_pumpportal_trade(
            {"txType": "buy", "mint": "Mint111", "marketCapSol": 50, "solAmount": 0.4},
            utc_now(),
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.kind, "trade")
        self.assertEqual(event.mint, "Mint111")
        self.assertGreater(event.observed_price or 0, 0)

    def test_price_pipeline_uses_numeric_string_after_invalid_direct_price_alias(self) -> None:
        candidate = PricePipeline.from_payload({"price": "not-a-number", "priceSol": "0.000042"})

        self.assertEqual(candidate.source, "direct")
        self.assertAlmostEqual(candidate.price or 0, 0.000042)

    def test_pumpportal_new_token_uses_numeric_string_after_invalid_aliases(self) -> None:
        token = normalize_pumpportal_new_token(
            {
                "txType": "create",
                "mint": "Mint111",
                "symbol": "ARC",
                "name": "Arc Token",
                "initialBuy": "not-a-number",
                "initialBuySol": "2.5",
                "marketCapSol": "not-a-number",
                "marketCap": "42",
                "creatorHoldPct": "not-a-number",
                "creator_hold_pct": "7.5",
            },
            utc_now(),
        )

        self.assertIsNotNone(token)
        assert token is not None
        self.assertEqual(token.initial_buy_sol, 2.5)
        self.assertEqual(token.market_cap_sol, 42.0)
        self.assertEqual(token.creator_hold_pct, 7.5)
        self.assertAlmostEqual(token.current_price or 0, 0.000042)

    def test_pumpportal_trade_uses_numeric_string_after_invalid_sol_amount_alias(self) -> None:
        event = normalize_pumpportal_trade(
            {"txType": "buy", "mint": "Mint111", "solAmount": "not-a-number", "sol_amount": "0.4"},
            utc_now(),
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.sol_amount, 0.4)

    def test_sources_has_no_independent_numeric_parser(self) -> None:
        sources_path = Path(sources_module.__file__ or "")
        module = ast.parse(sources_path.read_text(encoding="utf-8"))
        functions = [node.name for node in module.body if isinstance(node, ast.FunctionDef)]

        self.assertNotIn("numeric", functions)
        self.assertIs(sources_module.numeric, price_pipeline_numeric)

    def test_pumpportal_launch_stream_uses_public_url_without_api_key(self) -> None:
        source = PumpPortalLaunchSource(
            ws_url="wss://pumpportal.fun/api/data?api-key=secret-key&foo=bar",
            max_trade_subscriptions=20,
        )

        self.assertEqual(source.launch_ws_url(), "wss://pumpportal.fun/api/data?foo=bar")

    def test_pumpfun_report_includes_creator_performance_reputation(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            for index, pnl in enumerate([0.01, 0.02, -0.03]):
                token = self.make_token()
                token.id = f"tok_creator_perf_{index}"
                token.mint = f"MintCreatorPerf{index}"
                token.creator = "CreatorPerf"
                state.storage.save_token(token)
                state.storage.save_trade(
                    TradeRecord(
                        id=f"trd_creator_perf_{index}",
                        token_id=token.id,
                        mode="paper",
                        strategy_profile="balanced",
                        entry_price=0.00001,
                        exit_price=0.00002,
                        amount_sol=0.1,
                        pnl_sol=pnl,
                        entry_reason="creator test",
                        exit_reason="creator exit",
                        opened_at=now,
                        closed_at=now,
                    )
                )
            weak = self.make_token()
            weak.id = "tok_creator_weak"
            weak.mint = "MintCreatorWeak"
            weak.creator = "CreatorWeak"
            state.storage.save_token(weak)
            state.storage.save_trade(
                TradeRecord(
                    id="trd_creator_weak",
                    token_id=weak.id,
                    mode="paper",
                    strategy_profile="balanced",
                    entry_price=0.00001,
                    exit_price=0.000005,
                    amount_sol=0.1,
                    pnl_sol=-0.01,
                    entry_reason="weak",
                    exit_reason="bad price",
                    opened_at=now,
                    closed_at=now,
                )
            )
            state.label_trade("tok_creator_weak", "bad_price_data")

            report = state.pumpfun_report()
            by_creator = {row["creator"]: row for row in report["creator_performance"]}

            self.assertIn("CreatorPerf", by_creator)
            self.assertEqual(by_creator["CreatorPerf"]["launches"], 3)
            self.assertEqual(by_creator["CreatorPerf"]["closed_trades"], 3)
            self.assertEqual(by_creator["CreatorPerf"]["wins"], 2)
            self.assertEqual(by_creator["CreatorPerf"]["losses"], 1)
            self.assertEqual(by_creator["CreatorPerf"]["win_rate_pct"], 66)
            self.assertEqual(by_creator["CreatorWeak"]["reputation"], "exclude_or_review")
            self.assertEqual(by_creator["CreatorWeak"]["labels"]["bad_price_data"], 1)

    def test_observed_trade_rebases_bad_entry_price_instead_of_fantasy_pnl(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.mint = "Mint111"
            token.status = TokenStatus.PAPER_BOUGHT
            token.entry_price = 0.000001
            token.current_price = 0.000001
            token.amount_sol = 0.1
            token.fee_paid_sol = 0.00025
            state.tokens.appendleft(token)
            event = normalize_pumpportal_trade({"txType": "buy", "mint": "Mint111", "marketCapSol": 30}, utc_now())
            assert event is not None

            state.apply_observed_trade(event)

            self.assertEqual(token.price_source, "observed_rebased")
            self.assertLess(abs(token.pnl_sol or 0), 0.001)
            self.assertAlmostEqual(token.entry_price or 0, event.observed_price or 0)

    def test_observed_trade_does_not_mutate_sold_position_pnl(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.mint = "Mint111"
            token.status = TokenStatus.PAPER_SOLD
            token.entry_price = 0.00003
            token.current_price = 0.00004
            token.exit_price = 0.00004
            token.amount_sol = 0.1
            token.pnl_sol = 0.033
            state.tokens.appendleft(token)
            event = normalize_pumpportal_trade({"txType": "sell", "mint": "Mint111", "marketCapSol": 10}, utc_now())
            assert event is not None

            state.apply_observed_trade(event)

            self.assertEqual(token.pnl_sol, 0.033)
            self.assertEqual(token.current_price, 0.00004)
            self.assertEqual(token.observed_price_updates, 0)

    def test_price_pipeline_rejects_low_confidence_virtual_reserve_price(self) -> None:
        observation = PricePipeline().observe(
            {
                "mint": "Mint111",
                "vSolInBondingCurve": 30,
                "vTokensInBondingCurve": 1_000_000_000,
            },
            mint="Mint111",
            settings=BotSettings(min_price_confidence=0.45),
        )

        self.assertFalse(observation.accepted)
        self.assertIn("confidence", observation.reason)

    def test_backtest_counts_fee_only_trade_as_scratch(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.status = TokenStatus.PAPER_SOLD
            token.score = 95
            token.pnl_sol = -0.0005
            state.tokens.appendleft(token)

            run = state.replay_backtest(limit=1)

            self.assertEqual(run.scratches, 1)
            self.assertEqual(run.losses, 0)
            self.assertEqual(run.win_rate_pct, 0)

    def test_replay_uses_launch_time_age_for_stored_tokens(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.detected_at = utc_now() - timedelta(minutes=15)
            token.age_seconds = 900
            token.status = TokenStatus.PAPER_SOLD
            token.score = 95
            token.pnl_sol = 0.01
            state.tokens.appendleft(token)

            run = state.replay_backtest(limit=1)

            self.assertEqual(run.paper_buys, 1)
            self.assertEqual(run.skips, 0)
            self.assertEqual(run.trades[0]["decision"], "buy")
            self.assertEqual(token.age_seconds, 900)

    def test_backtest_runs_have_deterministic_fingerprints(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.status = TokenStatus.PAPER_SOLD
            token.score = 95
            token.pnl_sol = 0.01
            state.tokens.appendleft(token)

            first = state.replay_backtest(limit=1)
            second = state.replay_backtest(limit=1)

            self.assertRegex(first.determinism_fingerprint, r"^[0-9a-f]{16}$")
            self.assertEqual(first.determinism_fingerprint, second.determinism_fingerprint)
            self.assertEqual(state.storage.load_backtest_runs(1)[0].determinism_fingerprint, second.determinism_fingerprint)

    def test_raw_replay_fingerprint_ignores_temporary_token_ids(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            received_at = utc_now()
            state.storage.save_source_event(
                SourceEvent(
                    id="src_raw_fp",
                    source="fixture",
                    received_at=received_at,
                    raw_payload={"mint": "MintRawFingerprint", "symbol": "RAWFP", "creator": "CreatorRaw"},
                    normalized_token_id=None,
                    status="normalized",
                )
            )

            first = state.replay_raw_source_events(limit=1)
            second = state.replay_raw_source_events(limit=1)

            self.assertRegex(first.determinism_fingerprint, r"^[0-9a-f]{16}$")
            self.assertEqual(first.determinism_fingerprint, second.determinism_fingerprint)

    def test_data_integrity_and_price_v3_reports(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.score = 88
            state.storage.save_token(token)
            state.storage.save_price_observation(
                PriceObservation(id="px_test", source="pumpportal", mint=token.mint, observed_at=utc_now(), price=0.00002, price_source="direct", confidence=0.9, accepted=True, token_id=token.id)
            )
            state.storage.save_source_event(SourceEvent(id="src_test", source="pumpportal", received_at=utc_now(), raw_payload={"mint": token.mint}, normalized_token_id=token.id, status="normalized"))

            integrity = state.data_integrity_report()
            price = state.price_diagnostics()

            self.assertIn("determinism_fingerprint", integrity)
            self.assertGreaterEqual(integrity["replay_confidence"]["score"], 0)
            self.assertEqual(price["engine_version"], "price-v3")
            self.assertEqual(price["accepted"], 1)

    def test_backtest_v3_and_trade_review_detail(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.status = TokenStatus.PAPER_SOLD
            token.score = 92
            token.pnl_sol = 0.01
            token.exit_reason = "take profit"
            state.storage.save_token(token)
            state.storage.save_trade(
                TradeRecord(
                    id="trd_test",
                    token_id=token.id,
                    mode="paper",
                    strategy_profile="balanced",
                    entry_price=0.00001,
                    exit_price=0.00002,
                    amount_sol=0.1,
                    pnl_sol=0.01,
                    entry_reason="test",
                    exit_reason="take profit",
                    opened_at=utc_now(),
                    closed_at=utc_now(),
                )
            )

            suite = state.backtest_v3(limit=5)
            detail = state.trade_review_detail(token.id)
            safety = state.safety_status()

            self.assertEqual(suite["engine_version"], "backtest-v3")
            self.assertIn("runs", suite)
            self.assertEqual(detail["trade"]["id"], "trd_test")
            self.assertTrue(safety["paper_only"])

    def test_readiness_empty_state_needs_data(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            readiness = state.readiness_status()

            self.assertEqual(readiness["engine_version"], "readiness-v1")
            self.assertEqual(readiness["status"], "not_enough_data")
            self.assertTrue(readiness["paper_only"])
            self.assertTrue(readiness["entries_allowed"])
            self.assertEqual(readiness["strategy_promotion"]["status"], "not_enough_data")
            self.assertFalse(readiness["strategy_promotion"]["can_promote"])

    def test_readiness_strong_dataset_is_ready(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)

            readiness = state.readiness_status()

            self.assertEqual(readiness["status"], "ready")
            self.assertGreaterEqual(readiness["score"], 75)
            self.assertTrue(all(gate["status"] != "fail" for gate in readiness["gates"]))
            self.assertTrue(readiness["strategy_promotion"]["can_promote"])
            self.assertEqual(readiness["strategy_promotion"]["status"], "eligible")
            self.assertIn("out_of_sample", {gate["id"] for gate in readiness["strategy_promotion"]["gates"]})
            self.assertFalse(readiness["strategy_promotion"]["out_of_sample"]["collapse_warning"])

    def test_strategy_promotion_blocks_when_out_of_sample_collapses(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            candidates = [
                token
                for token in state.storage.load_all_tokens(100)
                if token.status in {TokenStatus.SKIPPED, TokenStatus.PAPER_SOLD, TokenStatus.DETECTED, TokenStatus.ANALYZING}
            ]
            self.assertEqual(len(candidates), 30)
            for token in candidates[15:]:
                token.pnl_sol = -0.02
                token.exit_reason = "validation collapse"
                state.storage.save_token(token)

            readiness = state.readiness_status()
            promotion = readiness["strategy_promotion"]
            gate_status = {gate["id"]: gate["status"] for gate in promotion["gates"]}

            self.assertFalse(promotion["can_promote"])
            self.assertEqual(gate_status["out_of_sample"], "fail")
            self.assertEqual(gate_status["strategy_drift"], "fail")
            self.assertTrue(promotion["out_of_sample"]["collapse_warning"])
            self.assertTrue(any("Validation replay" in blocker for blocker in promotion["blockers"]))

    def test_readiness_source_failure_blocks_after_enough_data(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state, source_connected=False)

            readiness = state.readiness_status()
            source_gate = next(gate for gate in readiness["gates"] if gate["id"] == "source_health")

            self.assertEqual(readiness["status"], "blocked")
            self.assertEqual(source_gate["status"], "fail")
            self.assertFalse(readiness["strategy_promotion"]["can_promote"])
            self.assertIn("Source trust must be trusted before strategy promotion.", readiness["strategy_promotion"]["blockers"])

    def test_readiness_halt_waits_for_evidence_then_blocks_entries(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.settings.halt_on_low_readiness = True
            state.settings.min_readiness_score = 70
            state.settings.max_trades_per_hour_enabled = False

            self.assertIsNone(state.evaluate_session_guards(self.make_token()))

            self.seed_readiness_dataset(state, source_connected=False)
            guard = state.evaluate_session_guards(self.make_token())
            safety = state.safety_status()

            self.assertIsNotNone(guard)
            self.assertIn("readiness halt active", guard or "")
            self.assertIn("readiness halt active", ", ".join(safety["stop_reasons"]))

    def test_schema_experiments_labels_and_presets_round_trip(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "test.db"))
            now = utc_now()
            storage.save_experiment_run(ExperimentRun(id="exp_test", name="Experiment", created_at=now, settings_version_id="set_test", profile="balanced", replay_source="backtest_v3", result={"ok": True}, fingerprint="abc"))
            storage.save_trade_label(TradeLabel(id="lbl_test", token_id="tok_test", trade_id="trd_test", label="good_entry", created_at=now))
            storage.save_strategy_preset(StrategyPreset(id="strat_test", name="My preset", created_at=now, settings={"score_threshold": 60}))

            self.assertTrue(storage.schema_status()["ok"])
            self.assertEqual(storage.count_experiment_runs(), 1)
            self.assertEqual(storage.load_trade_labels()[0].label, "good_entry")
            self.assertEqual(storage.load_strategy_presets()[0].name, "My preset")

    def test_trade_review_queue_groups_unlabeled_problem_trades(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            trades = [
                ("tok_review_win", "trd_review_win", 0.01, 60, 0.9),
                ("tok_review_loss", "trd_review_loss", -0.02, 90, 0.9),
                ("tok_review_bad_price", "trd_review_bad_price", 0.005, 45, 0.4),
                ("tok_review_long", "trd_review_long", 0.002, 900, 0.9),
            ]
            for token_id, trade_id, pnl, hold, confidence in trades:
                state.storage.save_trade(
                    TradeRecord(
                        id=trade_id,
                        token_id=token_id,
                        mode="paper",
                        strategy_profile="balanced",
                        entry_price=0.00001,
                        exit_price=0.00002,
                        amount_sol=0.1,
                        pnl_sol=pnl,
                        entry_reason="review entry",
                        exit_reason="review exit",
                        opened_at=now - timedelta(minutes=5),
                        closed_at=now,
                        hold_duration_seconds=hold,
                        source_price_confidence=confidence,
                    )
                )
                if token_id != "tok_review_long":
                    state.storage.save_strategy_decision(
                        StrategyDecisionRecord(
                            id=f"dec_{token_id}",
                            token_id=token_id,
                            mint=f"Mint{token_id}",
                            created_at=now,
                            engine_version="strategy-v3",
                            profile="balanced",
                            score=80,
                            allowed=True,
                            action="paper_buy",
                            reason="review",
                            risk_reason="ok",
                        )
                    )
            state.storage.save_price_observation(
                PriceObservation(
                    id="px_review_rejected",
                    source="pumpportal",
                    mint="MintBadPrice",
                    observed_at=now,
                    price=None,
                    price_source="direct",
                    confidence=0.2,
                    accepted=False,
                    reason="impossible jump",
                    token_id="tok_review_bad_price",
                )
            )
            state.label_trade("tok_review_win", "good_entry")
            state.label_trade("tok_review_bad_price", "ignore_from_tuning")

            queue = state.trade_review_queue()
            by_id = {item["id"]: item for item in queue["queues"]}

            self.assertEqual(queue["total_closed"], 4)
            self.assertEqual(queue["labeled"], 2)
            self.assertEqual(queue["unlabeled"], 2)
            self.assertEqual(queue["label_counts"]["good_entry"], 1)
            self.assertEqual(by_id["losses"]["count"], 1)
            self.assertEqual(by_id["bad_price_data"]["count"], 1)
            self.assertEqual(by_id["long_holds"]["count"], 1)
            self.assertEqual(by_id["missing_decision"]["count"], 1)
            self.assertEqual(by_id["ignored_from_tuning"]["count"], 1)
            self.assertEqual(queue["next_queue_id"], "unlabeled")
            self.assertEqual(queue["next_token_id"], "tok_review_loss")
            self.assertIn("tok_review_loss", by_id["unlabeled"]["sample_token_ids"])

            detail = state.trade_review_detail("tok_review_bad_price")
            workflow = detail["review_workflow"]
            checklist = {item["id"]: item for item in workflow["checklist"]}

            self.assertEqual(workflow["selected_label"], "ignore_from_tuning")
            self.assertIn("bad_price_data", workflow["suggested_labels"])
            self.assertEqual(checklist["price_observations"]["status"], "warn")
            self.assertEqual(checklist["decisions"]["status"], "pass")
            self.assertEqual(workflow["total_closed"], 4)

    def test_live_request_storage_and_safety_boundary(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "test.db"))
            request = LiveExecutionRequest(
                id="live_test",
                created_at=utc_now(),
                action="buy",
                mint="Mint111",
                amount_sol=0.01,
                status="blocked",
                reason="test boundary",
            )

            storage.save_live_execution_request(request)

            loaded = storage.load_live_execution_requests()[0]
            self.assertEqual(loaded.id, "live_test")
            self.assertEqual(storage.load_live_execution_request("live_test").mint, "Mint111")
            self.assertEqual(storage.count_live_execution_requests(), 1)

    def test_watchdog_and_manual_live_request_are_blocked(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            state.start()
            state.tick()
            request = state.create_manual_live_request("buy", "Mint111", 0.01)
            watchdog = state.watchdog_status()
            safety = state.safety_status()

            self.assertEqual(watchdog["status"], "ok")
            self.assertEqual(request["status"], "blocked")
            self.assertTrue(safety["paper_only"])
            self.assertFalse(safety["manual_live_ready"])

    def test_watchdog_tick_telemetry_defaults_before_first_completed_tick(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            watchdog = state.watchdog_status()

            self.assertEqual(watchdog["last_tick_tokens_seen"], 0)
            self.assertEqual(watchdog["last_tick_active_tokens"], 0)
            self.assertEqual(watchdog["last_tick_closed"], 0)
            self.assertIsNone(watchdog["last_tick_completed_at"])

    def test_tick_publishes_exact_work_telemetry_for_mixed_tokens(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.settings.max_position_ticks = 1
            inactive = self.make_token()
            inactive.id = "tok_inactive"
            inactive.status = TokenStatus.SKIPPED
            pending = self.make_token()
            pending.id = "tok_pending"
            pending.status = TokenStatus.BUYING
            closing = self.make_token()
            closing.id = "tok_closing"
            closing.status = TokenStatus.MONITORING
            closing.entry_price = 0.00001
            closing.current_price = 0.00001
            closing.amount_sol = 0.1
            closing.opened_at = utc_now()
            state.tokens.extend((inactive, pending, closing))

            state.tick()

            watchdog = state.watchdog_status()
            self.assertEqual(watchdog["last_tick_tokens_seen"], 3)
            self.assertEqual(watchdog["last_tick_active_tokens"], 2)
            self.assertEqual(watchdog["last_tick_closed"], 1)
            self.assertEqual(closing.status, TokenStatus.PAPER_SOLD)
            self.assertEqual(closing.exit_reason, "max position ticks")
            self.assertIsNotNone(watchdog["last_tick_completed_at"])
            datetime.fromisoformat(str(watchdog["last_tick_completed_at"]))

    def test_tick_failure_keeps_last_completed_telemetry_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.tick()
            completed = state.watchdog_status()
            active = self.make_token()
            active.status = TokenStatus.BUYING
            state.tokens.append(active)

            def fail_recalculate() -> None:
                raise RuntimeError("injected recalculate failure")

            state.recalculate_stats = fail_recalculate  # type: ignore[method-assign]

            with self.assertRaisesRegex(RuntimeError, "injected recalculate failure"):
                state.tick()

            watchdog = state.watchdog_status()
            self.assertEqual(watchdog["last_tick_tokens_seen"], completed["last_tick_tokens_seen"])
            self.assertEqual(watchdog["last_tick_active_tokens"], completed["last_tick_active_tokens"])
            self.assertEqual(watchdog["last_tick_closed"], completed["last_tick_closed"])
            self.assertEqual(watchdog["last_tick_completed_at"], completed["last_tick_completed_at"])

    def test_snapshot_failure_keeps_last_completed_telemetry_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.tick()
            completed = state.watchdog_status()
            active = self.make_token()
            active.status = TokenStatus.BUYING
            state.tokens.append(active)

            def fail_snapshot() -> object:
                raise RuntimeError("injected snapshot failure")

            state.snapshot = fail_snapshot  # type: ignore[method-assign]

            with self.assertRaisesRegex(RuntimeError, "injected snapshot failure"):
                state.tick()

            watchdog = state.watchdog_status()
            self.assertEqual(watchdog["last_tick_tokens_seen"], completed["last_tick_tokens_seen"])
            self.assertEqual(watchdog["last_tick_active_tokens"], completed["last_tick_active_tokens"])
            self.assertEqual(watchdog["last_tick_closed"], completed["last_tick_closed"])
            self.assertEqual(watchdog["last_tick_completed_at"], completed["last_tick_completed_at"])

    def test_snapshot_default_still_hydrates_tokens(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            state.storage.save_token(token)
            calls: list[bool] = []
            original_snapshot_tokens = state._snapshot_tokens

            def record_snapshot_tokens() -> list[TokenSignal]:
                calls.append(True)
                return original_snapshot_tokens()

            state._snapshot_tokens = record_snapshot_tokens  # type: ignore[method-assign]

            default_snapshot = state.snapshot()
            explicit_snapshot = state.snapshot(include_tokens=True)

            self.assertEqual(default_snapshot.to_dict(), explicit_snapshot.to_dict())
            self.assertEqual(calls, [True, True])

    def test_snapshot_can_skip_token_hydration_without_changing_other_fields(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            state.storage.save_token(token)
            full_payload = state.snapshot().to_dict()

            def fail_token_hydration(*args: object, **kwargs: object) -> list[TokenSignal]:
                raise AssertionError("token hydration must be skipped")

            state._snapshot_tokens = fail_token_hydration  # type: ignore[method-assign]
            state.storage.load_tokens = fail_token_hydration  # type: ignore[method-assign]

            compact_payload = state.snapshot(include_tokens=False).to_dict()
            expected_payload = dict(full_payload)
            expected_payload["tokens"] = []

            self.assertEqual(compact_payload, expected_payload)

    def test_tick_can_complete_without_building_a_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            state.tokens.append(token)
            recalculate_calls: list[bool] = []
            original_recalculate_stats = state.recalculate_stats

            def record_recalculate_stats() -> None:
                recalculate_calls.append(True)
                original_recalculate_stats()

            def fail_snapshot() -> object:
                raise AssertionError("snapshot must not be built")

            state.recalculate_stats = record_recalculate_stats  # type: ignore[method-assign]
            state.snapshot = fail_snapshot  # type: ignore[method-assign]

            result = state.tick(build_snapshot=False)

            self.assertIsNone(result)
            self.assertEqual(recalculate_calls, [True])
            self.assertTrue(any(saved.id == token.id for saved in state.storage.load_all_tokens(20)))
            self.assertIsNotNone(state.watchdog_status()["last_tick_completed_at"])

    def test_manual_live_request_review_remains_audit_only(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            request = state.create_manual_live_request("sell", "Mint222", 0.02)
            reviewed = state.review_live_request(str(request["id"]), "rejected", "bad setup")
            loaded = state.storage.load_live_execution_request(str(request["id"]))

            self.assertEqual(reviewed["status"], "rejected")
            self.assertIsNotNone(reviewed["reviewed_at"])
            self.assertIn("without execution", reviewed["reason"])
            self.assertTrue(reviewed["payload"]["reviewed_without_execution"])
            self.assertTrue(reviewed["payload"]["paper_only_boundary"])
            self.assertEqual(loaded.status, "rejected")

    def test_live_wallet_balance_uses_backend_rpc_helper(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state._wallet_sol_balance = lambda wallet_public_key: {"wallet_public_key": wallet_public_key, "balance_sol": 0.123456789, "error": ""}  # type: ignore[method-assign]

            balance = state.live_wallet_balance("WalletBalance")

            self.assertEqual(balance["wallet_public_key"], "WalletBalance")
            self.assertEqual(balance["balance_sol"], 0.123456789)
            self.assertEqual(balance["error"], "")

    def test_live_fill_stamps_token_with_wallet_public_key(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.id = "tok_live_wallet"
            token.mint = "MintLiveWallet"
            state.storage.save_token(token)
            audit = LiveExecutionAudit(
                id="audit_live_wallet",
                created_at=utc_now(),
                updated_at=utc_now(),
                action="buy",
                mint="MintLiveWallet",
                amount="0.001",
                wallet_public_key="WalletLiveToken",
                signer_mode="browser_wallet",
                status="submitted",
                final_status="submitted",
            )

            state._record_live_fill(audit)
            loaded = next(item for item in state.storage.load_all_tokens() if item.id == "tok_live_wallet")

            self.assertEqual(loaded.wallet_public_key, "WalletLiveToken")

    def configure_live_caps(self, state: BotState, include_backup: bool = True) -> None:
        state.settings.live_max_trade_sol = 0.01
        state.settings.live_daily_loss_cap_sol = 0.05
        state.settings.live_wallet_exposure_cap_sol = 0.1
        state.settings.live_max_open_positions = 1
        state.settings.live_max_slippage_pct = 5
        state.settings.live_priority_fee_cap_sol = 0.0001
        state.settings.live_session_acknowledged = True
        state.storage.save_settings(state.settings)
        state.ensure_settings_version("settings save", list(state.LIVE_CAP_SETTING_KEYS))
        state.source_status.status = "connected"
        state.source_status.message = "healthy"
        state.source_status.last_event_at = utc_now()
        if include_backup:
            state.storage.create_backup_artifact()

    def seed_ready_source_soak_events(self, state: BotState) -> None:
        now = utc_now()
        state.source_status.status = "connected"
        state.source_status.last_event_at = now
        state.source_status.raw_events_seen = 120
        state.source_status.normalized_events = 120
        for index in range(100):
            mint = f"MintSoak{index:03d}"
            state.storage.save_source_event(
                SourceEvent(
                    id=f"src_pump_soak_{index}",
                    source="pumpportal",
                    received_at=now + timedelta(milliseconds=index),
                    raw_payload={"txType": "create", "mint": mint, "signature": f"SigSoak{index:03d}"},
                    normalized_token_id=f"tok_soak_{index}",
                    status="normalized",
                )
            )
        for index in range(20):
            mint = f"MintSoak{index:03d}"
            state.storage.save_source_event(
                SourceEvent(
                    id=f"src_direct_soak_{index}",
                    source="solana_logs",
                    received_at=now + timedelta(seconds=1, milliseconds=index),
                    raw_payload={
                        "result": {
                            "context": {"slot": 1000 + index},
                            "value": {
                                "signature": f"SigSoak{index:03d}",
                                "err": None,
                                "logs": [
                                    "Program log: Instruction: Create",
                                    f"Program log: mint {mint}",
                                    f"Program log: name=Token {index} symbol=SOAK uri=https://example.com/{index}.json creator=CreatorSoak{index:03d} bondingCurveKey=CurveSoak{index:03d}",
                                ],
                            },
                        }
                    },
                    status="raw",
                )
            )

    def test_alert_router_status_hides_telegram_secret_and_test_sends(self) -> None:
        sent: list[tuple[str, str, str]] = []
        router = AlertRouter(
            telegram_bot_token="secret-token",
            telegram_chat_id="12345",
            telegram_enabled=True,
            sender=lambda token, chat_id, text: (sent.append((token, chat_id, text)) or (True, "ok")),
        )

        status = router.status()
        result = router.test()

        self.assertTrue(status["telegram_configured"])
        self.assertNotIn("secret-token", json.dumps(status))
        self.assertEqual(result["status"], "sent")
        self.assertEqual(sent[0][0], "secret-token")
        self.assertIn("CryptoARC test alert", sent[0][2])

    def test_alert_router_throttles_duplicate_critical_events(self) -> None:
        sent: list[str] = []
        router = AlertRouter(
            telegram_bot_token="secret-token",
            telegram_chat_id="12345",
            telegram_enabled=True,
            min_interval_seconds=60,
            sender=lambda token, chat_id, text: (sent.append(text) or (True, "ok")),
        )

        first = router.alert_event("danger", "live", "Live kill switch enabled")
        second = router.alert_event("danger", "live", "Live kill switch enabled")

        self.assertEqual(first["status"], "sent")
        self.assertEqual(second["status"], "throttled")
        self.assertEqual(len(sent), 1)

    def test_bot_state_alerts_on_live_kill_switch_event(self) -> None:
        sent: list[str] = []
        router = AlertRouter(
            telegram_bot_token="secret-token",
            telegram_chat_id="12345",
            telegram_enabled=True,
            sender=lambda token, chat_id, text: (sent.append(text) or (True, "ok")),
        )
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"), alert_router=router)
            self.configure_live_caps(state)

            state.set_live_kill_switch(True, "operator panic stop")

            self.assertEqual(router.last_result["status"], "sent")
            self.assertTrue(any("kill switch" in message.lower() for message in sent))

    def test_live_status_blocks_without_env_caps_or_wallet(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            status = state.live_status(env_live_enabled=False)

            self.assertFalse(status["live_execution_available"])
            self.assertIn("LIVE_TRADING_ENABLED is false", status["blockers"])
            self.assertIn("no connected signer", status["blockers"])
            self.assertTrue(any("max_trade_sol" in blocker for blocker in status["blockers"]))

    def test_live_status_reports_future_signer_capabilities(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)

            browser = state.live_status(env_live_enabled=True, wallet_public_key="Wallet111")
            daemon = state.live_status(env_live_enabled=True, wallet_public_key="", signer_mode="local_signer_daemon")
            mode_ids = [item["id"] for item in browser["mode_visibility"]]
            mode_states = {item["id"]: item["state"] for item in browser["mode_visibility"]}

            self.assertFalse(browser["signer"]["can_unattended_sign"])
            self.assertFalse(browser["signer"]["supports_auto_sell"])
            self.assertFalse(browser["signer"]["supports_auto_buy"])
            self.assertIn("manual signing only", browser["signer"]["disabled_reason"].lower())
            self.assertEqual(browser["execution_backend"]["submit_path"], "browser_wallet_manual_signature")
            self.assertTrue(browser["execution_backend"]["implemented"])
            self.assertTrue(browser["execution_backend"]["manual_approval_required"])
            self.assertFalse(browser["execution_backend"]["unattended_submit_available"])
            self.assertEqual(mode_ids, ["paper", "shadow", "manual_live", "autonomous_live"])
            self.assertEqual(mode_states["manual_live"], "ready")
            self.assertEqual(mode_states["autonomous_live"], "blocked")
            self.assertTrue(any("backend is not armed" in blocker for blocker in next(item for item in browser["mode_visibility"] if item["id"] == "autonomous_live")["blockers"]))
            self.assertFalse(browser["auto_sell_available"])
            self.assertFalse(browser["auto_buy_available"])
            self.assertIn("entry", browser["autonomy"])
            self.assertIn("exit", browser["autonomy"])
            self.assertFalse(browser["autonomy"]["active_backend_matches"])
            self.assertFalse(browser["autonomy"]["override"]["available"])
            self.assertIn("autonomous live is disabled", " ".join(browser["autonomy_blockers"]).lower())
            self.assertFalse(daemon["signer"]["connected"])
            self.assertIn("unavailable", daemon["signer"]["disabled_reason"].lower())
            self.assertFalse(daemon["wallet_adapter"]["supports_auto_sell"])
            self.assertEqual(daemon["execution_backend"]["submit_path"], "localhost_signer_daemon")
            self.assertFalse(daemon["execution_backend"]["implemented"])

    def test_live_status_reuses_recent_readiness_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            calls = 0
            original_readiness = state.readiness_status

            def counted_readiness() -> dict[str, object]:
                nonlocal calls
                calls += 1
                return original_readiness()

            state.readiness_status = counted_readiness  # type: ignore[method-assign]

            first = state.live_status(True, "Wallet111", "browser_wallet")
            second = state.live_status(True, "Wallet111", "browser_wallet")

            self.assertEqual(first["readiness"]["engine_version"], "readiness-v1")
            self.assertEqual(second["readiness"]["engine_version"], "readiness-v1")
            self.assertEqual(calls, 1)

    def test_readiness_status_computes_execution_readiness_once(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            calls = 0
            original_execution = state._execution_readiness_status

            def counted_execution(*args: object, **kwargs: object) -> dict[str, object]:
                nonlocal calls
                calls += 1
                return original_execution(*args, **kwargs)

            state._execution_readiness_status = counted_execution  # type: ignore[method-assign]

            readiness = state.readiness_status()

            self.assertEqual(readiness["execution_readiness"]["mode"], "dry_run_to_shadow")
            self.assertEqual(calls, 1)

    def test_live_status_uses_readiness_execution_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            calls = 0
            original_execution = state._execution_readiness_status

            def counted_execution(*args: object, **kwargs: object) -> dict[str, object]:
                nonlocal calls
                calls += 1
                return original_execution(*args, **kwargs)

            state._execution_readiness_status = counted_execution  # type: ignore[method-assign]

            status = state.live_status(True, "Wallet111", "browser_wallet")

            self.assertEqual(status["execution_readiness"]["mode"], "dry_run_to_shadow")
            self.assertEqual(calls, 1)

    def test_live_status_reuses_wallet_metrics_for_blockers(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            calls = 0
            original_metrics = state._wallet_live_metrics

            def counted_metrics(wallet_public_key: str) -> dict[str, object]:
                nonlocal calls
                calls += 1
                return original_metrics(wallet_public_key)

            state._wallet_live_metrics = counted_metrics  # type: ignore[method-assign]

            status = state.live_status(True, "Wallet111", "browser_wallet")

            self.assertEqual(status["live_pnl"]["open_positions"], 0)
            self.assertEqual(calls, 1)

    def test_hot_wallet_import_lock_unlock_and_status(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            keypair = Keypair()

            imported = state.import_hot_wallet(str(keypair), "password123", "ops")
            locked = state.lock_hot_wallet()
            unlocked = state.unlock_hot_wallet("password123")

            self.assertTrue(imported["imported"])
            self.assertTrue(imported["unlocked"])
            self.assertEqual(imported["wallet_public_key"], str(keypair.pubkey()))
            self.assertFalse(locked["unlocked"])
            self.assertTrue(unlocked["unlocked"])
            self.assertEqual(state.signer_status("local_hot_wallet", "")["wallet_public_key"], str(keypair.pubkey()))

    def test_hot_wallet_status_reports_do_not_expose_storage_or_key_material(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.import_hot_wallet(str(Keypair()), "password123", "ops")

            payloads = [
                state.hot_wallet_status(),
                state.live_status(True, signer_mode="local_hot_wallet")["hot_wallet"],
                state.pilot_readiness_report(signer_mode="local_hot_wallet")["evidence"]["live_status"]["hot_wallet"],
            ]
            forbidden_keys = {
                "file_path",
                "path",
                "private_key",
                "private_key_bytes",
                "secret",
                "seed",
                "mnemonic",
                "salt_b64",
                "nonce_b64",
                "ciphertext_b64",
                "mac_b64",
            }

            def assert_public_hot_wallet_status(payload: dict[str, object]) -> None:
                keys = {str(key) for key in payload.keys()}
                self.assertFalse(keys & forbidden_keys)
                self.assertEqual(payload["storage_scope"], "local_encrypted_sidecar")
                self.assertEqual(payload["recovery_note"], "Hot wallet sidecar is local-only and is not embedded in database backup artifacts.")

            for payload in payloads:
                assert_public_hot_wallet_status(payload)

    def test_hot_wallet_restore_without_sidecar_clears_stale_settings_metadata(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.db"
            state = BotState(database_path=str(database_path))
            imported = state.import_hot_wallet(str(Keypair()), "password123", "ops")
            sidecar = database_path.with_suffix(".hotwallet.json")
            sidecar.unlink()

            restored = BotState(database_path=str(database_path))
            status = restored.hot_wallet_status()

            self.assertFalse(status["imported"])
            self.assertFalse(restored.settings.live_hot_wallet_enabled)
            self.assertEqual(restored.settings.live_hot_wallet_public_key, "")
            self.assertEqual(restored.settings.live_hot_wallet_label, "")
            self.assertNotEqual(imported["wallet_public_key"], restored.settings.live_hot_wallet_public_key)

    def test_hot_wallet_restore_without_sidecar_disarms_stale_local_backend(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.db"
            state = BotState(database_path=str(database_path))
            self.configure_live_caps(state)
            state.settings.autonomous_live_enabled = True
            state.storage.save_settings(state.settings)
            imported = state.import_hot_wallet(str(Keypair()), "password123", "ops")
            state.unlock_hot_wallet("password123")
            state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            database_path.with_suffix(".hotwallet.json").unlink()

            restored = BotState(database_path=str(database_path))
            live_status = restored.live_status(True, signer_mode="local_hot_wallet")

            self.assertFalse(restored.settings.live_active_backend_armed)
            self.assertEqual(restored.settings.live_active_wallet_public_key, "")
            self.assertFalse(live_status["active_backend"]["armed"])
            self.assertNotEqual(imported["wallet_public_key"], live_status["active_backend"]["wallet_public_key"])
            self.assertFalse(live_status["autonomy"]["active_backend_matches"])

    def test_hot_wallet_restore_without_sidecar_persists_disarmed_backend(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.db"
            state = BotState(database_path=str(database_path))
            self.configure_live_caps(state)
            state.settings.autonomous_live_enabled = True
            state.storage.save_settings(state.settings)
            state.import_hot_wallet(str(Keypair()), "password123", "ops")
            state.unlock_hot_wallet("password123")
            state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            database_path.with_suffix(".hotwallet.json").unlink()

            restored = BotState(database_path=str(database_path))
            persisted = restored.storage.load_settings()

            self.assertFalse(restored.settings.live_active_backend_armed)
            self.assertFalse(persisted.live_active_backend_armed)
            self.assertEqual(persisted.live_active_wallet_public_key, "")
            self.assertFalse(persisted.live_hot_wallet_enabled)
            self.assertEqual(persisted.live_hot_wallet_public_key, "")

    def test_backup_restore_without_sidecar_disarms_stale_local_backend(self) -> None:
        with TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.db"
            source = BotState(database_path=str(source_path))
            self.configure_live_caps(source)
            source.settings.autonomous_live_enabled = True
            source.storage.save_settings(source.settings)
            imported = source.import_hot_wallet(str(Keypair()), "password123", "ops")
            source.unlock_hot_wallet("password123")
            source.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            artifact = source.storage.create_backup_artifact()

            restored = BotState(database_path=str(Path(directory) / "restored.db"))
            restored.settings.kill_switch_enabled = True
            restored.confirm_restore_artifact(artifact)
            live_status = restored.live_status(True, signer_mode="local_hot_wallet")

            self.assertFalse(restored.settings.live_active_backend_armed)
            self.assertEqual(restored.settings.live_active_wallet_public_key, "")
            self.assertFalse(live_status["active_backend"]["armed"])
            self.assertNotEqual(imported["wallet_public_key"], live_status["active_backend"]["wallet_public_key"])
            self.assertFalse(live_status["autonomy"]["active_backend_matches"])

    def test_hot_wallet_backend_can_be_armed_for_autonomy(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.import_hot_wallet(str(Keypair()), "password123", "ops")

            armed = state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            live_status = state.live_status(True, signer_mode="local_hot_wallet")

            self.assertTrue(armed["armed"])
            self.assertTrue(armed["live_status"]["autonomy"]["override"]["local_auth_enabled"])
            self.assertTrue(live_status["active_backend"]["armed"])
            self.assertEqual(live_status["active_backend"]["mode"], "local_hot_wallet")
            self.assertTrue(live_status["autonomy"]["active_backend_matches"])
            self.assertEqual(live_status["execution_backend"]["submit_path"], "encrypted_local_hot_wallet")
            self.assertTrue(live_status["execution_backend"]["implemented"])
            self.assertTrue(live_status["execution_backend"]["local_only"])
            self.assertTrue(live_status["execution_backend"]["unattended_submit_available"])
            self.assertTrue(live_status["execution_backend"]["can_submit_now"])

    def test_live_backend_arm_local_auth_is_keyword_only(self) -> None:
        parameter = inspect.signature(BotState.arm_live_backend).parameters.get("local_auth_enabled")

        self.assertIsNotNone(parameter)
        self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_live_backend_arm_requires_local_auth_without_mutation(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.import_hot_wallet(str(Keypair()), "password123", "ops")
            initial_mode = state.settings.live_signer_mode

            with self.assertRaisesRegex(ValueError, "local auth"):
                state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=False)

            self.assertFalse(state.settings.live_active_backend_armed)
            self.assertEqual(state.settings.live_active_wallet_public_key, "")
            self.assertEqual(state.settings.live_signer_mode, initial_mode)
            self.assertEqual(state.storage.count_live_sessions(), 0)

    def test_startup_live_auth_policy_disarms_persisted_backend(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.db"
            state = BotState(database_path=str(database_path))
            state.settings.live_signer_mode = "browser_wallet"
            state.settings.live_active_backend_armed = True
            state.settings.live_active_wallet_public_key = "WalletPersisted"
            state.storage.save_settings(state.settings)
            restarted = BotState(database_path=str(database_path))
            policy = getattr(restarted, "enforce_live_auth_startup_policy", None)

            self.assertIsNotNone(policy)
            result = policy(False)

            persisted = restarted.storage.load_settings()
            self.assertTrue(result["disarmed"])
            self.assertFalse(restarted.settings.live_active_backend_armed)
            self.assertEqual(restarted.settings.live_active_wallet_public_key, "")
            self.assertFalse(persisted.live_active_backend_armed)
            self.assertEqual(persisted.live_active_wallet_public_key, "")
            self.assertTrue(any(event.level == "warning" and "local auth" in event.message.lower() for event in restarted.events))

    def test_stale_balance_verification_blocks_autonomy(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.autonomous_live_enabled = True
            state.settings.source_stale_seconds = 30
            wallet = state.import_hot_wallet(str(Keypair()), "password123", "ops")["wallet_public_key"]
            state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="livepos_stale_balance",
                    created_at=utc_now() - timedelta(minutes=10),
                    updated_at=utc_now() - timedelta(minutes=10),
                    mint="MintStaleBalance",
                    wallet_public_key=str(wallet),
                    status="open",
                    token_balance=10.0,
                    cost_basis_sol=0.001,
                    reconciliation_status="matched",
                    reconciliation={"wallet_public_key": str(wallet), "mint": "MintStaleBalance", "token_balance": 10.0, "error": "", "checked_at": (utc_now() - timedelta(minutes=10)).isoformat()},
                    balance_verified_at=utc_now() - timedelta(minutes=10),
                )
            )

            status = state.live_status(True, signer_mode="local_hot_wallet")

            self.assertGreater(status["live_pnl"]["open_positions"], 0)
            self.assertTrue(any("stale token-balance verification" in blocker for blocker in status["autonomy_blockers"]))
            self.assertFalse(status["autonomy"]["exit"]["available"])

    def test_browser_wallet_live_quote_creates_blocked_audit_when_env_disabled(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)

            audit = state.live_quote(False, "buy", "Mint111", "0.001", True, 1, 0.00001, "pump", "Wallet111")

            self.assertEqual(audit["status"], "blocked")
            self.assertIn("LIVE_TRADING_ENABLED is false", audit["errors"])
            checks = {check["id"]: check for check in audit["preflight_checks"]}
            self.assertEqual(checks["environment"]["status"], "fail")
            self.assertEqual(checks["blockers"]["status"], "fail")
            self.assertIn("LIVE_TRADING_ENABLED", checks["blockers"]["reason"])
            self.assertEqual(state.storage.count_live_execution_audits(), 1)

    def test_live_quote_records_structured_preflight_checks(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            audit = state.live_quote(True, "buy", "Mint111", "0.001", True, 1, 0.00001, "pump", "Wallet111")

            checks = {check["id"]: check for check in audit["preflight_checks"]}
            self.assertEqual(checks["environment"]["status"], "pass")
            self.assertEqual(checks["mint"]["status"], "pass")
            self.assertEqual(checks["wallet"]["status"], "pass")
            self.assertEqual(checks["signer"]["status"], "pass")
            self.assertEqual(checks["amount"]["status"], "pass")
            self.assertEqual(checks["slippage"]["status"], "pass")
            self.assertEqual(checks["priority_fee"]["status"], "pass")
            self.assertEqual(checks["caps"]["status"], "pass")
            self.assertEqual(checks["blockers"]["status"], "pass")
            stored = state.storage.load_live_execution_audit(audit["id"])
            self.assertTrue(stored.preflight_checks)

    def test_live_buy_quote_blocks_estimated_wallet_spend_over_trade_cap(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.001
            state.storage.save_settings(state.settings)
            calls: list[dict[str, object]] = []
            state._pumpportal_local_transaction = lambda **kwargs: calls.append(kwargs) or ({"ok": True}, "dHgi", "")  # type: ignore[method-assign]

            audit = state.live_quote(True, "buy", "MintSpendEstimate", "0.001", True, 5, 0.00001, "pump", "WalletSpendEstimate")

            checks = {check["id"]: check for check in audit["preflight_checks"]}
            estimate = audit["quote"]["wallet_spend_estimate"]
            self.assertEqual(audit["status"], "blocked")
            self.assertEqual(calls, [])
            self.assertGreater(estimate["estimated_wallet_spend_sol"], 0.0049)
            self.assertEqual(estimate["requested_amount_sol"], 0.001)
            self.assertEqual(estimate["max_trade_cap_sol"], 0.001)
            self.assertTrue(estimate["exceeds_max_trade_cap"])
            self.assertEqual(checks["estimated_wallet_spend"]["status"], "fail")
            self.assertTrue(any("estimated wallet spend exceeds live max trade cap" in error for error in audit["errors"]))

    def test_live_buy_quote_records_estimated_wallet_spend_when_within_trade_cap(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.006
            state.storage.save_settings(state.settings)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            audit = state.live_quote(True, "buy", "MintSpendEstimate", "0.001", True, 5, 0.00001, "pump", "WalletSpendEstimate")

            checks = {check["id"]: check for check in audit["preflight_checks"]}
            estimate = audit["quote"]["wallet_spend_estimate"]
            self.assertEqual(audit["status"], "ready")
            self.assertFalse(estimate["exceeds_max_trade_cap"])
            self.assertEqual(checks["estimated_wallet_spend"]["status"], "pass")
            self.assertEqual(estimate["components"]["token_account_setup_rent_sol"], 0.00391848)
            self.assertGreaterEqual(estimate["estimated_wallet_spend_sol"], estimate["requested_amount_sol"] + estimate["components"]["token_account_setup_rent_sol"])

    def test_live_buy_quote_marks_rent_dominant_dust_buy(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.006
            state.storage.save_settings(state.settings)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")  # type: ignore[method-assign]

            audit = state.live_quote(True, "buy", "MintRentDominant", "0.001", True, 5, 0.00001, "pump", "WalletRentDominant")

            checks = {check["id"]: check for check in audit["preflight_checks"]}
            estimate = audit["quote"]["wallet_spend_estimate"]
            self.assertTrue(estimate["rent_dominates_trade"])
            self.assertGreater(estimate["wallet_spend_to_trade_ratio"], 2)
            self.assertEqual(checks["rent_dominance"]["status"], "warn")
            self.assertTrue(any("setup rent dominates" in warning.lower() for warning in audit["warnings"]))

    def test_live_rent_recovery_scan_only_allows_zero_balance_non_open_positions(self) -> None:
        class FakeClient:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                pass

            def token_accounts(self, wallet_public_key: str) -> list[dict[str, object]]:
                return [
                    {"token_account": "AcctEmpty", "mint": "MintEmpty", "token_amount": 0.0, "rent_sol": 0.002, "lamports": 2_000_000, "program_id": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                    {"token_account": "AcctNonzero", "mint": "MintNonzero", "token_amount": 1.0, "rent_sol": 0.002, "lamports": 2_000_000, "program_id": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                    {"token_account": "AcctOpen", "mint": "MintOpen", "token_amount": 0.0, "rent_sol": 0.002, "lamports": 2_000_000, "program_id": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                ]

        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="pos_open_rent",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    mint="MintOpen",
                    wallet_public_key="WalletRent",
                    status="open",
                    token_balance=0.0,
                )
            )

            with patch("app.core.state.SolanaReadOnlyClient", FakeClient):
                scan = state.live_rent_recovery_scan("WalletRent")

            self.assertEqual(scan["eligible_count"], 1)
            self.assertEqual(scan["recoverable_rent_sol"], 0.002)
            self.assertEqual(scan["eligible_accounts"][0]["token_account"], "AcctEmpty")
            ineligible = {item["token_account"]: item["reason"] for item in scan["ineligible_accounts"]}
            self.assertIn("non-zero", ineligible["AcctNonzero"])
            self.assertIn("open live position", ineligible["AcctOpen"])

    def test_live_rent_recovery_preview_builds_unsigned_close_transaction(self) -> None:
        class FakeClient:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                pass

            def token_accounts(self, wallet_public_key: str) -> list[dict[str, object]]:
                return [
                    {"token_account": "11111111111111111111111111111112", "mint": "MintEmpty", "token_amount": 0.0, "rent_sol": 0.002, "lamports": 2_000_000, "program_id": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                ]

            def latest_blockhash(self) -> str:
                return "11111111111111111111111111111111"

        wallet = str(Keypair().pubkey())
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            with patch("app.core.state.SolanaReadOnlyClient", FakeClient):
                preview = state.live_rent_recovery_preview(wallet, ["11111111111111111111111111111112"])

            raw = base64.b64decode(preview["unsigned_transaction_base64"])
            transaction = VersionedTransaction.from_bytes(raw)
            self.assertEqual(preview["selected_count"], 1)
            self.assertEqual(preview["recoverable_rent_sol"], 0.002)
            self.assertEqual(preview["manual_approval_required"], True)
            self.assertTrue(preview["audit_id"])
            stored = state.storage.load_live_execution_audit(preview["audit_id"])
            self.assertIsNotNone(stored)
            self.assertEqual(stored.action, "rent_recovery")
            self.assertEqual(stored.wallet_public_key, wallet)
            self.assertEqual(stored.status, "ready")
            self.assertEqual(len(transaction.message.instructions), 1)

    def test_live_quote_validates_caps_and_disabled_signer(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)

            too_large = state.live_quote(True, "buy", "Mint111", "0.02", True, 1, 0.00001, "pump", "Wallet111")
            daemon = state.live_quote(True, "buy", "Mint111", "0.001", True, 1, 0.00001, "pump", "Wallet111", signer_mode="local_signer_daemon")

            self.assertTrue(any("amount exceeds live max trade cap" in error for error in too_large["errors"]))
            self.assertTrue(any("connected signer" in error.lower() or "unavailable" in error.lower() for error in daemon["errors"]))
            self.assertFalse(state.signer_status("browser_wallet", "Wallet111")["can_unattended_sign"])

    def test_live_simulation_submit_and_confirm_update_audit(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 10.0, "error": ""}
            audit = LiveExecutionRequest(
                id="legacy",
                created_at=utc_now(),
                action="buy",
                mint="Mint111",
                amount_sol=0.01,
                status="blocked",
                reason="legacy",
            )
            state.storage.save_live_execution_request(audit)
            live_audit = state.live_quote(True, "buy", "Mint111", "0.001", True, 1, 0.00001, "pump", "Wallet111")

            simulated = state.live_simulate(live_audit["id"], False, "simulation warning")
            submitted = state.live_submit(live_audit["id"], "sig111")
            confirmed = state.live_confirm(live_audit["id"], "confirmed")

            self.assertEqual(simulated["status"], "simulation_warning")
            self.assertEqual(submitted["transaction_signature"], "sig111")
            self.assertEqual(confirmed["status"], "reconciled")
            self.assertEqual(confirmed["confirmation_status"], "confirmed")
            self.assertIn("submitted_at", confirmed["execution_timing"])
            self.assertIn("confirmed_at", confirmed["execution_timing"])
            self.assertGreaterEqual(confirmed["execution_timing"]["quote_to_submit_ms"], 0)
            self.assertGreaterEqual(confirmed["execution_timing"]["submit_to_confirm_ms"], 0)

    def test_backend_live_submit_persists_submitting_audit_before_executor(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "test.db")
            state = BotState(database_path=db_path)
            self.configure_live_caps(state)
            state.settings.live_signer_mode = "local_signer_daemon"
            state.storage.save_settings(state.settings)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state.signer_status = lambda mode="browser_wallet", wallet_public_key="": {
                "mode": mode,
                "connected": True,
                "ready_to_submit": True,
                "healthy": True,
                "can_sign": True,
                "can_unattended_sign": True,
                "supports_auto_buy": True,
                "supports_auto_sell": True,
                "wallet_public_key": wallet_public_key or "WalletSubmit",
            }

            def timeout_executor(audit: LiveExecutionAudit) -> dict[str, object]:
                stored = state.storage.load_live_execution_audit(audit.id)
                self.assertIsNotNone(stored)
                self.assertEqual(stored.status, "submitting")
                self.assertEqual(stored.final_status, "submitting")
                self.assertIn("backend executor started", stored.warnings)
                raise TimeoutError("lost response after submit")

            state._execute_backend_audit = timeout_executor  # type: ignore[method-assign]
            quote = state.live_quote(True, "buy", "MintSubmitting", "0.001", True, 1, 0.00001, "pump", "WalletSubmit", signer_mode="local_signer_daemon")

            with self.assertRaisesRegex(TimeoutError, "lost response"):
                state.live_submit(quote["id"], "")

            reloaded = BotState(database_path=db_path)
            self.configure_live_caps(reloaded)
            reloaded.source_status.status = "connected"
            reloaded.source_status.last_event_at = utc_now()
            status = reloaded.live_status(True, "WalletSubmit", "local_signer_daemon")

            self.assertEqual(status["unresolved_audit_count"], 1)
            self.assertIn("unresolved live audit recovery debt blocks new entries", status["blockers"])

    def test_live_submit_rejects_blocked_or_stale_quotes(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            blocked = state.live_quote(False, "buy", "Mint111", "0.001", True, 1, 0.00001, "pump", "Wallet111")

            with self.assertRaises(ValueError):
                state.live_submit(blocked["id"], "sig111")

    def test_live_submit_rejects_failed_preflight_checks(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            quote = state.live_quote(True, "buy", "Mint111", "0.001", True, 1, 0.00001, "pump", "Wallet111")
            audit = state.storage.load_live_execution_audit(quote["id"])
            audit.preflight_checks.append(
                {
                    "id": "tampered_cap",
                    "label": "Tampered Cap",
                    "status": "fail",
                    "value": "0.001",
                    "target": "approved cap",
                    "reason": "test-injected failed preflight",
                }
            )
            state.storage.save_live_execution_audit(audit)

            with self.assertRaisesRegex(ValueError, "failed preflight"):
                state.live_submit(quote["id"], "sig111")

    def test_live_intent_generation_cap_and_quote_expiry(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.trade_size_sol = 0.001
            state.settings.live_max_trade_sol = 0.006
            state.storage.save_settings(state.settings)
            for index in range(12):
                token = self.make_token()
                token.id = f"tok_live_{index}"
                token.mint = f"MintLive{index}"
                token.score = 90 - index
                state.tokens.append(token)

            intents = state.generate_live_intents("Wallet111")
            first = intents[0]
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            quoted = state.quote_live_intent(True, first["id"], 1, 0.00001, "pump")

            self.assertLessEqual(len(intents), 10)
            self.assertGreaterEqual(intents[0]["score"], intents[-1]["score"])
            self.assertEqual(quoted["status"], "ready")
            loaded = state.storage.load_live_intent(first["id"])
            loaded.expires_at = utc_now().replace(year=2000)
            state.storage.save_live_intent(loaded)
            stale = next(item for item in state.live_intents() if item["id"] == first["id"])
            self.assertTrue(stale["stale"])

    def test_live_intent_readiness_warning_does_not_block_quote(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            intent = state.create_live_intent("buy", "Mint111", "0.001", True, "Wallet111")
            quote = state.quote_live_intent(True, intent["id"], 1, 0.00001, "pump")

            self.assertEqual(state.readiness_status()["status"], "not_enough_data")
            self.assertEqual(quote["status"], "ready")

    def test_promoted_paper_intents_auto_quote_shadow_without_signer(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.001
            state.settings.trade_size_sol = 0.001
            state.settings.live_priority_fee_cap_sol = 0.0001
            state.settings.paper_fee_bps = 25
            state.settings.paper_price_impact_pct = 0.4
            token = self.make_token()
            token.id = "tok_shadow_quote"
            token.mint = "MintShadowQuote"
            token.symbol = "SHDW"
            token.score = 95
            token.status = TokenStatus.PAPER_BOUGHT
            token.price_confidence = 0.9
            state.tokens.appendleft(token)
            calls: list[dict[str, object]] = []

            def fake_local_transaction(**kwargs):
                calls.append(kwargs)
                return {"ok": True}, "dHgi", ""

            state._pumpportal_local_transaction = fake_local_transaction

            intents = state.generate_live_intents("WalletShadow")
            promoted = next(intent for intent in intents if intent["mint"] == "MintShadowQuote")
            audit = state.storage.load_live_execution_audit(str(promoted["audit_id"]))
            refreshed_token = next(item for item in state.tokens if item.mint == "MintShadowQuote")

            self.assertEqual(promoted["source"], "paper_promoted")
            self.assertEqual(promoted["status"], "quoted")
            self.assertEqual(audit.status, "ready")
            self.assertTrue(audit.quote["shadow_only"])
            self.assertEqual(audit.errors, [])
            self.assertEqual(calls[0]["wallet_public_key"], "WalletShadow")
            self.assertAlmostEqual(audit.shadow_comparison["costs"]["priority_fee_sol"], 0.0001)
            self.assertAlmostEqual(refreshed_token.quote_shadow_total_cost_sol, audit.shadow_comparison["costs"]["total_cost_sol"])
            self.assertEqual(refreshed_token.quote_shadow_status, "ready")

    def test_quote_adjusted_trade_pnl_subtracts_only_unmodeled_shadow_costs(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.id = "tok_quote_adjusted"
            token.status = TokenStatus.PAPER_SOLD
            token.amount_sol = 0.1
            token.pnl_sol = 0.02
            token.fee_paid_sol = 0.0005
            token.exit_fee_sol = 0.0005
            token.entry_price_impact_cost_sol = 0.0002
            token.quote_shadow_total_cost_sol = 0.002
            token.quote_shadow_status = "ready"

            trade = state.trade_from_token(token)

            self.assertAlmostEqual(trade.paper_model_cost_sol, 0.0012)
            self.assertAlmostEqual(trade.shadow_quote_cost_sol, 0.002)
            self.assertAlmostEqual(trade.quote_adjustment_sol, 0.0008)
            self.assertAlmostEqual(trade.quote_adjusted_pnl_sol, 0.0192)
            self.assertEqual(trade.simulation_accuracy_status, "quote_adjusted")

    def test_shadow_quote_failure_is_recorded_on_promoted_paper_token(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.001
            state.settings.trade_size_sol = 0.001
            token = self.make_token()
            token.id = "tok_shadow_failure"
            token.mint = "MintShadowFailure"
            token.symbol = "FAIL"
            token.score = 95
            token.status = TokenStatus.PAPER_BOUGHT
            state.tokens.appendleft(token)

            def fail_local_transaction(**kwargs):
                raise RuntimeError("quote provider unavailable")

            state._pumpportal_local_transaction = fail_local_transaction

            intents = state.generate_live_intents("WalletShadow")
            promoted = next(intent for intent in intents if intent["mint"] == "MintShadowFailure")
            refreshed_token = next(item for item in state.tokens if item.mint == "MintShadowFailure")

            self.assertEqual(promoted["source"], "paper_promoted")
            self.assertIn("Automatic shadow quote failed", " ".join(promoted["warnings"]))
            self.assertEqual(refreshed_token.quote_shadow_status, "quote_failed")
            self.assertIn("quote provider unavailable", " ".join(refreshed_token.decision_log))

    def test_simulation_accuracy_report_compares_paper_shadow_and_live(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.storage.save_trade(
                TradeRecord(
                    id="trd_accuracy",
                    token_id="tok_accuracy",
                    mode="paper",
                    strategy_profile="balanced",
                    entry_price=0.00001,
                    exit_price=0.000012,
                    amount_sol=0.1,
                    pnl_sol=0.02,
                    entry_reason="test",
                    exit_reason="test",
                    opened_at=now - timedelta(seconds=10),
                    closed_at=now,
                    quote_adjusted_pnl_sol=0.018,
                    shadow_quote_cost_sol=0.002,
                    quote_adjustment_sol=0.001,
                    simulation_accuracy_status="quote_adjusted",
                )
            )
            audit = LiveExecutionAudit(
                id="audit_accuracy_shadow",
                created_at=now,
                updated_at=now,
                action="buy",
                mint="MintAccuracy",
                amount="0.1",
                status="ready",
                signer_mode="browser_wallet",
                wallet_public_key="WalletAccuracy",
                quote={"shadow_only": True},
                shadow_comparison={"status": "evaluated", "estimated_pnl_sol": 0.015, "latency_ms": 250, "outcome": "win"},
            )
            state.storage.save_live_execution_audit(audit)
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="pos_accuracy_live",
                    created_at=now,
                    updated_at=now,
                    mint="MintAccuracy",
                    wallet_public_key="WalletAccuracy",
                    status="closed",
                    realized_pnl_sol=0.012,
                    total_fees_sol=0.0002,
                    realized_pnl_confidence="audited",
                )
            )

            report = state.simulation_accuracy_report("WalletAccuracy")

            self.assertEqual(report["paper"]["samples"], 1)
            self.assertEqual(report["paper"]["quote_adjusted_pnl_sol"], 0.018)
            self.assertEqual(report["shadow"]["samples"], 1)
            self.assertEqual(report["live"]["samples"], 1)
            self.assertAlmostEqual(report["error"]["paper_minus_shadow_sol"], 0.003)
            self.assertAlmostEqual(report["error"]["shadow_minus_live_sol"], 0.003)
            self.assertEqual(report["operator_action"], "Use quote-adjusted paper and shadow-vs-live error before raising real-money size.")

    def test_recalculate_stats_reports_total_paper_fees(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.storage.save_trade(
                TradeRecord(
                    id="trd_fee_rollup",
                    token_id="tok_fee_rollup",
                    mode="paper",
                    strategy_profile="balanced",
                    entry_price=0.00001,
                    exit_price=0.00002,
                    amount_sol=0.1,
                    pnl_sol=0.01,
                    entry_reason="test fee entry",
                    exit_reason="test fee exit",
                    opened_at=now - timedelta(seconds=45),
                    closed_at=now,
                    entry_fee_sol=0.00025,
                    exit_fee_sol=0.0003,
                    hold_duration_seconds=45,
                )
            )

            state.recalculate_stats()

            self.assertAlmostEqual(state.stats.entry_fees_sol, 0.00025)
            self.assertAlmostEqual(state.stats.exit_fees_sol, 0.0003)
            self.assertAlmostEqual(state.stats.total_fees_sol, 0.00055)

    def test_live_position_risk_exit_generates_priority_sell_intent_with_soft_autonomy_block(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            token = self.make_token()
            token.mint = "MintRisk"
            token.symbol = "RISK"
            token.current_price = 0.000007
            token.sell_pressure = 0.9
            token.hold_duration_seconds = 120
            state.storage.save_token(token)
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="livepos_risk",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    mint="MintRisk",
                    wallet_public_key="WalletRisk",
                    symbol="RISK",
                    status="open",
                    token_balance=100.0,
                    cost_basis_sol=0.001,
                    average_entry_price_sol=0.00001,
                )
            )

            intents = state.generate_live_intents("WalletRisk")
            sell_intent = next(intent for intent in intents if intent["action"] == "sell")

            self.assertTrue(sell_intent["generated_from_position"])
            self.assertEqual(sell_intent["source"], "live_position_rules")
            self.assertIn("stop-loss", sell_intent["reason"].lower())
            self.assertTrue(sell_intent["autonomy_blocked"])
            self.assertTrue(any("autonomous live is disabled" in blocker.lower() for blocker in sell_intent["autonomy_blockers"]))
            self.assertTrue(any("manual signing only" in blocker.lower() or "unattended" in blocker.lower() for blocker in sell_intent["autonomy_blockers"]))

    def test_source_degradation_reports_exit_only_and_blocks_buy_not_sell_quote(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_session_acknowledged = True
            state.storage.save_settings(state.settings)
            state.source_status.status = "error"
            state.source_status.message = "PumpPortal disconnected"
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 10.0, "error": ""}

            status = state.live_status(True, "WalletExitOnly", "browser_wallet")
            buy_quote = state.live_quote(True, "buy", "MintExitOnly", "0.001", True, 1, 0.00001, "pump", "WalletExitOnly")
            sell_quote = state.live_quote(True, "sell", "MintExitOnly", "10", False, 1, 0.00001, "pump", "WalletExitOnly")

            self.assertEqual(status["source_degraded_mode"]["mode"], "exit_only")
            self.assertFalse(status["source_degraded_mode"]["live_entries_allowed"])
            self.assertTrue(status["source_degraded_mode"]["protective_exits_available"])
            self.assertIn("source is not connected", status["source_degraded_mode"]["entry_blockers"])
            self.assertEqual(buy_quote["status"], "blocked")
            self.assertTrue(any("source trust" in error for error in buy_quote["errors"]))
            self.assertEqual(sell_quote["status"], "ready")
            self.assertFalse(sell_quote["errors"])

    def test_low_replay_confidence_halt_blocks_live_buy_not_protective_sell(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.halt_on_low_replay_confidence = True
            state.settings.min_replay_confidence = 90
            state.storage.save_settings(state.settings)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 10.0, "error": ""}

            status = state.live_status(True, "WalletReplayHalt", "browser_wallet")
            buy_quote = state.live_quote(True, "buy", "MintReplayHalt", "0.001", True, 1, 0.00001, "pump", "WalletReplayHalt")
            sell_quote = state.live_quote(True, "sell", "MintReplayHalt", "10", False, 1, 0.00001, "pump", "WalletReplayHalt")

            self.assertTrue(any("low replay confidence halt active" in blocker for blocker in status["autonomy"]["entry"]["blockers"]))
            self.assertEqual(buy_quote["status"], "blocked")
            self.assertTrue(any("low replay confidence halt active" in error for error in buy_quote["errors"]))
            self.assertEqual(sell_quote["status"], "ready")
            self.assertFalse(any("low replay confidence" in error for error in sell_quote["errors"]))

    def test_full_sniper_gate_requires_entry_exit_backend_source_and_backup(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state, include_backup=False)

            browser = state.live_status(True, "WalletGate", "browser_wallet")

            self.assertFalse(browser["full_sniper_gate"]["ready"])
            self.assertFalse(browser["full_sniper_gate"]["entry_ready"])
            self.assertFalse(browser["full_sniper_gate"]["exit_ready"])
            self.assertIn("backup artifact is required", " ".join(browser["full_sniper_gate"]["blockers"]).lower())
            self.assertFalse(browser["full_sniper_gate"]["audited_override_active"])
            self.assertIn("audit-only", browser["full_sniper_gate"]["override_effect"])

        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.03
            state.storage.save_settings(state.settings)
            state.settings.autonomous_live_enabled = True
            state.storage.save_settings(state.settings)
            state.import_hot_wallet(str(Keypair()), "password123", "ops")
            armed = state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            wallet = str(armed["wallet_public_key"])
            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_gate_manual_verified",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintGateManual",
                    amount="0.001",
                    status="reconciled",
                    final_status="reconciled",
                    signer_mode="local_hot_wallet",
                    wallet_public_key=wallet,
                    transaction_signature="siggatemanual",
                    reconciliation_status="matched",
                )
            )

            ready = state.live_status(True, wallet, "local_hot_wallet")

            self.assertTrue(ready["full_sniper_gate"]["ready"])
            self.assertTrue(ready["full_sniper_gate"]["entry_ready"])
            self.assertTrue(ready["full_sniper_gate"]["exit_ready"])
            self.assertTrue(ready["full_sniper_gate"]["active_backend_matches"])
            self.assertEqual(ready["full_sniper_gate"]["source_mode"], "normal")
            self.assertTrue(ready["full_sniper_gate"]["pre_run_backup_fresh"])

    def test_full_sniper_gate_requires_recent_manual_live_success(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.trade_size_sol = 0.001
            state.settings.live_max_trade_sol = 0.006
            state.storage.save_settings(state.settings)
            state.settings.autonomous_live_enabled = True
            state.storage.save_settings(state.settings)
            state.import_hot_wallet(str(Keypair()), "password123", "ops")
            armed = state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            wallet = str(armed["wallet_public_key"])

            without_manual = state.live_status(True, wallet, "local_hot_wallet")

            self.assertFalse(without_manual["full_sniper_gate"]["ready"])
            self.assertFalse(without_manual["full_sniper_gate"]["manual_live_verified"])
            self.assertTrue(any("manual live" in blocker.lower() for blocker in without_manual["full_sniper_gate"]["blockers"]))

            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_manual_verified",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintManualVerified",
                    amount="0.001",
                    status="reconciled",
                    final_status="reconciled",
                    signer_mode="local_hot_wallet",
                    wallet_public_key=wallet,
                    transaction_signature="sigmanualverified",
                    reconciliation_status="matched",
                )
            )

            with_manual = state.live_status(True, wallet, "local_hot_wallet")

            self.assertTrue(with_manual["full_sniper_gate"]["manual_live_verified"])
            self.assertEqual(with_manual["full_sniper_gate"]["manual_live_audit_id"], "liveaudit_manual_verified")
            self.assertTrue(with_manual["full_sniper_gate"]["ready"])

    def test_full_sniper_gate_requires_manual_live_proof_from_selected_signer_path(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.autonomous_live_enabled = True
            state.storage.save_settings(state.settings)
            state.import_hot_wallet(str(Keypair()), "password123", "ops")
            armed = state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            wallet = str(armed["wallet_public_key"])
            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_browser_wallet_proof_only",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintBrowserProofOnly",
                    amount="0.001",
                    status="reconciled",
                    final_status="reconciled",
                    signer_mode="browser_wallet",
                    wallet_public_key=wallet,
                    transaction_signature="sigbrowserproofonly",
                    reconciliation_status="matched",
                )
            )

            browser_only = state.live_status(True, wallet, "local_hot_wallet")

            self.assertFalse(browser_only["full_sniper_gate"]["manual_live_verified"])
            self.assertFalse(browser_only["full_sniper_gate"]["ready"])
            self.assertTrue(any("local_hot_wallet" in blocker for blocker in browser_only["full_sniper_gate"]["blockers"]))

            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_local_hot_wallet_proof",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintLocalProof",
                    amount="0.001",
                    status="reconciled",
                    final_status="reconciled",
                    signer_mode="local_hot_wallet",
                    wallet_public_key=wallet,
                    transaction_signature="siglocalproof",
                    reconciliation_status="matched",
                )
            )

            local_proof = state.live_status(True, wallet, "local_hot_wallet")

            self.assertTrue(local_proof["full_sniper_gate"]["manual_live_verified"])
            self.assertEqual(local_proof["full_sniper_gate"]["manual_live_audit_id"], "liveaudit_local_hot_wallet_proof")
            self.assertTrue(local_proof["full_sniper_gate"]["ready"])

    def test_full_sniper_gate_rejects_pending_manual_live_reconciliation(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.autonomous_live_enabled = True
            state.storage.save_settings(state.settings)
            state.import_hot_wallet(str(Keypair()), "password123", "ops")
            armed = state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            wallet = str(armed["wallet_public_key"])
            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_manual_pending_reconciliation",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintManualPending",
                    amount="0.001",
                    status="confirmed",
                    final_status="confirmed",
                    signer_mode="browser_wallet",
                    wallet_public_key=wallet,
                    transaction_signature="sigmanualpending",
                    reconciliation_status="pending",
                )
            )

            pending_reconciliation = state.live_status(True, wallet, "local_hot_wallet")

            self.assertFalse(pending_reconciliation["full_sniper_gate"]["manual_live_verified"])
            self.assertFalse(pending_reconciliation["full_sniper_gate"]["ready"])
            self.assertTrue(
                any("reconcile" in blocker.lower() or "manual live" in blocker.lower() for blocker in pending_reconciliation["full_sniper_gate"]["blockers"])
            )

    def test_full_sniper_gate_rejects_manual_live_proof_with_errors(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.autonomous_live_enabled = True
            state.storage.save_settings(state.settings)
            state.import_hot_wallet(str(Keypair()), "password123", "ops")
            armed = state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            wallet = str(armed["wallet_public_key"])
            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_manual_error_reconciled",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintManualError",
                    amount="0.001",
                    status="reconciled",
                    final_status="reconciled",
                    signer_mode="local_hot_wallet",
                    wallet_public_key=wallet,
                    transaction_signature="sigmanualerror",
                    reconciliation_status="matched",
                    errors=["RPC confirmation mismatch requires review"],
                )
            )

            status = state.live_status(True, wallet, "local_hot_wallet")

            self.assertFalse(status["full_sniper_gate"]["manual_live_verified"])
            self.assertFalse(status["full_sniper_gate"]["ready"])
            self.assertTrue(any("manual live" in blocker.lower() for blocker in status["full_sniper_gate"]["blockers"]))

    def test_run_live_autonomy_executes_hot_wallet_intent(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.trade_size_sol = 0.001
            state.settings.live_max_trade_sol = 0.006
            state.storage.save_settings(state.settings)
            state.settings.autonomous_live_enabled = True
            state.import_hot_wallet(str(Keypair()), "password123", "ops")
            state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state.hot_wallet.simulate_and_submit = lambda unsigned_transaction_base64, rpc_url: {  # type: ignore[method-assign]
                "signature": "sighot111",
                "transaction_signature": "sighot111",
                "simulation": {"ok": True, "warning": "", "error": "", "result": {}},
            }
            state._signature_status = lambda signature: {
                "ok": True,
                "found": True,
                "signature": signature,
                "confirmation_status": "confirmed",
                "err": None,
                "slot": 123,
            }
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 100.0, "error": ""}
            token = self.make_token()
            token.id = "tok_live_auto"
            token.mint = "MintAuto"
            token.symbol = "AUTO"
            token.score = 95
            state.tokens.appendleft(token)

            result = state.run_live_autonomy(True, local_auth_enabled=True)

            self.assertEqual(result["status"], "ok")
            self.assertGreaterEqual(len(result["executed"]), 1)
            self.assertGreaterEqual(state.storage.count_live_execution_audits(), 1)

    def test_run_live_autonomy_requires_local_auth_before_intent_generation(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.db"
            state = BotState(database_path=str(database_path))
            state.settings.live_signer_mode = "browser_wallet"
            state.settings.live_active_backend_armed = True
            state.settings.live_active_wallet_public_key = "WalletPersisted"
            state.storage.save_settings(state.settings)
            restarted = BotState(database_path=str(database_path))
            generated: list[bool] = []
            restarted.generate_live_intents = lambda *args, **kwargs: generated.append(True) or []  # type: ignore[method-assign]

            result = restarted.run_live_autonomy(True)

            self.assertEqual(result["status"], "disabled")
            self.assertIn("local auth", result["reason"].lower())
            self.assertEqual(generated, [])
            self.assertEqual(restarted.storage.count_live_intents(), 0)

    def test_run_live_autonomy_blocks_failed_quote_preflight(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.autonomous_live_enabled = True
            state.import_hot_wallet(str(Keypair()), "password123", "ops")
            state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            submitted: list[str] = []
            state.hot_wallet.simulate_and_submit = lambda unsigned_transaction_base64, rpc_url: submitted.append(unsigned_transaction_base64) or {  # type: ignore[method-assign]
                "signature": "should-not-submit",
                "transaction_signature": "should-not-submit",
                "simulation": {"ok": True, "warning": "", "error": "", "result": {}},
            }
            state._live_order_preflight_checks = lambda **kwargs: [  # type: ignore[method-assign]
                {
                    "id": "autonomy_guard",
                    "label": "Autonomy Guard",
                    "status": "fail",
                    "value": "quote",
                    "target": "all preflight checks pass",
                    "reason": "test-injected failed preflight",
                }
            ]
            token = self.make_token()
            token.id = "tok_live_auto_preflight"
            token.mint = "MintAutoPreflight"
            token.symbol = "APRE"
            token.score = 95
            state.tokens.appendleft(token)

            result = state.run_live_autonomy(True, local_auth_enabled=True)
            matching_intents = [intent for intent in state.storage.load_live_intents(20) if intent.mint == "MintAutoPreflight"]
            blocked_intent = next(intent for intent in matching_intents if intent.autonomy_blocked)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["executed"], [])
            self.assertEqual(submitted, [])
            self.assertTrue(blocked_intent.autonomy_blocked)
            self.assertIn("Autonomy Guard", " ".join(blocked_intent.autonomy_blockers))

    def test_profit_sweep_triggers_immediately_on_realized_live_profit(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            wallet = state.import_hot_wallet(str(Keypair()), "password123", "ops")["wallet_public_key"]
            self.configure_live_caps(state)
            state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            state.update_settings(
                {
                    "profit_sweep_enabled": True,
                    "profit_sweep_threshold_sol": 0.05,
                    "profit_sweep_amount_sol": 0.02,
                    "profit_sweep_destination_wallet": "Vault111111111111111111111111111111111111111",
                    "profit_sweep_min_reserve_sol": 0.01,
                    "profit_sweep_cooldown_seconds": 3600,
                    "profit_sweep_max_per_day": 1,
                }
            )
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="livepos_profit_sweep",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    mint="MintProfit",
                    wallet_public_key=str(wallet),
                    symbol="WIN",
                    status="closed",
                    realized_pnl_sol=0.06,
                    reconciliation_status="matched",
                )
            )
            state._wallet_sol_balance = lambda wallet_public_key: {"wallet_public_key": wallet_public_key, "balance_sol": 0.08, "error": ""}  # type: ignore[method-assign]
            submitted: list[tuple[str, float]] = []
            state.hot_wallet.transfer_sol = lambda destination, amount_sol, rpc_url: submitted.append((destination, amount_sol)) or {  # type: ignore[attr-defined, method-assign]
                "signature": "sigsweep111",
                "transaction_signature": "sigsweep111",
                "simulation": {"ok": True, "warning": "", "error": "", "result": {}},
            }

            result = state.maybe_run_profit_sweep()

            self.assertEqual(result["status"], "submitted")
            self.assertEqual(submitted, [("Vault111111111111111111111111111111111111111", 0.02)])
            audit = state.storage.load_live_execution_audits(1)[0]
            self.assertEqual(audit.action, "profit_sweep")
            self.assertEqual(audit.transaction_signature, "sigsweep111")
            self.assertEqual(audit.final_status, "submitted")

    def test_profit_sweep_blocks_when_minimum_reserve_would_be_breached(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            wallet = state.import_hot_wallet(str(Keypair()), "password123", "ops")["wallet_public_key"]
            self.configure_live_caps(state)
            state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            state.update_settings(
                {
                    "profit_sweep_enabled": True,
                    "profit_sweep_threshold_sol": 0.05,
                    "profit_sweep_amount_sol": 0.02,
                    "profit_sweep_destination_wallet": "Vault111111111111111111111111111111111111111",
                    "profit_sweep_min_reserve_sol": 0.01,
                }
            )
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="livepos_profit_sweep_reserve",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    mint="MintProfitReserve",
                    wallet_public_key=str(wallet),
                    status="closed",
                    realized_pnl_sol=0.06,
                    reconciliation_status="matched",
                )
            )
            state._wallet_sol_balance = lambda wallet_public_key: {"wallet_public_key": wallet_public_key, "balance_sol": 0.025, "error": ""}  # type: ignore[method-assign]
            submitted: list[str] = []
            state.hot_wallet.transfer_sol = lambda destination, amount_sol, rpc_url: submitted.append(destination) or {}  # type: ignore[attr-defined, method-assign]

            result = state.maybe_run_profit_sweep()

            self.assertEqual(result["status"], "blocked")
            self.assertIn("minimum reserve", result["reason"])
            self.assertFalse(submitted)

    def test_profit_sweep_respects_cooldown_and_daily_cap(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            wallet = state.import_hot_wallet(str(Keypair()), "password123", "ops")["wallet_public_key"]
            self.configure_live_caps(state)
            state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            state.update_settings(
                {
                    "profit_sweep_enabled": True,
                    "profit_sweep_threshold_sol": 0.05,
                    "profit_sweep_amount_sol": 0.02,
                    "profit_sweep_destination_wallet": "Vault111111111111111111111111111111111111111",
                    "profit_sweep_min_reserve_sol": 0.01,
                    "profit_sweep_cooldown_seconds": 3600,
                    "profit_sweep_max_per_day": 1,
                }
            )
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="livepos_profit_sweep_cap",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    mint="MintProfitCap",
                    wallet_public_key=str(wallet),
                    status="closed",
                    realized_pnl_sol=0.10,
                    reconciliation_status="matched",
                )
            )
            state._wallet_sol_balance = lambda wallet_public_key: {"wallet_public_key": wallet_public_key, "balance_sol": 0.20, "error": ""}  # type: ignore[method-assign]
            submitted: list[str] = []
            state.hot_wallet.transfer_sol = lambda destination, amount_sol, rpc_url: submitted.append(destination) or {  # type: ignore[attr-defined, method-assign]
                "signature": f"sigsweep{len(submitted)}",
                "simulation": {"ok": True, "warning": "", "error": "", "result": {}},
            }

            first = state.maybe_run_profit_sweep()
            second = state.maybe_run_profit_sweep()

            self.assertEqual(first["status"], "submitted")
            self.assertEqual(second["status"], "blocked")
            self.assertIn("daily sweep cap", second["reason"])
            self.assertEqual(len(submitted), 1)

    def test_profit_sweep_percentage_mode_sweeps_percent_of_realized_profit(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            wallet = state.import_hot_wallet(str(Keypair()), "password123", "ops")["wallet_public_key"]
            self.configure_live_caps(state)
            state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            state.update_settings(
                {
                    "profit_sweep_enabled": True,
                    "profit_sweep_mode": "percentage",
                    "profit_sweep_percentage": 25.0,
                    "profit_sweep_min_profit_sol": 0.05,
                    "profit_sweep_destination_wallet": "Vault111111111111111111111111111111111111111",
                    "profit_sweep_min_reserve_sol": 0.01,
                    "profit_sweep_cooldown_seconds": 3600,
                    "profit_sweep_max_per_day": 1,
                }
            )
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="livepos_profit_sweep_pct",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    mint="MintProfitPct",
                    wallet_public_key=str(wallet),
                    status="closed",
                    realized_pnl_sol=0.10,
                    reconciliation_status="matched",
                )
            )
            state._wallet_sol_balance = lambda wallet_public_key: {"wallet_public_key": wallet_public_key, "balance_sol": 0.20, "error": ""}  # type: ignore[method-assign]
            submitted: list[tuple[str, float]] = []
            state.hot_wallet.transfer_sol = lambda destination, amount_sol, rpc_url: submitted.append((destination, amount_sol)) or {  # type: ignore[attr-defined, method-assign]
                "signature": "sigsweeppct",
                "simulation": {"ok": True, "warning": "", "error": "", "result": {}},
            }

            result = state.maybe_run_profit_sweep()

            self.assertEqual(result["status"], "submitted")
            self.assertEqual(submitted, [("Vault111111111111111111111111111111111111111", 0.025)])
            audit = state.storage.load_live_execution_audits(1)[0]
            self.assertEqual(audit.quote["sweep_mode"], "percentage")
            self.assertEqual(audit.quote["sweep_percentage"], 25.0)
            self.assertEqual(audit.quote["amount_sol"], 0.025)

    def test_profit_sweep_blocks_below_minimum_profit_to_sweep(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            wallet = state.import_hot_wallet(str(Keypair()), "password123", "ops")["wallet_public_key"]
            self.configure_live_caps(state)
            state.arm_live_backend(True, "local_hot_wallet", local_auth_enabled=True)
            state.update_settings(
                {
                    "profit_sweep_enabled": True,
                    "profit_sweep_mode": "percentage",
                    "profit_sweep_percentage": 50.0,
                    "profit_sweep_min_profit_sol": 0.05,
                    "profit_sweep_destination_wallet": "Vault111111111111111111111111111111111111111",
                    "profit_sweep_min_reserve_sol": 0.01,
                }
            )
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="livepos_profit_sweep_min_profit",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    mint="MintProfitMin",
                    wallet_public_key=str(wallet),
                    status="closed",
                    realized_pnl_sol=0.04,
                    reconciliation_status="matched",
                )
            )
            submitted: list[str] = []
            state.hot_wallet.transfer_sol = lambda destination, amount_sol, rpc_url: submitted.append(destination) or {}  # type: ignore[attr-defined, method-assign]

            result = state.maybe_run_profit_sweep()

            self.assertEqual(result["status"], "idle")
            self.assertIn("minimum profit", result["reason"])
            self.assertFalse(submitted)

    def test_profit_sweep_history_returns_only_sweep_audits_newest_first(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_buy",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintBuy",
                    amount="0.01",
                    status="submitted",
                    signer_mode="local_hot_wallet",
                    wallet_public_key="WalletSweep",
                )
            )
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_sweep_old",
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=5),
                    action="profit_sweep",
                    mint="SOL",
                    amount="0.01",
                    status="submitted",
                    signer_mode="local_hot_wallet",
                    wallet_public_key="WalletSweep",
                    quote={"destination_wallet": "VaultOld", "realized_pnl_sol": 0.04},
                    transaction_signature="sigold",
                    final_status="submitted",
                )
            )
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_sweep_new",
                    created_at=now,
                    updated_at=now,
                    action="profit_sweep",
                    mint="SOL",
                    amount="0.02",
                    status="failed",
                    signer_mode="local_hot_wallet",
                    wallet_public_key="WalletSweep",
                    quote={"destination_wallet": "VaultNew", "realized_pnl_sol": 0.08},
                    errors=["simulation failed"],
                    final_status="failed",
                )
            )

            history = state.profit_sweep_history(limit=10)

            self.assertEqual([item["id"] for item in history], ["liveaudit_sweep_new", "liveaudit_sweep_old"])
            self.assertEqual(history[0]["quote"]["destination_wallet"], "VaultNew")
            self.assertEqual(history[0]["quote"]["realized_pnl_sol"], 0.08)
            self.assertEqual(history[0]["errors"], ["simulation failed"])

    def test_live_kill_switch_blocks_new_intent_quotes(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.kill_switch_enabled = True
            intent = state.create_live_intent("buy", "Mint111", "0.001", True, "Wallet111")

            quote = state.quote_live_intent(True, intent["id"], 1, 0.00001, "pump")

            self.assertEqual(quote["status"], "blocked")
            self.assertIn("manual kill switch enabled", quote["errors"])

    def test_live_kill_switch_blocks_ready_buy_submit(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            quote = state.live_quote(True, "buy", "MintKillSubmit", "0.001", True, 1, 0.00001, "pump", "WalletKill")

            self.assertEqual(quote["status"], "ready")
            state.set_live_kill_switch(True, "operator panic stop")

            with self.assertRaisesRegex(ValueError, "manual kill switch enabled"):
                state.live_submit(quote["id"], "sigkill")

    def test_live_submit_rechecks_hard_caps_before_accepting_buy_signature(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_max_open_positions = 1
            state.storage.save_settings(state.settings)
            wallet = "WalletCapRace"
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            quote = state.live_quote(True, "buy", "MintCapRace", "0.001", True, 1, 0.00001, "pump", wallet)
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="livepos_cap_race",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    mint="MintAlreadyOpen",
                    wallet_public_key=wallet,
                    status="open",
                    token_balance=10.0,
                    cost_basis_sol=0.001,
                    reconciliation_status="matched",
                )
            )

            self.assertEqual(quote["status"], "ready")
            with self.assertRaisesRegex(ValueError, "wallet max open positions reached"):
                state.live_submit(quote["id"], "sigcaprace")

    def test_live_submit_rechecks_source_trust_before_accepting_buy_signature(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            quote = state.live_quote(True, "buy", "MintSourceRace", "0.001", True, 1, 0.00001, "pump", "WalletSourceRace")
            state.source_status.last_event_at = utc_now() - timedelta(seconds=state.settings.source_stale_seconds + 5)

            self.assertEqual(quote["status"], "ready")
            with self.assertRaisesRegex(ValueError, "source trust"):
                state.live_submit(quote["id"], "sigsource")

    def test_live_quote_blocks_buy_when_rpc_balance_check_fails(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            wallet = "11111111111111111111111111111112"
            state._wallet_sol_balance = lambda wallet_public_key: {"wallet_public_key": wallet_public_key, "balance_sol": 0.0, "error": "RPC timeout"}  # type: ignore[method-assign]
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            quote = state.live_quote(True, "buy", "MintRpcDown", "0.001", True, 1, 0.00001, "pump", wallet)

            self.assertEqual(quote["status"], "blocked")
            self.assertIn("wallet SOL balance check failed: RPC timeout", quote["errors"])

    def test_live_status_exposes_runtime_connectivity_guard(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            wallet = "11111111111111111111111111111112"
            state._wallet_sol_balance = lambda wallet_public_key: {"wallet_public_key": wallet_public_key, "balance_sol": 0.0, "error": "RPC unavailable"}  # type: ignore[method-assign]

            status = state.live_status(True, wallet, "browser_wallet")
            runtime = status["runtime_connectivity"]

            self.assertFalse(runtime["rpc_available"])
            self.assertFalse(runtime["safe_for_new_entry"])
            self.assertIn("wallet SOL balance check failed: RPC unavailable", runtime["blockers"])

    def test_live_status_blocks_reconnecting_source_for_new_entries(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.source_status.status = "reconnecting"
            state.source_status.message = "PumpPortal reconnecting"
            state.source_status.last_event_at = utc_now()

            status = state.live_status(True, "WalletReconnect", "browser_wallet")

            self.assertIn("source trust requires PumpPortal source connected before live entries", status["runtime_connectivity"]["blockers"])
            self.assertFalse(status["runtime_connectivity"]["safe_for_new_entry"])

    def test_unresolved_submitted_audit_blocks_new_entry_after_restart(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "test.db")
            state = BotState(database_path=db_path)
            self.configure_live_caps(state)
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_restart_debt",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    action="buy",
                    mint="MintRestartDebt",
                    amount="0.001",
                    status="submitted",
                    final_status="submitted",
                    transaction_signature="sigrestart",
                    wallet_public_key="WalletRestart",
                    signer_mode="browser_wallet",
                )
            )

            reloaded = BotState(database_path=db_path)
            reloaded.source_status.status = "connected"
            reloaded.source_status.message = "healthy"
            reloaded.source_status.last_event_at = utc_now()
            status = reloaded.live_status(True, "WalletRestart", "browser_wallet")

            self.assertIn("unresolved live audit recovery debt blocks new entries", status["blockers"])
            self.assertFalse(status["runtime_connectivity"]["recovery_debt_clear"])

    def test_live_kill_switch_action_records_risk_state(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)

            enabled = state.set_live_kill_switch(True, "operator panic stop")
            disabled = state.set_live_kill_switch(False, "resume after review")
            events = state.storage.load_events(2)
            latest_payload = json.loads(events[0].operator_action)
            previous_payload = json.loads(events[1].operator_action)

            self.assertTrue(enabled["kill_switch_enabled"])
            self.assertFalse(disabled["kill_switch_enabled"])
            self.assertEqual(latest_payload["effect"], "allows_entries_when_other_gates_pass")
            self.assertEqual(previous_payload["effect"], "blocks_new_entries")
            self.assertIn("risk_state", previous_payload)
            self.assertTrue(previous_payload["risk_state"]["kill_switch_enabled"])

    def test_live_session_acknowledgement_records_caps_and_backend_state(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)

            result = state.acknowledge_live_session()
            event = state.storage.load_events(1)[0]
            payload = json.loads(event.operator_action)

            self.assertTrue(result["acknowledged"])
            self.assertTrue(result["risk_state"]["session_acknowledged"])
            self.assertEqual(payload["effect"], "session_risk_acknowledged")
            self.assertIn("caps", payload)
            self.assertIn("active_backend", payload)

    def test_live_events_include_session_context(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.solana_rpc_url = "https://rpc.example.invalid"

            session = state.start_live_session(True, "WalletSession", "browser_wallet")
            event = state.storage.load_events(1)[0]

            self.assertEqual(event.session_id, session["id"])
            self.assertEqual(event.context["session_id"], session["id"])
            self.assertEqual(event.context["active_backend"]["mode"], "browser_wallet")
            self.assertTrue(event.context["live_session_acknowledged"])

    def test_operational_monitoring_reports_session_event_metrics(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.solana_rpc_url = "https://rpc.example.invalid"
            session = state.start_live_session(True, "WalletSession", "browser_wallet")
            state.add_event("warning", "Live session follow-up", subsystem="live")
            state.add_event("info", "Paper-only note", subsystem="paper")

            observability = state.operational_monitoring()["observability"]
            metrics = observability["session_metrics"]

            self.assertEqual(metrics["active_session_id"], session["id"])
            self.assertGreaterEqual(metrics["session_event_count"], 2)
            self.assertEqual(metrics["sessions_seen"], 1)
            self.assertEqual(metrics["top_sessions"][0]["session_id"], session["id"])

    def test_pre_run_backup_blocks_live_entries_until_fresh_artifact_exists(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state, include_backup=False)
            state.settings.solana_rpc_url = "https://rpc.example.invalid"

            blocked = state.live_status(True, "WalletBackup", "browser_wallet")

            self.assertEqual(blocked["pre_run_backup"]["state"], "missing")
            self.assertTrue(blocked["pre_run_backup"]["blocks_live_entries"])
            self.assertIn("pre-run backup artifact is required before live entries", blocked["autonomy"]["entry"]["blockers"])
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            quote = state.live_quote(True, "buy", "MintBackup", "0.001", True, 1, 0.00001, "pump", "WalletBackup")

            self.assertEqual(quote["status"], "ready")
            with self.assertRaisesRegex(ValueError, "pre-run backup"):
                state.live_submit(quote["id"], "sigbackup")

            state.storage.create_backup_artifact()
            ready = state.live_status(True, "WalletBackup", "browser_wallet")

            self.assertEqual(ready["pre_run_backup"]["state"], "fresh")
            self.assertFalse(ready["pre_run_backup"]["blocks_live_entries"])
            self.assertNotIn("pre-run backup artifact is required before live entries", ready["autonomy"]["entry"]["blockers"])

    def test_pre_run_backup_is_superseded_by_later_restore_history(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.storage.create_backup_artifact()
            state.storage.save_backup_restore_history(
                {
                    "id": "restore_after_backup",
                    "created_at": (utc_now() + timedelta(seconds=1)).isoformat(),
                    "action": "restore",
                    "status": "restored",
                }
            )

            status = state._pre_run_backup_status()

            self.assertEqual(status["state"], "superseded_by_restore")
            self.assertTrue(status["blocks_live_entries"])
            self.assertEqual(status["blocker"], "pre-run backup is older than the latest restore")

    def test_unresolved_recovery_debt_blocks_new_entries_not_protective_exits(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_debt",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    action="buy",
                    mint="MintDebt",
                    amount="0.001",
                    status="submitted",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletDebt",
                    transaction_signature="sigdebt",
                )
            )
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 100.0, "error": ""}

            buy_quote = state.live_quote(True, "buy", "MintNext", "0.001", True, 1, 0.00001, "pump", "WalletDebt")
            sell_quote = state.live_quote(True, "sell", "MintDebt", "100", False, 1, 0.00001, "pump", "WalletDebt")
            status = state.live_status(True, "WalletDebt")

            self.assertEqual(buy_quote["status"], "blocked")
            self.assertIn("unresolved live audit recovery debt blocks new entries", buy_quote["errors"])
            self.assertEqual(sell_quote["status"], "ready")
            self.assertTrue(status["autonomy"]["recovery_debt"]["blocks_new_entries"])
            self.assertTrue(status["autonomy"]["entry"]["recovery_debt_blocks_entries"])

    def test_expert_override_is_auth_gated_and_audit_only(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)

            with self.assertRaises(ValueError):
                state.record_expert_override(False, "entry_autonomy", "buy", "testing override without auth", "WalletOverride")

            event = state.record_expert_override(True, "entry_autonomy", "buy", "testing audit only override path", "WalletOverride")
            latest = state.storage.load_events(1)[0]
            payload = json.loads(latest.operator_action)

            self.assertEqual(event["effect"], "audit_only_no_gate_bypass")
            self.assertEqual(payload["target_gate"], "entry_autonomy")
            self.assertEqual(payload["effect"], "audit_only_no_gate_bypass")
            self.assertIn("blockers", payload["risk_state"])

    def test_source_trust_blocks_live_entries_but_not_protective_exits(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.source_status.status = "offline"
            state.source_status.message = "feed down"
            state.source_status.last_event_at = utc_now()
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 100.0, "error": ""}

            buy_quote = state.live_quote(True, "buy", "MintTrust", "0.001", True, 1, 0.00001, "pump", "WalletTrust")
            sell_quote = state.live_quote(True, "sell", "MintTrust", "100", False, 1, 0.00001, "pump", "WalletTrust")

            self.assertEqual(buy_quote["status"], "blocked")
            self.assertTrue(any("source trust" in error for error in buy_quote["errors"]))
            self.assertEqual(sell_quote["status"], "ready")

    def test_execution_readiness_reports_policy_and_quote_sample_blockers(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            execution = state.readiness_status()["execution_readiness"]

            self.assertEqual(execution["status"], "not_enough_quote_data")
            self.assertEqual(execution["metrics"]["quote_attempts"], 0)
            self.assertIn("live max trade cap must be set", execution["policy"]["blockers"])
            self.assertTrue(any(gate["id"] == "quote_audit_sample" and gate["status"] == "fail" for gate in execution["gates"]))

    def test_execution_readiness_can_promote_to_shadow_after_clean_quotes(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            for index in range(5):
                state.live_quote(True, "buy", f"MintShadow{index}", "0.001", True, 1, 0.00001, "pump", "WalletShadow")

            execution = state.readiness_status()["execution_readiness"]

            self.assertEqual(execution["status"], "shadow_ready")
            self.assertTrue(execution["can_shadow"])
            self.assertEqual(execution["metrics"]["quote_attempts"], 5)
            self.assertEqual(execution["metrics"]["stale_quotes"], 0)
            self.assertFalse(execution["blockers"])

    def test_execution_readiness_blocks_shadow_when_pumpportal_trade_observations_need_funded_key(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            now = utc_now()
            state.storage.save_source_event(
                SourceEvent(
                    id="src_shadow_funding_blocker",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"message": "'subscribeTokenTrade' and 'subscribeAccountTrade' methods are only available when connecting with an API key funded with at least 0.02 SOL."},
                    status="status",
                    message="'subscribeTokenTrade' and 'subscribeAccountTrade' methods are only available when connecting with an API key funded with at least 0.02 SOL.",
                )
            )

            for index in range(5):
                state.live_quote(True, "buy", f"MintFundingShadow{index}", "0.001", True, 1, 0.00001, "pump", "WalletFundingShadow")

            execution = state.readiness_status()["execution_readiness"]

            self.assertEqual(execution["status"], "blocked")
            self.assertFalse(execution["can_shadow"])
            self.assertTrue(any(gate["id"] == "shadow_price_observations" and gate["status"] == "fail" for gate in execution["gates"]))
            self.assertTrue(any("funded API key" in blocker for blocker in execution["blockers"]))

    def test_execution_readiness_blocks_shadow_on_stale_quote_pressure(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            stale_id = ""
            for index in range(5):
                quote = state.live_quote(True, "buy", f"MintStale{index}", "0.001", True, 1, 0.00001, "pump", "WalletStale")
                if index < 2:
                    stale_id = str(quote["id"])
                    audit = state.storage.load_live_execution_audit(stale_id)
                    self.assertIsNotNone(audit)
                    audit.status = "stale"
                    audit.final_status = "stale"
                    audit.quote["stale"] = True
                    state.storage.save_live_execution_audit(audit)

            execution = state.readiness_status()["execution_readiness"]

            self.assertEqual(execution["status"], "blocked")
            self.assertEqual(execution["metrics"]["stale_quotes"], 2)
            self.assertGreater(execution["metrics"]["stale_quote_rate"], 0.25)
            self.assertTrue(any(gate["id"] == "quote_freshness" and gate["status"] == "fail" for gate in execution["gates"]))

    def test_execution_readiness_ignores_stale_shadow_only_quote_ttl(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            for index in range(5):
                quote = state.live_quote(False, "buy", f"MintShadowOnlyStale{index}", "0.001", True, 1, 0.00001, "pump", "WalletShadowOnlyStale", shadow_only=True)
                audit = state.storage.load_live_execution_audit(str(quote["id"]))
                self.assertIsNotNone(audit)
                audit.status = "stale"
                audit.final_status = "stale"
                audit.quote["stale"] = True
                state.storage.save_live_execution_audit(audit)

            execution = state.readiness_status()["execution_readiness"]

            self.assertEqual(execution["metrics"]["quote_attempts"], 5)
            self.assertEqual(execution["metrics"]["stale_quotes"], 0)
            self.assertEqual(execution["metrics"]["stale_quote_rate"], 0.0)
            self.assertFalse(any(gate["id"] == "quote_freshness" and gate["status"] == "fail" for gate in execution["gates"]))
            self.assertEqual(execution["status"], "shadow_ready")

    def test_execution_readiness_reports_queryable_quote_issue_taxonomy(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            state.live_quote(True, "buy", "MintCapIssue", "0.02", True, 1, 0.00001, "pump", "WalletIssues")
            state.live_quote(True, "buy", "MintSlipIssue", "0.001", True, 10, 0.00001, "pump", "WalletIssues")
            stale = state.live_quote(True, "buy", "MintStaleIssue", "0.001", True, 1, 0.00001, "pump", "WalletIssues")
            stale_audit = state.storage.load_live_execution_audit(str(stale["id"]))
            self.assertIsNotNone(stale_audit)
            stale_audit.status = "stale"
            stale_audit.final_status = "stale"
            stale_audit.quote["stale"] = True
            stale_audit.quote["error"] = "quote expired before signing"
            state.storage.save_live_execution_audit(stale_audit)
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_provider_issue",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    action="buy",
                    mint="MintProviderIssue",
                    amount="0.001",
                    status="failed",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletIssues",
                    quote={"id": "quote_provider_issue", "status": "failed", "error": "PumpPortal HTTP 500"},
                    errors=["PumpPortal HTTP 500"],
                    final_status="failed",
                )
            )

            quote_issues = state.readiness_status()["execution_readiness"]["quote_issues"]
            categories = {item["category"]: item for item in quote_issues["categories"]}

            self.assertEqual(quote_issues["total_issues"], 4)
            self.assertEqual(quote_issues["blocked_count"], 2)
            self.assertEqual(quote_issues["stale_count"], 1)
            self.assertEqual(quote_issues["failed_count"], 1)
            self.assertIn("cap_policy", categories)
            self.assertIn("slippage_policy", categories)
            self.assertIn("stale_quote", categories)
            self.assertIn("provider_or_rpc", categories)
            self.assertTrue(any("amount exceeds live max trade cap" in reason for reason in categories["cap_policy"]["reasons"]))
            self.assertTrue(any(item["audit_id"] == "liveaudit_provider_issue" for item in quote_issues["recent"]))
            self.assertIn("Review the top quote issue category", quote_issues["operator_action"])

    def test_execution_readiness_reports_stage_failure_taxonomy(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            for audit in [
                LiveExecutionAudit(
                    id="liveaudit_quote_stage",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintQuoteStage",
                    amount="0.001",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletStage",
                    status="blocked",
                    final_status="blocked",
                    quote={"id": "quote_stage_1", "status": "blocked", "error": "source trust degraded"},
                    errors=["source trust degraded"],
                ),
                LiveExecutionAudit(
                    id="liveaudit_sim_stage",
                    created_at=now + timedelta(seconds=1),
                    updated_at=now + timedelta(seconds=1),
                    action="buy",
                    mint="MintSimStage",
                    amount="0.001",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletStage",
                    status="simulation_warning",
                    final_status="simulation_warning",
                    quote={"id": "quote_stage_2", "status": "ready"},
                    simulation={"status": "warning", "warning": "simulation compute unit warning"},
                ),
                LiveExecutionAudit(
                    id="liveaudit_confirm_stage",
                    created_at=now + timedelta(seconds=2),
                    updated_at=now + timedelta(seconds=2),
                    action="buy",
                    mint="MintConfirmStage",
                    amount="0.001",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletStage",
                    status="needs_review",
                    final_status="needs_review",
                    transaction_signature="SigConfirmUnknown",
                    quote={"id": "quote_stage_3", "status": "ready"},
                    last_recovery_error="RPC confirmation timeout",
                ),
                LiveExecutionAudit(
                    id="liveaudit_reconcile_stage",
                    created_at=now + timedelta(seconds=3),
                    updated_at=now + timedelta(seconds=3),
                    action="sell",
                    mint="MintReconStage",
                    amount="10",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletStage",
                    status="needs_review",
                    final_status="needs_review",
                    transaction_signature="SigReconNeedsReview",
                    confirmation_status="confirmed",
                    reconciliation_status="needs_review",
                    quote={"id": "quote_stage_4", "status": "ready"},
                    execution_timing={"confirmed_at": (now + timedelta(seconds=4)).isoformat()},
                    errors=["ledger reconciliation mismatch"],
                ),
            ]:
                state.storage.save_live_execution_audit(audit)

            stages = state.readiness_status()["execution_readiness"]["failure_stages"]
            by_stage = {row["stage"]: row for row in stages["stages"]}

            self.assertEqual(stages["total_failures"], 4)
            self.assertEqual(by_stage["quote"]["count"], 1)
            self.assertEqual(by_stage["simulation"]["count"], 1)
            self.assertEqual(by_stage["confirmation"]["count"], 1)
            self.assertEqual(by_stage["reconciliation"]["count"], 1)
            self.assertEqual(by_stage["quote"]["categories"][0]["category"], "source_trust")
            self.assertEqual(by_stage["simulation"]["categories"][0]["category"], "simulation_warning")
            self.assertEqual(by_stage["confirmation"]["categories"][0]["category"], "provider_or_rpc")
            self.assertEqual(by_stage["reconciliation"]["categories"][0]["category"], "ledger_reconciliation")
            self.assertTrue(any(item["audit_id"] == "liveaudit_reconcile_stage" for item in stages["recent"]))

    def test_execution_readiness_recommends_bounded_policy_from_quote_pressure(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_max_slippage_pct = 3
            state.settings.live_priority_fee_cap_sol = 0.0002
            state.storage.save_settings(state.settings)
            state.ensure_settings_version("settings save", ["live_max_slippage_pct", "live_priority_fee_cap_sol"])
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            for index in range(5):
                quote = state.live_quote(True, "buy", f"MintPolicy{index}", "0.001", True, 1, 0.00001, "pump", "WalletPolicy")
                audit = state.storage.load_live_execution_audit(str(quote["id"]))
                self.assertIsNotNone(audit)
                if index < 2:
                    audit.status = "stale"
                    audit.final_status = "stale"
                    audit.quote["stale"] = True
                    audit.quote["error"] = "quote expired before signing"
                audit.shadow_comparison = {
                    "mode": "dry_run_shadow",
                    "status": "evaluated",
                    "landing_windows": [
                        {"delay_ms": 500, "status": "stale_quote", "fill_status": "missed", "outcome": "missed"},
                        {"delay_ms": 1000, "status": "evaluated", "fill_status": "filled", "outcome": "win", "estimated_pnl_sol": 0.001},
                    ],
                }
                state.storage.save_live_execution_audit(audit)
            blocked = state.live_quote(True, "buy", "MintPolicySlip", "0.001", True, 10, 0.00001, "pump", "WalletPolicy")
            self.assertEqual(blocked["status"], "blocked")

            policy = state.readiness_status()["execution_readiness"]["policy"]
            recommendation = policy["recommendation"]

            self.assertEqual(recommendation["status"], "raise_priority_fee")
            self.assertLessEqual(recommendation["suggested_slippage_pct"], state.settings.live_max_slippage_pct)
            self.assertLessEqual(recommendation["suggested_priority_fee_sol"], state.settings.live_priority_fee_cap_sol)
            self.assertGreaterEqual(recommendation["inputs"]["missed_landing_rate"], 0.25)
            self.assertIn("stale_quote", recommendation["inputs"]["issue_categories"])
            self.assertTrue(any("stale quote pressure" in reason for reason in recommendation["reasons"]))

    def test_live_quote_records_non_submitting_shadow_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            token = self.make_token()
            token.mint = "MintShadowSnap"
            token.current_price = 0.00001
            state.storage.save_token(token)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            quote = state.live_quote(True, "buy", "MintShadowSnap", "0.001", True, 1, 0.00001, "pump", "WalletShadowSnap")

            self.assertEqual(quote["status"], "ready")
            self.assertEqual(quote["shadow_comparison"]["mode"], "dry_run_shadow")
            self.assertEqual(quote["shadow_comparison"]["entry_price"], 0.00001)
            self.assertEqual(quote["shadow_comparison"]["outcome"], "pending")
            self.assertEqual(quote["transaction_signature"], "")

    def test_shadow_only_quote_collects_evidence_without_live_env_and_cannot_submit(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            token = self.make_token()
            token.mint = "MintShadowOnly"
            token.current_price = 0.00001
            state.storage.save_token(token)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            quote = state.live_quote(False, "buy", "MintShadowOnly", "0.001", True, 1, 0.00001, "pump", "WalletShadowOnly", shadow_only=True)

            self.assertEqual(quote["status"], "ready")
            self.assertTrue(quote["quote"]["shadow_only"])
            self.assertEqual(quote["shadow_comparison"]["mode"], "dry_run_shadow")
            self.assertEqual(quote["transaction_signature"], "")
            with self.assertRaisesRegex(ValueError, "shadow-only"):
                state.live_submit(str(quote["id"]), "sigshadowonly")

    def test_shadow_only_quotes_do_not_create_live_recovery_debt(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            for mint in ("MintShadowDebtOne", "MintShadowDebtTwo"):
                token = self.make_token()
                token.id = f"tok_{mint.lower()}"
                token.mint = mint
                token.current_price = 0.00001
                state.storage.save_token(token)

            first = state.live_quote(False, "buy", "MintShadowDebtOne", "0.001", True, 1, 0.00001, "pump", "WalletShadowDebt", shadow_only=True)
            second = state.live_quote(False, "buy", "MintShadowDebtTwo", "0.001", True, 1, 0.00001, "pump", "WalletShadowDebt", shadow_only=True)
            live_status = state.live_status(False, "WalletShadowDebt", "browser_wallet")

            self.assertEqual(first["status"], "ready")
            self.assertEqual(second["status"], "ready")
            self.assertEqual(live_status["unresolved_audit_count"], 0)
            self.assertFalse(any("recovery debt" in blocker.lower() for blocker in live_status["blockers"]))

    def test_stale_shadow_only_quote_does_not_create_live_recovery_debt(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            stale_at = utc_now() - timedelta(minutes=5)
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_stale_shadow_only",
                    created_at=stale_at,
                    updated_at=stale_at,
                    action="buy",
                    mint="MintStaleShadowOnly",
                    amount="0.001",
                    status="stale",
                    final_status="stale",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletShadowDebt",
                    quote={
                        "id": "quote_stale_shadow_only",
                        "created_at": stale_at.isoformat(),
                        "status": "stale",
                        "shadow_only": True,
                        "unsigned_transaction_base64": "dHgi",
                    },
                    shadow_comparison={"mode": "dry_run_shadow", "status": "waiting_for_price"},
                )
            )

            live_status = state.live_status(False, "WalletShadowDebt", "browser_wallet")

            self.assertEqual(live_status["unresolved_audit_count"], 0)
            self.assertFalse(any("recovery debt" in blocker.lower() for blocker in live_status["blockers"]))

    def test_stale_unsigned_quote_counts_as_quote_pressure_not_recovery_debt(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            quote = state.live_quote(True, "buy", "MintStaleUnsigned", "0.001", True, 1, 0.00001, "pump", "WalletStaleUnsigned")
            audit = state.storage.load_live_execution_audit(str(quote["id"]))
            self.assertIsNotNone(audit)
            audit.status = "stale"
            audit.final_status = "stale"
            audit.quote["stale"] = True
            audit.quote["error"] = "quote expired before signing"
            state.storage.save_live_execution_audit(audit)

            live_status = state.live_status(True, "WalletStaleUnsigned", "browser_wallet")
            execution = state.readiness_status()["execution_readiness"]

            self.assertEqual(live_status["unresolved_audit_count"], 0)
            self.assertFalse(any("recovery debt" in blocker.lower() for blocker in live_status["blockers"]))
            self.assertEqual(execution["metrics"]["stale_quotes"], 1)
            self.assertGreater(execution["metrics"]["stale_quote_rate"], 0)

    def test_shadow_comparison_evaluates_against_later_price(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            token = self.make_token()
            token.mint = "MintShadowEval"
            token.current_price = 0.00001
            state.storage.save_token(token)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            quote = state.live_quote(True, "buy", "MintShadowEval", "0.001", True, 1, 0.00001, "pump", "WalletShadowEval")
            audit = state.storage.load_live_execution_audit(str(quote["id"]))
            self.assertIsNotNone(audit)
            state.storage.save_price_observation(
                PriceObservation(
                    id="px_shadow_eval",
                    source="pumpportal",
                    mint="MintShadowEval",
                    observed_at=audit.created_at + timedelta(seconds=5),
                    price=0.00003,
                    price_source="direct",
                    confidence=0.9,
                    accepted=True,
                )
            )

            execution = state.readiness_status()["execution_readiness"]
            refreshed = state.storage.load_live_execution_audit(str(quote["id"]))

            self.assertEqual(execution["metrics"]["shadow_samples"], 1)
            self.assertEqual(execution["metrics"]["shadow_evaluated"], 1)
            self.assertEqual(execution["metrics"]["shadow_win_rate_pct"], 100)
            self.assertEqual(refreshed.shadow_comparison["status"], "evaluated")
            self.assertGreater(refreshed.shadow_comparison["estimated_pnl_sol"], 0)
            self.assertEqual(refreshed.shadow_comparison["outcome"], "win")

    def test_shadow_comparison_uses_take_profit_exit_rule_before_later_drop(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.02
            state.storage.save_settings(state.settings)
            state.settings.take_profit_pct = 50
            token = self.make_token()
            token.mint = "MintShadowTp"
            token.current_price = 0.00001
            state.storage.save_token(token)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            quote = state.live_quote(True, "buy", "MintShadowTp", "0.01", True, 1, 0.00001, "pump", "WalletShadowTp")
            audit = state.storage.load_live_execution_audit(str(quote["id"]))
            self.assertIsNotNone(audit)
            state.storage.save_price_observation(
                PriceObservation(
                    id="px_shadow_tp",
                    source="pumpportal",
                    mint="MintShadowTp",
                    observed_at=audit.created_at + timedelta(seconds=5),
                    price=0.000016,
                    price_source="direct",
                    confidence=0.9,
                    accepted=True,
                )
            )
            state.storage.save_price_observation(
                PriceObservation(
                    id="px_shadow_tp_later_drop",
                    source="pumpportal",
                    mint="MintShadowTp",
                    observed_at=audit.created_at + timedelta(seconds=10),
                    price=0.000005,
                    price_source="direct",
                    confidence=0.9,
                    accepted=True,
                )
            )

            state.readiness_status()
            refreshed = state.storage.load_live_execution_audit(str(quote["id"]))

            self.assertEqual(refreshed.shadow_comparison["exit_reason"], "take profit")
            self.assertEqual(refreshed.shadow_comparison["exit_price"], 0.000016)
            self.assertEqual(refreshed.shadow_comparison["outcome"], "win")

    def test_shadow_comparison_respects_minimum_hold_before_exit(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.02
            state.storage.save_settings(state.settings)
            state.settings.take_profit_pct = 50
            state.settings.stop_loss_pct = 30
            state.settings.minimum_hold_time_seconds = 10
            token = self.make_token()
            token.mint = "MintShadowMinHold"
            token.current_price = 0.00001
            state.storage.save_token(token)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            quote = state.live_quote(True, "buy", "MintShadowMinHold", "0.01", True, 1, 0.00001, "pump", "WalletShadowMinHold")
            audit = state.storage.load_live_execution_audit(str(quote["id"]))
            self.assertIsNotNone(audit)
            state.storage.save_price_observation(
                PriceObservation(
                    id="px_shadow_min_hold_early",
                    source="pumpportal",
                    mint="MintShadowMinHold",
                    observed_at=audit.created_at + timedelta(seconds=5),
                    price=0.000016,
                    price_source="direct",
                    confidence=0.9,
                    accepted=True,
                )
            )
            state.storage.save_price_observation(
                PriceObservation(
                    id="px_shadow_min_hold_stop",
                    source="pumpportal",
                    mint="MintShadowMinHold",
                    observed_at=audit.created_at + timedelta(seconds=12),
                    price=0.000006,
                    price_source="direct",
                    confidence=0.9,
                    accepted=True,
                )
            )

            state.readiness_status()
            refreshed = state.storage.load_live_execution_audit(str(quote["id"]))

            self.assertEqual(refreshed.shadow_comparison["exit_reason"], "stop loss")
            self.assertEqual(refreshed.shadow_comparison["hold_duration_seconds"], 12)
            self.assertEqual(refreshed.shadow_comparison["outcome"], "loss")

    def test_shadow_landing_windows_show_delay_sensitive_outcomes(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.02
            state.storage.save_settings(state.settings)
            state.settings.take_profit_pct = 50
            state.settings.stop_loss_pct = 30
            token = self.make_token()
            token.mint = "MintShadowDelay"
            token.current_price = 0.00001
            state.storage.save_token(token)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            quote = state.live_quote(True, "buy", "MintShadowDelay", "0.01", True, 1, 0.00001, "pump", "WalletShadowDelay")
            audit = state.storage.load_live_execution_audit(str(quote["id"]))
            self.assertIsNotNone(audit)
            for obs_id, seconds, price in [
                ("px_shadow_delay_fast", 0.1, 0.000016),
                ("px_shadow_delay_late_entry", 0.6, 0.000015),
                ("px_shadow_delay_drop", 2.5, 0.000005),
            ]:
                state.storage.save_price_observation(
                    PriceObservation(
                        id=obs_id,
                        source="pumpportal",
                        mint="MintShadowDelay",
                        observed_at=audit.created_at + timedelta(seconds=seconds),
                        price=price,
                        price_source="direct",
                        confidence=0.9,
                        accepted=True,
                    )
                )

            execution = state.readiness_status()["execution_readiness"]
            refreshed = state.storage.load_live_execution_audit(str(quote["id"]))
            windows = {window["delay_ms"]: window for window in refreshed.shadow_comparison["landing_windows"]}

            self.assertEqual(windows[0]["outcome"], "win")
            self.assertEqual(windows[0]["exit_reason"], "take profit")
            self.assertEqual(windows[500]["outcome"], "loss")
            self.assertEqual(windows[500]["exit_reason"], "stop loss")
            self.assertGreaterEqual(execution["metrics"]["shadow_landing_evaluated"], 2)
            self.assertLess(execution["metrics"]["shadow_landing_worst_pnl_sol"], 0)

    def test_shadow_landing_window_marks_stale_quote_after_expiry(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.02
            state.storage.save_settings(state.settings)
            token = self.make_token()
            token.mint = "MintShadowStaleWindow"
            token.current_price = 0.00001
            state.storage.save_token(token)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            quote = state.live_quote(True, "buy", "MintShadowStaleWindow", "0.01", True, 1, 0.00001, "pump", "WalletShadowStaleWindow")
            audit = state.storage.load_live_execution_audit(str(quote["id"]))
            self.assertIsNotNone(audit)
            audit.quote["expires_at"] = (audit.created_at + timedelta(seconds=1)).isoformat()
            state.storage.save_live_execution_audit(audit)
            state.storage.save_price_observation(
                PriceObservation(
                    id="px_shadow_stale_window",
                    source="pumpportal",
                    mint="MintShadowStaleWindow",
                    observed_at=audit.created_at + timedelta(seconds=2),
                    price=0.00002,
                    price_source="direct",
                    confidence=0.9,
                    accepted=True,
                )
            )

            state.readiness_status()
            refreshed = state.storage.load_live_execution_audit(str(quote["id"]))
            windows = {window["delay_ms"]: window for window in refreshed.shadow_comparison["landing_windows"]}

            self.assertEqual(windows[2000]["status"], "stale_quote")
            self.assertEqual(windows[2000]["fill_status"], "missed")
            self.assertEqual(windows[2000]["outcome"], "missed")

    def test_landing_calibration_uses_live_audit_timing_samples(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            token = self.make_token()
            token.mint = "MintCalibration"
            token.current_price = 0.00001
            state.storage.save_token(token)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")

            delays = [250, 750, 1500, 3000]
            for index, delay_ms in enumerate(delays):
                signer_mode = "local_hot_wallet" if index >= 2 else "browser_wallet"
                pool = "raydium" if index >= 2 else "pump"
                quote = state.live_quote(True, "buy", f"MintCalibration{index}", "0.001", True, 1, 0.00001, pool, "WalletCalibration", signer_mode=signer_mode)
                audit = state.storage.load_live_execution_audit(str(quote["id"]))
                self.assertIsNotNone(audit)
                audit.signer_mode = signer_mode
                submitted_at = audit.created_at + timedelta(milliseconds=delay_ms)
                confirmed_at = submitted_at + timedelta(milliseconds=2000)
                audit.transaction_signature = f"sigcal{index}"
                audit.status = "reconciled"
                audit.confirmation_status = "confirmed"
                audit.confirmation_checked_at = confirmed_at
                audit.execution_timing = {
                    "submitted_at": submitted_at.isoformat(),
                    "confirmed_at": confirmed_at.isoformat(),
                    "quote_to_submit_ms": delay_ms,
                    "submit_to_confirm_ms": 2000,
                    "quote_to_confirm_ms": delay_ms + 2000,
                }
                state.storage.save_live_execution_audit(audit)

            execution = state.readiness_status()["execution_readiness"]

            self.assertEqual(execution["landing_calibration"]["source"], "live_audits")
            self.assertEqual(execution["landing_calibration"]["samples"], 4)
            self.assertEqual(execution["metrics"]["live_quote_to_submit_p50_ms"], 1500)
            self.assertEqual(execution["metrics"]["live_quote_to_submit_p90_ms"], 3000)
            self.assertEqual(execution["metrics"]["live_quote_to_submit_p99_ms"], 3000)
            self.assertEqual(execution["landing_calibration"]["by_signer_mode"]["browser_wallet"]["samples"], 2)
            self.assertEqual(execution["landing_calibration"]["by_signer_mode"]["browser_wallet"]["quote_to_submit_p90_ms"], 750)
            self.assertEqual(execution["landing_calibration"]["by_signer_mode"]["local_hot_wallet"]["samples"], 2)
            self.assertEqual(execution["landing_calibration"]["by_signer_mode"]["local_hot_wallet"]["quote_to_submit_p99_ms"], 3000)
            self.assertEqual(execution["landing_calibration"]["by_pool"]["pump"]["samples"], 2)
            self.assertEqual(execution["landing_calibration"]["by_pool"]["raydium"]["quote_to_submit_p90_ms"], 3000)
            self.assertEqual(execution["landing_calibration"]["by_quote_source"]["pumpportal_local"]["samples"], 4)
            self.assertEqual(execution["landing_calibration"]["by_quote_source"]["pumpportal_local"]["quote_to_submit_p99_ms"], 3000)
            self.assertIn(1500, execution["landing_calibration"]["suggested_delay_windows_ms"])
            self.assertIn(3000, execution["landing_calibration"]["suggested_delay_windows_ms"])

    def test_execution_readiness_reports_pipeline_stage_latency(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            now = utc_now()
            token = self.make_token()
            token.id = "tok_latency"
            token.mint = "MintLatency"
            token.detected_at = now + timedelta(milliseconds=100)
            state.storage.save_token(token)
            state.storage.save_source_event(
                SourceEvent(
                    id="src_latency",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"mint": token.mint},
                    normalized_token_id=token.id,
                    status="normalized",
                )
            )
            state.storage.save_strategy_decision(
                StrategyDecisionRecord(
                    id="dec_latency",
                    token_id=token.id,
                    mint=token.mint,
                    created_at=now + timedelta(milliseconds=250),
                    engine_version="strategy-v2",
                    profile="balanced",
                    score=80,
                    allowed=True,
                    action="paper_buy",
                    reason="ok",
                    risk_reason="ok",
                )
            )
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._signature_status = lambda signature: {"ok": True, "found": True, "confirmation_status": "confirmed", "signature": signature, "err": None}
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 1.0, "error": ""}

            intent = state.create_live_intent("buy", token.mint, "0.001", True, "WalletLatency", source="paper_promoted", score=80)
            saved_intent = state.storage.load_live_intent(intent["id"])
            self.assertIsNotNone(saved_intent)
            saved_intent.created_at = now + timedelta(milliseconds=400)
            saved_intent.updated_at = saved_intent.created_at
            state.storage.save_live_intent(saved_intent)
            quote = state.quote_live_intent(True, intent["id"], 1, 0.00001, "pump")
            audit = state.storage.load_live_execution_audit(quote["id"])
            self.assertIsNotNone(audit)
            audit.created_at = now + timedelta(milliseconds=700)
            audit.quote["created_at"] = audit.created_at.isoformat()
            audit.execution_timing = {
                "submitted_at": (now + timedelta(milliseconds=900)).isoformat(),
                "quote_to_submit_ms": 200,
            }
            audit.transaction_signature = "siglatency"
            audit.status = "submitted"
            audit.final_status = "submitted"
            state.storage.save_live_execution_audit(audit)

            execution = state.readiness_status()["execution_readiness"]
            pipeline = execution["pipeline_latency"]

            self.assertEqual(pipeline["samples"], 1)
            self.assertEqual(pipeline["totals"]["source_to_token_ms"]["p50_ms"], 100)
            self.assertEqual(pipeline["totals"]["token_to_decision_ms"]["p50_ms"], 150)
            self.assertEqual(pipeline["totals"]["decision_to_intent_ms"]["p50_ms"], 150)
            self.assertEqual(pipeline["totals"]["intent_to_quote_ms"]["p50_ms"], 300)
            self.assertEqual(pipeline["totals"]["signal_to_quote_ms"]["p50_ms"], 700)
            self.assertEqual(execution["metrics"]["signal_to_quote_p50_ms"], 700)
            self.assertEqual(execution["metrics"]["intent_to_quote_p50_ms"], 300)
            self.assertEqual(pipeline["recent_samples"][0]["source_event_id"], "src_latency")
            self.assertEqual(execution["latency_summary"]["status"], "fast")
            self.assertEqual(execution["latency_summary"]["samples"], 1)
            self.assertEqual(execution["latency_summary"]["signal_to_quote_p90_ms"], 700)
            self.assertEqual(execution["latency_summary"]["quote_to_submit_p90_ms"], 200)
            self.assertFalse(execution["latency_summary"]["issues"])

    def test_live_ledger_reconciliation_needs_review_on_balance_error(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": None, "error": "rpc down"}

            intent = state.create_live_intent("buy", "Mint111", "0.001", True, "Wallet111")
            quote = state.quote_live_intent(True, intent["id"], 1, 0.00001, "pump")
            state.live_submit(quote["id"], "sig111")
            confirmed = state.live_confirm(quote["id"], "confirmed")
            ledger = state.live_ledger()

            self.assertEqual(confirmed["status"], "needs_review")
            self.assertEqual(ledger["positions"][0]["reconciliation_status"], "needs_review")
            self.assertEqual(ledger["positions"][0]["realized_pnl_confidence"], "needs_review")
            self.assertEqual(ledger["positions"][0]["unrealized_pnl_confidence"], "needs_review")
            self.assertEqual(ledger["summary"]["pnl_confidence"], "needs_review")
            self.assertGreaterEqual(ledger["positions"][0]["cost_basis_sol"], 0.001)

    def test_live_buy_reconciliation_uses_confirmed_transaction_deltas(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.2
            state.settings.live_daily_loss_cap_sol = 0.5
            state.settings.live_wallet_exposure_cap_sol = 0.5
            state.storage.save_settings(state.settings)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 500.0, "error": ""}
            state._transaction_details = lambda signature: {
                "ok": True,
                "found": True,
                "signature": signature,
                "transaction": {
                    "transaction": {
                        "signatures": [signature],
                        "message": {"accountKeys": [{"pubkey": "WalletExact"}, {"pubkey": "Other"}]},
                    },
                    "meta": {
                        "fee": 15000,
                        "preBalances": [1_000_000_000, 0],
                        "postBalances": [899_985_000, 0],
                        "preTokenBalances": [],
                        "postTokenBalances": [
                            {
                                "mint": "MintExactBuy",
                                "owner": "WalletExact",
                                "uiTokenAmount": {"uiAmount": 500.0, "amount": "500000000", "decimals": 6},
                            }
                        ],
                    },
                },
            }

            quote = state.live_quote(True, "buy", "MintExactBuy", "0.1", True, 1, 0.00001, "pump", "WalletExact")
            state.live_submit(quote["id"], "sigexactbuy")
            state.live_confirm(quote["id"], "confirmed")
            ledger = state.live_ledger("WalletExact")

            position = ledger["positions"][0]
            fill = position["fills"][0]
            accounting = fill["accounting"]
            self.assertEqual(accounting["provenance"], "transaction_meta")
            self.assertEqual(accounting["wallet_sol_delta_sol"], -0.100015)
            self.assertEqual(accounting["token_delta"], 500.0)
            self.assertEqual(fill["fee_sol"], 0.000015)
            self.assertEqual(fill["priority_fee_sol"], 0.00001)
            self.assertEqual(position["total_fees_sol"], 0.000015)
            self.assertEqual(position["total_priority_fees_sol"], 0.00001)
            self.assertEqual(position["cost_basis_sol"], 0.100015)
            self.assertEqual(position["cost_basis_breakdown"]["explanation"], "Weighted-average live cost basis from confirmed wallet deltas when transaction metadata is available.")

    def test_live_buy_reconciliation_exposes_confirmed_spend_breakdown(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.006
            state.settings.live_wallet_exposure_cap_sol = 0.01
            state.storage.save_settings(state.settings)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 22851.04325, "error": ""}
            state._transaction_details = lambda signature: {
                "ok": True,
                "found": True,
                "signature": signature,
                "transaction": {
                    "transaction": {
                        "signatures": [signature],
                        "message": {
                            "accountKeys": [
                                {"pubkey": "WalletSpend"},
                                {"pubkey": "AtaAccount"},
                                {"pubkey": "BondingCurve"},
                                {"pubkey": "Other"},
                                {"pubkey": "PlatformFee"},
                                {"pubkey": "PumpAccount"},
                            ]
                        },
                    },
                    "meta": {
                        "fee": 15000,
                        "preBalances": [123441000, 0, 7541609307, 0, 26382144, 0],
                        "postBalances": [118489588, 2074080, 7542609730, 0, 26385146, 1844400],
                        "preTokenBalances": [],
                        "postTokenBalances": [
                            {
                                "mint": "MintSpend",
                                "owner": "WalletSpend",
                                "uiTokenAmount": {"uiAmount": 22851.04325, "amount": "22851043250", "decimals": 6},
                            }
                        ],
                    },
                },
            }

            quote = state.live_quote(True, "buy", "MintSpend", "0.001", True, 5, 0.00001, "pump", "WalletSpend")
            state.live_submit(quote["id"], "sigspend")
            state.live_confirm(quote["id"], "confirmed")
            ledger = state.live_ledger("WalletSpend")

            accounting = ledger["positions"][0]["fills"][0]["accounting"]
            self.assertEqual(accounting["wallet_sol_spent_sol"], 0.004951412)
            self.assertEqual(accounting["requested_amount_sol"], 0.001)
            self.assertEqual(accounting["confirmed_spend_over_request_sol"], 0.003951412)
            self.assertEqual(accounting["spend_breakdown"]["wallet_spent_sol"], 0.004951412)
            self.assertEqual(accounting["spend_breakdown"]["network_fee_sol"], 0.000015)
            self.assertEqual(accounting["spend_breakdown"]["net_account_creation_sol"], 0.00391848)
            self.assertEqual(accounting["spend_breakdown"]["net_trade_and_program_sol"], 0.001017932)
            self.assertIn("confirmed wallet spend exceeded requested amount", ledger["positions"][0]["review_notes"])

    def test_live_status_blocks_new_buys_after_confirmed_spend_exceeds_trade_cap(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.live_max_trade_sol = 0.001
            state.settings.live_wallet_exposure_cap_sol = 0.01
            state.storage.save_settings(state.settings)
            now = utc_now()
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="pos_over_cap",
                    created_at=now,
                    updated_at=now,
                    mint="MintOverCap",
                    wallet_public_key="WalletOverCap",
                    status="open",
                    token_balance=10.0,
                    cost_basis_sol=0.004951412,
                    fills=[
                        {
                            "id": "fill_over_cap",
                            "created_at": now.isoformat(),
                            "audit_id": "audit_over_cap",
                            "intent_id": "",
                            "action": "buy",
                            "mint": "MintOverCap",
                            "amount": "0.001",
                            "amount_sol": 0.001,
                            "token_amount": 10.0,
                            "fee_sol": 0.000015,
                            "priority_fee_sol": 0.00001,
                            "signature": "sig_over_cap",
                            "accounting": {
                                "type": "buy",
                                "provenance": "transaction_meta",
                                "wallet_sol_spent_sol": 0.004951412,
                                "requested_amount_sol": 0.001,
                                "confirmed_spend_over_request_sol": 0.003951412,
                            },
                        }
                    ],
                    reconciliation_status="matched",
                )
            )

            status = state.live_status(True, "WalletOverCap", "browser_wallet")

            self.assertIn("confirmed live buy spend exceeded max trade cap; review cap/rent exposure before new buys", status["blockers"])
            self.assertFalse(status["live_execution_available"])

    def test_live_intent_decoration_reuses_autonomy_blockers_per_wallet_action(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            calls: list[tuple[str, str, str, bool]] = []

            def fake_blockers(env_live_enabled: bool, action: str, wallet_public_key: str, signer_mode: str, autonomous: bool = False) -> list[str]:
                calls.append((action, wallet_public_key, signer_mode, autonomous))
                return ["cached blocker"]

            state._live_execution_blockers = fake_blockers  # type: ignore[method-assign]
            now = utc_now()
            intents = [
                LiveExecutionIntent(
                    id=f"intent_cache_{index}",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint=f"MintCache{index}",
                    amount="0.001",
                    denominated_in_sol=True,
                    wallet_public_key="WalletCache",
                    signer_mode="browser_wallet",
                )
                for index in range(25)
            ]

            decorated = state._decorate_live_intents(intents, readiness={})

            self.assertEqual(len(decorated), 25)
            self.assertEqual(len(calls), 1)
            self.assertTrue(all(intent.autonomy_blocked for intent in decorated))

    def test_live_sell_reconciliation_uses_confirmed_net_wallet_proceeds(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            now = utc_now()
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="pos_exact_sell",
                    created_at=now,
                    updated_at=now,
                    mint="MintExactSell",
                    wallet_public_key="WalletExactSell",
                    status="open",
                    token_balance=500.0,
                    cost_basis_sol=0.100015,
                    total_fees_sol=0.000015,
                    total_priority_fees_sol=0.00001,
                    fills=[
                        {
                            "id": "fill_exact_buy",
                            "created_at": now.isoformat(),
                            "audit_id": "liveaudit_exact_buy",
                            "intent_id": "",
                            "action": "buy",
                            "mint": "MintExactSell",
                            "amount": "0.1",
                            "amount_sol": 0.1,
                            "token_amount": 500.0,
                            "price_sol": 0.0,
                            "fee_sol": 0.000015,
                            "priority_fee_sol": 0.00001,
                            "signature": "sigexactbuy",
                            "accounting": {
                                "type": "buy",
                                "provenance": "transaction_meta",
                                "wallet_sol_delta_sol": -0.100015,
                                "wallet_sol_spent_sol": 0.100015,
                                "token_delta": 500.0,
                                "network_fee_sol": 0.000015,
                                "base_fee_sol": 0.000005,
                                "priority_fee_sol": 0.00001,
                                "cost_basis_added_sol": 0.100015,
                                "cost_basis_after_sol": 0.100015,
                            },
                        }
                    ],
                    reconciliation_status="matched",
                )
            )
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 0.0, "error": ""}
            state._transaction_details = lambda signature: {
                "ok": True,
                "found": True,
                "signature": signature,
                "transaction": {
                    "transaction": {
                        "signatures": [signature],
                        "message": {"accountKeys": [{"pubkey": "WalletExactSell"}, {"pubkey": "Other"}]},
                    },
                    "meta": {
                        "fee": 15000,
                        "preBalances": [900_000_000, 0],
                        "postBalances": [1_099_985_000, 0],
                        "preTokenBalances": [
                            {
                                "mint": "MintExactSell",
                                "owner": "WalletExactSell",
                                "uiTokenAmount": {"uiAmount": 500.0, "amount": "500000000", "decimals": 6},
                            }
                        ],
                        "postTokenBalances": [],
                    },
                },
            }
            audit = LiveExecutionAudit(
                id="liveaudit_exact_sell",
                created_at=now,
                updated_at=now,
                action="sell",
                mint="MintExactSell",
                amount="100%",
                status="confirmed",
                signer_mode="browser_wallet",
                wallet_public_key="WalletExactSell",
                quote={"priority_fee_sol": 0.00001},
                request={"denominated_in_sol": False},
                transaction_signature="sigexactsell",
                confirmation_status="confirmed",
                final_status="confirmed",
            )
            state.storage.save_live_execution_audit(audit)

            state._record_live_fill(audit)
            ledger = state.live_ledger("WalletExactSell")

            position = ledger["positions"][0]
            fill = position["fills"][-1]
            accounting = fill["accounting"]
            self.assertEqual(position["status"], "closed")
            self.assertEqual(position["cost_basis_sol"], 0.0)
            self.assertEqual(position["total_fees_sol"], 0.00003)
            self.assertEqual(position["total_priority_fees_sol"], 0.00002)
            self.assertEqual(position["realized_pnl_sol"], 0.09997)
            self.assertEqual(fill["fee_sol"], 0.000015)
            self.assertEqual(fill["priority_fee_sol"], 0.00001)
            self.assertEqual(accounting["provenance"], "transaction_meta")
            self.assertEqual(accounting["wallet_sol_received_sol"], 0.199985)
            self.assertEqual(accounting["token_delta"], -500.0)
            self.assertEqual(accounting["realized_pnl_delta_sol"], 0.09997)

    def test_live_ledger_summary_exposes_net_pnl_fees_and_recent_fills(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="pos_live_net",
                    created_at=now,
                    updated_at=now,
                    mint="MintLiveNet",
                    wallet_public_key="WalletLiveNet",
                    symbol="NET",
                    status="closed",
                    token_balance=0.0,
                    cost_basis_sol=0.0,
                    realized_pnl_sol=0.09997,
                    unrealized_pnl_sol=0.0,
                    total_fees_sol=0.00003,
                    total_priority_fees_sol=0.00002,
                    fills=[
                        {
                            "id": "fill_buy_net",
                            "created_at": now.isoformat(),
                            "audit_id": "audit_buy_net",
                            "intent_id": "",
                            "action": "buy",
                            "mint": "MintLiveNet",
                            "amount": "0.1",
                            "amount_sol": 0.1,
                            "token_amount": 500.0,
                            "price_sol": 0.0,
                            "fee_sol": 0.000015,
                            "priority_fee_sol": 0.00001,
                            "signature": "sigbuynet",
                            "accounting": {"provenance": "transaction_meta", "wallet_sol_delta_sol": -0.100015, "token_delta": 500.0},
                        },
                        {
                            "id": "fill_sell_net",
                            "created_at": (now + timedelta(seconds=1)).isoformat(),
                            "audit_id": "audit_sell_net",
                            "intent_id": "",
                            "action": "sell",
                            "mint": "MintLiveNet",
                            "amount": "100%",
                            "amount_sol": 0.0,
                            "token_amount": 500.0,
                            "price_sol": 0.0,
                            "fee_sol": 0.000015,
                            "priority_fee_sol": 0.00001,
                            "signature": "sigsellnet",
                            "accounting": {
                                "provenance": "transaction_meta",
                                "wallet_sol_delta_sol": 0.199985,
                                "wallet_sol_received_sol": 0.199985,
                                "token_delta": -500.0,
                                "realized_pnl_delta_sol": 0.09997,
                            },
                        },
                    ],
                    reconciliation_status="matched",
                    realized_pnl_confidence="audited",
                    unrealized_pnl_confidence="none",
                )
            )

            ledger = state.live_ledger("WalletLiveNet")

            self.assertEqual(ledger["summary"]["net_pnl_sol"], 0.09997)
            self.assertEqual(ledger["summary"]["total_pnl_sol"], 0.09997)
            self.assertEqual(ledger["summary"]["total_fees_sol"], 0.00003)
            self.assertEqual(ledger["summary"]["total_priority_fees_sol"], 0.00002)
            self.assertEqual(len(ledger["recent_fills"]), 2)
            self.assertEqual(ledger["recent_fills"][0]["action"], "sell")
            self.assertEqual(ledger["recent_fills"][0]["wallet_sol_delta_sol"], 0.199985)
            self.assertEqual(ledger["recent_fills"][0]["realized_pnl_delta_sol"], 0.09997)

    def test_live_recovery_confirms_and_reconciles_submitted_audit(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 100.0, "error": ""}
            state._signature_status = lambda signature: {
                "ok": True,
                "found": True,
                "signature": signature,
                "confirmation_status": "confirmed",
                "err": None,
                "slot": 123,
            }

            quote = state.live_quote(True, "buy", "MintRecover", "0.001", True, 1, 0.00001, "pump", "WalletRecover")
            submitted = state.live_submit(quote["id"], "sigrecover")
            recovered = state.recover_live_audit(submitted["id"])
            status = state.live_status(True, "WalletRecover")

            self.assertEqual(recovered["status"], "reconciled")
            self.assertEqual(recovered["confirmation_status"], "confirmed")
            self.assertEqual(recovered["reconciliation_status"], "matched")
            self.assertEqual(status["unresolved_audit_count"], 0)

    def test_live_recovery_keeps_unknown_signature_unresolved(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._signature_status = lambda signature: {"ok": True, "found": False, "confirmation_status": "not_found", "signature": signature}

            quote = state.live_quote(True, "buy", "MintUnknown", "0.001", True, 1, 0.00001, "pump", "WalletUnknown")
            submitted = state.live_submit(quote["id"], "sigunknown")
            recovered = state.recover_live_audit(submitted["id"])

            self.assertEqual(recovered["status"], "submitted")
            self.assertEqual(recovered["recovery_attempts"], 1)
            self.assertIn("not visible", recovered["recommended_action"])

    def test_live_recovery_escalates_unknown_signature_after_retry_limit(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._signature_status = lambda signature: {"ok": True, "found": False, "confirmation_status": "not_found", "signature": signature}

            quote = state.live_quote(True, "buy", "MintRetryLimit", "0.001", True, 1, 0.00001, "pump", "WalletRetry")
            submitted = state.live_submit(quote["id"], "sigretrylimit")
            recovered = submitted
            for _ in range(state.live_recovery_max_attempts):
                recovered = state.recover_live_audit(submitted["id"])

            self.assertEqual(recovered["status"], "needs_review")
            self.assertEqual(recovered["final_status"], "needs_review")
            self.assertEqual(recovered["recovery_attempts"], state.live_recovery_max_attempts)
            self.assertIn("retry limit", recovered["recommended_action"].lower())
            self.assertIn("not found", recovered["last_recovery_error"])
            self.assertTrue(any("not found" in warning for warning in recovered["warnings"]))

            poll = state.poll_live_audits(True)
            unchanged = state.storage.load_live_execution_audit(submitted["id"])

            self.assertTrue(poll["skipped"])
            self.assertEqual(unchanged.recovery_attempts, state.live_recovery_max_attempts)

    def test_live_recovery_rpc_failure_records_review_warning(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._signature_status = lambda signature: {"ok": False, "found": False, "confirmation_status": "", "signature": signature, "error": "RPC down"}

            quote = state.live_quote(True, "buy", "MintRpcDown", "0.001", True, 1, 0.00001, "pump", "WalletRpc")
            submitted = state.live_submit(quote["id"], "sigrpc")
            recovered = state.recover_live_audit(submitted["id"])

            self.assertEqual(recovered["status"], "needs_review")
            self.assertEqual(recovered["last_recovery_error"], "RPC down")
            self.assertIn("RPC down", recovered["warnings"])

    def test_live_poller_skips_without_env_or_audits(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            disabled = state.poll_live_audits(False)
            enabled_empty = state.poll_live_audits(True)

            self.assertTrue(disabled["skipped"])
            self.assertIn("LIVE_TRADING_ENABLED", disabled["reason"])
            self.assertTrue(enabled_empty["skipped"])
            self.assertEqual(enabled_empty["reason"], "no unresolved submitted audits")

    def test_live_recovery_endpoint_path_never_submits_transactions(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 1.0, "error": ""}
            state._signature_status = lambda signature: {"ok": True, "found": True, "confirmation_status": "finalized", "signature": signature, "err": None}

            quote = state.live_quote(True, "buy", "MintNoSubmit", "0.001", True, 1, 0.00001, "pump", "WalletNoSubmit")
            state.live_submit(quote["id"], "signosubmit")
            summary = state.recover_unresolved_live_audits()

            self.assertEqual(summary["summary"]["checked"], 1)
            self.assertEqual(state.storage.count_live_execution_audits(), 1)

    def test_live_ledger_pnl_uses_wallet_balance_and_latest_price(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            token = self.make_token()
            token.mint = "MintPnl"
            token.current_price = 0.00002
            state.storage.save_token(token)
            state.storage.save_price_observation(
                PriceObservation(
                    id="px_live_pnl",
                    source="pumpportal",
                    mint="MintPnl",
                    observed_at=utc_now(),
                    price=0.00002,
                    price_source="direct",
                    confidence=0.9,
                    accepted=True,
                )
            )
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": 100.0, "error": ""}

            intent = state.create_live_intent("buy", "MintPnl", "0.001", True, "WalletPnl")
            quote = state.quote_live_intent(True, intent["id"], 1, 0.00001, "pump")
            state.live_submit(quote["id"], "sigpnl")
            state.live_confirm(quote["id"], "confirmed")
            ledger = state.live_ledger("WalletPnl")
            other_wallet = state.live_ledger("OtherWallet")

            self.assertEqual(len(ledger["positions"]), 1)
            self.assertGreater(ledger["summary"]["unrealized_pnl_sol"], 0)
            self.assertEqual(ledger["summary"]["pnl_confidence"], "estimated")
            self.assertEqual(ledger["positions"][0]["mark_price_source"], "pumpportal:direct")
            self.assertEqual(ledger["positions"][0]["mark_price_confidence"], 0.9)
            self.assertEqual(ledger["positions"][0]["realized_pnl_confidence"], "audited")
            self.assertEqual(ledger["positions"][0]["unrealized_pnl_confidence"], "estimated")
            self.assertIsNotNone(ledger["positions"][0]["balance_age_seconds"])
            self.assertLessEqual(ledger["positions"][0]["balance_age_seconds"], 2)
            self.assertEqual(ledger["summary"]["stale_balance_positions"], 0)
            self.assertEqual(other_wallet["positions"], [])

    def test_live_positions_only_probe_open_wallet_ledger_mints(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            for mint, wallet, status, balance in (
                ("MintOpen", "WalletA", "open", 12.5),
                ("MintClosed", "WalletA", "closed", 0.0),
                ("MintOther", "WalletB", "open", 9.0),
            ):
                state.storage.save_live_execution_audit(
                    LiveExecutionAudit(
                        id=f"audit_{mint}",
                        created_at=now,
                        updated_at=now,
                        action="buy",
                        mint=mint,
                        amount="0.001",
                        wallet_public_key=wallet,
                        signer_mode="browser_wallet",
                        status="reconciled",
                    )
                )
                state.storage.save_live_ledger_position(
                    LiveLedgerPosition(
                        id=f"pos_{mint}",
                        created_at=now,
                        updated_at=now,
                        mint=mint,
                        wallet_public_key=wallet,
                        status=status,
                        token_balance=balance,
                        reconciliation_status="matched",
                    )
                )

            calls: list[tuple[str, str]] = []

            class FakeSolanaClient:
                def __init__(self, rpc_url: str) -> None:
                    self.rpc_url = rpc_url

                def token_balance(self, wallet_address: str, mint: str) -> float:
                    calls.append((wallet_address, mint))
                    return 12.5

            with patch("app.core.state.SolanaReadOnlyClient", FakeSolanaClient):
                positions = state.live_positions("WalletA")

            self.assertEqual(calls, [("WalletA", "MintOpen")])
            self.assertEqual([position["mint"] for position in positions], ["MintOpen"])
            self.assertEqual(positions[0]["token_balance"], 12.5)

    def test_performance_analytics_include_wallet_scoped_live_rows(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="pos_wallet_a",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    mint="MintWalletA",
                    wallet_public_key="WalletA",
                    status="open",
                    token_balance=100,
                    cost_basis_sol=0.01,
                    realized_pnl_sol=0.002,
                    unrealized_pnl_sol=0.003,
                    total_fees_sol=0.0002,
                    total_priority_fees_sol=0.0001,
                    reconciliation_status="matched",
                    realized_pnl_confidence="audited",
                    unrealized_pnl_confidence="estimated",
                    balance_verified_at=utc_now(),
                    balance_age_seconds=0,
                )
            )
            state.storage.save_live_ledger_position(
                LiveLedgerPosition(
                    id="pos_wallet_b",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    mint="MintWalletB",
                    wallet_public_key="WalletB",
                    status="closed",
                    token_balance=0,
                    cost_basis_sol=0,
                    realized_pnl_sol=-0.004,
                    unrealized_pnl_sol=0,
                    total_fees_sol=0.0001,
                    reconciliation_status="needs_review",
                    realized_pnl_confidence="unknown",
                )
            )

            analytics = state.performance_analytics()
            wallets = {row["wallet_public_key"]: row for row in analytics["wallets"]}

            self.assertEqual(analytics["wallet_summary"]["wallets"], 2)
            self.assertEqual(wallets["WalletA"]["total_pnl_sol"], 0.005)
            self.assertEqual(wallets["WalletB"]["pnl_confidence"], "needs_review")
            self.assertEqual(analytics["mode_comparison"]["live"]["pnl_sol"], 0.001)
            self.assertEqual(analytics["mode_comparison"]["live"]["source"], "wallet-scoped live ledger")
            self.assertEqual(analytics["mode_comparison"]["paper"]["samples"], 0)

    def test_performance_analytics_reads_latest_backtest_run_fields(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            token = self.make_token()
            token.status = TokenStatus.PAPER_SOLD
            token.score = 95
            token.pnl_sol = 0.012345
            state.tokens.appendleft(token)
            state.replay_backtest(limit=1)

            analytics = state.performance_analytics()
            replay = analytics["mode_comparison"]["replay"]

            self.assertEqual(replay["samples"], 1)
            self.assertEqual(replay["pnl_sol"], 0.012345)
            self.assertEqual(replay["confidence"], "fingerprinted")
            self.assertEqual(replay["source"], "tokens")

    def test_live_full_token_amount_sell_closes_position(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            token = self.make_token()
            token.mint = "MintClose"
            token.current_price = 0.00002
            state.storage.save_token(token)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            balances = iter([10.0, 10.0, 0.0])
            state._wallet_token_balance = lambda wallet, mint: {"wallet_public_key": wallet, "mint": mint, "token_balance": next(balances), "error": ""}

            buy_intent = state.create_live_intent("buy", "MintClose", "0.001", True, "WalletClose")
            buy_quote = state.quote_live_intent(True, buy_intent["id"], 1, 0.00001, "pump")
            state.live_submit(buy_quote["id"], "sigbuy")
            state.live_confirm(buy_quote["id"], "confirmed")

            sell_intent = state.create_live_intent("sell", "MintClose", "10", False, "WalletClose")
            sell_quote = state.quote_live_intent(True, sell_intent["id"], 1, 0.00001, "pump")
            state.live_submit(sell_quote["id"], "sigsell")
            state.live_confirm(sell_quote["id"], "confirmed")
            ledger = state.live_ledger("WalletClose")

            self.assertEqual(len(ledger["positions"]), 1)
            self.assertEqual(ledger["positions"][0]["status"], "closed")
            self.assertEqual(ledger["positions"][0]["token_balance"], 0.0)
            self.assertEqual(ledger["summary"]["open_positions"], 0)
            self.assertEqual(ledger["positions"][0]["cost_basis_method"], "weighted_average")
            self.assertEqual(ledger["positions"][0]["cost_basis_breakdown"]["buy_fills"], 1)
            self.assertEqual(ledger["positions"][0]["cost_basis_breakdown"]["sell_fills"], 1)
            self.assertEqual(ledger["positions"][0]["cost_basis_breakdown"]["remaining_basis_sol"], 0.0)
            realized_event = ledger["positions"][0]["realized_pnl_events"][-1]
            self.assertEqual(realized_event["sale_fraction"], 1.0)
            self.assertGreater(realized_event["cost_basis_consumed_sol"], 0)
            self.assertGreater(realized_event["estimated_proceeds_sol"], 0)
            self.assertLess(realized_event["realized_pnl_delta_sol"], 0)
            self.assertIn("estimated", realized_event["provenance"])

    def test_operator_session_report_includes_recovery_and_action_items(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.kill_switch_enabled = True
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_report",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    action="buy",
                    mint="MintReport",
                    amount="0.001",
                    status="submitted",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletReport",
                    transaction_signature="sigreport",
                )
            )

            report = state.operator_session_report("24h", "WalletReport")

            self.assertEqual(report["artifact_type"], "cryptoarc_operator_session_report")
            self.assertEqual(report["timeframe"], "24h")
            self.assertEqual(report["live_recovery"]["unresolved_audits"][0]["id"], "liveaudit_report")
            self.assertEqual(report["open_risk"]["status"], "blocked")
            self.assertEqual(report["open_risk"]["unresolved_audits"], 1)
            self.assertEqual(report["open_risk"]["wallet_exposure_cap_sol"], state.settings.live_wallet_exposure_cap_sol)
            self.assertIn("unresolved live audit recovery debt", report["open_risk"]["blockers"])
            self.assertIn("paper", report["mode_comparison"])
            self.assertIn("live", report["mode_comparison"])
            self.assertIn("source_quality", report)
            self.assertIn("normalized_ratio", report["source_quality"])
            self.assertTrue(any("unresolved live audit" in item.lower() for item in report["action_items"]))
            self.assertTrue(any("kill switch" in item.lower() for item in report["action_items"]))

    def test_evidence_mode_separation_keeps_paper_replay_shadow_and_live_distinct(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.storage.save_trade(
                TradeRecord(
                    id="trd_mode_paper",
                    token_id="tok_mode_paper",
                    mode="paper",
                    strategy_profile="balanced",
                    entry_price=0.00001,
                    exit_price=0.00002,
                    amount_sol=0.1,
                    pnl_sol=0.02,
                    entry_reason="test",
                    exit_reason="take profit",
                    opened_at=now,
                    closed_at=now,
                    source_price_confidence=0.9,
                )
            )
            state.storage.save_backtest_run(
                BacktestRun(
                    id="bt_mode",
                    created_at=now,
                    profile="balanced",
                    risk_tolerance="medium",
                    tokens_replayed=8,
                    paper_buys=3,
                    skips=5,
                    wins=2,
                    losses=1,
                    win_rate_pct=66,
                    estimated_pnl_sol=0.03,
                    max_drawdown_sol=0.01,
                    profit_factor=2.0,
                    replay_source="raw_source_events",
                )
            )
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="shadow_mode",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintShadow",
                    amount="0.001",
                    status="ready",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletMode",
                    final_status="ready",
                    shadow_comparison={"status": "evaluated", "estimated_pnl_sol": 0.004, "outcome": "win"},
                )
            )
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="manual_mode",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintManual",
                    amount="0.001",
                    status="submitted",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletMode",
                    transaction_signature="sigmanual",
                    final_status="submitted",
                )
            )
            intent = LiveExecutionIntent(
                id="intent_auto_mode",
                created_at=now,
                updated_at=now,
                action="buy",
                mint="MintAuto",
                amount="0.001",
                denominated_in_sol=True,
                signer_mode="local_hot_wallet",
                wallet_public_key="WalletMode",
                source="paper_promoted",
                status="submitted",
                audit_id="auto_mode",
            )
            state.storage.save_live_intent(intent)
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="auto_mode",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintAuto",
                    amount="0.001",
                    status="submitted",
                    signer_mode="local_hot_wallet",
                    wallet_public_key="WalletMode",
                    transaction_signature="sigauto",
                    final_status="submitted",
                    intent_id=intent.id,
                    request=intent.to_dict(),
                )
            )

            report = state.evidence_mode_separation_report()
            rows = {row["mode"]: row for row in report["modes"]}

            self.assertEqual(report["artifact_type"], "cryptoarc_evidence_mode_separation")
            self.assertTrue(report["ready"])
            self.assertEqual(rows["paper"]["samples"], 1)
            self.assertEqual(rows["replay"]["samples"], 1)
            self.assertEqual(rows["shadow"]["samples"], 1)
            self.assertEqual(rows["shadow"]["evaluated"], 1)
            self.assertEqual(rows["manual_live"]["samples"], 1)
            self.assertEqual(rows["autonomous_live"]["samples"], 1)
            self.assertEqual(rows["autonomous_live"]["sources"], ["paper_promoted"])
            self.assertIn("paper trades", rows["paper"]["source"])
            self.assertIn("shadow_comparison", rows["shadow"]["source"])
            self.assertFalse(report["contamination_warnings"])

    def test_setup_readiness_report_separates_paper_blockers_from_warnings(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            report = state.setup_readiness_report(env_live_enabled=False, local_auth_enabled=False)
            gate_status = {gate["id"]: gate["status"] for gate in report["gates"]}

            self.assertEqual(report["artifact_type"], "cryptoarc_setup_readiness")
            self.assertTrue(report["ready_for_paper"])
            self.assertEqual(report["status"], "review")
            self.assertEqual(gate_status["mode"], "pass")
            self.assertEqual(gate_status["paper_settings"], "pass")
            self.assertEqual(gate_status["auth"], "warn")
            self.assertEqual(gate_status["backup"], "warn")
            self.assertFalse(report["blockers"])
            self.assertTrue(any("paper monitoring" in item.lower() for item in report["next_steps"]))
            self.assertIn("privacy_note", report)

            state.settings.mode = BotMode.LIVE_LOCKED
            state.settings.detect_new_tokens = False
            state.settings.trade_size_sol = 0
            blocked = state.setup_readiness_report(env_live_enabled=True, local_auth_enabled=True)
            blocked_status = {gate["id"]: gate["status"] for gate in blocked["gates"]}

            self.assertFalse(blocked["ready_for_paper"])
            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(blocked_status["mode"], "fail")
            self.assertEqual(blocked_status["source_detection"], "fail")
            self.assertEqual(blocked_status["paper_settings"], "fail")
            self.assertTrue(any("paper" in blocker.lower() for blocker in blocked["blockers"]))

    def test_pilot_readiness_report_combines_acceptance_gates(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.kill_switch_enabled = True
            state.storage.create_backup_artifact()

            report = state.pilot_readiness_report(False, "WalletPilot", "browser_wallet")
            gate_ids = {gate["id"] for gate in report["gates"]}

            self.assertEqual(report["artifact_type"], "cryptoarc_tiny_pilot_readiness")
            self.assertEqual(report["status"], "blocked")
            self.assertFalse(report["ready"])
            self.assertIn("env_live_enabled", gate_ids)
            self.assertIn("source_trust", gate_ids)
            self.assertIn("source_soak", gate_ids)
            self.assertIn("strategy_promotion", gate_ids)
            self.assertIn("execution_shadow", gate_ids)
            self.assertIn("backup", gate_ids)
            self.assertIn("ledger_confidence", gate_ids)
            self.assertIn("manual_live_proof", gate_ids)
            self.assertIn("live_status", report["evidence"])
            self.assertIn("live_ledger", report["evidence"])
            self.assertIn("source_soak", report["evidence"])
            self.assertTrue(any("manual live" in blocker.lower() for blocker in report["blockers"]))
            runbook = report["runbook_checklist"]
            runbook_ids = [item["id"] for item in runbook]
            self.assertEqual(runbook_ids, ["launch", "run", "stop", "recover", "review"])
            self.assertEqual(runbook[0]["label"], "Launch")
            self.assertEqual(runbook[0]["status"], "blocked")
            self.assertTrue(any("LIVE_TRADING_ENABLED" in item for item in runbook[0]["blockers"]))
            self.assertTrue(any(item["command"] == "scripts\\verify.ps1" for item in runbook[0]["actions"]))
            self.assertTrue(any("kill switch" in item["label"].lower() for item in runbook[2]["actions"]))
            self.assertTrue(any("post-run review" in item["label"].lower() for item in runbook[4]["actions"]))
            self.assertTrue(any("kill-switch" in item["label"].lower() or "kill switch" in item["label"].lower() for item in runbook[4]["actions"]))
            self.assertTrue(any("LIVE_TRADING_ENABLED" in blocker for blocker in report["blockers"]))
            self.assertTrue(any("kill switch" in blocker.lower() for blocker in report["blockers"]))
            self.assertIn("privacy_note", report)

    def test_pilot_readiness_requires_local_auth(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            without_auth = state.pilot_readiness_report(local_auth_enabled=False)
            with_auth = state.pilot_readiness_report(local_auth_enabled=True)
            without_auth_gates = {gate["id"]: gate for gate in without_auth["gates"]}
            with_auth_gates = {gate["id"]: gate for gate in with_auth["gates"]}

            self.assertIn("local_auth", without_auth_gates)
            self.assertIn("local_auth", with_auth_gates)
            without_auth_gate = without_auth_gates["local_auth"]
            with_auth_gate = with_auth_gates["local_auth"]

            self.assertEqual(without_auth_gate["status"], "fail")
            self.assertIn("dashboard password", without_auth_gate["reason"].lower())
            self.assertIn(without_auth_gate["reason"], without_auth["blockers"])
            self.assertEqual(with_auth_gate["status"], "pass")
            self.assertNotIn(with_auth_gate["reason"], with_auth["blockers"])

    def test_pilot_readiness_requires_operator_visible_cap_settings_version(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            state.settings.live_max_trade_sol = 0.01
            state.settings.live_daily_loss_cap_sol = 0.05
            state.settings.live_wallet_exposure_cap_sol = 0.1
            state.settings.live_max_open_positions = 1
            state.settings.live_max_slippage_pct = 5
            state.settings.live_priority_fee_cap_sol = 0.0001
            state.settings.live_session_acknowledged = True
            state.storage.create_backup_artifact()

            unaudited = state.pilot_readiness_report(False, "WalletPilot", "browser_wallet")
            gate_status = {gate["id"]: gate["status"] for gate in unaudited["gates"]}

            self.assertEqual(gate_status["policy_caps"], "fail")
            self.assertTrue(any("operator intent" in blocker.lower() for blocker in unaudited["blockers"]))

            state.ensure_settings_version("settings save", list(state.LIVE_CAP_SETTING_KEYS))
            audited = state.pilot_readiness_report(False, "WalletPilot", "browser_wallet")
            gate_status = {gate["id"]: gate["status"] for gate in audited["gates"]}

            self.assertEqual(gate_status["policy_caps"], "pass")
            self.assertFalse(any("operator intent" in blocker.lower() for blocker in audited["blockers"]))

    def test_pilot_readiness_blocks_when_configured_direct_source_soak_is_incomplete(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(
                database_path=str(Path(directory) / "test.db"),
                default_solana_wss_endpoint="wss://example.invalid",
                default_solana_logs_mentions_address="PumpFunProgram111",
            )
            self.configure_live_caps(state)

            report = state.pilot_readiness_report(True, "WalletPilot", "browser_wallet", local_auth_enabled=True)
            gate_status = {gate["id"]: gate["status"] for gate in report["gates"]}

            self.assertEqual(gate_status["source_soak"], "fail")
            self.assertTrue(report["evidence"]["source_soak"]["hard_required"])
            self.assertTrue(any("source-soak" in blocker.lower() for blocker in report["blockers"]))

    def test_pilot_readiness_requires_connected_recent_pumpportal_source(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            now = utc_now()
            for index in range(12):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_historical_launch_{index}",
                        source="pumpportal",
                        received_at=now - timedelta(minutes=30),
                        raw_payload={"txType": "create", "mint": f"MintHistorical{index}", "symbol": f"HIST{index}"},
                        normalized_token_id=f"tok_historical_{index}",
                        status="normalized",
                    )
                )
            state.source_status.status = "offline"
            state.source_status.message = "Source is idle"
            state.source_status.last_event_at = None
            state.source_status.raw_events_seen = 0
            state.source_status.normalized_events = 0

            report = state.pilot_readiness_report(True, "WalletPilot", "browser_wallet", local_auth_enabled=True)
            gate_status = {gate["id"]: gate["status"] for gate in report["gates"]}

            self.assertEqual(report["evidence"]["source"]["trust_state"], "trusted")
            self.assertEqual(gate_status["source_trust"], "fail")
            self.assertTrue(any("source" in blocker.lower() and ("connected" in blocker.lower() or "recent" in blocker.lower()) for blocker in report["blockers"]))

    def test_pilot_readiness_requires_archived_pumpportal_source_events(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state.storage.clear_source_events()

            report = state.pilot_readiness_report(True, "WalletPilot", "browser_wallet", local_auth_enabled=True)
            gate_status = {gate["id"]: gate["status"] for gate in report["gates"]}

            self.assertEqual(gate_status["source_trust"], "fail")
            self.assertTrue(any("archived pumpportal" in blocker.lower() for blocker in report["blockers"]))

    def test_pilot_readiness_requires_saved_ready_source_soak_snapshot_when_direct_required(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(
                database_path=str(Path(directory) / "test.db"),
                default_solana_wss_endpoint="wss://example.invalid",
                default_solana_logs_mentions_address="PumpFunProgram111",
            )
            self.configure_live_caps(state)
            self.seed_ready_source_soak_events(state)

            without_snapshot = state.pilot_readiness_report(True, "WalletPilot", "browser_wallet", local_auth_enabled=True)
            gate_status = {gate["id"]: gate["status"] for gate in without_snapshot["gates"]}

            self.assertEqual(gate_status["source_soak"], "pass")
            self.assertEqual(gate_status["source_soak_history"], "fail")
            self.assertTrue(any("source-soak snapshot" in blocker.lower() for blocker in without_snapshot["blockers"]))

            state.record_source_soak_snapshot(limit=200)
            with_snapshot = state.pilot_readiness_report(True, "WalletPilot", "browser_wallet", local_auth_enabled=True)
            gate_status = {gate["id"]: gate["status"] for gate in with_snapshot["gates"]}

            self.assertEqual(gate_status["source_soak"], "pass")
            self.assertEqual(gate_status["source_soak_history"], "pass")

    def test_pilot_readiness_rejects_stale_ready_source_soak_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(
                database_path=str(Path(directory) / "test.db"),
                default_solana_wss_endpoint="wss://example.invalid",
                default_solana_logs_mentions_address="PumpFunProgram111",
            )
            self.configure_live_caps(state)
            self.seed_ready_source_soak_events(state)
            stale_created_at = (utc_now() - timedelta(hours=25)).isoformat()
            state.storage.save_source_soak_snapshot(
                {
                    "id": "source_soak_stale_ready",
                    "created_at": stale_created_at,
                    "generated_at": stale_created_at,
                    "status": "ready",
                    "ready": True,
                    "summary": {"direct_events": 20, "match_rate": 1.0, "decoded_create_rate": 1.0},
                }
            )

            stale_report = state.pilot_readiness_report(True, "WalletPilot", "browser_wallet", local_auth_enabled=True)
            stale_gate_status = {gate["id"]: gate["status"] for gate in stale_report["gates"]}
            stale_history = stale_report["evidence"]["source_soak"]["history_summary"]

            self.assertEqual(stale_gate_status["source_soak"], "pass")
            self.assertEqual(stale_gate_status["source_soak_history"], "fail")
            self.assertFalse(stale_history["latest_ready_recent"])
            self.assertGreater(stale_history["latest_ready_age_hours"], 24)
            self.assertTrue(any("within 24 hours" in blocker.lower() for blocker in stale_report["blockers"]))

            state.record_source_soak_snapshot(limit=200)
            fresh_report = state.pilot_readiness_report(True, "WalletPilot", "browser_wallet", local_auth_enabled=True)
            fresh_gate_status = {gate["id"]: gate["status"] for gate in fresh_report["gates"]}
            fresh_history = fresh_report["evidence"]["source_soak"]["history_summary"]

            self.assertEqual(fresh_gate_status["source_soak_history"], "pass")
            self.assertTrue(fresh_history["latest_ready_recent"])

    def test_pilot_readiness_rejects_stale_shadow_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            stale_at = utc_now() - timedelta(hours=25)
            for index in range(5):
                state.storage.save_live_execution_audit(
                    LiveExecutionAudit(
                        id=f"liveaudit_stale_shadow_{index}",
                        created_at=stale_at,
                        updated_at=stale_at,
                        action="buy",
                        mint=f"MintStaleShadow{index}",
                        amount="0.001",
                        status="ready",
                        final_status="ready",
                        signer_mode="browser_wallet",
                        wallet_public_key="WalletPilot",
                        quote={"id": f"quote_stale_shadow_{index}", "created_at": stale_at.isoformat(), "stale": False},
                        shadow_comparison={
                            "mode": "dry_run_shadow",
                            "status": "evaluated",
                            "quoted_at": stale_at.isoformat(),
                            "estimated_pnl_sol": 0.002,
                            "outcome": "win",
                        },
                    )
                )

            report = state.pilot_readiness_report(True, "WalletPilot", "browser_wallet", local_auth_enabled=True)
            gate_status = {gate["id"]: gate["status"] for gate in report["gates"]}
            execution_metrics = report["evidence"]["readiness"]["execution_readiness"]["metrics"]

            self.assertEqual(execution_metrics["shadow_evaluated"], 5)
            self.assertEqual(execution_metrics["recent_shadow_evaluated"], 0)
            self.assertEqual(gate_status["shadow_samples"], "fail")
            self.assertTrue(any("24 hours" in blocker.lower() for blocker in report["blockers"]))

    def test_pilot_readiness_bubbles_pumpportal_shadow_funding_blocker(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            now = utc_now()
            state.storage.save_source_event(
                SourceEvent(
                    id="src_pilot_shadow_funding_blocker",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"message": "'subscribeTokenTrade' and 'subscribeAccountTrade' methods are only available when connecting with an API key funded with at least 0.02 SOL."},
                    status="status",
                    message="'subscribeTokenTrade' and 'subscribeAccountTrade' methods are only available when connecting with an API key funded with at least 0.02 SOL.",
                )
            )
            for index in range(5):
                state.live_quote(True, "buy", f"MintPilotFunding{index}", "0.001", True, 1, 0.00001, "pump", "WalletPilot")

            report = state.pilot_readiness_report(True, "WalletPilot", "browser_wallet", local_auth_enabled=True)

            self.assertTrue(any("funded API key" in blocker for blocker in report["blockers"]))
            self.assertTrue(any("funded API key" in blocker for stage in report["runbook_checklist"] for blocker in stage["blockers"]))

    def test_release_readiness_report_tracks_docs_scripts_and_live_blockers(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.settings.live_trading_enabled = True
            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_release_debt",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintRelease",
                    amount="0.001",
                    status="submitted",
                    final_status="submitted",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletRelease",
                    transaction_signature="sigrelease",
                    reconciliation_status="pending",
                )
            )

            report = state.release_readiness_report("0.1.0", env_live_enabled=False, local_auth_enabled=False)
            gate_status = {gate["id"]: gate["status"] for gate in report["gates"]}

            self.assertEqual(report["artifact_type"], "cryptoarc_release_readiness")
            self.assertEqual(report["status"], "blocked")
            self.assertFalse(report["ready"])
            self.assertEqual(gate_status["changelog"], "pass")
            self.assertEqual(gate_status["release_checklist"], "pass")
            self.assertEqual(gate_status["verify_script"], "pass")
            self.assertEqual(gate_status["bootstrap_script"], "pass")
            self.assertEqual(gate_status["doctor_script"], "pass")
            self.assertEqual(gate_status["frontend_audit"], "pass")
            self.assertEqual(gate_status["schema"], "pass")
            self.assertEqual(gate_status["live_disabled"], "fail")
            self.assertEqual(gate_status["recovery_debt"], "fail")
            self.assertEqual(gate_status["manual_verification"], "warn")
            self.assertFalse(any("solana advisory" in warning.lower() for warning in report["warnings"]))
            self.assertTrue(any("live execution disabled" in blocker.lower() for blocker in report["blockers"]))
            self.assertTrue(any("unresolved live audits" in blocker.lower() for blocker in report["blockers"]))
            self.assertTrue(report["evidence"]["scripts"]["doctor_present"])
            self.assertTrue(report["evidence"]["scripts"]["frontend_audit_present"])
            self.assertFalse(report["evidence"]["dependency_audit"]["known_chain_present"])
            self.assertEqual(report["evidence"]["dependency_audit"]["status"], "ready")
            self.assertIsNone(report["evidence"]["dependency_audit"]["acknowledged_exception"])
            self.assertIn("unresolved_audits", report["evidence"])
            self.assertIn("privacy_note", report)

    def test_frontend_dependency_audit_policy_preserves_vulnerable_uuid_review(self) -> None:
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            frontend_root = repo_root / "frontend"
            scripts_root = repo_root / "scripts"
            frontend_root.mkdir()
            scripts_root.mkdir()
            (frontend_root / "package-lock.json").write_text(
                json.dumps(
                    {
                        "packages": {
                            "node_modules/@solana/web3.js": {"version": "1.98.4"},
                            "node_modules/jayson": {"version": "4.3.0"},
                            "node_modules/uuid": {"version": "11.1.0"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            audit_script = scripts_root / "audit-frontend.ps1"
            audit_script.write_text("# fixture", encoding="utf-8")
            state = BotState(database_path=str(repo_root / "test.db"))

            policy = state._frontend_dependency_audit_policy(repo_root, audit_script)

            self.assertEqual(policy["status"], "review")
            self.assertTrue(policy["known_chain_present"])
            self.assertIn("@solana/web3.js -> jayson -> uuid", policy["acknowledged_exception"])

    def test_frontend_dependency_audit_policy_blocks_missing_or_invalid_lockfile(self) -> None:
        for fixture_name, lock_contents in (("missing", None), ("invalid", "{not-json")):
            with self.subTest(fixture=fixture_name), TemporaryDirectory() as directory:
                repo_root = Path(directory)
                frontend_root = repo_root / "frontend"
                scripts_root = repo_root / "scripts"
                frontend_root.mkdir()
                scripts_root.mkdir()
                if lock_contents is not None:
                    (frontend_root / "package-lock.json").write_text(lock_contents, encoding="utf-8")
                audit_script = scripts_root / "audit-frontend.ps1"
                audit_script.write_text("# fixture", encoding="utf-8")
                state = BotState(database_path=str(repo_root / "test.db"))

                policy = state._frontend_dependency_audit_policy(repo_root, audit_script)

                self.assertEqual(policy["status"], "blocked")
                self.assertIsNone(policy["acknowledged_exception"])
                self.assertTrue(any("package-lock.json" in blocker for blocker in policy["blockers"]))
                self.assertIn("package-lock.json", policy["operator_action"])

    def test_frontend_dependency_audit_policy_treats_patched_prereleases_as_affected(self) -> None:
        for uuid_version in ("11.1.1-beta.1", "12.0.1-rc.1", "13.0.1-beta.2"):
            with self.subTest(uuid_version=uuid_version), TemporaryDirectory() as directory:
                repo_root = Path(directory)
                frontend_root = repo_root / "frontend"
                scripts_root = repo_root / "scripts"
                frontend_root.mkdir()
                scripts_root.mkdir()
                (frontend_root / "package-lock.json").write_text(
                    json.dumps(
                        {
                            "packages": {
                                "node_modules/@solana/web3.js": {"version": "1.98.4"},
                                "node_modules/jayson": {"version": "4.3.0"},
                                "node_modules/uuid": {"version": uuid_version},
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                audit_script = scripts_root / "audit-frontend.ps1"
                audit_script.write_text("# fixture", encoding="utf-8")
                state = BotState(database_path=str(repo_root / "test.db"))

                policy = state._frontend_dependency_audit_policy(repo_root, audit_script)

                self.assertEqual(policy["status"], "review")
                self.assertTrue(policy["known_chain_present"])
                self.assertIsNotNone(policy["acknowledged_exception"])

    def test_frontend_dependency_audit_policy_reviews_nested_vulnerable_uuid(self) -> None:
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            frontend_root = repo_root / "frontend"
            scripts_root = repo_root / "scripts"
            frontend_root.mkdir()
            scripts_root.mkdir()
            (frontend_root / "package-lock.json").write_text(
                json.dumps(
                    {
                        "packages": {
                            "node_modules/@solana/web3.js": {"version": "1.98.4"},
                            "node_modules/jayson": {"version": "4.3.0"},
                            "node_modules/uuid": {"version": "11.1.1"},
                            "node_modules/rpc-websockets/node_modules/uuid": {"version": "11.1.0"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            audit_script = scripts_root / "audit-frontend.ps1"
            audit_script.write_text("# fixture", encoding="utf-8")
            state = BotState(database_path=str(repo_root / "test.db"))

            policy = state._frontend_dependency_audit_policy(repo_root, audit_script)

            self.assertEqual(policy["status"], "review")
            self.assertTrue(policy["known_chain_present"])
            self.assertIn("11.1.0", policy["packages"]["uuid_versions"])

    def test_frontend_dependency_audit_policy_blocks_malformed_required_versions(self) -> None:
        valid_versions = {
            "node_modules/@solana/web3.js": "1.98.4",
            "node_modules/jayson": "4.3.0",
            "node_modules/uuid": "11.1.1",
        }
        for dependency_path in valid_versions:
            with self.subTest(dependency_path=dependency_path), TemporaryDirectory() as directory:
                repo_root = Path(directory)
                frontend_root = repo_root / "frontend"
                scripts_root = repo_root / "scripts"
                frontend_root.mkdir()
                scripts_root.mkdir()
                versions = dict(valid_versions)
                versions[dependency_path] = "not-semver"
                (frontend_root / "package-lock.json").write_text(
                    json.dumps(
                        {
                            "packages": {
                                path: {"version": version}
                                for path, version in versions.items()
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                audit_script = scripts_root / "audit-frontend.ps1"
                audit_script.write_text("# fixture", encoding="utf-8")
                state = BotState(database_path=str(repo_root / "test.db"))

                policy = state._frontend_dependency_audit_policy(repo_root, audit_script)

                self.assertEqual(policy["status"], "blocked")
                self.assertTrue(any("valid semantic versions" in blocker for blocker in policy["blockers"]))
                self.assertIn("package-lock.json", policy["operator_action"])

    def test_frontend_dependency_audit_policy_blocks_malformed_nested_uuid_version(self) -> None:
        fixtures = {
            "empty_object": {},
            "empty_version": {"version": ""},
            "null_entry": None,
            "malformed_version": {"version": "not-semver"},
        }
        for fixture_name, nested_entry in fixtures.items():
            with self.subTest(fixture=fixture_name), TemporaryDirectory() as directory:
                repo_root = Path(directory)
                frontend_root = repo_root / "frontend"
                scripts_root = repo_root / "scripts"
                frontend_root.mkdir()
                scripts_root.mkdir()
                (frontend_root / "package-lock.json").write_text(
                    json.dumps(
                        {
                            "packages": {
                                "node_modules/@solana/web3.js": {"version": "1.98.4"},
                                "node_modules/jayson": {"version": "4.3.0"},
                                "node_modules/uuid": {"version": "11.1.1"},
                                "node_modules/rpc-websockets/node_modules/uuid": nested_entry,
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                audit_script = scripts_root / "audit-frontend.ps1"
                audit_script.write_text("# fixture", encoding="utf-8")
                state = BotState(database_path=str(repo_root / "test.db"))

                policy = state._frontend_dependency_audit_policy(repo_root, audit_script)

                self.assertEqual(policy["status"], "blocked")
                self.assertTrue(any("installed uuid" in blocker.lower() for blocker in policy["blockers"]))
                self.assertIn("package-lock.json", policy["operator_action"])

    def test_frontend_dependency_audit_policy_reports_missing_script_action(self) -> None:
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            frontend_root = repo_root / "frontend"
            frontend_root.mkdir()
            (frontend_root / "package-lock.json").write_text(
                json.dumps(
                    {
                        "packages": {
                            "node_modules/@solana/web3.js": {"version": "1.98.4"},
                            "node_modules/jayson": {"version": "4.3.0"},
                            "node_modules/uuid": {"version": "11.1.1"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            audit_script = repo_root / "scripts" / "audit-frontend.ps1"
            state = BotState(database_path=str(repo_root / "test.db"))

            policy = state._frontend_dependency_audit_policy(repo_root, audit_script)

            self.assertEqual(policy["status"], "blocked")
            self.assertIn("audit-frontend.ps1", policy["operator_action"])
            self.assertNotIn("package-lock.json is missing", policy["operator_action"])

    def test_release_next_steps_uses_current_frontend_audit_guidance(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            steps = state._release_next_steps(
                [{"id": "frontend_audit", "status": "fail"}],
                "blocked",
            )

            self.assertEqual(
                steps,
                ["Run scripts/audit-frontend.ps1 -Strict and resolve reported blockers or review items before release."],
            )
            self.assertNotIn("Solana advisory", steps[0])

    def test_release_readiness_accepts_recent_verifier_attestation(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.storage.save_event(
                TradeEvent(
                    id="evt_release_verify",
                    created_at=utc_now(),
                    level="info",
                    message="Release verification recorded for 0.1.0",
                    subsystem="release",
                    operator_action="Local verifier passed and git diff was reviewed.",
                    context={
                        "artifact_type": "cryptoarc_release_verification",
                        "app_version": "0.1.0",
                        "verify_passed": True,
                        "diff_reviewed": True,
                        "docs_reviewed": True,
                    },
                )
            )

            report = state.release_readiness_report("0.1.0", env_live_enabled=False, local_auth_enabled=True)
            gate_status = {gate["id"]: gate["status"] for gate in report["gates"]}

            self.assertEqual(gate_status["manual_verification"], "pass")
            self.assertEqual(report["evidence"]["release_verification"]["status"], "verified")
            self.assertTrue(report["evidence"]["release_verification"]["verified"])
            self.assertEqual(report["evidence"]["release_verification"]["event_id"], "evt_release_verify")
            self.assertFalse(any("Run scripts/verify.ps1" in step for step in report["next_steps"]))

    def test_record_release_verification_persists_auditable_attestation(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            attestation = state.record_release_verification(
                "0.1.0",
                verify_passed=True,
                diff_reviewed=True,
                docs_reviewed=True,
                note="Verified after roadmap gate hardening.",
            )
            report = state.release_readiness_report("0.1.0", env_live_enabled=False, local_auth_enabled=True)
            gate_status = {gate["id"]: gate["status"] for gate in report["gates"]}
            event = state.storage.load_all_events(5)[0]

            self.assertEqual(attestation["artifact_type"], "cryptoarc_release_verification")
            self.assertTrue(attestation["verified"])
            self.assertEqual(attestation["event_id"], event.id)
            self.assertEqual(event.subsystem, "release")
            self.assertEqual(event.context["app_version"], "0.1.0")
            self.assertTrue(event.context["verify_passed"])
            self.assertTrue(event.context["diff_reviewed"])
            self.assertTrue(event.context["docs_reviewed"])
            self.assertNotIn("seed", json.dumps(event.context).lower())
            self.assertEqual(gate_status["manual_verification"], "pass")

    def test_post_run_review_report_flags_incident_export_candidates(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_clear",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintClear",
                    amount="0.001",
                    status="reconciled",
                    final_status="reconciled",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletReview",
                    transaction_signature="sigclear",
                    reconciliation_status="matched",
                )
            )
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_review",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintReview",
                    amount="0.001",
                    status="needs_review",
                    final_status="needs_review",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletReview",
                    transaction_signature="sigreview",
                    reconciliation_status="needs_review",
                    recovery_attempts=state.live_recovery_max_attempts,
                    recommended_action="Inspect failed reconciliation.",
                )
            )

            report = state.post_run_review_report("24h", "WalletReview")

            self.assertEqual(report["artifact_type"], "cryptoarc_post_run_review")
            self.assertEqual(report["status"], "review_required")
            self.assertFalse(report["ready"])
            self.assertEqual(report["summary"]["audits"], 2)
            self.assertEqual(report["summary"]["incident_export_candidates"], 1)
            self.assertEqual(report["incident_exports"][0]["audit_id"], "liveaudit_review")
            self.assertIn("/api/live/audit/liveaudit_review/incident-export", report["incident_exports"][0]["export_path"])
            self.assertTrue(any("Export" in item for item in report["action_items"]))

    def test_post_run_review_clears_after_incident_export_review_is_recorded(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_reviewed_export",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintReviewedExport",
                    amount="0.001",
                    status="blocked",
                    final_status="blocked",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletReviewedExport",
                    reconciliation_status="not_submitted",
                    recommended_action="Export and inspect blocked live-entry evidence.",
                    caps_snapshot=state.live_caps_snapshot(),
                )
            )

            before = state.post_run_review_report("24h", "WalletReviewedExport")
            before_checklist = {item["id"]: item for item in before["checklist"]}

            self.assertEqual(before["status"], "review_required")
            self.assertFalse(before["ready"])
            self.assertEqual(before_checklist["incident_exports"]["status"], "review")

            attestation = state.record_incident_export_review(
                "liveaudit_reviewed_export",
                exported=True,
                reviewed=True,
                note="Incident bundle exported and reviewed after pilot.",
            )
            after = state.post_run_review_report("24h", "WalletReviewedExport")
            after_checklist = {item["id"]: item for item in after["checklist"]}

            self.assertTrue(attestation["reviewed"])
            self.assertEqual(attestation["audit_id"], "liveaudit_reviewed_export")
            self.assertEqual(after["status"], "clear")
            self.assertTrue(after["ready"])
            self.assertEqual(after["summary"]["incident_export_candidates"], 1)
            self.assertEqual(after["summary"]["pending_incident_exports"], 0)
            self.assertEqual(after_checklist["incident_exports"]["status"], "pass")
            self.assertTrue(after["incident_exports"][0]["reviewed"])
            self.assertFalse(any("Export" in item for item in after["action_items"]))

    def test_post_run_review_report_is_clear_for_reconciled_audits(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_done",
                    created_at=now,
                    updated_at=now,
                    action="sell",
                    mint="MintDone",
                    amount="100%",
                    status="reconciled",
                    final_status="reconciled",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletDone",
                    transaction_signature="sigdone",
                    reconciliation_status="matched",
                    caps_snapshot=state.live_caps_snapshot(),
                )
            )

            report = state.post_run_review_report("24h", "WalletDone")

            self.assertEqual(report["status"], "clear")
            self.assertTrue(report["ready"])
            self.assertEqual(report["summary"]["incident_export_candidates"], 0)
            self.assertFalse(report["incident_exports"])

    def test_post_run_review_includes_cap_and_kill_switch_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_controls",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintControls",
                    amount="0.001",
                    status="reconciled",
                    final_status="reconciled",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletControls",
                    transaction_signature="sigcontrols",
                    reconciliation_status="matched",
                    caps_snapshot=state.live_caps_snapshot(),
                )
            )

            report = state.post_run_review_report("24h", "WalletControls")
            controls = report["run_controls"]
            checklist = {item["id"]: item for item in report["checklist"]}

            self.assertFalse(controls["kill_switch_enabled"])
            self.assertEqual(controls["caps"]["max_trade_sol"], state.settings.live_max_trade_sol)
            self.assertEqual(controls["audits_missing_caps_snapshot"], 0)
            self.assertEqual(checklist["cap_and_stop_evidence"]["status"], "pass")

    def test_post_run_review_requires_recent_live_audit_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            report = state.post_run_review_report("24h", "WalletEmpty")
            checklist = {item["id"]: item for item in report["checklist"]}

            self.assertEqual(report["status"], "missing_evidence")
            self.assertFalse(report["ready"])
            self.assertEqual(report["summary"]["audits"], 0)
            self.assertEqual(checklist["live_audit_inventory"]["status"], "empty")
            self.assertTrue(any("No live audits" in item for item in report["action_items"]))

    def test_post_run_review_excludes_shadow_only_evidence_audits(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="liveaudit_shadow_only_review",
                    created_at=now,
                    updated_at=now,
                    action="buy",
                    mint="MintShadowReview",
                    amount="0.001",
                    status="needs_review",
                    final_status="needs_review",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletShadowReview",
                    quote={"id": "quote_shadow_review", "shadow_only": True},
                    shadow_comparison={"mode": "dry_run_shadow", "status": "waiting_for_price"},
                    recommended_action="Shadow-only quote is evidence-only.",
                )
            )

            report = state.post_run_review_report("24h", "WalletShadowReview")
            checklist = {item["id"]: item for item in report["checklist"]}

            self.assertEqual(report["status"], "missing_evidence")
            self.assertFalse(report["ready"])
            self.assertEqual(report["summary"]["audits"], 0)
            self.assertEqual(report["summary"]["needs_review"], 0)
            self.assertEqual(report["summary"]["incident_export_candidates"], 0)
            self.assertFalse(report["incident_exports"])
            self.assertEqual(checklist["live_audit_inventory"]["status"], "empty")

    def test_outcome_explanations_cover_decisions_live_blocks_recovery_and_overrides(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            bought = self.make_token()
            bought.id = "tok_bought"
            bought.mint = "MintBought"
            bought.symbol = "BUY"
            bought.status = TokenStatus.PAPER_SOLD
            bought.opened_at = now - timedelta(minutes=20)
            bought.closed_at = now - timedelta(minutes=5)
            bought.entry_reason = "strategy allowed paper entry"
            bought.exit_reason = "take profit"
            bought.pnl_sol = 0.012
            state.storage.save_token(bought)
            skipped = self.make_token()
            skipped.id = "tok_skipped"
            skipped.mint = "MintSkipped"
            skipped.symbol = "SKIP"
            skipped.status = TokenStatus.SKIPPED
            skipped.detected_at = now - timedelta(minutes=10)
            skipped.reason = "below entry threshold"
            state.storage.save_token(skipped)
            state.storage.save_strategy_decision(
                StrategyDecisionRecord(
                    id="decision_skip",
                    token_id=skipped.id,
                    mint=skipped.mint,
                    created_at=now - timedelta(minutes=10),
                    engine_version="strategy-v2",
                    profile="balanced",
                    score=41,
                    allowed=False,
                    action="skip",
                    reason="score too low",
                    risk_reason="below entry threshold",
                )
            )
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="audit_blocked",
                    created_at=now - timedelta(minutes=8),
                    updated_at=now - timedelta(minutes=8),
                    action="buy",
                    mint="MintBlocked",
                    amount="0.001",
                    status="blocked",
                    final_status="blocked",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletExplain",
                    errors=["LIVE_TRADING_ENABLED is false"],
                )
            )
            state.storage.save_live_execution_audit(
                LiveExecutionAudit(
                    id="audit_recovery",
                    created_at=now - timedelta(minutes=6),
                    updated_at=now - timedelta(minutes=6),
                    action="sell",
                    mint="MintRecover",
                    amount="100%",
                    status="needs_review",
                    final_status="needs_review",
                    signer_mode="browser_wallet",
                    wallet_public_key="WalletExplain",
                    transaction_signature="sigrecover",
                    reconciliation_status="needs_review",
                    recovery_attempts=3,
                    recommended_action="Review wallet/RPC balance reconciliation.",
                )
            )
            state.storage.save_live_execution_request(
                LiveExecutionRequest(
                    id="request_block",
                    created_at=now - timedelta(minutes=4),
                    action="buy",
                    mint="MintRequest",
                    amount_sol=0.01,
                    status="blocked",
                    reason="legacy manual live request capture is audit-only",
                )
            )
            state.record_expert_override(True, "entry_autonomy", "buy", "documenting why operator accepts this risk", "WalletExplain")

            report = state.outcome_explanations_report("24h", 50)
            outcome_types = {item["outcome_type"] for item in report["outcomes"]}
            ids = {item["id"] for item in report["outcomes"]}

            self.assertEqual(report["artifact_type"], "cryptoarc_outcome_explanations")
            self.assertIn("buy", outcome_types)
            self.assertIn("sell", outcome_types)
            self.assertIn("skip", outcome_types)
            self.assertIn("block", outcome_types)
            self.assertIn("recovery", outcome_types)
            self.assertIn("override", outcome_types)
            self.assertIn("decision:decision_skip", ids)
            self.assertIn("live-audit:audit_blocked", ids)
            self.assertIn("live-audit:audit_recovery", ids)
            self.assertIn("manual-request:request_block", ids)
            self.assertGreaterEqual(report["summary"]["by_type"]["block"], 2)
            self.assertTrue(report["action_items"])
            self.assertIn("privacy_note", report)

    def test_incident_export_contains_audit_intent_source_and_operator_events(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            intent = state.create_live_intent("buy", "MintIncident", "0.001", True, "WalletIncident")
            quote = state.quote_live_intent(True, intent["id"], 1, 0.00001, "pump")
            state.storage.save_source_event(
                SourceEvent(
                    id="src_incident",
                    source="pumpportal",
                    received_at=utc_now(),
                    raw_payload={"mint": "MintIncident"},
                    status="raw",
                )
            )
            state.add_event("warning", "Live incident follow-up for MintInci", subsystem="live")

            export = state.incident_export(str(quote["id"]))

            self.assertEqual(export["artifact_type"], "cryptoarc_live_incident_export")
            self.assertEqual(export["audit"]["id"], quote["id"])
            self.assertEqual(export["intent"]["id"], intent["id"])
            self.assertEqual(export["source_events"][0]["id"], "src_incident")
            self.assertTrue(export["operator_events"])
            self.assertIn("privacy_note", export)

    def test_operational_monitoring_includes_structured_observability_summary(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.add_event("warning", "Readiness blocked by source trust", subsystem="source", operator_action="Review source trust.")
            state.add_event("danger", "Kill switch enabled", subsystem="live", operator_action="Stop entries.")
            state.add_event("info", "Routine review event", subsystem="review")

            monitoring = state.operational_monitoring()
            observability = monitoring["observability"]
            subsystems = {row["subsystem"]: row for row in observability["subsystems"]}

            self.assertEqual(observability["event_count"], 3)
            self.assertEqual(observability["level_counts"]["warning"], 1)
            self.assertEqual(observability["level_counts"]["danger"], 1)
            self.assertIn("source", subsystems)
            self.assertEqual(subsystems["live"]["errors"], 1)
            self.assertEqual(observability["high_severity"][0]["level"], "danger")
            self.assertTrue(any("Readiness blocked" in event["message"] for event in observability["readiness_changes"]))
            self.assertIn("source_metrics", observability)
            self.assertIn("signer_metrics", observability)
            self.assertIn("recovery_metrics", observability)

    def test_operator_logs_report_filters_and_exports_structured_local_events(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.active_live_session_id = "session_logs"
            state.add_event("warning", "Backup recovery needs review", subsystem="recovery", operator_action="Run restore smoke test.")
            state.add_event("danger", "Live quote failed", subsystem="live", operator_action="Review the quote provider.")
            state.add_event("info", "Source parser replay complete", subsystem="source")

            report = state.operator_logs_report("24h", "", "", 10)
            live_only = state.operator_logs_report("24h", "danger", "live", 10)

            self.assertEqual(report["artifact_type"], "cryptoarc_operator_logs")
            self.assertEqual(report["summary"]["total_events"], 3)
            self.assertEqual(report["summary"]["warnings"], 1)
            self.assertEqual(report["summary"]["errors"], 1)
            self.assertEqual(report["summary"]["recovery_related_events"], 1)
            self.assertEqual(report["summary"]["source_related_events"], 1)
            self.assertEqual(report["summary"]["live_related_events"], 1)
            self.assertEqual(report["session_counts"][0]["session_id"], "session_logs")
            self.assertIn("Run restore smoke test.", report["action_items"])
            self.assertIn("privacy_note", report)
            self.assertEqual(live_only["summary"]["total_events"], 1)
            self.assertEqual(live_only["events"][0]["subsystem"], "live")

    def test_snapshot_keeps_all_non_skipped_tokens_for_monitor_filters(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            for index in range(90):
                token = self.make_token()
                token.id = f"skip_{index}"
                token.mint = f"SkipMint{index}"
                token.detected_at = utc_now()
                token.status = TokenStatus.SKIPPED
                state.storage.save_token(token)
            for index in range(14):
                token = self.make_token()
                token.id = f"sold_{index}"
                token.mint = f"SoldMint{index}"
                token.status = TokenStatus.PAPER_SOLD
                token.pnl_sol = 0.001
                state.storage.save_token(token)
            state.tokens = deque(state.storage.load_tokens(), maxlen=80)

            snapshot = state.snapshot()
            non_skipped = [token for token in snapshot.tokens if token.status != TokenStatus.SKIPPED]

            self.assertEqual(len(non_skipped), 14)

    def test_idle_source_health_uses_historical_quality_without_offline_penalty(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            for index in range(12):
                event = SourceEvent(
                    id=f"src_{index}",
                    source="pumpportal",
                    received_at=utc_now(),
                    raw_payload={"mint": f"Mint{index}"},
                    normalized_token_id=f"tok_{index}",
                    status="normalized",
                    message="normalized",
                )
                state.storage.save_source_event(event)

            state.source_status.status = "offline"
            state.source_status.message = "Source is idle"
            state.source_status.raw_events_seen = 0
            state.source_status.normalized_events = 0

            health = state.source_health()

            self.assertEqual(health["status_message"], "idle")
            self.assertGreaterEqual(health["health_score"], 80)
            self.assertEqual(health["trust_state"], "trusted")
            self.assertTrue(health["paper_collection_allowed"])

    def test_fresh_idle_source_health_is_full_when_bot_is_not_running(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            health = state.source_health()

            self.assertEqual(health["status_message"], "idle")
            self.assertEqual(health["health_score"], 100)
            self.assertEqual(health["trust_state"], "unknown")
            self.assertFalse(health["live_entry_blocked"])

    def test_source_health_reports_conflicting_low_normalization_trust(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.status = BotStatus.RUNNING
            state.source_status.status = "connected"
            state.source_status.last_event_at = now
            state.source_status.raw_events_seen = 20
            state.source_status.normalized_events = 4
            for index in range(4):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_norm_{index}",
                        source="pumpportal",
                        received_at=now,
                        raw_payload={"mint": f"MintNorm{index}"},
                        normalized_token_id=f"tok_norm_{index}",
                        status="normalized",
                    )
                )
            for index in range(16):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_raw_{index}",
                        source="pumpportal",
                        received_at=now,
                        raw_payload={"mint": f"MintRaw{index}"},
                        status="raw",
                    )
                )

            health = state.source_health()

            self.assertEqual(health["trust_state"], "conflicting")
            self.assertTrue(health["live_entry_blocked"])
            self.assertIn("normalization ratio is below 35%", health["trust_blockers"])
            self.assertEqual(health["raw_event_inspection"]["recent_events"], 20)

    def test_source_health_does_not_treat_trade_stream_as_normalization_failure(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.status = BotStatus.RUNNING
            state.source_status.status = "connected"
            state.source_status.last_event_at = now
            state.source_status.raw_events_seen = 103
            state.source_status.normalized_events = 3
            state.source_status.trade_events_seen = 100
            for index in range(3):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_trade_heavy_norm_{index}",
                        source="pumpportal",
                        received_at=now,
                        raw_payload={"mint": f"MintTradeHeavy{index}", "txType": "create"},
                        normalized_token_id=f"tok_trade_heavy_{index}",
                        status="normalized",
                    )
                )
            for index in range(100):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_trade_heavy_trade_{index}",
                        source="pumpportal",
                        received_at=now,
                        raw_payload={"mint": "MintTradeHeavy0", "txType": "buy", "solAmount": 0.1},
                        status="trade",
                        message="token trade buy",
                    )
                )

            health = state.source_health()

            self.assertGreaterEqual(health["health_score"], 70)
            self.assertEqual(health["normalized_ratio"], 1.0)
            self.assertEqual(health["recent_normalized_ratio"], 1.0)
            self.assertNotIn("normalization ratio is below 35%", health["trust_blockers"])
            self.assertFalse(any("duplicate mint" in warning.lower() for warning in health["trust_warnings"]))

    def test_source_health_treats_fresh_reconnect_as_warning_not_failure(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.status = BotStatus.RUNNING
            state.source_status.status = "reconnecting"
            state.source_status.message = "PumpPortal reconnecting in 2s: ConnectionClosedError"
            state.source_status.last_event_at = now
            state.source_status.reconnect_attempts = 15
            state.source_status.raw_events_seen = 20
            state.source_status.normalized_events = 20
            for index in range(20):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_fresh_reconnect_{index}",
                        source="pumpportal",
                        received_at=now,
                        raw_payload={"mint": f"MintFreshReconnect{index}", "txType": "create"},
                        normalized_token_id=f"tok_fresh_reconnect_{index}",
                        status="normalized",
                    )
                )

            health = state.source_health()

            self.assertGreaterEqual(health["health_score"], 70)
            self.assertEqual(health["status_message"], "reconnecting")
            self.assertEqual(health["trust_state"], "trusted")
            self.assertNotIn("source is not connected", health["trust_blockers"])
            self.assertTrue(any("recent events are fresh" in warning for warning in health["trust_warnings"]))

    def test_source_health_treats_stopped_source_as_idle_after_run(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.status = BotStatus.STOPPED
            state.source_status.status = "offline"
            state.source_status.message = "Source is idle"
            state.source_status.last_event_at = now - timedelta(minutes=10)
            state.source_status.raw_events_seen = 20
            state.source_status.normalized_events = 20
            state.source_status.active_trade_subscriptions = 20
            for index in range(20):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_stopped_idle_{index}",
                        source="pumpportal",
                        received_at=now - timedelta(minutes=10),
                        raw_payload={"mint": f"MintStoppedIdle{index}", "txType": "create"},
                        normalized_token_id=f"tok_stopped_idle_{index}",
                        status="normalized",
                    )
                )

            health = state.source_health()

            self.assertEqual(health["health_score"], 100)
            self.assertEqual(health["status_message"], "idle")
            self.assertEqual(health["trust_state"], "trusted")
            self.assertEqual(health["trust_blockers"], [])
            self.assertTrue(any("idle" in warning.lower() for warning in health["trust_warnings"]))

    def test_source_health_treats_initial_connecting_as_startup_warning(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.status = BotStatus.RUNNING
            state.source_status.status = "connecting"
            state.source_status.message = "Connecting to PumpPortal"
            state.source_status.reconnect_attempts = 3
            state.settings.source_max_reconnects = 5

            health = state.source_health()

            self.assertGreaterEqual(health["health_score"], 70)
            self.assertEqual(health["status_message"], "connecting")
            self.assertEqual(health["trust_state"], "trusted")
            self.assertNotIn("source is not connected", health["trust_blockers"])
            self.assertTrue(any("startup" in warning.lower() for warning in health["trust_warnings"]))

    def test_source_health_includes_connection_timing_telemetry(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.status = BotStatus.RUNNING
            state.source_status.status = "connected"
            state.source_status.connection_requested_at = now - timedelta(milliseconds=450)
            state.source_status.connected_at = now
            state.source_status.last_event_at = now

            health = state.source_health()

            self.assertGreaterEqual(health["connection"]["startup_ms"], 0)
            self.assertEqual(health["connection"]["state"], "connected")
            self.assertIn("connected_at", health["connection"])

    def test_source_health_does_not_report_stale_first_event_before_current_connection(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.status = BotStatus.RUNNING
            state.source_status.status = "connecting"
            state.source_status.connection_requested_at = now
            state.source_status.first_event_at = now - timedelta(seconds=30)

            health = state.source_health()

            self.assertIsNone(health["connection"]["first_event_at"])
            self.assertIsNone(health["connection"]["first_event_ms"])

    def test_source_health_warns_when_pumpportal_trade_subscriptions_need_funding(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.source_status.status = "connected"
            state.source_status.last_event_at = now
            state.source_status.raw_events_seen = 1
            state.source_status.normalized_events = 1
            state.source_status.active_trade_subscriptions = 5
            state.storage.save_source_event(
                SourceEvent(
                    id="src_trade_subscription_funding",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"message": "'subscribeTokenTrade' and 'subscribeAccountTrade' methods are only available when connecting with an API key funded with at least 0.02 SOL."},
                    status="status",
                    message="'subscribeTokenTrade' and 'subscribeAccountTrade' methods are only available when connecting with an API key funded with at least 0.02 SOL.",
                )
            )

            health = state.source_health()

            self.assertTrue(any("funded" in warning.lower() and "trade" in warning.lower() for warning in health["trust_warnings"]))

    def test_snapshot_tokens_are_capped_for_live_monitor_responsiveness(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            for index in range(330):
                token = self.make_token()
                token.id = f"tok_snapshot_cap_{index}"
                token.mint = f"MintSnapshotCap{index}"
                token.detected_at = utc_now() - timedelta(seconds=index)
                state.storage.save_token(token)

            snapshot = state.snapshot()

            self.assertLessEqual(len(snapshot.tokens), 300)

    def test_integrity_uses_enough_token_history_for_trade_references(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            oldest = self.make_token()
            oldest.id = "tok_integrity_oldest"
            oldest.mint = "MintIntegrityOldest"
            oldest.detected_at = utc_now() - timedelta(days=2)
            state.storage.save_token(oldest)
            for index in range(5000):
                token = self.make_token()
                token.id = f"tok_integrity_recent_{index}"
                token.mint = f"MintIntegrityRecent{index}"
                token.detected_at = utc_now() - timedelta(seconds=index)
                state.storage.save_token(token)
            trade = state.trade_from_token(oldest)
            trade.closed_at = utc_now()
            trade.pnl_sol = 0.01
            trade.lifecycle_status = "closed"
            trade.exit_reason = "take profit"
            state.storage.save_trade(trade)

            report = state.data_integrity_report()

            self.assertFalse(any(issue["message"] == "Trade records reference missing token snapshots" for issue in report["issues"]))

    def test_pumpportal_unfunded_runtime_message_alerts_once_and_blocks_shadow_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            message = "'subscribeTokenTrade' and 'subscribeAccountTrade' methods are only available when connecting with an API key funded with at least 0.02 SOL."
            event = LaunchEvent(
                source="pumpportal",
                received_at=now,
                raw_payload={"message": message},
                token=None,
                message=message,
            )

            state.ingest_source_event(event)
            state.ingest_source_event(event)
            health = state.source_health()
            alerts = [item for item in state.storage.load_all_events(20) if item.subsystem == "source"]

            self.assertTrue(health["pumpportal_funding_blocked"])
            self.assertTrue(health["shadow_price_observations_blocked"])
            self.assertIn("PumpPortal API wallet appears unfunded", health["trust_blockers"])
            self.assertEqual(len([item for item in alerts if "PumpPortal API wallet appears unfunded" in item.message]), 1)

    def test_source_health_ignores_quote_mint_duplicates_and_min_balance_status_errors(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.source_status.status = "connected"
            state.source_status.last_event_at = now
            state.source_status.raw_events_seen = 3
            state.source_status.normalized_events = 2
            for index in range(2):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_quote_{index}",
                        source="pumpportal",
                        received_at=now,
                        raw_payload={"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "txType": "create"},
                        normalized_token_id=f"tok_quote_{index}",
                        status="normalized",
                    )
                )
            state.storage.save_source_event(
                SourceEvent(
                    id="src_min_balance_status",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"errors": "Minimum balance not met for PumpSwap websocket data."},
                    status="raw",
                )
            )

            health = state.source_health()

            self.assertEqual(health["raw_event_inspection"]["duplicate_mints"], [])
            self.assertEqual(health["raw_event_inspection"]["malformed_events"], 0)
            self.assertFalse(any("duplicate mint" in warning.lower() for warning in health["trust_warnings"]))
            self.assertFalse(any("missing a mint" in warning.lower() for warning in health["trust_warnings"]))

    def test_pumpportal_quote_mint_reject_is_archived_as_ignored_not_raw(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.ingest_source_event(
                LaunchEvent(
                    source="pumpportal",
                    received_at=utc_now(),
                    raw_payload={
                        "signature": "sig_quote_reject",
                        "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                        "traderPublicKey": "trader_quote_reject",
                        "txType": "create",
                        "initialBuy": 0,
                        "solAmount": 0,
                        "bondingCurveKey": "curve_quote_reject",
                        "marketCapSol": 27.95,
                    },
                    token=None,
                )
            )

            events = state.source_events(limit=10)
            integrity = state.data_integrity_report()

            self.assertEqual(state.storage.count_tokens(), 0)
            self.assertEqual(events[0]["status"], "ignored")
            self.assertEqual(events[0]["parser_result"], "ignored")
            self.assertEqual(integrity["score"], 100)
            self.assertEqual(integrity["issues"], [])

    def test_source_health_includes_quality_history_buckets(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            older = now - timedelta(minutes=25)
            for index in range(12):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_good_{index}",
                        source="pumpportal",
                        received_at=older + timedelta(seconds=index),
                        raw_payload={"mint": f"MintGood{index}"},
                        normalized_token_id=f"tok_good_{index}",
                        status="normalized",
                    )
                )
            for index in range(4):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_recent_norm_{index}",
                        source="pumpportal",
                        received_at=now - timedelta(minutes=3, seconds=index),
                        raw_payload={"mint": f"MintRecentNorm{index}"},
                        normalized_token_id=f"tok_recent_{index}",
                        status="normalized",
                    )
                )
            for index in range(12):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_recent_raw_{index}",
                        source="pumpportal",
                        received_at=now - timedelta(minutes=2, seconds=index),
                        raw_payload={"mint": f"MintRecentRaw{index}"},
                        status="raw",
                    )
                )

            health = state.source_health()
            history = health["quality_history"]
            populated = [bucket for bucket in history if bucket["events"]]

            self.assertEqual(len(history), 12)
            self.assertTrue(any(bucket["trust_state"] == "trusted" for bucket in populated))
            self.assertTrue(any(bucket["trust_state"] == "conflicting" for bucket in populated))
            self.assertTrue(all("normalized_ratio" in bucket for bucket in history))

    def test_source_health_report_exports_history_and_recent_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            for index in range(12):
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_export_norm_{index}",
                        source="pumpportal",
                        received_at=now - timedelta(minutes=5, seconds=index),
                        raw_payload={"mint": f"MintExportNorm{index}", "parser_result": "normalized"},
                        normalized_token_id=f"tok_export_norm_{index}",
                        status="normalized",
                    )
                )
            state.storage.save_source_event(
                SourceEvent(
                    id="src_export_bad",
                    source="pumpportal",
                    received_at=now - timedelta(minutes=3),
                    raw_payload={"name": "Missing Mint"},
                    status="raw",
                    message="missing mint",
                )
            )
            state.add_event("warning", "Source trust review requested", subsystem="source", operator_action="Inspect raw source evidence.")

            report = state.source_health_report(limit=20)

            self.assertEqual(report["artifact_type"], "cryptoarc_source_health_history")
            self.assertIn("current", report)
            self.assertGreaterEqual(report["history_summary"]["active_buckets"], 1)
            self.assertGreaterEqual(report["history_summary"]["malformed_events"], 1)
            self.assertEqual(report["event_window"]["status_counts"]["normalized"], 12)
            self.assertTrue(any(row["id"] == "src_export_bad" for row in report["recent_source_events"]))
            self.assertTrue(any("Source trust review" in event["message"] for event in report["recent_operator_events"]))
            self.assertIn("must not contain seed phrases", report["privacy_note"])

    def test_source_events_filter_by_status_source_and_mint(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.storage.save_source_event(
                SourceEvent(
                    id="src_keep",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"mint": "MintKeep111"},
                    normalized_token_id="tok_keep",
                    status="normalized",
                )
            )
            state.storage.save_source_event(
                SourceEvent(
                    id="src_drop_status",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"mint": "MintKeep111"},
                    status="raw",
                )
            )
            state.storage.save_source_event(
                SourceEvent(
                    id="src_drop_source",
                    source="mock",
                    received_at=now,
                    raw_payload={"mint": "MintKeep111"},
                    normalized_token_id="tok_mock",
                    status="normalized",
                )
            )

            events = state.source_events(status="normalized", source="pumpportal", mint="keep")

            self.assertEqual([event["id"] for event in events], ["src_keep"])

    def test_source_events_filter_by_event_kind_and_parser_result(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.storage.save_source_event(
                SourceEvent(
                    id="src_launch",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"txType": "create", "mint": "MintLaunchKind"},
                    normalized_token_id="tok_launch",
                    status="normalized",
                )
            )
            state.storage.save_source_event(
                SourceEvent(
                    id="src_trade",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"txType": "buy", "mint": "MintTradeKind", "solAmount": 1.0},
                    status="trade",
                )
            )
            state.storage.save_source_event(
                SourceEvent(
                    id="src_missing",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"txType": "create"},
                    status="raw",
                )
            )

            normalized = state.source_events(event_kind="create", parser_result="normalized")
            missing = state.source_events(parser_result="missing_mint")

            self.assertEqual([event["id"] for event in normalized], ["src_launch"])
            self.assertEqual(normalized[0]["event_kind"], "create")
            self.assertEqual(normalized[0]["parser_result"], "normalized")
            self.assertEqual([event["id"] for event in missing], ["src_missing"])

    def test_source_parser_replay_report_counts_failures_without_persisting_backtest(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            now = utc_now()
            state.storage.save_source_event(
                SourceEvent(
                    id="src_valid_create",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"txType": "create", "mint": "MintReplayValid", "symbol": "RPLY", "name": "Replay"},
                    status="raw",
                )
            )
            state.storage.save_source_event(
                SourceEvent(
                    id="src_missing_mint",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"txType": "create", "symbol": "MISS"},
                    status="raw",
                )
            )
            state.storage.save_source_event(
                SourceEvent(
                    id="src_trade_event",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"txType": "buy", "mint": "MintReplayValid", "solAmount": 1.0},
                    status="trade",
                )
            )

            before_backtests = state.storage.count_backtest_runs()
            report = state.source_parser_replay_report(limit=20)

            self.assertEqual(report["artifact_type"], "cryptoarc_source_parser_replay")
            self.assertEqual(report["summary"]["raw_events"], 3)
            self.assertEqual(report["summary"]["normalized"], 1)
            self.assertEqual(report["summary"]["normalization_failures"], 1)
            self.assertEqual(report["summary"]["trade_events"], 1)
            self.assertEqual(report["summary"]["normalization_rate"], 0.5)
            self.assertEqual(report["dry_backtest"]["tokens_replayed"], 1)
            self.assertEqual(state.storage.count_backtest_runs(), before_backtests)
            failures = {item["event_id"]: item for item in report["failures"]}
            self.assertEqual(failures["src_missing_mint"]["parser_result"], "missing_mint")
            self.assertIn("mint", failures["src_missing_mint"]["failure_reason"])
            self.assertIn("privacy_note", report)

    def test_source_adapters_include_direct_solana_logs_verifier_status(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            adapters = {adapter["name"]: adapter for adapter in state.source_adapters()}

            self.assertIn("pumpportal", adapters)
            self.assertIn("solana_logs", adapters)
            self.assertFalse(adapters["solana_logs"]["enabled"])
            self.assertEqual(adapters["solana_logs"]["status"], "not_configured")
            self.assertIn("logsSubscribe", adapters["solana_logs"]["capabilities"])
            self.assertEqual(adapters["solana_logs"]["details"]["filter"], "mentions")

        with TemporaryDirectory() as directory:
            state = BotState(
                database_path=str(Path(directory) / "test.db"),
                default_solana_wss_endpoint="wss://example.invalid",
            )
            adapters = {adapter["name"]: adapter for adapter in state.source_adapters()}

            self.assertFalse(adapters["solana_logs"]["enabled"])
            self.assertEqual(adapters["solana_logs"]["status"], "missing_mentions_address")
            self.assertTrue(adapters["solana_logs"]["details"]["wss_configured"])
            self.assertFalse(adapters["solana_logs"]["details"]["mentions_address_configured"])

        with TemporaryDirectory() as directory:
            state = BotState(
                database_path=str(Path(directory) / "test.db"),
                default_solana_wss_endpoint="wss://example.invalid",
                default_solana_logs_mentions_address="PumpFunProgram111",
            )
            state.solana_logs_status.status = "connected"
            state.solana_logs_status.last_event_at = utc_now()
            adapters = {adapter["name"]: adapter for adapter in state.source_adapters()}

            self.assertTrue(adapters["solana_logs"]["enabled"])
            self.assertEqual(adapters["solana_logs"]["status"], "connected")
            self.assertTrue(adapters["solana_logs"]["details"]["wss_configured"])
            self.assertTrue(adapters["solana_logs"]["details"]["mentions_address_configured"])
            self.assertIn("paper_create_normalization", adapters["solana_logs"]["capabilities"])
            self.assertFalse(adapters["solana_logs"]["details"]["paper_normalization_enabled"])

    def test_solana_logs_subscribe_payload_uses_single_mentions_address(self) -> None:
        payload = solana_logs_subscribe_payload("PumpFunProgram111", "processed")

        self.assertEqual(payload["method"], "logsSubscribe")
        self.assertEqual(payload["params"][0], {"mentions": ["PumpFunProgram111"]})
        self.assertEqual(payload["params"][1], {"commitment": "processed"})

    def test_solana_logs_verification_ingest_archives_without_launching_token(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            before_tokens = state.storage.count_tokens()
            state.ingest_source_event(
                LaunchEvent(
                    source="solana_logs",
                    received_at=utc_now(),
                    raw_payload={
                        "method": "logsNotification",
                        "params": {
                            "result": {
                                "context": {"slot": 42},
                                "value": {"signature": "SigArchive111", "err": None, "logs": ["Program log: Instruction: Create", "Program log: mint MintArchive111"]},
                            }
                        },
                    },
                    token=None,
                    message="Solana logsSubscribe notification",
                    kind="verification",
                )
            )
            events = state.source_events(source="solana_logs")

            self.assertEqual(state.storage.count_tokens(), before_tokens)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["status"], "raw")
            self.assertEqual(events[0]["parser_result"], "missing_mint")

    def test_solana_logs_can_normalize_direct_create_evidence_for_paper_when_enabled(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            state.status = BotStatus.RUNNING
            state.settings.direct_solana_paper_enabled = True
            state.settings.direct_solana_min_confidence = 0.65
            state.storage.save_settings(state.settings)
            state.ingest_source_event(
                LaunchEvent(
                    source="solana_logs",
                    received_at=utc_now(),
                    raw_payload={
                        "method": "logsNotification",
                        "params": {
                            "result": {
                                "context": {"slot": 42},
                                "value": {
                                    "signature": "SigDirectPaper111",
                                    "err": None,
                                    "logs": [
                                        "Program log: Instruction: Create",
                                        "Program log: mint MintDirectPaper111",
                                        "Program log: name=Direct Paper symbol=DIRP uri=https://example.com/direct.json creator=CreatorDirectPaper111 bondingCurveKey=CurveDirectPaper111",
                                    ],
                                },
                            }
                        },
                    },
                    token=None,
                    message="Solana logsSubscribe notification",
                    kind="verification",
                )
            )

            tokens = state.storage.load_all_tokens(20)
            events = state.source_events(source="solana_logs")

            self.assertEqual(len(tokens), 1)
            self.assertEqual(tokens[0].mint, "MintDirectPaper111")
            self.assertEqual(tokens[0].symbol, "DIRP")
            self.assertEqual(tokens[0].price_source, "direct_solana_derived")
            self.assertIn("direct solana create", tokens[0].intelligence_tags)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["status"], "normalized")
            self.assertEqual(events[0]["parser_result"], "normalized")
            self.assertEqual(events[0]["normalized_token_id"], tokens[0].id)

    def test_solana_logs_verification_matches_direct_logs_to_pumpportal(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(
                database_path=str(Path(directory) / "test.db"),
                default_solana_wss_endpoint="wss://example.invalid",
                default_solana_logs_mentions_address="PumpFunProgram111",
            )
            now = utc_now()
            state.storage.save_source_event(
                SourceEvent(
                    id="src_pump_match",
                    source="pumpportal",
                    received_at=now,
                    raw_payload={"txType": "create", "mint": "MintDirect111", "signature": "SigDirect111"},
                    normalized_token_id="tok_direct",
                    status="normalized",
                )
            )
            state.storage.save_source_event(
                SourceEvent(
                    id="src_solana_match",
                    source="solana_logs",
                    received_at=now + timedelta(milliseconds=125),
                    raw_payload={
                        "jsonrpc": "2.0",
                        "method": "logsNotification",
                        "params": {
                            "result": {
                                "context": {"slot": 12345},
                                "value": {
                                    "signature": "SigDirect111",
                                    "err": None,
                                    "logs": [
                                        "Program log: Instruction: Create",
                                        "Program log: mint MintDirect111",
                                    ],
                                },
                            }
                        },
                    },
                    status="raw",
                )
            )

            report = state.solana_logs_verification_report(limit=20)

            self.assertEqual(report["artifact_type"], "cryptoarc_solana_logs_verification")
            self.assertEqual(report["status"], "matching")
            self.assertTrue(report["configured"])
            self.assertEqual(report["summary"]["direct_events"], 1)
            self.assertEqual(report["summary"]["pumpportal_events"], 1)
            self.assertEqual(report["summary"]["direct_create_hints"], 1)
            self.assertEqual(report["summary"]["decoded_create_events"], 1)
            self.assertEqual(report["summary"]["matches"], 1)
            self.assertEqual(report["matches"][0]["match_type"], "signature")
            self.assertEqual(report["matches"][0]["direct_minus_portal_ms"], 125)
            self.assertIn("MintDirect111", report["matches"][0]["mints"])
            create_evidence = report["direct_events"][0]["create_evidence"]
            self.assertEqual(create_evidence["fields"]["mint"], "MintDirect111")
            self.assertGreaterEqual(create_evidence["confidence"], 0.3)
            self.assertIn("privacy_note", report)

    def test_solana_logs_verification_decodes_program_data_create_fields(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(
                database_path=str(Path(directory) / "test.db"),
                default_solana_wss_endpoint="wss://example.invalid",
                default_solana_logs_mentions_address="PumpFunProgram111",
            )
            encoded = base64.b64encode(
                b"name=Arc Token symbol=ARC uri=https://example.com/arc.json creator=CreatorDirect111 bondingCurveKey=CurveDirect111 mint=MintProgram111"
            ).decode("ascii")
            state.storage.save_source_event(
                SourceEvent(
                    id="src_solana_program_data",
                    source="solana_logs",
                    received_at=utc_now(),
                    raw_payload={
                        "result": {
                            "context": {"slot": 700},
                            "value": {
                                "signature": "SigProgram111",
                                "err": None,
                                "logs": [
                                    "Program log: Instruction: Create",
                                    f"Program data: {encoded}",
                                ],
                            },
                        }
                    },
                    status="raw",
                )
            )

            report = state.solana_logs_verification_report(limit=20)
            evidence = report["direct_events"][0]["create_evidence"]

            self.assertEqual(report["summary"]["decoded_create_events"], 1)
            self.assertEqual(evidence["fields"]["name"], "Arc Token")
            self.assertEqual(evidence["fields"]["symbol"], "ARC")
            self.assertEqual(evidence["fields"]["metadata_uri"], "https://example.com/arc.json")
            self.assertEqual(evidence["fields"]["creator"], "CreatorDirect111")
            self.assertEqual(evidence["fields"]["bonding_curve"], "CurveDirect111")
            self.assertEqual(evidence["fields"]["mint"], "MintProgram111")
            self.assertIn("program_data_text", evidence)
            self.assertTrue(evidence["program_data_decoded"])

    def test_solana_logs_verification_flags_errors_and_missing_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            unconfigured = state.solana_logs_verification_report(limit=20)

            self.assertEqual(unconfigured["status"], "not_configured")
            self.assertFalse(unconfigured["configured"])
            self.assertTrue(any("SOLANA_WSS_ENDPOINT" in item for item in unconfigured["action_items"]))

        with TemporaryDirectory() as directory:
            state = BotState(
                database_path=str(Path(directory) / "test.db"),
                default_solana_wss_endpoint="wss://example.invalid",
                default_solana_logs_mentions_address="PumpFunProgram111",
            )
            state.storage.save_source_event(
                SourceEvent(
                    id="src_solana_error",
                    source="solana_logs",
                    received_at=utc_now(),
                    raw_payload={
                        "result": {
                            "context": {"slot": 500},
                            "value": {
                                "signature": "SigError111",
                                "err": {"InstructionError": [0, "Custom"]},
                                "logs": ["Program log: Instruction: Create", "Program log: mint MintError111"],
                            },
                        }
                    },
                    status="raw",
                )
            )

            report = state.solana_logs_verification_report(limit=20)

            self.assertEqual(report["status"], "review")
            self.assertEqual(report["summary"]["conflicts"], 1)
            self.assertEqual(report["conflicts"][0]["event_id"], "src_solana_error")
            self.assertTrue(any("error notifications" in item for item in report["action_items"]))

    def test_source_soak_acceptance_requires_matched_direct_samples(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.db"
            state = BotState(
                database_path=str(database_path),
                default_solana_wss_endpoint="wss://example.invalid",
                default_solana_logs_mentions_address="PumpFunProgram111",
            )
            now = utc_now()
            state.source_status.status = "connected"
            state.source_status.last_event_at = now
            state.source_status.raw_events_seen = 120
            state.source_status.normalized_events = 120
            for index in range(100):
                mint = f"MintSoak{index:03d}"
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_pump_soak_{index}",
                        source="pumpportal",
                        received_at=now + timedelta(milliseconds=index),
                        raw_payload={"txType": "create", "mint": mint, "signature": f"SigSoak{index:03d}"},
                        normalized_token_id=f"tok_soak_{index}",
                        status="normalized",
                    )
                )
            for index in range(20):
                mint = f"MintSoak{index:03d}"
                state.storage.save_source_event(
                    SourceEvent(
                        id=f"src_direct_soak_{index}",
                        source="solana_logs",
                        received_at=now + timedelta(seconds=1, milliseconds=index),
                        raw_payload={
                            "result": {
                                "context": {"slot": 1000 + index},
                                "value": {
                                    "signature": f"SigSoak{index:03d}",
                                    "err": None,
                                    "logs": [
                                        "Program log: Instruction: Create",
                                        f"Program log: mint {mint}",
                                        f"Program log: name=Token {index} symbol=SOAK uri=https://example.com/{index}.json creator=CreatorSoak{index:03d} bondingCurveKey=CurveSoak{index:03d}",
                                    ],
                                },
                            }
                        },
                        status="raw",
                    )
                )

            report = state.source_soak_acceptance_report(limit=200)
            gate_status = {gate["id"]: gate["status"] for gate in report["gates"]}

            self.assertEqual(report["artifact_type"], "cryptoarc_source_soak_acceptance")
            self.assertEqual(report["status"], "ready")
            self.assertTrue(report["ready"])
            self.assertTrue(report["hard_required"])
            self.assertEqual(report["summary"]["matches"], 20)
            self.assertEqual(report["summary"]["match_rate"], 1.0)
            self.assertEqual(report["summary"]["decoded_create_rate"], 1.0)
            self.assertEqual(gate_status["direct_matches"], "pass")
            self.assertEqual(gate_status["decoded_coverage"], "pass")
            self.assertEqual(report["history_summary"]["snapshots"], 0)

            snapshot = state.record_source_soak_snapshot(limit=200)
            self.assertEqual(snapshot["status"], "ready")
            self.assertEqual(snapshot["history_summary"]["snapshots"], 1)
            self.assertEqual(state.storage.count_source_soak_history(), 1)

            reloaded = BotState(
                database_path=str(database_path),
                default_solana_wss_endpoint="wss://example.invalid",
                default_solana_logs_mentions_address="PumpFunProgram111",
            )
            history = reloaded.storage.load_source_soak_history(5)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["status"], "ready")
            self.assertTrue(history[0]["ready"])

    def test_source_soak_history_storage_round_trip(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "test.db"))

            storage.save_source_soak_snapshot(
                {
                    "id": "soak_snapshot_1",
                    "created_at": utc_now().isoformat(),
                    "status": "blocked",
                    "ready": False,
                    "summary": {"direct_events": 4, "match_rate": 0.25, "decoded_create_rate": 0.0},
                }
            )

            self.assertEqual(storage.count_source_soak_history(), 1)
            history = storage.load_source_soak_history()
            self.assertEqual(history[0]["id"], "soak_snapshot_1")
            self.assertEqual(history[0]["status"], "blocked")
            self.assertFalse(history[0]["ready"])

    def test_strategy_promotion_blocks_when_configured_direct_soak_is_incomplete(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(
                database_path=str(Path(directory) / "test.db"),
                default_solana_wss_endpoint="wss://example.invalid",
                default_solana_logs_mentions_address="PumpFunProgram111",
            )
            self.seed_readiness_dataset(state, pnl_sol=0.03, source_connected=True)

            readiness = state.readiness_status()
            promotion = readiness["strategy_promotion"]
            gate_status = {gate["id"]: gate["status"] for gate in promotion["gates"]}

            self.assertFalse(promotion["can_promote"])
            self.assertEqual(gate_status["source_soak"], "fail")
            self.assertTrue(promotion["source_soak"]["hard_required"])
            self.assertTrue(any("Direct/PumpPortal soak must pass" in blocker for blocker in promotion["blockers"]))

    def test_apply_tuning_suggestion_updates_settings(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            result = state.apply_tuning_suggestion("cooldown_after_loss_enabled", True)

            self.assertTrue(state.settings.cooldown_after_loss_enabled)
            self.assertEqual(result["setting"], "cooldown_after_loss_enabled")
            self.assertTrue(result["suggested_value"])

    def test_tuning_suggestions_include_evidence_and_review_fields(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state, pnl_sol=-0.01, source_connected=True)

            suggestion = state.tuning_suggestions()[0]

            self.assertIn("expected_benefit", suggestion)
            self.assertGreaterEqual(suggestion["supporting_sample_size"], 1)
            self.assertEqual(suggestion["supporting_closed_trades"], 30)
            self.assertLess(suggestion["supporting_pnl_sol"], 0)
            self.assertIn(suggestion["overfit_risk"], {"low", "medium", "high"})
            self.assertTrue(suggestion["requires_operator_review"])
            self.assertIn("settings version", suggestion["review_note"])

    def test_orphaned_open_token_is_recovered_on_startup(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.db"
            state = BotState(database_path=str(database_path))
            for index in range(85):
                token = self.make_token()
                token.id = f"tok_recent_{index}"
                token.mint = f"MintRecent{index}"
                token.detected_at = utc_now()
                token.status = TokenStatus.SKIPPED
                state.storage.save_token(token)
            orphan = self.make_token()
            orphan.id = "tok_orphan"
            orphan.mint = "MintOrphan"
            orphan.detected_at = utc_now().replace(year=2025)
            orphan.status = TokenStatus.MONITORING
            orphan.entry_price = 0.00001
            orphan.current_price = 0.000011
            orphan.amount_sol = 0.1
            orphan.opened_at = utc_now().replace(year=2025)
            state.storage.save_token(orphan)

            reloaded = BotState(database_path=str(database_path))
            recovered = next(token for token in reloaded.storage.load_all_tokens(5000) if token.id == "tok_orphan")

            self.assertEqual(recovered.status, TokenStatus.PAPER_SOLD)
            self.assertEqual(recovered.exit_reason, "orphaned state recovery")

    def test_no_private_key_fields_are_added_to_settings_or_live_audit(self) -> None:
        settings_keys = set(BotSettings.__dataclass_fields__.keys())
        audit_keys = set(LiveExecutionAudit.__dataclass_fields__.keys())

        self.assertFalse(any("private" in key.lower() or "seed" in key.lower() for key in settings_keys))
        self.assertFalse(any("private" in key.lower() or "seed" in key.lower() for key in audit_keys))


if __name__ == "__main__":
    unittest.main()
