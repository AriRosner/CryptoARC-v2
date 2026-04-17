from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.models import BotSettings, PriceObservation, TokenSignal, new_id, utc_now


@dataclass(frozen=True, slots=True)
class RawPriceCandidate:
    price: float | None
    source: str
    confidence: float
    reason: str
    market_cap_sol: float | None = None
    direct_price: float | None = None
    market_cap_price: float | None = None
    virtual_reserve_price: float | None = None


class PricePipeline:
    """Normalizes source price hints before they are allowed to affect paper PnL."""

    ENGINE_VERSION = "price-v3"

    @staticmethod
    def from_payload(payload: dict[str, Any], source: str = "pumpportal") -> RawPriceCandidate:
        direct = numeric(payload, "price", "priceSol", "tokenPriceSol")
        market_cap = numeric(payload, "marketCapSol", "marketCap", "market_cap")
        market_cap_price = max(0.000000001, market_cap / 1_000_000) if market_cap and market_cap > 0 else None
        virtual_sol = numeric(payload, "vSolInBondingCurve", "virtualSolReserves")
        virtual_tokens = numeric(payload, "vTokensInBondingCurve", "virtualTokenReserves")
        virtual_price = (
            max(0.000000001, virtual_sol / virtual_tokens)
            if virtual_sol and virtual_tokens and virtual_sol > 0 and virtual_tokens > 0
            else None
        )
        if direct and direct > 0:
            selected = max(0.000000001, direct)
            return RawPriceCandidate(selected, "direct", 0.9, "direct source price", market_cap, selected, market_cap_price, virtual_price)

        if market_cap_price:
            return RawPriceCandidate(market_cap_price, "market_cap", 0.75, "market cap normalized price", market_cap, None, market_cap_price, virtual_price)

        if virtual_price:
            return RawPriceCandidate(virtual_price, "virtual_reserves", 0.4, "virtual reserve ratio price", market_cap, None, market_cap_price, virtual_price)

        return RawPriceCandidate(None, source, 0.0, "no usable price fields", market_cap, None, market_cap_price, virtual_price)

    def observe(
        self,
        payload: dict[str, Any],
        mint: str,
        settings: BotSettings,
        source: str = "pumpportal",
        trade_side: str | None = None,
        sol_amount: float | None = None,
        token_id: str | None = None,
    ) -> PriceObservation:
        candidate = self.from_payload(payload, source)
        if not settings.prefer_market_cap_price and candidate.source == "market_cap":
            virtual_sol = numeric(payload, "vSolInBondingCurve", "virtualSolReserves")
            virtual_tokens = numeric(payload, "vTokensInBondingCurve", "virtualTokenReserves")
            if virtual_sol and virtual_tokens and virtual_sol > 0 and virtual_tokens > 0:
                candidate = RawPriceCandidate(
                    max(0.000000001, virtual_sol / virtual_tokens),
                    "virtual_reserves",
                    0.4,
                    "virtual reserve ratio price",
                    candidate.market_cap_sol,
                    candidate.direct_price,
                    candidate.market_cap_price,
                    max(0.000000001, virtual_sol / virtual_tokens),
                )
        accepted = candidate.price is not None and candidate.confidence >= settings.min_price_confidence
        reason = candidate.reason if accepted else f"rejected: {candidate.reason}; confidence {candidate.confidence:.2f}"
        return PriceObservation(
            id=new_id("px"),
            source=source,
            mint=mint,
            observed_at=utc_now(),
            price=candidate.price,
            price_source=candidate.source,
            confidence=candidate.confidence,
            accepted=accepted,
            reason=reason,
            market_cap_sol=candidate.market_cap_sol,
            sol_amount=sol_amount,
            trade_side=trade_side,
            token_id=token_id,
            direct_price=candidate.direct_price,
            market_cap_price=candidate.market_cap_price,
            virtual_reserve_price=candidate.virtual_reserve_price,
            selected_price=candidate.price,
        )

    def diagnostics(self, observations: list[PriceObservation]) -> dict[str, Any]:
        accepted = [item for item in observations if item.accepted]
        rejected = [item for item in observations if not item.accepted]
        by_source: dict[str, dict[str, Any]] = {}
        impossible_jumps = 0
        previous_by_mint: dict[str, float] = {}
        for item in sorted(observations, key=lambda observation: observation.observed_at):
            bucket = by_source.setdefault(item.price_source or "unknown", {"count": 0, "accepted": 0, "confidence_total": 0.0})
            bucket["count"] += 1
            bucket["accepted"] += 1 if item.accepted else 0
            bucket["confidence_total"] += item.confidence or 0.0
            if item.accepted and item.price and item.mint in previous_by_mint:
                previous = previous_by_mint[item.mint]
                if previous > 0 and abs((item.price - previous) / previous) > 10:
                    impossible_jumps += 1
            if item.accepted and item.price:
                previous_by_mint[item.mint] = item.price

        source_rows = []
        for source, stats in by_source.items():
            count = max(1, int(stats["count"]))
            source_rows.append(
                {
                    "source": source,
                    "count": stats["count"],
                    "accepted": stats["accepted"],
                    "acceptance_rate": round(stats["accepted"] / count, 3),
                    "avg_confidence": round(stats["confidence_total"] / count, 3),
                }
            )

        return {
            "engine_version": self.ENGINE_VERSION,
            "observations": len(observations),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "acceptance_rate": round(len(accepted) / max(1, len(observations)), 3),
            "impossible_jump_warnings": impossible_jumps,
            "sources": sorted(source_rows, key=lambda row: row["count"], reverse=True),
            "recommended_min_confidence": self.recommended_confidence(observations),
        }

    def recommended_confidence(self, observations: list[PriceObservation]) -> float:
        if not observations:
            return 0.45
        accepted = [item.confidence for item in observations if item.accepted]
        if not accepted:
            return 0.55
        average = sum(accepted) / len(accepted)
        return round(max(0.45, min(0.85, average - 0.05)), 2)

    def validate_first_tick(self, token: TokenSignal, observation: PriceObservation, settings: BotSettings) -> PriceObservation:
        if not observation.accepted or not observation.price or not token.entry_price or token.observed_price_updates > 0:
            return observation
        move_pct = abs((observation.price - token.entry_price) / max(token.entry_price, 0.000000001)) * 100
        if move_pct <= settings.max_first_observed_move_pct:
            return observation
        return PriceObservation(
            id=observation.id,
            source=observation.source,
            mint=observation.mint,
            observed_at=observation.observed_at,
            price=observation.price,
            price_source=observation.price_source,
            confidence=observation.confidence,
            accepted=False,
            reason=f"rejected: first observed move {move_pct:.1f}% exceeds {settings.max_first_observed_move_pct:.1f}%",
            market_cap_sol=observation.market_cap_sol,
            sol_amount=observation.sol_amount,
            trade_side=observation.trade_side,
            token_id=observation.token_id,
            direct_price=observation.direct_price,
            market_cap_price=observation.market_cap_price,
            virtual_reserve_price=observation.virtual_reserve_price,
            selected_price=observation.selected_price,
        )


def numeric(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None
