from __future__ import annotations

import asyncio
import hmac
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator, Callable, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from weakref import WeakSet

import websockets
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth import AuthManager, random_totp_secret, verify_totp
from app.config import get_config
from app.core.alerts import AlertRouter
from app.core.models import SourceStatus, utc_now
from app.core.sources import LaunchEvent, SolanaLogsSource, make_source
from app.core.state import BotState
from app.mobile.contracts import MobileRealtimeEnvelope, MobileScope
from app.mobile.router import create_mobile_router
from app.mobile.service import MobileCommandCenterService


class SettingsPatch(BaseModel):
    launch_source: Literal["mock", "pumpportal"] | None = None
    strategy_profile: Literal["conservative", "balanced", "aggressive", "scalper", "custom"] | None = None
    trade_size_sol: float | None = Field(default=None, gt=0)
    slippage_tolerance_pct: float | None = Field(default=None, ge=0.01, le=100)
    take_profit_pct: float | None = Field(default=None, gt=0)
    stop_loss_pct: float | None = Field(default=None, gt=0)
    daily_loss_cap_sol: float | None = Field(default=None, gt=0)
    wallet_balance_cap_sol: float | None = Field(default=None, gt=0)
    max_creator_hold_pct: float | None = Field(default=None, ge=0, le=100)
    trading_speed: Literal["slow", "normal", "fast", "turbo"] | None = None
    max_hold_time_seconds: int | None = Field(default=None, ge=5, le=86400)
    minimum_hold_time_seconds: int | None = Field(default=None, ge=0, le=86400)
    risk_tolerance: Literal["low", "medium", "high", "degen"] | None = None
    score_threshold: int | None = Field(default=None, ge=0, le=100)
    max_open_positions: int | None = Field(default=None, ge=1, le=25)
    launch_interval_seconds: float | None = Field(default=None, ge=0.5, le=60)
    paper_price_volatility_pct: float | None = Field(default=None, ge=1, le=100)
    max_position_ticks: int | None = Field(default=None, ge=1, le=120)
    detect_new_tokens: bool | None = None
    auto_refresh: bool | None = None
    filter_honeypots: bool | None = None
    filter_rug_risk: bool | None = None
    live_trading_enabled: bool | None = None
    min_buy_velocity: float | None = Field(default=None, ge=0, le=1)
    max_sell_pressure: float | None = Field(default=None, ge=0, le=1)
    min_metadata_score: float | None = Field(default=None, ge=0, le=1)
    max_token_age_seconds: int | None = Field(default=None, ge=1, le=86400)
    source_stale_seconds: int | None = Field(default=None, ge=5, le=3600)
    source_max_reconnects: int | None = Field(default=None, ge=0, le=100)
    backtest_replay_limit: int | None = Field(default=None, ge=1, le=5000)
    raw_replay_limit: int | None = Field(default=None, ge=1, le=5000)
    enable_trade_toasts: bool | None = None
    compact_table_mode: bool | None = None
    paper_fill_delay_ticks: int | None = Field(default=None, ge=0, le=20)
    paper_fee_bps: float | None = Field(default=None, ge=0, le=1000)
    paper_price_impact_pct: float | None = Field(default=None, ge=0, le=25)
    paper_failed_fill_pct: float | None = Field(default=None, ge=0, le=100)
    duplicate_symbol_penalty: bool | None = None
    strict_metadata_checks: bool | None = None
    use_observed_prices: bool | None = None
    max_trade_subscriptions: int | None = Field(default=None, ge=0, le=5000)
    min_price_confidence: float | None = Field(default=None, ge=0, le=1)
    max_first_observed_move_pct: float | None = Field(default=None, ge=10, le=100000)
    prefer_market_cap_price: bool | None = None
    trailing_stop_enabled: bool | None = None
    trailing_stop_pct: float | None = Field(default=None, ge=1, le=1000)
    partial_take_profit_enabled: bool | None = None
    partial_take_profit_pct: float | None = Field(default=None, ge=1, le=1000)
    partial_take_profit_fraction: float | None = Field(default=None, ge=0.05, le=1)
    cooldown_after_loss_enabled: bool | None = None
    cooldown_after_loss_seconds: int | None = Field(default=None, ge=0, le=86400)
    entry_confirmation_enabled: bool | None = None
    entry_confirmation_min_buy_velocity: float | None = Field(default=None, ge=0, le=1)
    entry_confirmation_max_sell_pressure: float | None = Field(default=None, ge=0, le=1)
    entry_confirmation_min_metadata_score: float | None = Field(default=None, ge=0, le=1)
    entry_confirmation_min_initial_buy_sol: float | None = Field(default=None, ge=0, le=100)
    entry_confirmation_min_price_confidence: float | None = Field(default=None, ge=0, le=1)
    entry_confirmation_min_observed_trades: int | None = Field(default=None, ge=0, le=100)
    max_trades_per_hour_enabled: bool | None = None
    max_trades_per_hour: int | None = Field(default=None, ge=1, le=10000)
    velocity_slippage_enabled: bool | None = None
    max_same_creator_buys_enabled: bool | None = None
    max_same_creator_buys: int | None = Field(default=None, ge=1, le=1000)
    stop_on_source_degraded: bool | None = None
    direct_solana_paper_enabled: bool | None = None
    direct_solana_min_confidence: float | None = Field(default=None, ge=0, le=1)
    max_rejected_price_streak_enabled: bool | None = None
    max_rejected_price_streak: int | None = Field(default=None, ge=0, le=1000)
    strategy_weight_metadata: float | None = Field(default=None, ge=0, le=3)
    strategy_weight_momentum: float | None = Field(default=None, ge=0, le=3)
    strategy_weight_pressure: float | None = Field(default=None, ge=0, le=3)
    strategy_weight_creator: float | None = Field(default=None, ge=0, le=3)
    break_even_stop_enabled: bool | None = None
    break_even_after_profit_pct: float | None = Field(default=None, ge=0, le=1000)
    stalled_trade_exit_enabled: bool | None = None
    stalled_trade_seconds: int | None = Field(default=None, ge=1, le=86400)
    stalled_trade_min_move_pct: float | None = Field(default=None, ge=0, le=1000)
    sell_pressure_exit_enabled: bool | None = None
    sell_pressure_exit_threshold: float | None = Field(default=None, ge=0, le=1)
    kill_switch_enabled: bool | None = None
    max_consecutive_losses_enabled: bool | None = None
    max_consecutive_losses: int | None = Field(default=None, ge=1, le=100)
    halt_on_low_replay_confidence: bool | None = None
    min_replay_confidence: int | None = Field(default=None, ge=0, le=100)
    halt_on_low_readiness: bool | None = None
    min_readiness_score: int | None = Field(default=None, ge=0, le=100)
    solana_rpc_url: str | None = Field(default=None, min_length=8, max_length=300)
    watch_wallet_address: str | None = Field(default=None, max_length=80)
    manual_live_enabled: bool | None = None
    manual_live_max_sol: float | None = Field(default=None, gt=0, le=10)
    autonomous_live_enabled: bool | None = None
    live_max_trade_sol: float | None = Field(default=None, ge=0, le=100)
    live_daily_loss_cap_sol: float | None = Field(default=None, ge=0, le=100)
    live_wallet_exposure_cap_sol: float | None = Field(default=None, ge=0, le=1000)
    live_max_open_positions: int | None = Field(default=None, ge=0, le=100)
    live_max_slippage_pct: float | None = Field(default=None, ge=0, le=100)
    live_priority_fee_cap_sol: float | None = Field(default=None, ge=0, le=1)
    live_session_acknowledged: bool | None = None
    live_signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] | None = None
    live_active_backend_armed: bool | None = None
    live_active_wallet_public_key: str | None = Field(default=None, max_length=100)
    live_hot_wallet_enabled: bool | None = None
    live_hot_wallet_public_key: str | None = Field(default=None, max_length=100)
    live_hot_wallet_label: str | None = Field(default=None, max_length=120)
    profit_sweep_enabled: bool | None = None
    profit_sweep_mode: Literal["fixed_sol", "percentage"] | None = None
    profit_sweep_threshold_sol: float | None = Field(default=None, ge=0, le=1000)
    profit_sweep_amount_sol: float | None = Field(default=None, ge=0, le=1000)
    profit_sweep_percentage: float | None = Field(default=None, ge=0, le=100)
    profit_sweep_min_profit_sol: float | None = Field(default=None, ge=0, le=1000)
    profit_sweep_destination_wallet: str | None = Field(default=None, max_length=100)
    profit_sweep_min_reserve_sol: float | None = Field(default=None, ge=0, le=1000)
    profit_sweep_cooldown_seconds: int | None = Field(default=None, ge=0, le=86400)
    profit_sweep_max_per_day: int | None = Field(default=None, ge=0, le=1000)


class BacktestRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=5000)
    profile: Literal["conservative", "balanced", "aggressive", "scalper", "custom"] | None = None
    replay_source: Literal["tokens", "raw"] = "tokens"
    date_from: str | None = None
    date_to: str | None = None
    replay_speed: float = Field(default=50, ge=1, le=1000)


class LoginRequest(BaseModel):
    password: str = ""
    code: str = ""


class PasswordUpdateRequest(BaseModel):
    current_password: str = ""
    new_password: str = Field(min_length=8)


class TotpVerifyRequest(BaseModel):
    secret: str
    code: str


class ExperimentRequest(BaseModel):
    name: str = "Replay experiment"
    profile: str | None = None
    limit: int | None = Field(default=None, ge=1, le=5000)
    notes: str = ""


class TradeLabelRequest(BaseModel):
    label: Literal["good_entry", "bad_entry", "bad_exit", "bad_price_data", "rug_behavior", "exited_too_early", "held_too_long", "ignore_from_tuning"]
    note: str = ""


