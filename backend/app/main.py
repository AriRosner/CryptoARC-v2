from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth import AuthManager
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


class BacktestRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=5000)
    profile: Literal["conservative", "balanced", "aggressive", "scalper", "custom"] | None = None
    replay_source: Literal["tokens", "raw"] = "tokens"


class LoginRequest(BaseModel):
    password: str = ""
    code: str = ""


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
state = BotState(database_path=config.database_path, default_source=config.pumpfun_source)
clients: set[WebSocket] = set()
launch_queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
source_task: asyncio.Task | None = None
source_key: tuple[str, float] | None = None


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
        await ensure_source_task()
        await drain_launch_queue()
        state.tick()
        await broadcast_snapshot()
        await asyncio.sleep(bot_tick_seconds())


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

    desired_key = (state.settings.launch_source, state.settings.launch_interval_seconds)
    if source_task and source_key == desired_key and not source_task.done():
        return

    if source_task:
        source_task.cancel()

    state.source_status = SourceStatus(source=state.settings.launch_source, status="connecting")
    source = make_source(
        name=state.settings.launch_source,
        launch_interval_seconds=state.settings.launch_interval_seconds,
        pumpportal_ws_url=config.pumpportal_ws_url,
    )
    source_key = desired_key
    source_task = asyncio.create_task(source.run(launch_queue, state.source_status))


async def drain_launch_queue() -> None:
    while not launch_queue.empty():
        event = await launch_queue.get()
        state.record_source_event(event.source, event.raw_payload, event.token, event.message)
        if event.token:
            state.ingest_launch(event.token)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(bot_loop())
    try:
        yield
    finally:
        if source_task:
            source_task.cancel()
        task.cancel()
        try:
            await task
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
        "live_trading_enabled": config.live_trading_enabled and state.settings.live_trading_enabled,
        "database": config.database_path,
        "source": state.source_status.to_dict(),
    }


@app.get("/api/security/status", dependencies=[Depends(require_auth)])
async def security_status() -> dict:
    return {
        "auth_enabled": auth.enabled,
        "totp_enabled": auth.totp_enabled,
        "live_trading_env_enabled": config.live_trading_enabled,
        "live_trading_requested": state.settings.live_trading_enabled,
        "effective_live_trading_enabled": config.live_trading_enabled and state.settings.live_trading_enabled,
        "allowed_origins": [origin.strip() for origin in config.allowed_origins.split(",") if origin.strip()],
        "paper_only_boundary": not (config.live_trading_enabled and state.settings.live_trading_enabled),
    }


@app.get("/api/snapshot", dependencies=[Depends(require_auth)])
async def snapshot() -> dict:
    return state.snapshot().to_dict()


@app.post("/api/start", dependencies=[Depends(require_auth)])
async def start() -> dict:
    mode = state.settings.mode.value if hasattr(state.settings.mode, "value") else state.settings.mode
    if mode == "live_locked" or state.settings.live_trading_enabled:
        state.add_event("danger", "Live execution is disabled by safety boundary")
        return state.snapshot().to_dict()
    return state.start().to_dict()


@app.post("/api/stop", dependencies=[Depends(require_auth)])
async def stop() -> dict:
    return state.stop().to_dict()


@app.patch("/api/settings", dependencies=[Depends(require_auth)])
async def update_settings(patch: SettingsPatch) -> dict:
    clean_patch = {key: value for key, value in patch.model_dump().items() if value is not None}
    return state.update_settings(clean_patch).to_dict()


@app.post("/api/backtest/replay", dependencies=[Depends(require_auth)])
async def replay_backtest(payload: BacktestRequest | None = None) -> dict:
    payload = payload or BacktestRequest()
    result = state.replay_backtest(limit=payload.limit, profile=payload.profile)
    state.add_event("info", f"Replay backtest finished: {result.paper_buys} buys, {result.skips} skips")
    await broadcast_snapshot()
    return result.to_dict()


@app.post("/api/backtest/raw-replay", dependencies=[Depends(require_auth)])
async def raw_replay_backtest(payload: BacktestRequest | None = None) -> dict:
    payload = payload or BacktestRequest(replay_source="raw")
    result = state.replay_raw_source_events(limit=payload.limit, profile=payload.profile)
    state.add_event("info", f"Raw replay finished: {result.paper_buys} buys, {result.skips} skips")
    await broadcast_snapshot()
    return result.to_dict()


@app.post("/api/backtest/compare", dependencies=[Depends(require_auth)])
async def compare_strategies() -> dict:
    result = state.compare_strategies()
    state.add_event("info", "Strategy comparison finished")
    await broadcast_snapshot()
    return result.to_dict()


@app.get("/api/backtests", dependencies=[Depends(require_auth)])
async def backtests() -> list[dict]:
    return state.backtests()


@app.get("/api/source-events", dependencies=[Depends(require_auth)])
async def source_events() -> list[dict]:
    return state.source_events()


@app.get("/api/trades", dependencies=[Depends(require_auth)])
async def trades() -> list[dict]:
    return state.trades()


@app.get("/api/source-health", dependencies=[Depends(require_auth)])
async def source_health() -> dict:
    return state.source_health()


@app.get("/api/data/summary", dependencies=[Depends(require_auth)])
async def data_summary() -> dict:
    return state.data_summary()


@app.post("/api/data/clear/{target}", dependencies=[Depends(require_auth)])
async def clear_data(target: Literal["tokens", "events", "source_events", "backtests", "trades", "all"]) -> dict:
    result = state.clear_data(target)
    await broadcast_snapshot()
    return result


@app.get("/api/export/{target}", dependencies=[Depends(require_auth)])
async def export_data(target: Literal["tokens", "source_events", "backtests", "trades", "all"]) -> JSONResponse:
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
