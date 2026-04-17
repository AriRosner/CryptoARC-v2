from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict
from datetime import datetime, timedelta

from app.core.models import (
    BacktestRun,
    BotSettings,
    BotSnapshot,
    BotStats,
    BotStatus,
    SourceStatus,
    SourceEvent,
    TokenSignal,
    TokenStatus,
    TradeEvent,
    TradeRecord,
    new_id,
    utc_now,
)
from app.core.paper_trader import PaperTrader
from app.core.risk import RiskEngine
from app.core.scoring import ScoringEngine
from app.core.simulator import LaunchSimulator
from app.core.storage import Storage
from app.core.sources import LaunchEvent, normalize_pumpportal_new_token
from app.core.strategy import DecisionPipeline


class BotState:
    def __init__(self, database_path: str = "data/cryptoarc.db", default_source: str = "mock") -> None:
        self.storage = Storage(database_path)
        self.status = BotStatus.STOPPED
        has_saved_settings = self.storage.has_settings()
        self.settings = self.storage.load_settings()
        if self.settings.launch_source not in {"mock", "pumpportal"}:
            self.settings.launch_source = default_source
        elif not has_saved_settings and self.settings.launch_source == "mock" and default_source != "mock":
            self.settings.launch_source = default_source
        self.stats = BotStats()
        self.tokens: deque[TokenSignal] = deque(self.storage.load_tokens(), maxlen=80)
        self.events: deque[TradeEvent] = deque(self.storage.load_events(), maxlen=30)
        self.backtest_runs: deque[BacktestRun] = deque(self.storage.load_backtest_runs(), maxlen=20)
        self.source_status = SourceStatus(source=self.settings.launch_source, status="offline")
        self.scoring = ScoringEngine()
        self.risk = RiskEngine()
        self.strategy = DecisionPipeline(self.scoring, self.risk)
        self.paper = PaperTrader()
        self.simulator = LaunchSimulator()
        self.creator_history = Counter(token.creator for token in self.tokens)
        self.recalculate_stats()

    def start(self) -> BotSnapshot:
        self.status = BotStatus.RUNNING
        self.add_event("info", "Paper trading loop started")
        return self.snapshot()

    def stop(self) -> BotSnapshot:
        self.status = BotStatus.STOPPED
        self.add_event("warning", "Paper trading loop stopped")
        return self.snapshot()

    def update_settings(self, patch: dict[str, object]) -> BotSnapshot:
        current = asdict(self.settings)
        current.update({key: value for key, value in patch.items() if key in current})
        self.settings = BotSettings(**current)
        self.source_status.source = self.settings.launch_source
        self.storage.save_settings(self.settings)
        changed = ", ".join(sorted(patch.keys()))
        self.add_event("info", f"Settings saved: {changed}")
        return self.snapshot()

    def add_event(self, level: str, message: str, token_id: str | None = None) -> None:
        event = TradeEvent(
            id=new_id("evt"),
            created_at=utc_now(),
            level=level,
            message=message,
            token_id=token_id,
        )
        self.events.appendleft(event)
        self.storage.save_event(event)

    def record_source_event(self, source: str, raw_payload: dict[str, object], token: TokenSignal | None, message: str = "", status: str | None = None) -> None:
        event = SourceEvent(
            id=new_id("src"),
            source=source,
            received_at=utc_now(),
            raw_payload=raw_payload,
            normalized_token_id=token.id if token else None,
            status=status or ("normalized" if token else "raw"),
            message=message,
        )
        self.storage.save_source_event(event)

    def ingest_source_event(self, event: LaunchEvent) -> None:
        if event.kind == "trade":
            self.record_source_event(event.source, event.raw_payload, None, event.message, status="trade")
            self.apply_observed_trade(event)
            return
        self.record_source_event(event.source, event.raw_payload, event.token, event.message)
        if event.token:
            self.ingest_launch(event.token)

    def apply_observed_trade(self, event: LaunchEvent) -> None:
        if not self.settings.use_observed_prices or not event.mint or not event.observed_price:
            return
        for token in self.tokens:
            if token.mint != event.mint:
                continue
            old_price = token.current_price or event.observed_price
            token.current_price = event.observed_price
            token.price_source = "observed"
            token.observed_price_updates += 1
            token.last_observed_trade_at = event.received_at
            if event.trade_side == "buy":
                token.buy_velocity = min(1.0, round(token.buy_velocity + 0.04, 3))
            if event.trade_side == "sell":
                token.sell_pressure = min(1.0, round(token.sell_pressure + 0.05, 3))
            if token.entry_price:
                move_pct = ((token.current_price - token.entry_price) / token.entry_price) * 100
                token.unrealized_pct = round(move_pct, 2)
                token.pnl_sol = round((token.amount_sol or self.settings.trade_size_sol) * (move_pct / 100), 6)
            token.decision_log.append(f"Observed {event.trade_side} trade updated price from {old_price:.8f} to {event.observed_price:.8f}")
            self.storage.save_token(token)
            break

    def tick(self) -> BotSnapshot:
        for token in list(self.tokens):
            token.age_seconds = max(0, int((utc_now() - token.detected_at).total_seconds()))
            if token.status not in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}:
                self.storage.save_token(token)
                continue

            delta_pct = 0.0 if self.settings.use_observed_prices and token.price_source == "observed" else self.simulator.price_delta_pct(token, self.settings.paper_price_volatility_pct)
            closed = self.paper.tick(token, self.settings, delta_pct)
            self.storage.save_token(token)
            if closed:
                pnl = token.pnl_sol or 0.0
                level = "success" if pnl > 0 else "danger"
                reason = f" ({token.exit_reason})" if token.exit_reason else ""
                self.add_event(level, f"Paper sold {token.symbol} at {pnl:+.4f} SOL{reason}", token.id)
                self.storage.save_trade(self.trade_from_token(token))

        self.recalculate_stats()
        return self.snapshot()

    def ingest_launch(self, token: TokenSignal) -> None:
        if self.status != BotStatus.RUNNING or not self.settings.detect_new_tokens:
            return

        token.status = TokenStatus.ANALYZING
        self.enrich_token_intelligence(token)

        open_positions = self.open_position_count()
        decision = self.strategy.evaluate(token, self.settings, self.stats, open_positions)
        token.decision_log.extend(decision.log)
        if decision.allowed:
            token.status = TokenStatus.BUYING
            token.entry_reason = f"score {token.score}: {token.reason}"
            self.paper.buy(token, self.settings)
            if token.fill_failed:
                token.reason = "paper buy fill failed"
                self.add_event("warning", f"Paper buy failed {token.symbol}: simulated fill miss", token.id)
            else:
                self.storage.save_trade(self.trade_from_token(token))
                fill_note = "queued" if token.status == TokenStatus.BUYING else "filled"
                self.add_event(
                    "success",
                    f"Paper bought {token.symbol} for {self.settings.trade_size_sol:.3f} SOL ({fill_note})",
                    token.id,
                )
        else:
            token.status = TokenStatus.SKIPPED
            token.reason = decision.reason
            self.add_event("info", f"Skipped {token.symbol}: {decision.reason}", token.id)

        self.tokens.appendleft(token)
        self.creator_history[token.creator] += 1
        self.storage.save_token(token)
        self.recalculate_stats()

    def enrich_token_intelligence(self, token: TokenSignal) -> None:
        previous_launches = self.creator_history[token.creator]
        token.creator_launch_count = previous_launches + 1
        tags: list[str] = []

        duplicate_symbols = sum(1 for existing in self.tokens if existing.symbol.upper() == token.symbol.upper())

        if previous_launches == 0:
            tags.append("new creator")
        else:
            tags.append(f"repeat creator x{previous_launches + 1}")

        if token.creator_hold_pct > self.settings.max_creator_hold_pct:
            tags.append("creator concentration risk")
        elif token.creator_hold_pct > 0:
            tags.append("creator hold checked")

        if token.metadata_score < 0.35:
            tags.append("weak metadata")
        elif token.metadata_score >= 0.85:
            tags.append("strong metadata")
        if duplicate_symbols:
            tags.append(f"symbol seen x{duplicate_symbols + 1}")
            if self.settings.duplicate_symbol_penalty:
                token.metadata_score = max(0.0, round(token.metadata_score - 0.08, 3))
        if self.settings.strict_metadata_checks and token.metadata_score < 0.65:
            token.rug_risk = True
            tags.append("strict metadata risk")
        if token.buy_velocity >= 0.7:
            tags.append("early demand")
        elif token.buy_velocity < 0.25:
            tags.append("thin demand")
        if token.sell_pressure >= 0.65:
            tags.append("sell pressure")
        if token.honeypot_risk:
            tags.append("honeypot risk")
        if token.rug_risk:
            tags.append("rug-pull risk")

        token.intelligence_tags = tags

    def trade_from_token(self, token: TokenSignal) -> TradeRecord:
        return TradeRecord(
            id=f"trd_{token.id}",
            token_id=token.id,
            mode=str(self.settings.mode.value if hasattr(self.settings.mode, "value") else self.settings.mode),
            strategy_profile=token.entry_strategy_profile or self.settings.strategy_profile,
            entry_price=token.entry_price,
            exit_price=token.exit_price,
            amount_sol=token.amount_sol,
            pnl_sol=token.pnl_sol,
            entry_reason=token.entry_reason,
            exit_reason=token.exit_reason,
            opened_at=token.opened_at,
            closed_at=token.closed_at,
            hold_duration_seconds=token.hold_duration_seconds,
            decision_log=token.decision_log,
        )

    def replay_backtest(
        self,
        limit: int | None = None,
        profile: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        replay_speed: float = 50,
    ) -> BacktestRun:
        limit = limit or self.settings.backtest_replay_limit
        settings = self._settings_for_profile(profile)
        candidates = [
            token
            for token in list(self.tokens)[:limit]
            if token.status in {TokenStatus.SKIPPED, TokenStatus.PAPER_SOLD, TokenStatus.DETECTED, TokenStatus.ANALYZING}
        ]
        candidates = self._filter_tokens_by_date(candidates, date_from, date_to)
        replay_stats = BotStats()
        buys = 0
        skips = 0
        simulated_pnl = 0.0
        wins = 0
        losses = 0
        gross_win = 0.0
        gross_loss = 0.0
        pnl_curve = [0.0]
        trough = 0.0
        trades: list[dict[str, object]] = []
        for token in candidates:
            decision = self.risk.evaluate(token, settings, replay_stats, open_positions=0)
            if decision.allowed:
                buys += 1
                pnl = token.pnl_sol if token.pnl_sol is not None else self._estimated_replay_pnl(token, settings)
                simulated_pnl = round(simulated_pnl + pnl, 6)
                pnl_curve.append(simulated_pnl)
                trough = min(trough, simulated_pnl)
                if pnl > 0:
                    wins += 1
                    gross_win += pnl
                elif pnl < 0:
                    losses += 1
                    gross_loss += abs(pnl)
                trades.append(
                    {
                        "token_id": token.id,
                        "symbol": token.symbol,
                        "decision": "buy",
                        "reason": token.reason,
                        "score": token.score,
                        "pnl_sol": round(pnl, 6),
                    }
                )
            else:
                skips += 1
                trades.append(
                    {
                        "token_id": token.id,
                        "symbol": token.symbol,
                        "decision": "skip",
                        "reason": decision.reason,
                        "score": token.score,
                        "pnl_sol": 0,
                    }
                )

        run = BacktestRun(
            id=new_id("bt"),
            created_at=utc_now(),
            profile=settings.strategy_profile,
            risk_tolerance=settings.risk_tolerance,
            tokens_replayed=len(candidates),
            paper_buys=buys,
            skips=skips,
            wins=wins,
            losses=losses,
            win_rate_pct=int((wins / buys) * 100) if buys else 0,
            estimated_pnl_sol=round(simulated_pnl, 6),
            max_drawdown_sol=round(trough, 6),
            profit_factor=round(gross_win / gross_loss, 2) if gross_loss else 0.0,
            pnl_curve=pnl_curve[-80:],
            trades=trades[:80],
            comparison=[{"date_from": date_from or "any", "date_to": date_to or "any", "replay_speed": replay_speed}],
        )
        self.backtest_runs.appendleft(run)
        self.storage.save_backtest_run(run)
        return run

    def replay_raw_source_events(
        self,
        limit: int | None = None,
        profile: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        replay_speed: float = 50,
    ) -> BacktestRun:
        limit = limit or self.settings.raw_replay_limit
        source_events = self._filter_source_events_by_date(self.storage.load_source_events(limit), date_from, date_to)
        candidates: list[TokenSignal] = []
        failures = 0
        for event in source_events:
            if event.source == "pumpportal":
                token = normalize_pumpportal_new_token(event.raw_payload, event.received_at)
                if token:
                    candidates.append(token)
                else:
                    failures += 1
            elif event.raw_payload.get("mint"):
                token = TokenSignal(
                    id=new_id("replay"),
                    symbol=str(event.raw_payload.get("symbol") or "MOCK")[:12].upper(),
                    name=str(event.raw_payload.get("symbol") or "Mock Replay"),
                    mint=str(event.raw_payload.get("mint")),
                    creator=str(event.raw_payload.get("creator") or "unknown"),
                    detected_at=event.received_at,
                    current_price=0.00003,
                    metadata_score=0.65,
                    buy_velocity=0.45,
                    sell_pressure=0.2,
                )
                candidates.append(token)
        run = self._run_backtest(candidates[:limit], replay_source="raw_source_events", settings=self._settings_for_profile(profile))
        run.comparison = [{"raw_events": len(source_events), "normalized": len(candidates), "normalization_failures": failures, "date_from": date_from or "any", "date_to": date_to or "any", "replay_speed": replay_speed}]
        self.storage.save_backtest_run(run)
        return run

    def compare_strategies(self, limit: int = 80) -> BacktestRun:
        candidates = [
            token
            for token in list(self.tokens)[:limit]
            if token.status in {TokenStatus.SKIPPED, TokenStatus.PAPER_SOLD, TokenStatus.DETECTED, TokenStatus.ANALYZING}
        ]
        run = self._run_backtest(candidates, replay_source="strategy_comparison")
        comparison = []
        current = asdict(self.settings)
        for profile, offset in {"conservative": 8, "balanced": 0, "aggressive": -7, "scalper": -4}.items():
            settings = BotSettings(**{**current, "strategy_profile": profile})
            buys = 0
            skips = 0
            pnl = 0.0
            wins = 0
            losses = 0
            drawdown = 0.0
            for token in candidates:
                decision = self.risk.evaluate(token, settings, BotStats(), open_positions=0)
                if decision.allowed:
                    buys += 1
                    trade_pnl = token.pnl_sol if token.pnl_sol is not None else self._estimated_replay_pnl(token, settings) + abs(offset) / 2000
                    pnl += trade_pnl
                    wins += 1 if trade_pnl > 0 else 0
                    losses += 1 if trade_pnl < 0 else 0
                    drawdown = min(drawdown, pnl)
                else:
                    skips += 1
            comparison.append({
                "profile": profile,
                "buys": buys,
                "skips": skips,
                "wins": wins,
                "losses": losses,
                "win_rate_pct": int((wins / buys) * 100) if buys else 0,
                "max_drawdown_sol": round(drawdown, 6),
                "estimated_pnl_sol": round(pnl, 6),
            })
        run.comparison = comparison
        self.storage.save_backtest_run(run)
        return run

    def _run_backtest(self, candidates: list[TokenSignal], replay_source: str, settings: BotSettings | None = None) -> BacktestRun:
        settings = settings or self.settings
        replay_stats = BotStats()
        buys = 0
        skips = 0
        simulated_pnl = 0.0
        wins = 0
        losses = 0
        gross_win = 0.0
        gross_loss = 0.0
        pnl_curve = [0.0]
        trough = 0.0
        trades: list[dict[str, object]] = []
        for token in candidates:
            if not token.score:
                self.enrich_token_intelligence(token)
                score = self.scoring.score(token, settings)
                token.score = score.score
                token.reason = score.reason
                token.score_breakdown = score.breakdown
            decision = self.risk.evaluate(token, settings, replay_stats, open_positions=0)
            if decision.allowed:
                buys += 1
                pnl = token.pnl_sol if token.pnl_sol is not None else self._estimated_replay_pnl(token, settings)
                simulated_pnl = round(simulated_pnl + pnl, 6)
                pnl_curve.append(simulated_pnl)
                trough = min(trough, simulated_pnl)
                if pnl > 0:
                    wins += 1
                    gross_win += pnl
                elif pnl < 0:
                    losses += 1
                    gross_loss += abs(pnl)
                trades.append({"token_id": token.id, "symbol": token.symbol, "decision": "buy", "reason": token.reason, "score": token.score, "pnl_sol": round(pnl, 6)})
            else:
                skips += 1
                trades.append({"token_id": token.id, "symbol": token.symbol, "decision": "skip", "reason": decision.reason, "score": token.score, "pnl_sol": 0})
        run = BacktestRun(
            id=new_id("bt"),
            created_at=utc_now(),
            profile=settings.strategy_profile,
            risk_tolerance=settings.risk_tolerance,
            tokens_replayed=len(candidates),
            paper_buys=buys,
            skips=skips,
            wins=wins,
            losses=losses,
            win_rate_pct=int((wins / buys) * 100) if buys else 0,
            estimated_pnl_sol=round(simulated_pnl, 6),
            max_drawdown_sol=round(trough, 6),
            profit_factor=round(gross_win / gross_loss, 2) if gross_loss else 0.0,
            pnl_curve=pnl_curve[-120:],
            trades=trades[:120],
            replay_source=replay_source,
        )
        self.backtest_runs.appendleft(run)
        self.storage.save_backtest_run(run)
        return run

    def backtests(self) -> list[dict[str, object]]:
        return [run.to_dict() for run in self.backtest_runs]

    def source_events(self, limit: int = 80) -> list[dict[str, object]]:
        return [event.to_dict() for event in self.storage.load_source_events(limit)]

    def trades(self, limit: int = 300) -> list[dict[str, object]]:
        return [trade.to_dict() for trade in self.storage.load_trades(limit)]

    def source_health(self) -> dict[str, object]:
        events = self.storage.load_source_events(300)
        normalized = [event for event in events if event.status == "normalized"]
        failures = len([event for event in events if event.status == "raw"])
        last_age = None
        if self.source_status.last_event_at:
            last_age = max(0, int((utc_now() - self.source_status.last_event_at).total_seconds()))
        raw = max(1, self.source_status.raw_events_seen)
        ratio = self.source_status.normalized_events / raw
        health = 100
        if self.source_status.status != "connected":
            health -= 35
        if last_age is not None and last_age > self.settings.source_stale_seconds:
            health -= 25
        if ratio < 0.35:
            health -= 20
        health -= min(20, max(0, self.source_status.reconnect_attempts - self.settings.source_max_reconnects) * 4)
        newest_normalized = normalized[0] if normalized else None
        cutoff = utc_now() - timedelta(minutes=1)
        recent_events = [event for event in events if event.received_at >= cutoff]
        recent_normalized = [event for event in recent_events if event.status == "normalized"]
        status_message = "healthy"
        if health < 50:
            status_message = "degraded"
        if self.source_status.status != "connected":
            status_message = "offline"
        return {
            "status": self.source_status.status,
            "events_per_minute": round(len(recent_events), 2),
            "normalized_ratio": round(ratio, 3),
            "recent_normalized_ratio": round(len(recent_normalized) / max(1, len(recent_events)), 3),
            "normalization_failures": failures,
            "last_event_age_seconds": last_age,
            "reconnect_attempts": self.source_status.reconnect_attempts,
            "health_score": max(0, min(100, health)),
            "status_message": status_message,
            "last_valid_token_id": newest_normalized.normalized_token_id if newest_normalized else None,
            "last_source_message": self.source_status.message,
            "trade_events": len([event for event in events if event.status == "trade"]),
            "reliability_note": "Using one PumpPortal WebSocket for launch and token trade subscriptions.",
        }

    def _settings_for_profile(self, profile: str | None) -> BotSettings:
        if not profile or profile == self.settings.strategy_profile:
            return self.settings
        current = asdict(self.settings)
        presets: dict[str, dict[str, object]] = {
            "conservative": {"trade_size_sol": 0.05, "score_threshold": 72, "max_creator_hold_pct": 6, "risk_tolerance": "low", "trading_speed": "slow"},
            "balanced": {"trade_size_sol": 0.1, "score_threshold": 62, "max_creator_hold_pct": 10, "risk_tolerance": "medium", "trading_speed": "normal"},
            "aggressive": {"trade_size_sol": 0.15, "score_threshold": 54, "max_creator_hold_pct": 16, "risk_tolerance": "high", "trading_speed": "fast"},
            "scalper": {"trade_size_sol": 0.08, "score_threshold": 58, "max_creator_hold_pct": 12, "risk_tolerance": "medium", "trading_speed": "turbo"},
        }
        current.update(presets.get(profile, {}))
        current["strategy_profile"] = profile
        return BotSettings(**current)

    def _estimated_replay_pnl(self, token: TokenSignal, settings: BotSettings) -> float:
        edge = (token.score - 50) / 1000
        flow = (token.buy_velocity - token.sell_pressure) * 0.015
        fee_drag = (settings.paper_fee_bps / 10000) * settings.trade_size_sol * 2
        impact_drag = settings.trade_size_sol * (settings.paper_price_impact_pct / 100)
        return round(edge + flow - fee_drag - impact_drag, 6)

    def _filter_tokens_by_date(self, tokens: list[TokenSignal], date_from: str | None, date_to: str | None) -> list[TokenSignal]:
        start = self._parse_date(date_from)
        end = self._parse_date(date_to)
        return [token for token in tokens if (start is None or token.detected_at >= start) and (end is None or token.detected_at <= end)]

    def _filter_source_events_by_date(self, events: list[SourceEvent], date_from: str | None, date_to: str | None) -> list[SourceEvent]:
        start = self._parse_date(date_from)
        end = self._parse_date(date_to)
        return [event for event in events if (start is None or event.received_at >= start) and (end is None or event.received_at <= end)]

    def _parse_date(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=utc_now().tzinfo)

    def export_data(self, target: str) -> dict[str, object]:
        if target == "tokens":
            return {"tokens": [token.to_dict() for token in self.storage.load_all_tokens()]}
        if target == "source_events":
            return {"source_events": [event.to_dict() for event in self.storage.load_source_events(5000)]}
        if target == "backtests":
            return {"backtests": [run.to_dict() for run in self.storage.load_backtest_runs(5000)]}
        if target == "trades":
            return {"trades": [trade.to_dict() for trade in self.storage.load_trades(5000)]}
        return {
            "tokens": [token.to_dict() for token in self.storage.load_all_tokens()],
            "events": [event.to_dict() for event in self.storage.load_all_events()],
            "source_events": [event.to_dict() for event in self.storage.load_source_events(5000)],
            "backtests": [run.to_dict() for run in self.storage.load_backtest_runs(5000)],
            "trades": [trade.to_dict() for trade in self.storage.load_trades(5000)],
        }

    def data_summary(self) -> dict[str, int]:
        return {
            "tokens": len(self.tokens),
            "events": len(self.events),
            "source_events": len(self.storage.load_source_events(10000)),
            "backtests": len(self.backtest_runs),
            "trades": len(self.storage.load_trades(10000)),
        }

    def clear_data(self, target: str) -> dict[str, int]:
        if target in {"tokens", "all"}:
            self.storage.clear_tokens()
            self.tokens.clear()
        if target in {"events", "all"}:
            self.storage.clear_events()
            self.events.clear()
        if target in {"source_events", "all"}:
            self.storage.clear_source_events()
        if target in {"backtests", "all"}:
            self.storage.clear_backtests()
            self.backtest_runs.clear()
        if target in {"trades", "all"}:
            self.storage.clear_trades()
        self.add_event("warning", f"Data cleared: {target}")
        self.recalculate_stats()
        return self.data_summary()

    def open_position_count(self) -> int:
        return sum(1 for token in self.tokens if token.status in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING})

    def recalculate_stats(self) -> None:
        skipped = [token for token in self.tokens if token.status == TokenStatus.SKIPPED]
        open_tokens = [token for token in self.tokens if token.status in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}]
        closed = [token for token in self.tokens if token.status == TokenStatus.PAPER_SOLD]
        wins = [token.pnl_sol or 0.0 for token in closed if (token.pnl_sol or 0.0) > 0]
        losses = [token.pnl_sol or 0.0 for token in closed if (token.pnl_sol or 0.0) < 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))

        self.stats = BotStats(
            total_trades=len(closed),
            successful_trades=len(wins),
            skipped_tokens=len(skipped),
            open_positions=len(open_tokens),
            closed_trades=len(closed),
            win_rate_pct=int((len(wins) / len(closed)) * 100) if closed else 0,
            total_pnl_sol=round(sum(token.pnl_sol or 0.0 for token in closed), 6),
            best_trade_sol=round(max([token.pnl_sol or 0.0 for token in closed], default=0.0), 6),
            worst_trade_sol=round(min([token.pnl_sol or 0.0 for token in closed], default=0.0), 6),
            average_win_sol=round(gross_win / len(wins), 6) if wins else 0.0,
            average_loss_sol=round(sum(losses) / len(losses), 6) if losses else 0.0,
            profit_factor=round(gross_win / gross_loss, 2) if gross_loss else 0.0,
            max_drawdown_sol=round(sum(losses), 6) if losses else 0.0,
        )

    def snapshot(self) -> BotSnapshot:
        return BotSnapshot(
            status=self.status,
            settings=self.settings,
            tokens=list(self.tokens),
            events=list(self.events),
            stats=self.stats,
            source_status=self.source_status,
        )
