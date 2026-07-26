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