class TradeGradeCorrectionRequest(BaseModel):
    operator_intent_id: str = Field(min_length=1, max_length=200)
    patch: dict[str, object]
    note: str = Field(default="", max_length=1000)


class StrategyCandidateRequest(BaseModel):
    base_version: dict[str, object]
    patch: dict[str, object]
    evidence_ids: list[str] = Field(min_length=1, max_length=500)


class StrategyCandidatePromotionRequest(BaseModel):
    operator_intent_id: str = Field(min_length=1, max_length=200)


class PilotRiskPolicyRequest(BaseModel):
    reference_usd_per_sol: str = Field(min_length=1, max_length=40)
    wallet_equity_sol: str = Field(min_length=1, max_length=40)
    observed_at: datetime
    reference_observation_id: str = Field(min_length=1, max_length=200)
    operator_intent_id: str = Field(min_length=1, max_length=200)
    initial_slippage_pct: str = Field(default="3", min_length=1, max_length=20)


class ProductionRehearsalRequest(BaseModel):
    evidence: dict[str, object]


class PostPilotDecisionRequest(BaseModel):
    decision: Literal["scale", "hold", "revise", "stop"]
    rationale: str = Field(min_length=1, max_length=2000)
    authorization_id: str = Field(min_length=1, max_length=200)


class PaperRecoveryRequest(BaseModel):
    note: str = Field(default="operator stopped run", max_length=160)


class ApplyTuningSuggestionRequest(BaseModel):
    setting: str = Field(min_length=1, max_length=100)
    suggested_value: bool | int | float | str


class ReleaseVerificationRequest(BaseModel):
    app_version: str | None = None
    verify_passed: bool
    diff_reviewed: bool
    docs_reviewed: bool
    note: str = Field(default="", max_length=500)


class IncidentExportReviewRequest(BaseModel):
    exported: bool = True
    reviewed: bool = True
    note: str = Field(default="", max_length=500)


class RestoreArtifactPayload(BaseModel):
    artifact: dict[str, object]


class StrategyPresetRequest(BaseModel):
    name: str
    description: str = ""


class LiveExecutionPayload(BaseModel):
    action: Literal["buy", "sell"]
    mint: str = Field(min_length=1, max_length=100)
    amount_sol: float = Field(gt=0, le=100)


class LiveExecutionReviewPayload(BaseModel):
    status: Literal["reviewed", "rejected"]
    note: str = Field(default="", max_length=500)


class LiveSessionStartPayload(BaseModel):
    wallet_public_key: str = Field(default="", max_length=100)
    signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] = "browser_wallet"


class LiveQuotePayload(BaseModel):
    action: Literal["buy", "sell"]
    mint: str = Field(min_length=1, max_length=100)
    amount: str = Field(min_length=1, max_length=40)
    denominated_in_sol: bool = True
    slippage_pct: float = Field(ge=0, le=100)
    priority_fee_sol: float = Field(ge=0, le=1)
    pool: Literal["pump", "raydium", "pump-amm", "launchlab", "raydium-cpmm", "bonk", "auto"] = "pump"
    wallet_public_key: str = Field(default="", max_length=100)
    signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] = "browser_wallet"
    shadow_only: bool = False


class LiveIntentPayload(BaseModel):
    action: Literal["buy", "sell"]
    mint: str = Field(min_length=1, max_length=100)
    amount: str = Field(min_length=1, max_length=40)
    denominated_in_sol: bool = True
    wallet_public_key: str = Field(default="", max_length=100)
    signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] = "browser_wallet"
    source: str = Field(default="manual", max_length=40)
    reason: str = Field(default="", max_length=500)
    symbol: str = Field(default="", max_length=40)
    score: int = Field(default=0, ge=0, le=100)


class LiveIntentGeneratePayload(BaseModel):
    wallet_public_key: str = Field(default="", max_length=100)
    signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] = "browser_wallet"
    watchlist: list[str] = Field(default_factory=list, max_length=50)


class LiveHotWalletImportPayload(BaseModel):
    private_key: str = Field(min_length=1, max_length=4096)
    password: str = Field(min_length=8, max_length=200)
    label: str = Field(default="", max_length=120)


class LiveHotWalletUnlockPayload(BaseModel):
    password: str = Field(min_length=8, max_length=200)


class LiveBackendArmPayload(BaseModel):
    wallet_public_key: str = Field(default="", max_length=100)
    signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] = "browser_wallet"


class LiveKillSwitchPayload(BaseModel):
    enabled: bool
    reason: str = Field(default="", max_length=500)


class LiveIntentQuotePayload(BaseModel):
    slippage_pct: float = Field(ge=0, le=100)
    priority_fee_sol: float = Field(ge=0, le=1)
    pool: Literal["pump", "raydium", "pump-amm", "launchlab", "raydium-cpmm", "bonk", "auto"] = "pump"


class LiveExpertOverridePayload(BaseModel):
    target_gate: Literal["entry_autonomy", "exit_autonomy", "source_trust", "recovery_debt", "signer_boundary"]
    action: Literal["buy", "sell"] = "buy"
    reason: str = Field(min_length=12, max_length=1000)
    wallet_public_key: str = Field(default="", max_length=100)
    signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] = "browser_wallet"


class LiveSimulationPayload(BaseModel):
    audit_id: str
    ok: bool = False
    warning: str = Field(default="", max_length=500)
    error: str = Field(default="", max_length=500)
    result: dict = Field(default_factory=dict)


class LiveSubmitPayload(BaseModel):
    audit_id: str
    signature: str = Field(default="", max_length=200)


class LiveConfirmPayload(BaseModel):
    audit_id: str
    confirmation_status: str = Field(default="confirmed", max_length=50)
    error: str = Field(default="", max_length=500)


class LiveRentRecoveryPreviewPayload(BaseModel):
    wallet_public_key: str = Field(min_length=1, max_length=100)
    token_accounts: list[str] = Field(default_factory=list, min_length=1, max_length=40)


def require_auth(authorization: str | None = Header(default=None)) -> None:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not auth.valid(token):
        raise HTTPException(status_code=401, detail="Authentication required")


def _mobile_bearer_token(authorization: str | None) -> str:
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    return token


def require_mobile_scope(
    required_scope: str,
) -> Callable[..., dict[str, object]]:
    def dependency(
        authorization: str | None = Header(default=None),
    ) -> dict[str, object]:
        token = _mobile_bearer_token(authorization)
        device = state.validate_mobile_token(
            token,
            required_scope="",
        )
        if not device:
            raise HTTPException(status_code=401, detail="Mobile authentication required")
        scopes = [str(scope) for scope in device.get("scopes") or []]
        if required_scope and required_scope not in scopes:
            raise HTTPException(status_code=403, detail="Mobile scope required")
        return device

    return dependency


require_mobile_auth = require_mobile_scope(MobileScope.MONITOR)
require_mobile_control = require_mobile_scope(MobileScope.CONTROL)


config = get_config()
auth = AuthManager(password=config.dashboard_password, totp_secret=config.dashboard_totp_secret)
state = BotState(
    database_path=config.database_path,
    default_source=config.pumpfun_source,
    default_solana_rpc_url=config.solana_rpc_url,
    default_solana_wss_endpoint=config.solana_wss_endpoint,
    default_solana_logs_mentions_address=config.solana_logs_mentions_address,
    default_watch_wallet_address=config.watch_wallet_address,
    signer_daemon_url=config.live_signer_daemon_url,
    signer_daemon_auth_token=config.live_signer_daemon_auth_token,
    alert_router=AlertRouter(
        telegram_bot_token=config.telegram_bot_token,
        telegram_chat_id=config.telegram_chat_id,
        telegram_enabled=config.telegram_alerts_enabled,
        min_interval_seconds=config.telegram_alert_min_interval_seconds,
    ),
)
state.MOBILE_TOKEN_TTL_DAYS = max(1, min(365, int(config.mobile_token_ttl_days or state.MOBILE_TOKEN_TTL_DAYS)))
clients: set[WebSocket] = set()
mobile_clients: dict[WebSocket, str] = {}
mobile_realtime_sequence = 0
launch_queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
source_task: asyncio.Task | None = None
source_key: tuple[str, float, int] | None = None
solana_logs_task: asyncio.Task | None = None
solana_logs_key: tuple[str, str] | None = None
last_broadcast_payload: str | None = None
broadcast_snapshot_lock = asyncio.Lock()
latency_status: dict[str, object] = {
    "artifact_type": "cryptoarc_latency_status",
    "format_version": 1,
    "updated_at": None,
    "api_loop_ms": None,
    "pumpportal_public_ms": None,
    "pumpportal_state": "unknown",
    "pumpportal_error": "",
}


def websocket_snapshot_payload() -> dict:
    payload = state.snapshot(include_tokens=False).to_dict()
    payload["events"] = payload.get("events", [])[:25]
    return payload


async def broadcast_snapshot(force: bool = False) -> None:
    global last_broadcast_payload
    if not clients or broadcast_snapshot_lock.locked():
        return
    async with broadcast_snapshot_lock:
        payload = websocket_snapshot_payload()
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if not force and serialized == last_broadcast_payload:
            return
        last_broadcast_payload = serialized
        disconnected: list[WebSocket] = []
        for websocket in list(clients):
            try:
                await websocket.send_json(payload)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            clients.discard(websocket)


def _next_mobile_realtime_sequence() -> int:
    global mobile_realtime_sequence
    mobile_realtime_sequence += 1
    return mobile_realtime_sequence


def _current_mobile_realtime_sequence() -> int:
    if mobile_realtime_sequence < 1:
        return _next_mobile_realtime_sequence()
    return mobile_realtime_sequence


