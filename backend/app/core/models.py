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
    launch_source: str = "pumpportal"
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
    paper_fee_bps: float = 50.0
    paper_priority_fee_sol: float = 0.00001
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
    entry_confirmation_enabled: bool = True
    entry_confirmation_min_buy_velocity: float = 0.7
    entry_confirmation_max_sell_pressure: float = 0.35
    entry_confirmation_min_metadata_score: float = 0.65
    entry_confirmation_min_initial_buy_sol: float = 0.35
    entry_confirmation_min_price_confidence: float = 0.7
    entry_confirmation_min_observed_trades: int = 1
    max_trades_per_hour_enabled: bool = True
    max_trades_per_hour: int = 30
    velocity_slippage_enabled: bool = True
    max_same_creator_buys_enabled: bool = True
    max_same_creator_buys: int = 3
    stop_on_source_degraded: bool = False
    direct_solana_paper_enabled: bool = False
    direct_solana_min_confidence: float = 0.65
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
    kill_switch_enabled: bool = False
    max_consecutive_losses_enabled: bool = False
    max_consecutive_losses: int = 5
    halt_on_low_replay_confidence: bool = False
    min_replay_confidence: int = 50
    halt_on_low_readiness: bool = False
    min_readiness_score: int = 70
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    watch_wallet_address: str = ""
    manual_live_enabled: bool = False
    manual_live_max_sol: float = 0.05
    autonomous_live_enabled: bool = False
    live_max_trade_sol: float = 0.0
    live_daily_loss_cap_sol: float = 0.0
    live_wallet_exposure_cap_sol: float = 0.0
    live_max_open_positions: int = 0
    live_max_slippage_pct: float = 0.0
    live_priority_fee_cap_sol: float = 0.0
    live_session_acknowledged: bool = False
    live_signer_mode: str = "browser_wallet"
    live_active_backend_armed: bool = False
    live_active_wallet_public_key: str = ""
    live_hot_wallet_enabled: bool = False
    live_hot_wallet_public_key: str = ""
    live_hot_wallet_label: str = ""
    profit_sweep_enabled: bool = False
    profit_sweep_mode: str = "fixed_sol"
    profit_sweep_threshold_sol: float = 0.0
    profit_sweep_amount_sol: float = 0.0
    profit_sweep_percentage: float = 0.0
    profit_sweep_min_profit_sol: float = 0.0
    profit_sweep_destination_wallet: str = ""
    profit_sweep_min_reserve_sol: float = 0.0
    profit_sweep_cooldown_seconds: int = 3600
    profit_sweep_max_per_day: int = 1


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
    exit_fee_sol: float = 0.0
    total_fees_sol: float = 0.0
    entry_provider_fee_sol: float = 0.0
    exit_provider_fee_sol: float = 0.0
    entry_network_fee_sol: float = 0.0
    exit_network_fee_sol: float = 0.0
    entry_priority_fee_sol: float = 0.0
    exit_priority_fee_sol: float = 0.0
    entry_slippage_cost_sol: float = 0.0
    entry_price_impact_cost_sol: float = 0.0
    price_impact_pct: float = 0.0
    quote_shadow_fee_sol: float = 0.0
    quote_shadow_priority_fee_sol: float = 0.0
    quote_shadow_impact_sol: float = 0.0
    quote_shadow_total_cost_sol: float = 0.0
    quote_shadow_slippage_pct: float = 0.0
    quote_shadow_status: str = ""
    wallet_public_key: str = ""
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
    subsystem: str = "app"
    operator_action: str = ""
    session_id: str = ""
    context: dict[str, Any] = field(default_factory=dict)

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
        raw = self.raw_payload or {}
        event_kind = str(raw.get("txType") or raw.get("type") or raw.get("event") or raw.get("method") or "").strip().lower()
        if not event_kind:
            if self.status == "trade" or any(key in raw for key in ("price", "solAmount", "tokenAmount", "marketCapSol")):
                event_kind = "trade"
            elif any(key in raw for key in ("mint", "tokenMint", "bondingCurveKey", "creator")):
                event_kind = "launch"
            else:
                event_kind = "unknown"
        mint = next((str(raw.get(key) or "").strip() for key in ("mint", "tokenMint", "token", "ca", "normalized_mint") if str(raw.get(key) or "").strip()), "")
        if self.status == "normalized" or self.normalized_token_id:
            parser_result = "normalized"
        elif self.status == "trade":
            parser_result = "trade"
        elif not mint:
            parser_result = "missing_mint"
        elif self.status == "raw":
            parser_result = "unparsed"
        else:
            parser_result = self.status or "unknown"
        payload["event_kind"] = event_kind
        payload["parser_result"] = parser_result
        return payload


@dataclass(slots=True)
class LiveExecutionRequest:
    id: str
    created_at: datetime
    action: str
    mint: str
    amount_sol: float
    status: str
    reason: str
    mode: str = "manual_review"
    payload: dict[str, Any] = field(default_factory=dict)
    reviewed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["reviewed_at"] = self.reviewed_at.isoformat() if self.reviewed_at else None
        return data


