from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websockets

from app.core.models import AcceptedMarketObservation, SourceStatus, TokenSignal, TokenStatus, new_id, utc_now
from app.core.price_pipeline import PricePipeline, numeric
from app.core.simulator import LaunchSimulator


logger = logging.getLogger(__name__)


PUMPPORTAL_NON_LAUNCH_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}


@dataclass(frozen=True, slots=True)
class SourceEvidenceResult:
    shadow_eligible: bool
    blockers: tuple[str, ...]
    accepted_count: int
    genuine_count: int
    fixture_count: int
    conflict_count: int
    direct_comparison_sample_ids: tuple[str, ...]


class SourceEvidenceGate:
    """Fail-closed eligibility check for attributable accepted market prices."""

    @staticmethod
    def evaluate(
        observations: Sequence[AcceptedMarketObservation],
        access_state: str,
        now: datetime,
        *,
        max_age_seconds: int = 300,
        required_strategy_id: str = "",
        required_strategy_version: str = "",
    ) -> SourceEvidenceResult:
        items = list(observations)
        fixture_count = sum(1 for item in items if item.fixture_only)
        genuine = [item for item in items if not item.fixture_only]
        conflicts = [item for item in genuine if item.conflict_state != "clear"]
        blockers: list[str] = []
        if access_state != "ready":
            blockers.append(
                "funded_trade_price_access_unavailable"
                if access_state in {"funding_required", "unfunded", "denied"}
                else f"source_access_{access_state or 'unknown'}"
            )
        else:
            identities: set[tuple[str, str, str]] = set()
            for item in items:
                identity = (item.source, item.source_event_id, item.observed_at.isoformat())
                if identity in identities:
                    blockers.append("duplicate_source_event_identity")
                identities.add(identity)
                if item.price is None or item.price <= 0:
                    blockers.append("missing_price")
                if item.observed_at.tzinfo is None or item.observed_at.utcoffset() is None:
                    blockers.append("naive_observation_time")
                    continue
                observed_at = item.observed_at.astimezone(timezone.utc)
                if now.tzinfo is None or now.utcoffset() is None:
                    blockers.append("naive_evaluation_time")
                elif observed_at > now.astimezone(timezone.utc):
                    blockers.append("future_observation")
                elif (now.astimezone(timezone.utc) - observed_at).total_seconds() > max(1, max_age_seconds):
                    blockers.append("stale_observation")
                if item.conflict_state != "clear":
                    blockers.append("source_conflict")
                if required_strategy_id and item.strategy_id != required_strategy_id:
                    blockers.append("strategy_id_mismatch")
                if required_strategy_version and item.strategy_version != required_strategy_version:
                    blockers.append("strategy_version_mismatch")
            if not genuine:
                blockers.append("genuine_observation_required")
        deduped = tuple(dict.fromkeys(blockers))
        direct_ids = tuple(
            dict.fromkeys(
                item.direct_comparison_sample_id
                for item in genuine
                if item.direct_comparison_sample_id
            )
        )
        return SourceEvidenceResult(
            shadow_eligible=not deduped and bool(genuine),
            blockers=deduped,
            accepted_count=len(items),
            genuine_count=len(genuine),
            fixture_count=fixture_count,
            conflict_count=len(conflicts),
            direct_comparison_sample_ids=direct_ids,
        )


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
    preferred_trade_mints: Callable[[], list[str]] | None = None
    preference_poll_seconds: float = 1.0
    name: str = "pumpportal"

    def _trade_subscription_can_rotate(self, subscribed_at: float, now: float) -> bool:
        return self.max_trade_subscriptions != 1 or now - subscribed_at >= 600

    def _preferred_trade_mint(self) -> str | None:
        if self.preferred_trade_mints is None:
            return ""
        try:
            return next(
                (str(mint).strip() for mint in self.preferred_trade_mints() if str(mint).strip()),
                "",
            )
        except Exception:
            return None

    def _set_trade_subscription_status(
        self,
        status: SourceStatus,
        active_preferred: str,
        subscribed_lookup: set[str],
    ) -> None:
        status.active_trade_subscriptions = len(subscribed_lookup)
        status.trade_subscription_priority = "shadow_candidate" if active_preferred else "ordinary_launch"
        status.preferred_trade_mint_prefix = active_preferred[:8] if active_preferred else ""

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
        subscribed_at: dict[str, float] = {}
        active_preferred = ""
        backoff_seconds = 2
        while True:
            preferred = self._preferred_trade_mint()
            if preferred is None:
                preferred = active_preferred
            if preferred:
                first_mint = preferred
                active_preferred = preferred
            else:
                first_mint = await subscription_queue.get()
                subscription_queue.task_done()
            if first_mint not in subscribed_lookup:
                while len(subscribed_mints) >= self.max_trade_subscriptions:
                    old_mint = subscribed_mints.popleft()
                    subscribed_lookup.discard(old_mint)
                    subscribed_at.pop(old_mint, None)
                    status.dropped_trade_subscriptions += 1
                subscribed_mints.append(first_mint)
                subscribed_lookup.add(first_mint)
                subscribed_at[first_mint] = time.monotonic()
                self._set_trade_subscription_status(status, active_preferred, subscribed_lookup)
            try:
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as websocket:
                    for mint in subscribed_mints:
                        await websocket.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
                    backoff_seconds = 2
                    while True:
                        recv_task = asyncio.create_task(websocket.recv())
                        subscribe_task = (
                            asyncio.create_task(subscription_queue.get())
                            if len(subscribed_mints) < self.max_trade_subscriptions or not active_preferred
                            else None
                        )
                        preference_task = asyncio.create_task(
                            asyncio.sleep(max(0.01, self.preference_poll_seconds))
                        )
                        wait_tasks = {recv_task, preference_task}
                        if subscribe_task is not None:
                            wait_tasks.add(subscribe_task)
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
                        if subscribe_task is not None and subscribe_task in done:
                            mint = subscribe_task.result()
                            subscription_queue.task_done()
                            if mint not in subscribed_lookup:
                                if subscribed_mints and not self._trade_subscription_can_rotate(
                                    subscribed_at.get(subscribed_mints[0], 0.0), time.monotonic()
                                ):
                                    continue
                                while len(subscribed_mints) >= self.max_trade_subscriptions:
                                    old_mint = subscribed_mints.popleft()
                                    subscribed_lookup.discard(old_mint)
                                    subscribed_at.pop(old_mint, None)
                                    status.dropped_trade_subscriptions += 1
                                    await websocket.send(json.dumps({"method": "unsubscribeTokenTrade", "keys": [old_mint]}))
                                await websocket.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
                                subscribed_mints.append(mint)
                                subscribed_lookup.add(mint)
                                subscribed_at[mint] = time.monotonic()
                                self._set_trade_subscription_status(status, active_preferred, subscribed_lookup)
                        if preference_task in done:
                            preferred = self._preferred_trade_mint()
                            if preferred is None:
                                self._set_trade_subscription_status(status, active_preferred, subscribed_lookup)
                                continue
                            if preferred and preferred != active_preferred:
                                if active_preferred and active_preferred in subscribed_lookup:
                                    subscribed_mints.remove(active_preferred)
                                    subscribed_lookup.discard(active_preferred)
                                    subscribed_at.pop(active_preferred, None)
                                    await websocket.send(json.dumps({"method": "unsubscribeTokenTrade", "keys": [active_preferred]}))
                                    status.dropped_trade_subscriptions += 1
                                while len(subscribed_mints) >= self.max_trade_subscriptions:
                                    old_mint = next(
                                        (item for item in subscribed_mints if item != active_preferred),
                                        subscribed_mints[0],
                                    )
                                    subscribed_mints.remove(old_mint)
                                    await websocket.send(json.dumps({"method": "unsubscribeTokenTrade", "keys": [old_mint]}))
                                    subscribed_lookup.discard(old_mint)
                                    subscribed_at.pop(old_mint, None)
                                    status.dropped_trade_subscriptions += 1
                                await websocket.send(json.dumps({"method": "subscribeTokenTrade", "keys": [preferred]}))
                                subscribed_mints.append(preferred)
                                subscribed_lookup.add(preferred)
                                subscribed_at[preferred] = time.monotonic()
                                active_preferred = preferred
                            elif active_preferred and not preferred:
                                if active_preferred in subscribed_lookup:
                                    subscribed_mints.remove(active_preferred)
                                    await websocket.send(json.dumps({"method": "unsubscribeTokenTrade", "keys": [active_preferred]}))
                                    subscribed_lookup.discard(active_preferred)
                                    subscribed_at.pop(active_preferred, None)
                                active_preferred = ""
                            self._set_trade_subscription_status(status, active_preferred, subscribed_lookup)
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
                        params = payload.get("params")
                        result = params.get("result") if isinstance(params, dict) else None
                        value = result.get("value") if isinstance(result, dict) else None
                        if isinstance(value, dict) and value.get("err") is not None:
                            status.failed_events_seen += 1
                            status.message = (
                                "Solana logsSubscribe verifier active; "
                                f"{status.failed_events_seen} failed transaction notifications skipped"
                            )
                            continue
                        logs = value.get("logs") if isinstance(value, dict) else None
                        if not isinstance(logs, list) or not any("Instruction: Create" in str(log) for log in logs):
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


def make_source(
    name: str,
    launch_interval_seconds: float,
    pumpportal_ws_url: str,
    max_trade_subscriptions: int = 60,
    preferred_trade_mints: Callable[[], list[str]] | None = None,
) -> LaunchSource:
    if name == "pumpportal":
        return PumpPortalLaunchSource(
            ws_url=pumpportal_ws_url,
            max_trade_subscriptions=max_trade_subscriptions,
            preferred_trade_mints=preferred_trade_mints,
        )
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
