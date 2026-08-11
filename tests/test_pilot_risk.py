from __future__ import annotations

import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.core.pilot_risk import PilotRiskPolicy, PilotRiskRequest, PilotRiskState
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


if __name__ == "__main__":
    unittest.main()