@dataclass(slots=True)
class LiveSession:
    id: str
    created_at: datetime
    status: str
    signer_mode: str
    wallet_public_key: str
    caps_snapshot: dict[str, Any] = field(default_factory=dict)
    acknowledged_at: datetime | None = None
    closed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["acknowledged_at"] = self.acknowledged_at.isoformat() if self.acknowledged_at else None
        payload["closed_at"] = self.closed_at.isoformat() if self.closed_at else None
        return payload


@dataclass(slots=True)
class SignerStatus:
    mode: str
    connected: bool
    wallet_public_key: str = ""
    healthy: bool = False
    can_sign: bool = False
    can_unattended_sign: bool = False
    supports_auto_sell: bool = False
    supports_auto_buy: bool = False
    disabled_reason: str = ""
    message: str = ""
    endpoint: str = ""
    transport: str = "manual"
    version: str = ""
    last_heartbeat_at: str = ""
    auth_configured: bool = False
    ready_to_submit: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LivePosition:
    mint: str
    symbol: str = ""
    token_balance: float = 0.0
    estimated_value_sol: float = 0.0
    source: str = "wallet_rpc"
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LiveExecutionIntent:
    id: str
    created_at: datetime
    updated_at: datetime
    action: str
    mint: str
    amount: str
    denominated_in_sol: bool
    signer_mode: str
    wallet_public_key: str
    status: str = "created"
    reason: str = ""
    source: str = "dashboard"
    symbol: str = ""
    score: int = 0
    priority: float = 0.0
    quote_id: str = ""
    audit_id: str = ""
    expires_at: datetime | None = None
    stale: bool = False
    warnings: list[str] = field(default_factory=list)
    autonomy_blocked: bool = False
    autonomy_blockers: list[str] = field(default_factory=list)
    operator_recommendation: str = ""
    priority_reason: str = ""
    generated_from_position: bool = False
    generated_position_id: str = ""
    generated_position_version: int = 0
    generated_position_token_balance: float = 0.0
    last_mobile_action_id: str = ""
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["updated_at"] = self.updated_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat() if self.expires_at else None
        return payload


@dataclass(slots=True)
class LiveQuote:
    id: str
    created_at: datetime
    intent_id: str
    provider: str
    action: str
    mint: str
    amount: str
    denominated_in_sol: bool
    slippage_pct: float
    priority_fee_sol: float
    pool: str
    status: str
    unsigned_transaction_base64: str = ""
    error: str = ""
    expires_at: datetime | None = None
    stale: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat() if self.expires_at else None
        return payload


@dataclass(slots=True)
class LiveSimulation:
    id: str
    created_at: datetime
    quote_id: str
    status: str
    ok: bool
    warning: str = ""
    error: str = ""
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass(slots=True)
class LiveExecutionAudit:
    id: str
    created_at: datetime
    updated_at: datetime
    action: str
    mint: str
    amount: str
    status: str
    signer_mode: str
    wallet_public_key: str
    quote: dict[str, Any] = field(default_factory=dict)
    simulation: dict[str, Any] = field(default_factory=dict)
    request: dict[str, Any] = field(default_factory=dict)
    preflight_checks: list[dict[str, Any]] = field(default_factory=list)
    caps_snapshot: dict[str, Any] = field(default_factory=dict)
    balance_snapshot: dict[str, Any] = field(default_factory=dict)
    transaction_signature: str = ""
    confirmation_status: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    final_status: str = "pending"
    intent_id: str = ""
    reconciliation_status: str = "pending"
    reconciliation: dict[str, Any] = field(default_factory=dict)
    confirmation: dict[str, Any] = field(default_factory=dict)
    confirmation_checked_at: datetime | None = None
    recovery_attempts: int = 0
    last_recovery_error: str = ""
    recommended_action: str = ""
    shadow_comparison: dict[str, Any] = field(default_factory=dict)
    execution_timing: dict[str, Any] = field(default_factory=dict)
    guarded_action_id: str = ""
    guarded_authorization: dict[str, Any] = field(default_factory=dict)
    dispatch_started_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["updated_at"] = self.updated_at.isoformat()
        payload["confirmation_checked_at"] = self.confirmation_checked_at.isoformat() if self.confirmation_checked_at else None
        payload["dispatch_started_at"] = self.dispatch_started_at.isoformat() if self.dispatch_started_at else None
        return payload


