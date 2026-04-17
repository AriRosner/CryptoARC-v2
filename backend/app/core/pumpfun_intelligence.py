from __future__ import annotations

from collections import Counter
from typing import Any

from app.core.models import SourceEvent, TokenSignal


class PumpFunIntelligence:
    """Aggregates Pump.fun/PumpPortal fields into explainable research signals."""

    def summarize(self, tokens: list[TokenSignal], events: list[SourceEvent]) -> dict[str, Any]:
        creators = Counter(token.creator for token in tokens)
        repeat_creators = sum(1 for count in creators.values() if count > 1)
        with_bonding_curve = len([token for token in tokens if token.bonding_curve])
        with_metadata = len([token for token in tokens if token.metadata_uri])
        high_creator_hold = len([token for token in tokens if token.creator_hold_pct >= 20])
        large_initial_buys = len([token for token in tokens if token.initial_buy_sol >= 1])
        migration_markers = len(
            [
                event
                for event in events
                if any(str(value).lower() in {"complete", "migrate", "migration"} for value in event.raw_payload.values())
            ]
        )
        total = max(1, len(tokens))
        field_coverage = {
            "bonding_curve": round(with_bonding_curve / total, 3),
            "metadata_uri": round(with_metadata / total, 3),
            "market_cap": round(len([token for token in tokens if token.market_cap_sol > 0]) / total, 3),
            "initial_buy": round(len([token for token in tokens if token.initial_buy_sol > 0]) / total, 3),
            "creator_hold": round(len([token for token in tokens if token.creator_hold_pct > 0]) / total, 3),
        }
        return {
            "tokens_analyzed": len(tokens),
            "unique_creators": len(creators),
            "repeat_creators": repeat_creators,
            "high_creator_hold": high_creator_hold,
            "large_initial_buys": large_initial_buys,
            "migration_markers": migration_markers,
            "field_coverage": field_coverage,
            "top_creators": [{"creator": creator, "launches": count} for creator, count in creators.most_common(8)],
            "research_notes": self.notes(field_coverage, repeat_creators, high_creator_hold),
        }

    def notes(self, field_coverage: dict[str, float], repeat_creators: int, high_creator_hold: int) -> list[str]:
        notes: list[str] = []
        if field_coverage.get("creator_hold", 0) < 0.5:
            notes.append("Creator hold coverage is thin; treat creator concentration filters as low-confidence.")
        if field_coverage.get("market_cap", 0) < 0.5:
            notes.append("Market-cap coverage is below 50%; price engine will rely more on fallback sources.")
        if repeat_creators:
            notes.append("Repeat creators are present; creator history should stay in the entry decision log.")
        if high_creator_hold:
            notes.append("High creator-hold launches detected; keep rug-risk filtering enabled for paper tests.")
        if not notes:
            notes.append("Pump.fun source fields look usable for current paper research.")
        return notes
