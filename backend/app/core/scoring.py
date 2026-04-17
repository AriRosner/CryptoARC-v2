from __future__ import annotations

from dataclasses import dataclass

from app.core.models import TokenSignal


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: int
    success_rate_pct: int
    reason: str
    breakdown: list[str]


class ScoringEngine:
    """Explainable first-pass scoring for new token launches."""

    def score(self, token: TokenSignal) -> ScoreResult:
        score = 35
        reasons: list[str] = []

        if token.metadata_score >= 0.75:
            score += 18
            reasons.append("clean metadata")
        elif token.metadata_score < 0.35:
            score -= 18
            reasons.append("weak metadata")

        if token.buy_velocity >= 0.70:
            score += 24
            reasons.append("strong early buy velocity")
        elif token.buy_velocity < 0.25:
            score -= 16
            reasons.append("thin early demand")

        if token.sell_pressure <= 0.25:
            score += 12
            reasons.append("low sell pressure")
        elif token.sell_pressure >= 0.65:
            score -= 28
            reasons.append("heavy sell pressure")

        if token.age_seconds <= 20:
            score += 6
            reasons.append("fresh launch")

        if token.creator_hold_pct >= 20:
            score -= 18
            reasons.append("high creator concentration")
        elif 0 < token.creator_hold_pct <= 8:
            score += 5
            reasons.append("low creator concentration")

        if token.creator_launch_count > 3:
            score -= 8
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
