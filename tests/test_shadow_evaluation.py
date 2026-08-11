from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.auth import AuthManager
from app.core.models import AcceptedMarketObservation, LiveExecutionAudit, ShadowComparison, ShadowCostBreakdown
from app.core.pilot_risk import PilotRiskPolicy
from app.core.shadow_evaluation import EconomicValidator
from app.core.state import BotState
from app.core.storage import Storage


NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def comparison(
    index: int = 0,
    *,
    gross: float = 1.0,
    base: float = 0.1,
    variable: float = 0.2,
    day: int = 0,
    regime: str = "normal",
    held_out: bool = False,
    strategy_version: str = "sniper-v1",
    evidence_mode: str = "shadow",
    fixture_only: bool = False,
    landing_status: str = "evaluated",
    contaminated: bool = False,
    reference_usd_per_sol: float = 1.0,
) -> ShadowComparison:
    completed_at = NOW - timedelta(days=6 - day, minutes=index)
    return ShadowComparison(
        record_id=f"shadow-{index}-{day}-{regime}",
        created_at=completed_at - timedelta(minutes=1),
        schema_version=1,
        strategy_id="sniper",
        strategy_version=strategy_version,
        evidence_mode=evidence_mode,
        completed_at=completed_at,
        regime=regime,
        gross_pnl_sol=gross,
        costs=ShadowCostBreakdown(
            base_fee_sol=base,
            priority_fee_sol=variable,
            inclusion_tip_sol=0.0,
            rent_setup_sol=0.0,
            failed_attempt_sol=0.0,
            entry_slippage_sol=0.0,
            exit_slippage_sol=0.0,
        ),
        held_out=held_out,
        source_evidence_ids=(f"source-{index}",),
        quote_id=f"quote-{index}",
        landing_status=landing_status,
        fixture_only=fixture_only,
        contaminated=contaminated,
        exit_reason="take_profit" if gross > 0 else "stop_loss",
        hold_seconds=30,
        reference_usd_per_sol=reference_usd_per_sol,
    )


def ready_campaign() -> list[ShadowComparison]:
    rows: list[ShadowComparison] = []
    for index in range(100):
        rows.append(
            comparison(
                index,
                gross=1.0 if index % 4 else -0.3,
                base=0.02,
                variable=0.01,
                day=index % 7,
                regime="high" if index % 2 else "normal",
                held_out=index >= 80,
            )
        )
    return rows


