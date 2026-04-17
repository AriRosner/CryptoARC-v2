from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class BotMode(str, Enum):
    PREVIEW = "preview"
    PAPER = "paper"
    LIVE_LOCKED = "live_locked"


class BotStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"


class TokenStatus(str, Enum):
    DETECTED = "detected"
    ANALYZING = "analyzing"
    BUYING = "buying"
    PAPER_BOUGHT = "paper_bought"
    MONITORING = "monitoring"
    SELLING = "selling"
    PAPER_SOLD = "paper_sold"
    SKIPPED = "skipped"


@dataclass(slots=True)
class BotSettings:
    mode: BotMode = BotMode.PAPER
    launch_source: str = "mock"
    strategy_profile: str = "balanced"
    trade_size_sol: float = 0.1
    slippage_tolerance_pct: float = 1.0
    take_profit_pct: float = 50.0
    stop_loss_pct: float = 30.0
    daily_loss_cap_sol: float = 1.0
    wallet_balance_cap_sol: float = 1.0
    max_creator_hold_pct: float = 10.0
    trading_speed: str = "normal"
    max_hold_time_seconds: int = 600
    risk_tolerance: str = "medium"
    score_threshold: int = 62
    max_open_positions: int = 3
    launch_interval_seconds: float = 2.0
    paper_price_volatility_pct: float = 18.0
    max_position_ticks: int = 12
    require_live_confirmation: bool = True
    detect_new_tokens: bool = True
    auto_refresh: bool = True
    filter_honeypots: bool = True
    filter_rug_risk: bool = True
    live_trading_enabled: bool = False
    min_buy_velocity: float = 0.0
    max_sell_pressure: float = 1.0
    min_metadata_score: float = 0.0
    max_token_age_seconds: int = 120
    source_stale_seconds: int = 60
    source_max_reconnects: int = 5
    backtest_replay_limit: int = 80
    raw_replay_limit: int = 120
    enable_trade_toasts: bool = True
    compact_table_mode: bool = False
    paper_fill_delay_ticks: int = 0
    paper_fee_bps: float = 25.0
    paper_price_impact_pct: float = 0.15
    paper_failed_fill_pct: float = 0.0
    duplicate_symbol_penalty: bool = True
    strict_metadata_checks: bool = False


@dataclass(slots=True)
class TokenSignal:
    id: str
    symbol: str
    name: str
    mint: str
    creator: str
    detected_at: datetime
    status: TokenStatus = TokenStatus.DETECTED
    score: int = 0
    reason: str = "Waiting for analysis"
    amount_sol: float | None = None
    pnl_sol: float | None = None
    success_rate_pct: int = 0
    age_seconds: int = 0
    buy_velocity: float = 0.0
    sell_pressure: float = 0.0
    metadata_score: float = 0.0
    score_breakdown: list[str] = field(default_factory=list)
    entry_price: float | None = None
    current_price: float | None = None
    exit_price: float | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    ticks_held: int = 0
    peak_price: float | None = None
    trough_price: float | None = None
    unrealized_pct: float = 0.0
    creator_hold_pct: float = 0.0
    creator_launch_count: int = 0
    intelligence_tags: list[str] = field(default_factory=list)
    exit_reason: str | None = None
    honeypot_risk: bool = False
    rug_risk: bool = False
    decision_log: list[str] = field(default_factory=list)
    entry_reason: str | None = None
    entry_strategy_profile: str | None = None
    entry_risk_filters: list[str] = field(default_factory=list)
    slippage_paid_pct: float = 0.0
    highest_unrealized_pct: float = 0.0
    lowest_unrealized_pct: float = 0.0
    hold_duration_seconds: int = 0
    fill_delay_ticks_remaining: int = 0
    fee_paid_sol: float = 0.0
    price_impact_pct: float = 0.0
    fill_failed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["detected_at"] = self.detected_at.isoformat()
        payload["opened_at"] = self.opened_at.isoformat() if self.opened_at else None
        payload["closed_at"] = self.closed_at.isoformat() if self.closed_at else None
        return payload


@dataclass(slots=True)
class TradeEvent:
    id: str
    created_at: datetime
    level: str
    message: str
    token_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass(slots=True)
class SourceEvent:
    id: str
    source: str
    received_at: datetime
    raw_payload: dict[str, Any]
    normalized_token_id: str | None = None
    status: str = "raw"
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["received_at"] = self.received_at.isoformat()
        return payload


@dataclass(slots=True)
class BacktestRun:
    id: str
    created_at: datetime
    profile: str
    risk_tolerance: str
    tokens_replayed: int
    paper_buys: int
    skips: int
    wins: int
    losses: int
    win_rate_pct: int
    estimated_pnl_sol: float
    max_drawdown_sol: float
    profit_factor: float
    pnl_curve: list[float] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    comparison: list[dict[str, Any]] = field(default_factory=list)
    replay_source: str = "tokens"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass(slots=True)
class BotStats:
    total_trades: int = 0
    successful_trades: int = 0
    skipped_tokens: int = 0
    open_positions: int = 0
    closed_trades: int = 0
    win_rate_pct: int = 0
    total_pnl_sol: float = 0.0
    best_trade_sol: float = 0.0
    worst_trade_sol: float = 0.0
    average_win_sol: float = 0.0
    average_loss_sol: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_sol: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceStatus:
    source: str = "mock"
    status: str = "offline"
    message: str = "Source is idle"
    events_received: int = 0
    last_event_at: datetime | None = None
    reconnect_attempts: int = 0
    raw_events_seen: int = 0
    normalized_events: int = 0
    normalization_failures: int = 0
    events_per_minute: float = 0.0
    last_event_age_seconds: int | None = None
    health_score: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["last_event_at"] = self.last_event_at.isoformat() if self.last_event_at else None
        return payload


@dataclass(slots=True)
class TradeRecord:
    id: str
    token_id: str
    mode: str
    strategy_profile: str
    entry_price: float | None
    exit_price: float | None
    amount_sol: float | None
    pnl_sol: float | None
    entry_reason: str | None
    exit_reason: str | None
    opened_at: datetime | None
    closed_at: datetime | None
    hold_duration_seconds: int = 0
    decision_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["opened_at"] = self.opened_at.isoformat() if self.opened_at else None
        payload["closed_at"] = self.closed_at.isoformat() if self.closed_at else None
        return payload


@dataclass(slots=True)
class BotSnapshot:
    status: BotStatus
    settings: BotSettings
    tokens: list[TokenSignal] = field(default_factory=list)
    events: list[TradeEvent] = field(default_factory=list)
    stats: BotStats = field(default_factory=BotStats)
    source_status: SourceStatus = field(default_factory=SourceStatus)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "settings": asdict(self.settings),
            "tokens": [token.to_dict() for token in self.tokens],
            "events": [event.to_dict() for event in self.events],
            "stats": self.stats.to_dict(),
            "source_status": self.source_status.to_dict(),
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"
