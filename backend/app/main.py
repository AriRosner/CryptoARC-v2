from __future__ import annotations

import asyncio
import hmac
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth import AuthManager, random_totp_secret, verify_totp
from app.config import get_config
from app.core.models import SourceStatus
from app.core.sources import LaunchEvent, make_source
from app.core.state import BotState


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
    max_trades_per_hour_enabled: bool | None = None
    max_trades_per_hour: int | None = Field(default=None, ge=1, le=10000)
    velocity_slippage_enabled: bool | None = None
    max_same_creator_buys_enabled: bool | None = None
    max_same_creator_buys: int | None = Field(default=None, ge=1, le=1000)
    stop_on_source_degraded: bool | None = None
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
    live_signer_mode: Literal["browser_wallet", "local_signer_daemon"] | None = None


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


class ApplyTuningSuggestionRequest(BaseModel):
    setting: str = Field(min_length=1, max_length=100)
    suggested_value: bool | int | float | str


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
    signer_mode: Literal["browser_wallet", "local_signer_daemon"] = "browser_wallet"


class LiveQuotePayload(BaseModel):
    action: Literal["buy", "sell"]
    mint: str = Field(min_length=1, max_length=100)
    amount: str = Field(min_length=1, max_length=40)
    denominated_in_sol: bool = True
    slippage_pct: float = Field(ge=0, le=100)
    priority_fee_sol: float = Field(ge=0, le=1)
    pool: Literal["pump", "raydium", "pump-amm", "launchlab", "raydium-cpmm", "bonk", "auto"] = "pump"
    wallet_public_key: str = Field(default="", max_length=100)
    signer_mode: Literal["browser_wallet", "local_signer_daemon"] = "browser_wallet"


class LiveIntentPayload(BaseModel):
    action: Literal["buy", "sell"]
    mint: str = Field(min_length=1, max_length=100)
    amount: str = Field(min_length=1, max_length=40)
    denominated_in_sol: bool = True
    wallet_public_key: str = Field(default="", max_length=100)
    signer_mode: Literal["browser_wallet", "local_signer_daemon"] = "browser_wallet"
    source: str = Field(default="manual", max_length=40)
    reason: str = Field(default="", max_length=500)
    symbol: str = Field(default="", max_length=40)
    score: int = Field(default=0, ge=0, le=100)


class LiveIntentGeneratePayload(BaseModel):
    wallet_public_key: str = Field(default="", max_length=100)
    signer_mode: Literal["browser_wallet", "local_signer_daemon"] = "browser_wallet"
    watchlist: list[str] = Field(default_factory=list, max_length=50)


class LiveIntentQuotePayload(BaseModel):
    slippage_pct: float = Field(ge=0, le=100)
    priority_fee_sol: float = Field(ge=0, le=1)
    pool: Literal["pump", "raydium", "pump-amm", "launchlab", "raydium-cpmm", "bonk", "auto"] = "pump"


class LiveSimulationPayload(BaseModel):
    audit_id: str
    ok: bool = False
    warning: str = Field(default="", max_length=500)
    error: str = Field(default="", max_length=500)
    result: dict = Field(default_factory=dict)


class LiveSubmitPayload(BaseModel):
    audit_id: str
    signature: str = Field(min_length=1, max_length=200)


class LiveConfirmPayload(BaseModel):
    audit_id: str
    confirmation_status: str = Field(default="confirmed", max_length=50)
    error: str = Field(default="", max_length=500)


def require_auth(authorization: str | None = Header(default=None), token_query: str | None = Query(default=None, alias="token")) -> None:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if token_query:
        token = token_query
    if not auth.valid(token):
        raise HTTPException(status_code=401, detail="Authentication required")


config = get_config()
auth = AuthManager(password=config.dashboard_password, totp_secret=config.dashboard_totp_secret)
state = BotState(
    database_path=config.database_path,
    default_source=config.pumpfun_source,
    default_solana_rpc_url=config.solana_rpc_url,
    default_watch_wallet_address=config.watch_wallet_address,
)
clients: set[WebSocket] = set()
launch_queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
source_task: asyncio.Task | None = None
source_key: tuple[str, float, int] | None = None


async def broadcast_snapshot() -> None:
    payload = state.snapshot().to_dict()
    disconnected: list[WebSocket] = []
    for websocket in clients:
        try:
            await websocket.send_json(payload)
        except Exception:
            disconnected.append(websocket)

    for websocket in disconnected:
        clients.discard(websocket)


async def bot_loop() -> None:
    while True:
        try:
            await ensure_source_task()
            await drain_launch_queue()
            state.tick()
            await broadcast_snapshot()
        except Exception as exc:
            state.record_bot_loop_error(exc)
        await asyncio.sleep(bot_tick_seconds())


async def live_audit_poll_loop() -> None:
    while True:
        try:
            state.poll_live_audits(config.live_trading_enabled)
        except Exception as exc:
            state.add_event("warning", f"Live audit poller warning: {exc.__class__.__name__}: {exc}")
        await asyncio.sleep(15)


