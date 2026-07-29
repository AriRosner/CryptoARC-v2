from __future__ import annotations

import json
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.models import utc_now
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
    ) -> dict[str, object]:
        del address, asset
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
        }

    def execute_mobile_treasury(
        self,
        *,
        action_id: str,
        action: str,
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
        self.execute_calls += 1
        return {
            "status": self.execute_status,
            "operator_message": "Treasury request submitted",
            "transaction_signature": "PublicSignature111",
            "action": action,
            "destination": address,
            "asset": asset,
            "amount": str(amount),
            "token_accounts": token_accounts,
        }

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
        address: str | None = None,
        asset: str = "SOL",
        max_amount: Decimal = Decimal("0.25"),
        expires_in_seconds: int = 300,
        purpose: str = "manual profit transfer",
    ) -> dict[str, object]:
        return self.service.authorize_destination(
            desktop_operator=self.desktop_operator,
            device_id=device_id or self.device["id"],
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
        stored.expires_at = utc_now() - timedelta(seconds=1)
        self.storage.save_mobile_destination_authorization(stored)
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
                authorization = self.authorize(purpose=action)
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
                "address": self.destination,
                "asset": "SOL",
                "max_amount": "0.25",
                "expires_in_seconds": 300,
                "purpose": "desktop issue",
            },
        )
        self.assertEqual(desktop.status_code, 200)
        self.assertNotIn("desktop_operator", json.dumps(desktop.json()).lower())


if __name__ == "__main__":
    unittest.main()
