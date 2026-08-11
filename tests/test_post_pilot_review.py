from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.post_pilot_review import PilotReview
from app.core.storage import Storage


WINDOW = {
    "window_id": "pilot-window-closed-1",
    "status": "CLOSED",
    "opened": True,
    "wallet_public_key": "wallet-review-1",
    "policy_id": "pilot-policy-1",
    "manual_proof_id": "manual-proof-1",
    "ended_with_kill_switch": True,
    "backend_disarmed": True,
    "reconciled": True,
}
AUDITS = [
    {
        "audit_id": "audit-buy-1", "transaction_signature": "sig-buy-1", "action": "buy",
        "status": "reconciled", "explained": True, "fees_complete": True, "pnl_complete": True,
        "cap_bypass": False, "reconciliation_complete": True,
    },
    {
        "audit_id": "audit-sell-1", "transaction_signature": "sig-sell-1", "action": "sell",
        "status": "reconciled", "explained": True, "fees_complete": True, "pnl_complete": True,
        "cap_bypass": False, "reconciliation_complete": True,
    },
]
LEDGER = {
    "wallet_public_key": "wallet-review-1",
    "balances_explained": True,
    "fees_complete": True,
    "pnl_complete": True,
    "open_positions": 0,
    "unresolved_audits": 0,
    "ledger_debt": 0,
    "unknown_transactions": 0,
    "manual_database_repair": False,
    "cumulative_loss_usd": "7.50",
}
GRADES = [{"trade_id": "audit-buy-1", "status": "graded"}, {"trade_id": "audit-sell-1", "status": "graded"}]
PERFORMANCE = {
    "drawdown_complete": True,
    "fills_complete": True,
    "latency_complete": True,
    "exits_complete": True,
    "caps_complete": True,
    "max_drawdown_usd": "3.20",
}


class PostPilotReviewTests(unittest.TestCase):
    def test_complete_explained_closed_window_is_clear(self) -> None:
        review = PilotReview.close(WINDOW, AUDITS, LEDGER, GRADES, PERFORMANCE)
        self.assertTrue(review.clear)
        self.assertFalse(review.next_pilot_blocked)
        self.assertFalse(review.authority_changed)
        self.assertFalse(review.automatic_scaling_applied)

    def test_unexplained_transaction_forces_stop_or_revise_and_blocks_next_pilot(self) -> None:
        audit = {**AUDITS[0], "explained": False}
        review = PilotReview.close(WINDOW, [audit, AUDITS[1]], LEDGER, GRADES, PERFORMANCE)
        self.assertFalse(review.clear)
        self.assertIn("unexplained_transaction", review.blockers)
        self.assertTrue(review.next_pilot_blocked)
        self.assertEqual(set(review.allowed_decisions), {"revise", "stop"})

    def test_cap_bypass_unresolved_position_and_debt_block(self) -> None:
        audit = {**AUDITS[0], "cap_bypass": True}
        ledger = {**LEDGER, "open_positions": 1, "unresolved_audits": 1, "ledger_debt": 1}
        review = PilotReview.close(WINDOW, [audit, AUDITS[1]], ledger, GRADES, PERFORMANCE)
        self.assertTrue({"cap_bypass", "unresolved_position", "audit_debt", "ledger_debt"}.issubset(review.blockers))

    def test_twenty_five_dollar_cumulative_freeze_blocks_next_pilot(self) -> None:
        review = PilotReview.close(WINDOW, AUDITS, {**LEDGER, "cumulative_loss_usd": "25.00"}, GRADES, PERFORMANCE)
        self.assertIn("cumulative_loss_freeze", review.blockers)
        self.assertTrue(review.next_pilot_blocked)

    def test_every_transaction_balance_fee_pnl_and_metric_must_be_explained(self) -> None:
        cases = (
            (AUDITS, {**LEDGER, "balances_explained": False}, PERFORMANCE, "balance_unexplained"),
            ([{**AUDITS[0], "fees_complete": False}, AUDITS[1]], LEDGER, PERFORMANCE, "fees_incomplete"),
            (AUDITS, {**LEDGER, "pnl_complete": False}, PERFORMANCE, "pnl_incomplete"),
            (AUDITS, LEDGER, {**PERFORMANCE, "latency_complete": False}, "latency_incomplete"),
            (AUDITS, LEDGER, {**PERFORMANCE, "exits_complete": False}, "exits_incomplete"),
            (AUDITS, LEDGER, {**PERFORMANCE, "caps_complete": False}, "caps_incomplete"),
            (AUDITS, LEDGER, {**PERFORMANCE, "fills_complete": False}, "fills_incomplete"),
            (AUDITS, LEDGER, {**PERFORMANCE, "drawdown_complete": False}, "drawdown_incomplete"),
        )
        for audits, ledger, performance, blocker in cases:
            with self.subTest(blocker=blocker):
                self.assertIn(blocker, PilotReview.close(WINDOW, audits, ledger, GRADES, performance).blockers)

    def test_window_must_be_closed_killed_disarmed_and_reconciled(self) -> None:
        for field, value, blocker in (
            ("status", "OPEN", "window_not_closed"),
            ("ended_with_kill_switch", False, "kill_switch_incomplete"),
            ("backend_disarmed", False, "backend_disarm_incomplete"),
            ("reconciled", False, "window_reconciliation_incomplete"),
        ):
            with self.subTest(field=field):
                self.assertIn(blocker, PilotReview.close({**WINDOW, field: value}, AUDITS, LEDGER, GRADES, PERFORMANCE).blockers)


class PilotDecisionStorageTests(unittest.TestCase):
    def test_operator_decision_is_append_only_and_scale_has_no_effect(self) -> None:
        review = PilotReview.close(WINDOW, AUDITS, LEDGER, GRADES, PERFORMANCE).to_dict()
        with TemporaryDirectory() as temp_dir:
            storage = Storage(str(Path(temp_dir) / "review.db"))
            saved = storage.save_post_pilot_review(review)
            decision = PilotReview.record_operator_decision(saved["review_id"], "scale", "Evidence reviewed", "scale-auth-1")
            first = storage.save_pilot_operator_decision(decision.to_dict())
            same = storage.save_pilot_operator_decision(decision.to_dict())
            self.assertEqual(first, same)
            self.assertFalse(first["authority_changed"])
            self.assertFalse(first["scaling_applied"])
            with self.assertRaises(ValueError):
                other = PilotReview.record_operator_decision(saved["review_id"], "hold", "Changed mind", "hold-auth-2")
                storage.save_pilot_operator_decision(other.to_dict())

    def test_blocked_review_rejects_scale_or_hold_decision(self) -> None:
        review = PilotReview.close(WINDOW, [{**AUDITS[0], "cap_bypass": True}, AUDITS[1]], LEDGER, GRADES, PERFORMANCE)
        with self.assertRaises(ValueError):
            PilotReview.record_operator_decision(review.review_id, "scale", "Unsafe", "auth-1", allowed_decisions=review.allowed_decisions)


if __name__ == "__main__":
    unittest.main()
