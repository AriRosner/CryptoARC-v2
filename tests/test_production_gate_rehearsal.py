from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.core.production_rehearsal import ProductionGateRehearsal


def passing_evidence() -> dict[str, object]:
    evidence = {
        "fixture_only": False,
        "physical_window_authorized": True,
        "authorization_id": "auth-production-rehearsal-1",
        "authorization_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        "password_restart": "pass",
        "totp_restart": "pass",
        "bearer_only": "pass",
        "wallet_signer_match": "pass",
        "signer_rotation_invalidation": "pass",
        "signer_loss_disarm": "pass",
        "source_loss_entry_block": "pass",
        "protective_exit_prepared": "pass",
        "kill_switch": "pass",
        "fresh_backup": "pass",
        "restore_preview": "pass",
        "restore_smoke": "pass",
        "schema_match": "pass",
        "restart_recovery": "pass",
        "unresolved_audits": 0,
        "ledger_debt": 0,
        "tailnet_only": True,
        "public_exposure": False,
        "notification_disclosure": "pass",
        "image_size_risk_accepted": True,
        "image_size_risk_acceptance_expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    }
    evidence["evidence_ids"] = {
        key: f"evidence_{key}"
        for key in (
            "password_restart", "totp_restart", "bearer_only", "wallet_signer_match",
            "signer_rotation_invalidation", "signer_loss_disarm", "source_loss_entry_block",
            "protective_exit_prepared", "kill_switch", "fresh_backup", "restore_preview",
            "restore_smoke", "schema_match", "restart_recovery", "notification_disclosure",
            "tailnet_only", "public_exposure", "image_size_risk_accepted",
        )
    }
    return evidence


class ProductionGateRehearsalTests(unittest.TestCase):
    def test_fixture_rehearsal_cannot_qualify_production_gate(self) -> None:
        evidence = passing_evidence()
        evidence["fixture_only"] = True
        report = ProductionGateRehearsal.evaluate(evidence)
        self.assertFalse(report.ready)
        self.assertIn("physical_rehearsal_required", report.blockers)
        self.assertFalse(report.authority_changed)

    def test_complete_fresh_physical_evidence_can_qualify(self) -> None:
        report = ProductionGateRehearsal.evaluate(passing_evidence())
        self.assertTrue(report.ready)
        self.assertEqual(report.blockers, ())

    def test_every_production_gate_fails_closed(self) -> None:
        base = passing_evidence()
        failures = {
            "password_restart": "password_restart",
            "totp_restart": "totp_restart",
            "bearer_only": "bearer_only",
            "wallet_signer_match": "wallet_signer_match",
            "signer_rotation_invalidation": "signer_rotation_invalidation",
            "signer_loss_disarm": "signer_loss_disarm",
            "source_loss_entry_block": "source_loss_entry_block",
            "protective_exit_prepared": "protective_exit_prepared",
            "kill_switch": "kill_switch",
            "fresh_backup": "fresh_backup",
            "restore_preview": "restore_preview",
            "restore_smoke": "restore_smoke",
            "schema_match": "schema_match",
            "restart_recovery": "restart_recovery",
            "notification_disclosure": "notification_disclosure",
        }
        for key, blocker in failures.items():
            with self.subTest(key=key):
                evidence = dict(base)
                evidence[key] = "fail"
                self.assertIn(blocker, ProductionGateRehearsal.evaluate(evidence).blockers)

    def test_debt_exposure_and_identity_mismatches_block(self) -> None:
        evidence = passing_evidence()
        evidence.update({"unresolved_audits": 1, "ledger_debt": 2, "tailnet_only": False, "public_exposure": True})
        report = ProductionGateRehearsal.evaluate(evidence)
        self.assertEqual(
            set(report.blockers),
            {"unresolved_audit_debt", "ledger_debt", "tailnet_only", "public_exposure"},
        )

    def test_authorization_and_image_size_acceptance_must_be_fresh(self) -> None:
        evidence = passing_evidence()
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        evidence["authorization_expires_at"] = expired
        evidence["image_size_risk_acceptance_expires_at"] = expired
        report = ProductionGateRehearsal.evaluate(evidence)
        self.assertIn("physical_authorization_expired", report.blockers)
        self.assertIn("image_size_risk_acceptance_expired", report.blockers)

    def test_actual_pass_without_attributable_evidence_ids_fails_closed(self) -> None:
        evidence = passing_evidence()
        evidence["evidence_ids"] = {}
        report = ProductionGateRehearsal.evaluate(evidence)
        self.assertFalse(report.ready)
        self.assertIn("wallet_signer_match_evidence_id", report.blockers)

    def test_report_redacts_unexpected_secret_fields(self) -> None:
        evidence = passing_evidence()
        evidence.update({"password": "do-not-export", "totp_secret": "do-not-export", "private_key": "do-not-export"})
        payload = ProductionGateRehearsal.evaluate(evidence).to_dict()
        serialized = str(payload)
        self.assertNotIn("do-not-export", serialized)
        self.assertNotIn("password", payload["evidence"])


if __name__ == "__main__":
    unittest.main()
