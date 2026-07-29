from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.core.models import (
    LiveExecutionAudit,
    LiveExecutionIntent,
    LiveLedgerPosition,
    MobileActionReceipt,
    utc_now,
)
from app.core.storage import Storage
from app.mobile.contracts import MobileActionStatus
from app.mobile.service import MobileCommandCenterService


class GuardedStorage:
    def __init__(self, path: str) -> None:
        self.receipts = Storage(path)
        self._intent_id = "intent_mobile_guarded"
        self._audit_id = "audit_mobile_guarded"
        self._position_id = "live-position-guarded"
        intent = LiveExecutionIntent(
            id="intent_mobile_guarded",
            created_at=utc_now(),
            updated_at=utc_now(),
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
        )
        audit = LiveExecutionAudit(
            id="audit_mobile_guarded",
            created_at=utc_now(),
            updated_at=utc_now(),
            action="buy",
            mint=intent.mint,
            amount=intent.amount,
            status="simulated",
            signer_mode=intent.signer_mode,
            wallet_public_key=intent.wallet_public_key,
            quote={
                "id": intent.quote_id,
                "status": "ready",
                "amount": intent.amount,
                "slippage_pct": 1.0,
                "unsigned_transaction_base64": "test-only-unsigned-transaction",
                "expires_at": (utc_now() + timedelta(minutes=2)).isoformat(),
                "live_env_enabled_at_quote": True,
                "shadow_only": False,
            },
            simulation={"status": "ok", "ok": True, "result": {"units": 123}},
            request={"id": intent.id, "denominated_in_sol": True},
            preflight_checks=[
                {
                    "id": check_id,
                    "label": check_id.replace("_", " ").title(),
                    "status": "pass",
                    "reason": "prepared",
                }
                for check_id in (
                    "environment",
                    "mint",
                    "wallet",
                    "signer",
                    "amount",
                    "slippage",
                    "priority_fee",
                    "pool",
                    "caps",
                    "blockers",
                )
            ],
            final_status="simulated",
            intent_id=intent.id,
        )
        position = LiveLedgerPosition(
            id="live-position-guarded",
            created_at=utc_now(),
            updated_at=utc_now(),
            mint=intent.mint,
            wallet_public_key=intent.wallet_public_key,
            status="open",
            token_balance=100.0,
            stop_pct=None,
            target_pct=None,
            version=4,
        )
        self.receipts.save_live_intent(intent)
        self.receipts.save_live_execution_audit(audit)
        self.receipts.save_live_ledger_position(position)

    def __getattr__(self, name: str):
        return getattr(self.receipts, name)

    @property
    def intent(self) -> LiveExecutionIntent:
        intent = self.receipts.load_live_intent(self._intent_id)
        assert intent is not None
        return intent

    @intent.setter
    def intent(self, intent: LiveExecutionIntent) -> None:
        self.receipts.save_live_intent(intent)

    @property
    def audit(self) -> LiveExecutionAudit:
        audit = self.receipts.load_live_execution_audit(self._audit_id)
        assert audit is not None
        return audit

    @audit.setter
    def audit(self, audit: LiveExecutionAudit) -> None:
        self.receipts.save_live_execution_audit(audit)

    @property
    def position(self) -> LiveLedgerPosition:
        position = self.receipts.load_live_ledger_position(self._position_id)
        assert position is not None
        return position

    @position.setter
    def position(self, position: LiveLedgerPosition) -> None:
        self.receipts.save_live_ledger_position(position)


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

    def live_submit(
        self,
        audit_id: str,
        signature: str,
        *,
        guarded_action_id: str = "",
    ):
        self.assert_submit_is_keyless(signature)
        audit = self.storage.begin_mobile_execution_dispatch(
            audit_id=audit_id,
            action_id=guarded_action_id,
        )
        if audit is None:
            current = self.storage.load_live_execution_audit(audit_id)
            assert current is not None
            return current.to_dict()
        self.signer_submit_calls += 1
        if self.submit_error is not None:
            raise self.submit_error
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
        mobile_action_id: str = "",
    ):
        position = self.storage.load_live_ledger_position(position_id)
        if position is None:
            raise LookupError("Mobile live position not found")
        if position.version != expected_version:
            raise ValueError("Position version conflict")
        self.position_adjust_calls += 1
        position.stop_pct = stop_pct
        position.target_pct = target_pct
        position.last_mobile_action_id = mobile_action_id
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

    def create_service(self) -> MobileCommandCenterService:
        return MobileCommandCenterService(
            state_provider=lambda: self.state,
            config_provider=lambda: self.config,
            auth_provider=lambda: SimpleNamespace(enabled=True, totp_enabled=True),
            require_dashboard_auth=lambda: None,
            broadcast_snapshot=self._noop,
            broadcast_mobile_cockpit=self._noop,
            stop_runtime_tasks=self._noop_stop,
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

    def test_different_key_or_device_cannot_dispatch_an_already_claimed_audit(self) -> None:
        first = self.approve(key="first-claim")
        other_device = {**self.execute_device, "id": "device-other"}

        with self.assertRaisesRegex(ValueError, "claimed|submitting"):
            self.approve(key="second-claim")
        with self.assertRaisesRegex(ValueError, "claimed|submitting"):
            self.service.approve_trade(
                device=other_device,
                intent_id=self.storage.intent.id,
                expected_version=3,
                draft=self.valid_draft,
                idempotency_key="other-device-claim",
            )

        self.assertEqual(first["action_id"], "first-claim")
        self.assertEqual(self.state.signer_submit_calls, 1)
        self.assertEqual(
            self.storage.audit.guarded_action_id,
            first["action_id"],
        )

    def test_concurrent_service_instances_claim_one_audit_and_submit_once(self) -> None:
        first_service = self.create_service()
        second_service = self.create_service()

        def approve(service: MobileCommandCenterService, key: str):
            return service.approve_trade(
                device=self.execute_device,
                intent_id=self.storage.intent.id,
                expected_version=3,
                draft=self.valid_draft,
                idempotency_key=key,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(approve, first_service, "concurrent-one"),
                executor.submit(approve, second_service, "concurrent-two"),
            ]
            outcomes = []
            failures = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except ValueError as exc:
                    failures.append(str(exc))

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(failures), 1)
        self.assertRegex(failures[0], "claimed|submitting|version")
        self.assertEqual(self.state.signer_submit_calls, 1)

    def test_timeout_and_service_restart_never_redispatch_claimed_audit(self) -> None:
        self.state.submit_error = TimeoutError("fake signer timeout")
        first = self.approve(key="timeout-claim")
        restarted = self.create_service()

        same = restarted.approve_trade(
            device=self.execute_device,
            intent_id=self.storage.intent.id,
            expected_version=3,
            draft=self.valid_draft,
            idempotency_key="timeout-claim",
        )
        with self.assertRaisesRegex(ValueError, "claimed|submitting|version"):
            restarted.approve_trade(
                device=self.execute_device,
                intent_id=self.storage.intent.id,
                expected_version=3,
                draft=self.valid_draft,
                idempotency_key="restart-new-key",
            )

        self.assertEqual(first["action_id"], same["action_id"])
        self.assertEqual(first["status"], MobileActionStatus.VERIFYING.value)
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

    def test_authorized_stop_and_target_are_persisted_with_the_claim(self) -> None:
        self.approve(key="bounded-risk-controls")

        audit = self.storage.audit
        self.assertEqual(
            audit.guarded_authorization,
            {
                "action_id": "bounded-risk-controls",
                "stop_pct": "20",
                "target_pct": "40",
            },
        )

    def test_canonical_generated_full_close_is_bound_to_exact_position(self) -> None:
        intent = self.storage.intent
        self.assertTrue(
            hasattr(intent, "generated_position_id"),
            "generated close intents must persist their exact position binding",
        )
        intent.action = "sell"
        intent.amount = "100%"
        intent.denominated_in_sol = False
        intent.generated_from_position = True
        intent.generated_position_id = self.storage.position.id
        intent.generated_position_version = self.storage.position.version
        intent.generated_position_token_balance = self.storage.position.token_balance
        self.storage.intent = intent
        audit = self.storage.audit
        audit.action = "sell"
        audit.amount = "100%"
        audit.request["denominated_in_sol"] = False
        self.storage.audit = audit
        close_draft = {
            **self.valid_draft,
            "amount": "100%",
        }

        receipt = self.service.close_position(
            device=self.execute_device,
            position_id=self.storage.position.id,
            position_version=self.storage.position.version,
            intent_id=intent.id,
            expected_version=intent.version,
            draft=close_draft,
            escalation_acknowledged=False,
            idempotency_key="full-close",
        )

        self.assertEqual(receipt["action_id"], "full-close")
        self.assertEqual(self.state.signer_submit_calls, 1)

    def test_partial_or_unbound_sell_cannot_be_mislabeled_as_position_close(self) -> None:
        intent = self.storage.intent
        intent.action = "sell"
        intent.amount = "50"
        intent.denominated_in_sol = False
        self.storage.intent = intent
        audit = self.storage.audit
        audit.action = "sell"
        audit.amount = "50"
        audit.request["denominated_in_sol"] = False
        self.storage.audit = audit

        with self.assertRaisesRegex(ValueError, "full|position|100%"):
            self.service.close_position(
                device=self.execute_device,
                position_id=self.storage.position.id,
                position_version=self.storage.position.version,
                intent_id=intent.id,
                expected_version=intent.version,
                draft={**self.valid_draft, "amount": "50"},
                escalation_acknowledged=False,
                idempotency_key="partial-close",
            )
        self.assertEqual(self.state.signer_submit_calls, 0)

    def test_close_rechecks_material_position_state_inside_atomic_claim(self) -> None:
        intent = self.storage.intent
        intent.action = "sell"
        intent.amount = "100%"
        intent.denominated_in_sol = False
        intent.generated_from_position = True
        intent.generated_position_id = self.storage.position.id
        intent.generated_position_version = self.storage.position.version
        intent.generated_position_token_balance = self.storage.position.token_balance
        self.storage.intent = intent
        audit = self.storage.audit
        audit.action = "sell"
        audit.amount = "100%"
        audit.request["denominated_in_sol"] = False
        self.storage.audit = audit
        original_validate = self.service.validate_trade

        def validate_then_change_position(**kwargs):
            result = original_validate(**kwargs)
            position = self.storage.position
            position.token_balance = 75
            position.version += 1
            self.storage.position = position
            return result

        self.service.validate_trade = validate_then_change_position
        with self.assertRaisesRegex(ValueError, "position|version|balance"):
            self.service.close_position(
                device=self.execute_device,
                position_id=self.storage.position.id,
                position_version=4,
                intent_id=intent.id,
                expected_version=intent.version,
                draft={**self.valid_draft, "amount": "100%"},
                escalation_acknowledged=False,
                idempotency_key="raced-close",
            )

        self.assertEqual(self.state.signer_submit_calls, 0)
        self.assertIsNone(
            self.storage.load_mobile_action_receipt("raced-close")
        )

    def test_execution_audit_must_be_exactly_simulated_before_claim(self) -> None:
        for status, final_status in (
            ("submitting", "submitting"),
            ("simulated", "needs_review"),
            ("needs_review", "simulated"),
        ):
            with self.subTest(status=status, final_status=final_status):
                audit = self.storage.audit
                audit.status = status
                audit.final_status = final_status
                self.storage.audit = audit
                with self.assertRaisesRegex(
                    ValueError,
                    "audit|simulated|claimed|submitting",
                ):
                    self.approve(key=f"audit-state-{status}-{final_status}")
                audit.status = "simulated"
                audit.final_status = "simulated"
                self.storage.audit = audit
        self.assertEqual(self.state.signer_submit_calls, 0)

    def test_missing_simulation_and_stale_quote_fail_closed(self) -> None:
        audit = self.storage.audit
        audit.simulation = {}
        self.storage.audit = audit
        with self.assertRaisesRegex(ValueError, "simulation"):
            self.approve(key="missing-simulation")

        audit = self.storage.audit
        audit.simulation = {"status": "ok", "ok": True}
        audit.quote["expires_at"] = (utc_now() - timedelta(seconds=1)).isoformat()
        self.storage.audit = audit
        with self.assertRaisesRegex(ValueError, "stale|expired"):
            self.approve(key="stale-quote")
        self.assertEqual(self.state.signer_submit_calls, 0)

    def test_missing_malformed_or_unknown_preflight_evidence_fails_closed(self) -> None:
        cases = {
            "missing": [],
            "malformed": [{"id": "environment", "status": "pass"}],
            "unknown": [
                *self.storage.audit.preflight_checks,
                {
                    "id": "future_check",
                    "label": "Unknown check",
                    "status": "pass",
                    "reason": "not recognized",
                },
            ],
            "unknown-status": [
                *[
                    row
                    for row in self.storage.audit.preflight_checks
                    if row["id"] != "caps"
                ],
                {
                    "id": "caps",
                    "label": "Live Caps",
                    "status": "warning",
                    "reason": "not a passing status",
                },
            ],
        }

        for name, rows in cases.items():
            with self.subTest(name=name):
                audit = self.storage.audit
                audit.preflight_checks = rows
                self.storage.audit = audit
                with self.assertRaisesRegex(
                    ValueError,
                    "preflight|missing|unknown|recognized|passing",
                ):
                    self.approve(key=f"preflight-{name}")
                audit.preflight_checks = [
                    {
                        "id": check_id,
                        "label": check_id,
                        "status": "pass",
                        "reason": "prepared",
                    }
                    for check_id in (
                        "environment",
                        "mint",
                        "wallet",
                        "signer",
                        "amount",
                        "slippage",
                        "priority_fee",
                        "pool",
                        "caps",
                        "blockers",
                    )
                ]
                self.storage.audit = audit
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

        audit = self.storage.audit
        audit.status = "needs_review"
        audit.final_status = "needs_review"
        self.storage.audit = audit
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
        audit = self.storage.audit
        audit.status = "needs_review"
        audit.final_status = "needs_review"
        audit.recommended_action = "Review the signature manually."
        self.storage.audit = audit
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

    def test_restart_reconciles_pending_reject_and_adjust_receipts(self) -> None:
        now = utc_now()
        intent = self.storage.intent
        intent.status = "cancelled"
        intent.version += 1
        intent.reason = "Rejected from paired mobile device: operator rejected"
        self.storage.intent = intent
        reject_receipt = MobileActionReceipt(
            id="recover-reject",
            idempotency_key_hash="reject-hash",
            device_id=self.execute_device["id"],
            action_type="trade_reject",
            entity_id=intent.id,
            payload={
                "operator_message": "Rejecting prepared intent",
                "submitted_at": now.isoformat(),
                "reconcile_after_ms": 500,
                "expected_version": 3,
                "reason": "operator rejected",
            },
            status=MobileActionStatus.PENDING.value,
            created_at=now,
            updated_at=now,
        )
        self.storage.reserve_mobile_action_receipt(reject_receipt)

        position = self.storage.position
        position.stop_pct = 25
        position.target_pct = 45
        position.version += 1
        self.storage.position = position
        adjust_receipt = MobileActionReceipt(
            id="recover-adjust",
            idempotency_key_hash="adjust-hash",
            device_id=self.execute_device["id"],
            action_type="position_adjust_exit",
            entity_id=position.id,
            payload={
                "operator_message": "Applying bounded exit controls",
                "submitted_at": now.isoformat(),
                "reconcile_after_ms": 500,
                "expected_version": 4,
                "stop_pct": "25",
                "target_pct": "45",
            },
            status=MobileActionStatus.PENDING.value,
            created_at=now,
            updated_at=now,
        )
        self.storage.reserve_mobile_action_receipt(adjust_receipt)
        restarted = self.create_service()

        rejected = restarted.action(
            device=self.execute_device,
            action_id=reject_receipt.id,
        )
        adjusted = restarted.action(
            device=self.execute_device,
            action_id=adjust_receipt.id,
        )

        self.assertEqual(rejected["status"], MobileActionStatus.CANCELLED.value)
        self.assertEqual(adjusted["status"], MobileActionStatus.CONFIRMED.value)

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
