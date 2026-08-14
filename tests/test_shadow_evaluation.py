from __future__ import annotations

import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.auth import AuthManager
from app.core.models import AcceptedMarketObservation, LiveExecutionAudit, ShadowComparison, ShadowCostBreakdown, ShadowTrackingCandidate, TokenSignal, TokenStatus, utc_now
from app.core.pilot_risk import PilotRiskPolicy
from app.core.shadow_evaluation import EconomicValidator
from app.core.sources import LaunchEvent
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
            state.settings.take_profit_pct = 5
            state.settings.paper_fee_bps = 100
            state.storage.save_settings(state.settings)
            state.current_settings_version_id = state.ensure_settings_version(
                "captured shadow rules", ["take_profit_pct", "paper_fee_bps"]
            )
            policy = PilotRiskPolicy.create(
                Decimal("200"), Decimal("0.4"), NOW - timedelta(minutes=10),
                reference_observation_id="sol-usd-1", settings_version=state.current_settings_version_id,
                operator_intent_id="intent-1",
            )
            state.storage.save_pilot_risk_policy(policy)
            state.storage.save_accepted_market_observation(AcceptedMarketObservation(
                record_id="market-exit", created_at=NOW - timedelta(minutes=1), schema_version=1,
                strategy_id=state.settings.strategy_profile, strategy_version=state.current_settings_version_id,
                evidence_mode="shadow", source="pumpportal", source_event_id="source-exit",
                observed_at=NOW - timedelta(minutes=1), received_at=NOW - timedelta(minutes=1),
                mint="mint-1", price=0.00011, confidence=0.9, acceptance_reason="direct: accepted",
            ))
            audit = LiveExecutionAudit(
                id="audit-1", created_at=NOW - timedelta(minutes=2), updated_at=NOW,
                action="buy", mint="mint-1", amount="0.01", status="ready",
                signer_mode="local_hot_wallet", wallet_public_key="wallet-1", quote={"id": "quote-1"},
                shadow_comparison={
                    "status": "evaluated", "exit_observed_at": NOW.isoformat(), "gross_pnl_sol": 0.002,
                    "quoted_at": (NOW - timedelta(minutes=2)).isoformat(),
                    "strategy_id": state.settings.strategy_profile,
                    "strategy_version": state.current_settings_version_id,
                    "exit_reason": "take_profit", "hold_duration_seconds": 60,
                    "costs": {"paper_fee_drag_sol": 0.0001, "priority_fee_sol": 0.00001, "price_impact_drag_sol": 0.00002},
                },
            )

            state.storage.save_accepted_market_observation(AcceptedMarketObservation(
                record_id="market-paper-entry", created_at=NOW - timedelta(minutes=3), schema_version=1,
                strategy_id=state.settings.strategy_profile, strategy_version=state.current_settings_version_id,
                evidence_mode="paper", source="pumpportal", source_event_id="source-paper-entry",
                observed_at=NOW - timedelta(minutes=3), received_at=NOW - timedelta(minutes=3),
                mint="mint-1", price=0.0001, confidence=0.9, acceptance_reason="direct: accepted",
            ))
            self.assertFalse(state._persist_economic_shadow_comparison(audit))
            state.storage.save_accepted_market_observation(AcceptedMarketObservation(
                record_id="market-entry", created_at=NOW - timedelta(minutes=3), schema_version=1,
                strategy_id=state.settings.strategy_profile, strategy_version=state.current_settings_version_id,
                evidence_mode="shadow", source="pumpportal", source_event_id="source-entry",
                observed_at=NOW - timedelta(minutes=3), received_at=NOW - timedelta(minutes=3),
                mint="mint-1", price=0.0001, confidence=0.9, acceptance_reason="direct: accepted",
            ))
            for market_observation_id, role in (("market-entry", "entry"), ("market-exit", "path")):
                state.storage.save_shadow_market_evidence_binding(
                    audit_id=audit.id,
                    market_observation_id=market_observation_id,
                    strategy_id=state.settings.strategy_profile,
                    strategy_version=state.current_settings_version_id,
                    role=role,
                    created_at=NOW,
                )
            state.settings.take_profit_pct = 50
            state.settings.paper_fee_bps = 900
            self.assertTrue(state._persist_economic_shadow_comparison(audit))
            self.assertTrue(state._persist_economic_shadow_comparison(audit))
            stored = state.storage.load_shadow_comparisons(limit=10)
            self.assertEqual(stored[0].source_evidence_ids, ("market-entry", "market-exit"))
            self.assertEqual(stored[0].reference_usd_per_sol, 200.0)
            self.assertFalse(stored[0].fixture_only)
            self.assertEqual(stored[0].exit_reason, "take profit")
            self.assertAlmostEqual(stored[0].costs.base_fee_sol, 0.0002)
            self.assertEqual(audit.shadow_comparison["economic_evidence"]["entry_market_evidence_id"], "market-entry")
            self.assertEqual(audit.shadow_comparison["economic_evidence"]["exit_market_evidence_id"], "market-exit")

    def test_production_ingestion_binds_real_observations_to_shadow_quote_and_materializes(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "shadow.db"))
            state.settings.take_profit_pct = 5
            state.settings.paper_fee_bps = 100
            state.settings.live_max_trade_sol = 0.02
            state.settings.live_max_slippage_pct = 5
            state.settings.live_priority_fee_cap_sol = 0.001
            state.storage.save_settings(state.settings)
            state.current_settings_version_id = state.ensure_settings_version(
                "production shadow capture", ["take_profit_pct", "paper_fee_bps"]
            )
            now = utc_now()
            state.storage.save_pilot_risk_policy(PilotRiskPolicy.create(
                Decimal("200"), Decimal("0.4"), now - timedelta(minutes=1),
                reference_observation_id="sol-usd-production", settings_version=state.current_settings_version_id,
                operator_intent_id="intent-production",
            ))
            token = TokenSignal(
                id="token-production-shadow", symbol="SHDW", name="Shadow", mint="mint-production-shadow",
                creator="creator", detected_at=now - timedelta(minutes=1), status=TokenStatus.MONITORING,
                entry_price=1.0, current_price=1.0,
            )
            state.tokens.append(token)
            state.storage.save_token(token)

            state.ingest_source_event(LaunchEvent(
                source="pumpportal", received_at=now - timedelta(seconds=1),
                raw_payload={"signature": "entry-source", "mint": token.mint, "txType": "buy", "price": 1.0},
                token=None, kind="trade", mint=token.mint, trade_side="buy",
            ))
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            quoted = state.live_quote(
                False, "buy", token.mint, "0.01", True, 1, 0.00001, "pump", "WalletShadow",
                shadow_only=True,
            )
            audit = state.storage.load_live_execution_audit(str(quoted["id"]))
            self.assertIsNotNone(audit)

            # The campaign may close the paper token before the paid stream emits
            # the shadow exit tick. Accepted market evidence must still drive the
            # shadow evaluator even though the active-token price table no longer
            # receives that tick.
            token.status = TokenStatus.PAPER_SOLD
            state.storage.save_token(token)

            for index in range(501):
                unrelated_at = audit.created_at + timedelta(milliseconds=index + 1)
                state.storage.save_live_execution_audit(LiveExecutionAudit(
                    id=f"unrelated-newer-{index}", created_at=unrelated_at, updated_at=unrelated_at,
                    action="sell", mint=f"unrelated-mint-{index}", amount="100%", status="ready",
                    signer_mode="browser_wallet", wallet_public_key="OtherWallet",
                ))

            state.ingest_source_event(LaunchEvent(
                source="pumpportal", received_at=audit.created_at + timedelta(seconds=5),
                raw_payload={"signature": "exit-source", "mint": token.mint, "txType": "sell", "price": 1.1},
                token=None, kind="trade", mint=token.mint, trade_side="sell",
            ))
            refreshed = state.storage.load_live_execution_audit(audit.id)
            accepted = state.storage.load_accepted_market_observations(limit=10)
            bindings = state.storage.load_shadow_market_evidence_bindings(audit.id)
            materialized = state.storage.load_shadow_comparisons(limit=10)

            self.assertIsNotNone(refreshed)
            self.assertEqual(refreshed.shadow_comparison["status"], "evaluated")
            self.assertTrue(refreshed.shadow_comparison["landing_windows"])
            immediate_window = next(item for item in refreshed.shadow_comparison["landing_windows"] if item["delay_ms"] == 0)
            self.assertEqual(immediate_window["status"], "evaluated")
            self.assertEqual(immediate_window["move_pct"], refreshed.shadow_comparison["move_pct"])
            self.assertEqual({item["role"] for item in bindings}, {"entry", "path"})
            self.assertEqual({item.evidence_mode for item in accepted}, {"paper"})
            self.assertEqual(len({item.source_event_id for item in accepted}), 2)
            self.assertEqual(len(materialized), 1)
            self.assertEqual(set(materialized[0].source_evidence_ids), {item.record_id for item in accepted})

    def test_subthreshold_price_tick_does_not_prematurely_complete_shadow(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "shadow.db"))
            state.settings.take_profit_pct = 50
            state.settings.stop_loss_pct = 30
            state.settings.minimum_hold_time_seconds = 0
            state.settings.max_hold_time_seconds = 600
            state.settings.max_position_ticks = 1000
            state.settings.live_max_trade_sol = 0.02
            state.settings.live_max_slippage_pct = 5
            state.settings.live_priority_fee_cap_sol = 0.001
            state.storage.save_settings(state.settings)
            state.current_settings_version_id = state.ensure_settings_version(
                "shadow exit-rule evidence", [
                    "take_profit_pct",
                    "stop_loss_pct",
                    "minimum_hold_time_seconds",
                    "max_hold_time_seconds",
                    "max_position_ticks",
                ]
            )
            now = utc_now()
            token = TokenSignal(
                id="token-waiting-shadow", symbol="WAIT", name="Waiting Shadow",
                mint="mint-waiting-shadow", creator="creator", detected_at=now - timedelta(minutes=1),
                status=TokenStatus.MONITORING, entry_price=1.0, current_price=1.0,
            )
            state.tokens.append(token)
            state.storage.save_token(token)
            state.ingest_source_event(LaunchEvent(
                source="pumpportal", received_at=now - timedelta(seconds=1),
                raw_payload={"signature": "entry-waiting", "mint": token.mint, "txType": "buy", "price": 1.0},
                token=None, kind="trade", mint=token.mint, trade_side="buy",
            ))
            state._pumpportal_local_transaction = lambda **kwargs: ({"ok": True}, "dHgi", "")
            quoted = state.live_quote(
                False, "buy", token.mint, "0.01", True, 1, 0.00001, "pump", "WalletShadow",
                shadow_only=True,
            )
            audit = state.storage.load_live_execution_audit(str(quoted["id"]))
            self.assertIsNotNone(audit)

            state.ingest_source_event(LaunchEvent(
                source="pumpportal", received_at=audit.created_at + timedelta(seconds=5),
                raw_payload={"signature": "path-waiting", "mint": token.mint, "txType": "sell", "price": 1.01},
                token=None, kind="trade", mint=token.mint, trade_side="sell",
            ))

            refreshed = state.storage.load_live_execution_audit(audit.id)
            immediate_window = next(
                item for item in refreshed.shadow_comparison["landing_windows"] if item["delay_ms"] == 0
            )
            self.assertEqual(refreshed.shadow_comparison["status"], "waiting_for_exit_rule")
            self.assertEqual(refreshed.shadow_comparison["evaluation_model"], "exit_rules_v2_strict")
            self.assertEqual(immediate_window["status"], "waiting_for_exit_rule")
            self.assertEqual(state.storage.load_shadow_comparisons(limit=10), [])
            self.assertEqual(state.storage.count_pending_shadow_audit_captures(audit.id), 1)

    def test_evaluated_shadow_capture_stays_pending_until_economic_evidence_persists(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "shadow.db"))
            version_id = state.ensure_settings_version("pending economic evidence", [])
            now = utc_now()
            audit = LiveExecutionAudit(
                id="pending-economic-audit", created_at=now, updated_at=now,
                action="buy", mint="pending-economic-mint", amount="0.01", status="ready",
                signer_mode="browser_wallet", wallet_public_key="PendingWallet",
                quote={"id": "pending-economic-quote", "shadow_only": True},
                shadow_comparison={
                    "mode": "dry_run_shadow", "status": "evaluated",
                    "strategy_id": state.settings.strategy_profile,
                    "strategy_version": version_id,
                    "entry_price": 1.0, "quoted_at": now.isoformat(),
                },
            )
            state.storage.save_shadow_quote_audit_capture(audit, None)

            state._evaluate_shadow_comparison = lambda item: item.shadow_comparison
            state._persist_economic_shadow_comparison = lambda item: False

            state._refresh_shadow_comparisons([audit])

            with state.storage._connect() as connection:
                status = connection.execute(
                    "SELECT status FROM pending_shadow_audit_captures WHERE audit_id = ?",
                    (audit.id,),
                ).fetchone()["status"]
            self.assertEqual(status, "pending")
            self.assertEqual(state.storage.load_shadow_comparisons(limit=10), [])

    def test_stale_shadow_audit_closes_legacy_pending_capture(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "shadow.db"))
            version_id = state.ensure_settings_version("stale capture reconciliation", [])
            now = utc_now()
            audit = LiveExecutionAudit(
                id="stale-shadow-audit", created_at=now - timedelta(minutes=20), updated_at=now,
                action="buy", mint="stale-shadow-mint", amount="0.01", status="stale", final_status="stale",
                signer_mode="browser_wallet", wallet_public_key="StaleWallet",
                quote={"id": "stale-shadow-quote", "shadow_only": True},
                shadow_comparison={
                    "mode": "dry_run_shadow", "status": "waiting_for_price",
                    "strategy_id": state.settings.strategy_profile,
                    "strategy_version": version_id,
                    "quoted_at": (now - timedelta(minutes=20)).isoformat(),
                },
            )
            state.storage.save_shadow_quote_audit_capture(audit, None)
            self.assertEqual(state.storage.count_pending_shadow_audit_captures(audit.id), 1)

            state._normalize_live_audits([audit])

            self.assertEqual(state.storage.count_pending_shadow_audit_captures(audit.id), 0)
            with state.storage._connect() as connection:
                row = connection.execute(
                    "SELECT status, closed_at FROM pending_shadow_audit_captures WHERE audit_id = ?",
                    (audit.id,),
                ).fetchone()
            self.assertEqual(row["status"], "closed")
            self.assertIsNotNone(row["closed_at"])

    def test_recent_direct_stale_shadow_capture_stays_open_for_evaluation_window(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "shadow.db"))
            state.settings.max_hold_time_seconds = 600
            version_id = state.ensure_settings_version("direct stale window", ["max_hold_time_seconds"])
            now = utc_now()
            audit = LiveExecutionAudit(
                id="direct-stale-audit", created_at=now - timedelta(minutes=1), updated_at=now,
                action="buy", mint="direct-stale-mint", amount="0.01", status="stale", final_status="stale",
                signer_mode="browser_wallet", wallet_public_key="DirectWallet",
                quote={"id": "direct-stale-quote", "shadow_only": True},
                shadow_comparison={
                    "mode": "dry_run_shadow", "status": "waiting_for_price",
                    "strategy_id": state.settings.strategy_profile,
                    "strategy_version": version_id,
                    "quoted_at": (now - timedelta(minutes=1)).isoformat(),
                },
            )
            state.storage.save_shadow_quote_audit_capture(audit, None)

            state._normalize_live_audits([audit])

            self.assertEqual(state.storage.count_pending_shadow_audit_captures(audit.id), 1)

    def test_startup_reconciles_expired_stale_shadow_capture(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "shadow.db")
            state = BotState(database_path=database_path)
            state.settings.max_hold_time_seconds = 60
            state.storage.save_settings(state.settings)
            version_id = state.ensure_settings_version("startup stale window", ["max_hold_time_seconds"])
            now = utc_now()
            audit = LiveExecutionAudit(
                id="startup-stale-audit", created_at=now - timedelta(minutes=5), updated_at=now,
                action="buy", mint="startup-stale-mint", amount="0.01", status="stale", final_status="stale",
                signer_mode="browser_wallet", wallet_public_key="StartupWallet",
                quote={"id": "startup-stale-quote", "shadow_only": True},
                shadow_comparison={
                    "mode": "dry_run_shadow", "status": "waiting_for_price",
                    "strategy_id": state.settings.strategy_profile,
                    "strategy_version": version_id,
                    "quoted_at": (now - timedelta(minutes=5)).isoformat(),
                },
            )
            state.storage.save_shadow_quote_audit_capture(audit, None)
            self.assertEqual(state.storage.count_pending_shadow_audit_captures(audit.id), 1)

            reloaded = BotState(database_path=database_path)

            self.assertEqual(reloaded.storage.count_pending_shadow_audit_captures(audit.id), 0)

    def test_stale_quote_keeps_capture_open_for_active_tracking_candidate(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "shadow.db"))
            version_id = state.ensure_settings_version("active stale quote", [])
            now = utc_now()
            audit = LiveExecutionAudit(
                id="active-stale-audit", created_at=now - timedelta(minutes=1), updated_at=now,
                action="buy", mint="active-stale-mint", amount="0.01", status="stale", final_status="stale",
                signer_mode="browser_wallet", wallet_public_key="ActiveWallet",
                quote={"id": "active-stale-quote", "shadow_only": True},
                shadow_comparison={
                    "mode": "dry_run_shadow", "status": "waiting_for_price",
                    "strategy_id": state.settings.strategy_profile,
                    "strategy_version": version_id,
                    "quoted_at": (now - timedelta(minutes=1)).isoformat(),
                },
            )
            state.storage.save_shadow_quote_audit_capture(audit, None)
            candidate = ShadowTrackingCandidate(
                candidate_id="active-stale-candidate", intent_id="active-stale-intent",
                mint=audit.mint, strategy_id=state.settings.strategy_profile,
                strategy_version=version_id, state="tracking_shadow",
                selected_at=now - timedelta(minutes=1), deadline_at=now + timedelta(minutes=9),
                audit_id=audit.id, reason="tracking later paper observation", updated_at=now,
            )
            state.storage.save_shadow_tracking_candidate(candidate)

            state._normalize_live_audits([audit])

            self.assertEqual(state.storage.count_pending_shadow_audit_captures(audit.id), 1)

    def test_data_summary_counts_only_open_shadow_captures(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "shadow.db"))
            version_id = state.ensure_settings_version("pending summary", [])
            now = utc_now()
            for audit_id in ("open-capture", "closed-capture"):
                audit = LiveExecutionAudit(
                    id=audit_id, created_at=now, updated_at=now,
                    action="buy", mint=f"{audit_id}-mint", amount="0.01", status="ready",
                    signer_mode="browser_wallet", wallet_public_key="SummaryWallet",
                    quote={"id": f"{audit_id}-quote", "shadow_only": True},
                    shadow_comparison={
                        "mode": "dry_run_shadow", "status": "waiting_for_price",
                        "strategy_id": state.settings.strategy_profile,
                        "strategy_version": version_id, "quoted_at": now.isoformat(),
                    },
                )
                state.storage.save_shadow_quote_audit_capture(audit, None)
            state.storage.close_pending_shadow_audit_capture("closed-capture", closed_at=now)

            self.assertEqual(state.storage.count_pending_shadow_audit_captures(), 1)
            self.assertEqual(state.data_summary()["pending_shadow_audit_captures"], 1)

    def test_existing_economic_record_closes_pending_capture_on_retry(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "shadow.db"))
            state.settings.take_profit_pct = 50
            state.settings.paper_fee_bps = 100
            state.storage.save_settings(state.settings)
            version_id = state.ensure_settings_version("retry economic close", ["take_profit_pct", "paper_fee_bps"])
            now = utc_now()
            state.storage.save_pilot_risk_policy(PilotRiskPolicy.create(
                Decimal("200"), Decimal("0.4"), now - timedelta(minutes=1),
                reference_observation_id="sol-usd-retry", settings_version=version_id,
                operator_intent_id="intent-retry",
            ))
            entry = AcceptedMarketObservation(
                record_id="retry-entry", created_at=now - timedelta(seconds=1), schema_version=1,
                strategy_id=state.settings.strategy_profile, strategy_version=version_id,
                evidence_mode="paper", source="pumpportal", source_event_id="retry-entry-source",
                observed_at=now - timedelta(seconds=1), received_at=now - timedelta(seconds=1),
                mint="retry-mint", price=1.0, confidence=0.9, acceptance_reason="direct: accepted",
            )
            exit_observation = AcceptedMarketObservation(
                record_id="retry-exit", created_at=now + timedelta(seconds=1), schema_version=1,
                strategy_id=state.settings.strategy_profile, strategy_version=version_id,
                evidence_mode="paper", source="pumpportal", source_event_id="retry-exit-source",
                observed_at=now + timedelta(seconds=1), received_at=now + timedelta(seconds=1),
                mint="retry-mint", price=1.6, confidence=0.9, acceptance_reason="direct: accepted",
            )
            state.storage.save_accepted_market_observation(entry)
            state.storage.save_accepted_market_observation(exit_observation)
            audit = LiveExecutionAudit(
                id="retry-audit", created_at=now, updated_at=now,
                action="buy", mint="retry-mint", amount="0.01", status="ready",
                signer_mode="browser_wallet", wallet_public_key="RetryWallet",
                quote={"id": "retry-quote", "shadow_only": True},
                shadow_comparison={
                    "mode": "dry_run_shadow", "status": "evaluated", "entry_price": 1.0,
                    "quoted_at": now.isoformat(), "amount_sol": 0.01, "regime": "normal",
                    "strategy_id": state.settings.strategy_profile, "strategy_version": version_id,
                },
            )
            state.storage.save_shadow_quote_audit_capture(audit, entry)
            state.storage.save_shadow_market_evidence_binding(
                audit_id=audit.id, market_observation_id=exit_observation.record_id,
                strategy_id=state.settings.strategy_profile, strategy_version=version_id,
                role="path", created_at=now + timedelta(seconds=1),
            )
            self.assertTrue(state._persist_economic_shadow_comparison(audit))

            # Persisted economic evidence is immutable. A later storage-schema
            # migration must reuse it instead of rebuilding the same record
            # with a new schema_version and raising a content conflict.
            with state.storage._connect() as connection:
                row = connection.execute(
                    "SELECT payload FROM shadow_economic_comparisons WHERE record_id = ?",
                    (f"economic_{audit.id}",),
                ).fetchone()
                payload = json.loads(row["payload"])
                payload["schema_version"] = state.storage.SCHEMA_VERSION - 1
                connection.execute(
                    "UPDATE shadow_economic_comparisons SET payload = ? WHERE record_id = ?",
                    (json.dumps(payload), f"economic_{audit.id}"),
                )

            state._refresh_shadow_comparisons([audit])

            with state.storage._connect() as connection:
                status = connection.execute(
                    "SELECT status FROM pending_shadow_audit_captures WHERE audit_id = ?", (audit.id,)
                ).fetchone()["status"]
            self.assertEqual(status, "closed")

    def test_shadow_capture_rolls_back_if_audit_persistence_fails(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "shadow.db"))
            version_id = state.ensure_settings_version("rollback shadow capture", [])
            now = utc_now()
            entry = AcceptedMarketObservation(
                record_id="rollback-entry", created_at=now - timedelta(seconds=1), schema_version=1,
                strategy_id=state.settings.strategy_profile, strategy_version=version_id,
                evidence_mode="paper", source="pumpportal", source_event_id="rollback-source",
                observed_at=now - timedelta(seconds=1), received_at=now - timedelta(seconds=1),
                mint="rollback-mint", price=1.0, confidence=0.9, acceptance_reason="direct: accepted",
            )
            state.storage.save_accepted_market_observation(entry)
            audit = LiveExecutionAudit(
                id="rollback-audit", created_at=now, updated_at=now,
                action="buy", mint=entry.mint, amount="0.01", status="ready",
                signer_mode="browser_wallet", wallet_public_key="RollbackWallet",
                quote={"id": "rollback-quote", "shadow_only": True},
                shadow_comparison={
                    "mode": "dry_run_shadow", "status": "waiting_for_price",
                    "strategy_id": state.settings.strategy_profile, "strategy_version": version_id,
                },
            )
            with state.storage._connect() as connection:
                connection.execute(
                    """
                    CREATE TRIGGER fail_shadow_audit_insert
                    BEFORE INSERT ON live_execution_audits
                    WHEN NEW.id = 'rollback-audit'
                    BEGIN
                        SELECT RAISE(ABORT, 'injected audit persistence failure');
                    END
                    """
                )

            with self.assertRaises(sqlite3.IntegrityError):
                state.storage.save_shadow_quote_audit_capture(audit, entry)

            self.assertIsNone(state.storage.load_live_execution_audit(audit.id))
            self.assertEqual(state.storage.count_pending_shadow_audit_captures(audit.id), 0)
            self.assertEqual(state.storage.load_shadow_market_evidence_bindings(audit.id), [])


if __name__ == "__main__":
    unittest.main()
