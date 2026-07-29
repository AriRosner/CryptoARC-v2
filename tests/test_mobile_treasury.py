from __future__ import annotations

import base64
import json
import threading
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from solders.keypair import Keypair

from app.core.models import (
    LiveExecutionAudit,
    MobileActionReceipt,
    MobileDestinationAuthorization,
    utc_now,
)
from app.core.state import BotState
from app.core.storage import Storage
from app.mobile.router import create_mobile_router
from app.mobile.service import MobileCommandCenterService


class TreasuryState:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.settings = SimpleNamespace(
            live_active_backend_armed=True,
            live_active_wallet_public_key="WalletTreasurySource1111111111111111111111111",
            live_signer_mode="local_hot_wallet",
            kill_switch_enabled=False,
        )
        self.blockers: list[str] = []
        self.execute_calls = 0
        self.reconcile_calls = 0
        self.execute_status = "pending"
        self.wallet_payload = {
            "artifact_type": "cryptoarc_mobile_wallet",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "wallet_public_key": self.settings.live_active_wallet_public_key,
            "total_value_sol": 1.25,
            "freshness": {
                "status": "fresh",
                "generated_at": utc_now().isoformat(),
                "age_seconds": 0,
                "stale_after_seconds": 30,
                "approximate": True,
            },
            "balances": [
                {
                    "asset": "SOL",
                    "total": 1.25,
                    "committed": 0.4,
                    "available": 0.7,
                    "reserved": 0.15,
                    "approximate": True,
                }
            ],
            "allocation": [
                {"asset": "SOL", "value_sol": 1.25, "percentage": 100.0}
            ],
            "pnl": {
                "realized_sol": 0.2,
                "unrealized_sol": 0.1,
                "approximate": True,
            },
            "fees": {
                "network_sol": 0.001,
                "priority_sol": 0.0002,
                "total_sol": 0.0012,
                "approximate": False,
            },
            "rent": {
                "recoverable_sol": 0.004,
                "eligible_accounts": 2,
                "eligible_token_accounts": [
                    "TokenAccount111111111111111111111111111111"
                ],
                "status": "ready",
                "approximate": False,
            },
            "reconciliation": {
                "status": "matched",
                "last_reconciled_at": utc_now().isoformat(),
                "approximate": False,
            },
            "health": {
                "rpc": "healthy",
                "signer": "healthy",
                "backend": "armed",
                "readiness": "ready",
                "kill_switch": "clear",
            },
        }
        self.transaction_rows = [
            {
                "id": "tx-public-1",
                "action": "withdrawal",
                "asset": "SOL",
                "amount": "0.2",
                "destination": "DestinationTreasury111111111111111111111111",
                "status": "confirmed",
                "created_at": utc_now().isoformat(),
                "transaction_signature": "PublicSignature111",
            }
        ]

    def mobile_wallet(self) -> dict[str, object]:
        return dict(self.wallet_payload)

    def mobile_wallet_transactions(self) -> dict[str, object]:
        return {
            "artifact_type": "cryptoarc_mobile_wallet_transactions",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "transactions": list(self.transaction_rows),
        }

    def mobile_treasury_preflight(
        self,
        *,
        action: str,
        address: str,
        asset: str,
        amount: Decimal,
        token_accounts: list[str],
        exclude_action_id: str = "",
    ) -> dict[str, object]:
        del address, asset, exclude_action_id
        if self.blockers:
            return {"blockers": list(self.blockers)}
        expected_fee = Decimal("0.000005")
        remaining = (
            Decimal("1.25") + amount - expected_fee
            if action == "rent_recovery"
            else Decimal("1.25") - amount - expected_fee
        )
        return {
            "blockers": [],
            "expected_fee_sol": expected_fee,
            "remaining_balance_sol": remaining,
            "warnings": ["Treasury movement requires elevated confirmation."],
            "token_accounts": list(token_accounts),
            "wallet_public_key": self.settings.live_active_wallet_public_key,
            "profit_sweep_policy": (
                {
                    "max_per_day": 1,
                    "cooldown_seconds": 3600,
                }
                if action == "profit_sweep"
                else {}
            ),
        }

    def execute_mobile_treasury(
        self,
        *,
        action_id: str,
        action: str,
        source_wallet_public_key: str,
        address: str,
        asset: str,
        amount: Decimal,
        token_accounts: list[str],
    ) -> dict[str, object]:
        receipt = self.storage.load_mobile_action_receipt(action_id)
        if receipt is None:
            raise AssertionError("treasury side effect ran before durable receipt")
        authorization = self.storage.load_mobile_destination_authorization(
            str(receipt.payload["authorization_id"])
        )
        if authorization is None or authorization.used_at is None:
            raise AssertionError("authorization was not consumed atomically")
        if (
            source_wallet_public_key
            != self.settings.live_active_wallet_public_key
        ):
            raise AssertionError("treasury source wallet was not bound")
        self.execute_calls += 1
        result = {
            "status": self.execute_status,
            "operator_message": "Treasury request submitted",
            "transaction_signature": "PublicSignature111",
            "action": action,
            "destination": address,
            "asset": asset,
            "amount": str(amount),
            "token_accounts": token_accounts,
        }
        if action in {"profit_sweep", "rent_recovery"}:
            result["execution_audit_id"] = f"audit-{action}-{action_id}"
        return result

    def reconcile_mobile_treasury_action(
        self,
        receipt: object,
    ) -> dict[str, object]:
        del receipt
        self.reconcile_calls += 1
        return {
            "status": "confirmed",
            "operator_message": "Treasury transaction confirmed",
        }


class MobileTreasuryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = Storage(str(Path(self.directory.name) / "treasury.db"))
        self.state = TreasuryState(self.storage)
        self.config = SimpleNamespace(live_trading_enabled=True)
        self.service = self.create_service()
        self.desktop_operator = {"authenticated": True, "id": "desktop-test"}
        self.device = {
            "id": "device_treasury",
            "scopes": ["mobile:wallet:read", "mobile:treasury:request"],
        }
        self.other_device = {
            "id": "device_other",
            "scopes": ["mobile:wallet:read", "mobile:treasury:request"],
        }
        self.destination = "DestinationTreasury111111111111111111111111"

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

    async def _noop(self) -> None:
        return None

    async def _noop_stop(self) -> dict[str, object]:
        return {}

    def authorize(
        self,
        *,
        device_id: str | None = None,
        action: str = "withdrawal",
        address: str | None = None,
        asset: str = "SOL",
        max_amount: Decimal = Decimal("0.25"),
        expires_in_seconds: int = 300,
        purpose: str = "manual profit transfer",
    ) -> dict[str, object]:
        return self.service.authorize_destination(
            desktop_operator=self.desktop_operator,
            device_id=device_id or self.device["id"],
            action=action,
            address=address or self.destination,
            asset=asset,
            max_amount=max_amount,
            expires_in_seconds=expires_in_seconds,
            purpose=purpose,
        )

    def preview(
        self,
        authorization: dict[str, object],
        *,
        action: str = "withdrawal",
        device: dict[str, object] | None = None,
        address: str | None = None,
        asset: str = "SOL",
        amount: Decimal = Decimal("0.20"),
        token_accounts: list[str] | None = None,
    ) -> dict[str, object]:
        method = getattr(self.service, f"preview_{action}")
        return method(
            device=device or self.device,
            authorization_id=authorization["id"],
            address=address or self.destination,
            asset=asset,
            amount=amount,
            token_accounts=token_accounts or [],
        )

    def execute(
        self,
        authorization: dict[str, object],
        preview: dict[str, object],
        *,
        action: str = "withdrawal",
        device: dict[str, object] | None = None,
        address: str | None = None,
        asset: str = "SOL",
        amount: Decimal = Decimal("0.20"),
        idempotency_key: str = "withdraw-1",
        preview_id: str | None = None,
        token_accounts: list[str] | None = None,
    ) -> dict[str, object]:
        method = getattr(self.service, f"request_{action}")
        return method(
            device=device or self.device,
            authorization_id=authorization["id"],
            preview_id=preview_id if preview_id is not None else preview["preview_id"],
            address=address or self.destination,
            asset=asset,
            amount=amount,
            idempotency_key=idempotency_key,
            token_accounts=token_accounts or [],
        )

    def test_temporary_destination_authorization_is_bound_and_single_use(self) -> None:
        authorization = self.authorize()
        preview = self.preview(authorization)
        receipt = self.execute(authorization, preview)

        self.assertEqual(receipt["status"], "pending")
        self.assertEqual(self.state.execute_calls, 1)
        with self.assertRaisesRegex(ValueError, "already used"):
            self.execute(
                authorization,
                preview,
                amount=Decimal("0.20"),
                idempotency_key="withdraw-2",
            )
        self.assertEqual(self.state.execute_calls, 1)

    def test_concurrent_stale_preview_cannot_reactivate_consumed_authorization(self) -> None:
        authorization = self.authorize()
        original_preview = self.preview(authorization)
        late_preflight_started = threading.Event()
        release_late_preflight = threading.Event()
        original_preflight = self.state.mobile_treasury_preflight
        late_result: list[object] = []

        def delayed_preflight(**kwargs: object) -> dict[str, object]:
            if kwargs.get("amount") == Decimal("0.19"):
                late_preflight_started.set()
                self.assertTrue(release_late_preflight.wait(timeout=5))
            return original_preflight(**kwargs)

        self.state.mobile_treasury_preflight = delayed_preflight  # type: ignore[method-assign]

        def create_late_preview() -> None:
            try:
                late_result.append(
                    self.preview(authorization, amount=Decimal("0.19"))
                )
            except Exception as exc:
                late_result.append(exc)

        thread = threading.Thread(target=create_late_preview)
        thread.start()
        self.assertTrue(late_preflight_started.wait(timeout=5))
        self.execute(authorization, original_preview)
        release_late_preflight.set()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())

        stored = self.storage.load_mobile_destination_authorization(
            str(authorization["id"])
        )
        self.assertIsNotNone(stored)
        self.assertIsNotNone(stored.used_at if stored else None)
        self.assertEqual(len(late_result), 1)
        self.assertIsInstance(late_result[0], ValueError)
        self.assertIn("already used", str(late_result[0]))
        with self.assertRaisesRegex(ValueError, "already used"):
            self.preview(authorization, amount=Decimal("0.18"))
        self.assertEqual(self.state.execute_calls, 1)

    def test_concurrent_services_atomically_claim_one_profit_sweep_slot(
        self,
    ) -> None:
        first_authorization = self.authorize(
            action="profit_sweep",
            purpose="first concurrent sweep",
        )
        second_authorization = self.authorize(
            action="profit_sweep",
            purpose="second concurrent sweep",
        )
        first_preview = self.preview(
            first_authorization,
            action="profit_sweep",
        )
        second_preview = self.preview(
            second_authorization,
            action="profit_sweep",
        )
        first_service = self.create_service()
        second_service = self.create_service()
        start = threading.Barrier(2)
        outcomes: list[object] = []

        def request(
            service: MobileCommandCenterService,
            authorization: dict[str, object],
            preview: dict[str, object],
            key: str,
        ) -> None:
            start.wait(timeout=5)
            try:
                outcomes.append(
                    service.request_profit_sweep(
                        device=self.device,
                        authorization_id=authorization["id"],
                        preview_id=preview["preview_id"],
                        address=self.destination,
                        asset="SOL",
                        amount=Decimal("0.20"),
                        idempotency_key=key,
                        token_accounts=[],
                    )
                )
            except Exception as exc:
                outcomes.append(exc)

        threads = [
            threading.Thread(
                target=request,
                args=(
                    first_service,
                    first_authorization,
                    first_preview,
                    "concurrent-profit-first",
                ),
            ),
            threading.Thread(
                target=request,
                args=(
                    second_service,
                    second_authorization,
                    second_preview,
                    "concurrent-profit-second",
                ),
            ),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())

        receipts = [value for value in outcomes if isinstance(value, dict)]
        errors = [value for value in outcomes if isinstance(value, Exception)]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(len(errors), 1)
        self.assertRegex(str(errors[0]), "daily sweep cap|cooldown")
        self.assertEqual(self.state.execute_calls, 1)
        stored = self.storage.load_mobile_action_receipt(
            str(receipts[0]["action_id"])
        )
        self.assertIsNotNone(stored)
        claim = stored.payload.get("profit_sweep_policy_claim") if stored else None
        self.assertEqual(
            claim,
            {
                "action": "profit_sweep",
                "source_wallet_public_key": (
                    self.state.settings.live_active_wallet_public_key
                ),
                "claim_day": stored.created_at.date().isoformat(),
                "max_per_day": 1,
                "cooldown_seconds": 3600,
                "claimed_at": stored.created_at.isoformat(),
            },
        )

    def test_destination_authorization_is_bound_to_one_treasury_action(self) -> None:
        authorization = self.service.authorize_destination(
            desktop_operator=self.desktop_operator,
            device_id=self.device["id"],
            action="profit_sweep",
            address=self.destination,
            asset="SOL",
            max_amount=Decimal("0.25"),
            expires_in_seconds=300,
            purpose="configured profit sweep",
        )
        with self.assertRaisesRegex(ValueError, "action"):
            self.preview(authorization, action="withdrawal")

    def test_execute_requires_exact_unexpired_preview_binding(self) -> None:
        cases = [
            ("address", {"address": "OtherDestination1111111111111111111111111"}),
            ("asset", {"asset": "USDC"}),
            ("amount", {"amount": Decimal("0.19")}),
            ("device", {"device": self.other_device}),
            ("preview", {"preview_id": "missing-preview"}),
        ]
        for label, overrides in cases:
            with self.subTest(label=label):
                authorization = self.authorize()
                preview = self.preview(authorization)
                with self.assertRaisesRegex(ValueError, label):
                    self.execute(
                        authorization,
                        preview,
                        idempotency_key=f"wrong-{label}",
                        **overrides,
                    )
        self.assertEqual(self.state.execute_calls, 0)

    def test_authorization_rejects_wrong_binding_excess_and_expiry(self) -> None:
        checks = [
            ("address", {"address": "OtherDestination1111111111111111111111111"}),
            ("asset", {"asset": "USDC"}),
            ("device", {"device": self.other_device}),
            ("maximum", {"amount": Decimal("0.26")}),
        ]
        for label, overrides in checks:
            with self.subTest(label=label):
                authorization = self.authorize()
                with self.assertRaisesRegex(ValueError, label):
                    self.preview(authorization, **overrides)

        authorization = self.authorize(expires_in_seconds=1)
        stored = self.storage.load_mobile_destination_authorization(
            str(authorization["id"])
        )
        assert stored is not None
        with self.storage._connect() as connection:
            connection.execute(
                """
                UPDATE mobile_destination_authorizations
                SET expires_at = ?
                WHERE id = ?
                """,
                (
                    (utc_now() - timedelta(seconds=1)).isoformat(),
                    stored.id,
                ),
            )
        with self.assertRaisesRegex(ValueError, "expired"):
            self.preview(authorization)

    def test_preflight_fails_closed_for_all_treasury_health_and_balance_gates(self) -> None:
        blockers = [
            "kill switch is enabled",
            "readiness is not ready",
            "signer is unhealthy",
            "RPC wallet health is unavailable",
            "insufficient available balance after reserves and fees",
            "rent recovery amount does not match eligible rent",
        ]
        for index, blocker in enumerate(blockers):
            with self.subTest(blocker=blocker):
                self.state.blockers = [blocker]
                authorization = self.authorize(purpose=f"gate {index}")
                with self.assertRaisesRegex(ValueError, blocker):
                    self.preview(authorization)
        self.assertEqual(self.state.execute_calls, 0)

    def test_duplicate_idempotency_returns_same_receipt_without_second_side_effect(self) -> None:
        authorization = self.authorize()
        preview = self.preview(authorization)
        first = self.execute(authorization, preview, idempotency_key="duplicate-key")
        self.config.live_trading_enabled = False
        second = self.execute(authorization, preview, idempotency_key="duplicate-key")

        self.assertEqual(first, second)
        self.assertEqual(first["action_id"], "duplicate-key")
        self.assertEqual(self.state.execute_calls, 1)

        self.config.live_trading_enabled = True
        with self.assertRaisesRegex(ValueError, "another request"):
            self.execute(
                authorization,
                preview,
                idempotency_key="duplicate-key",
                amount=Decimal("0.19"),
            )

    def test_restart_reconciles_owner_receipt_without_resubmission(self) -> None:
        authorization = self.authorize()
        preview = self.preview(authorization)
        receipt = self.execute(
            authorization,
            preview,
            idempotency_key="restart-action",
        )
        restarted = self.create_service()

        reconciled = restarted.action(
            device=self.device,
            action_id=receipt["action_id"],
        )

        self.assertEqual(reconciled["status"], "confirmed")
        self.assertEqual(self.state.execute_calls, 1)
        self.assertEqual(self.state.reconcile_calls, 1)
        with self.assertRaisesRegex(LookupError, "not found"):
            restarted.action(
                device=self.other_device,
                action_id=receipt["action_id"],
            )

    def test_restart_routes_bound_treasury_audit_through_treasury_reconciliation(
        self,
    ) -> None:
        authorization = self.authorize(
            action="profit_sweep",
            purpose="profit sweep restart",
        )
        preview = self.preview(
            authorization,
            action="profit_sweep",
        )
        receipt = self.execute(
            authorization,
            preview,
            action="profit_sweep",
            idempotency_key="profit-sweep-restart",
        )

        restarted = self.create_service()
        reconciled = restarted.action(
            device=self.device,
            action_id=str(receipt["action_id"]),
        )

        self.assertEqual(reconciled["status"], "confirmed")
        self.assertEqual(self.state.execute_calls, 1)
        self.assertEqual(self.state.reconcile_calls, 1)

    def test_all_treasury_actions_are_preview_first_and_authorization_bound(self) -> None:
        for action, token_accounts in [
            ("withdrawal", []),
            ("profit_sweep", []),
            (
                "rent_recovery",
                ["TokenAccount111111111111111111111111111111"],
            ),
        ]:
            with self.subTest(action=action):
                authorization = self.authorize(action=action, purpose=action)
                preview = self.preview(
                    authorization,
                    action=action,
                    token_accounts=token_accounts,
                )
                self.assertEqual(preview["action"], action)
                self.assertEqual(preview["authorization_id"], authorization["id"])
                self.assertEqual(preview["token_accounts"], token_accounts)
                receipt = self.execute(
                    authorization,
                    preview,
                    action=action,
                    idempotency_key=f"{action}-action",
                    token_accounts=token_accounts,
                )
                self.assertEqual(receipt["status"], "pending")
        self.assertEqual(self.state.execute_calls, 3)

    def test_profit_and_rent_receipts_persist_their_execution_audit_binding(
        self,
    ) -> None:
        for action, token_accounts in (
            ("profit_sweep", []),
            (
                "rent_recovery",
                ["TokenAccount111111111111111111111111111111"],
            ),
        ):
            with self.subTest(action=action):
                authorization = self.authorize(
                    action=action,
                    purpose=f"{action} audit binding",
                )
                preview = self.preview(
                    authorization,
                    action=action,
                    token_accounts=token_accounts,
                )
                public_receipt = self.execute(
                    authorization,
                    preview,
                    action=action,
                    idempotency_key=f"{action}-audit-binding",
                    token_accounts=token_accounts,
                )
                stored = self.storage.load_mobile_action_receipt(
                    str(public_receipt["action_id"])
                )
                self.assertEqual(
                    stored.execution_audit_id if stored else "",
                    f"audit-{action}-{public_receipt['action_id']}",
                )

    def test_wallet_reads_distinguish_funds_and_redact_request_material(self) -> None:
        authorization = self.authorize()
        preview = self.preview(authorization)
        self.execute(authorization, preview)

        wallet = self.service.wallet(device=self.device)
        transactions = self.service.wallet_transactions(device=self.device)
        destinations = self.service.destinations(device=self.device)

        sol = wallet["balances"][0]
        self.assertEqual(sol["committed"], 0.4)
        self.assertEqual(sol["available"], 0.7)
        self.assertEqual(sol["reserved"], 0.15)
        self.assertTrue(wallet["freshness"]["approximate"])
        self.assertEqual(transactions["transactions"][0]["destination"], self.destination)
        self.assertEqual(destinations["destinations"][0]["address"], self.destination)

        persisted = self.storage.load_mobile_action_receipt("withdraw-1")
        self.assertIsNotNone(persisted)
        serialized = json.dumps(
            {
                "wallet": wallet,
                "transactions": transactions,
                "destinations": destinations,
                "receipt": persisted.to_dict() if persisted else {},
            }
        ).lower()
        for forbidden in (
            "private_key",
            "seed_phrase",
            "auth_token",
            "unsigned_transaction",
            "signed_transaction",
            "request_body",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_treasury_http_validation_is_redacted_and_desktop_authorized(self) -> None:
        app = FastAPI()

        def require_scope(_: str):
            return lambda: self.device

        app.include_router(create_mobile_router(self.service, require_scope))
        client = TestClient(app)
        response = client.post(
            "/api/mobile/wallet/withdrawals",
            headers={"Idempotency-Key": "http-redaction"},
            json={
                "authorization_id": "auth",
                "preview_id": "preview",
                "address": self.destination,
                "asset": "SOL",
                "amount": "0.2",
                "private_key": "must-never-echo",
                "unsigned_transaction_base64": "must-never-echo",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "Invalid mobile request"})

        desktop = client.post(
            "/api/mobile/destination-authorizations",
            json={
                "device_id": self.device["id"],
                "action": "withdrawal",
                "address": self.destination,
                "asset": "SOL",
                "max_amount": "0.25",
                "expires_in_seconds": 300,
                "purpose": "desktop issue",
            },
        )
        self.assertEqual(desktop.status_code, 200)
        self.assertNotIn("desktop_operator", json.dumps(desktop.json()).lower())


class ProductionTreasurySafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = BotState(
            database_path=str(Path(self.directory.name) / "production-treasury.db")
        )
        self.wallet = str(Keypair().pubkey())
        self.destination = str(Keypair().pubkey())
        settings = self.state.settings
        settings.live_active_backend_armed = True
        settings.live_active_wallet_public_key = self.wallet
        settings.live_hot_wallet_public_key = self.wallet
        settings.live_signer_mode = "local_hot_wallet"
        settings.live_session_acknowledged = True
        settings.kill_switch_enabled = False
        settings.solana_rpc_url = "http://127.0.0.1:1"
        settings.profit_sweep_min_reserve_sol = 0.05
        settings.profit_sweep_enabled = True
        settings.profit_sweep_mode = "fixed_sol"
        settings.profit_sweep_threshold_sol = 0.05
        settings.profit_sweep_min_profit_sol = 0.05
        settings.profit_sweep_amount_sol = 0.02
        settings.profit_sweep_percentage = 25.0
        settings.profit_sweep_destination_wallet = self.destination
        settings.profit_sweep_cooldown_seconds = 3600
        settings.profit_sweep_max_per_day = 2
        self.balance = Decimal("0.50")
        self.realized = Decimal("0.10")
        self._configure_safe_fakes()

    def _configure_safe_fakes(self) -> None:
        self.state.signer_status = lambda *_args, **_kwargs: {  # type: ignore[method-assign]
            "connected": True,
            "healthy": True,
            "can_sign": True,
            "wallet_public_key": self.wallet,
        }
        self.state.hot_wallet = SimpleNamespace(
            status=lambda: {
                "imported": True,
                "unlocked": True,
                "wallet_public_key": self.wallet,
            },
            transfer_sol=lambda *_args, **_kwargs: {
                "signature": "must-not-run-unless-asserted"
            },
            simulate_and_submit=lambda *_args, **_kwargs: {
                "signature": "PublicRentSignature111"
            },
        )
        self.state.live_wallet_balance = lambda wallet: {  # type: ignore[method-assign]
            "wallet_public_key": wallet,
            "balance_sol": float(self.balance),
            "error": "",
        }
        self.state.live_ledger = lambda _wallet: {  # type: ignore[method-assign]
            "summary": {"realized_pnl_sol": float(self.realized)}
        }
        self.state._recent_readiness_status = lambda: {  # type: ignore[method-assign]
            "strategy_promotion": {"can_promote": True}
        }
        self.state._execution_readiness_status = (  # type: ignore[method-assign]
            lambda **_kwargs: {
                "status": "live_ready",
                "can_live_submit": True,
                "blockers": [],
            }
        )
        self.state._pre_run_backup_status = lambda: {  # type: ignore[method-assign]
            "fresh": True,
            "state": "fresh",
            "blocker": "",
        }
        self.state._manual_live_verification_status = (  # type: ignore[method-assign]
            lambda *_args, **_kwargs: {"verified": True, "blocker": ""}
        )

    def _receipt(
        self,
        action_id: str,
        *,
        action: str = "withdrawal",
        wallet: str | None = None,
        amount: str = "0.10",
        expected_fee: str = "0.000005",
        status: str = "pending",
    ) -> MobileActionReceipt:
        now = utc_now()
        receipt = MobileActionReceipt(
            id=action_id,
            idempotency_key_hash=f"hash-{action_id}",
            device_id="device-production",
            action_type=action,
            entity_id=f"authorization-{action_id}",
            payload={
                "source_wallet_public_key": wallet or self.wallet,
                "address": self.destination,
                "asset": "SOL",
                "amount": amount,
                "expected_fee_sol": expected_fee,
                "submitted_at": now.isoformat(),
            },
            status=status,
            created_at=now,
            updated_at=now,
        )
        self.state.storage.reserve_mobile_action_receipt(receipt)
        return receipt

    def _preflight(
        self,
        *,
        action: str = "withdrawal",
        amount: str = "0.20",
        address: str | None = None,
        exclude_action_id: str = "",
        token_accounts: list[str] | None = None,
    ) -> dict[str, object]:
        return self.state.mobile_treasury_preflight(
            action=action,
            address=address or self.destination,
            asset="SOL",
            amount=Decimal(amount),
            token_accounts=token_accounts or [],
            exclude_action_id=exclude_action_id,
        )

    def test_preflight_rejects_reimported_or_mismatched_unlocked_wallet(self) -> None:
        replacement = str(Keypair().pubkey())
        self.state.signer_status = lambda *_args, **_kwargs: {  # type: ignore[method-assign]
            "connected": True,
            "healthy": True,
            "can_sign": True,
            "wallet_public_key": replacement,
        }
        self.state.hot_wallet.status = lambda: {
            "imported": True,
            "unlocked": True,
            "wallet_public_key": replacement,
        }

        result = self._preflight()

        self.assertIn(
            "armed wallet does not match unlocked local hot wallet",
            result["blockers"],
        )

    def test_execute_rechecks_source_wallet_immediately_before_signing(self) -> None:
        receipt = self._receipt("wallet-swap")
        transfer_calls: list[object] = []
        self.state.hot_wallet.transfer_sol = lambda *_args, **_kwargs: transfer_calls.append(
            True
        )
        original_preflight = self.state.mobile_treasury_preflight

        def swap_after_preflight(**kwargs: object) -> dict[str, object]:
            result = original_preflight(**kwargs)
            replacement = str(Keypair().pubkey())
            self.state.hot_wallet.status = lambda: {
                "imported": True,
                "unlocked": True,
                "wallet_public_key": replacement,
            }
            return result

        self.state.mobile_treasury_preflight = swap_after_preflight  # type: ignore[method-assign]

        with self.assertRaisesRegex(
            ValueError, "armed wallet does not match unlocked local hot wallet"
        ):
            self.state.execute_mobile_treasury(
                action_id=receipt.id,
                action="withdrawal",
                source_wallet_public_key=self.wallet,
                address=self.destination,
                asset="SOL",
                amount=Decimal("0.10"),
                token_accounts=[],
            )
        self.assertEqual(transfer_calls, [])

    def test_profit_sweep_rechecks_wallet_after_audit_before_transfer(self) -> None:
        receipt = self._receipt(
            "profit-wallet-swap",
            action="profit_sweep",
            amount="0.02",
        )
        transfer_calls: list[object] = []
        self.state.hot_wallet.transfer_sol = lambda *_args, **_kwargs: transfer_calls.append(
            True
        )
        self.state.mobile_treasury_preflight = lambda **_kwargs: {  # type: ignore[method-assign]
            "blockers": [],
            "wallet_public_key": self.wallet,
            "profit_sweep_policy": {"sweep_mode": "fixed_sol"},
        }
        original_audit = self.state._mobile_treasury_audit

        def swap_after_audit(**kwargs: object) -> LiveExecutionAudit:
            audit = original_audit(**kwargs)
            replacement = str(Keypair().pubkey())
            self.state.hot_wallet.status = lambda: {
                "imported": True,
                "unlocked": True,
                "wallet_public_key": replacement,
            }
            return audit

        self.state._mobile_treasury_audit = swap_after_audit  # type: ignore[method-assign]

        with self.assertRaisesRegex(
            ValueError, "armed wallet does not match unlocked local hot wallet"
        ):
            self.state.execute_mobile_treasury(
                action_id=receipt.id,
                action="profit_sweep",
                source_wallet_public_key=self.wallet,
                address=self.destination,
                asset="SOL",
                amount=Decimal("0.02"),
                token_accounts=[],
            )
        self.assertEqual(transfer_calls, [])

    def test_profit_audit_binding_survives_ambiguous_signing_failure(
        self,
    ) -> None:
        receipt = self._receipt(
            "profit-ambiguous-audit",
            action="profit_sweep",
            amount="0.02",
        )
        self.state.mobile_treasury_preflight = lambda **_kwargs: {  # type: ignore[method-assign]
            "blockers": [],
            "wallet_public_key": self.wallet,
            "profit_sweep_policy": {"sweep_mode": "fixed_sol"},
        }

        def fail_after_audit(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("ambiguous signer boundary")

        self.state.hot_wallet.transfer_sol = fail_after_audit

        with self.assertRaisesRegex(RuntimeError, "ambiguous signer boundary"):
            self.state.execute_mobile_treasury(
                action_id=receipt.id,
                action="profit_sweep",
                source_wallet_public_key=self.wallet,
                address=self.destination,
                asset="SOL",
                amount=Decimal("0.02"),
                token_accounts=[],
            )

        stored = self.state.storage.load_mobile_action_receipt(receipt.id)
        self.assertTrue(stored.execution_audit_id if stored else "")
        audit = self.state.storage.load_live_execution_audit(
            stored.execution_audit_id if stored else ""
        )
        self.assertEqual(audit.status if audit else "", "submitting")
        receipt.status = "verifying"
        self.state.storage.save_mobile_action_receipt(receipt)
        preserved = self.state.storage.load_mobile_action_receipt(receipt.id)
        self.assertEqual(
            preserved.execution_audit_id if preserved else "",
            stored.execution_audit_id if stored else "",
        )

    def test_rent_recovery_rechecks_wallet_after_build_before_signing(self) -> None:
        receipt = self._receipt(
            "rent-wallet-swap",
            action="rent_recovery",
            amount="0.004",
        )
        submit_calls: list[object] = []
        self.state.hot_wallet.simulate_and_submit = lambda *_args, **_kwargs: submit_calls.append(
            True
        )
        self.state.mobile_treasury_preflight = lambda **_kwargs: {  # type: ignore[method-assign]
            "blockers": [],
            "wallet_public_key": self.wallet,
        }

        def build_then_swap(*_args: object, **_kwargs: object) -> dict[str, object]:
            replacement = str(Keypair().pubkey())
            self.state.hot_wallet.status = lambda: {
                "imported": True,
                "unlocked": True,
                "wallet_public_key": replacement,
            }
            return {
                "unsigned_transaction_base64": base64.b64encode(b"unsigned").decode(),
                "selected_count": 1,
                "recoverable_rent_sol": "0.004",
            }

        self.state._build_mobile_rent_recovery_transaction = build_then_swap  # type: ignore[method-assign]

        with self.assertRaisesRegex(
            ValueError, "armed wallet does not match unlocked local hot wallet"
        ):
            self.state.execute_mobile_treasury(
                action_id=receipt.id,
                action="rent_recovery",
                source_wallet_public_key=self.wallet,
                address=self.wallet,
                asset="SOL",
                amount=Decimal("0.004"),
                token_accounts=[str(Keypair().pubkey())],
            )
        self.assertEqual(submit_calls, [])

    def test_profit_sweep_requires_exact_existing_policy(self) -> None:
        self.state.settings.profit_sweep_enabled = False
        disabled = self._preflight(
            action="profit_sweep",
            amount="0.02",
        )
        self.assertIn("profit sweep is disabled", disabled["blockers"])

        self.state.settings.profit_sweep_enabled = True
        wrong_amount = self._preflight(
            action="profit_sweep",
            amount="0.03",
        )
        self.assertIn(
            "profit sweep amount does not match configured policy",
            wrong_amount["blockers"],
        )

        self.realized = Decimal("0.01")
        below_profit = self._preflight(
            action="profit_sweep",
            amount="0.02",
        )
        self.assertIn(
            "realized live profit is below minimum profit to sweep",
            below_profit["blockers"],
        )

        self.realized = Decimal("0.10")
        self.state.settings.profit_sweep_mode = "percentage"
        percentage = self._preflight(
            action="profit_sweep",
            amount="0.025",
        )
        self.assertEqual(percentage["blockers"], [])
        self.assertEqual(
            Decimal(str(percentage["profit_sweep_policy"]["expected_amount_sol"])),
            Decimal("0.025"),
        )

        self.state.settings.profit_sweep_max_per_day = 1
        now = utc_now()
        self.state.storage.save_live_execution_audit(
            LiveExecutionAudit(
                id="existing-sweep",
                created_at=now,
                updated_at=now,
                action="profit_sweep",
                mint="SOL",
                amount="0.025",
                status="submitted",
                signer_mode="local_hot_wallet",
                wallet_public_key=self.wallet,
                final_status="submitted",
            )
        )
        capped = self._preflight(
            action="profit_sweep",
            amount="0.025",
        )
        self.assertIn("daily sweep cap reached", capped["blockers"])
        self.assertIn("profit sweep cooldown active", capped["blockers"])

    def test_reservations_are_wallet_scoped_unbounded_and_exclude_current(self) -> None:
        current = self._receipt("current", amount="0.25")
        self._receipt("older-same-wallet", amount="0.10")
        self._receipt(
            "rent-fee-same-wallet",
            action="rent_recovery",
            amount="0.004",
        )
        self._receipt(
            "review-required-same-wallet",
            amount="0.01",
            status="review_required",
        )
        other_wallet = str(Keypair().pubkey())
        for index in range(510):
            self._receipt(
                f"newer-other-{index}",
                wallet=other_wallet,
                amount="0.40",
            )

        result = self._preflight(
            amount="0.25",
            exclude_action_id=current.id,
        )
        self.assertEqual(result["blockers"], [])
        self.assertEqual(
            Decimal(str(result["remaining_balance_sol"])),
            Decimal("0.139980"),
        )

        wallet = self.state.mobile_wallet()
        sol = wallet["balances"][0]
        self.assertEqual(Decimal(str(sol["reserved"])), Decimal("0.410020"))
        self.assertEqual(Decimal(str(sol["available"])), Decimal("0.089980"))

    def test_live_execution_recovery_backup_and_operator_proof_all_gate(self) -> None:
        self.state._execution_readiness_status = (  # type: ignore[method-assign]
            lambda **_kwargs: {
                "status": "blocked",
                "can_live_submit": False,
                "blockers": ["live quote evidence blocked"],
            }
        )
        self.state._pre_run_backup_status = lambda: {  # type: ignore[method-assign]
            "fresh": False,
            "state": "missing",
            "blocker": "pre-run backup artifact is required",
        }
        self.state._manual_live_verification_status = (  # type: ignore[method-assign]
            lambda *_args, **_kwargs: {
                "verified": False,
                "blocker": "manual live proof is required",
            }
        )
        now = utc_now()
        self.state.storage.save_live_execution_audit(
            LiveExecutionAudit(
                id="unresolved-live-audit",
                created_at=now,
                updated_at=now,
                action="buy",
                mint="MintUnresolved",
                amount="0.01",
                status="submitted",
                signer_mode="local_hot_wallet",
                wallet_public_key=self.wallet,
                final_status="submitted",
            )
        )

        result = self._preflight()
        joined = "; ".join(result["blockers"])
        self.assertIn("live execution readiness", joined)
        self.assertIn("recovery debt", joined)
        self.assertIn("pre-run backup", joined)
        self.assertIn("manual live proof", joined)

    def test_mobile_rent_audit_and_backup_never_persist_transaction_blob(self) -> None:
        receipt = self._receipt(
            "rent-redaction",
            action="rent_recovery",
            amount="0.004",
        )
        raw_marker = "RAW_UNSIGNED_MOBILE_RENT_TRANSACTION_MUST_NOT_PERSIST"
        encoded = base64.b64encode(raw_marker.encode()).decode()
        self.state.mobile_treasury_preflight = lambda **_kwargs: {  # type: ignore[method-assign]
            "blockers": [],
            "wallet_public_key": self.wallet,
        }
        self.state.live_rent_recovery_preview = lambda *_args, **_kwargs: (  # type: ignore[method-assign]
            self.fail("mobile execution must not call the persisted browser preview")
        )
        self.state._build_mobile_rent_recovery_transaction = (  # type: ignore[attr-defined]
            lambda *_args, **_kwargs: {
                "unsigned_transaction_base64": encoded,
                "selected_count": 1,
                "recoverable_rent_sol": 0.004,
            }
        )

        result = self.state.execute_mobile_treasury(
            action_id=receipt.id,
            action="rent_recovery",
            source_wallet_public_key=self.wallet,
            address=self.wallet,
            asset="SOL",
            amount=Decimal("0.004"),
            token_accounts=[str(Keypair().pubkey())],
        )

        self.assertEqual(result["status"], "submitted")
        audits = [
            audit
            for audit in self.state.storage.load_live_execution_audits(20)
            if audit.action == "rent_recovery"
        ]
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].signer_mode, "local_hot_wallet")
        serialized_audit = json.dumps(audits[0].to_dict())
        self.assertNotIn(raw_marker, serialized_audit)
        self.assertNotIn(encoded, serialized_audit)
        self.assertNotIn("unsigned_transaction", serialized_audit.lower())

        artifact = self.state.storage.create_backup_artifact()
        backup_bytes = base64.b64decode(str(artifact["database_base64"]))
        self.assertNotIn(raw_marker.encode(), backup_bytes)
        self.assertNotIn(encoded.encode(), backup_bytes)

    def test_confirmed_profit_receipt_terminalizes_bound_audit_and_readiness(
        self,
    ) -> None:
        receipt = self._receipt(
            "profit-confirmed-audit",
            action="profit_sweep",
            amount="0.02",
        )
        self.state.mobile_treasury_preflight = lambda **_kwargs: {  # type: ignore[method-assign]
            "blockers": [],
            "wallet_public_key": self.wallet,
            "profit_sweep_policy": {"sweep_mode": "fixed_sol"},
        }

        result = self.state.execute_mobile_treasury(
            action_id=receipt.id,
            action="profit_sweep",
            source_wallet_public_key=self.wallet,
            address=self.destination,
            asset="SOL",
            amount=Decimal("0.02"),
            token_accounts=[],
        )
        receipt.execution_audit_id = str(result["execution_audit_id"])
        receipt.payload["transaction_signature"] = str(
            result["transaction_signature"]
        )
        self.state.storage.save_mobile_action_receipt(receipt)
        self.state._signature_status = lambda _signature: {  # type: ignore[method-assign]
            "ok": True,
            "err": None,
            "confirmation_status": "confirmed",
        }

        reconciled = self.state.reconcile_mobile_treasury_action(receipt)

        self.assertEqual(reconciled["status"], "confirmed")
        audit = self.state.storage.load_live_execution_audit(
            receipt.execution_audit_id
        )
        self.assertIsNotNone(audit)
        self.assertEqual(audit.status if audit else "", "confirmed")
        self.assertEqual(audit.final_status if audit else "", "confirmed")
        self.assertEqual(
            audit.reconciliation_status if audit else "",
            "matched",
        )
        readiness = self.state._mobile_treasury_readiness(self.wallet)
        self.assertNotIn(
            "recovery debt",
            "; ".join(str(value) for value in readiness["blockers"]),
        )

    def test_backup_preview_and_restore_include_treasury_lifecycle_tables(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            source = Storage(str(Path(directory) / "source.db"))
            target = Storage(str(Path(directory) / "target.db"))
            now = utc_now()
            authorization = MobileDestinationAuthorization(
                id="restore-treasury-authorization",
                payload={
                    "device_id": "restore-device",
                    "action": "withdrawal",
                    "address": self.destination,
                    "asset": "SOL",
                    "max_amount": "0.2",
                    "purpose": "restore proof",
                },
                created_at=now,
                expires_at=now + timedelta(minutes=5),
            )
            source.create_mobile_destination_authorization(authorization)
            with source._connect() as connection:
                connection.execute(
                    """
                    UPDATE mobile_destination_authorizations
                    SET used_at = ?
                    WHERE id = ?
                    """,
                    (now.isoformat(), authorization.id),
                )
            receipt = MobileActionReceipt(
                id="restore-review-required",
                idempotency_key_hash="restore-review-required-hash",
                device_id="restore-device",
                action_type="withdrawal",
                entity_id=authorization.id,
                payload={
                    "source_wallet_public_key": self.wallet,
                    "asset": "SOL",
                    "amount": "0.2",
                },
                status="review_required",
                created_at=now,
                updated_at=now,
            )
            source.reserve_mobile_action_receipt(receipt)
            artifact = source.create_backup_artifact()

            preview = target.preview_restore_artifact(artifact)

            self.assertEqual(preview["risk_level"], "review")
            self.assertIn("mobile_action_receipts", preview["changed_tables"])
            self.assertIn(
                "mobile_destination_authorizations",
                preview["changed_tables"],
            )
            self.assertEqual(
                preview["table_deltas"]["mobile_action_receipts"]["artifact"],
                1,
            )
            target.restore_backup_artifact(artifact)
            restored_receipt = target.load_mobile_action_receipt(receipt.id)
            restored_authorization = (
                target.load_mobile_destination_authorization(authorization.id)
            )
            self.assertEqual(
                restored_receipt.status if restored_receipt else "",
                "review_required",
            )
            self.assertIsNotNone(
                restored_authorization.used_at
                if restored_authorization
                else None
            )

    def test_restore_preview_detects_current_treasury_state_missing_from_artifact(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            artifact_source = Storage(str(Path(directory) / "artifact.db"))
            target = Storage(str(Path(directory) / "target.db"))
            artifact = artifact_source.create_backup_artifact()
            now = utc_now()
            authorization = MobileDestinationAuthorization(
                id="current-only-authorization",
                payload={
                    "device_id": "current-device",
                    "action": "withdrawal",
                    "address": self.destination,
                    "asset": "SOL",
                    "max_amount": "0.2",
                    "purpose": "current unresolved treasury state",
                },
                created_at=now,
                expires_at=now + timedelta(minutes=5),
            )
            target.create_mobile_destination_authorization(authorization)
            target.reserve_mobile_action_receipt(
                MobileActionReceipt(
                    id="current-only-review",
                    idempotency_key_hash="current-only-review-hash",
                    device_id="current-device",
                    action_type="withdrawal",
                    entity_id=authorization.id,
                    payload={
                        "source_wallet_public_key": self.wallet,
                        "asset": "SOL",
                        "amount": "0.2",
                    },
                    status="review_required",
                    created_at=now,
                    updated_at=now,
                )
            )

            preview = target.preview_restore_artifact(artifact)

            self.assertEqual(preview["risk_level"], "review")
            self.assertIn("mobile_action_receipts", preview["changed_tables"])
            self.assertIn(
                "mobile_destination_authorizations",
                preview["changed_tables"],
            )
            self.assertEqual(
                preview["table_deltas"]["mobile_action_receipts"],
                {"current": 1, "artifact": 0, "delta": -1},
            )
            self.assertEqual(
                preview["table_deltas"]["mobile_destination_authorizations"],
                {"current": 1, "artifact": 0, "delta": -1},
            )


if __name__ == "__main__":
    unittest.main()
