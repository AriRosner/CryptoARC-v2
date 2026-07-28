from __future__ import annotations

import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.core.models import LiveExecutionAudit, MobileActionReceipt, utc_now
from app.core.storage import Storage
from app.mobile.contracts import MobileActionStatus
from app.mobile.service import MobileCommandCenterService


class GuardedStorage:
    def __init__(self, path: str) -> None:
        self.receipts = Storage(path)
        self.intent = SimpleNamespace(
            id="intent_mobile_guarded",
            action="buy",
            mint="MintMobileGuarded",
            amount="0.05",
            denominated_in_sol=True,
            signer_mode="local_signer_daemon",
            wallet_public_key="WalletMobileGuarded",
            status="simulated",
            reason="Prepared by desktop review",
            source="manual",
            symbol="ARC",
            score=71,
            priority=71.0,
            quote_id="quote_mobile_guarded",
            audit_id="audit_mobile_guarded",
            expires_at=utc_now() + timedelta(minutes=2),
            stale=False,
            warnings=[],
            autonomy_blocked=False,
            autonomy_blockers=[],
            operator_recommendation="Review and approve",
            priority_reason="Focused test",
            generated_from_position=False,
            version=3,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.audit = LiveExecutionAudit(
            id="audit_mobile_guarded",
            created_at=utc_now(),
            updated_at=utc_now(),
            action="buy",
            mint=self.intent.mint,
            amount=self.intent.amount,
            status="simulated",
            signer_mode=self.intent.signer_mode,
            wallet_public_key=self.intent.wallet_public_key,
            quote={
                "id": self.intent.quote_id,
                "status": "ready",
                "amount": self.intent.amount,
                "slippage_pct": 1.0,
                "unsigned_transaction_base64": "test-only-unsigned-transaction",
                "expires_at": (utc_now() + timedelta(minutes=2)).isoformat(),
                "live_env_enabled_at_quote": True,
                "shadow_only": False,
            },
            simulation={"status": "ok", "ok": True, "result": {"units": 123}},
            request={"id": self.intent.id},
            preflight_checks=[
                {
                    "id": "test",
                    "label": "Focused test preflight",
                    "status": "pass",
                    "reason": "prepared",
                }
            ],
            final_status="simulated",
            intent_id=self.intent.id,
        )
        self.position = SimpleNamespace(
            id="live-position-guarded",
            mint=self.intent.mint,
            wallet_public_key=self.intent.wallet_public_key,
            status="open",
            token_balance=100.0,
            stop_pct=None,
            target_pct=None,
            version=4,
            updated_at=utc_now(),
        )

    def __getattr__(self, name: str):
        return getattr(self.receipts, name)

    def load_live_intent(self, intent_id: str):
        return self.intent if intent_id == self.intent.id else None

    def load_live_intents(self, limit: int = 100):
        del limit
        return [self.intent]

    def save_live_intent(self, intent) -> None:
        self.intent = intent

    def load_live_execution_audit(self, audit_id: str):
        return self.audit if audit_id == self.audit.id else None

    def save_live_execution_audit(self, audit: LiveExecutionAudit) -> None:
        self.audit = audit

    def load_live_ledger_position(self, position_id: str):
        return self.position if position_id == self.position.id else None

    def save_live_ledger_position(self, position) -> None:
        self.position = position


class GuardedState:
    def __init__(self, storage: GuardedStorage) -> None:
        self.storage = storage
        self.settings = SimpleNamespace(
            live_active_backend_armed=True,
            live_active_wallet_public_key=storage.intent.wallet_public_key,
            live_signer_mode=storage.intent.signer_mode,
            kill_switch_enabled=False,
            live_max_trade_sol=0.10,
            live_max_slippage_pct=2.0,
            stop_loss_pct=30.0,
            take_profit_pct=50.0,
        )
        self.execution_blockers: list[str] = []
        self.signer = {
            "connected": True,
            "healthy": True,
            "can_sign": True,
            "can_unattended_sign": True,
            "ready_to_submit": True,
        }
        self.signer_submit_calls = 0
        self.position_adjust_calls = 0
        self.submit_error: Exception | None = None

    def signer_status(self, mode: str, wallet_public_key: str):
        del mode, wallet_public_key
        return dict(self.signer)

    def mobile_live_execution_blockers(self, intent):
        del intent
        return list(self.execution_blockers)

    def live_submit(self, audit_id: str, signature: str):
        self.signer_submit_calls += 1
        self.assert_submit_is_keyless(signature)
        if self.submit_error is not None:
            raise self.submit_error
        audit = self.storage.load_live_execution_audit(audit_id)
        audit.status = "submitted"
        audit.final_status = "submitted"
        audit.updated_at = utc_now()
        self.storage.save_live_execution_audit(audit)
        return audit.to_dict()

    @staticmethod
    def assert_submit_is_keyless(signature: str) -> None:
        if signature:
            raise AssertionError("mobile approval must never supply signed transaction material")

    def recover_live_audit(self, audit_id: str):
        audit = self.storage.load_live_execution_audit(audit_id)
        return audit.to_dict()

    def mobile_adjust_position_exit(
        self,
        *,
        position_id: str,
        expected_version: int,
        stop_pct: float,
        target_pct: float,
    ):
        position = self.storage.load_live_ledger_position(position_id)
        if position is None:
            raise LookupError("Mobile live position not found")
        if position.version != expected_version:
            raise ValueError("Position version conflict")
        self.position_adjust_calls += 1
        position.stop_pct = stop_pct
        position.target_pct = target_pct
        position.version += 1
        position.updated_at = utc_now()
        self.storage.save_live_ledger_position(position)
        return {"id": position.id, "version": position.version}


class MobileGuardedActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = GuardedStorage(str(Path(self.directory.name) / "test.db"))
        self.state = GuardedState(self.storage)
        self.config = SimpleNamespace(live_trading_enabled=True)
        self.service = MobileCommandCenterService(
            state_provider=lambda: self.state,
            config_provider=lambda: self.config,
            auth_provider=lambda: SimpleNamespace(enabled=True, totp_enabled=True),
            require_dashboard_auth=lambda: None,
            broadcast_snapshot=self._noop,
            broadcast_mobile_cockpit=self._noop,
            stop_runtime_tasks=self._noop_stop,
        )
        self.execute_device = {
            "id": "device_execute",
            "scopes": ["mobile:trade:review", "mobile:trade:execute"],
        }
        self.valid_draft = {
            "amount": "0.05",
            "slippage_pct": "1.0",
            "stop_pct": "20",
            "target_pct": "40",
        }

    async def _noop(self) -> None:
        return None

    async def _noop_stop(self) -> dict[str, object]:
        return {}

    def require_guarded_service(self) -> None:
        self.assertTrue(
            hasattr(self.service, "approve_trade"),
            "guarded mobile approval service is not implemented",
        )

    def approve(
        self,
        *,
        key: str = "approval-key",
        expected_version: int = 3,
        draft: dict[str, str | None] | None = None,
        escalation_acknowledged: bool = False,
    ) -> dict[str, object]:
        self.require_guarded_service()
        return self.service.approve_trade(
            device=self.execute_device,
            intent_id=self.storage.intent.id,
            expected_version=expected_version,
            draft=draft or self.valid_draft,
            escalation_acknowledged=escalation_acknowledged,
            idempotency_key=key,
        )

    def test_duplicate_approval_returns_same_receipt_without_second_execution(self) -> None:
        first = self.approve(key="same-key")
        second = self.approve(key="same-key")

        self.assertEqual(first["action_id"], "same-key")
        self.assertEqual(first["action_id"], second["action_id"])
        self.assertEqual(self.state.signer_submit_calls, 1)

    def test_stale_version_conflict_fails_before_submission(self) -> None:
        with self.assertRaisesRegex(ValueError, "version"):
            self.approve(expected_version=2)
        self.assertEqual(self.state.signer_submit_calls, 0)

    def test_action_id_is_validated_and_receipt_lookup_is_device_scoped(self) -> None:
        with self.assertRaisesRegex(ValueError, "Idempotency key"):
            self.approve(key="bad key")
        self.assertEqual(self.state.signer_submit_calls, 0)

        receipt = self.approve(key="owner-key")
        other_device = {**self.execute_device, "id": "device-other"}
        with self.assertRaisesRegex(LookupError, "not found"):
            self.service.action(
                device=other_device,
                action_id=str(receipt["action_id"]),
            )

    def test_out_of_bounds_size_slippage_stop_and_target_fail_closed(self) -> None:
        cases = {
            "amount": {**self.valid_draft, "amount": "0.11"},
            "slippage": {**self.valid_draft, "slippage_pct": "2.1"},
            "stop": {**self.valid_draft, "stop_pct": "101"},
            "target": {**self.valid_draft, "target_pct": "101"},
        }
        for name, draft in cases.items():
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "bound|match|limit"):
                self.approve(key=f"bounds-{name}", draft=draft)
        self.assertEqual(self.state.signer_submit_calls, 0)

    def test_position_exit_adjustment_is_bounded_versioned_and_idempotent(self) -> None:
        first = self.service.adjust_position_exit(
            device=self.execute_device,
            position_id=self.storage.position.id,
            expected_version=4,
            stop_pct="25",
            target_pct="45",
            escalation_acknowledged=False,
            idempotency_key="adjust-key",
        )
        second = self.service.adjust_position_exit(
            device=self.execute_device,
            position_id=self.storage.position.id,
            expected_version=4,
            stop_pct="25",
            target_pct="45",
            escalation_acknowledged=False,
            idempotency_key="adjust-key",
        )

        self.assertEqual(first["status"], MobileActionStatus.CONFIRMED.value)
        self.assertEqual(first["action_id"], "adjust-key")
        self.assertEqual(first, second)
        self.assertEqual(self.state.position_adjust_calls, 1)
        self.assertEqual(self.storage.position.version, 5)

        with self.assertRaisesRegex(ValueError, "version"):
            self.service.adjust_position_exit(
                device=self.execute_device,
                position_id=self.storage.position.id,
                expected_version=4,
                stop_pct="20",
                target_pct="40",
                escalation_acknowledged=False,
                idempotency_key="stale-adjust",
            )
        self.assertIsNone(
            self.storage.load_mobile_action_receipt("stale-adjust")
        )

    def test_missing_simulation_and_stale_quote_fail_closed(self) -> None:
        self.storage.audit.simulation = {}
        with self.assertRaisesRegex(ValueError, "simulation"):
            self.approve(key="missing-simulation")

        self.storage.audit.simulation = {"status": "ok", "ok": True}
        self.storage.audit.quote["expires_at"] = (utc_now() - timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "stale|expired"):
            self.approve(key="stale-quote")
        self.assertEqual(self.state.signer_submit_calls, 0)

    def test_readiness_signer_backend_and_kill_switch_fail_closed(self) -> None:
        cases = ("readiness", "signer", "backend", "kill_switch")
        for name in cases:
            with self.subTest(name=name):
                self.state.execution_blockers = []
                self.state.signer["ready_to_submit"] = True
                self.state.settings.live_active_backend_armed = True
                self.state.settings.kill_switch_enabled = False
                if name == "readiness":
                    self.state.execution_blockers = ["readiness gate blocked"]
                elif name == "signer":
                    self.state.signer["ready_to_submit"] = False
                elif name == "backend":
                    self.state.settings.live_active_backend_armed = False
                else:
                    self.state.settings.kill_switch_enabled = True
                with self.assertRaisesRegex(ValueError, "readiness|signer|backend|kill switch"):
                    self.approve(key=f"guard-{name}")
        self.assertEqual(self.state.signer_submit_calls, 0)

    def test_high_risk_validation_lists_reasons_and_requires_acknowledgement(self) -> None:
        self.require_guarded_service()
        high_risk = {
            **self.valid_draft,
            "amount": "0.05",
            "slippage_pct": "1.0",
            "stop_pct": "80",
            "target_pct": "95",
        }
        validation = self.service.validate_trade(
            device=self.execute_device,
            intent_id=self.storage.intent.id,
            expected_version=3,
            draft=high_risk,
            escalation_acknowledged=False,
        )

        self.assertTrue(validation["requires_escalation"])
        self.assertGreaterEqual(len(validation["escalation_reasons"]), 2)
        with self.assertRaisesRegex(ValueError, "escalation"):
            self.approve(key="risk-no-ack", draft=high_risk)
        approved = self.approve(
            key="risk-ack",
            draft=high_risk,
            escalation_acknowledged=True,
        )
        self.assertEqual(approved["status"], MobileActionStatus.VERIFYING.value)

    def test_ambiguous_result_returns_verifying_receipt_without_retrying(self) -> None:
        self.state.submit_error = TimeoutError("signer response timed out")
        action_id = "ambiguous-key"
        first = self.approve(key=action_id)

        self.assertEqual(first["status"], MobileActionStatus.VERIFYING.value)
        self.assertEqual(first["operator_message"], "Verifying outcome")
        self.assertEqual(first["action_id"], action_id)
        self.assertEqual(self.state.signer_submit_calls, 1)

        self.storage.audit.status = "needs_review"
        self.storage.audit.final_status = "needs_review"
        reconciled = self.service.action(
            device=self.execute_device,
            action_id=action_id,
        )

        self.assertEqual(reconciled["action_id"], action_id)
        self.assertEqual(
            reconciled["status"],
            MobileActionStatus.REVIEW_REQUIRED.value,
        )
        self.assertEqual(self.state.signer_submit_calls, 1)

    def test_review_required_reconciliation_updates_existing_receipt(self) -> None:
        receipt = self.approve(key="review-key")
        self.storage.audit.status = "needs_review"
        self.storage.audit.final_status = "needs_review"
        self.storage.audit.recommended_action = "Review the signature manually."
        reconciled = self.service.action(
            device=self.execute_device,
            action_id=str(receipt["action_id"]),
        )

        self.assertEqual(reconciled["action_id"], receipt["action_id"])
        self.assertEqual(
            reconciled["status"],
            MobileActionStatus.REVIEW_REQUIRED.value,
        )
        self.assertIn("Review", reconciled["operator_message"])

    def test_receipt_payload_never_persists_request_secrets_or_transaction_material(self) -> None:
        receipt = self.approve(key="secret-surface")
        persisted = self.storage.load_mobile_action_receipt(str(receipt["action_id"]))
        encoded = str(persisted.to_dict()).lower()
        for forbidden in (
            "private_key",
            "seed",
            "signed_transaction",
            "raw_transaction",
            "unsigned_transaction_base64",
            "backend_arm",
            "readiness_override",
        ):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
