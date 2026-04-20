import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from app.core.models import BacktestRun, BotSettings, BotStats, ExperimentRun, LiveExecutionAudit, LiveExecutionRequest, PriceObservation, SourceEvent, StrategyDecisionRecord, StrategyPreset, TokenSignal, TokenStatus, TradeLabel, TradeRecord, TradeSession, new_id, utc_now
from app.core.paper_trader import PaperTrader
from app.core.price_pipeline import PricePipeline
from app.core.risk import RiskEngine
from app.core.scoring import ScoringEngine
from app.core.sources import normalize_pumpportal_new_token, normalize_pumpportal_trade
from app.core.storage import Storage
from app.core.state import BotState


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
                    normalized_token_id=f"tok_ready_{index % 30}",
                    status="normalized",
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

    def test_paper_trade_closes_at_take_profit(self) -> None:
        token = self.make_token()
        settings = BotSettings(trade_size_sol=0.1, take_profit_pct=50, stop_loss_pct=30, paper_fee_bps=0, paper_price_impact_pct=0)
        trader = PaperTrader()
        trader.buy(token, settings)
        closed = trader.tick(token, settings, price_delta_pct=52)
        self.assertTrue(closed)
        self.assertEqual(token.status, TokenStatus.PAPER_SOLD)
        self.assertAlmostEqual(token.pnl_sol or 0, 0.052)
        self.assertEqual(token.exit_reason, "take profit")

    def test_paper_trade_can_delay_fill_and_charge_fees(self) -> None:
        token = self.make_token()
        settings = BotSettings(paper_fill_delay_ticks=1, paper_fee_bps=50, paper_price_impact_pct=0.2)
        trader = PaperTrader()
        trader.buy(token, settings)

        self.assertEqual(token.status, TokenStatus.BUYING)
        self.assertEqual(token.fill_delay_ticks_remaining, 1)
        self.assertFalse(trader.tick(token, settings, price_delta_pct=10))
        self.assertEqual(token.status, TokenStatus.PAPER_BOUGHT)
        self.assertGreater(token.fee_paid_sol, 0)
        self.assertGreater(token.price_impact_pct, 0)

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

    def test_fresh_state_defaults_to_pumpportal_source(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            self.assertEqual(state.settings.launch_source, "pumpportal")
            self.assertEqual(state.source_status.source, "pumpportal")

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

    def test_readiness_strong_dataset_is_ready(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state)

            readiness = state.readiness_status()

            self.assertEqual(readiness["status"], "ready")
            self.assertGreaterEqual(readiness["score"], 75)
            self.assertTrue(all(gate["status"] != "fail" for gate in readiness["gates"]))

    def test_readiness_source_failure_blocks_after_enough_data(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.seed_readiness_dataset(state, source_connected=False)

            readiness = state.readiness_status()
            source_gate = next(gate for gate in readiness["gates"] if gate["id"] == "source_health")

            self.assertEqual(readiness["status"], "blocked")
            self.assertEqual(source_gate["status"], "fail")

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

    def configure_live_caps(self, state: BotState) -> None:
        state.settings.live_max_trade_sol = 0.01
        state.settings.live_daily_loss_cap_sol = 0.05
        state.settings.live_wallet_exposure_cap_sol = 0.1
        state.settings.live_max_open_positions = 1
        state.settings.live_max_slippage_pct = 5
        state.settings.live_priority_fee_cap_sol = 0.0001
        state.settings.live_session_acknowledged = True

    def test_live_status_blocks_without_env_caps_or_wallet(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))

            status = state.live_status(env_live_enabled=False)

            self.assertFalse(status["live_execution_available"])
            self.assertIn("LIVE_TRADING_ENABLED is false", status["blockers"])
            self.assertIn("no connected signer", status["blockers"])
            self.assertTrue(any("max_trade_sol" in blocker for blocker in status["blockers"]))

    def test_browser_wallet_live_quote_creates_blocked_audit_when_env_disabled(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)

            audit = state.live_quote(False, "buy", "Mint111", "0.001", True, 1, 0.00001, "pump", "Wallet111")

            self.assertEqual(audit["status"], "blocked")
            self.assertIn("LIVE_TRADING_ENABLED is false", audit["errors"])
            self.assertEqual(state.storage.count_live_execution_audits(), 1)

    def test_live_quote_validates_caps_and_disabled_signer(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)

            too_large = state.live_quote(True, "buy", "Mint111", "0.02", True, 1, 0.00001, "pump", "Wallet111")
            daemon = state.live_quote(True, "buy", "Mint111", "0.001", True, 1, 0.00001, "pump", "Wallet111", signer_mode="local_signer_daemon")

            self.assertTrue(any("amount exceeds live max trade cap" in error for error in too_large["errors"]))
            self.assertIn("local signer daemon is disabled in v1", daemon["errors"])
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

    def test_live_submit_rejects_blocked_or_stale_quotes(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            blocked = state.live_quote(False, "buy", "Mint111", "0.001", True, 1, 0.00001, "pump", "Wallet111")

            with self.assertRaises(ValueError):
                state.live_submit(blocked["id"], "sig111")

    def test_live_intent_generation_cap_and_quote_expiry(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
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

    def test_live_kill_switch_blocks_new_intent_quotes(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            self.configure_live_caps(state)
            state.settings.kill_switch_enabled = True
            intent = state.create_live_intent("buy", "Mint111", "0.001", True, "Wallet111")

            quote = state.quote_live_intent(True, intent["id"], 1, 0.00001, "pump")

            self.assertEqual(quote["status"], "blocked")
            self.assertIn("manual kill switch enabled", quote["errors"])

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
            self.assertGreaterEqual(ledger["positions"][0]["cost_basis_sol"], 0.001)

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
            self.assertEqual(other_wallet["positions"], [])

    def test_no_private_key_fields_are_added_to_settings_or_live_audit(self) -> None:
        settings_keys = set(BotSettings.__dataclass_fields__.keys())
        audit_keys = set(LiveExecutionAudit.__dataclass_fields__.keys())

        self.assertFalse(any("private" in key.lower() or "seed" in key.lower() for key in settings_keys))
        self.assertFalse(any("private" in key.lower() or "seed" in key.lower() for key in audit_keys))


if __name__ == "__main__":
    unittest.main()