def _mobile_realtime_envelope(
    *,
    event_type: Literal["cockpit", "invalidate"],
    sequence: int,
    payload: dict[str, object],
) -> dict[str, object]:
    return MobileRealtimeEnvelope(
        event_type=event_type,
        server_time=utc_now(),
        sequence=sequence,
        payload=payload,
    ).model_dump(mode="json")


async def _send_mobile_client_update(
    websocket: WebSocket,
    device_id: str,
    sequence: int,
    *,
    forced_invalidation_reason: str = "",
) -> bool:
    device, invalidation_reason = mobile_service.websocket_device_status(device_id)
    reason = forced_invalidation_reason or invalidation_reason
    if not device or reason:
        try:
            await websocket.send_json(
                _mobile_realtime_envelope(
                    event_type="invalidate",
                    sequence=sequence,
                    payload={"reason": reason or "device_invalidated"},
                )
            )
        finally:
            await websocket.close(code=4003)
        return False
    await websocket.send_json(
        _mobile_realtime_envelope(
            event_type="cockpit",
            sequence=sequence,
            payload=state.mobile_cockpit(
                config.live_trading_enabled,
                local_auth_enabled=auth.enabled,
                device=device,
            ),
        )
    )
    return True


async def invalidate_mobile_device_connections(device_id: str, reason: str) -> None:
    if not mobile_clients:
        return
    sequence = _next_mobile_realtime_sequence()
    disconnected: list[WebSocket] = []
    for websocket, connected_device_id in list(mobile_clients.items()):
        try:
            keep = await _send_mobile_client_update(
                websocket,
                connected_device_id,
                sequence,
                forced_invalidation_reason=reason if connected_device_id == device_id else "",
            )
            if not keep:
                disconnected.append(websocket)
        except Exception:
            disconnected.append(websocket)
    for websocket in disconnected:
        mobile_clients.pop(websocket, None)


async def invalidate_all_mobile_connections(reason: str) -> None:
    if not mobile_clients:
        return
    sequence = _next_mobile_realtime_sequence()
    for websocket in list(mobile_clients):
        try:
            await websocket.send_json(
                _mobile_realtime_envelope(
                    event_type="invalidate",
                    sequence=sequence,
                    payload={"reason": reason},
                )
            )
            await websocket.close(code=4003)
        except Exception:
            pass
        finally:
            mobile_clients.pop(websocket, None)


async def broadcast_mobile_cockpit() -> None:
    if not mobile_clients:
        return
    sequence = _next_mobile_realtime_sequence()
    disconnected: list[WebSocket] = []
    for websocket, device_id in list(mobile_clients.items()):
        try:
            if not await _send_mobile_client_update(websocket, device_id, sequence):
                disconnected.append(websocket)
        except Exception:
            disconnected.append(websocket)

    for websocket in disconnected:
        mobile_clients.pop(websocket, None)


async def bot_loop() -> None:
    while True:
        try:
            await ensure_source_task()
            await ensure_solana_logs_task()
            await drain_launch_queue()
            state.tick(build_snapshot=False)
            state.run_live_autonomy(config.live_trading_enabled, local_auth_enabled=auth.enabled)
            await broadcast_snapshot()
            await broadcast_mobile_cockpit()
        except Exception as exc:
            state.record_bot_loop_error(exc)
        await asyncio.sleep(bot_tick_seconds())


async def live_audit_poll_loop() -> None:
    while True:
        try:
            state.poll_live_audits(config.live_trading_enabled)
        except Exception as exc:
            state.add_event("warning", _safe_failure_message("Live audit poller", exc))
        await asyncio.sleep(15)


async def latency_probe_loop() -> None:
    while True:
        try:
            await update_latency_status()
        except Exception as exc:
            latency_status.update(
                {
                    "updated_at": time.time(),
                    "pumpportal_state": "error",
                    "pumpportal_error": _safe_failure_message("PumpPortal latency probe", exc),
                }
            )
        await asyncio.sleep(30)


async def update_latency_status() -> dict[str, object]:
    started = time.perf_counter()
    await asyncio.sleep(0)
    api_loop_ms = round((time.perf_counter() - started) * 1000, 1)
    pumpportal_ms: float | None = None
    pumpportal_state = "disabled"
    pumpportal_error = ""
    if state.settings.launch_source == "pumpportal" and config.pumpportal_ws_url.strip():
        pumpportal_state = "probing"
        probe_started = time.perf_counter()
        try:
            async with websockets.connect(public_pumpportal_ws_url(), open_timeout=5, ping_interval=None, close_timeout=1) as websocket:
                await websocket.send(json.dumps({"method": "subscribeNewToken"}))
            pumpportal_ms = round((time.perf_counter() - probe_started) * 1000, 1)
            pumpportal_state = "connected"
        except Exception as exc:
            pumpportal_state = "error"
            pumpportal_error = _safe_failure_message("PumpPortal latency probe", exc)
    source_connection = state.source_health().get("connection", {})
    latency_status.update(
        {
            "artifact_type": "cryptoarc_latency_status",
            "format_version": 1,
            "updated_at": time.time(),
            "api_loop_ms": api_loop_ms,
            "pumpportal_public_ms": pumpportal_ms,
            "pumpportal_state": pumpportal_state,
            "pumpportal_error": pumpportal_error,
            "source_connection": source_connection,
        }
    )
    return latency_status