def bot_tick_seconds() -> float:
    return {
        "slow": 4.0,
        "normal": 2.0,
        "fast": 1.0,
        "turbo": 0.5,
    }.get(state.settings.trading_speed, 2.0)


async def ensure_source_task() -> None:
    global source_key, source_task

    if source_task and source_task.done():
        try:
            error = source_task.exception()
        except asyncio.CancelledError:
            error = None
        if error:
            state.source_status.status = "error"
            state.source_status.message = f"Source task failed: {error.__class__.__name__}: {error}"
            state.add_event("danger", state.source_status.message)
        source_task = None
        source_key = None

    if state.status.value != "running" or not state.settings.detect_new_tokens:
        if source_task:
            source_task.cancel()
            source_task = None
            source_key = None
        state.source_status.status = "offline"
        state.source_status.message = "Source is idle"
        return

    desired_key = (state.settings.launch_source, state.settings.launch_interval_seconds, state.settings.max_trade_subscriptions)
    if source_task and source_key == desired_key and not source_task.done():
        return

    if source_task:
        source_task.cancel()

    state.source_status = SourceStatus(source=state.settings.launch_source, status="connecting")
    source = make_source(
        name=state.settings.launch_source,
        launch_interval_seconds=state.settings.launch_interval_seconds,
        pumpportal_ws_url=config.pumpportal_ws_url,
        max_trade_subscriptions=state.settings.max_trade_subscriptions,
    )
    source_key = desired_key
    source_task = asyncio.create_task(source.run(launch_queue, state.source_status))


async def drain_launch_queue() -> None:
    if state.status.value != "running":
        clear_launch_queue()
        return

    while not launch_queue.empty():
        if state.status.value != "running":
            clear_launch_queue()
            return
        event = await launch_queue.get()
        state.ingest_source_event(event)
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
    global source_key, source_task

    cancelled_source = False
    source_stop_warning = ""
    if source_task and not source_task.done():
        cancelled_source = True
        source_task.cancel()
        try:
            await asyncio.wait_for(source_task, timeout=1.0)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            source_stop_warning = "Source task did not acknowledge cancellation within 1 second"
            state.add_event("warning", source_stop_warning)
        except Exception as exc:
            source_stop_warning = f"Source stop warning: {exc.__class__.__name__}: {exc}"
            state.add_event("warning", source_stop_warning)

    source_task = None
    source_key = None
    queued_launches_dropped = clear_launch_queue()
    state.source_status.status = "offline"
    state.source_status.message = "Source stopped"
    return {
        "source_task_cancelled": cancelled_source,
        "queued_launches_dropped": queued_launches_dropped,
        "source_stop_warning": source_stop_warning,
    }


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(bot_loop())
    live_poll_task = asyncio.create_task(live_audit_poll_loop())
    try:
        yield
    finally:
        if source_task:
            source_task.cancel()
        task.cancel()
        live_poll_task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        try:
            await live_poll_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="CryptoARC v2 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in config.allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        return state.snapshot().to_dict()
    snapshot = state.start().to_dict()
    await broadcast_snapshot()
    return snapshot


@app.post("/api/stop", dependencies=[Depends(require_auth)])
async def stop() -> dict:
    state.stop()
    runtime = await stop_runtime_tasks()
    await broadcast_snapshot()
    payload = state.snapshot().to_dict()
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
async def source_events() -> list[dict]:
    return state.source_events()


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


@app.get("/api/analytics/suggestions", dependencies=[Depends(require_auth)])
async def tuning_suggestions() -> list[dict]:
    return state.tuning_suggestions()


