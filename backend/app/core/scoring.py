from __future__ import annotations

from dataclasses import dataclass

from app.core.models import BotSettings, TokenSignal


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: int
    success_rate_pct: int
    reason: str
    breakdown: list[str]


class ScoringEngine:
    """Explainable first-pass scoring for new token launches."""

    def score(self, token: TokenSignal, settings: BotSettings | None = None) -> ScoreResult:
        settings = settings or BotSettings()
        score = 35
        reasons: list[str] = []

        if token.metadata_score >= 0.75:
            score += int(18 * settings.strategy_weight_metadata)
            reasons.append("clean metadata")
        elif token.metadata_score < 0.35:
            score -= int(18 * settings.strategy_weight_metadata)
            reasons.append("weak metadata")

        if token.buy_velocity >= 0.70:
            score += int(24 * settings.strategy_weight_momentum)
            reasons.append("strong early buy velocity")
        elif token.buy_velocity < 0.25:
            score -= int(16 * settings.strategy_weight_momentum)
            reasons.append("thin early demand")

        if token.sell_pressure <= 0.25:
            score += int(12 * settings.strategy_weight_pressure)
            reasons.append("low sell pressure")
        elif token.sell_pressure >= 0.65:
            score -= int(28 * settings.strategy_weight_pressure)
            reasons.append("heavy sell pressure")

        if token.age_seconds <= 20:
            score += 6
            reasons.append("fresh launch")

        if token.creator_hold_pct >= 20:
            score -= int(18 * settings.strategy_weight_creator)
            reasons.append("high creator concentration")
        elif 0 < token.creator_hold_pct <= 8:
            score += int(5 * settings.strategy_weight_creator)
            reasons.append("low creator concentration")

        if token.creator_launch_count > 3:
            score -= int(8 * settings.strategy_weight_creator)
            reasons.append("repeat creator pattern")

        if token.honeypot_risk:
            score -= 35
            reasons.append("honeypot risk")

        if token.rug_risk:
            score -= 26
            reasons.append("rug-pull risk")

        bounded_score = max(0, min(100, score))
        success_rate = max(5, min(95, int(bounded_score * 0.82)))

        if not reasons:
            reasons.append("neutral launch profile")

        return ScoreResult(
            score=bounded_score,
            success_rate_pct=success_rate,
            reason=", ".join(reasons),
            breakdown=reasons,
        )
