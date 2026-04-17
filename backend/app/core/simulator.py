from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

from app.core.models import TokenSignal, TokenStatus, new_id


SYLLABLES = [
    "arc",
    "crab",
    "nova",
    "byte",
    "meme",
    "pulse",
    "mint",
    "flux",
    "ape",
    "spark",
]


@dataclass(slots=True)
class LaunchSimulator:
    seed: int = 42
    randomizer: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self.randomizer = random.Random(self.seed)

    def make_token(self, now: datetime) -> TokenSignal:
        left = self.randomizer.choice(SYLLABLES)
        right = self.randomizer.choice(SYLLABLES)
        symbol = f"{left[:3]}{right[:2]}".upper()
        return TokenSignal(
            id=new_id("tok"),
            symbol=symbol,
            name=f"{left.title()} {right.title()}",
            mint=new_id("mint"),
            creator=new_id("creator"),
            detected_at=now,
            status=TokenStatus.DETECTED,
            age_seconds=self.randomizer.randint(1, 18),
            buy_velocity=round(self.randomizer.random(), 2),
            sell_pressure=round(self.randomizer.random(), 2),
            metadata_score=round(self.randomizer.random(), 2),
            current_price=round(self.randomizer.uniform(0.00001, 0.00008), 8),
            creator_hold_pct=round(self.randomizer.uniform(2, 26), 2),
            honeypot_risk=self.randomizer.random() < 0.04,
            rug_risk=self.randomizer.random() < 0.08,
        )

    def price_delta_pct(self, token: TokenSignal, volatility_pct: float) -> float:
        quality_bias = (token.score - 50) / 18
        noise = self.randomizer.uniform(-volatility_pct, volatility_pct)
        return round(quality_bias + noise, 2)
