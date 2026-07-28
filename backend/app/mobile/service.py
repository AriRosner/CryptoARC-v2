from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from cryptography.fernet import Fernet

from app.core.models import (
    MobileActionReceipt as StoredMobileActionReceipt,
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
    MAX_WEBSOCKET_TICKETS = 512

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
            receipt, created = self.state.storage.reserve_mobile_action_receipt(
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
                        "operator_message": "Rejecting prepared intent",
                        "reconcile_after_ms": 1000,
                        "submitted_at": now.isoformat(),
                    },
                    status=MobileActionStatus.PENDING.value,
                    created_at=now,
                    updated_at=now,
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
            intent.status = "cancelled"
            intent.reason = f"Rejected from paired mobile device: {clean_reason}"
            intent.updated_at = utc_now()
            intent.version = int(getattr(intent, "version", 1)) + 1
            self.state.storage.save_live_intent(intent)
            receipt.status = MobileActionStatus.CANCELLED.value
            receipt.updated_at = utc_now()
            receipt.payload["operator_message"] = "Trade intent rejected"
            self.state.storage.save_mobile_action_receipt(receipt)
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
            receipt, created = self.state.storage.reserve_mobile_action_receipt(
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
                        "operator_message": "Applying bounded exit controls",
                        "reconcile_after_ms": 500,
                        "submitted_at": now.isoformat(),
                    },
                    status=MobileActionStatus.PENDING.value,
                    created_at=now,
                    updated_at=now,
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
            self.state.mobile_adjust_position_exit(
                position_id=position_id,
                expected_version=expected_version,
                stop_pct=float(stop),
                target_pct=float(target),
            )
            receipt.status = MobileActionStatus.CONFIRMED.value
            receipt.updated_at = utc_now()
            receipt.payload["operator_message"] = "Exit controls updated"
            self.state.storage.save_mobile_action_receipt(receipt)
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
        intent = self.state.storage.load_live_intent(intent_id)
        if intent is None:
            raise LookupError("Prepared close intent not found")
        if (
            str(getattr(intent, "action", "")) != "sell"
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
        audit_id = str(receipt.payload.get("audit_id") or "")
        if audit_id and receipt.status in {
            MobileActionStatus.PENDING.value,
            MobileActionStatus.VERIFYING.value,
            MobileActionStatus.REVIEW_REQUIRED.value,
        }:
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
        return self._receipt_public(receipt)

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
            receipt, created = self.state.storage.reserve_mobile_action_receipt(
                StoredMobileActionReceipt(
                    id=self._action_id(idempotency_key),
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
                )
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
                result = self.state.live_submit(audit_id, "")
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
        amount = self._decimal(payload["amount"], "amount")
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
        prepared_amount = self._decimal(
            getattr(intent, "amount", "0"), "prepared amount"
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
        if amount != prepared_amount:
            blockers.append("Trade amount must match the prepared intent bound")
        if amount > amount_cap and str(getattr(intent, "action", "")) == "buy":
            blockers.append("Trade amount exceeds the live size limit")
        if slippage != prepared_slippage:
            blockers.append("Slippage must match the prepared quote bound")
        if slippage > slippage_cap:
            blockers.append("Slippage exceeds the live limit")
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
        if audit is not None:
            for check in audit.preflight_checks or []:
                if str(check.get("status") or "").lower() == "fail":
                    blockers.append(
                        f"{check.get('label') or check.get('id') or 'preflight'} failed"
                    )
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
        if amount_cap > 0 and amount >= amount_cap * Decimal("0.75"):
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
        return {"device": device, "alerts": self.state.alerts.status()}

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
