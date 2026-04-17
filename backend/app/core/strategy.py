from __future__ import annotations

from dataclasses import dataclass, field

from app.core.models import BotSettings, BotStats, TokenSignal
from app.core.risk import RiskDecision, RiskEngine
from app.core.scoring import ScoreResult, ScoringEngine


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    allowed: bool
    action: str
    reason: str
    score: ScoreResult
    risk: RiskDecision
    log: list[str] = field(default_factory=list)


class DecisionPipeline:
    def __init__(self, scoring: ScoringEngine | None = None, risk: RiskEngine | None = None) -> None:
        self.scoring = scoring or ScoringEngine()
        self.risk = risk or RiskEngine()

    def evaluate(
        self,
        token: TokenSignal,
        settings: BotSettings,
        stats: BotStats,
        open_positions: int,
    ) -> StrategyDecision:
        log = ["Detected", "Analyzing launch profile"]
        score = self.scoring.score(token, settings)
        token.score = score.score
        token.success_rate_pct = score.success_rate_pct
        token.reason = score.reason
        token.score_breakdown = score.breakdown
        log.extend(f"Score factor: {item}" for item in score.breakdown)

        risk = self.risk.evaluate(token, settings, stats, open_positions)
        if risk.allowed:
            log.append("Risk checks passed")
            log.append("Paper buy queued")
            return StrategyDecision(True, "paper_buy", score.reason, score, risk, log)

        log.append(f"Skipped: {risk.reason}")
        return StrategyDecision(False, "skip", risk.reason, score, risk, log)
