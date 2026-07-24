from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websockets

from app.core.models import SourceStatus, TokenSignal, TokenStatus, new_id, utc_now
from app.core.price_pipeline import PricePipeline, numeric
from app.core.simulator import LaunchSimulator


logger = logging.getLogger(__name__)


PUMPPORTAL_NON_LAUNCH_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}


def _log_cleanup_failures(context: str, results: list[Any]) -> None:
    for result in results:
        if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
            logger.warning("%s cleanup failure (%s)", context, result.__class__.__name__)


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
        status.connection_requested_at = utc_now()
        status.status = "connected"
        status.message = "Mock launch stream active"
        status.connected_at = utc_now()
        while True:
            now = utc_now()
            if status.first_event_at is None:
                status.first_event_at = now
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
        subscription_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max(1, self.max_trade_subscriptions * 4 or 1))
        tasks = [asyncio.create_task(self._run_launch_stream(queue, status, subscription_queue))]
        if self.max_trade_subscriptions > 0:
            tasks.append(asyncio.create_task(self._run_trade_stream(queue, status, subscription_queue)))
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            _log_cleanup_failures("PumpPortal source", results)
            raise

    async def _run_launch_stream(
        self,
        queue: asyncio.Queue[LaunchEvent],
        status: SourceStatus,
        subscription_queue: asyncio.Queue[str],
    ) -> None:
        backoff_seconds = 2
        while True:
            try:
                status.status = "connecting"
                status.message = "Connecting to PumpPortal"
                status.connection_requested_at = utc_now()
                status.connected_at = None
                status.first_event_at = None
                async with websockets.connect(self.launch_ws_url(), ping_interval=20, ping_timeout=20) as websocket:
                    await websocket.send(json.dumps({"method": "subscribeNewToken"}))
                    status.status = "connected"
                    status.message = "PumpPortal new-token stream active"
                    status.connected_at = utc_now()
                    status.reconnect_attempts = 0
                    backoff_seconds = 2
                    async for message in websocket:
                        if status.first_event_at is None:
                            status.first_event_at = utc_now()
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
                            status.status_events_seen += 1
                            await queue.put(LaunchEvent(self.name, utc_now(), payload, None, payload["message"]))
                            continue
                        trade = normalize_pumpportal_trade(payload, utc_now())
                        if trade:
                            await queue.put(trade)
                            status.events_received += 1
                            status.trade_events_seen += 1
                            status.last_event_at = utc_now()
                            continue
                        token = normalize_pumpportal_new_token(payload, utc_now())
                        await queue.put(LaunchEvent(self.name, utc_now(), payload, token, mint=token.mint if token else None))
                        if token is None:
                            status.normalization_failures += 1
                            continue
                        self._queue_trade_subscription(subscription_queue, token.mint, status)
                        status.events_received += 1
                        status.launch_events_seen += 1
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

    def _queue_trade_subscription(
        self,
        subscription_queue: asyncio.Queue[str],
        mint: str,
        status: SourceStatus,
    ) -> None:
        if self.max_trade_subscriptions <= 0:
            return
        try:
            subscription_queue.put_nowait(mint)
        except asyncio.QueueFull:
            try:
                subscription_queue.get_nowait()
                subscription_queue.task_done()
            except asyncio.QueueEmpty:
                pass
            status.dropped_trade_subscriptions += 1
            try:
                subscription_queue.put_nowait(mint)
            except asyncio.QueueFull:
                status.dropped_trade_subscriptions += 1

    async def _run_trade_stream(
        self,
        queue: asyncio.Queue[LaunchEvent],
        status: SourceStatus,
        subscription_queue: asyncio.Queue[str],
    ) -> None:
        subscribed_mints: deque[str] = deque()
        subscribed_lookup: set[str] = set()
        backoff_seconds = 2
        while True:
            first_mint = await subscription_queue.get()
            subscription_queue.task_done()
            if first_mint not in subscribed_lookup:
                subscribed_mints.append(first_mint)
                subscribed_lookup.add(first_mint)
                status.active_trade_subscriptions = len(subscribed_mints)
            try:
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as websocket:
                    for mint in subscribed_mints:
                        await websocket.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
                    backoff_seconds = 2
                    while True:
                        recv_task = asyncio.create_task(websocket.recv())
                        subscribe_task = asyncio.create_task(subscription_queue.get())
                        wait_tasks = {recv_task, subscribe_task}
                        try:
                            done, pending = await asyncio.wait(
                                wait_tasks,
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                        except asyncio.CancelledError:
                            for task in wait_tasks:
                                task.cancel()
                            results = await asyncio.gather(*wait_tasks, return_exceptions=True)
                            _log_cleanup_failures("PumpPortal trade stream", results)
                            raise
                        for task in pending:
                            task.cancel()
                        results = await asyncio.gather(*pending, return_exceptions=True)
                        _log_cleanup_failures("PumpPortal trade stream", results)
                        if subscribe_task in done:
                            mint = subscribe_task.result()
                            subscription_queue.task_done()
                            if mint not in subscribed_lookup:
                                while len(subscribed_mints) >= self.max_trade_subscriptions:
                                    old_mint = subscribed_mints.popleft()
                                    subscribed_lookup.discard(old_mint)
                                    status.dropped_trade_subscriptions += 1
                                    await websocket.send(json.dumps({"method": "unsubscribeTokenTrade", "keys": [old_mint]}))
                                await websocket.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
                                subscribed_mints.append(mint)
                                subscribed_lookup.add(mint)
                                status.active_trade_subscriptions = len(subscribed_mints)
                        if recv_task in done:
                            received_at = utc_now()
                            payload = json.loads(recv_task.result())
                            trade = normalize_pumpportal_trade(payload, received_at)
                            if trade:
                                await queue.put(trade)
                                status.events_received += 1
                                status.trade_events_seen += 1
                            elif isinstance(payload.get("message"), str):
                                status.status_events_seen += 1
                                await queue.put(LaunchEvent(self.name, received_at, payload, None, payload["message"]))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status.pumpportal_funding_message = f"PumpPortal trade stream reconnecting in {backoff_seconds}s: {exc.__class__.__name__}"
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(30, backoff_seconds * 2)

    def launch_ws_url(self) -> str:
        parts = urlsplit(self.ws_url)
        query = urlencode([(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key.lower() != "api-key"])
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


@dataclass(slots=True)
class SolanaLogsSource(LaunchSource):
    wss_endpoint: str
    mentions_address: str
    commitment: str = "confirmed"
    name: str = "solana_logs"

    async def run(self, queue: asyncio.Queue[LaunchEvent], status: SourceStatus) -> None:
        status.source = self.name
        backoff_seconds = 2
        while True:
            try:
                status.status = "connecting"
                status.message = "Connecting to Solana logsSubscribe verifier"
                status.connection_requested_at = utc_now()
                status.connected_at = None
                status.first_event_at = None
                async with websockets.connect(self.wss_endpoint, ping_interval=20, ping_timeout=20) as websocket:
                    await websocket.send(json.dumps(solana_logs_subscribe_payload(self.mentions_address, self.commitment)))
                    status.status = "connected"
                    status.message = "Solana logsSubscribe verifier active"
                    status.connected_at = utc_now()
                    backoff_seconds = 2
                    async for message in websocket:
                        if status.first_event_at is None:
                            status.first_event_at = utc_now()
                        status.raw_events_seen += 1
                        received_at = utc_now()
                        try:
                            payload = json.loads(message)
                        except json.JSONDecodeError:
                            await queue.put(
                                LaunchEvent(self.name, received_at, {"raw": message}, None, "invalid Solana logs JSON payload", kind="verification")
                            )
                            status.normalization_failures += 1
                            continue
                        if "result" in payload and "method" not in payload and "params" not in payload:
                            status.status_events_seen += 1
                            status.message = f"Solana logsSubscribe subscription id {payload.get('result')}"
                            await queue.put(LaunchEvent(self.name, received_at, payload, None, status.message, kind="verification_status"))
                            continue
                        await queue.put(LaunchEvent(self.name, received_at, payload, None, "Solana logsSubscribe notification", kind="verification"))
                        status.events_received += 1
                        status.launch_events_seen += 1
                        status.last_event_at = received_at
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status.status = "reconnecting"
                status.message = f"Solana logsSubscribe reconnecting in {backoff_seconds}s: {exc.__class__.__name__}"
                status.reconnect_attempts += 1
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(30, backoff_seconds * 2)


def solana_logs_subscribe_payload(mentions_address: str, commitment: str = "confirmed") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "logsSubscribe",
        "params": [
            {"mentions": [mentions_address]},
            {"commitment": commitment},
        ],
    }


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
    if mint in PUMPPORTAL_NON_LAUNCH_MINTS:
        return None

    symbol = first_string(payload, "symbol", "ticker") or mint[:5].upper()
    name = first_string(payload, "name", "tokenName") or symbol
    creator = first_string(payload, "traderPublicKey", "creator", "user", "owner") or "unknown"
    uri = first_string(payload, "uri", "metadataUri", "metadata_uri")
    bonding_curve = first_string(payload, "bondingCurveKey", "bondingCurve", "bonding_curve")
    initial_buy = numeric(payload, "initialBuy", "initialBuySol", "solAmount")
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
    price_candidate = PricePipeline.from_payload(payload, "pumpportal")
    current_price = price_candidate.price or max(0.000001, (market_cap or 30.0) / 1_000_000)

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
        current_price=round(current_price, 10),
        creator_hold_pct=round(max(0.0, min(100.0, creator_hold if creator_hold is not None else 0.0)), 2),
        honeypot_risk=honeypot_risk,
        rug_risk=rug_risk,
    )
    token.market_cap_sol = round(market_cap or 0.0, 4)
    token.initial_buy_sol = round(initial_buy or 0.0, 4)
    token.bonding_curve = bonding_curve or ""
    token.metadata_uri = uri or ""
    token.price_source = price_candidate.source if price_candidate.price else "derived"
    token.price_confidence = price_candidate.confidence
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
    return PricePipeline.from_payload(payload, "pumpportal").price


def first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
