from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


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