def public_pumpportal_ws_url() -> str:
    parts = urlsplit(config.pumpportal_ws_url)
    query = urlencode([(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key.lower() != "api-key"])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def bot_tick_seconds() -> float:
    return {
        "slow": 4.0,
        "normal": 2.0,
        "fast": 1.0,
        "turbo": 0.5,
    }.get(state.settings.trading_speed, 2.0)


_source_task_callbacks: WeakSet[asyncio.Task] = WeakSet()
_source_task_failures_reported: WeakSet[asyncio.Task] = WeakSet()
_source_task_timeouts_reported: WeakSet[asyncio.Task] = WeakSet()


def _safe_failure_message(context: str, exc: BaseException) -> str:
    return f"{context} failure ({exc.__class__.__name__})"


def _consume_source_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        if task in _source_task_failures_reported:
            return
        _source_task_failures_reported.add(task)
        state.add_event("warning", _safe_failure_message("Source cleanup", exc), subsystem="source")


async def _cancel_and_wait_source_tasks(
    named_tasks: list[tuple[str, asyncio.Task]],
    timeout_seconds: float = 1.0,
) -> list[str]:
    tracked_tasks = list(named_tasks)
    active_tasks = [(name, task) for name, task in named_tasks if not task.done()]
    done: set[asyncio.Task] = {task for _, task in tracked_tasks if task.done()}
    pending: set[asyncio.Task] = set()
    if active_tasks:
        for _, task in active_tasks:
            task.cancel()
        completed, pending = await asyncio.wait(
            {task for _, task in active_tasks},
            timeout=timeout_seconds,
        )
        done.update(completed)

    warnings: list[str] = []
    for name, task in tracked_tasks:
        if task in pending and not task.done():
            if task not in _source_task_timeouts_reported:
                warnings.append(f"{name} task did not acknowledge cancellation within {timeout_seconds:g} second")
                _source_task_timeouts_reported.add(task)
            if task not in _source_task_callbacks:
                task.add_done_callback(_consume_source_task_result)
                _source_task_callbacks.add(task)
            continue
        if task not in done and not task.done():
            continue
        try:
            task.result()
        except asyncio.CancelledError:
            continue
        except Exception as exc:
            if task in _source_task_failures_reported:
                continue
            _source_task_failures_reported.add(task)
            warnings.append(_safe_failure_message(f"{name} cleanup", exc))
    return warnings


def _record_source_stop_warnings(warnings: list[str]) -> None:
    for warning in warnings:
        state.add_event("warning", warning, subsystem="source")


def _record_background_task_failures(
    named_results: list[tuple[str, object]],
) -> None:
    for name, result in named_results:
        if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
            state.add_event(
                "warning",
                _safe_failure_message(f"{name} shutdown", result),
                subsystem="runtime",
            )


async def ensure_source_task() -> None:
    global source_key, source_task

    if source_task and source_task.done():
        try:
            error = source_task.exception()
        except asyncio.CancelledError:
            error = None
        if error:
            state.source_status.status = "error"
            state.source_status.message = _safe_failure_message("Source task", error)
            state.add_event("danger", state.source_status.message, subsystem="source")
        source_task = None
        source_key = None

    if state.status.value != "running" or not state.settings.detect_new_tokens:
        if source_task:
            previous_task = source_task
            warnings = await _cancel_and_wait_source_tasks([("Source", previous_task)])
            _record_source_stop_warnings(warnings)
            if not previous_task.done():
                state.source_status.status = "error"
                state.source_status.message = warnings[0] if warnings else "Source cancellation is still pending"
                return
            source_task = None
            source_key = None
        state.source_status.status = "offline"
        state.source_status.message = "Source is idle"
        return

    desired_key = (state.settings.launch_source, state.settings.launch_interval_seconds, state.settings.max_trade_subscriptions)
    if source_task and source_key == desired_key and not source_task.done():
        return

    if source_task:
        previous_task = source_task
        warnings = await _cancel_and_wait_source_tasks([("Source", previous_task)])
        _record_source_stop_warnings(warnings)
        if not previous_task.done():
            state.source_status.status = "error"
            state.source_status.message = warnings[0] if warnings else "Source cancellation is still pending"
            return
        source_task = None
        source_key = None

    state.source_status = SourceStatus(source=state.settings.launch_source, status="connecting", connection_requested_at=utc_now())
    source = make_source(
        name=state.settings.launch_source,
        launch_interval_seconds=state.settings.launch_interval_seconds,
        pumpportal_ws_url=config.pumpportal_ws_url,
        max_trade_subscriptions=state.settings.max_trade_subscriptions,
    )
    source_key = desired_key
    source_task = asyncio.create_task(source.run(launch_queue, state.source_status))


async def ensure_solana_logs_task() -> None:
    global solana_logs_key, solana_logs_task

    if solana_logs_task and solana_logs_task.done():
        try:
            error = solana_logs_task.exception()
        except asyncio.CancelledError:
            error = None
        if error:
            state.solana_logs_status.status = "error"
            state.solana_logs_status.message = _safe_failure_message("Solana logs verifier", error)
            state.add_event("warning", state.solana_logs_status.message, subsystem="source")
        solana_logs_task = None
        solana_logs_key = None

    endpoint = config.solana_wss_endpoint.strip()
    mentions_address = config.solana_logs_mentions_address.strip()
    state.solana_wss_endpoint = endpoint
    state.solana_logs_mentions_address = mentions_address

    if state.status.value != "running" or not state.settings.detect_new_tokens or not endpoint or not mentions_address:
        if solana_logs_task:
            previous_task = solana_logs_task
            warnings = await _cancel_and_wait_source_tasks([("Solana logs verifier", previous_task)])
            _record_source_stop_warnings(warnings)
            if not previous_task.done():
                state.solana_logs_status.status = "error"
                state.solana_logs_status.message = warnings[0] if warnings else "Solana logs cancellation is still pending"
                return
            solana_logs_task = None
            solana_logs_key = None
        state.solana_logs_status.status = "offline"
        if not endpoint:
            state.solana_logs_status.message = "Solana logs verifier is idle; SOLANA_WSS_ENDPOINT is not configured"
        elif not mentions_address:
            state.solana_logs_status.message = "Solana logs verifier is idle; SOLANA_LOGS_MENTIONS_ADDRESS is not configured"
        else:
            state.solana_logs_status.message = "Solana logs verifier is idle"
        return

    desired_key = (endpoint, mentions_address)
    if solana_logs_task and solana_logs_key == desired_key and not solana_logs_task.done():
        return

    if solana_logs_task:
        previous_task = solana_logs_task
        warnings = await _cancel_and_wait_source_tasks([("Solana logs verifier", previous_task)])
        _record_source_stop_warnings(warnings)
        if not previous_task.done():
            state.solana_logs_status.status = "error"
            state.solana_logs_status.message = warnings[0] if warnings else "Solana logs cancellation is still pending"
            return
        solana_logs_task = None
        solana_logs_key = None

    state.solana_logs_status = SourceStatus(source="solana_logs", status="connecting")
    verifier = SolanaLogsSource(wss_endpoint=endpoint, mentions_address=mentions_address)
    solana_logs_key = desired_key
    solana_logs_task = asyncio.create_task(verifier.run(launch_queue, state.solana_logs_status))


async def drain_launch_queue() -> None:
    if state.status.value != "running":
        clear_launch_queue()
        return

    active_tokens_loaded = False
    while not launch_queue.empty():
        if state.status.value != "running":
            clear_launch_queue()
            return
        event = await launch_queue.get()
        state.ingest_source_event(event, active_tokens_loaded=active_tokens_loaded)
        if event.kind == "trade" and state.settings.use_observed_prices and event.mint:
            active_tokens_loaded = True
        launch_queue.task_done()


def clear_launch_queue() -> int:
    cleared = 0
    while not launch_queue.empty():
        try:
            launch_queue.get_nowait()
            launch_queue.task_done()
            cleared += 1
        except asyncio.QueueEmpty:
            break
    return cleared


async def stop_runtime_tasks() -> dict[str, object]:
    global source_key, source_task, solana_logs_key, solana_logs_task

    source_root = source_task
    solana_logs_root = solana_logs_task
    cancelled_source = bool(source_root and not source_root.done())
    cancelled_solana_logs = bool(solana_logs_root and not solana_logs_root.done())
    named_tasks = []
    if source_root:
        named_tasks.append(("Source", source_root))
    if solana_logs_root:
        named_tasks.append(("Solana logs verifier", solana_logs_root))
    warnings = await _cancel_and_wait_source_tasks(named_tasks)
    _record_source_stop_warnings(warnings)

    if source_root is None or source_root.done():
        source_task = None
        source_key = None
        state.source_status.status = "offline"
        state.source_status.message = "Source stopped"
    else:
        state.source_status.status = "error"
        state.source_status.message = warnings[0] if warnings else "Source cancellation is still pending"
    if solana_logs_root is None or solana_logs_root.done():
        solana_logs_task = None
        solana_logs_key = None
        state.solana_logs_status.status = "offline"
        state.solana_logs_status.message = "Solana logs verifier stopped"
    else:
        state.solana_logs_status.status = "error"
        state.solana_logs_status.message = warnings[-1] if warnings else "Solana logs cancellation is still pending"
    queued_launches_dropped = clear_launch_queue()
    return {
        "source_task_cancelled": cancelled_source,
        "solana_logs_task_cancelled": cancelled_solana_logs,
        "queued_launches_dropped": queued_launches_dropped,
        "source_stop_warning": "; ".join(warnings),
    }


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global source_key, source_task, solana_logs_key, solana_logs_task

    state.enforce_live_auth_startup_policy(auth.enabled)
    task = asyncio.create_task(bot_loop())
    live_poll_task = asyncio.create_task(live_audit_poll_loop())
    latency_task = asyncio.create_task(latency_probe_loop())
    try:
        yield
    finally:
        task.cancel()
        live_poll_task.cancel()
        latency_task.cancel()
        named_tasks = []
        if source_task:
            named_tasks.append(("Source", source_task))
        if solana_logs_task:
            named_tasks.append(("Solana logs verifier", solana_logs_task))
        warnings = await _cancel_and_wait_source_tasks(named_tasks)
        _record_source_stop_warnings(warnings)
        if source_task is None or source_task.done():
            source_task = None
            source_key = None
        if solana_logs_task is None or solana_logs_task.done():
            solana_logs_task = None
            solana_logs_key = None
        background_results = await asyncio.gather(
            task,
            live_poll_task,
            latency_task,
            return_exceptions=True,
        )
        _record_background_task_failures(
            list(
                zip(
                    ("Bot loop", "Live audit poller", "Latency probe"),
                    background_results,
                    strict=True,
                )
            )
        )


app = FastAPI(title="CryptoARC v2 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in config.allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mobile_service = MobileCommandCenterService(
    state_provider=lambda: state,
    config_provider=lambda: config,
    auth_provider=lambda: auth,
    require_dashboard_auth=require_auth,
    broadcast_snapshot=broadcast_snapshot,
    broadcast_mobile_cockpit=broadcast_mobile_cockpit,
    invalidate_mobile_connections=invalidate_mobile_device_connections,
    stop_runtime_tasks=stop_runtime_tasks,
)
app.include_router(create_mobile_router(mobile_service, require_mobile_scope))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/auth/status")
async def auth_status() -> dict:
    return {"enabled": auth.enabled, "totp_enabled": auth.totp_enabled}


@app.post("/api/auth/login")
async def login(payload: LoginRequest) -> dict:
    token = auth.login(payload.password, payload.code)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": token}


@app.get("/health/deep")
async def health_deep() -> dict:
    return {
        "status": "ok",
        "mode": state.settings.mode.value if hasattr(state.settings.mode, "value") else state.settings.mode,
        "live_trading_enabled": False,
        "live_trading_env_enabled": config.live_trading_enabled,
        "live_execution_available": False,
        "database": config.database_path,
        "source": state.source_status.to_dict(),
    }


@app.get("/api/security/status", dependencies=[Depends(require_auth)])
async def security_status() -> dict:
    return {
        "auth_enabled": auth.enabled,
        "totp_enabled": auth.totp_enabled,
        "failed_attempts": auth.failed_attempts,
        "locked": auth.locked_until > time.time(),
        "session_ttl_seconds": auth.session_ttl_seconds,
        "live_trading_env_enabled": config.live_trading_enabled,
        "live_trading_requested": state.settings.live_trading_enabled,
        "effective_live_trading_enabled": False,
        "allowed_origins": [origin.strip() for origin in config.allowed_origins.split(",") if origin.strip()],
        "paper_only_boundary": True,
        "live_execution_available": False,
        "runtime_password_configurable": True,
    }


@app.get("/api/alerts/status", dependencies=[Depends(require_auth)])
async def alerts_status() -> dict:
    return state.alerts.status()


@app.post("/api/alerts/test", dependencies=[Depends(require_auth)])
async def alerts_test() -> dict:
    return state.alerts.test()


@app.get("/api/latency/status", dependencies=[Depends(require_auth)])
async def latency_status_endpoint() -> dict[str, object]:
    if not latency_status.get("updated_at"):
        await update_latency_status()
    payload = dict(latency_status)
    payload["server_time"] = time.time()
    payload["source_connection"] = state.source_health().get("connection", {})
    return payload


# The mobile pairing route is registered by create_mobile_router.
# @app.post("/api/mobile/pairing/start")
@app.post("/api/security/password", dependencies=[Depends(require_auth)])
async def update_password(payload: PasswordUpdateRequest) -> dict:
    if auth.enabled and not hmac.compare_digest(payload.current_password, auth.password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    auth.set_password(payload.new_password)
    return {"updated": True, "requires_login": True}


@app.post("/api/security/totp/setup", dependencies=[Depends(require_auth)])
async def setup_totp() -> dict:
    secret = random_totp_secret()
    issuer = "CryptoARC v2"
    account = "dashboard"
    otpauth_url = f"otpauth://totp/{issuer}:{account}?secret={secret}&issuer={issuer.replace(' ', '%20')}"
    return {"secret": secret, "otpauth_url": otpauth_url}


@app.post("/api/security/totp/verify", dependencies=[Depends(require_auth)])
async def verify_totp_setup(payload: TotpVerifyRequest) -> dict:
    if not verify_totp(payload.secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    auth.set_totp_secret(payload.secret)
    return {"enabled": True, "requires_login": True}


@app.post("/api/security/totp/disable", dependencies=[Depends(require_auth)])
async def disable_totp() -> dict:
    auth.disable_totp()
    return {"enabled": False, "requires_login": True}


@app.get("/api/snapshot", dependencies=[Depends(require_auth)])
async def snapshot() -> dict:
    return state.snapshot().to_dict()


@app.post("/api/start", dependencies=[Depends(require_auth)])
async def start() -> dict:
    mode = state.settings.mode.value if hasattr(state.settings.mode, "value") else state.settings.mode
    if mode == "live_locked" or state.settings.live_trading_enabled:
        state.add_event("danger", "Live execution is disabled by safety boundary")
        await broadcast_snapshot()
        return websocket_snapshot_payload()
    state.start()
    await ensure_source_task()
    deadline = time.perf_counter() + 1.0
    while state.source_status.status in {"connecting", "reconnecting"} and time.perf_counter() < deadline:
        await asyncio.sleep(0.05)
    await broadcast_snapshot()
    return websocket_snapshot_payload()


@app.post("/api/stop", dependencies=[Depends(require_auth)])
async def stop() -> dict:
    state.stop()
    runtime = await stop_runtime_tasks()
    await broadcast_snapshot()
    payload = websocket_snapshot_payload()
    payload["stop_runtime"] = runtime
    return payload


@app.patch("/api/settings", dependencies=[Depends(require_auth)])
async def update_settings(patch: SettingsPatch) -> dict:
    clean_patch = {key: value for key, value in patch.model_dump().items() if value is not None}
    return state.update_settings(clean_patch).to_dict()


@app.post("/api/backtest/replay", dependencies=[Depends(require_auth)])
async def replay_backtest(payload: BacktestRequest | None = None) -> dict:
    payload = payload or BacktestRequest()
    result = state.replay_backtest(limit=payload.limit, profile=payload.profile, date_from=payload.date_from, date_to=payload.date_to, replay_speed=payload.replay_speed)
    state.add_event("info", f"Replay backtest finished: {result.paper_buys} buys, {result.skips} skips")
    await broadcast_snapshot()
    return result.to_dict()


@app.post("/api/backtest/raw-replay", dependencies=[Depends(require_auth)])
async def raw_replay_backtest(payload: BacktestRequest | None = None) -> dict:
    payload = payload or BacktestRequest(replay_source="raw")
    result = state.replay_raw_source_events(limit=payload.limit, profile=payload.profile, date_from=payload.date_from, date_to=payload.date_to, replay_speed=payload.replay_speed)
    state.add_event("info", f"Raw replay finished: {result.paper_buys} buys, {result.skips} skips")
    await broadcast_snapshot()
    return result.to_dict()


@app.post("/api/backtest/compare", dependencies=[Depends(require_auth)])
async def compare_strategies() -> dict:
    result = state.compare_strategies()
    state.add_event("info", "Strategy comparison finished")
    await broadcast_snapshot()
    return result.to_dict()


@app.post("/api/backtest/ab-replay", dependencies=[Depends(require_auth)])
async def ab_strategy_replay(payload: BacktestRequest | None = None) -> dict:
    payload = payload or BacktestRequest()
    result = state.ab_strategy_replay(limit=payload.limit or state.settings.raw_replay_limit)
    state.add_event("info", "A/B strategy replay finished")
    await broadcast_snapshot()
    return result.to_dict()


@app.post("/api/backtest/v3", dependencies=[Depends(require_auth)])
async def backtest_v3(payload: BacktestRequest | None = None) -> dict:
    payload = payload or BacktestRequest()
    result = state.backtest_v3(limit=payload.limit)
    state.add_event("info", "Backtest v3 suite finished")
    await broadcast_snapshot()
    return result


@app.get("/api/backtests", dependencies=[Depends(require_auth)])
async def backtests() -> list[dict]:
    return state.backtests()


@app.get("/api/source-events", dependencies=[Depends(require_auth)])
async def source_events(
    limit: int = Query(default=80, ge=1, le=1000),
    status: str = Query(default="", max_length=40),
    mint: str = Query(default="", max_length=120),
    source: str = Query(default="", max_length=40),
    event_kind: str = Query(default="", max_length=40),
    parser_result: str = Query(default="", max_length=40),
) -> list[dict]:
    return state.source_events(limit=limit, status=status, mint=mint, source=source, event_kind=event_kind, parser_result=parser_result)


@app.get("/api/source-events/parser-replay", dependencies=[Depends(require_auth)])
async def source_parser_replay(
    limit: int = Query(default=120, ge=1, le=5000),
    profile: str = Query(default="", max_length=40),
    date_from: str = Query(default="", max_length=40),
    date_to: str = Query(default="", max_length=40),
) -> dict:
    return state.source_parser_replay_report(limit=limit, profile=profile or None, date_from=date_from or None, date_to=date_to or None)


@app.get("/api/source-events/parser-replay/export", dependencies=[Depends(require_auth)])
async def source_parser_replay_export(
    limit: int = Query(default=120, ge=1, le=5000),
    profile: str = Query(default="", max_length=40),
    date_from: str = Query(default="", max_length=40),
    date_to: str = Query(default="", max_length=40),
) -> JSONResponse:
    content = state.source_parser_replay_report(limit=limit, profile=profile or None, date_from=date_from or None, date_to=date_to or None)
    return JSONResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-source-parser-replay-{limit}.json"'},
    )


@app.get("/api/source-events/solana-logs-verification", dependencies=[Depends(require_auth)])
async def solana_logs_verification(limit: int = Query(default=500, ge=1, le=5000)) -> dict:
    return state.solana_logs_verification_report(limit=limit)


@app.get("/api/source-events/solana-logs-verification/export", dependencies=[Depends(require_auth)])
async def solana_logs_verification_export(limit: int = Query(default=500, ge=1, le=5000)) -> JSONResponse:
    content = state.solana_logs_verification_report(limit=limit)
    return JSONResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-solana-logs-verification-{limit}.json"'},
    )


@app.get("/api/source-events/source-soak", dependencies=[Depends(require_auth)])
async def source_soak_acceptance(limit: int = Query(default=500, ge=1, le=5000)) -> dict:
    return state.source_soak_acceptance_report(limit=limit)


@app.post("/api/source-events/source-soak/snapshot", dependencies=[Depends(require_auth)])
async def source_soak_acceptance_snapshot(limit: int = Query(default=500, ge=1, le=5000)) -> dict:
    result = state.record_source_soak_snapshot(limit=limit)
    await broadcast_snapshot()
    return result


@app.get("/api/source-events/source-soak/export", dependencies=[Depends(require_auth)])
async def source_soak_acceptance_export(limit: int = Query(default=500, ge=1, le=5000)) -> JSONResponse:
    content = state.source_soak_acceptance_report(limit=limit)
    return JSONResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-source-soak-{limit}.json"'},
    )


