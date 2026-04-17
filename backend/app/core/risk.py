from __future__ import annotations

from dataclasses import dataclass

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

    def effective_score_threshold(self, settings: BotSettings) -> int:
        profile_offset = self.PROFILE_SCORE_OFFSETS.get(settings.strategy_profile, 0)
        tolerance_offset = self.RISK_SCORE_OFFSETS.get(settings.risk_tolerance, 0)
        return max(0, min(100, settings.score_threshold + profile_offset + tolerance_offset))
