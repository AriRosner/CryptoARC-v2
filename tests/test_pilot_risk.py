from __future__ import annotations

import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.core.pilot_risk import PilotRiskPolicy, PilotRiskRequest, PilotRiskState
from app.core.models import LiveExecutionAudit, LiveLedgerPosition
from app.core.state import BotState
from app.core.storage import Storage


NOW = datetime(2026, 8, 10, 23, 0, tzinfo=timezone.utc)


class PilotRiskPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = PilotRiskPolicy.create(
            reference_usd_per_sol=Decimal("200"),
            wallet_equity_sol=Decimal("0.4"),
            observed_at=NOW,
            reference_observation_id="price-1",
            settings_version="settings-1",
            operator_intent_id="intent-1",
        )

    def test_trade_cap_is_lower_of_five_dollars_or_five_percent_equity_and_rounds_down(self) -> None:
        self.assertEqual(self.policy.max_trade_sol, Decimal("0.0200"))
        rounded = PilotRiskPolicy.create(Decimal("199.99"), Decimal("0.33333"), NOW)
        self.assertEqual(rounded.max_trade_sol, Decimal("0.0166"))

    def test_usd_caps_convert_once_and_policy_is_immutable(self) -> None:
        self.assertEqual(self.policy.session_loss_stop_sol, Decimal("0.0500"))
        self.assertEqual(self.policy.daily_loss_stop_sol, Decimal("0.0500"))
        self.assertEqual(self.policy.cumulative_loss_freeze_sol, Decimal("0.1250"))
        with self.assertRaises(FrozenInstanceError):
            self.policy.max_trade_sol = Decimal("1")

    def test_entry_enforces_trade_position_loss_freeze_and_three_loss_boundaries(self) -> None:
        base_request = PilotRiskRequest("buy", Decimal("0.02"), Decimal("3"), Decimal("0.001"))
        self.assertTrue(self.policy.evaluate_entry(base_request, PilotRiskState()).allowed)
        cases = (
            (replace(base_request, requested_sol=Decimal("0.0201")), PilotRiskState(), "trade_cap"),
            (base_request, PilotRiskState(open_positions=1), "one_position"),
            (base_request, PilotRiskState(session_pnl_sol=Decimal("-0.05")), "session_loss_stop"),
            (base_request, PilotRiskState(daily_pnl_sol=Decimal("-0.05")), "daily_loss_stop"),
            (base_request, PilotRiskState(cumulative_loss_sol=Decimal("0.125")), "cumulative_loss_freeze"),
            (base_request, PilotRiskState(consecutive_losses=3), "consecutive_losses"),
        )
        for request, state, blocker in cases:
            with self.subTest(blocker=blocker):
                self.assertIn(blocker, self.policy.evaluate_entry(request, state).blockers)

    def test_slippage_and_total_cost_caps_fail_closed(self) -> None:
        self.assertIn("slippage_cap", self.policy.evaluate_entry(PilotRiskRequest("buy", Decimal("0.02"), Decimal("3.01"), Decimal("0.001")), PilotRiskState()).blockers)
        self.assertEqual(self.policy.cost_cap_for(Decimal("0.02")), Decimal("0.0010"))
        self.assertIn("total_cost_cap", self.policy.evaluate_entry(PilotRiskRequest("buy", Decimal("0.02"), Decimal("3"), Decimal("0.0011")), PilotRiskState()).blockers)
        with self.assertRaises(ValueError):
            PilotRiskPolicy.create(Decimal("200"), Decimal("0.4"), NOW, initial_slippage_pct=Decimal("5.01"))

    def test_stop_cannot_auto_restart_increase_or_replenish(self) -> None:
        state = PilotRiskState(stopped=True, restart_requested=True, replenished=True, cap_increase_requested=True)
        decision = self.policy.evaluate_entry(PilotRiskRequest("buy", Decimal("0.01"), Decimal("1"), Decimal("0.0001")), state)
        self.assertFalse(decision.allowed)
        self.assertTrue({"pilot_stopped", "automatic_restart_forbidden", "wallet_replenishment_forbidden", "cap_increase_forbidden"}.issubset(decision.blockers))

    def test_protective_exit_overage_requires_explicit_recovery_decision(self) -> None:
        request = PilotRiskRequest("sell", Decimal("0.4"), Decimal("7"), Decimal("0.02"), protective=True)
        decision = self.policy.evaluate_exit(request, PilotRiskState(stopped=True))
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_explicit_recovery_decision)
        self.assertNotIn("pilot_stopped", decision.blockers)


