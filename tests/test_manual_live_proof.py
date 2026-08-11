from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.core.manual_live_proof import ManualLiveProof


NOW = datetime(2026, 8, 11, 16, 0, tzinfo=timezone.utc)
WALLET = "wallet-actual-1"
SIGNER = {
    "wallet_public_key": WALLET,
    "signer_mode": "local_signer_daemon",
    "signer_identity_id": "signer-identity-1",
}
AUTH = {
    "authorization_id": "manual-live-auth-1",
    "scope": "manual-live-proof",
    "wallet_public_key": WALLET,
    "signer_mode": "local_signer_daemon",
    "signer_identity_id": "signer-identity-1",
    "issued_at": (NOW - timedelta(minutes=5)).isoformat(),
    "expires_at": (NOW + timedelta(minutes=10)).isoformat(),
}
AUDITS = [
    {
        "audit_id": "buy-audit-1", "action": "buy", "wallet_public_key": WALLET,
        "signer_mode": "local_signer_daemon", "signer_identity_id": "signer-identity-1",
        "transaction_signature": "buy-signature-1", "status": "confirmed", "amount_usd": "3.00",
        "fixture_only": False, "error": "", "reconciled": True, "fees_complete": True,
    },
    {
        "audit_id": "sell-audit-1", "action": "sell", "wallet_public_key": WALLET,
        "signer_mode": "local_signer_daemon", "signer_identity_id": "signer-identity-1",
        "transaction_signature": "sell-signature-1", "status": "confirmed", "amount_usd": "3.00",
        "fixture_only": False, "error": "", "reconciled": True, "fees_complete": True,
        "protective_exit": False,
    },
]
LEDGER = {
    "wallet_public_key": WALLET,
    "round_trip_complete": True,
    "open_positions": 0,
    "fees_complete": True,
    "pnl_complete": True,
    "realized_pnl_sol": "-0.001",
    "unknown_transactions": 0,
    "manual_database_repair": False,
    "review_debt": 0,
}


class ManualLiveProofTests(unittest.TestCase):
    def test_complete_actual_round_trip_qualifies(self) -> None:
        report = ManualLiveProof.qualify(AUDITS, LEDGER, SIGNER, AUTH, now=NOW)
        self.assertTrue(report.qualified)
        self.assertEqual(report.blockers, ())
        self.assertFalse(report.authority_changed)

    def test_fixture_evidence_is_deferred(self) -> None:
        audits = [{**item, "fixture_only": True} for item in AUDITS]
        report = ManualLiveProof.qualify(audits, LEDGER, SIGNER, AUTH, now=NOW)
        self.assertFalse(report.qualified)
        self.assertIn("actual_live_evidence_required", report.blockers)
        self.assertEqual(report.status, "DEFERRED")

    def test_exact_wallet_and_signer_identity_are_required(self) -> None:
        for field, value, blocker in (
            ("wallet_public_key", "wrong-wallet", "wallet_identity_mismatch"),
            ("signer_mode", "browser_wallet", "signer_mode_mismatch"),
            ("signer_identity_id", "wrong-signer", "signer_identity_mismatch"),
        ):
            with self.subTest(field=field):
                signer = {**SIGNER, field: value}
                self.assertIn(blocker, ManualLiveProof.qualify(AUDITS, LEDGER, signer, AUTH, now=NOW).blockers)

    def test_requires_fresh_scoped_authorization(self) -> None:
        for patch, blocker in (
            ({"scope": "other"}, "authorization_scope"),
            ({"expires_at": (NOW - timedelta(seconds=1)).isoformat()}, "authorization_expired"),
            ({"authorization_id": ""}, "authorization_id"),
        ):
            with self.subTest(blocker=blocker):
                self.assertIn(blocker, ManualLiveProof.qualify(AUDITS, LEDGER, SIGNER, {**AUTH, **patch}, now=NOW).blockers)

    def test_requires_one_confirmed_buy_and_actual_sell_within_two_to_five_dollars(self) -> None:
        cases = (
            (AUDITS[:1], "sell_audit"),
            ([{**AUDITS[0], "amount_usd": "1.99"}, AUDITS[1]], "buy_notional_bounds"),
            ([AUDITS[0], {**AUDITS[1], "status": "unknown"}], "unconfirmed_transaction"),
            ([AUDITS[0], {**AUDITS[1], "transaction_signature": ""}], "confirmed_signature"),
        )
        for audits, blocker in cases:
            with self.subTest(blocker=blocker):
                self.assertIn(blocker, ManualLiveProof.qualify(audits, LEDGER, SIGNER, AUTH, now=NOW).blockers)

    def test_manual_proof_is_invalidated_by_manual_database_repair(self) -> None:
        report = ManualLiveProof.qualify(AUDITS, {**LEDGER, "manual_database_repair": True}, SIGNER, AUTH, now=NOW)
        self.assertFalse(report.qualified)
        self.assertIn("manual_database_repair", report.blockers)

    def test_errors_reconciliation_accounting_and_review_debt_fail_closed(self) -> None:
        cases = (
            ([{**AUDITS[0], "error": "rpc failure"}, AUDITS[1]], LEDGER, "audit_error"),
            ([{**AUDITS[0], "reconciled": False}, AUDITS[1]], LEDGER, "reconciliation_incomplete"),
            (AUDITS, {**LEDGER, "fees_complete": False}, "fees_incomplete"),
            (AUDITS, {**LEDGER, "pnl_complete": False}, "pnl_incomplete"),
            (AUDITS, {**LEDGER, "unknown_transactions": 1}, "unknown_transaction"),
            (AUDITS, {**LEDGER, "review_debt": 1}, "review_debt"),
            (AUDITS, {**LEDGER, "open_positions": 1}, "round_trip_incomplete"),
        )
        for audits, ledger, blocker in cases:
            with self.subTest(blocker=blocker):
                self.assertIn(blocker, ManualLiveProof.qualify(audits, ledger, SIGNER, AUTH, now=NOW).blockers)

    def test_export_contains_references_not_secret_fields(self) -> None:
        report = ManualLiveProof.qualify(AUDITS, {**LEDGER, "private_key": "secret"}, {**SIGNER, "token": "secret"}, AUTH, now=NOW)
        payload = report.to_dict()
        self.assertEqual(payload["audit_ids"], ["buy-audit-1", "sell-audit-1"])
        self.assertNotIn("secret", str(payload))


if __name__ == "__main__":
    unittest.main()
