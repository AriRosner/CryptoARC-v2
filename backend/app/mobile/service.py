from __future__ import annotations

import hashlib
import time
from collections.abc import Awaitable, Callable
from typing import Any

from cryptography.fernet import Fernet

from app.core.models import MobilePushRegistration, new_id, utc_now


class MobilePushTokenEncryptionUnavailable(RuntimeError):
    pass


class MobileCommandCenterService:
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
            "websocket_path": "/ws/mobile?token=...",
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