class PilotRiskStorageTests(unittest.TestCase):
    def test_policy_and_cumulative_ledger_are_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            storage = Storage(str(Path(root) / "pilot.db"))
            policy = PilotRiskPolicy.create(Decimal("200"), Decimal("0.4"), NOW, reference_observation_id="price-1", settings_version="settings-1", operator_intent_id="intent-1")
            self.assertTrue(storage.save_pilot_risk_policy(policy))
            self.assertFalse(storage.save_pilot_risk_policy(policy))
            storage.append_pilot_loss(policy.policy_id, "loss-1", Decimal("0.01"), NOW)
            storage.append_pilot_loss(policy.policy_id, "loss-2", Decimal("0.02"), NOW)
            ledger = storage.pilot_loss_ledger(policy.policy_id)
            self.assertEqual(ledger["cumulative_loss_sol"], "0.03")
            self.assertEqual(len(ledger["entries"]), 2)

    def test_realized_outcomes_survive_restart_and_wins_reset_the_loss_streak(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            database = str(Path(root) / "pilot.db")
            state = BotState(database)
            policy = PilotRiskPolicy.create(
                Decimal("200"), Decimal("0.4"), NOW - timedelta(hours=1),
                reference_observation_id="price-1", settings_version="settings-1", operator_intent_id="intent-1",
            )
            state.storage.save_pilot_risk_policy(policy)
            state.storage.append_pilot_outcome(policy.policy_id, "window-1", "sell-1", Decimal("-0.01"), NOW - timedelta(minutes=3))
            state.storage.append_pilot_outcome(policy.policy_id, "window-1", "sell-2", Decimal("0.005"), NOW - timedelta(minutes=2))
            state.storage.append_pilot_outcome(policy.policy_id, "window-1", "sell-3", Decimal("-0.02"), NOW - timedelta(minutes=1))

            restarted = BotState(database)
            risk = restarted._pilot_risk_state(policy, now=NOW)
            self.assertEqual(risk.session_pnl_sol, Decimal("-0.025"))
            self.assertEqual(risk.daily_pnl_sol, Decimal("-0.025"))
            self.assertEqual(risk.cumulative_loss_sol, Decimal("0.03"))
            self.assertEqual(risk.consecutive_losses, 1)

    def test_authoritatively_reconciled_pilot_sell_is_recorded_once(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            database = str(Path(root) / "pilot.db")
            state = BotState(database)
            policy = PilotRiskPolicy.create(
                Decimal("200"), Decimal("0.4"), NOW - timedelta(minutes=10),
                reference_observation_id="price-1", settings_version="settings-1", operator_intent_id="intent-1",
            )
            state.storage.save_pilot_risk_policy(policy)
            state.storage.save_autonomous_pilot_window({
                "window_id": "window-1", "status": "OPEN", "eligible": True, "opened": True,
                "wallet_public_key": "wallet-1", "policy_id": policy.policy_id,
                "starts_at": (NOW - timedelta(minutes=5)).isoformat(),
                "ends_at": (NOW + timedelta(minutes=5)).isoformat(),
            })
            audit = LiveExecutionAudit(
                id="sell-1", created_at=NOW, updated_at=NOW, action="sell", mint="mint-1",
                amount="100%", status="reconciled", signer_mode="local_hot_wallet",
                wallet_public_key="wallet-1", reconciliation_status="matched", final_status="reconciled",
                pilot_risk_policy_id=policy.policy_id, autonomous_pilot_window_id="window-1",
            )
            position = LiveLedgerPosition(
                id="position-1", created_at=NOW, updated_at=NOW, mint="mint-1", wallet_public_key="wallet-1",
                reconciliation_status="matched", realized_pnl_events=[{
                    "audit_id": "sell-1", "recorded_at": NOW.isoformat(), "provenance": "transaction_meta",
                    "realized_pnl_delta_sol": -0.02,
                }],
            )

            state.storage.stop_autonomous_pilot_window("window-1", state.settings, ["window_expired"], NOW)
            state.storage.save_autonomous_pilot_window({
                "window_id": "window-2", "status": "OPEN", "eligible": True, "opened": True,
                "wallet_public_key": "wallet-1", "policy_id": policy.policy_id,
                "starts_at": NOW.isoformat(), "ends_at": (NOW + timedelta(minutes=10)).isoformat(),
            })

            self.assertTrue(state._record_reconciled_pilot_outcome(audit, position))
            restarted = BotState(database)
            self.assertFalse(restarted._record_reconciled_pilot_outcome(audit, position))
            ledger = restarted.storage.pilot_loss_ledger(policy.policy_id)
            self.assertEqual(ledger["cumulative_loss_sol"], "0.02")
            self.assertEqual(ledger["entries"][0]["window_id"], "window-1")

    def test_fresh_trustworthy_unrealized_loss_counts_toward_stops_and_stale_marks_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = BotState(str(Path(root) / "pilot.db"))
            policy = PilotRiskPolicy.create(
                Decimal("200"), Decimal("0.4"), NOW - timedelta(hours=1),
                reference_observation_id="price-1", settings_version=state.current_settings_version_id,
                operator_intent_id="intent-1",
            )
            state.storage.save_live_ledger_position(LiveLedgerPosition(
                id="open-1", created_at=NOW, updated_at=NOW, mint="mint-1", wallet_public_key="wallet-1",
                status="open", token_balance=100, unrealized_pnl_sol=-0.051,
                reconciliation_status="matched", mark_price_confidence=0.9, mark_price_at=NOW,
                balance_verified_at=NOW, unrealized_pnl_confidence="estimated",
            ))

            risk = state._pilot_risk_state(policy, "wallet-1", now=NOW)
            self.assertEqual(risk.session_pnl_sol, Decimal("-0.051"))
            self.assertFalse(risk.unrealized_pnl_unavailable)
            decision = policy.evaluate_entry(
                PilotRiskRequest("buy", Decimal("0.01"), Decimal("1"), Decimal("0.0001")),
                risk,
            )
            self.assertIn("session_loss_stop", decision.blockers)

            position = state.storage.load_live_ledger_positions(1)[0]
            position.mark_price_at = NOW - timedelta(minutes=10)
            state.storage.save_live_ledger_position(position)
            stale = state._pilot_risk_state(policy, "wallet-1", now=NOW)
            self.assertTrue(stale.unrealized_pnl_unavailable)
            self.assertIn(
                "unrealized_pnl_unavailable",
                policy.evaluate_entry(PilotRiskRequest("buy", Decimal("0.01"), Decimal("1"), Decimal("0.0001")), stale).blockers,
            )


if __name__ == "__main__":
    unittest.main()
