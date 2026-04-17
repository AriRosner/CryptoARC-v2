import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from app.core.models import BacktestRun, BotSettings, BotStats, SourceEvent, TokenSignal, TokenStatus, new_id, utc_now
from app.core.paper_trader import PaperTrader
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


if __name__ == "__main__":
    unittest.main()
