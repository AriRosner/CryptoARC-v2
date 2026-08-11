from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.core.models import BotSettings, BotStats, TokenSignal


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    reason: str


class RiskEngine:
    """Hard guardrails that can veto strategy decisions."""

    PROFILE_SCORE_OFFSETS = {
        "conservative": 8,
        "balanced": 0,
        "aggressive": -7,
        "scalper": -4,
    }

    RISK_SCORE_OFFSETS = {
        "low": 8,
        "medium": 0,
        "high": -6,
        "degen": -12,
    }

    @staticmethod
    def contract_session_reasons(
        strategy: Mapping[str, object],
        session_state: Mapping[str, object],
    ) -> tuple[str, ...]:
        exposure = strategy.get("exposure") if isinstance(strategy.get("exposure"), Mapping) else {}
        stops = strategy.get("stops") if isinstance(strategy.get("stops"), Mapping) else {}
        version = str(strategy.get("strategy_version") or "")
        checks = (
            (session_state.get("active_strategy_version") not in {None, "", version}, "strategy_version_changed_restart_required"),
            (int(session_state.get("open_positions") or 0) >= int(exposure.get("max_positions") or 0), "maximum_positions_reached"),
            (float(session_state.get("exposure_sol") or 0) >= float(exposure.get("max_exposure_sol") or 0), "maximum_exposure_reached"),
            (float(session_state.get("session_loss_sol") or 0) >= float(stops.get("session_loss_sol") or 0), "session_loss_stop"),
            (float(session_state.get("daily_loss_sol") or 0) >= float(stops.get("daily_loss_sol") or 0), "daily_loss_stop"),
            (float(session_state.get("cumulative_drawdown_sol") or 0) >= float(stops.get("cumulative_drawdown_sol") or 0), "cumulative_drawdown_stop"),
            (int(session_state.get("consecutive_losses") or 0) >= int(stops.get("consecutive_losses") or 0), "consecutive_loss_stop"),
        )
        return tuple(reason for failed, reason in checks if failed)

    def evaluate(
        self,
        token: TokenSignal,
        settings: BotSettings,
        stats: BotStats,
        open_positions: int,
    ) -> RiskDecision:
        if settings.trade_size_sol <= 0:
            return RiskDecision(False, "trade size must be above zero")

        if settings.trade_size_sol > settings.daily_loss_cap_sol:
            return RiskDecision(False, "trade size exceeds daily loss cap")

        if abs(min(0.0, stats.total_pnl_sol)) >= settings.daily_loss_cap_sol:
            return RiskDecision(False, "daily loss cap reached")

        if open_positions >= settings.max_open_positions:
            return RiskDecision(False, "maximum paper positions reached")

        if settings.filter_honeypots and token.honeypot_risk:
            return RiskDecision(False, "honeypot risk filter triggered")

        if settings.filter_rug_risk and token.rug_risk:
            return RiskDecision(False, "rug-pull risk filter triggered")

        if token.buy_velocity < settings.min_buy_velocity:
            return RiskDecision(False, f"buy velocity {token.buy_velocity:.2f} below minimum {settings.min_buy_velocity:.2f}")

        if token.sell_pressure > settings.max_sell_pressure:
            return RiskDecision(False, f"sell pressure {token.sell_pressure:.2f} above maximum {settings.max_sell_pressure:.2f}")

        if token.metadata_score < settings.min_metadata_score:
            return RiskDecision(False, f"metadata score {token.metadata_score:.2f} below minimum {settings.min_metadata_score:.2f}")

        entry_confirmation = self.entry_confirmation_reason(token, settings)
        if entry_confirmation:
            return RiskDecision(False, entry_confirmation)

        if token.age_seconds > settings.max_token_age_seconds:
            return RiskDecision(False, f"token age {token.age_seconds}s above maximum {settings.max_token_age_seconds}s")

        if token.creator_hold_pct > settings.max_creator_hold_pct:
            return RiskDecision(
                False,
                f"creator hold {token.creator_hold_pct:.1f}% above limit {settings.max_creator_hold_pct:.1f}%",
            )

        threshold = self.effective_score_threshold(settings)
        if token.score < threshold:
            return RiskDecision(False, f"score {token.score} below entry threshold {threshold}")

        return RiskDecision(True, "risk checks passed")

    def entry_confirmation_reason(self, token: TokenSignal, settings: BotSettings) -> str:
        if not settings.entry_confirmation_enabled:
            return ""

        observed_required = max(0, int(settings.entry_confirmation_min_observed_trades))
        observed_ok = token.observed_price_updates >= observed_required
        price_ok = token.price_confidence >= settings.entry_confirmation_min_price_confidence
        observed_confirmation = observed_ok and price_ok

        launch_confirmation = (
            token.buy_velocity >= settings.entry_confirmation_min_buy_velocity
            and token.sell_pressure <= settings.entry_confirmation_max_sell_pressure
            and token.metadata_score >= settings.entry_confirmation_min_metadata_score
        )
        seeded_launch_confirmation = launch_confirmation and (
            token.initial_buy_sol >= settings.entry_confirmation_min_initial_buy_sol
            or price_ok
            or token.buy_velocity >= min(1.0, settings.entry_confirmation_min_buy_velocity + 0.15)
        )

        if observed_confirmation or seeded_launch_confirmation:
            return ""

        return (
            "entry confirmation missing: "
            f"buy velocity {token.buy_velocity:.2f}/{settings.entry_confirmation_min_buy_velocity:.2f}, "
            f"sell pressure {token.sell_pressure:.2f}/{settings.entry_confirmation_max_sell_pressure:.2f} max, "
            f"metadata {token.metadata_score:.2f}/{settings.entry_confirmation_min_metadata_score:.2f}, "
            f"initial buy {token.initial_buy_sol:.2f}/{settings.entry_confirmation_min_initial_buy_sol:.2f} SOL, "
            f"price confidence {token.price_confidence:.2f}/{settings.entry_confirmation_min_price_confidence:.2f}, "
            f"observed trades {token.observed_price_updates}/{observed_required}"
        )

    def effective_score_threshold(self, settings: BotSettings) -> int:
        profile_offset = self.PROFILE_SCORE_OFFSETS.get(settings.strategy_profile, 0)
        tolerance_offset = self.RISK_SCORE_OFFSETS.get(settings.risk_tolerance, 0)
        return max(0, min(100, settings.score_threshold + profile_offset + tolerance_offset))