@app.get("/api/trades", dependencies=[Depends(require_auth)])
async def trades() -> list[dict]:
    return state.trades()


@app.get("/api/tokens", dependencies=[Depends(require_auth)])
async def monitor_tokens() -> list[dict]:
    return state.monitor_tokens()


@app.get("/api/market/sol-usd", dependencies=[Depends(require_auth)])
async def market_sol_usd() -> dict:
    return state.market_sol_usd()


@app.get("/api/price-observations", dependencies=[Depends(require_auth)])
async def price_observations() -> list[dict]:
    return state.price_observations()


@app.get("/api/strategy-decisions", dependencies=[Depends(require_auth)])
async def strategy_decisions() -> list[dict]:
    return state.strategy_decisions()


@app.get("/api/trade-sessions", dependencies=[Depends(require_auth)])
async def trade_sessions() -> list[dict]:
    return state.trade_sessions()


@app.get("/api/settings/versions", dependencies=[Depends(require_auth)])
async def settings_versions() -> list[dict]:
    return state.settings_versions()


@app.get("/api/analytics/performance", dependencies=[Depends(require_auth)])
async def performance_analytics() -> dict:
    return state.performance_analytics()


@app.get("/api/monitor/pnl", dependencies=[Depends(require_auth)])
async def monitor_pnl(timeframe: Literal["5m", "15m", "1h", "24h", "all"] = "all") -> dict:
    return state.monitor_pnl_summary(timeframe)


@app.get("/api/analytics/suggestions", dependencies=[Depends(require_auth)])
async def tuning_suggestions() -> list[dict]:
    return state.tuning_suggestions()


