from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, SecretStr
from starlette.responses import JSONResponse

from app.mobile.contracts import (
    MobileActionReceipt,
    MobileAdjustExitRequest,
    MobileGuardedActionRequest,
    MobilePortfolioPayload,
    MobilePositionCloseRequest,
    MobilePositionDetail,
    MobilePositionsPayload,
    MobileRejectTradeRequest,
    MobileScope,
)
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
    token: SecretStr = Field(min_length=1, max_length=4096)
    platform: str = Field(default="android", max_length=40)


class MobilePushRegistrationRoute(APIRoute):
    def get_route_handler(self):
        route_handler = super().get_route_handler()

        async def redacted_route_handler(request: Request):
            try:
                return await route_handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={"detail": "Invalid mobile push registration request"},
                )

        return redacted_route_handler


def create_mobile_router(
    service: MobileCommandCenterService,
    require_scope: Callable[[str], Callable[..., dict[str, object]]],
) -> APIRouter:
    router = APIRouter(prefix="/api/mobile", tags=["mobile"])

    def guarded_error(exc: Exception) -> HTTPException:
        if isinstance(exc, LookupError):
            return HTTPException(status_code=404, detail=str(exc))
        message = str(exc)
        if "version conflict" in message.lower() or "idempotency key" in message.lower():
            return HTTPException(status_code=409, detail=message)
        return HTTPException(status_code=422, detail=message)

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

    @router.get("/portfolio", response_model=MobilePortfolioPayload)
    async def mobile_portfolio(
        timeframe: str = "1d",
        device: dict[str, object] = Depends(require_scope(MobileScope.PORTFOLIO_READ)),
    ) -> dict[str, object]:
        try:
            return service.portfolio(device=device, timeframe=timeframe)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/positions", response_model=MobilePositionsPayload)
    async def mobile_positions(
        device: dict[str, object] = Depends(require_scope(MobileScope.PORTFOLIO_READ)),
    ) -> dict[str, object]:
        return service.positions(device=device)

    @router.get("/positions/{position_id}", response_model=MobilePositionDetail)
    async def mobile_position(
        position_id: str,
        device: dict[str, object] = Depends(require_scope(MobileScope.PORTFOLIO_READ)),
    ) -> dict[str, object]:
        try:
            return service.position(device=device, position_id=position_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/ws-ticket")
    async def mobile_websocket_ticket(
        device: dict[str, object] = Depends(require_scope(MobileScope.MONITOR)),
    ) -> dict[str, object]:
        return service.issue_websocket_ticket(device)

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

    @router.get("/trades")
    async def mobile_trades(
        device: dict[str, object] = Depends(
            require_scope(MobileScope.TRADE_REVIEW)
        ),
    ) -> dict[str, object]:
        return service.trades(device=device)

    @router.get("/trades/{intent_id}")
    async def mobile_trade(
        intent_id: str,
        device: dict[str, object] = Depends(
            require_scope(MobileScope.TRADE_REVIEW)
        ),
    ) -> dict[str, object]:
        try:
            return service.trade(device=device, intent_id=intent_id)
        except (LookupError, ValueError) as exc:
            raise guarded_error(exc) from exc

    @router.post("/trades/{intent_id}/validate")
    async def mobile_trade_validate(
        intent_id: str,
        payload: MobileGuardedActionRequest,
        device: dict[str, object] = Depends(
            require_scope(MobileScope.TRADE_REVIEW)
        ),
    ) -> dict[str, object]:
        try:
            return service.validate_trade(
                device=device,
                intent_id=intent_id,
                expected_version=payload.expected_version,
                draft=payload.draft,
                escalation_acknowledged=payload.escalation_acknowledged,
            )
        except (LookupError, ValueError) as exc:
            raise guarded_error(exc) from exc

    @router.post(
        "/trades/{intent_id}/approve",
        response_model=MobileActionReceipt,
    )
    async def mobile_trade_approve(
        intent_id: str,
        payload: MobileGuardedActionRequest,
        idempotency_key: str = Header(
            min_length=8,
            max_length=120,
            alias="Idempotency-Key",
        ),
        device: dict[str, object] = Depends(
            require_scope(MobileScope.TRADE_EXECUTE)
        ),
    ) -> dict[str, object]:
        try:
            return service.approve_trade(
                device=device,
                intent_id=intent_id,
                expected_version=payload.expected_version,
                draft=payload.draft,
                escalation_acknowledged=payload.escalation_acknowledged,
                idempotency_key=idempotency_key,
            )
        except (LookupError, ValueError) as exc:
            raise guarded_error(exc) from exc

    @router.post(
        "/trades/{intent_id}/reject",
        response_model=MobileActionReceipt,
    )
    async def mobile_trade_reject(
        intent_id: str,
        payload: MobileRejectTradeRequest,
        idempotency_key: str = Header(
            min_length=8,
            max_length=120,
            alias="Idempotency-Key",
        ),
        device: dict[str, object] = Depends(
            require_scope(MobileScope.TRADE_REVIEW)
        ),
    ) -> dict[str, object]:
        try:
            return service.reject_trade(
                device=device,
                intent_id=intent_id,
                expected_version=payload.expected_version,
                reason=payload.reason,
                idempotency_key=idempotency_key,
            )
        except (LookupError, ValueError) as exc:
            raise guarded_error(exc) from exc

    @router.post(
        "/positions/{position_id}/adjust-exit",
        response_model=MobileActionReceipt,
    )
    async def mobile_position_adjust_exit(
        position_id: str,
        payload: MobileAdjustExitRequest,
        idempotency_key: str = Header(
            min_length=8,
            max_length=120,
            alias="Idempotency-Key",
        ),
        device: dict[str, object] = Depends(
            require_scope(MobileScope.TRADE_EXECUTE)
        ),
    ) -> dict[str, object]:
        try:
            return service.adjust_position_exit(
                device=device,
                position_id=position_id,
                expected_version=payload.expected_version,
                stop_pct=payload.stop_pct,
                target_pct=payload.target_pct,
                escalation_acknowledged=payload.escalation_acknowledged,
                idempotency_key=idempotency_key,
            )
        except (LookupError, ValueError) as exc:
            raise guarded_error(exc) from exc

    @router.post(
        "/positions/{position_id}/close",
        response_model=MobileActionReceipt,
    )
    async def mobile_position_close(
        position_id: str,
        payload: MobilePositionCloseRequest,
        idempotency_key: str = Header(
            min_length=8,
            max_length=120,
            alias="Idempotency-Key",
        ),
        device: dict[str, object] = Depends(
            require_scope(MobileScope.TRADE_EXECUTE)
        ),
    ) -> dict[str, object]:
        try:
            return service.close_position(
                device=device,
                position_id=position_id,
                position_version=payload.position_version,
                intent_id=payload.intent_id,
                expected_version=payload.expected_version,
                draft=payload.draft,
                escalation_acknowledged=payload.escalation_acknowledged,
                idempotency_key=idempotency_key,
            )
        except (LookupError, ValueError) as exc:
            raise guarded_error(exc) from exc

    @router.get("/actions/{action_id}", response_model=MobileActionReceipt)
    async def mobile_action(
        action_id: str,
        device: dict[str, object] = Depends(
            require_scope(MobileScope.TRADE_REVIEW)
        ),
    ) -> dict[str, object]:
        try:
            return service.action(device=device, action_id=action_id)
        except (LookupError, ValueError) as exc:
            raise guarded_error(exc) from exc

    async def mobile_notifications_register(
        payload: MobilePushRegistrationRequest,
        device: dict[str, object] = Depends(require_scope(MobileScope.ALERTS)),
    ) -> dict[str, object]:
        try:
            return service.register_push_token(
                device=device,
                token=payload.token.get_secret_value(),
                platform=payload.platform,
            )
        except MobilePushTokenEncryptionUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    router.add_api_route(
        "/notifications/register",
        mobile_notifications_register,
        methods=["POST"],
        route_class_override=MobilePushRegistrationRoute,
    )

    return router
