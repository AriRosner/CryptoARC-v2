from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MobileScope:
    MONITOR = "mobile:monitor"
    CONTROL = "mobile:control"
    PORTFOLIO_READ = "mobile:portfolio:read"
    TRADE_REVIEW = "mobile:trade:review"
    TRADE_EXECUTE = "mobile:trade:execute"
    WALLET_READ = "mobile:wallet:read"
    TREASURY_REQUEST = "mobile:treasury:request"
    ALERTS = "mobile:alerts"
    DIAGNOSTICS = "mobile:diagnostics"


class MobileRealtimeEnvelope(BaseModel):
    event_type: Literal["cockpit", "portfolio", "position", "trade", "wallet", "alert", "invalidate"]
    schema_version: Literal[1] = 1
    server_time: datetime
    sequence: int = Field(ge=1)
    entity_id: str = ""
    payload: dict[str, Any]


class MobileActionStatus(str, Enum):
    PENDING = "pending"
    VERIFYING = "verifying"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REVIEW_REQUIRED = "review_required"


class MobileAlert(BaseModel):
    event_id: str
    created_at: datetime
    severity: Literal["info", "warning", "danger", "error"]
    subsystem: str
    title: str
    summary: str
    route: str
    acknowledged: bool
    acknowledged_at: datetime | None = None


class MobileAlertsPayload(BaseModel):
    artifact_type: Literal["cryptoarc_mobile_alerts"] = "cryptoarc_mobile_alerts"
    format_version: Literal[1] = 1
    generated_at: datetime
    alerts: list[MobileAlert]


class MobileDiagnosticFreshness(BaseModel):
    status: Literal["fresh", "stale", "unavailable"]
    age_seconds: int | None = Field(default=None, ge=0)
    stale_after_seconds: int = Field(ge=1)


class MobileDiagnosticCheck(BaseModel):
    id: Literal[
        "tunnel",
        "api",
        "websocket",
        "token_scope",
        "push",
        "telegram",
        "clock_drift",
        "snapshot_age",
        "rpc",
        "signer",
    ]
    label: str
    status: Literal["healthy", "warning", "blocked", "unavailable"]
    detail: str
    observed_at: datetime | None = None


class MobileRecoveryAction(BaseModel):
    id: str
    label: str
    detail: str
    enabled: bool


class MobileDiagnosticsPayload(BaseModel):
    artifact_type: Literal["cryptoarc_mobile_diagnostics"] = (
        "cryptoarc_mobile_diagnostics"
    )
    format_version: Literal[1] = 1
    generated_at: datetime
    freshness: MobileDiagnosticFreshness
    checks: list[MobileDiagnosticCheck] = Field(max_length=10)
    recovery_actions: list[MobileRecoveryAction] = Field(max_length=8)


class MobileTradeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal | Literal["100%"]
    slippage_pct: Decimal = Field(gt=0)
    stop_pct: Decimal = Field(gt=0, le=100)
    target_pct: Decimal = Field(gt=0, le=100)


class MobileGuardedActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    draft: MobileTradeDraft
    escalation_acknowledged: bool = False


class MobileRejectTradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class MobileAdjustExitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    stop_pct: Decimal = Field(gt=0, le=100)
    target_pct: Decimal = Field(gt=0, le=100)
    escalation_acknowledged: bool = False


class MobilePositionCloseRequest(MobileGuardedActionRequest):
    intent_id: str = Field(min_length=1, max_length=120)
    position_version: int = Field(ge=1)


class MobileActionReceipt(BaseModel):
    action_id: str
    status: MobileActionStatus
    submitted_at: datetime
    updated_at: datetime
    operator_message: str
    reconcile_after_ms: int = Field(ge=250, le=30000)


class MobileDestinationAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=120)
    action: Literal["withdrawal", "profit_sweep", "rent_recovery"]
    address: str = Field(min_length=32, max_length=100)
    asset: str = Field(min_length=1, max_length=16)
    max_amount: Decimal = Field(gt=0)
    expires_in_seconds: int = Field(ge=1, le=900)
    purpose: str = Field(min_length=1, max_length=240)


class MobileTreasuryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorization_id: str = Field(min_length=1, max_length=120)
    preview_id: str = Field(default="", max_length=120)
    address: str = Field(min_length=32, max_length=100)
    asset: str = Field(min_length=1, max_length=16)
    amount: Decimal = Field(gt=0)
    token_accounts: list[str] = Field(default_factory=list, max_length=64)


