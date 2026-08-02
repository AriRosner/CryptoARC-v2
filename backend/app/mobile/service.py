from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from cryptography.fernet import Fernet

from app.core.models import (
    MobileActionReceipt as StoredMobileActionReceipt,
    MobileDestinationAuthorization,
    MobilePushRegistration,
    new_id,
    utc_now,
)
from app.mobile.contracts import MobileActionStatus, MobileScope


class MobilePushTokenEncryptionUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class _MobileWebSocketTicket:
    device_id: str
    scope: str
    expires_at: float


class MobileCommandCenterService:
    WEBSOCKET_TICKET_TTL_SECONDS = 30
    PUSH_DELIVERY_LEASE_SECONDS = 60
    MAX_WEBSOCKET_TICKETS = 512
    REQUIRED_PREFLIGHT_CHECKS = frozenset(
        {
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
        }
    )
    OPTIONAL_PREFLIGHT_CHECKS = frozenset(
        {"estimated_wallet_spend", "rent_dominance", "wallet_token_balance"}
    )
    TREASURY_ACTIONS = frozenset(
        {"withdrawal", "profit_sweep", "rent_recovery"}
    )
    PUSH_ROUTE_PATTERNS = (
        re.compile(r"^/(?:alerts|diagnostics)$"),
        re.compile(r"^/trade/[A-Za-z0-9][A-Za-z0-9_-]{0,119}$"),
        re.compile(r"^/position/[A-Za-z0-9][A-Za-z0-9_-]{0,119}$"),
    )
    MOBILE_IDENTIFIER_PATTERN = re.compile(
        r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$"
    )
    EXPO_PUSH_TOKEN_PATTERN = re.compile(
        r"^(?:ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]{1,512}\]$"
    )
    DIAGNOSTIC_SENSITIVE_KEY = re.compile(
        r"token|secret|seed|private|signature|pairing|authorization|"
        r"credential|password|cipher|fingerprint|raw_?tx|logs?",
        re.IGNORECASE,
    )
    DIAGNOSTIC_PUBLIC_IDENTIFIER_KEY = re.compile(
        r"wallet|public_?key|address|mint",
        re.IGNORECASE,
    )
    DIAGNOSTIC_PATH_KEY = re.compile(
        r"path|directory|filename",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        state_provider: Callable[[], Any],
        config_provider: Callable[[], Any],
        auth_provider: Callable[[], Any],
        require_dashboard_auth: Callable[..., Any],
        broadcast_snapshot: Callable[[], Awaitable[None]],
        broadcast_mobile_cockpit: Callable[[], Awaitable[None]],
        stop_runtime_tasks: Callable[[], Awaitable[dict[str, object]]],
        push_sender: Callable[
            [str, dict[str, object]], dict[str, object] | bool
        ]
        | None = None,
    ) -> None:
        self._state_provider = state_provider
        self._config_provider = config_provider
        self._auth_provider = auth_provider
        self.require_dashboard_auth = require_dashboard_auth
        self._broadcast_snapshot = broadcast_snapshot
        self._broadcast_mobile_cockpit = broadcast_mobile_cockpit
        self._stop_runtime_tasks = stop_runtime_tasks
        self._monotonic = time.monotonic
        self._ws_ticket_lock = threading.Lock()
        self._ws_tickets: dict[str, _MobileWebSocketTicket] = {}
        self._guarded_action_lock = threading.RLock()
        self._push_sender = push_sender

    @property
    def state(self) -> Any:
        return self._state_provider()

    @property
    def config(self) -> Any:
        return self._config_provider()

    @property
    def auth(self) -> Any:
        return self._auth_provider()

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "artifact_type": "cryptoarc_mobile_health",
            "format_version": 1,
            "server_time": time.time(),
            "dashboard_auth_enabled": self.auth.enabled,
            "dashboard_totp_enabled": self.auth.totp_enabled,
            "mobile_pairing_available": True,
            "websocket_path": "/ws/mobile?ticket=...",
            "private_tunnel_required": True,
        }

    async def start_pairing(self, api_base_url: str, scopes: list[str]) -> dict[str, object]:
        pairing = self.state.create_mobile_pairing(
            api_base_url=api_base_url.strip() or self.config.mobile_public_api_base_url.strip(),
            scopes=scopes,
            ttl_seconds=self.config.mobile_pairing_ttl_seconds,
        )
        pairing["dashboard_auth_enabled"] = self.auth.enabled
        pairing["dashboard_totp_enabled"] = self.auth.totp_enabled
        pairing["pairing_security_note"] = (
            "Dashboard password and TOTP are recommended before pairing mobile devices."
            if not self.auth.enabled or not self.auth.totp_enabled
            else "Pair only over the private tunnel."
        )
        await self._broadcast_mobile_cockpit()
        return pairing

    async def claim_pairing(
        self,
        pairing_id: str,
        code: str,
        device_name: str,
        platform: str,
    ) -> dict[str, object]:
        claimed = self.state.claim_mobile_pairing(
            pairing_id=pairing_id,
            code=code,
            device_name=device_name,
            platform=platform,
        )
        await self._broadcast_mobile_cockpit()
        return claimed

    def devices(self, include_revoked: bool) -> dict[str, object]:
        return {
            "devices": self.state.mobile_devices(include_revoked=include_revoked),
            "pairing_ttl_seconds": self.config.mobile_pairing_ttl_seconds,
            "token_ttl_days": self.state.MOBILE_TOKEN_TTL_DAYS,
        }

    async def revoke_device(self, device_id: str) -> dict[str, object]:
        device = self.state.revoke_mobile_device(device_id)
        await self._broadcast_mobile_cockpit()
        return {"revoked": True, "device": device}

    def cockpit(self, device: dict[str, object]) -> dict[str, object]:
        return self.state.mobile_cockpit(
            self.config.live_trading_enabled,
            local_auth_enabled=self.auth.enabled,
            device=device,
        )

    def portfolio(
        self,
        *,
        device: dict[str, object],
        timeframe: str,
    ) -> dict[str, object]:
        del device
        return self.state.mobile_portfolio(timeframe)

    def positions(self, *, device: dict[str, object]) -> dict[str, object]:
        del device
        return self.state.mobile_positions()

    def position(
        self,
        *,
        device: dict[str, object],
        position_id: str,
    ) -> dict[str, object]:
        del device
        payload = self.state.mobile_position(position_id)
        if payload is None:
            raise LookupError("Mobile position not found")
        return payload

    def wallet(self, *, device: dict[str, object]) -> dict[str, object]:
        del device
        return self.state.mobile_wallet()

    def wallet_transactions(
        self,
        *,
        device: dict[str, object],
    ) -> dict[str, object]:
        del device
        return self.state.mobile_wallet_transactions()

    def destinations(
        self,
        *,
        device: dict[str, object],
    ) -> dict[str, object]:
        device_id = self._device_id(device)
        authorizations = self.state.storage.load_mobile_destination_authorizations(
            device_id=device_id,
            limit=100,
        )
        return {
            "artifact_type": "cryptoarc_mobile_destinations",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "destinations": [
                authorization.to_public_dict()
                for authorization in authorizations
            ],
        }

    def authorize_destination(
        self,
        *,
        desktop_operator: dict[str, object],
        device_id: str,
        action: str,
        address: str,
        asset: str,
        max_amount: Any,
        expires_in_seconds: int,
        purpose: str,
    ) -> dict[str, object]:
        if not desktop_operator or not desktop_operator.get("authenticated"):
            raise ValueError("Desktop authentication is required")
        clean_device_id = device_id.strip()
        clean_action = action.strip().lower()
        clean_address = address.strip()
        clean_asset = asset.strip().upper()
        clean_purpose = purpose.strip()
        maximum = self._decimal(max_amount, "maximum amount")
        if not clean_device_id:
            raise ValueError("Mobile device binding is required")
        if clean_action not in self.TREASURY_ACTIONS:
            raise ValueError("Destination authorization action is invalid")
        if (
            len(clean_address) < 32
            or len(clean_address) > 100
            or not re.fullmatch(r"[A-Za-z0-9]+", clean_address)
        ):
            raise ValueError("Destination address is invalid")
        if not re.fullmatch(r"[A-Z0-9_-]{1,16}", clean_asset):
            raise ValueError("Destination asset is invalid")
        if not clean_purpose:
            raise ValueError("Destination purpose is required")
        ttl_seconds = int(expires_in_seconds)
        if ttl_seconds < 1 or ttl_seconds > 900:
            raise ValueError(
                "Destination authorization expiry must be between 1 and 900 seconds"
            )
        now = utc_now()
        authorization = MobileDestinationAuthorization(
            id=new_id("destinationauth"),
            payload={
                "device_id": clean_device_id,
                "action": clean_action,
                "address": clean_address,
                "asset": clean_asset,
                "max_amount": str(maximum),
                "purpose": clean_purpose,
                "issued_by": str(desktop_operator.get("id") or "desktop"),
            },
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        self.state.storage.create_mobile_destination_authorization(authorization)
        return authorization.to_public_dict()

    def preview_withdrawal(self, **kwargs: Any) -> dict[str, object]:
        return self._preview_treasury(action="withdrawal", **kwargs)

    def preview_profit_sweep(self, **kwargs: Any) -> dict[str, object]:
        return self._preview_treasury(action="profit_sweep", **kwargs)

    def preview_rent_recovery(self, **kwargs: Any) -> dict[str, object]:
        return self._preview_treasury(action="rent_recovery", **kwargs)

    def request_withdrawal(self, **kwargs: Any) -> dict[str, object]:
        return self._request_treasury(action="withdrawal", **kwargs)

    def request_profit_sweep(self, **kwargs: Any) -> dict[str, object]:
        return self._request_treasury(action="profit_sweep", **kwargs)

    def request_rent_recovery(self, **kwargs: Any) -> dict[str, object]:
        return self._request_treasury(action="rent_recovery", **kwargs)

    def _preview_treasury(
        self,
        *,
        action: str,
        device: dict[str, object],
        authorization_id: str,
        address: str,
        asset: str,
        amount: Any,
        token_accounts: list[str] | None = None,
    ) -> dict[str, object]:
        device_id = self._device_id(device)
        clean_address = address.strip()
        clean_asset = asset.strip().upper()
        numeric_amount = self._decimal(amount, "amount")
        clean_accounts = self._token_accounts(token_accounts or [])
        if not bool(self.config.live_trading_enabled):
            raise ValueError("Live treasury environment is disabled")
        authorization = self._require_destination_authorization(
            authorization_id=authorization_id,
            device_id=device_id,
            action=action,
            address=clean_address,
            asset=clean_asset,
            amount=numeric_amount,
        )
        preflight = self.state.mobile_treasury_preflight(
            action=action,
            address=clean_address,
            asset=clean_asset,
            amount=numeric_amount,
            token_accounts=clean_accounts,
        )
        blockers = [str(value) for value in preflight.get("blockers", [])]
        if blockers:
            raise ValueError("; ".join(blockers))
        now = utc_now()
        expires_at = min(authorization.expires_at, now + timedelta(seconds=60))
        preview_id = new_id("treasurypreview")
        preview = {
            "preview_id": preview_id,
            "action": action,
            "device_id": device_id,
            "address": clean_address,
            "asset": clean_asset,
            "amount": str(numeric_amount),
            "authorization_id": authorization.id,
            "source_wallet_public_key": str(
                preflight.get("wallet_public_key") or ""
            ),
            "expected_fee_sol": str(
                preflight.get("expected_fee_sol") or "0"
            ),
            "remaining_balance_sol": str(
                preflight.get("remaining_balance_sol") or "0"
            ),
            "expires_at": expires_at.isoformat(),
            "token_accounts": clean_accounts,
            "created_at": now.isoformat(),
        }
        self.state.storage.attach_mobile_destination_preview(
            authorization.id,
            preview,
        )
        return {
            "preview_id": preview_id,
            "action": action,
            "destination": clean_address,
            "asset": clean_asset,
            "amount": numeric_amount,
            "expected_fee_sol": Decimal(preview["expected_fee_sol"]),
            "remaining_balance_sol": Decimal(
                preview["remaining_balance_sol"]
            ),
            "authorization_id": authorization.id,
            "expires_at": expires_at.isoformat(),
            "warnings": [
                str(value) for value in preflight.get("warnings", [])
            ],
            "token_accounts": clean_accounts,
            "source_wallet_public_key": preview["source_wallet_public_key"],
            "purpose": str(authorization.payload.get("purpose") or ""),
        }

    def _request_treasury(
        self,
        *,
        action: str,
        device: dict[str, object],
        authorization_id: str,
        preview_id: str,
        address: str,
        asset: str,
        amount: Any,
        idempotency_key: str,
        token_accounts: list[str] | None = None,
    ) -> dict[str, object]:
        device_id = self._device_id(device)
        clean_address = address.strip()
        clean_asset = asset.strip().upper()
        numeric_amount = self._decimal(amount, "amount")
        clean_accounts = self._token_accounts(token_accounts or [])
        fingerprint = self._request_fingerprint(
            {
                "action": action,
                "authorization_id": authorization_id,
                "preview_id": preview_id,
                "address": clean_address,
                "asset": clean_asset,
                "amount": str(numeric_amount),
                "token_accounts": clean_accounts,
            }
        )
        with self._guarded_action_lock:
            existing = self._existing_idempotent_receipt(
                device_id=device_id,
                action_type=action,
                entity_id=authorization_id,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
            if existing:
                return self._receipt_public(existing)
            if not bool(self.config.live_trading_enabled):
                raise ValueError("Live treasury environment is disabled")
            if not preview_id:
                raise ValueError("Treasury preview is missing")
            self._require_destination_authorization(
                authorization_id=authorization_id,
                device_id=device_id,
                action=action,
                address=clean_address,
                asset=clean_asset,
                amount=numeric_amount,
            )
            preflight = self.state.mobile_treasury_preflight(
                action=action,
                address=clean_address,
                asset=clean_asset,
                amount=numeric_amount,
                token_accounts=clean_accounts,
            )
            blockers = [str(value) for value in preflight.get("blockers", [])]
            if blockers:
                raise ValueError("; ".join(blockers))
            now = utc_now()
            source_wallet_public_key = str(
                preflight.get("wallet_public_key") or ""
            )
            action_id = self._action_id(idempotency_key)
            receipt = StoredMobileActionReceipt(
                id=action_id,
                idempotency_key_hash=self._idempotency_hash(
                    device_id, idempotency_key
                ),
                device_id=device_id,
                action_type=action,
                entity_id=authorization_id,
                payload={
                    "request_fingerprint": fingerprint,
                    "authorization_id": authorization_id,
                    "preview_id": preview_id,
                    "address": clean_address,
                    "asset": clean_asset,
                    "amount": str(numeric_amount),
                    "expected_fee_sol": str(
                        preflight.get("expected_fee_sol") or "0"
                    ),
                    "source_wallet_public_key": source_wallet_public_key,
                    "token_accounts": clean_accounts,
                    "operator_message": "Treasury request pending",
                    "reconcile_after_ms": 1000,
                    "submitted_at": now.isoformat(),
                    "dispatch_claimed_at": now.isoformat(),
                },
                status=MobileActionStatus.PENDING.value,
                created_at=now,
                updated_at=now,
            )
            receipt, created = self.state.storage.reserve_mobile_treasury_action(
                receipt,
                authorization_id=authorization_id,
                preview_id=preview_id,
                action=action,
                address=clean_address,
                asset=clean_asset,
                amount=str(numeric_amount),
                token_accounts=clean_accounts,
                source_wallet_public_key=source_wallet_public_key,
                profit_sweep_policy=(
                    preflight.get("profit_sweep_policy")
                    if isinstance(
                        preflight.get("profit_sweep_policy"),
                        dict,
                    )
                    else {}
                ),
            )
            if not created:
                return self._verify_existing_receipt(
                    receipt,
                    device_id=device_id,
                    action_type=action,
                    entity_id=authorization_id,
                    request_fingerprint=fingerprint,
                )
            try:
                result = self.state.execute_mobile_treasury(
                    action_id=action_id,
                    action=action,
                    source_wallet_public_key=source_wallet_public_key,
                    address=clean_address,
                    asset=clean_asset,
                    amount=numeric_amount,
                    token_accounts=clean_accounts,
                )
                status, message = self._treasury_receipt_status(result)
                transaction_signature = str(
                    result.get("transaction_signature")
                    or result.get("signature")
                    or ""
                )
                if transaction_signature:
                    receipt.payload["transaction_signature"] = (
                        transaction_signature
                    )
                execution_audit_id = str(
                    result.get("execution_audit_id") or ""
                )
                if execution_audit_id:
                    receipt.execution_audit_id = execution_audit_id
            except Exception:
                status = MobileActionStatus.VERIFYING.value
                message = "Verifying treasury outcome"
            receipt.status = status
            receipt.updated_at = utc_now()
            receipt.payload["operator_message"] = message
            self.state.storage.save_mobile_action_receipt(receipt)
            return self._receipt_public(receipt)

    def _require_destination_authorization(
        self,
        *,
        authorization_id: str,
        device_id: str,
        action: str,
        address: str,
        asset: str,
        amount: Decimal,
    ) -> MobileDestinationAuthorization:
        authorization = self.state.storage.load_mobile_destination_authorization(
            authorization_id
        )
        if authorization is None:
            raise LookupError("Mobile destination authorization not found")
        if authorization.used_at:
            raise ValueError("Destination authorization is already used")
        if authorization.expires_at <= utc_now():
            raise ValueError("Destination authorization expired")
        payload = authorization.payload
        if str(payload.get("device_id") or "") != device_id:
            raise ValueError("Destination authorization device binding does not match")
        if str(payload.get("action") or "") != action:
            raise ValueError("Destination authorization action binding does not match")
        if str(payload.get("address") or "") != address:
            raise ValueError("Destination authorization address binding does not match")
        if str(payload.get("asset") or "") != asset:
            raise ValueError("Destination authorization asset binding does not match")
        maximum = self._decimal(payload.get("max_amount"), "maximum amount")
        if amount > maximum:
            raise ValueError("Destination authorization maximum amount exceeded")
        return authorization

    @staticmethod
    def _token_accounts(values: list[str]) -> list[str]:
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Treasury token account binding contains duplicates")
        if len(cleaned) > 64:
            raise ValueError("Treasury token account selection is too large")
        return cleaned

    def trades(self, *, device: dict[str, object]) -> dict[str, object]:
        del device
        rows = []
        for intent in self.state.storage.load_live_intents(200):
            try:
                rows.append(self._trade_detail(intent))
            except (LookupError, ValueError):
                continue
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return {
            "artifact_type": "cryptoarc_mobile_trades",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "trades": rows,
        }

    def trade(
        self,
        *,
        device: dict[str, object],
        intent_id: str,
    ) -> dict[str, object]:
        del device
        intent = self.state.storage.load_live_intent(intent_id)
        if intent is None:
            raise LookupError("Mobile trade intent not found")
        return self._trade_detail(intent)

    def validate_trade(
        self,
        *,
        device: dict[str, object],
        intent_id: str,
        expected_version: int,
        draft: Any,
        escalation_acknowledged: bool,
    ) -> dict[str, object]:
        del device
        intent = self.state.storage.load_live_intent(intent_id)
        if intent is None:
            raise LookupError("Mobile trade intent not found")
        review = self._trade_validation(
            intent=intent,
            expected_version=expected_version,
            draft=draft,
        )
        review["escalation_acknowledged"] = bool(escalation_acknowledged)
        review["valid"] = not review["blockers"] and (
            not review["requires_escalation"] or bool(escalation_acknowledged)
        )
        return review

    def approve_trade(
        self,
        *,
        device: dict[str, object],
        intent_id: str,
        expected_version: int,
        draft: Any,
        idempotency_key: str,
        escalation_acknowledged: bool = False,
    ) -> dict[str, object]:
        return self._approve_prepared_intent(
            device=device,
            intent_id=intent_id,
            expected_version=expected_version,
            draft=draft,
            idempotency_key=idempotency_key,
            escalation_acknowledged=escalation_acknowledged,
            action_type="trade_approve",
            entity_id=intent_id,
        )

    def reject_trade(
        self,
        *,
        device: dict[str, object],
        intent_id: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("Rejection reason is required")
        device_id = self._device_id(device)
        fingerprint = self._request_fingerprint(
            {
                "action": "trade_reject",
                "intent_id": intent_id,
                "expected_version": expected_version,
                "reason": clean_reason,
            }
        )
        with self._guarded_action_lock:
            existing = self._existing_idempotent_receipt(
                device_id=device_id,
                action_type="trade_reject",
                entity_id=intent_id,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
            if existing:
                if existing.status == MobileActionStatus.PENDING.value:
                    existing = self._reconcile_local_mobile_action(existing)
                return self._receipt_public(existing)
            intent = self.state.storage.load_live_intent(intent_id)
            if intent is None:
                raise LookupError("Mobile trade intent not found")
            if int(getattr(intent, "version", 1)) != int(expected_version):
                raise ValueError("Trade intent version conflict")
            if str(getattr(intent, "status", "")) in {
                "submitted",
                "executed",
                "confirmed",
                "reconciled",
            }:
                raise ValueError("Submitted trade intent cannot be rejected")
            now = utc_now()
            receipt, created = (
                self.state.storage.apply_mobile_trade_rejection(
                    StoredMobileActionReceipt(
                        id=self._action_id(idempotency_key),
                        idempotency_key_hash=self._idempotency_hash(
                            device_id, idempotency_key
                        ),
                        device_id=device_id,
                        action_type="trade_reject",
                        entity_id=intent_id,
                        payload={
                            "request_fingerprint": fingerprint,
                            "operator_message": "Trade intent rejected",
                            "reconcile_after_ms": 1000,
                            "submitted_at": now.isoformat(),
                            "expected_version": expected_version,
                            "reason": clean_reason,
                        },
                        status=MobileActionStatus.CANCELLED.value,
                        created_at=now,
                        updated_at=now,
                    ),
                    expected_version=expected_version,
                    reason=clean_reason,
                )
            )
            if not created:
                return self._verify_existing_receipt(
                    receipt,
                    device_id=device_id,
                    action_type="trade_reject",
                    entity_id=intent_id,
                    request_fingerprint=fingerprint,
                )
            return self._receipt_public(receipt)

    def adjust_position_exit(
        self,
        *,
        device: dict[str, object],
        position_id: str,
        expected_version: int,
        stop_pct: Any,
        target_pct: Any,
        escalation_acknowledged: bool,
        idempotency_key: str,
    ) -> dict[str, object]:
        stop = self._decimal(stop_pct, "stop_pct")
        target = self._decimal(target_pct, "target_pct")
        if stop > Decimal("100") or target > Decimal("100"):
            raise ValueError("Exit adjustment is outside backend bounds")
        escalation_reasons = []
        if stop > Decimal(str(self.state.settings.stop_loss_pct)):
            escalation_reasons.append("Stop is wider than the configured strategy stop")
        if target > Decimal(str(self.state.settings.take_profit_pct)):
            escalation_reasons.append("Target is above the configured strategy target")
        if escalation_reasons and not escalation_acknowledged:
            raise ValueError("Risk escalation acknowledgement is required")
        device_id = self._device_id(device)
        fingerprint = self._request_fingerprint(
            {
                "action": "position_adjust_exit",
                "position_id": position_id,
                "expected_version": expected_version,
                "stop_pct": str(stop),
                "target_pct": str(target),
                "escalation_acknowledged": escalation_acknowledged,
            }
        )
        with self._guarded_action_lock:
            existing = self._existing_idempotent_receipt(
                device_id=device_id,
                action_type="position_adjust_exit",
                entity_id=position_id,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
            if existing:
                if existing.status == MobileActionStatus.PENDING.value:
                    existing = self._reconcile_local_mobile_action(existing)
                return self._receipt_public(existing)
            position = self.state.storage.load_live_ledger_position(position_id)
            if position is None:
                raise LookupError("Mobile live position not found")
            if int(getattr(position, "version", 1)) != int(expected_version):
                raise ValueError("Position version conflict")
            if (
                str(getattr(position, "status", "")) != "open"
                or float(getattr(position, "token_balance", 0) or 0) <= 0
            ):
                raise ValueError(
                    "Only an open live position can change exit controls"
                )
            now = utc_now()
            receipt, created = (
                self.state.storage.apply_mobile_position_exit_adjustment(
                    StoredMobileActionReceipt(
                        id=self._action_id(idempotency_key),
                        idempotency_key_hash=self._idempotency_hash(
                            device_id, idempotency_key
                        ),
                        device_id=device_id,
                        action_type="position_adjust_exit",
                        entity_id=position_id,
                        payload={
                            "request_fingerprint": fingerprint,
                            "operator_message": "Exit controls updated",
                            "reconcile_after_ms": 500,
                            "submitted_at": now.isoformat(),
                            "expected_version": expected_version,
                            "stop_pct": str(stop),
                            "target_pct": str(target),
                        },
                        status=MobileActionStatus.CONFIRMED.value,
                        created_at=now,
                        updated_at=now,
                    ),
                    expected_version=expected_version,
                    stop_pct=float(stop),
                    target_pct=float(target),
                )
            )
            if not created:
                return self._verify_existing_receipt(
                    receipt,
                    device_id=device_id,
                    action_type="position_adjust_exit",
                    entity_id=position_id,
                    request_fingerprint=fingerprint,
                )
            return self._receipt_public(receipt)

    def close_position(
        self,
        *,
        device: dict[str, object],
        position_id: str,
        position_version: int,
        intent_id: str,
        expected_version: int,
        draft: Any,
        escalation_acknowledged: bool,
        idempotency_key: str,
    ) -> dict[str, object]:
        position = self.state.storage.load_live_ledger_position(position_id)
        if position is None:
            raise LookupError("Mobile live position not found")
        if int(getattr(position, "version", 1)) != int(position_version):
            raise ValueError("Position version conflict")
        if (
            str(getattr(position, "status", "")) != "open"
            or float(getattr(position, "token_balance", 0) or 0) <= 0
            or str(getattr(position, "reconciliation_status", ""))
            == "needs_review"
        ):
            raise ValueError("Position is not eligible for a guarded full close")
        intent = self.state.storage.load_live_intent(intent_id)
        if intent is None:
            raise LookupError("Prepared close intent not found")
        if (
            str(getattr(intent, "action", "")) != "sell"
            or str(getattr(intent, "amount", "")) != "100%"
            or not bool(getattr(intent, "generated_from_position", False))
            or str(getattr(intent, "generated_position_id", "")) != position_id
            or int(getattr(intent, "generated_position_version", 0))
            != int(position_version)
            or abs(
                float(
                    getattr(intent, "generated_position_token_balance", 0)
                    or 0
                )
                - float(getattr(position, "token_balance", 0) or 0)
            )
            > 1e-12
            or str(getattr(intent, "mint", "")) != str(position.mint)
            or str(getattr(intent, "wallet_public_key", ""))
            != str(position.wallet_public_key)
        ):
            raise ValueError("Prepared close intent does not match the position")
        return self._approve_prepared_intent(
            device=device,
            intent_id=intent_id,
            expected_version=expected_version,
            draft=draft,
            idempotency_key=idempotency_key,
            escalation_acknowledged=escalation_acknowledged,
            action_type="position_close",
            entity_id=position_id,
            position_binding={
                "position_id": position_id,
                "position_version": position_version,
                "token_balance": float(position.token_balance),
            },
        )

    def action(
        self,
        *,
        device: dict[str, object],
        action_id: str,
    ) -> dict[str, object]:
        receipt = self.state.storage.load_mobile_action_receipt(action_id)
        if receipt is None or receipt.device_id != self._device_id(device):
            raise LookupError("Mobile action receipt not found")
        audit_id = str(
            receipt.execution_audit_id
            or receipt.payload.get("audit_id")
            or ""
        )
        if (
            receipt.action_type not in self.TREASURY_ACTIONS
            and audit_id
            and receipt.status
            in {
                MobileActionStatus.PENDING.value,
                MobileActionStatus.VERIFYING.value,
                MobileActionStatus.REVIEW_REQUIRED.value,
            }
        ):
            audit = self.state.storage.load_live_execution_audit(audit_id)
            if audit is not None and str(audit.status) in {
                "submitting",
                "submitted",
            }:
                try:
                    result = self.state.recover_live_audit(audit_id)
                except Exception:
                    result = audit.to_dict()
            elif audit is not None:
                result = audit.to_dict()
            else:
                result = {}
            status, message = self._receipt_status_from_audit(result)
            receipt.status = status
            receipt.updated_at = utc_now()
            receipt.payload["operator_message"] = message
            self.state.storage.save_mobile_action_receipt(receipt)
        elif (
            receipt.action_type in self.TREASURY_ACTIONS
            and receipt.status
            in {
                MobileActionStatus.PENDING.value,
                MobileActionStatus.VERIFYING.value,
                MobileActionStatus.REVIEW_REQUIRED.value,
            }
        ):
            try:
                result = self.state.reconcile_mobile_treasury_action(receipt)
                status, message = self._treasury_receipt_status(result)
            except Exception:
                status = MobileActionStatus.REVIEW_REQUIRED.value
                message = "Treasury outcome requires operator review"
            receipt.status = status
            receipt.updated_at = utc_now()
            receipt.payload["operator_message"] = message
            self.state.storage.save_mobile_action_receipt(receipt)
        elif receipt.status == MobileActionStatus.PENDING.value:
            receipt = self._reconcile_local_mobile_action(receipt)
        return self._receipt_public(receipt)

    def _reconcile_local_mobile_action(
        self,
        receipt: StoredMobileActionReceipt,
    ) -> StoredMobileActionReceipt:
        return self.state.storage.reconcile_mobile_local_action(receipt.id)

    def _approve_prepared_intent(
        self,
        *,
        device: dict[str, object],
        intent_id: str,
        expected_version: int,
        draft: Any,
        idempotency_key: str,
        escalation_acknowledged: bool,
        action_type: str,
        entity_id: str,
        position_binding: dict[str, object] | None = None,
    ) -> dict[str, object]:
        device_id = self._device_id(device)
        draft_payload = self._draft_payload(draft)
        fingerprint = self._request_fingerprint(
            {
                "action": action_type,
                "entity_id": entity_id,
                "intent_id": intent_id,
                "expected_version": expected_version,
                "draft": draft_payload,
                "escalation_acknowledged": escalation_acknowledged,
            }
        )
        with self._guarded_action_lock:
            existing = self._existing_idempotent_receipt(
                device_id=device_id,
                action_type=action_type,
                entity_id=entity_id,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
            if existing:
                return self._receipt_public(existing)
            validation = self.validate_trade(
                device=device,
                intent_id=intent_id,
                expected_version=expected_version,
                draft=draft_payload,
                escalation_acknowledged=escalation_acknowledged,
            )
            blockers = [str(value) for value in validation["blockers"]]
            if blockers:
                raise ValueError("; ".join(blockers))
            if validation["requires_escalation"] and not escalation_acknowledged:
                raise ValueError("Risk escalation acknowledgement is required")
            intent = self.state.storage.load_live_intent(intent_id)
            audit_id = str(getattr(intent, "audit_id", ""))
            now = utc_now()
            action_id = self._action_id(idempotency_key)
            authorization = {
                "action_id": action_id,
                "stop_pct": draft_payload["stop_pct"],
                "target_pct": draft_payload["target_pct"],
            }
            stored_receipt = StoredMobileActionReceipt(
                id=action_id,
                idempotency_key_hash=self._idempotency_hash(
                    device_id, idempotency_key
                ),
                device_id=device_id,
                action_type=action_type,
                entity_id=entity_id,
                payload={
                    "request_fingerprint": fingerprint,
                    "audit_id": audit_id,
                    "intent_id": intent_id,
                    "intent_version": expected_version,
                    "operator_message": "Authorization accepted",
                    "reconcile_after_ms": 1000,
                    "submitted_at": now.isoformat(),
                    "escalation_reasons": validation["escalation_reasons"],
                },
                status=MobileActionStatus.PENDING.value,
                created_at=now,
                updated_at=now,
                execution_audit_id=audit_id,
            )
            receipt, created = self.state.storage.reserve_mobile_execution_action(
                stored_receipt,
                audit_id=audit_id,
                intent_id=intent_id,
                expected_intent_version=expected_version,
                guarded_authorization=authorization,
                position_binding=position_binding,
            )
            if not created:
                return self._verify_existing_receipt(
                    receipt,
                    device_id=device_id,
                    action_type=action_type,
                    entity_id=entity_id,
                    request_fingerprint=fingerprint,
                )
            try:
                result = self.state.live_submit(
                    audit_id,
                    "",
                    guarded_action_id=receipt.id,
                )
                status, message = self._receipt_status_from_audit(result)
            except (TimeoutError, ConnectionError, OSError):
                status = MobileActionStatus.VERIFYING.value
                message = "Verifying outcome"
            except Exception as exc:
                audit = self.state.storage.load_live_execution_audit(audit_id)
                if audit is not None and (
                    str(audit.status)
                    in {"submitting", "submitted", "needs_review"}
                    or bool(audit.transaction_signature)
                ):
                    status = MobileActionStatus.VERIFYING.value
                    message = "Verifying outcome"
                else:
                    status = MobileActionStatus.FAILED.value
                    message = f"Authorization failed: {exc}"
            receipt.status = status
            receipt.updated_at = utc_now()
            receipt.payload["operator_message"] = message
            self.state.storage.save_mobile_action_receipt(receipt)
            return self._receipt_public(receipt)

    def _trade_detail(self, intent: Any) -> dict[str, object]:
        version = int(getattr(intent, "version", 1))
        audit = self.state.storage.load_live_execution_audit(
            str(getattr(intent, "audit_id", ""))
        )
        quote = audit.quote if audit is not None and isinstance(audit.quote, dict) else {}
        simulation = (
            audit.simulation
            if audit is not None and isinstance(audit.simulation, dict)
            else {}
        )
        default_draft = {
            "amount": str(getattr(intent, "amount", "0")),
            "slippage_pct": str(quote.get("slippage_pct") or "0"),
            "stop_pct": str(self.state.settings.stop_loss_pct),
            "target_pct": str(self.state.settings.take_profit_pct),
        }
        validation = self._trade_validation(
            intent=intent,
            expected_version=version,
            draft=default_draft,
        )
        expires_at = quote.get("expires_at") or getattr(intent, "expires_at", None)
        return {
            "id": str(getattr(intent, "id", "")),
            "version": version,
            "action": str(getattr(intent, "action", "")),
            "symbol": str(getattr(intent, "symbol", "")),
            "mint": str(getattr(intent, "mint", "")),
            "amount": str(getattr(intent, "amount", "")),
            "status": str(getattr(intent, "status", "")),
            "reason": str(getattr(intent, "reason", "")),
            "source": str(getattr(intent, "source", "")),
            "updated_at": self._iso(getattr(intent, "updated_at", None)),
            "expires_at": self._iso(expires_at),
            "quote": {
                "status": str(quote.get("status") or ""),
                "slippage_pct": float(quote.get("slippage_pct") or 0),
                "expires_at": self._iso(quote.get("expires_at")),
                "stale": self._quote_is_stale(quote),
            },
            "simulation": {
                "status": str(simulation.get("status") or ""),
                "ok": simulation.get("ok") is True,
                "warning": str(simulation.get("warning") or ""),
                "error": str(simulation.get("error") or ""),
            },
            "default_draft": default_draft,
            "limits": validation["limits"],
            "blockers": validation["blockers"],
            "escalation_reasons": validation["escalation_reasons"],
            "requires_escalation": validation["requires_escalation"],
            "allowed_actions": {
                "approve": not validation["blockers"],
                "reject": str(getattr(intent, "status", ""))
                not in {"submitted", "executed", "confirmed", "reconciled", "cancelled"},
            },
        }

    def _trade_validation(
        self,
        *,
        intent: Any,
        expected_version: int,
        draft: Any,
    ) -> dict[str, object]:
        payload = self._draft_payload(draft)
        amount, amount_is_full_close = self._prepared_amount(
            payload["amount"],
            action=str(getattr(intent, "action", "")),
            label="amount",
        )
        slippage = self._decimal(payload["slippage_pct"], "slippage_pct")
        stop = (
            self._decimal(payload["stop_pct"], "stop_pct")
            if payload["stop_pct"] is not None
            else None
        )
        target = (
            self._decimal(payload["target_pct"], "target_pct")
            if payload["target_pct"] is not None
            else None
        )
        audit = self.state.storage.load_live_execution_audit(
            str(getattr(intent, "audit_id", ""))
        )
        quote = audit.quote if audit is not None and isinstance(audit.quote, dict) else {}
        simulation = (
            audit.simulation
            if audit is not None and isinstance(audit.simulation, dict)
            else {}
        )
        prepared_amount, prepared_is_full_close = self._prepared_amount(
            getattr(intent, "amount", "0"),
            action=str(getattr(intent, "action", "")),
            label="prepared amount",
        )
        prepared_slippage = self._decimal(
            quote.get("slippage_pct") or "0", "prepared slippage"
        )
        amount_cap = Decimal(str(self.state.settings.live_max_trade_sol))
        slippage_cap = Decimal(str(self.state.settings.live_max_slippage_pct))
        limits = {
            "amount": {
                "min": float(prepared_amount),
                "max": float(prepared_amount),
                "unit": "SOL"
                if bool(getattr(intent, "denominated_in_sol", False))
                else "percent",
            },
            "slippage_pct": {
                "min": float(prepared_slippage),
                "max": float(prepared_slippage),
            },
            "stop_pct": {"min": 1.0, "max": 100.0},
            "target_pct": {"min": 1.0, "max": 100.0},
        }
        blockers: list[str] = []
        if int(getattr(intent, "version", 1)) != int(expected_version):
            blockers.append("Trade intent version conflict")
        if (
            amount != prepared_amount
            or amount_is_full_close != prepared_is_full_close
        ):
            blockers.append("Trade amount must match the prepared intent bound")
        if amount > amount_cap and str(getattr(intent, "action", "")) == "buy":
            blockers.append("Trade amount exceeds the live size limit")
        if slippage != prepared_slippage:
            blockers.append("Slippage must match the prepared quote bound")
        if slippage > slippage_cap:
            blockers.append("Slippage exceeds the live limit")
        if stop is None or target is None:
            blockers.append(
                "Guarded action requires both bounded stop and target controls"
            )
        if stop is not None and stop > Decimal("100"):
            blockers.append("Stop is outside the backend bound")
        if target is not None and target > Decimal("100"):
            blockers.append("Target is outside the backend bound")
        if not bool(self.config.live_trading_enabled):
            blockers.append("LIVE_TRADING_ENABLED is false")
        if bool(self.state.settings.kill_switch_enabled):
            blockers.append("manual kill switch enabled")
        if not bool(self.state.settings.live_active_backend_armed):
            blockers.append("no active backend is armed")
        if (
            str(self.state.settings.live_signer_mode)
            != str(getattr(intent, "signer_mode", ""))
            or str(self.state.settings.live_active_wallet_public_key)
            != str(getattr(intent, "wallet_public_key", ""))
        ):
            blockers.append("prepared intent does not match the armed backend")
        if str(getattr(intent, "status", "")) != "simulated":
            blockers.append("prepared intent is not in simulated state")
        if bool(getattr(intent, "stale", False)):
            blockers.append("prepared intent is stale")
        intent_expiry = getattr(intent, "expires_at", None)
        if self._is_expired(intent_expiry):
            blockers.append("prepared intent has expired")
        if audit is None or str(getattr(audit, "intent_id", "")) != str(
            getattr(intent, "id", "")
        ):
            blockers.append("prepared intent is missing its execution audit")
        elif (
            str(audit.action) != str(getattr(intent, "action", ""))
            or str(audit.mint) != str(getattr(intent, "mint", ""))
            or str(audit.amount) != str(getattr(intent, "amount", ""))
            or str(audit.signer_mode) != str(getattr(intent, "signer_mode", ""))
            or str(audit.wallet_public_key)
            != str(getattr(intent, "wallet_public_key", ""))
        ):
            blockers.append("prepared execution audit does not match the intent")
        elif (
            str(getattr(audit, "status", "")) != "simulated"
            or str(getattr(audit, "final_status", "")) != "simulated"
            or bool(str(getattr(audit, "guarded_action_id", "") or ""))
        ):
            blockers.append(
                "prepared execution audit is not exactly simulated or is already claimed"
            )
        if not quote or str(quote.get("status") or "") != "ready":
            blockers.append("prepared quote is not ready")
        if bool(quote.get("shadow_only")):
            blockers.append("shadow-only quote cannot be authorized")
        if not str(quote.get("unsigned_transaction_base64") or "").strip():
            blockers.append("prepared quote is missing transaction material")
        if self._quote_is_stale(quote):
            blockers.append("prepared quote is stale or expired")
        if simulation.get("ok") is not True or str(simulation.get("status") or "") != "ok":
            blockers.append("successful prepared simulation is required")
        blockers.extend(self._preflight_inventory_blockers(audit))
        signer = self.state.signer_status(
            str(getattr(intent, "signer_mode", "")),
            str(getattr(intent, "wallet_public_key", "")),
        )
        if (
            not signer.get("connected")
            or not signer.get("healthy")
            or not signer.get("can_sign")
            or not signer.get("can_unattended_sign")
        ):
            blockers.append("active signer is not ready for guarded submission")
        if (
            str(getattr(intent, "signer_mode", "")) == "local_signer_daemon"
            and signer.get("ready_to_submit") is not True
        ):
            blockers.append("local signer is not ready to submit")
        if str(getattr(intent, "signer_mode", "")) == "browser_wallet":
            blockers.append("browser-wallet intents cannot be authorized from mobile")
        if hasattr(self.state, "mobile_live_execution_blockers"):
            blockers.extend(self.state.mobile_live_execution_blockers(intent))
        else:
            blockers.extend(
                self.state._live_execution_blockers(
                    bool(self.config.live_trading_enabled),
                    str(getattr(intent, "action", "")),
                    str(getattr(intent, "wallet_public_key", "")),
                    str(getattr(intent, "signer_mode", "")),
                    autonomous=True,
                )
            )
        escalation_reasons = []
        if stop is not None and stop > Decimal(str(self.state.settings.stop_loss_pct)):
            escalation_reasons.append(
                "Stop is wider than the configured strategy stop"
            )
        if (
            target is not None
            and target > Decimal(str(self.state.settings.take_profit_pct))
        ):
            escalation_reasons.append(
                "Target is above the configured strategy target"
            )
        if (
            str(getattr(intent, "action", "")) == "buy"
            and amount_cap > 0
            and amount >= amount_cap * Decimal("0.75")
        ):
            escalation_reasons.append("Trade size is near the configured live cap")
        if slippage_cap > 0 and slippage >= slippage_cap * Decimal("0.75"):
            escalation_reasons.append(
                "Slippage is near the configured live cap"
            )
        return {
            "intent_id": str(getattr(intent, "id", "")),
            "expected_version": int(expected_version),
            "limits": limits,
            "blockers": list(dict.fromkeys(blockers)),
            "escalation_reasons": list(dict.fromkeys(escalation_reasons)),
            "requires_escalation": bool(escalation_reasons),
        }

    def _preflight_inventory_blockers(self, audit: Any) -> list[str]:
        if audit is None:
            return ["prepared preflight inventory is missing"]
        rows = getattr(audit, "preflight_checks", None)
        if not isinstance(rows, list) or not rows:
            return ["prepared preflight inventory is missing"]
        blockers: list[str] = []
        seen: set[str] = set()
        allowed = self.REQUIRED_PREFLIGHT_CHECKS | self.OPTIONAL_PREFLIGHT_CHECKS
        for row in rows:
            if not isinstance(row, dict):
                blockers.append("prepared preflight row is malformed")
                continue
            check_id = str(row.get("id") or "").strip()
            label = str(row.get("label") or "").strip()
            reason = str(row.get("reason") or "").strip()
            status = str(row.get("status") or "").strip().lower()
            if not check_id or not label or not reason:
                blockers.append("prepared preflight row is malformed")
                continue
            if check_id in seen:
                blockers.append(f"prepared preflight check {check_id} is duplicated")
                continue
            seen.add(check_id)
            if check_id not in allowed:
                blockers.append(
                    f"prepared preflight check {check_id} is not recognized"
                )
            if status != "pass":
                blockers.append(
                    f"prepared preflight check {label} is not passing"
                )
        missing = sorted(self.REQUIRED_PREFLIGHT_CHECKS - seen)
        if missing:
            blockers.append(
                "prepared preflight inventory is missing: "
                + ", ".join(missing)
            )
        return blockers

    def _existing_idempotent_receipt(
        self,
        *,
        device_id: str,
        action_type: str,
        entity_id: str,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> StoredMobileActionReceipt | None:
        key_hash = self._idempotency_hash(device_id, idempotency_key)
        receipt = self.state.storage.load_mobile_action_receipt_by_key_hash(key_hash)
        if receipt is None:
            return None
        self._verify_existing_receipt(
            receipt,
            device_id=device_id,
            action_type=action_type,
            entity_id=entity_id,
            request_fingerprint=request_fingerprint,
        )
        return receipt

    def _verify_existing_receipt(
        self,
        receipt: StoredMobileActionReceipt,
        *,
        device_id: str,
        action_type: str,
        entity_id: str,
        request_fingerprint: str,
    ) -> dict[str, object]:
        if (
            receipt.device_id != device_id
            or receipt.action_type != action_type
            or receipt.entity_id != entity_id
            or str(receipt.payload.get("request_fingerprint") or "")
            != request_fingerprint
        ):
            raise ValueError("Idempotency key is already bound to another request")
        return self._receipt_public(receipt)

    @staticmethod
    def _receipt_status_from_audit(
        audit: dict[str, object],
    ) -> tuple[str, str]:
        status = str(audit.get("status") or audit.get("final_status") or "")
        if status in {"confirmed", "reconciled", "executed"}:
            return MobileActionStatus.CONFIRMED.value, "Trade confirmed"
        if status in {"needs_review", "review_required"}:
            return (
                MobileActionStatus.REVIEW_REQUIRED.value,
                str(audit.get("recommended_action") or "Review required"),
            )
        if status in {"failed", "cancelled", "expired", "stale"}:
            return MobileActionStatus.FAILED.value, "Trade authorization failed"
        return MobileActionStatus.VERIFYING.value, "Verifying outcome"

    @staticmethod
    def _treasury_receipt_status(
        result: dict[str, object],
    ) -> tuple[str, str]:
        status = str(result.get("status") or "").lower()
        message = str(result.get("operator_message") or "").strip()
        if status in {"confirmed", "reconciled", "executed"}:
            return (
                MobileActionStatus.CONFIRMED.value,
                message or "Treasury transaction confirmed",
            )
        if status in {"failed"}:
            return (
                MobileActionStatus.FAILED.value,
                message or "Treasury transaction failed",
            )
        if status in {"cancelled"}:
            return (
                MobileActionStatus.CANCELLED.value,
                message or "Treasury transaction cancelled",
            )
        if status in {"expired", "stale"}:
            return (
                MobileActionStatus.EXPIRED.value,
                message or "Treasury authorization expired",
            )
        if status in {"review_required", "needs_review"}:
            return (
                MobileActionStatus.REVIEW_REQUIRED.value,
                message or "Treasury outcome requires operator review",
            )
        if status in {"verifying", "submitted"}:
            return (
                MobileActionStatus.VERIFYING.value,
                message or "Verifying treasury outcome",
            )
        return (
            MobileActionStatus.PENDING.value,
            message or "Treasury request pending",
        )

    @staticmethod
    def _receipt_public(receipt: StoredMobileActionReceipt) -> dict[str, object]:
        return {
            "action_id": receipt.id,
            "status": receipt.status,
            "submitted_at": str(
                receipt.payload.get("submitted_at") or receipt.created_at.isoformat()
            ),
            "updated_at": receipt.updated_at.isoformat(),
            "operator_message": str(
                receipt.payload.get("operator_message") or "Action pending"
            ),
            "reconcile_after_ms": int(
                receipt.payload.get("reconcile_after_ms") or 1000
            ),
        }

    @staticmethod
    def _device_id(device: dict[str, object]) -> str:
        device_id = str(device.get("id") or "").strip()
        if not device_id:
            raise ValueError("Mobile device identity is required")
        return device_id

    @staticmethod
    def _action_id(raw_key: str) -> str:
        clean_key = raw_key.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{7,119}", clean_key):
            raise ValueError(
                "Idempotency key must be 8-120 ASCII letters, digits, underscores, or hyphens"
            )
        return clean_key

    @classmethod
    def _idempotency_hash(cls, device_id: str, raw_key: str) -> str:
        clean_key = cls._action_id(raw_key)
        return hashlib.sha256(
            f"cryptoarc-mobile-action-v1:{device_id}:{clean_key}".encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _request_fingerprint(payload: dict[str, object]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _draft_payload(draft: Any) -> dict[str, str | None]:
        if hasattr(draft, "model_dump"):
            raw = draft.model_dump(mode="json")
        elif isinstance(draft, dict):
            raw = dict(draft)
        else:
            raw = {
                "amount": getattr(draft, "amount", None),
                "slippage_pct": getattr(draft, "slippage_pct", None),
                "stop_pct": getattr(draft, "stop_pct", None),
                "target_pct": getattr(draft, "target_pct", None),
            }
        return {
            "amount": str(raw.get("amount") or ""),
            "slippage_pct": str(raw.get("slippage_pct") or ""),
            "stop_pct": (
                str(raw.get("stop_pct"))
                if raw.get("stop_pct") is not None
                else None
            ),
            "target_pct": (
                str(raw.get("target_pct"))
                if raw.get("target_pct") is not None
                else None
            ),
        }

    @staticmethod
    def _decimal(value: Any, label: str) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{label} must be numeric") from exc
        if not result.is_finite() or result <= 0:
            raise ValueError(f"{label} must be positive and finite")
        return result

    @classmethod
    def _prepared_amount(
        cls,
        value: Any,
        *,
        action: str,
        label: str,
    ) -> tuple[Decimal, bool]:
        text = str(value).strip()
        if text == "100%":
            if action != "sell":
                raise ValueError("Only a sell can use the canonical 100% amount")
            return Decimal("100"), True
        if text.endswith("%"):
            raise ValueError(f"{label} must use the exact canonical 100% value")
        return cls._decimal(text, label), False

    @staticmethod
    def _is_expired(value: Any) -> bool:
        if not value:
            return False
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return True
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= datetime.now(timezone.utc)

    @classmethod
    def _quote_is_stale(cls, quote: dict[str, object]) -> bool:
        return bool(quote.get("stale")) or cls._is_expired(quote.get("expires_at"))

    @staticmethod
    def _iso(value: Any) -> str | None:
        if value is None or value == "":
            return None
        return value.isoformat() if isinstance(value, datetime) else str(value)

    def issue_websocket_ticket(self, device: dict[str, object]) -> dict[str, object]:
        raw_ticket = secrets.token_urlsafe(32)
        ticket_hash = self._hash_websocket_ticket(raw_ticket)
        now = self._monotonic()
        ticket = _MobileWebSocketTicket(
            device_id=str(device.get("id") or ""),
            scope=MobileScope.MONITOR,
            expires_at=now + self.WEBSOCKET_TICKET_TTL_SECONDS,
        )
        if not ticket.device_id:
            raise ValueError("Mobile device identity is required")
        with self._ws_ticket_lock:
            self._cleanup_websocket_tickets_locked(now)
            if len(self._ws_tickets) >= self.MAX_WEBSOCKET_TICKETS:
                oldest_hash = min(
                    self._ws_tickets,
                    key=lambda digest: self._ws_tickets[digest].expires_at,
                )
                self._ws_tickets.pop(oldest_hash, None)
            self._ws_tickets[ticket_hash] = ticket
        return {
            "ticket": raw_ticket,
            "scope": ticket.scope,
            "ttl_seconds": self.WEBSOCKET_TICKET_TTL_SECONDS,
        }

    def consume_websocket_ticket(self, raw_ticket: str) -> dict[str, object] | None:
        candidate = raw_ticket.strip()
        if not candidate:
            return None
        ticket_hash = self._hash_websocket_ticket(candidate)
        now = self._monotonic()
        with self._ws_ticket_lock:
            self._cleanup_websocket_tickets_locked(now)
            ticket = self._ws_tickets.pop(ticket_hash, None)
        if (
            ticket is None
            or ticket.expires_at <= now
            or ticket.scope != MobileScope.MONITOR
        ):
            return None
        return self._current_mobile_device(ticket.device_id, ticket.scope)

    @staticmethod
    def _hash_websocket_ticket(raw_ticket: str) -> str:
        return hashlib.sha256(
            f"cryptoarc-mobile-ws-ticket-v1:{raw_ticket}".encode("utf-8")
        ).hexdigest()

    def _cleanup_websocket_tickets_locked(self, now: float) -> None:
        expired = [
            digest
            for digest, ticket in self._ws_tickets.items()
            if ticket.expires_at <= now
        ]
        for digest in expired:
            self._ws_tickets.pop(digest, None)

    def _current_mobile_device(
        self,
        device_id: str,
        required_scope: str,
    ) -> dict[str, object] | None:
        for device in self.state.mobile_devices(include_revoked=True):
            if str(device.get("id") or "") != device_id:
                continue
            if str(device.get("revoked_at") or ""):
                return None
            if required_scope not in [str(scope) for scope in device.get("scopes") or []]:
                return None
            expires_at = str(device.get("expires_at") or "")
            try:
                parsed_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed_expiry.tzinfo is None:
                parsed_expiry = parsed_expiry.replace(tzinfo=timezone.utc)
            if parsed_expiry <= datetime.now(timezone.utc):
                return None
            return device
        return None

    def feed(
        self,
        *,
        level: str,
        subsystem: str,
        limit: int,
        device: dict[str, object],
    ) -> dict[str, object]:
        return {
            **self.state.mobile_feed(level=level, subsystem=subsystem, limit=limit),
            "device": device,
        }

    def alerts_status(self, device: dict[str, object]) -> dict[str, object]:
        status = self.state.alerts.status()
        last_result = (
            status.get("last_result")
            if isinstance(status.get("last_result"), dict)
            else {}
        )
        return {
            "device": device,
            "alerts": {
                "telegram_enabled": bool(status.get("telegram_enabled")),
                "telegram_configured": bool(
                    status.get("telegram_configured")
                ),
                "last_status": str(last_result.get("status") or "not_sent"),
            },
        }

    def alerts(
        self,
        *,
        device: dict[str, object],
        limit: int = 100,
    ) -> dict[str, object]:
        device_id = self._device_id(device)
        bounded_limit = max(1, min(200, int(limit or 100)))
        acknowledgements = {
            row["event_id"]: row
            for row in self.state.storage.load_mobile_alert_acknowledgements(
                device_id=device_id,
                limit=500,
            )
        }
        alert_events = [
            event
            for event in self.state.storage.load_all_events(bounded_limit * 3)
            if self._is_mobile_alert_event(event)
        ][:bounded_limit]
        return {
            "artifact_type": "cryptoarc_mobile_alerts",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "alerts": [
                self._public_mobile_alert(
                    event.to_dict(),
                    acknowledgements.get(event.id),
                )
                for event in alert_events
            ],
        }

    def acknowledge_alert(
        self,
        *,
        device: dict[str, object],
        event_id: str,
    ) -> dict[str, object]:
        clean_event_id = self._mobile_identifier(event_id, "event ID")
        event = next(
            (
                candidate
                for candidate in self.state.storage.load_all_events(1000)
                if candidate.id == clean_event_id
            ),
            None,
        )
        if event is None or not self._is_mobile_alert_event(event):
            raise LookupError("Mobile alert not found")
        acknowledgement = self.state.storage.acknowledge_mobile_alert(
            acknowledgement_id=new_id("malertack"),
            device_id=self._device_id(device),
            event_id=clean_event_id,
            acknowledged_at=utc_now().isoformat(),
        )
        return {
            "event_id": clean_event_id,
            "acknowledged": True,
            "acknowledged_at": acknowledgement["acknowledged_at"],
        }

    def build_push_payload(
        self,
        event: dict[str, object],
    ) -> dict[str, object]:
        event_id = self._mobile_identifier(event.get("id"), "event ID")
        severity = str(event.get("level") or event.get("severity") or "").lower()
        if severity not in {"info", "warning", "danger", "error"}:
            raise ValueError("Push severity is invalid")
        subsystem = str(event.get("subsystem") or "app").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", subsystem):
            raise ValueError("Push subsystem is invalid")
        route = self._event_route(event)
        channel = self._push_channel(severity)
        return {
            "title": (
                "Critical CryptoARC alert"
                if severity in {"danger", "error"}
                else "CryptoARC warning"
                if severity == "warning"
                else "CryptoARC activity"
            ),
            "body": "Open CryptoARC after unlocking.",
            "channelId": channel,
            "data": {
                "event_id": event_id,
                "severity": severity,
                "subsystem": subsystem,
                "route": route,
            },
        }

    def deliver_push_event(
        self,
        event: dict[str, object],
    ) -> dict[str, object]:
        payload = self.build_push_payload(event)
        event_id = str(payload["data"]["event_id"])
        channel = str(payload["channelId"])
        result = {
            "event_id": event_id,
            "channel": channel,
            "sent": 0,
            "failed": 0,
            "deduplicated": 0,
            "invalidated": 0,
            "unavailable": self._push_sender is None,
        }
        if self._push_sender is None:
            return result
        registrations = self.state.storage.load_mobile_push_registrations(
            limit=200
        )
        fernet = self._push_token_fernet()
        for registration in registrations:
            device_id = str(registration.get("device_id") or "")
            registration_id = str(registration.get("id") or "")
            if self._current_mobile_device(device_id, MobileScope.ALERTS) is None:
                self.state.storage.revoke_mobile_push_registrations(
                    device_id=device_id,
                    revoked_at=utc_now().isoformat(),
                )
                result["invalidated"] += 1
                continue
            attempt_id = new_id("mpushattempt")
            reserved_attempt = self.state.storage.reserve_mobile_notification_delivery(
                delivery_id=new_id("mpushdelivery"),
                attempt_id=attempt_id,
                event_id=event_id,
                device_id=device_id,
                channel=channel,
                registration_id=registration_id,
                attempted_at=utc_now().isoformat(),
                lease_seconds=self.PUSH_DELIVERY_LEASE_SECONDS,
            )
            if not reserved_attempt:
                result["deduplicated"] += 1
                continue
            status = "failed"
            raw_token: str | None = None
            try:
                if self._current_mobile_device(device_id, MobileScope.ALERTS) is None:
                    self.state.storage.revoke_mobile_push_registrations(
                        device_id=device_id,
                        revoked_at=utc_now().isoformat(),
                    )
                    result["invalidated"] += 1
                    continue
                raw_token = fernet.decrypt(
                    str(registration.get("token_ciphertext") or "").encode("ascii")
                ).decode("utf-8")
                sender_result = self._push_sender(raw_token, payload)
                if not self._push_sender_succeeded(sender_result):
                    raise RuntimeError("Push sender did not confirm delivery")
                result["sent"] += 1
                status = "sent"
            except Exception:
                result["failed"] += 1
            finally:
                raw_token = None
                self.state.storage.finish_mobile_notification_delivery(
                    attempt_id=attempt_id,
                    status=status,
                    updated_at=utc_now().isoformat(),
                )
        return result

    def unregister_push_token(
        self,
        *,
        device: dict[str, object],
    ) -> dict[str, object]:
        self.state.storage.revoke_mobile_push_registrations(
            device_id=self._device_id(device),
            revoked_at=utc_now().isoformat(),
        )
        return {"unregistered": True}

    def diagnostics(
        self,
        *,
        device: dict[str, object],
    ) -> dict[str, object]:
        now = utc_now()
        device_id = self._device_id(device)
        scopes = {str(scope) for scope in device.get("scopes") or []}
        registrations = [
            row
            for row in self.state.storage.load_mobile_push_registrations(
                limit=200
            )
            if str(row.get("device_id") or "") == device_id
        ]
        telegram = self.state.alerts.status()
        runtime_status = self.state.mobile_diagnostic_runtime_status()
        age_seconds = None
        stale_after_seconds = 60
        freshness_status = "unavailable"
        source_status = str(
            runtime_status.get("source_status") or "unknown"
        ).lower()
        rpc_healthy = source_status in {"healthy", "connected", "ok", "live"}
        source_observed_value = runtime_status.get("source_observed_at")
        source_observed_at = (
            datetime.fromisoformat(str(source_observed_value).replace("Z", "+00:00"))
            if source_observed_value
            else None
        )
        signer_configured = bool(
            runtime_status.get("signer_mode_configured")
        )
        checks = [
            self._diagnostic_check(
                "tunnel",
                "Private tunnel",
                "unavailable",
                "Private-tunnel state must be observed on-device.",
                None,
            ),
            self._diagnostic_check(
                "api", "API", "healthy", "Authenticated API is responding.", now
            ),
            self._diagnostic_check(
                "websocket",
                "WebSocket",
                "unavailable",
                "WebSocket state must be observed on-device.",
                None,
            ),
            self._diagnostic_check(
                "token_scope",
                "Token scope",
                "healthy" if MobileScope.DIAGNOSTICS in scopes else "blocked",
                "Required diagnostics scope is present."
                if MobileScope.DIAGNOSTICS in scopes
                else "Diagnostics scope is missing.",
                now,
            ),
            self._diagnostic_check(
                "push",
                "Push",
                "healthy" if registrations else "warning",
                "An active push registration exists."
                if registrations
                else "No active push registration exists.",
                self._parse_optional_datetime(
                    registrations[0].get("updated_at") if registrations else None
                ),
            ),
            self._diagnostic_check(
                "telegram",
                "Telegram",
                (
                    "healthy"
                    if telegram.get("telegram_enabled")
                    and telegram.get("telegram_configured")
                    else "warning"
                ),
                "Status only: enabled and configured."
                if telegram.get("telegram_enabled")
                and telegram.get("telegram_configured")
                else "Status only: disabled or not configured.",
                now,
            ),
            self._diagnostic_check(
                "clock_drift",
                "Clock drift",
                "unavailable",
                "Calculated on-device from server time.",
                None,
            ),
            self._diagnostic_check(
                "snapshot_age",
                "Snapshot age",
                "unavailable"
                if age_seconds is None
                else "healthy"
                if age_seconds <= stale_after_seconds
                else "warning",
                "No stored event timestamp is available."
                if age_seconds is None
                else f"Latest verified snapshot is {age_seconds} seconds old.",
                None,
            ),
            self._diagnostic_check(
                "rpc",
                "RPC",
                "healthy" if rpc_healthy and source_observed_at else "warning" if source_observed_at else "unavailable",
                "In-memory source state is healthy."
                if rpc_healthy and source_observed_at
                else "In-memory source state is not healthy."
                if source_observed_at
                else "No source transport observation is available.",
                source_observed_at,
            ),
            self._diagnostic_check(
                "signer",
                "Signer",
                "warning" if signer_configured else "unavailable",
                "Signer mode is configured; readiness must be verified locally."
                if signer_configured
                else "No signer mode is configured.",
                now,
            ),
        ]
        return {
            "artifact_type": "cryptoarc_mobile_diagnostics",
            "format_version": 1,
            "generated_at": now.isoformat(),
            "freshness": {
                "status": freshness_status,
                "age_seconds": age_seconds,
                "stale_after_seconds": stale_after_seconds,
            },
            "checks": checks,
            "recovery_actions": [
                {
                    "id": "reconnect",
                    "label": "Reconnect",
                    "detail": "Restore the private tunnel, then refresh.",
                    "enabled": True,
                },
                {
                    "id": "re_register_push",
                    "label": "Refresh push registration",
                    "detail": "Retry after connectivity returns.",
                    "enabled": not bool(registrations),
                },
                {
                    "id": "review_desktop",
                    "label": "Review desktop diagnostics",
                    "detail": "Inspect signer and RPC readiness on the trusted host.",
                    "enabled": True,
                },
            ],
        }

    def diagnostic_export(
        self,
        *,
        device: dict[str, object],
        include_public_identifiers: bool = False,
    ) -> dict[str, object]:
        payload = self.diagnostics(device=device)
        payload["exported_at"] = utc_now().isoformat()
        return self.redact_diagnostic_payload(
            payload,
            include_public_identifiers=include_public_identifiers,
        )

    @classmethod
    def redact_diagnostic_payload(
        cls,
        value: Any,
        *,
        include_public_identifiers: bool = False,
        _depth: int = 0,
    ) -> Any:
        if _depth >= 8:
            return "[REDACTED]"
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for index, (raw_key, item) in enumerate(value.items()):
                if index >= 100:
                    break
                key = str(raw_key)
                if cls.DIAGNOSTIC_PUBLIC_IDENTIFIER_KEY.search(key):
                    if include_public_identifiers and isinstance(item, str):
                        redacted[key] = cls._short_public_identifier(item)
                    continue
                if (
                    cls.DIAGNOSTIC_SENSITIVE_KEY.search(key)
                    or cls.DIAGNOSTIC_PATH_KEY.search(key)
                ):
                    redacted[key] = "[REDACTED]"
                    continue
                redacted[key] = cls.redact_diagnostic_payload(
                    item,
                    include_public_identifiers=include_public_identifiers,
                    _depth=_depth + 1,
                )
            return redacted
        if isinstance(value, (list, tuple)):
            return [
                cls.redact_diagnostic_payload(
                    item,
                    include_public_identifiers=include_public_identifiers,
                    _depth=_depth + 1,
                )
                for item in list(value)[:100]
            ]
        if isinstance(value, str):
            lowered = value.lower()
            if (
                "exponentpushtoken[" in lowered
                or "expopushtoken[" in lowered
                or "bearer " in lowered
                or "seed phrase" in lowered
                or "private key" in lowered
                or re.search(r"(?:^|[\s\"'])/[a-z0-9_.-]+/", lowered)
                or re.search(r"[a-z]:\\", lowered)
            ):
                return "[REDACTED]"
            return value[:1000]
        return value

    @classmethod
    def _event_route(cls, event: dict[str, object]) -> str:
        explicit = str(event.get("route") or "").strip()
        context = event.get("context")
        event_context = context if isinstance(context, dict) else {}
        if explicit:
            route = explicit
        elif event_context.get("intent_id"):
            route = f"/trade/{event_context['intent_id']}"
        elif event_context.get("position_id"):
            route = f"/position/{event_context['position_id']}"
        else:
            route = "/alerts"
        if not any(pattern.fullmatch(route) for pattern in cls.PUSH_ROUTE_PATTERNS):
            raise ValueError("Push route is invalid")
        return route

    @staticmethod
    def _is_mobile_alert_event(event: Any) -> bool:
        return (
            str(getattr(event, "level", "")).lower()
            in {"warning", "danger", "error"}
            or bool(getattr(event, "operator_action", ""))
        )

    @staticmethod
    def _push_sender_succeeded(result: object) -> bool:
        if result is True:
            return True
        if not isinstance(result, dict):
            return False
        return str(result.get("status") or "").strip().lower() == "sent"

    @staticmethod
    def _parse_optional_datetime(value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)

    @classmethod
    def _public_mobile_alert(
        cls,
        event: dict[str, object],
        acknowledgement: dict[str, str] | None,
    ) -> dict[str, object]:
        severity = str(event.get("level") or "warning").lower()
        subsystem = str(event.get("subsystem") or "app").lower()
        return {
            "event_id": cls._mobile_identifier(event.get("id"), "event ID"),
            "created_at": str(event.get("created_at") or utc_now().isoformat()),
            "severity": severity,
            "subsystem": subsystem,
            "title": (
                "Critical "
                if severity in {"danger", "error"}
                else "Warning "
            )
            + f"{subsystem} alert",
            "summary": "Review this event on the trusted backend.",
            "route": cls._event_route(event),
            "acknowledged": acknowledgement is not None,
            "acknowledged_at": (
                acknowledgement.get("acknowledged_at")
                if acknowledgement
                else None
            ),
        }

    @staticmethod
    def _push_channel(severity: str) -> str:
        if severity in {"danger", "error"}:
            return "critical"
        if severity == "warning":
            return "warning"
        return "activity"

    @classmethod
    def _mobile_identifier(cls, value: Any, label: str) -> str:
        candidate = str(value or "").strip()
        if not cls.MOBILE_IDENTIFIER_PATTERN.fullmatch(candidate):
            raise ValueError(f"Mobile {label} is invalid")
        return candidate

    @staticmethod
    def _diagnostic_check(
        check_id: str,
        label: str,
        status: str,
        detail: str,
        observed_at: datetime | None,
    ) -> dict[str, object]:
        return {
            "id": check_id,
            "label": label,
            "status": status,
            "detail": detail,
            "observed_at": observed_at.isoformat() if observed_at else None,
        }

    @staticmethod
    def _short_public_identifier(value: str) -> str:
        candidate = value.strip()
        if len(candidate) <= 12:
            return candidate
        return f"{candidate[:6]}...{candidate[-5:]}"

    async def start_action(self, device: dict[str, object]) -> dict[str, object]:
        mode = (
            self.state.settings.mode.value
            if hasattr(self.state.settings.mode, "value")
            else self.state.settings.mode
        )
        if mode == "live_locked" or self.state.settings.live_trading_enabled:
            self.state.add_event(
                "danger",
                "Mobile cockpit start denied by live safety boundary",
                subsystem="mobile",
            )
            await self._broadcast_snapshot()
            await self._broadcast_mobile_cockpit()
            return self.cockpit(device)
        payload = self.state.mobile_start_bot(
            self.config.live_trading_enabled,
            local_auth_enabled=self.auth.enabled,
        )
        payload["device"] = device
        await self._broadcast_snapshot()
        await self._broadcast_mobile_cockpit()
        return payload

    async def stop_action(self, device: dict[str, object]) -> dict[str, object]:
        payload = self.state.mobile_stop_bot(
            self.config.live_trading_enabled,
            local_auth_enabled=self.auth.enabled,
        )
        payload["stop_runtime"] = await self._stop_runtime_tasks()
        payload["device"] = device
        await self._broadcast_snapshot()
        await self._broadcast_mobile_cockpit()
        return payload

    async def set_kill_switch(
        self,
        *,
        enabled: bool,
        reason: str,
        device: dict[str, object],
    ) -> dict[str, object]:
        cockpit = self.state.mobile_set_kill_switch(
            enabled,
            reason,
            live_trading_enabled=self.config.live_trading_enabled,
            local_auth_enabled=self.auth.enabled,
        )
        cockpit["device"] = device
        await self._broadcast_snapshot()
        await self._broadcast_mobile_cockpit()
        return cockpit

    def register_push_token(
        self,
        *,
        device: dict[str, object],
        token: str,
        platform: str,
    ) -> dict[str, object]:
        fernet = self._push_token_fernet()
        raw_token = token.strip()
        if not self.EXPO_PUSH_TOKEN_PATTERN.fullmatch(raw_token):
            raise ValueError("Invalid mobile push registration request")
        now = utc_now()
        registration = MobilePushRegistration(
            id=new_id("mpush"),
            device_id=str(device["id"]),
            token_ciphertext=fernet.encrypt(raw_token.encode("utf-8")).decode("ascii"),
            token_fingerprint=hashlib.sha256(
                f"cryptoarc-mobile-push-v1:{raw_token}".encode("utf-8")
            ).hexdigest(),
            platform=str(platform or device.get("platform") or "unknown").strip().lower()[:40],
            created_at=now,
            updated_at=now,
        )
        persisted = self.state.storage.save_mobile_push_registration(registration)
        return {"registered": True, "registration": persisted.to_public_dict()}

    def _push_token_fernet(self) -> Fernet:
        key = str(self.config.mobile_push_token_encryption_key or "").strip()
        if not key:
            raise MobilePushTokenEncryptionUnavailable(
                "Mobile push token encryption is unavailable"
            )
        try:
            return Fernet(key.encode("ascii"))
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise MobilePushTokenEncryptionUnavailable(
                "Mobile push token encryption is unavailable"
            ) from exc
