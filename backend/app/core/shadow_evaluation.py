from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

from app.core.models import ShadowComparison


@dataclass(frozen=True, slots=True)
class EconomicMetrics:
    net_pnl: float
    profit_factor: float
    max_drawdown: float


@dataclass(frozen=True, slots=True)
class EconomicGateReport:
    strategy_version: str
    ready: bool
    blockers: tuple[str, ...]
    sample_count: int
    fixture_count: int
    calendar_days: int
    calendar_timezone: str
    regimes: tuple[str, ...]
    net_pnl: float
    profit_factor: float
    max_drawdown: float
    held_out: EconomicMetrics
    training: EconomicMetrics
    cost_stress: EconomicMetrics
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class EconomicValidator:
    MIN_SAMPLES = 100
    MIN_CALENDAR_DAYS = 7
    MIN_PROFIT_FACTOR = 1.20
    MODELED_EQUITY_USD = 100.0
    MAX_DRAWDOWN_PERCENT = 10.0
    STRESS_CATASTROPHE = -10.0
    CALENDAR_TIMEZONE_NAME = "America/New_York"
    CALENDAR_TIMEZONE = ZoneInfo(CALENDAR_TIMEZONE_NAME)
    VALID_EXIT_REASONS = frozenset(
        {
            "take profit",
            "trailing stop",
            "break-even stop",
            "stalled trade",
            "stop loss",
            "max hold time",
            "max position ticks",
        }
    )

    @classmethod
    def evaluate(
        cls,
        strategy_version: str,
        comparisons: Sequence[ShadowComparison],
        now: datetime,
    ) -> EconomicGateReport:
        blockers: list[str] = []
        fixture_count = sum(1 for item in comparisons if item.fixture_only)
        valid: list[ShadowComparison] = []
        for item in comparisons:
            if item.fixture_only:
                continue
            item_blocked = False
            if item.evidence_mode != "shadow" or item.contaminated:
                blockers.append("evidence_mode_contamination")
                item_blocked = True
            if item.strategy_version != strategy_version:
                blockers.append("strategy_version_mismatch")
                item_blocked = True
            if item.completed_at.tzinfo is None or item.completed_at.utcoffset() is None:
                blockers.append("naive_shadow_timestamp")
                item_blocked = True
            elif now.tzinfo is None or now.utcoffset() is None:
                blockers.append("naive_evaluation_time")
                item_blocked = True
            elif item.completed_at.astimezone(timezone.utc) > now.astimezone(timezone.utc):
                blockers.append("future_shadow_evidence")
                item_blocked = True
            if item.landing_status != "evaluated":
                blockers.append("incomplete_shadow_comparison")
                item_blocked = True
            normalized_exit_reason = str(item.exit_reason or "").strip().lower().replace("_", " ")
            if normalized_exit_reason not in cls.VALID_EXIT_REASONS:
                blockers.append("invalid_shadow_exit_reason")
                item_blocked = True
            if not item.source_evidence_ids or not item.quote_id:
                blockers.append("source_evidence_missing")
                item_blocked = True
            if item.reference_usd_per_sol <= 0:
                blockers.append("sol_usd_reference_missing")
                item_blocked = True
            if not item_blocked:
                valid.append(item)

        standard = cls._metrics(valid, cost_stress=False)
        stressed = cls._metrics(valid, cost_stress=True)
        held_out_rows = [item for item in valid if item.held_out]
        training_rows = [item for item in valid if not item.held_out]
        held_out = cls._metrics(held_out_rows, cost_stress=False)
        training = cls._metrics(training_rows, cost_stress=False)
        calendar_days = len({item.completed_at.astimezone(cls.CALENDAR_TIMEZONE).date() for item in valid})
        regimes = tuple(sorted({item.regime for item in valid if item.regime}))

        if len(valid) < cls.MIN_SAMPLES:
            blockers.append("sample_count_below_100")
        if calendar_days < cls.MIN_CALENDAR_DAYS:
            blockers.append("calendar_span_below_7_days")
        if len(regimes) < 2:
            blockers.append("multiple_regimes_required")
        if standard.net_pnl <= 0:
            blockers.append("aggregate_net_pnl_not_positive")
        if standard.profit_factor < cls.MIN_PROFIT_FACTOR:
            blockers.append("profit_factor_below_1_20")
        if standard.max_drawdown > cls.MAX_DRAWDOWN_PERCENT:
            blockers.append("max_drawdown_above_10_percent")
        if not held_out_rows or held_out.net_pnl <= 0:
            blockers.append("held_out_result_not_positive")
        elif training_rows:
            train_average = training.net_pnl / len(training_rows)
            held_out_average = held_out.net_pnl / len(held_out_rows)
            if train_average > 0 and held_out_average < train_average * 0.25:
                blockers.append("walk_forward_collapse")
        if stressed.net_pnl <= cls.STRESS_CATASTROPHE:
            blockers.append("cost_stress_catastrophic")

        deduped = tuple(dict.fromkeys(blockers))
        return EconomicGateReport(
            strategy_version=strategy_version,
            ready=not deduped,
            blockers=deduped,
            sample_count=len(valid),
            fixture_count=fixture_count,
            calendar_days=calendar_days,
            calendar_timezone=cls.CALENDAR_TIMEZONE_NAME,
            regimes=regimes,
            net_pnl=standard.net_pnl,
            profit_factor=standard.profit_factor,
            max_drawdown=standard.max_drawdown,
            held_out=held_out,
            training=training,
            cost_stress=stressed,
            generated_at=now.isoformat(),
        )

    @staticmethod
    def _metrics(rows: Sequence[ShadowComparison], *, cost_stress: bool) -> EconomicMetrics:
        pnls = [item.net_pnl_sol(cost_stress=cost_stress) for item in rows]
        wins = sum(value for value in pnls if value > 0)
        losses = abs(sum(value for value in pnls if value < 0))
        profit_factor = wins / losses if losses else (99.0 if wins > 0 else 0.0)
        running_usd = 0.0
        peak_usd = 0.0
        drawdown = 0.0
        for item, value in zip(rows, pnls):
            running_usd += value * float(item.reference_usd_per_sol)
            peak_usd = max(peak_usd, running_usd)
            drawdown_usd = peak_usd - running_usd
            drawdown = max(drawdown, (drawdown_usd / EconomicValidator.MODELED_EQUITY_USD) * 100.0)
        return EconomicMetrics(
            net_pnl=round(sum(pnls), 9),
            profit_factor=round(profit_factor, 4),
            max_drawdown=round(drawdown, 9),
        )