@app.post("/api/analytics/suggestions/apply", dependencies=[Depends(require_auth)])
async def apply_tuning_suggestion(payload: ApplyTuningSuggestionRequest) -> dict:
    try:
        result = state.apply_tuning_suggestion(payload.setting, payload.suggested_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
async def live_status(wallet_public_key: str = "", signer_mode: Literal["browser_wallet", "local_signer_daemon"] = "browser_wallet") -> dict:
    return state.live_status(config.live_trading_enabled, wallet_public_key, signer_mode)


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
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/live/intents/generate", dependencies=[Depends(require_auth)])
async def live_intent_generate(payload: LiveIntentGeneratePayload) -> list[dict]:
    return state.generate_live_intents(payload.wallet_public_key, payload.signer_mode, payload.watchlist)


@app.post("/api/live/intents/{intent_id}/cancel", dependencies=[Depends(require_auth)])
async def live_intent_cancel(intent_id: str) -> dict:
    try:
        return state.cancel_live_intent(intent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@app.post("/api/live/intents/{intent_id}/quote", dependencies=[Depends(require_auth)])
async def live_intent_quote(intent_id: str, payload: LiveIntentQuotePayload) -> dict:
    try:
        return state.quote_live_intent(config.live_trading_enabled, intent_id, payload.slippage_pct, payload.priority_fee_sol, payload.pool)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@app.post("/api/live/intents/{intent_id}/simulate", dependencies=[Depends(require_auth)])
async def live_intent_simulate(intent_id: str, payload: LiveSimulationPayload) -> dict:
    try:
        return state.live_simulate(payload.audit_id, payload.ok, payload.warning, payload.error, payload.result)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@app.post("/api/live/intents/{intent_id}/submit", dependencies=[Depends(require_auth)])
async def live_intent_submit(intent_id: str, payload: LiveSubmitPayload) -> dict:
    try:
        return state.live_submit(payload.audit_id, payload.signature)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@app.post("/api/live/intents/{intent_id}/confirm", dependencies=[Depends(require_auth)])
async def live_intent_confirm(intent_id: str, payload: LiveConfirmPayload) -> dict:
    try:
        return state.live_confirm(payload.audit_id, payload.confirmation_status, payload.error)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@app.post("/api/live/intents/{intent_id}/reconcile", dependencies=[Depends(require_auth)])
async def live_intent_reconcile(intent_id: str) -> dict:
    try:
        return state.reconcile_live_intent(intent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@app.get("/api/live/ledger", dependencies=[Depends(require_auth)])
async def live_ledger(wallet_public_key: str = "") -> dict:
    return state.live_ledger(wallet_public_key)


@app.get("/api/live/wallet/status", dependencies=[Depends(require_auth)])
async def live_wallet_status(wallet_public_key: str = "", signer_mode: Literal["browser_wallet", "local_signer_daemon"] = "browser_wallet") -> dict:
    return state.signer_status(signer_mode, wallet_public_key)


@app.post("/api/live/session/start", dependencies=[Depends(require_auth)])
async def live_session_start(payload: LiveSessionStartPayload) -> dict:
    return state.start_live_session(config.live_trading_enabled, payload.wallet_public_key, payload.signer_mode)


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
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/live/simulate", dependencies=[Depends(require_auth)])
async def live_simulate(payload: LiveSimulationPayload) -> dict:
    try:
        return state.live_simulate(payload.audit_id, payload.ok, payload.warning, payload.error, payload.result)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@app.post("/api/live/submit", dependencies=[Depends(require_auth)])
async def live_submit(payload: LiveSubmitPayload) -> dict:
    try:
        return state.live_submit(payload.audit_id, payload.signature)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@app.post("/api/live/confirm", dependencies=[Depends(require_auth)])
async def live_confirm(payload: LiveConfirmPayload) -> dict:
    try:
        return state.live_confirm(payload.audit_id, payload.confirmation_status, payload.error)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@app.get("/api/live/positions", dependencies=[Depends(require_auth)])
async def live_positions(wallet_public_key: str = "") -> list[dict]:
    return state.live_positions(wallet_public_key)


@app.get("/api/live/audit", dependencies=[Depends(require_auth)])
async def live_audit() -> list[dict]:
    return state.live_audit()


@app.post("/api/live/audit/recover-unresolved", dependencies=[Depends(require_auth)])
async def live_audit_recover_unresolved() -> dict:
    return state.recover_unresolved_live_audits()


@app.post("/api/live/audit/{audit_id}/recover", dependencies=[Depends(require_auth)])
async def live_audit_recover(audit_id: str) -> dict:
    try:
        return state.recover_live_audit(audit_id)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


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
        message = str(exc)
        raise HTTPException(status_code=404 if "not found" in message.lower() else 400, detail=message) from exc
    await broadcast_snapshot()
    return result


@app.get("/api/monitoring/ops", dependencies=[Depends(require_auth)])
async def operational_monitoring() -> dict:
    return state.operational_monitoring()


@app.get("/api/source-adapters", dependencies=[Depends(require_auth)])
async def source_adapters() -> list[dict]:
    return state.source_adapters()


@app.post("/api/data/backup", dependencies=[Depends(require_auth)])
async def backup_database() -> dict:
    return state.storage.backup()


@app.get("/api/source-health", dependencies=[Depends(require_auth)])
async def source_health() -> dict:
    return state.source_health()


@app.get("/api/data/summary", dependencies=[Depends(require_auth)])
async def data_summary() -> dict:
    return state.data_summary()


@app.post("/api/data/clear/{target}", dependencies=[Depends(require_auth)])
async def clear_data(target: Literal["tokens", "events", "source_events", "backtests", "trades", "price_observations", "strategy_decisions", "trade_sessions", "settings_versions", "experiments", "trade_labels", "strategy_presets", "live_execution_requests", "live_sessions", "live_execution_audits", "live_intents", "live_ledger_positions", "all"]) -> dict:
    result = state.clear_data(target)
    await broadcast_snapshot()
    return result


@app.get("/api/export/{target}", dependencies=[Depends(require_auth)])
async def export_data(target: Literal["tokens", "source_events", "backtests", "trades", "price_observations", "strategy_decisions", "trade_sessions", "settings_versions", "experiments", "trade_labels", "strategy_presets", "live_execution_requests", "live_sessions", "live_execution_audits", "live_intents", "live_ledger_positions", "all"]) -> JSONResponse:
    return JSONResponse(
        content=state.export_data(target),
        headers={"Content-Disposition": f'attachment; filename="cryptoarc-{target}.json"'},
    )


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
        await websocket.send_json(state.snapshot().to_dict())
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
