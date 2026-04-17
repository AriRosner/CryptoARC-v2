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
    minimum_hold_time_seconds: int = 0
    risk_tolerance: str = "medium"
    score_threshold: int = 62
    max_open_positions: int = 3
    launch_interval_seconds: float = 2.0
    paper_price_volatility_pct: float = 18.0
    max_position_ticks: int = 40
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
    use_observed_prices: bool = True
    max_trade_subscriptions: int = 60
    min_price_confidence: float = 0.45
    max_first_observed_move_pct: float = 500.0
    prefer_market_cap_price: bool = True
    trailing_stop_enabled: bool = False
    trailing_stop_pct: float = 18.0
    partial_take_profit_enabled: bool = False
    partial_take_profit_pct: float = 25.0
    partial_take_profit_fraction: float = 0.5
    cooldown_after_loss_enabled: bool = False
    cooldown_after_loss_seconds: int = 0
    max_trades_per_hour_enabled: bool = True
    max_trades_per_hour: int = 30
    velocity_slippage_enabled: bool = True
    max_same_creator_buys_enabled: bool = True
    max_same_creator_buys: int = 3
    stop_on_source_degraded: bool = False
    max_rejected_price_streak_enabled: bool = True
    max_rejected_price_streak: int = 5
    strategy_weight_metadata: float = 1.0
    strategy_weight_momentum: float = 1.0
    strategy_weight_pressure: float = 1.0
    strategy_weight_creator: float = 1.0
    break_even_stop_enabled: bool = False
    break_even_after_profit_pct: float = 15.0
    stalled_trade_exit_enabled: bool = False
    stalled_trade_seconds: int = 90
    stalled_trade_min_move_pct: float = 3.0
    sell_pressure_exit_enabled: bool = False
    sell_pressure_exit_threshold: float = 0.65


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
    partial_take_profit_taken: bool = False
    realized_pnl_sol: float = 0.0
    remaining_fraction: float = 1.0
    rejected_price_streak: int = 0
    market_cap_sol: float = 0.0
    initial_buy_sol: float = 0.0
    bonding_curve: str = ""
    metadata_uri: str = ""
    price_source: str = "simulated"
    price_confidence: float = 0.0
    price_reject_reason: str = ""
    observed_price_updates: int = 0
    last_observed_trade_at: datetime | None = None
    settings_version_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["detected_at"] = self.detected_at.isoformat()
        payload["opened_at"] = self.opened_at.isoformat() if self.opened_at else None
        payload["closed_at"] = self.closed_at.isoformat() if self.closed_at else None
        payload["last_observed_trade_at"] = self.last_observed_trade_at.isoformat() if self.last_observed_trade_at else None
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
class PriceObservation:
    id: str
    source: str
    mint: str
    observed_at: datetime
    price: float | None
    price_source: str
    confidence: float
    accepted: bool
    reason: str = ""
    market_cap_sol: float | None = None
    sol_amount: float | None = None
    trade_side: str | None = None
    token_id: str | None = None
    direct_price: float | None = None
    market_cap_price: float | None = None
    virtual_reserve_price: float | None = None
    selected_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["observed_at"] = self.observed_at.isoformat()
        return payload


@dataclass(slots=True)
class StrategyDecisionRecord:
    id: str
    token_id: str
    mint: str
    created_at: datetime
    engine_version: str
    profile: str
    score: int
    allowed: bool
    action: str
    reason: str
    risk_reason: str
    snapshot: dict[str, Any] = field(default_factory=dict)
    score_breakdown: list[str] = field(default_factory=list)
    decision_log: list[str] = field(default_factory=list)
    settings_version_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass(slots=True)
class TradeSession:
    id: str
    token_id: str
    mint: str
    symbol: str
    strategy_profile: str
    status: str
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    amount_sol: float | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    pnl_sol: float | None = None
    realized_pnl_sol: float = 0.0
    remaining_fraction: float = 1.0
    exit_reason: str | None = None
    lifecycle: list[dict[str, Any]] = field(default_factory=list)
    settings_version_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["opened_at"] = self.opened_at.isoformat() if self.opened_at else None
        payload["closed_at"] = self.closed_at.isoformat() if self.closed_at else None
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
    scratches: int = 0
    gross_win_rate_pct: int = 0
    scratch_rate_pct: int = 0
    avg_hold_seconds: int = 0
    best_trade_sol: float = 0.0
    worst_trade_sol: float = 0.0
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
    losing_trades: int = 0
    scratch_trades: int = 0
    skipped_tokens: int = 0
    open_positions: int = 0
    closed_trades: int = 0
    win_rate_pct: int = 0
    gross_win_rate_pct: int = 0
    scratch_rate_pct: int = 0
    scratch_threshold_sol: float = 0.001
    total_pnl_sol: float = 0.0
    best_trade_sol: float = 0.0
    worst_trade_sol: float = 0.0
    average_win_sol: float = 0.0
    average_loss_sol: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_sol: float = 0.0
    avg_hold_seconds: int = 0

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
    launch_events_seen: int = 0
    trade_events_seen: int = 0
    status_events_seen: int = 0
    active_trade_subscriptions: int = 0
    dropped_trade_subscriptions: int = 0

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
    lifecycle_status: str = "closed"
    entry_fee_sol: float = 0.0
    exit_fee_sol: float = 0.0
    price_impact_pct: float = 0.0
    slippage_paid_pct: float = 0.0
    source_price_confidence: float = 0.0
    decision_log: list[str] = field(default_factory=list)
    settings_version_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["opened_at"] = self.opened_at.isoformat() if self.opened_at else None
        payload["closed_at"] = self.closed_at.isoformat() if self.closed_at else None
        return payload


@dataclass(slots=True)
class SettingsVersion:
    id: str
    created_at: datetime
    settings: dict[str, Any]
    label: str = ""
    changed_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
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
