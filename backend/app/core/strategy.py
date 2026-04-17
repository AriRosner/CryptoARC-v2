from __future__ import annotations

from dataclasses import asdict, dataclass, field

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
    snapshot: dict[str, object] = field(default_factory=dict)


class DecisionPipeline:
    ENGINE_VERSION = "strategy-v2"

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
        snapshot = self.strategy_snapshot(settings)
        log = ["Detected", f"Analyzing launch profile with {self.ENGINE_VERSION}", f"Strategy snapshot: {snapshot['profile']} / threshold {snapshot['effective_threshold']}"]
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
            return StrategyDecision(True, "paper_buy", score.reason, score, risk, log, snapshot)

        log.append(f"Skipped: {risk.reason}")
        return StrategyDecision(False, "skip", risk.reason, score, risk, log, snapshot)

    def strategy_snapshot(self, settings: BotSettings) -> dict[str, object]:
        return {
            "engine_version": self.ENGINE_VERSION,
            "profile": settings.strategy_profile,
            "risk_tolerance": settings.risk_tolerance,
            "effective_threshold": self.risk.effective_score_threshold(settings),
            "weights": {
                "metadata": settings.strategy_weight_metadata,
                "momentum": settings.strategy_weight_momentum,
                "pressure": settings.strategy_weight_pressure,
                "creator": settings.strategy_weight_creator,
            },
            "exits": {
                "take_profit_pct": settings.take_profit_pct,
                "stop_loss_pct": settings.stop_loss_pct,
                "max_hold_time_seconds": settings.max_hold_time_seconds,
                "max_position_ticks": settings.max_position_ticks,
            },
            "raw": asdict(settings),
        }
