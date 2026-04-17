from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import websockets

from app.core.models import SourceStatus, TokenSignal, TokenStatus, new_id, utc_now
from app.core.simulator import LaunchSimulator


class LaunchSource(ABC):
    name: str

    @abstractmethod
    async def run(self, queue: asyncio.Queue[LaunchEvent], status: SourceStatus) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class LaunchEvent:
    source: str
    received_at: datetime
    raw_payload: dict[str, Any]
    token: TokenSignal | None
    message: str = ""
    kind: str = "launch"
    mint: str | None = None
    trade_side: str | None = None
    observed_price: float | None = None
    sol_amount: float | None = None


@dataclass(slots=True)
class MockLaunchSource(LaunchSource):
    launch_interval_seconds: float
    name: str = "mock"

    def __post_init__(self) -> None:
        self.simulator = LaunchSimulator()

    async def run(self, queue: asyncio.Queue[LaunchEvent], status: SourceStatus) -> None:
        status.source = self.name
        status.status = "connected"
        status.message = "Mock launch stream active"
        while True:
            now = utc_now()
            token = self.simulator.make_token(now)
            await queue.put(
                LaunchEvent(
                    source=self.name,
                    received_at=now,
                    raw_payload={"source": self.name, "mint": token.mint, "symbol": token.symbol, "creator": token.creator},
                    token=token,
                    message="mock token generated",
                )
            )
            status.events_received += 1
            status.raw_events_seen += 1
            status.normalized_events += 1
            status.last_event_at = utc_now()
            await asyncio.sleep(self.launch_interval_seconds)


@dataclass(slots=True)
class PumpPortalLaunchSource(LaunchSource):
    ws_url: str
    max_trade_subscriptions: int = 60
    name: str = "pumpportal"

    async def run(self, queue: asyncio.Queue[LaunchEvent], status: SourceStatus) -> None:
        status.source = self.name
        backoff_seconds = 2
        while True:
            try:
                status.status = "connecting"
                status.message = "Connecting to PumpPortal"
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as websocket:
                    subscribed_mints: set[str] = set()
                    await websocket.send(json.dumps({"method": "subscribeNewToken"}))
                    status.status = "connected"
                    status.message = "PumpPortal new-token stream active"
                    backoff_seconds = 2
                    async for message in websocket:
                        status.raw_events_seen += 1
                        try:
                            payload = json.loads(message)
                        except json.JSONDecodeError:
                            await queue.put(
                                LaunchEvent(self.name, utc_now(), {"raw": message}, None, "invalid JSON payload")
                            )
                            continue
                        if isinstance(payload.get("message"), str):
                            status.message = payload["message"]
                            await queue.put(LaunchEvent(self.name, utc_now(), payload, None, payload["message"]))
                            continue
                        trade = normalize_pumpportal_trade(payload, utc_now())
                        if trade:
                            await queue.put(trade)
                            status.events_received += 1
                            status.last_event_at = utc_now()
                            continue
                        token = normalize_pumpportal_new_token(payload, utc_now())
                        await queue.put(LaunchEvent(self.name, utc_now(), payload, token, mint=token.mint if token else None))
                        if token is None:
                            continue
                        if len(subscribed_mints) < self.max_trade_subscriptions and token.mint not in subscribed_mints:
                            await websocket.send(json.dumps({"method": "subscribeTokenTrade", "keys": [token.mint]}))
                            subscribed_mints.add(token.mint)
                        status.events_received += 1
                        status.normalized_events += 1
                        status.last_event_at = utc_now()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status.status = "reconnecting"
                status.message = f"PumpPortal reconnecting in {backoff_seconds}s: {exc.__class__.__name__}"
                status.reconnect_attempts += 1
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(30, backoff_seconds * 2)


def make_source(name: str, launch_interval_seconds: float, pumpportal_ws_url: str, max_trade_subscriptions: int = 60) -> LaunchSource:
    if name == "pumpportal":
        return PumpPortalLaunchSource(ws_url=pumpportal_ws_url, max_trade_subscriptions=max_trade_subscriptions)
    return MockLaunchSource(launch_interval_seconds=launch_interval_seconds)


