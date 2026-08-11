from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN


SOL_QUANTUM = Decimal("0.0001")


def _down(value: Decimal) -> Decimal:
    return value.quantize(SOL_QUANTUM, rounding=ROUND_DOWN)


@dataclass(frozen=True, slots=True)
class PilotRiskRequest:
    action: str
    requested_sol: Decimal
    slippage_pct: Decimal
    total_cost_sol: Decimal
    protective: bool = False


@dataclass(frozen=True, slots=True)
class PilotRiskState:
    open_positions: int = 0
    session_pnl_sol: Decimal = Decimal("0")
    daily_pnl_sol: Decimal = Decimal("0")
    cumulative_loss_sol: Decimal = Decimal("0")
    consecutive_losses: int = 0
    stopped: bool = False
    restart_requested: bool = False
    replenished: bool = False
    cap_increase_requested: bool = False


@dataclass(frozen=True, slots=True)
class PilotRiskDecision:
    allowed: bool
    blockers: tuple[str, ...]
    requires_explicit_recovery_decision: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "blockers": list(self.blockers),
            "requires_explicit_recovery_decision": self.requires_explicit_recovery_decision,
        }


@dataclass(frozen=True, slots=True)
class PilotRiskPolicy:
    policy_id: str
    policy_version: str
    created_at: datetime
    observed_at: datetime
    reference_observation_id: str
    settings_version: str
    operator_intent_id: str
    reference_usd_per_sol: Decimal
    wallet_equity_sol: Decimal
    max_trade_sol: Decimal
    max_open_positions: int
    session_loss_stop_sol: Decimal
    daily_loss_stop_sol: Decimal
    cumulative_loss_freeze_sol: Decimal
    consecutive_loss_stop: int
    initial_slippage_pct: Decimal
    max_reviewable_slippage_pct: Decimal
    external_reserve_accessible: bool = False
    automatic_restart_allowed: bool = False
    automatic_replenishment_allowed: bool = False
    automatic_cap_increase_allowed: bool = False

    @classmethod
    def create(
        cls,
        reference_usd_per_sol: Decimal,
        wallet_equity_sol: Decimal,
        observed_at: datetime,
        *,
        reference_observation_id: str = "unrecorded",
        settings_version: str = "unversioned",
        operator_intent_id: str = "unrecorded",
        initial_slippage_pct: Decimal = Decimal("3"),
    ) -> "PilotRiskPolicy":
        price = Decimal(reference_usd_per_sol)
        equity = Decimal(wallet_equity_sol)
        slippage = Decimal(initial_slippage_pct)
        if price <= 0 or equity <= 0:
            raise ValueError("reference SOL/USD price and wallet equity must be positive")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("reference observation timestamp must be timezone-aware")
        if equity * price > Decimal("100"):
            raise ValueError("pilot wallet funding exceeds $100 equivalent")
        if slippage <= 0 or slippage > Decimal("5"):
            raise ValueError("pilot slippage configuration must be above 0% and no greater than 5%")
        max_trade = _down(min(Decimal("5") / price, equity * Decimal("0.05")))
        identity = {
            "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
            "reference_observation_id": reference_observation_id,
            "settings_version": settings_version,
            "operator_intent_id": operator_intent_id,
            "reference_usd_per_sol": str(price),
            "wallet_equity_sol": str(equity),
            "initial_slippage_pct": str(slippage),
        }
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return cls(
            policy_id=f"pilot_policy_{fingerprint[:24]}",
            policy_version="micro-pilot-risk-v1",
            created_at=observed_at.astimezone(timezone.utc),
            observed_at=observed_at.astimezone(timezone.utc),
            reference_observation_id=reference_observation_id,
            settings_version=settings_version,
            operator_intent_id=operator_intent_id,
            reference_usd_per_sol=price,
            wallet_equity_sol=equity,
            max_trade_sol=max_trade,
            max_open_positions=1,
            session_loss_stop_sol=_down(Decimal("10") / price),
            daily_loss_stop_sol=_down(Decimal("10") / price),
            cumulative_loss_freeze_sol=_down(Decimal("25") / price),
            consecutive_loss_stop=3,
            initial_slippage_pct=slippage,
            max_reviewable_slippage_pct=Decimal("5"),
        )

    def cost_cap_for(self, requested_sol: Decimal) -> Decimal:
        return _down(min(Decimal("0.25") / self.reference_usd_per_sol, Decimal(requested_sol) * Decimal("0.05")))

    def evaluate_entry(self, request: PilotRiskRequest, state: PilotRiskState) -> PilotRiskDecision:
        blockers: list[str] = []
        if request.action != "buy":
            blockers.append("entry_action_required")
        if request.requested_sol <= 0 or request.requested_sol > self.max_trade_sol:
            blockers.append("trade_cap")
        if state.open_positions >= self.max_open_positions:
            blockers.append("one_position")
        if state.session_pnl_sol <= -self.session_loss_stop_sol:
            blockers.append("session_loss_stop")
        if state.daily_pnl_sol <= -self.daily_loss_stop_sol:
            blockers.append("daily_loss_stop")
        if state.cumulative_loss_sol >= self.cumulative_loss_freeze_sol:
            blockers.append("cumulative_loss_freeze")
        if state.consecutive_losses >= self.consecutive_loss_stop:
            blockers.append("consecutive_losses")
        if request.slippage_pct < 0 or request.slippage_pct > self.initial_slippage_pct:
            blockers.append("slippage_cap")
        if request.total_cost_sol < 0 or request.total_cost_sol > self.cost_cap_for(request.requested_sol):
            blockers.append("total_cost_cap")
        if state.stopped:
            blockers.append("pilot_stopped")
        if state.restart_requested:
            blockers.append("automatic_restart_forbidden")
        if state.replenished:
            blockers.append("wallet_replenishment_forbidden")
        if state.cap_increase_requested:
            blockers.append("cap_increase_forbidden")
        return PilotRiskDecision(not blockers, tuple(blockers))

    def evaluate_exit(self, request: PilotRiskRequest, state: PilotRiskState) -> PilotRiskDecision:
        del state
        blockers: list[str] = []
        if request.action != "sell":
            blockers.append("exit_action_required")
        if request.requested_sol <= 0:
            blockers.append("exit_amount_required")
        if request.slippage_pct < 0 or request.slippage_pct > self.initial_slippage_pct:
            blockers.append("slippage_cap")
        if request.total_cost_sol < 0 or request.total_cost_sol > self.cost_cap_for(request.requested_sol):
            blockers.append("total_cost_cap")
        requires_recovery = bool(request.protective and blockers)
        return PilotRiskDecision(not blockers, tuple(blockers), requires_recovery)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["observed_at"] = self.observed_at.isoformat()
        for key, value in tuple(payload.items()):
            if isinstance(value, Decimal):
                payload[key] = str(value)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "PilotRiskPolicy":
        values = dict(payload)
        values["created_at"] = datetime.fromisoformat(str(values["created_at"]))
        values["observed_at"] = datetime.fromisoformat(str(values["observed_at"]))
        for field_name in (
            "reference_usd_per_sol", "wallet_equity_sol", "max_trade_sol", "session_loss_stop_sol",
            "daily_loss_stop_sol", "cumulative_loss_freeze_sol", "initial_slippage_pct", "max_reviewable_slippage_pct",
        ):
            values[field_name] = Decimal(str(values[field_name]))
        return cls(**values)
