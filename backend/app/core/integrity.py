from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.core.models import PriceObservation, SourceEvent, StrategyDecisionRecord, TokenSignal, TradeRecord


@dataclass(slots=True)
class IntegrityIssue:
    severity: str
    category: str
    message: str
    count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "count": self.count,
        }


class DataIntegrityAnalyzer:
    """Read-only data checks used before trusting replay or performance results."""

    def report(
        self,
        tokens: list[TokenSignal],
        trades: list[TradeRecord],
        observations: list[PriceObservation],
        source_events: list[SourceEvent],
        decisions: list[StrategyDecisionRecord],
    ) -> dict[str, Any]:
        issues: list[IntegrityIssue] = []
        token_ids = {token.id for token in tokens}
        trade_token_ids = {trade.token_id for trade in trades}
        decision_token_ids = {decision.token_id for decision in decisions}
        token_mints_by_id = {token.id: token.mint for token in tokens}
        observations_by_mint = Counter(observation.mint for observation in observations)
        duplicate_mints = sum(count - 1 for count in Counter(token.mint for token in tokens).values() if count > 1)
        malformed_source = len([event for event in source_events if event.status == "raw"])
        rejected_prices = len([observation for observation in observations if not observation.accepted])
        missing_trade_tokens = len([trade for trade in trades if trade.token_id not in token_ids])
        missing_decisions = len([trade for trade in trades if trade.token_id not in decision_token_ids])
        closed_without_exit = len([trade for trade in trades if trade.lifecycle_status == "closed" and not trade.exit_reason])
        trades_without_price = len(
            [
                trade
                for trade in trades
                if trade.token_id in token_ids and not observations_by_mint.get(token_mints_by_id.get(trade.token_id, ""), 0)
            ]
        )

        if duplicate_mints:
            issues.append(IntegrityIssue("warning", "tokens", "Duplicate token mints detected", duplicate_mints))
        if malformed_source:
            issues.append(IntegrityIssue("warning", "source", "Raw source events could not be normalized", malformed_source))
        if rejected_prices:
            issues.append(IntegrityIssue("info", "price", "Rejected price observations require review", rejected_prices))
        if missing_trade_tokens:
            issues.append(IntegrityIssue("danger", "trades", "Trade records reference missing token snapshots", missing_trade_tokens))
        if missing_decisions:
            issues.append(IntegrityIssue("warning", "strategy", "Trades are missing strategy decision records", missing_decisions))
        if closed_without_exit:
            issues.append(IntegrityIssue("warning", "trades", "Closed trades are missing exit reasons", closed_without_exit))
        if trades_without_price:
            issues.append(IntegrityIssue("info", "price", "Some trades have no matching price observation history", trades_without_price))

        score = 100
        for issue in issues:
            score -= {"danger": 20, "warning": 10, "info": 1}.get(issue.severity, 5) * min(issue.count, 5)

        return {
            "score": max(0, min(100, score)),
            "tokens": len(tokens),
            "trades": len(trades),
            "source_events": len(source_events),
            "price_observations": len(observations),
            "strategy_decisions": len(decisions),
            "issues": [issue.to_dict() for issue in issues],
            "replay_confidence": self.replay_confidence(tokens, trades, observations, source_events),
            "determinism_fingerprint": self.fingerprint(tokens, observations, source_events),
        }

    def replay_confidence(
        self,
        tokens: list[TokenSignal],
        trades: list[TradeRecord],
        observations: list[PriceObservation],
        source_events: list[SourceEvent],
    ) -> dict[str, Any]:
        accepted = len([observation for observation in observations if observation.accepted])
        total_prices = max(1, len(observations))
        normalized = len([event for event in source_events if event.status in {"normalized", "trade"}])
        total_events = max(1, len(source_events))
        closed = len([trade for trade in trades if trade.lifecycle_status == "closed"])
        coverage = min(1.0, accepted / max(1, closed))
        confidence = (accepted / total_prices * 0.35) + (normalized / total_events * 0.35) + (coverage * 0.30)
        return {
            "score": round(confidence * 100),
            "accepted_price_ratio": round(accepted / total_prices, 3),
            "normalized_event_ratio": round(normalized / total_events, 3),
            "closed_trade_price_coverage": round(coverage, 3),
            "sample_size": {"tokens": len(tokens), "closed_trades": closed, "price_observations": len(observations)},
        }

    def fingerprint(
        self,
        tokens: list[TokenSignal],
        observations: list[PriceObservation],
        source_events: list[SourceEvent],
    ) -> str:
        payload = {
            "tokens": [(token.id, token.mint, token.detected_at.isoformat(), token.score) for token in tokens],
            "observations": [(item.id, item.mint, item.observed_at.isoformat(), item.price, item.accepted) for item in observations],
            "source_events": [(event.id, event.status, event.received_at.isoformat(), event.normalized_token_id) for event in source_events],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
