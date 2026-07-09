from __future__ import annotations

from collections import Counter
from typing import Any

from app.core.models import SourceEvent, TokenSignal, TradeLabel, TradeRecord


class PumpFunIntelligence:
    """Aggregates Pump.fun/PumpPortal fields into explainable research signals."""

    def summarize(self, tokens: list[TokenSignal], events: list[SourceEvent], trades: list[TradeRecord] | None = None, labels: list[TradeLabel] | None = None) -> dict[str, Any]:
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
        creator_performance = self.creator_performance(tokens, trades or [], labels or [])
        return {
            "tokens_analyzed": len(tokens),
            "unique_creators": len(creators),
            "repeat_creators": repeat_creators,
            "high_creator_hold": high_creator_hold,
            "large_initial_buys": large_initial_buys,
            "migration_markers": migration_markers,
            "field_coverage": field_coverage,
            "top_creators": [{"creator": creator, "launches": count} for creator, count in creators.most_common(8)],
            "creator_performance": creator_performance,
            "research_notes": self.notes(field_coverage, repeat_creators, high_creator_hold),
        }

    def creator_performance(self, tokens: list[TokenSignal], trades: list[TradeRecord], labels: list[TradeLabel]) -> list[dict[str, Any]]:
        token_creator = {token.id: token.creator for token in tokens if token.creator}
        latest_labels: dict[str, TradeLabel] = {}
        for label in sorted(labels, key=lambda item: item.created_at):
            latest_labels[label.token_id] = label
        rows: dict[str, dict[str, Any]] = {}
        for token in tokens:
            creator = token.creator or "unknown"
            row = rows.setdefault(
                creator,
                {
                    "creator": creator,
                    "launches": 0,
                    "closed_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "pnl_sol": 0.0,
                    "avg_pnl_sol": 0.0,
                    "win_rate_pct": 0,
                    "labels": {},
                    "reputation": "unproven",
                },
            )
            row["launches"] = int(row["launches"]) + 1
        for trade in trades:
            creator = token_creator.get(trade.token_id)
            if not creator:
                continue
            row = rows.setdefault(
                creator,
                {
                    "creator": creator,
                    "launches": 0,
                    "closed_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "pnl_sol": 0.0,
                    "avg_pnl_sol": 0.0,
                    "win_rate_pct": 0,
                    "labels": {},
                    "reputation": "unproven",
                },
            )
            pnl = float(trade.pnl_sol or 0.0)
            row["closed_trades"] = int(row["closed_trades"]) + 1
            row["wins"] = int(row["wins"]) + (1 if pnl > 0 else 0)
            row["losses"] = int(row["losses"]) + (1 if pnl < 0 else 0)
            row["pnl_sol"] = round(float(row["pnl_sol"]) + pnl, 6)
            label = latest_labels.get(trade.token_id)
            if label:
                label_counts = row["labels"]
                label_counts[label.label] = int(label_counts.get(label.label, 0)) + 1
        for row in rows.values():
            closed = int(row["closed_trades"])
            if closed:
                row["avg_pnl_sol"] = round(float(row["pnl_sol"]) / closed, 6)
                row["win_rate_pct"] = int((int(row["wins"]) / closed) * 100)
            pnl = float(row["pnl_sol"])
            labels_dict = row["labels"]
            if labels_dict.get("ignore_from_tuning") or labels_dict.get("bad_price_data"):
                row["reputation"] = "exclude_or_review"
            elif closed >= 2 and pnl > 0 and int(row["wins"]) >= int(row["losses"]):
                row["reputation"] = "positive"
            elif closed >= 2 and pnl < 0:
                row["reputation"] = "negative"
            elif closed:
                row["reputation"] = "mixed"
        return sorted(
            rows.values(),
            key=lambda item: (int(item["closed_trades"]) == 0, -abs(float(item["pnl_sol"])), -int(item["launches"]), str(item["creator"])),
        )[:12]

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