def normalize_pumpportal_new_token(payload: dict[str, Any], now: datetime) -> TokenSignal | None:
    tx_type = str(payload.get("txType") or payload.get("type") or payload.get("method") or "").lower()
    if tx_type in {"buy", "sell"}:
        return None
    has_create_shape = any(key in payload for key in ("mint", "tokenMint", "name", "symbol", "uri"))
    if tx_type and tx_type not in {"create", "newtoken", "subscribenewtoken"} and not has_create_shape:
        return None

    mint = first_string(payload, "mint", "tokenMint", "token", "ca")
    if not mint:
        return None

    symbol = first_string(payload, "symbol", "ticker") or mint[:5].upper()
    name = first_string(payload, "name", "tokenName") or symbol
    creator = first_string(payload, "traderPublicKey", "creator", "user", "owner") or "unknown"
    uri = first_string(payload, "uri", "metadataUri", "metadata_uri")
    bonding_curve = first_string(payload, "bondingCurveKey", "bondingCurve", "bonding_curve")
    initial_buy = numeric(payload, "initialBuy", "initialBuySol", "solAmount")
    virtual_sol = numeric(payload, "vSolInBondingCurve", "virtualSolReserves")
    virtual_tokens = numeric(payload, "vTokensInBondingCurve", "virtualTokenReserves")
    market_cap = numeric(payload, "marketCapSol", "marketCap", "market_cap")
    creator_hold = numeric(payload, "creatorHoldPct", "creator_hold_pct", "creatorHoldPercent", "devHoldPct")
    complete = bool(payload.get("complete"))
    risk_text = " ".join(str(payload.get(key, "")) for key in ("name", "symbol", "uri", "metadataUri")).lower()
    honeypot_risk = bool(
        payload.get("honeypot")
        or payload.get("isHoneypot")
        or payload.get("cannotSell")
        or "honeypot" in risk_text
    )
    rug_risk = bool(
        payload.get("rugRisk")
        or payload.get("isRug")
        or payload.get("freezeAuthority")
        or "rug" in risk_text
        or (creator_hold is not None and creator_hold >= 35)
    )

    metadata_score = 0.35
    if name and symbol:
        metadata_score += 0.25
    if uri:
        metadata_score += 0.25
    if bonding_curve:
        metadata_score += 0.15
    if complete:
        metadata_score += 0.05

    buy_velocity = min(1.0, max(0.05, initial_buy / 5 if initial_buy else 0.25))
    sell_pressure = 0.08
    current_price = observed_price_from_payload(payload) or max(0.000001, (market_cap or 30.0) / 1_000_000)
    if virtual_sol and virtual_tokens:
        current_price = max(0.000000001, virtual_sol / virtual_tokens)

    token = TokenSignal(
        id=new_id("tok"),
        symbol=symbol[:12].upper(),
        name=name[:80],
        mint=mint,
        creator=creator,
        detected_at=now,
        status=TokenStatus.DETECTED,
        age_seconds=0,
        buy_velocity=round(buy_velocity, 2),
        sell_pressure=sell_pressure,
        metadata_score=round(min(metadata_score, 1.0), 2),
        current_price=round(current_price, 8),
        creator_hold_pct=round(max(0.0, min(100.0, creator_hold if creator_hold is not None else 0.0)), 2),
        honeypot_risk=honeypot_risk,
        rug_risk=rug_risk,
    )
    token.market_cap_sol = round(market_cap or 0.0, 4)
    token.initial_buy_sol = round(initial_buy or 0.0, 4)
    token.bonding_curve = bonding_curve or ""
    token.metadata_uri = uri or ""
    token.price_source = "observed" if observed_price_from_payload(payload) else "derived"
    return token


def normalize_pumpportal_trade(payload: dict[str, Any], now: datetime) -> LaunchEvent | None:
    tx_type = str(payload.get("txType") or payload.get("type") or "").lower()
    if tx_type not in {"buy", "sell"}:
        return None
    mint = first_string(payload, "mint", "tokenMint", "token", "ca")
    if not mint:
        return None
    price = observed_price_from_payload(payload)
    sol_amount = numeric(payload, "solAmount", "sol_amount", "amountSol")
    return LaunchEvent(
        source="pumpportal",
        received_at=now,
        raw_payload=payload,
        token=None,
        message=f"token trade {tx_type}",
        kind="trade",
        mint=mint,
        trade_side=tx_type,
        observed_price=price,
        sol_amount=sol_amount,
    )


def observed_price_from_payload(payload: dict[str, Any]) -> float | None:
    direct = numeric(payload, "price", "priceSol", "tokenPriceSol")
    if direct:
        return max(0.000000001, direct)
    market_cap = numeric(payload, "marketCapSol", "marketCap", "market_cap")
    if market_cap:
        return max(0.000000001, market_cap / 1_000_000)
    virtual_sol = numeric(payload, "vSolInBondingCurve", "virtualSolReserves")
    virtual_tokens = numeric(payload, "vTokensInBondingCurve", "virtualTokenReserves")
    if virtual_sol and virtual_tokens:
        return max(0.000000001, virtual_sol / virtual_tokens)
    return None


def first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


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
