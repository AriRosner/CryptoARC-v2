from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.mobile.contracts import MobileScope
from app.mobile.service import (
    MobileCommandCenterService,
    MobilePushTokenEncryptionUnavailable,
)


class MobilePairingStartRequest(BaseModel):
    api_base_url: str = Field(default="", max_length=300)
    scopes: list[str] = Field(
        default_factory=lambda: [MobileScope.MONITOR, MobileScope.CONTROL],
        max_length=5,
    )


class MobilePairingClaimRequest(BaseModel):
    pairing_id: str = Field(min_length=1, max_length=80)
    code: str = Field(min_length=4, max_length=40)
    device_name: str = Field(default="Mobile device", max_length=80)
    platform: str = Field(default="android", max_length=40)


class MobileKillSwitchPayload(BaseModel):
    enabled: bool = True
    reason: str = Field(default="", max_length=500)


class MobilePushRegistrationRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4096)
    platform: str = Field(default="android", max_length=40)


def create_mobile_router(
    service: MobileCommandCenterService,
    require_scope: Callable[[str], Callable[..., dict[str, object]]],
) -> APIRouter:
    router = APIRouter(prefix="/api/mobile", tags=["mobile"])

    @router.get("/health")
    async def mobile_health() -> dict[str, object]:
        return service.health()

    @router.post(
        "/pairing/start",
        dependencies=[Depends(service.require_dashboard_auth)],
    )
    async def mobile_pairing_start(
        payload: MobilePairingStartRequest | None = None,
    ) -> dict[str, object]:
        payload = payload or MobilePairingStartRequest()
        return await service.start_pairing(payload.api_base_url, payload.scopes)

    @router.post("/pairing/claim")
    async def mobile_pairing_claim(
        payload: MobilePairingClaimRequest,
    ) -> dict[str, object]:
        try:
            return await service.claim_pairing(
                payload.pairing_id,
                payload.code,
                payload.device_name,
                payload.platform,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get(
        "/devices",
        dependencies=[Depends(service.require_dashboard_auth)],
    )
    async def mobile_devices(include_revoked: bool = False) -> dict[str, object]:
        return service.devices(include_revoked)

    @router.post(
        "/devices/{device_id}/revoke",
        dependencies=[Depends(service.require_dashboard_auth)],
    )
    async def mobile_device_revoke(device_id: str) -> dict[str, object]:
        try:
            return await service.revoke_device(device_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/cockpit")
    async def mobile_cockpit(
        device: dict[str, object] = Depends(require_scope(MobileScope.MONITOR)),
    ) -> dict[str, object]:
        return service.cockpit(device)

    @router.get("/feed")
    async def mobile_feed(
        level: str = "",
        subsystem: str = "",
        limit: int = 100,
        device: dict[str, object] = Depends(require_scope(MobileScope.MONITOR)),
    ) -> dict[str, object]:
        return service.feed(
            level=level,
            subsystem=subsystem,
            limit=limit,
            device=device,
        )

    @router.get("/alerts/status")
    async def mobile_alerts_status(
        device: dict[str, object] = Depends(require_scope(MobileScope.MONITOR)),
    ) -> dict[str, object]:
        return service.alerts_status(device)

    @router.post("/actions/start")
    async def mobile_action_start(
        device: dict[str, object] = Depends(require_scope(MobileScope.CONTROL)),
    ) -> dict[str, object]:
        return await service.start_action(device)

    @router.post("/actions/stop")
    async def mobile_action_stop(
        device: dict[str, object] = Depends(require_scope(MobileScope.CONTROL)),
    ) -> dict[str, object]:
        return await service.stop_action(device)

    @router.post("/actions/kill-switch")
    async def mobile_action_kill_switch(
        payload: MobileKillSwitchPayload,
        device: dict[str, object] = Depends(require_scope(MobileScope.CONTROL)),
    ) -> dict[str, object]:
        return await service.set_kill_switch(
            enabled=payload.enabled,
            reason=payload.reason,
            device=device,
        )

    @router.get("/wallet")
    async def mobile_wallet(
        _: dict[str, object] = Depends(require_scope(MobileScope.WALLET_READ)),
    ) -> dict[str, object]:
        raise HTTPException(status_code=501, detail="Mobile wallet read is not implemented")

    @router.post("/trades/{intent_id}/approve")
    async def mobile_trade_approve(
        intent_id: str,
        _: dict[str, object] = Depends(require_scope(MobileScope.TRADE_EXECUTE)),
    ) -> dict[str, object]:
        raise HTTPException(
            status_code=501,
            detail=f"Mobile trade approval is not implemented for {intent_id}",
        )

    @router.post("/notifications/register")
    async def mobile_notifications_register(
        payload: MobilePushRegistrationRequest,
        device: dict[str, object] = Depends(require_scope(MobileScope.ALERTS)),
    ) -> dict[str, object]:
        try:
            return service.register_push_token(
                device=device,
                token=payload.token,
                platform=payload.platform,
            )
        except MobilePushTokenEncryptionUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return router