@dataclass(slots=True)
class LiveFill:
    id: str
    created_at: datetime
    audit_id: str
    intent_id: str
    action: str
    mint: str
    amount: str
    amount_sol: float = 0.0
    token_amount: float = 0.0
    price_sol: float = 0.0
    fee_sol: float = 0.0
    priority_fee_sol: float = 0.0
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass(slots=True)
class LiveLedgerPosition:
    id: str
    created_at: datetime
    updated_at: datetime
    mint: str
    wallet_public_key: str
    symbol: str = ""
    status: str = "open"
    token_balance: float = 0.0
    cost_basis_sol: float = 0.0
    realized_pnl_sol: float = 0.0
    unrealized_pnl_sol: float = 0.0
    average_entry_price_sol: float = 0.0
    total_fees_sol: float = 0.0
    total_priority_fees_sol: float = 0.0
    fills: list[dict[str, Any]] = field(default_factory=list)
    reconciliation_status: str = "pending"
    reconciliation: dict[str, Any] = field(default_factory=dict)
    review_notes: str = ""
    cost_basis_method: str = "weighted_average"
    cost_basis_breakdown: dict[str, Any] = field(default_factory=dict)
    realized_pnl_events: list[dict[str, Any]] = field(default_factory=list)
    mark_price_sol: float = 0.0
    mark_price_source: str = ""
    mark_price_confidence: float = 0.0
    mark_price_at: datetime | None = None
    mark_price_age_seconds: int | None = None
    balance_verified_at: datetime | None = None
    balance_age_seconds: int | None = None
    realized_pnl_confidence: str = "unknown"
    unrealized_pnl_confidence: str = "unknown"
    pnl_confidence_notes: list[str] = field(default_factory=list)
    stop_pct: float | None = None
    target_pct: float | None = None
    last_mobile_action_id: str = ""
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["updated_at"] = self.updated_at.isoformat()
        payload["mark_price_at"] = self.mark_price_at.isoformat() if isinstance(self.mark_price_at, datetime) else self.mark_price_at
        payload["balance_verified_at"] = self.balance_verified_at.isoformat() if isinstance(self.balance_verified_at, datetime) else self.balance_verified_at
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
    determinism_fingerprint: str = ""

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
    entry_fees_sol: float = 0.0
    exit_fees_sol: float = 0.0
    total_fees_sol: float = 0.0
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
    source: str = "pumpportal"
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
    connection_requested_at: datetime | None = None
    connected_at: datetime | None = None
    first_event_at: datetime | None = None
    pumpportal_funding_blocked: bool = False
    pumpportal_funding_message: str = ""
    pumpportal_funding_blocked_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["last_event_at"] = self.last_event_at.isoformat() if self.last_event_at else None
        payload["connection_requested_at"] = self.connection_requested_at.isoformat() if self.connection_requested_at else None
        payload["connected_at"] = self.connected_at.isoformat() if self.connected_at else None
        payload["first_event_at"] = self.first_event_at.isoformat() if self.first_event_at else None
        payload["pumpportal_funding_blocked_at"] = self.pumpportal_funding_blocked_at.isoformat() if self.pumpportal_funding_blocked_at else None
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
    entry_provider_fee_sol: float = 0.0
    exit_provider_fee_sol: float = 0.0
    entry_network_fee_sol: float = 0.0
    exit_network_fee_sol: float = 0.0
    entry_priority_fee_sol: float = 0.0
    exit_priority_fee_sol: float = 0.0
    entry_slippage_cost_sol: float = 0.0
    entry_price_impact_cost_sol: float = 0.0
    price_impact_pct: float = 0.0
    slippage_paid_pct: float = 0.0
    paper_model_cost_sol: float = 0.0
    shadow_quote_cost_sol: float = 0.0
    quote_adjustment_sol: float = 0.0
    quote_adjusted_pnl_sol: float | None = None
    simulation_accuracy_status: str = "paper_only"
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
class ExperimentRun:
    id: str
    name: str
    created_at: datetime
    settings_version_id: str
    profile: str
    replay_source: str
    result: dict[str, Any]
    fingerprint: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass(slots=True)
class TradeLabel:
    id: str
    token_id: str
    trade_id: str
    label: str
    created_at: datetime
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass(slots=True)
class StrategyPreset:
    id: str
    name: str
    created_at: datetime
    settings: dict[str, Any]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass(slots=True)
class MobileActionReceipt:
    id: str
    idempotency_key_hash: str
    device_id: str
    action_type: str
    entity_id: str
    payload: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    execution_audit_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["updated_at"] = self.updated_at.isoformat()
        return payload


@dataclass(slots=True)
class MobileDestinationAuthorization:
    id: str
    payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        payload["used_at"] = self.used_at.isoformat() if self.used_at else None
        return payload


@dataclass(slots=True)
class MobilePushRegistration:
    id: str
    device_id: str
    token_ciphertext: str
    token_fingerprint: str
    platform: str
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["updated_at"] = self.updated_at.isoformat()
        payload["revoked_at"] = self.revoked_at.isoformat() if self.revoked_at else None
        return payload

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "platform": self.platform,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }


@dataclass(slots=True)
class MobileAlertAcknowledgement:
    id: str
    device_id: str
    event_id: str
    acknowledged_at: datetime

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["acknowledged_at"] = self.acknowledged_at.isoformat()
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