class MobileTreasuryPreview(BaseModel):
    preview_id: str
    action: Literal["withdrawal", "profit_sweep", "rent_recovery"]
    destination: str
    asset: str
    amount: Decimal
    expected_fee_sol: Decimal
    remaining_balance_sol: Decimal
    authorization_id: str
    expires_at: datetime
    warnings: list[str]
    token_accounts: list[str] = Field(default_factory=list, max_length=64)
    source_wallet_public_key: str
    purpose: str


class MobileFreshness(BaseModel):
    status: Literal["fresh", "stale", "unavailable"]
    generated_at: datetime
    age_seconds: int = Field(ge=0)
    stale_after_seconds: int = Field(ge=1)
    approximate_pnl: bool


class MobilePortfolioSummary(BaseModel):
    equity_sol: float | None = None
    tracked_value_sol: float
    cost_basis_sol: float
    net_pnl_sol: float
    realized_pnl_sol: float
    unrealized_pnl_sol: float
    selected_period_realized_pnl_sol: float
    win_rate_pct: int = Field(ge=0, le=100)
    health_score: int = Field(ge=0, le=100)
    open_positions: int = Field(ge=0)
    closed_trades: int = Field(ge=0)


class MobilePortfolioCurrentSnapshot(BaseModel):
    generated_at: datetime
    tracked_value_sol: float
    cost_basis_sol: float
    realized_pnl_sol: float
    unrealized_pnl_sol: float
    net_pnl_sol: float
    paper_pnl_sol: float
    live_pnl_sol: float
    open_positions: int = Field(ge=0)
    approximate: bool


class MobilePortfolioPoint(BaseModel):
    at: datetime
    net_pnl_sol: float
    paper_pnl_sol: float
    live_pnl_sol: float
    current_snapshot: bool
    approximate: bool


class MobileAllocation(BaseModel):
    key: str
    label: str
    value_sol: float
    percentage: float = Field(ge=0, le=100)
    mode: Literal["paper", "live"]


class MobilePositionSummary(BaseModel):
    id: str
    mode: Literal["paper", "live"]
    symbol: str
    mint: str
    status: str
    opened_at: datetime | None = None
    updated_at: datetime
    cost_basis_sol: float
    value_sol: float
    realized_pnl_sol: float
    unrealized_pnl_sol: float
    pnl_pct: float
    pnl_approximate: bool
    mark_fresh: bool
    mark_age_seconds: int | None = Field(default=None, ge=0)
    mark_source: str


class MobilePositionMark(BaseModel):
    price_sol: float
    source: str
    confidence: float = Field(ge=0, le=1)
    observed_at: datetime | None = None
    age_seconds: int | None = Field(default=None, ge=0)
    fresh: bool


class MobilePositionPnl(BaseModel):
    realized_sol: float
    unrealized_sol: float
    total_sol: float
    percentage: float
    approximate: bool
    confidence: str
    notes: list[str]


class MobilePositionAllowedActions(BaseModel):
    adjust_exit: bool
    close: bool
    reason: str


class MobilePreparedClose(BaseModel):
    intent_id: str
    intent_version: int = Field(ge=1)
    position_version: int = Field(ge=1)
    amount: Literal["100%"]
    slippage_pct: float = Field(gt=0)
    expires_at: datetime | None = None


class MobilePositionDetail(BaseModel):
    id: str
    mode: Literal["paper", "live"]
    symbol: str
    mint: str
    status: str
    opened_at: datetime | None = None
    updated_at: datetime
    wallet_label: str
    token_balance: float
    cost_basis_sol: float
    value_sol: float
    mark: MobilePositionMark
    pnl: MobilePositionPnl
    reconciliation_status: str
    version: int = Field(ge=1)
    stop_pct: float
    target_pct: float
    prepared_close: MobilePreparedClose | None = None
    allowed_actions: MobilePositionAllowedActions


class MobilePositionsPayload(BaseModel):
    artifact_type: Literal["cryptoarc_mobile_positions"] = "cryptoarc_mobile_positions"
    format_version: Literal[1] = 1
    generated_at: datetime
    freshness: MobileFreshness
    positions: list[MobilePositionSummary]


class MobilePortfolioPayload(BaseModel):
    artifact_type: Literal["cryptoarc_mobile_portfolio"] = "cryptoarc_mobile_portfolio"
    format_version: Literal[1] = 1
    generated_at: datetime
    timeframe: Literal["1d", "1w", "1m", "all"]
    freshness: MobileFreshness
    summary: MobilePortfolioSummary
    current_snapshot: MobilePortfolioCurrentSnapshot
    series: list[MobilePortfolioPoint]
    allocation: list[MobileAllocation]
    positions: list[MobilePositionSummary]