class ShadowEvaluationTests(unittest.TestCase):
    def test_cost_stress_doubles_only_variable_execution_costs(self) -> None:
        report = EconomicValidator.evaluate("sniper-v1", [comparison(gross=1.0, base=0.1, variable=0.2)], NOW)

        self.assertAlmostEqual(report.cost_stress.net_pnl, 1.0 - 0.1 - 0.4)

    def test_every_cost_component_is_accounted_for(self) -> None:
        costs = ShadowCostBreakdown(
            base_fee_sol=0.01,
            priority_fee_sol=0.02,
            inclusion_tip_sol=0.03,
            rent_setup_sol=0.04,
            failed_attempt_sol=0.05,
            entry_slippage_sol=0.06,
            exit_slippage_sol=0.07,
        )

        self.assertAlmostEqual(costs.total_sol(), 0.28)
        self.assertAlmostEqual(costs.stressed_total_sol(), 0.51)

    def test_ready_campaign_meets_all_distinct_economic_gates(self) -> None:
        report = EconomicValidator.evaluate("sniper-v1", ready_campaign(), NOW)

        self.assertTrue(report.ready)
        self.assertEqual(report.blockers, ())
        self.assertEqual(report.sample_count, 100)
        self.assertEqual(report.calendar_days, 7)
        self.assertEqual(report.regimes, ("high", "normal"))
        self.assertGreaterEqual(report.profit_factor, 1.2)
        self.assertGreater(report.held_out.net_pnl, 0)

    def test_fixture_quote_and_wrong_mode_do_not_become_completed_shadows(self) -> None:
        rows = ready_campaign()
        rows.extend(
            [
                comparison(200, fixture_only=True),
                comparison(201, landing_status="quote_ready"),
                comparison(202, evidence_mode="paper"),
            ]
        )
        report = EconomicValidator.evaluate("sniper-v1", rows, NOW)

        self.assertEqual(report.sample_count, 100)
        self.assertEqual(report.fixture_count, 1)
        self.assertIn("incomplete_shadow_comparison", report.blockers)
        self.assertIn("evidence_mode_contamination", report.blockers)

    def test_future_version_mismatch_and_explicit_contamination_block(self) -> None:
        future = comparison(1, strategy_version="sniper-v2", contaminated=True)
        future.completed_at = NOW + timedelta(seconds=1)
        report = EconomicValidator.evaluate("sniper-v1", [future], NOW)

        self.assertFalse(report.ready)
        self.assertIn("future_shadow_evidence", report.blockers)
        self.assertIn("strategy_version_mismatch", report.blockers)
        self.assertIn("evidence_mode_contamination", report.blockers)

    def test_each_threshold_reports_a_distinct_blocker(self) -> None:
        rows = [comparison(index, gross=-1.0, day=index % 2, regime="normal", held_out=index >= 8) for index in range(10)]
        report = EconomicValidator.evaluate("sniper-v1", rows, NOW)

        for blocker in (
            "sample_count_below_100",
            "calendar_span_below_7_days",
            "multiple_regimes_required",
            "aggregate_net_pnl_not_positive",
            "profit_factor_below_1_20",
            "max_drawdown_above_10_percent",
            "held_out_result_not_positive",
            "cost_stress_catastrophic",
        ):
            self.assertIn(blocker, report.blockers)

    def test_walk_forward_collapse_is_detected(self) -> None:
        rows = ready_campaign()
        for item in rows[-20:]:
            item.gross_pnl_sol = 0.031
        report = EconomicValidator.evaluate("sniper-v1", rows, NOW)

        self.assertIn("walk_forward_collapse", report.blockers)

    def test_drawdown_is_a_percent_of_modeled_one_hundred_dollar_equity(self) -> None:
        cases = (
            (9.99, False),
            (10.00, False),
            (10.01, True),
        )
        for drawdown_usd, blocked in cases:
            with self.subTest(drawdown_usd=drawdown_usd):
                row = comparison(
                    gross=-(drawdown_usd / 200), base=0, variable=0,
                    reference_usd_per_sol=200,
                )
                metrics = EconomicValidator._metrics([row], cost_stress=False)
                self.assertAlmostEqual(metrics.max_drawdown, drawdown_usd, places=6)
                self.assertEqual(metrics.max_drawdown > EconomicValidator.MAX_DRAWDOWN_PERCENT, blocked)

    def test_missing_sol_usd_reference_fails_closed(self) -> None:
        report = EconomicValidator.evaluate(
            "sniper-v1",
            [comparison(reference_usd_per_sol=0)],
            NOW,
        )
        self.assertIn("sol_usd_reference_missing", report.blockers)

    def test_comparisons_round_trip_with_cost_identity(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "shadow.db"))
            item = comparison()
            self.assertTrue(storage.save_shadow_comparison(item))
            loaded = storage.load_shadow_comparisons(limit=10, strategy_version="sniper-v1")

        self.assertEqual(loaded, [item])

    def test_comparison_record_identity_is_append_only(self) -> None:
        with TemporaryDirectory() as directory:
            storage = Storage(str(Path(directory) / "shadow.db"))
            item = comparison()
            self.assertTrue(storage.save_shadow_comparison(item))
            self.assertFalse(storage.save_shadow_comparison(item))
            changed = comparison(gross=2.0)
            with self.assertRaisesRegex(ValueError, "different content"):
                storage.save_shadow_comparison(changed)

    def test_authenticated_economic_report_fails_closed_without_campaign(self) -> None:
        from app import main as main_app

        with TemporaryDirectory() as directory:
            previous_state = main_app.state
            previous_auth = main_app.auth
            main_app.state = BotState(database_path=str(Path(directory) / "shadow.db"))
            main_app.auth = AuthManager(password="desktop-pass")
            token = main_app.auth.login("desktop-pass")
            try:
                client = TestClient(main_app.app)
                denied = client.get("/api/reports/economic-validation")
                allowed = client.get(
                    "/api/reports/economic-validation?strategy_version=sniper-v1",
                    headers={"Authorization": f"Bearer {token}"},
                )
            finally:
                main_app.state = previous_state
                main_app.auth = previous_auth

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 200)
        self.assertFalse(allowed.json()["ready"])
        self.assertIn("sample_count_below_100", allowed.json()["blockers"])

    def test_evaluated_runtime_shadow_is_persisted_with_genuine_source_and_usd_reference(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "shadow.db"))
            policy = PilotRiskPolicy.create(
                Decimal("200"), Decimal("0.4"), NOW - timedelta(minutes=10),
                reference_observation_id="sol-usd-1", settings_version=state.current_settings_version_id,
                operator_intent_id="intent-1",
            )
            state.storage.save_pilot_risk_policy(policy)
            state.storage.save_accepted_market_observation(AcceptedMarketObservation(
                record_id="market-1", created_at=NOW - timedelta(minutes=1), schema_version=1,
                strategy_id=state.settings.strategy_profile, strategy_version=state.current_settings_version_id,
                evidence_mode="shadow", source="pumpportal", source_event_id="source-1",
                observed_at=NOW - timedelta(minutes=1), received_at=NOW - timedelta(minutes=1),
                mint="mint-1", price=0.0001, confidence=0.9, acceptance_reason="direct: accepted",
            ))
            audit = LiveExecutionAudit(
                id="audit-1", created_at=NOW - timedelta(minutes=2), updated_at=NOW,
                action="buy", mint="mint-1", amount="0.01", status="ready",
                signer_mode="local_hot_wallet", wallet_public_key="wallet-1", quote={"id": "quote-1"},
                shadow_comparison={
                    "status": "evaluated", "exit_observed_at": NOW.isoformat(), "gross_pnl_sol": 0.002,
                    "exit_reason": "take_profit", "hold_duration_seconds": 60,
                    "costs": {"paper_fee_drag_sol": 0.0001, "priority_fee_sol": 0.00001, "price_impact_drag_sol": 0.00002},
                },
            )

            self.assertTrue(state._persist_economic_shadow_comparison(audit))
            self.assertFalse(state._persist_economic_shadow_comparison(audit))
            stored = state.storage.load_shadow_comparisons(limit=10)
            self.assertEqual(stored[0].source_evidence_ids, ("market-1",))
            self.assertEqual(stored[0].reference_usd_per_sol, 200.0)
            self.assertFalse(stored[0].fixture_only)


if __name__ == "__main__":
    unittest.main()