@app.post("/api/analytics/suggestions/apply", dependencies=[Depends(require_auth)])
async def apply_tuning_suggestion(payload: ApplyTuningSuggestionRequest) -> dict:
    try:
        result = state.apply_tuning_suggestion(payload.setting, payload.suggested_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Tuning suggestion could not be applied.") from exc
    await broadcast_snapshot()
    return result


@app.get("/api/experiments", dependencies=[Depends(require_auth)])
async def experiments() -> list[dict]:
    return state.experiments()


@app.post("/api/experiments", dependencies=[Depends(require_auth)])
async def create_experiment(payload: ExperimentRequest) -> dict:
    result = state.create_experiment(payload.name, payload.profile, payload.limit, payload.notes)
    await broadcast_snapshot()
    return result


@app.get("/api/trade-labels", dependencies=[Depends(require_auth)])
async def trade_labels() -> list[dict]:
    return state.trade_labels()


@app.get("/api/trade-grades", dependencies=[Depends(require_auth)])
async def trade_grades(trade_id: str = "", mode: str = "") -> list[dict]:
    return state.trade_grades(trade_id, mode)


@app.get("/api/trade-grades/{trade_id}/corrections", dependencies=[Depends(require_auth)])
async def trade_grade_corrections(trade_id: str) -> list[dict]:
    return state.trade_grade_corrections(trade_id)


@app.post("/api/trade-grades/{grade_id}/corrections", dependencies=[Depends(require_auth)])
async def correct_trade_grade(grade_id: str, payload: TradeGradeCorrectionRequest) -> dict:
    try:
        return state.correct_trade_grade(grade_id, payload.operator_intent_id, payload.patch, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Trade grade correction could not be applied.") from exc


@app.get("/api/strategy-candidates", dependencies=[Depends(require_auth)])
async def strategy_candidates() -> list[dict]:
    return state.strategy_candidates()


@app.post("/api/strategy-candidates", dependencies=[Depends(require_auth)])
async def propose_strategy_candidate(payload: StrategyCandidateRequest) -> dict:
    try:
        return state.propose_strategy_candidate(payload.base_version, payload.patch, payload.evidence_ids)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Strategy candidate request is invalid.") from exc


@app.post("/api/strategy-candidates/{candidate_id}/promote", dependencies=[Depends(require_auth)])
async def promote_strategy_candidate(candidate_id: str, payload: StrategyCandidatePromotionRequest) -> dict:
    result = state.promote_strategy_candidate(candidate_id, payload.operator_intent_id)
    if not result.get("promoted"):
        raise HTTPException(status_code=409, detail=str(result.get("blocker") or "promotion blocked"))
    await broadcast_snapshot()
    return result


@app.get("/api/trade-review/queue", dependencies=[Depends(require_auth)])
async def trade_review_queue() -> dict:
    return state.trade_review_queue()


@app.post("/api/trade-labels/{token_id}", dependencies=[Depends(require_auth)])
async def label_trade(token_id: str, payload: TradeLabelRequest) -> dict:
    result = state.label_trade(token_id, payload.label, payload.note)
    await broadcast_snapshot()
    return result


@app.get("/api/strategy-presets", dependencies=[Depends(require_auth)])
async def strategy_presets() -> list[dict]:
    return state.strategy_presets()


@app.post("/api/strategy-presets", dependencies=[Depends(require_auth)])
async def save_strategy_preset(payload: StrategyPresetRequest) -> dict:
    result = state.save_strategy_preset(payload.name, payload.description)
    await broadcast_snapshot()
    return result


@app.get("/api/replay/timeline/{token_id}", dependencies=[Depends(require_auth)])
async def replay_timeline(token_id: str) -> list[dict]:
    return state.replay_timeline(token_id)


@app.get("/api/trade-review/{token_id}", dependencies=[Depends(require_auth)])
async def trade_review_detail(token_id: str) -> dict:
    return state.trade_review_detail(token_id)


@app.post("/api/paper/recover-open", dependencies=[Depends(require_auth)])
async def recover_open_paper_positions(payload: PaperRecoveryRequest) -> dict:
    result = state.recover_open_paper_positions(payload.note)
    await broadcast_snapshot()
    return result


@app.get("/api/data/integrity", dependencies=[Depends(require_auth)])
async def data_integrity() -> dict:
    return state.data_integrity_report()


@app.get("/api/price/diagnostics", dependencies=[Depends(require_auth)])
async def price_diagnostics() -> dict:
    return state.price_diagnostics()


@app.get("/api/pumpfun/intelligence", dependencies=[Depends(require_auth)])
async def pumpfun_intelligence() -> dict:
    return state.pumpfun_report()


@app.get("/api/safety/status", dependencies=[Depends(require_auth)])
async def safety_status() -> dict:
    return state.safety_status()


@app.get("/api/readiness/status", dependencies=[Depends(require_auth)])
async def readiness_status() -> dict:
    return state.readiness_status()


@app.get("/api/pilot-risk/status", dependencies=[Depends(require_auth)])
async def pilot_risk_status() -> dict:
    return state.pilot_risk_status()


@app.post("/api/pilot-risk/policy", dependencies=[Depends(require_auth)])
async def create_pilot_risk_policy(payload: PilotRiskPolicyRequest) -> dict:
    try:
        return state.create_pilot_risk_policy(
            payload.reference_usd_per_sol,
            payload.wallet_equity_sol,
            payload.observed_at,
            payload.reference_observation_id,
            payload.operator_intent_id,
            payload.initial_slippage_pct,
        )
    except (ArithmeticError, ValueError) as exc:
        status_code = 409 if "active session" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Pilot risk policy could not be created.") from exc


@app.get("/api/production-rehearsal/status", dependencies=[Depends(require_auth)])
async def production_rehearsal_status() -> dict:
    return state.production_rehearsal_status()


@app.post("/api/production-rehearsal/evaluate", dependencies=[Depends(require_auth)])
async def evaluate_production_rehearsal(payload: ProductionRehearsalRequest) -> dict:
    return state.evaluate_production_rehearsal(payload.evidence)


@app.get("/api/sentinel/current", dependencies=[Depends(require_auth)])
async def sentinel_current() -> dict:
    return state.sentinel_current()


@app.get("/api/sentinel/history", dependencies=[Depends(require_auth)])
async def sentinel_history(limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    return state.sentinel_history(limit)


@app.get("/api/watchdog/status", dependencies=[Depends(require_auth)])
async def watchdog_status() -> dict:
    return state.watchdog_status()


@app.post("/api/watchdog/recover", dependencies=[Depends(require_auth)])
async def watchdog_recover() -> dict:
    result = state.recover_bot().to_dict()
    await broadcast_snapshot()
    return result


@app.get("/api/solana/status", dependencies=[Depends(require_auth)])
async def solana_status() -> dict:
    return state.solana_status()


@app.get("/api/live/requests", dependencies=[Depends(require_auth)])
async def live_requests() -> list[dict]:
    return state.live_requests()


@app.get("/api/live/status", dependencies=[Depends(require_auth)])
async def live_status(wallet_public_key: str = "", signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] = "browser_wallet") -> dict:
    return state.live_status(config.live_trading_enabled, wallet_public_key, signer_mode, local_auth_enabled=auth.enabled)


@app.get("/api/live/intents", dependencies=[Depends(require_auth)])
async def live_intents() -> list[dict]:
    return state.live_intents()


@app.post("/api/live/intents", dependencies=[Depends(require_auth)])
async def live_intent_create(payload: LiveIntentPayload) -> dict:
    try:
        return state.create_live_intent(
            payload.action,
            payload.mint,
            payload.amount,
            payload.denominated_in_sol,
            payload.wallet_public_key,
            payload.signer_mode,
            payload.source,
            payload.reason,
            payload.symbol,
            payload.score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Live intent request is invalid.") from exc


@app.post("/api/live/intents/generate", dependencies=[Depends(require_auth)])
async def live_intent_generate(payload: LiveIntentGeneratePayload) -> list[dict]:
    return state.generate_live_intents(payload.wallet_public_key, payload.signer_mode, payload.watchlist)


@app.post("/api/live/intents/{intent_id}/cancel", dependencies=[Depends(require_auth)])
async def live_intent_cancel(intent_id: str) -> dict:
    try:
        return state.cancel_live_intent(intent_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live intent could not be cancelled.") from exc


@app.post("/api/live/intents/{intent_id}/quote", dependencies=[Depends(require_auth)])
async def live_intent_quote(intent_id: str, payload: LiveIntentQuotePayload) -> dict:
    try:
        return state.quote_live_intent(config.live_trading_enabled, intent_id, payload.slippage_pct, payload.priority_fee_sol, payload.pool)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live intent could not be quoted.") from exc


@app.post("/api/live/intents/{intent_id}/simulate", dependencies=[Depends(require_auth)])
async def live_intent_simulate(intent_id: str, payload: LiveSimulationPayload) -> dict:
    try:
        return state.live_simulate(payload.audit_id, payload.ok, payload.warning, payload.error, payload.result)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live simulation could not be recorded.") from exc


@app.post("/api/live/intents/{intent_id}/submit", dependencies=[Depends(require_auth)])
async def live_intent_submit(intent_id: str, payload: LiveSubmitPayload) -> dict:
    try:
        return state.live_submit(payload.audit_id, payload.signature)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live submission could not be completed.") from exc


@app.post("/api/live/intents/{intent_id}/confirm", dependencies=[Depends(require_auth)])
async def live_intent_confirm(intent_id: str, payload: LiveConfirmPayload) -> dict:
    try:
        return state.live_confirm(payload.audit_id, payload.confirmation_status, payload.error)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live confirmation could not be recorded.") from exc


@app.post("/api/live/intents/{intent_id}/reconcile", dependencies=[Depends(require_auth)])
async def live_intent_reconcile(intent_id: str) -> dict:
    try:
        return state.reconcile_live_intent(intent_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live intent could not be reconciled.") from exc


@app.get("/api/live/ledger", dependencies=[Depends(require_auth)])
async def live_ledger(wallet_public_key: str = "") -> dict:
    return state.live_ledger(wallet_public_key)


@app.get("/api/live/wallet/status", dependencies=[Depends(require_auth)])
async def live_wallet_status(wallet_public_key: str = "", signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] = "browser_wallet") -> dict:
    return state.signer_status(signer_mode, wallet_public_key)


@app.get("/api/live/wallet/balance", dependencies=[Depends(require_auth)])
async def live_wallet_balance(wallet_public_key: str = "") -> dict:
    return state.live_wallet_balance(wallet_public_key)


@app.get("/api/live/hot-wallet/status", dependencies=[Depends(require_auth)])
async def live_hot_wallet_status() -> dict:
    return state.hot_wallet_status()


@app.post("/api/live/hot-wallet/import", dependencies=[Depends(require_auth)])
async def live_hot_wallet_import(payload: LiveHotWalletImportPayload) -> dict:
    try:
        return state.import_hot_wallet(payload.private_key, payload.password, payload.label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Hot wallet import was rejected.") from exc


@app.post("/api/live/hot-wallet/unlock", dependencies=[Depends(require_auth)])
async def live_hot_wallet_unlock(payload: LiveHotWalletUnlockPayload) -> dict:
    try:
        return state.unlock_hot_wallet(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Hot wallet unlock was rejected.") from exc


@app.post("/api/live/hot-wallet/lock", dependencies=[Depends(require_auth)])
async def live_hot_wallet_lock() -> dict:
    return state.lock_hot_wallet()


@app.post("/api/live/hot-wallet/clear", dependencies=[Depends(require_auth)])
async def live_hot_wallet_clear() -> dict:
    return state.clear_hot_wallet()


@app.post("/api/live/session/start", dependencies=[Depends(require_auth)])
async def live_session_start(payload: LiveSessionStartPayload) -> dict:
    return state.start_live_session(config.live_trading_enabled, payload.wallet_public_key, payload.signer_mode)


@app.post("/api/live/backend/arm", dependencies=[Depends(require_auth)])
async def live_backend_arm(payload: LiveBackendArmPayload) -> dict:
    try:
        return state.arm_live_backend(
            config.live_trading_enabled,
            payload.signer_mode,
            payload.wallet_public_key,
            local_auth_enabled=auth.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Live backend could not be armed.") from exc


@app.post("/api/live/backend/disarm", dependencies=[Depends(require_auth)])
async def live_backend_disarm() -> dict:
    return state.disarm_live_backend()


@app.post("/api/live/kill-switch", dependencies=[Depends(require_auth)])
async def live_kill_switch(payload: LiveKillSwitchPayload) -> dict:
    return state.set_live_kill_switch(payload.enabled, payload.reason)


@app.post("/api/live/override", dependencies=[Depends(require_auth)])
async def live_expert_override(payload: LiveExpertOverridePayload) -> dict:
    try:
        return state.record_expert_override(
            auth.enabled,
            payload.target_gate,
            payload.action,
            payload.reason,
            payload.wallet_public_key,
            payload.signer_mode,
        )
    except ValueError as exc:
        status_code = 403 if "auth" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live execution request was rejected.") from exc


@app.post("/api/live/session/acknowledge", dependencies=[Depends(require_auth)])
async def live_session_acknowledge() -> dict:
    return state.acknowledge_live_session()


@app.post("/api/live/quote", dependencies=[Depends(require_auth)])
async def live_quote(payload: LiveQuotePayload) -> dict:
    try:
        return state.live_quote(
            config.live_trading_enabled,
            payload.action,
            payload.mint,
            payload.amount,
            payload.denominated_in_sol,
            payload.slippage_pct,
            payload.priority_fee_sol,
            payload.pool,
            payload.wallet_public_key,
            payload.signer_mode,
            shadow_only=payload.shadow_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Live quote request was rejected.") from exc


@app.post("/api/live/simulate", dependencies=[Depends(require_auth)])
async def live_simulate(payload: LiveSimulationPayload) -> dict:
    try:
        return state.live_simulate(payload.audit_id, payload.ok, payload.warning, payload.error, payload.result)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live simulation could not be recorded.") from exc


@app.post("/api/live/submit", dependencies=[Depends(require_auth)])
async def live_submit(payload: LiveSubmitPayload) -> dict:
    try:
        return state.live_submit(payload.audit_id, payload.signature)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live submission could not be completed.") from exc


@app.post("/api/live/confirm", dependencies=[Depends(require_auth)])
async def live_confirm(payload: LiveConfirmPayload) -> dict:
    try:
        return state.live_confirm(payload.audit_id, payload.confirmation_status, payload.error)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live confirmation could not be recorded.") from exc


@app.get("/api/live/positions", dependencies=[Depends(require_auth)])
async def live_positions(wallet_public_key: str = "") -> list[dict]:
    return state.live_positions(wallet_public_key)


@app.get("/api/live/audit", dependencies=[Depends(require_auth)])
async def live_audit() -> list[dict]:
    return state.live_audit()


@app.get("/api/live/rent-recovery", dependencies=[Depends(require_auth)])
async def live_rent_recovery(wallet_public_key: str) -> dict:
    try:
        return state.live_rent_recovery_scan(wallet_public_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Rent-recovery scan was rejected.") from exc


@app.post("/api/live/rent-recovery/preview", dependencies=[Depends(require_auth)])
async def live_rent_recovery_preview(payload: LiveRentRecoveryPreviewPayload) -> dict:
    try:
        return state.live_rent_recovery_preview(payload.wallet_public_key, payload.token_accounts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Rent-recovery preview was rejected.") from exc


@app.get("/api/live/profit-sweeps", dependencies=[Depends(require_auth)])
async def live_profit_sweeps(limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    return state.profit_sweep_history(limit=limit)


@app.post("/api/live/audit/recover-unresolved", dependencies=[Depends(require_auth)])
async def live_audit_recover_unresolved() -> dict:
    return state.recover_unresolved_live_audits()


@app.post("/api/live/audit/{audit_id}/recover", dependencies=[Depends(require_auth)])
async def live_audit_recover(audit_id: str) -> dict:
    try:
        return state.recover_live_audit(audit_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live audit recovery was rejected.") from exc


@app.post("/api/live/manual-request", dependencies=[Depends(require_auth)])
async def manual_live_request(payload: LiveExecutionPayload) -> dict:
    result = state.create_manual_live_request(payload.action, payload.mint, payload.amount_sol)
    await broadcast_snapshot()
    return result


@app.post("/api/live/requests/{request_id}/review", dependencies=[Depends(require_auth)])
async def review_live_request(request_id: str, payload: LiveExecutionReviewPayload) -> dict:
    try:
        result = state.review_live_request(request_id, payload.status, payload.note)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Live execution request could not be reviewed.") from exc
    await broadcast_snapshot()
    return result


@app.get("/api/monitoring/ops", dependencies=[Depends(require_auth)])
async def operational_monitoring() -> dict:
    return state.operational_monitoring()


@app.get("/api/monitoring/workload-pressure", dependencies=[Depends(require_auth)])
async def workload_pressure() -> dict:
    return state.workload_pressure(connections=len(clients) + len(mobile_clients))


@app.get("/api/reports/operator-logs", dependencies=[Depends(require_auth)])
async def operator_logs_report(
    timeframe: str = "24h",
    level: str = "",
    subsystem: str = "",
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    return state.operator_logs_report(timeframe, level, subsystem, limit)


@app.get("/api/reports/operator-logs/export", dependencies=[Depends(require_auth)])
async def operator_logs_report_export(
    timeframe: str = "24h",
    level: str = "",
    subsystem: str = "",
    limit: int = Query(default=200, ge=1, le=1000),
) -> JSONResponse:
    return JSONResponse(
        content=state.operator_logs_report(timeframe, level, subsystem, limit),
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-operator-logs-{timeframe}.json"'},
    )


@app.get("/api/reports/session", dependencies=[Depends(require_auth)])
async def operator_session_report(timeframe: str = "24h", wallet_public_key: str = "") -> dict:
    return state.operator_session_report(timeframe, wallet_public_key)


@app.get("/api/reports/session/export", dependencies=[Depends(require_auth)])
async def operator_session_report_export(timeframe: str = "24h", wallet_public_key: str = "") -> JSONResponse:
    return JSONResponse(
        content=state.operator_session_report(timeframe, wallet_public_key),
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-session-report-{timeframe}.json"'},
    )


@app.get("/api/reports/evidence-mode-separation", dependencies=[Depends(require_auth)])
async def evidence_mode_separation_report() -> dict:
    return state.evidence_mode_separation_report()


@app.get("/api/reports/evidence-inventory", dependencies=[Depends(require_auth)])
async def evidence_inventory_report(
    wallet_public_key: str = "",
    signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] = "browser_wallet",
) -> dict:
    return state.evidence_inventory_report(
        env_live_enabled=config.live_trading_enabled,
        wallet_public_key=wallet_public_key,
        signer_mode=signer_mode,
        local_auth_enabled=auth.enabled,
    )


@app.get("/api/reports/economic-validation", dependencies=[Depends(require_auth)])
async def economic_validation_report(strategy_version: str = "") -> dict:
    return state.economic_validation_report(strategy_version=strategy_version)


@app.get("/api/reports/evidence-mode-separation/export", dependencies=[Depends(require_auth)])
async def evidence_mode_separation_report_export() -> JSONResponse:
    return JSONResponse(
        content=state.evidence_mode_separation_report(),
        headers={"Content-Disposition": 'attachment; filename="cryptoarc-evidence-mode-separation.json"'},
    )


@app.get("/api/reports/simulation-accuracy", dependencies=[Depends(require_auth)])
async def simulation_accuracy_report(wallet_public_key: str = "") -> dict:
    return state.simulation_accuracy_report(wallet_public_key)


@app.get("/api/reports/simulation-accuracy/export", dependencies=[Depends(require_auth)])
async def simulation_accuracy_report_export(wallet_public_key: str = "") -> JSONResponse:
    return JSONResponse(
        content=state.simulation_accuracy_report(wallet_public_key),
        headers={"Content-Disposition": 'attachment; filename="cryptoarc-simulation-accuracy.json"'},
    )


@app.get("/api/reports/setup-readiness", dependencies=[Depends(require_auth)])
async def setup_readiness_report() -> dict:
    return state.setup_readiness_report(config.live_trading_enabled, local_auth_enabled=auth.enabled)


@app.get("/api/reports/setup-readiness/export", dependencies=[Depends(require_auth)])
async def setup_readiness_report_export() -> JSONResponse:
    return JSONResponse(
        content=state.setup_readiness_report(config.live_trading_enabled, local_auth_enabled=auth.enabled),
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-setup-readiness.json"'},
    )


@app.get("/api/reports/release-readiness", dependencies=[Depends(require_auth)])
async def release_readiness_report() -> dict:
    return state.release_readiness_report(app.version, config.live_trading_enabled, local_auth_enabled=auth.enabled)


@app.get("/api/reports/release-readiness/export", dependencies=[Depends(require_auth)])
async def release_readiness_report_export() -> JSONResponse:
    return JSONResponse(
        content=state.release_readiness_report(app.version, config.live_trading_enabled, local_auth_enabled=auth.enabled),
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-release-readiness.json"'},
    )


@app.post("/api/reports/release-readiness/verification", dependencies=[Depends(require_auth)])
async def record_release_verification(payload: ReleaseVerificationRequest) -> dict:
    return state.record_release_verification(
        payload.app_version or app.version,
        verify_passed=payload.verify_passed,
        diff_reviewed=payload.diff_reviewed,
        docs_reviewed=payload.docs_reviewed,
        note=payload.note,
    )


@app.get("/api/reports/pilot-readiness", dependencies=[Depends(require_auth)])
async def pilot_readiness_report(wallet_public_key: str = "", signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] = "browser_wallet") -> dict:
    return state.pilot_readiness_report(config.live_trading_enabled, wallet_public_key, signer_mode, local_auth_enabled=auth.enabled)


@app.get("/api/reports/pilot-readiness/export", dependencies=[Depends(require_auth)])
async def pilot_readiness_report_export(wallet_public_key: str = "", signer_mode: Literal["browser_wallet", "local_hot_wallet", "local_signer_daemon"] = "browser_wallet") -> JSONResponse:
    return JSONResponse(
        content=state.pilot_readiness_report(config.live_trading_enabled, wallet_public_key, signer_mode, local_auth_enabled=auth.enabled),
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-pilot-readiness.json"'},
    )


@app.get("/api/reports/manual-live-proof", dependencies=[Depends(require_auth)])
async def manual_live_proof_report() -> dict:
    return state.manual_live_proof_status()


@app.get("/api/reports/manual-live-proof/export", dependencies=[Depends(require_auth)])
async def manual_live_proof_report_export() -> JSONResponse:
    return JSONResponse(
        content=state.manual_live_proof_status(),
        headers={"Content-Disposition": 'attachment; filename="cryptoarc-manual-live-proof.json"'},
    )


@app.get("/api/autonomous-pilot/status", dependencies=[Depends(require_auth)])
async def autonomous_pilot_status() -> dict:
    return state.autonomous_pilot_status()


@app.get("/api/reports/post-pilot-review", dependencies=[Depends(require_auth)])
async def post_pilot_review_status() -> dict:
    return state.post_pilot_review_status()


@app.get("/api/reports/post-pilot-review/export", dependencies=[Depends(require_auth)])
async def post_pilot_review_export() -> JSONResponse:
    return JSONResponse(
        content=state.post_pilot_review_status(),
        headers={"Content-Disposition": 'attachment; filename="cryptoarc-post-pilot-review.json"'},
    )


@app.post("/api/reports/post-pilot-review/{review_id}/decision", dependencies=[Depends(require_auth)])
async def record_post_pilot_decision(review_id: str, payload: PostPilotDecisionRequest) -> dict:
    try:
        return state.record_post_pilot_decision(review_id, payload.decision, payload.rationale, payload.authorization_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Post-pilot decision could not be recorded.") from exc


@app.get("/api/reports/post-run-review", dependencies=[Depends(require_auth)])
async def post_run_review_report(timeframe: str = "24h", wallet_public_key: str = "") -> dict:
    return state.post_run_review_report(timeframe, wallet_public_key)


@app.get("/api/reports/post-run-review/export", dependencies=[Depends(require_auth)])
async def post_run_review_report_export(timeframe: str = "24h", wallet_public_key: str = "") -> JSONResponse:
    return JSONResponse(
        content=state.post_run_review_report(timeframe, wallet_public_key),
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-post-run-review-{timeframe}.json"'},
    )


@app.get("/api/reports/outcome-explanations", dependencies=[Depends(require_auth)])
async def outcome_explanations_report(timeframe: str = "24h", limit: int = 80) -> dict:
    return state.outcome_explanations_report(timeframe, limit)


@app.get("/api/reports/outcome-explanations/export", dependencies=[Depends(require_auth)])
async def outcome_explanations_report_export(timeframe: str = "24h", limit: int = 80) -> JSONResponse:
    return JSONResponse(
        content=state.outcome_explanations_report(timeframe, limit),
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-outcome-explanations-{timeframe}.json"'},
    )


@app.get("/api/live/audit/{audit_id}/incident-export", dependencies=[Depends(require_auth)])
async def live_incident_export(audit_id: str) -> JSONResponse:
    try:
        content = state.incident_export(audit_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Incident export could not be created.") from exc
    return JSONResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-live-incident-{audit_id}.json"'},
    )


@app.post("/api/live/audit/{audit_id}/incident-export/review", dependencies=[Depends(require_auth)])
async def record_incident_export_review(audit_id: str, payload: IncidentExportReviewRequest) -> dict:
    try:
        return state.record_incident_export_review(audit_id, payload.exported, payload.reviewed, payload.note)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Incident export review could not be recorded.") from exc


@app.get("/api/source-adapters", dependencies=[Depends(require_auth)])
async def source_adapters() -> list[dict]:
    return state.source_adapters()


@app.post("/api/data/backup", dependencies=[Depends(require_auth)])
async def backup_database() -> dict:
    return state.storage.backup()


@app.post("/api/data/backup-artifact", dependencies=[Depends(require_auth)])
async def backup_artifact() -> dict:
    return state.backup_artifact()


@app.post("/api/data/restore/smoke-test", dependencies=[Depends(require_auth)])
async def restore_smoke_test() -> dict:
    try:
        result = state.restore_smoke_test()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Restore smoke test was rejected.") from exc
    await broadcast_snapshot()
    return result


@app.post("/api/data/restore/preview", dependencies=[Depends(require_auth)])
async def preview_restore_artifact(payload: RestoreArtifactPayload) -> dict:
    try:
        return state.preview_restore_artifact(payload.artifact)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Restore preview was rejected.") from exc


@app.post("/api/data/restore/confirm", dependencies=[Depends(require_auth)])
async def confirm_restore_artifact(payload: RestoreArtifactPayload) -> dict:
    try:
        result = state.confirm_restore_artifact(payload.artifact)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Restore request was rejected.") from exc
    await invalidate_all_mobile_connections("credentials_replaced")
    await broadcast_snapshot()
    return result


@app.get("/api/data/backup-restore/export", dependencies=[Depends(require_auth)])
async def backup_restore_export(entry_id: str = "") -> JSONResponse:
    try:
        content = state.backup_restore_export(entry_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail="Backup or restore export could not be created.") from exc
    suffix = entry_id or "latest"
    return JSONResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-backup-restore-{suffix}.json"'},
    )


@app.get("/api/source-health", dependencies=[Depends(require_auth)])
async def source_health() -> dict:
    return state.source_health()


@app.get("/api/source-health/export", dependencies=[Depends(require_auth)])
async def source_health_export(limit: int = Query(default=300, ge=1, le=5000)) -> JSONResponse:
    content = state.source_health_report(limit=limit)
    return JSONResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-source-health-{limit}.json"'},
    )


@app.get("/api/data/summary", dependencies=[Depends(require_auth)])
async def data_summary() -> dict:
    return state.data_summary()


@app.post("/api/data/clear/{target}", dependencies=[Depends(require_auth)])
async def clear_data(target: Literal["tokens", "events", "source_events", "backtests", "trades", "price_observations", "strategy_decisions", "trade_sessions", "settings_versions", "experiments", "trade_labels", "strategy_presets", "live_execution_requests", "live_sessions", "live_execution_audits", "live_intents", "live_ledger_positions", "source_soak_history", "all"]) -> dict:
    try:
        result = state.clear_data(target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Data clear request was rejected.") from exc
    await broadcast_snapshot()
    return result


@app.get("/api/export/{target}", dependencies=[Depends(require_auth)])
async def export_data(target: Literal["tokens", "source_events", "backtests", "trades", "price_observations", "strategy_decisions", "trade_sessions", "settings_versions", "experiments", "trade_labels", "strategy_presets", "live_execution_requests", "live_sessions", "live_execution_audits", "live_intents", "live_ledger_positions", "source_soak_history", "all"]) -> JSONResponse:
    return JSONResponse(
        content=state.export_data(target),
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-{target}.json"'},
    )


@app.websocket("/ws/mobile")
async def mobile_websocket_endpoint(websocket: WebSocket) -> None:
    ticket = websocket.query_params.get("ticket", "")
    device = mobile_service.consume_websocket_ticket(ticket)
    if not device:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    device_id = str(device.get("id") or "")
    mobile_clients[websocket] = device_id
    try:
        if not await _send_mobile_client_update(
            websocket,
            device_id,
            _current_mobile_realtime_sequence(),
        ):
            mobile_clients.pop(websocket, None)
            return
    except WebSocketDisconnect:
        mobile_clients.pop(websocket, None)
        return
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        mobile_clients.pop(websocket, None)
    except RuntimeError:
        mobile_clients.pop(websocket, None)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    if auth.enabled:
        token = websocket.query_params.get("token")
        if not auth.valid(token):
            await websocket.close(code=1008)
            return
    await websocket.accept()
    clients.add(websocket)
    try:
        await websocket.send_json(websocket_snapshot_payload())
    except WebSocketDisconnect:
        clients.discard(websocket)
        return
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        clients.discard(websocket)
    except RuntimeError:
        clients.discard(websocket)
