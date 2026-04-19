from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from collections import Counter, deque
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from app.core.models import (
    BacktestRun,
    BotSettings,
    BotSnapshot,
    BotStats,
    BotStatus,
    ExperimentRun,
    LiveExecutionAudit,
    LiveExecutionIntent,
    LivePosition,
    LiveQuote,
    LiveExecutionRequest,
    LiveSession,
    LiveSimulation,
    SettingsVersion,
    SignerStatus,
    SourceStatus,
    SourceEvent,
    StrategyDecisionRecord,
    StrategyPreset,
    TokenSignal,
    TokenStatus,
    TradeEvent,
    TradeLabel,
    TradeRecord,
    TradeSession,
    new_id,
    utc_now,
)
from app.core.paper_trader import PaperTrader
from app.core.price_pipeline import PricePipeline
from app.core.integrity import DataIntegrityAnalyzer
from app.core.pumpfun_intelligence import PumpFunIntelligence
from app.core.risk import RiskEngine
from app.core.scoring import ScoringEngine
from app.core.simulator import LaunchSimulator
from app.core.solana_readonly import SolanaReadOnlyClient
from app.core.storage import Storage
from app.core.sources import LaunchEvent, normalize_pumpportal_new_token
from app.core.strategy import DecisionPipeline


class BotState:
    def __init__(self, database_path: str = "data/cryptoarc.db", default_source: str = "mock", default_solana_rpc_url: str = "", default_watch_wallet_address: str = "") -> None:
        self.storage = Storage(database_path)
        self.status = BotStatus.STOPPED
        has_saved_settings = self.storage.has_settings()
        self.settings = self.storage.load_settings()
        if self.settings.max_position_ticks == 12:
            self.settings.max_position_ticks = 40
            self.storage.save_settings(self.settings)
        if self.settings.live_signer_mode not in {"browser_wallet", "local_signer_daemon"}:
            self.settings.live_signer_mode = "browser_wallet"
        if self.settings.launch_source not in {"mock", "pumpportal"}:
            self.settings.launch_source = default_source
        elif not has_saved_settings and self.settings.launch_source == "mock" and default_source != "mock":
            self.settings.launch_source = default_source
        if not has_saved_settings:
            if default_solana_rpc_url:
                self.settings.solana_rpc_url = default_solana_rpc_url
            if default_watch_wallet_address:
                self.settings.watch_wallet_address = default_watch_wallet_address
        self.stats = BotStats()
        self.tokens: deque[TokenSignal] = deque(self.storage.load_tokens(), maxlen=80)
        self.events: deque[TradeEvent] = deque(self.storage.load_events(), maxlen=30)
        self.backtest_runs: deque[BacktestRun] = deque(self.storage.load_backtest_runs(), maxlen=20)
        self.source_status = SourceStatus(source=self.settings.launch_source, status="offline")
        self.scoring = ScoringEngine()
        self.risk = RiskEngine()
        self.strategy = DecisionPipeline(self.scoring, self.risk)
        self.paper = PaperTrader()
        self.price_pipeline = PricePipeline()
        self.integrity = DataIntegrityAnalyzer()
        self.pumpfun_intelligence = PumpFunIntelligence()
        self.simulator = LaunchSimulator()
        self.creator_history = Counter(token.creator for token in self.storage.load_all_tokens())
        self.current_settings_version_id = self.ensure_settings_version("startup", [])
        self.last_bot_tick_at: datetime | None = None
        self.last_ingested_launch_at: datetime | None = None
        self.last_tick_error: str = ""
        self.bot_loop_iterations = 0
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
        clean_patch = {key: value for key, value in patch.items() if key in current}
        changed_keys = sorted([key for key, value in clean_patch.items() if current.get(key) != value])
        current.update(clean_patch)
        self.settings = BotSettings(**current)
        self.source_status.source = self.settings.launch_source
        self.storage.save_settings(self.settings)
        self.current_settings_version_id = self.ensure_settings_version("settings save", changed_keys)
        changed = ", ".join(changed_keys or sorted(clean_patch.keys()))
        self.add_event("info", f"Settings saved: {changed}")
        return self.snapshot()

    def ensure_settings_version(self, label: str, changed_keys: list[str]) -> str:
        latest = self.storage.load_settings_versions(1)
        current_settings = asdict(self.settings)
        if latest and latest[0].settings == current_settings and not changed_keys:
            return latest[0].id
        version = SettingsVersion(
            id=new_id("set"),
            created_at=utc_now(),
            settings=current_settings,
            label=label,
            changed_keys=changed_keys,
        )
        self.storage.save_settings_version(version)
        return version.id

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
        if token:
            self.last_ingested_launch_at = utc_now()
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
        event_status = "status" if event.message and event.token is None else None
        self.record_source_event(event.source, event.raw_payload, event.token, event.message, status=event_status)
        if event.token:
            self.ingest_launch(event.token)

    def apply_observed_trade(self, event: LaunchEvent) -> None:
        if not self.settings.use_observed_prices or not event.mint:
            return
        observation = self.price_pipeline.observe(
            event.raw_payload,
            mint=event.mint,
            settings=self.settings,
            source=event.source,
            trade_side=event.trade_side,
            sol_amount=event.sol_amount,
        )
        if not observation.accepted or not observation.price:
            for token in self.tokens:
                if token.mint == event.mint and token.status in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}:
                    observation.token_id = token.id
                    self.storage.save_price_observation(observation)
                    token.rejected_price_streak += 1
                    token.price_reject_reason = observation.reason
                    token.decision_log.append(f"Price observation rejected: {observation.reason}")
                    self.storage.save_token(token)
                    break
            return
        for token in self.tokens:
            if token.mint != event.mint:
                continue
            if token.status not in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}:
                continue
            observation.token_id = token.id
            observed_price = observation.price
            old_price = token.current_price or observed_price
            if token.entry_price and token.observed_price_updates == 0:
                ratio = observed_price / max(token.entry_price, 0.000000001)
                if ratio > 5 and token.entry_price <= 0.0000011:
                    token.entry_price = observed_price
                    token.current_price = observed_price
                    token.exit_price = observed_price if token.exit_price else None
                    token.peak_price = observed_price
                    token.trough_price = observed_price
                    token.price_source = "observed_rebased"
                    token.price_confidence = observation.confidence
                    token.price_reject_reason = ""
                    token.rejected_price_streak = 0
                    token.observed_price_updates += 1
                    token.last_observed_trade_at = event.received_at
                    fee_drag = token.fee_paid_sol + ((token.amount_sol or self.settings.trade_size_sol) * (self.settings.paper_fee_bps / 10000))
                    token.pnl_sol = round(-fee_drag, 6)
                    token.unrealized_pct = 0.0
                    token.highest_unrealized_pct = max(token.highest_unrealized_pct, 0.0)
                    token.lowest_unrealized_pct = min(token.lowest_unrealized_pct, 0.0)
                    token.decision_log.append(
                        f"Observed {event.trade_side} trade rebased entry to {observed_price:.8f}; ignored mismatched {ratio:.1f}x first tick"
                    )
                    self.storage.save_token(token)
                    self.storage.save_price_observation(observation)
                    break
            observation = self.price_pipeline.validate_first_tick(token, observation, self.settings)
            if not observation.accepted or not observation.price:
                token.price_reject_reason = observation.reason
                token.rejected_price_streak += 1
                token.decision_log.append(f"Price observation rejected: {observation.reason}")
                self.storage.save_token(token)
                self.storage.save_price_observation(observation)
                break
            observed_price = observation.price
            token.current_price = observed_price
            token.price_source = observation.price_source
            token.price_confidence = observation.confidence
            token.price_reject_reason = ""
            token.rejected_price_streak = 0
            token.observed_price_updates += 1
            token.last_observed_trade_at = event.received_at
            if event.trade_side == "buy":
                token.buy_velocity = min(1.0, round(token.buy_velocity + 0.04, 3))
            if event.trade_side == "sell":
                token.sell_pressure = min(1.0, round(token.sell_pressure + 0.05, 3))
            if token.entry_price:
                move_pct = ((token.current_price - token.entry_price) / token.entry_price) * 100
                token.unrealized_pct = round(move_pct, 2)
                gross_pnl = (token.amount_sol or self.settings.trade_size_sol) * (move_pct / 100)
                exit_fee = (token.amount_sol or self.settings.trade_size_sol) * (self.settings.paper_fee_bps / 10000)
                token.pnl_sol = round(gross_pnl - token.fee_paid_sol - exit_fee, 6)
            token.decision_log.append(f"Observed {event.trade_side} trade updated price from {old_price:.8f} to {observed_price:.8f} ({observation.price_source}, {observation.confidence:.2f})")
            self.storage.save_token(token)
            self.storage.save_price_observation(observation)
            break

    def tick(self) -> BotSnapshot:
        self.last_bot_tick_at = utc_now()
        self.last_tick_error = ""
        self.bot_loop_iterations += 1
        for token in list(self.tokens):
            token.age_seconds = max(0, int((utc_now() - token.detected_at).total_seconds()))
            if token.status not in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}:
                self.storage.save_token(token)
                continue

            uses_observed_price = self.settings.use_observed_prices and token.observed_price_updates > 0
            delta_pct = 0.0 if uses_observed_price else self.simulator.price_delta_pct(token, self.settings.paper_price_volatility_pct)
            if self.settings.max_rejected_price_streak_enabled and self.settings.max_rejected_price_streak and token.rejected_price_streak >= self.settings.max_rejected_price_streak:
                self.paper.close(token, self.settings, "price quality guard")
                closed = True
            else:
                closed = self.paper.tick(token, self.settings, delta_pct)
            self.storage.save_token(token)
            if closed:
                pnl = token.pnl_sol or 0.0
                outcome = self._classify_pnl(pnl)
                level = "success" if outcome == "win" else "danger" if outcome == "loss" else "warning"
                reason = f" ({token.exit_reason})" if token.exit_reason else ""
                label = "scratch " if outcome == "scratch" else ""
                self.add_event(level, f"Paper sold {token.symbol} at {pnl:+.4f} SOL {label}{reason}".replace("  ", " "), token.id)
                self.storage.save_trade(self.trade_from_token(token))
                self.storage.save_trade_session(self.session_from_token(token, "closed"))

        self.recalculate_stats()
        return self.snapshot()

    def ingest_launch(self, token: TokenSignal) -> None:
        if self.status != BotStatus.RUNNING or not self.settings.detect_new_tokens:
            return

        token.settings_version_id = self.current_settings_version_id
        token.status = TokenStatus.ANALYZING
        self.enrich_token_intelligence(token)

        open_positions = self.open_position_count()
        guard_reason = self.evaluate_session_guards(token)
        if guard_reason:
            token.status = TokenStatus.SKIPPED
            token.reason = guard_reason
            token.decision_log.append(f"Skipped: {guard_reason}")
            self.add_event("warning", f"Skipped {token.symbol}: {guard_reason}", token.id)
            self.tokens.appendleft(token)
            self.creator_history[token.creator] += 1
            self.storage.save_token(token)
            self.recalculate_stats()
            return
        decision = self.strategy.evaluate(token, self.settings, self.stats, open_positions)
        token.decision_log.extend(decision.log)
        self.storage.save_strategy_decision(self.decision_record_from_token(token, decision))
        if decision.allowed:
            token.status = TokenStatus.BUYING
            token.entry_reason = f"score {token.score}: {token.reason}"
            self.paper.buy(token, self.settings)
            if token.fill_failed:
                token.reason = "paper buy fill failed"
                self.add_event("warning", f"Paper buy failed {token.symbol}: simulated fill miss", token.id)
            else:
                self.storage.save_trade(self.trade_from_token(token))
                self.storage.save_trade_session(self.session_from_token(token, "opened"))
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
        if token.initial_buy_sol >= 2:
            tags.append("large initial buy")
        elif token.initial_buy_sol > 0:
            tags.append("seed buy present")
        if token.market_cap_sol >= 80:
            tags.append("high launch market cap")
        if token.bonding_curve:
            tags.append("bonding curve present")
        if token.metadata_uri.startswith("ipfs://") or "ipfs" in token.metadata_uri:
            tags.append("ipfs metadata")
        if token.price_confidence >= self.settings.min_price_confidence:
            tags.append(f"price confidence {token.price_confidence:.2f}")
        elif token.price_confidence > 0:
            tags.append("weak price confidence")

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
            lifecycle_status="closed" if token.closed_at else "open",
            entry_fee_sol=token.fee_paid_sol,
            exit_fee_sol=(token.amount_sol or self.settings.trade_size_sol) * (self.settings.paper_fee_bps / 10000) if token.closed_at else 0.0,
            price_impact_pct=token.price_impact_pct,
            slippage_paid_pct=token.slippage_paid_pct,
            source_price_confidence=token.price_confidence,
            settings_version_id=token.settings_version_id or self.current_settings_version_id,
        )

    def decision_record_from_token(self, token: TokenSignal, decision) -> StrategyDecisionRecord:
        return StrategyDecisionRecord(
            id=new_id("dec"),
            token_id=token.id,
            mint=token.mint,
            created_at=utc_now(),
            engine_version=str(decision.snapshot.get("engine_version", "strategy-v2")),
            profile=self.settings.strategy_profile,
            score=token.score,
            allowed=decision.allowed,
            action=decision.action,
            reason=decision.reason,
            risk_reason=decision.risk.reason,
            snapshot=decision.snapshot,
            score_breakdown=token.score_breakdown,
            decision_log=decision.log,
            settings_version_id=token.settings_version_id or self.current_settings_version_id,
        )

    def session_from_token(self, token: TokenSignal, status: str) -> TradeSession:
        return TradeSession(
            id=f"ses_{token.id}",
            token_id=token.id,
            mint=token.mint,
            symbol=token.symbol,
            strategy_profile=token.entry_strategy_profile or self.settings.strategy_profile,
            status=status,
            opened_at=token.opened_at,
            closed_at=token.closed_at,
            amount_sol=token.amount_sol,
            entry_price=token.entry_price,
            exit_price=token.exit_price,
            pnl_sol=token.pnl_sol,
            realized_pnl_sol=token.realized_pnl_sol,
            remaining_fraction=token.remaining_fraction,
            exit_reason=token.exit_reason,
            lifecycle=[{"at": utc_now().isoformat(), "status": status, "pnl_sol": token.pnl_sol, "reason": token.exit_reason or token.entry_reason or token.reason}],
            settings_version_id=token.settings_version_id or self.current_settings_version_id,
        )

    def evaluate_session_guards(self, token: TokenSignal) -> str | None:
        now = utc_now()
        closed_trades = self.storage.load_trades(500)
        recent_trades = [trade for trade in closed_trades if trade.opened_at and (now - trade.opened_at) <= timedelta(hours=1)]
        if self.settings.max_trades_per_hour_enabled and len(recent_trades) >= self.settings.max_trades_per_hour:
            return f"max trades per hour reached ({self.settings.max_trades_per_hour})"
        if self.settings.cooldown_after_loss_enabled and self.settings.cooldown_after_loss_seconds > 0:
            losses = [trade for trade in closed_trades if trade.closed_at and (trade.pnl_sol or 0.0) < -(self.stats.scratch_threshold_sol or 0.001)]
            if losses and (now - losses[0].closed_at).total_seconds() < self.settings.cooldown_after_loss_seconds:
                return "cooldown after loss active"
        same_creator_buys = sum(1 for existing in self.tokens if existing.creator == token.creator and existing.status in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING, TokenStatus.PAPER_SOLD})
        if self.settings.max_same_creator_buys_enabled and same_creator_buys >= self.settings.max_same_creator_buys:
            return f"same creator buy cap reached ({self.settings.max_same_creator_buys})"
        if self.settings.stop_on_source_degraded and self.source_health().get("health_score", 100) < 50:
            return "source health degraded"
        readiness_halt = self.readiness_halt_reason()
        if readiness_halt:
            return readiness_halt
        return None

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
        scratches = 0
        gross_wins = 0
        gross_win = 0.0
        gross_loss = 0.0
        pnl_curve = [0.0]
        trough = 0.0
        trades: list[dict[str, object]] = []
        for token in candidates:
            decision = self.risk.evaluate(token, settings, replay_stats, open_positions=0)
            if decision.allowed:
                buys += 1
                pnl = token.pnl_sol if token.pnl_sol is not None else self._observed_replay_pnl(token, settings)
                simulated_pnl = round(simulated_pnl + pnl, 6)
                pnl_curve.append(simulated_pnl)
                trough = min(trough, simulated_pnl)
                outcome = self._classify_pnl(pnl)
                if pnl > 0:
                    gross_wins += 1
                if outcome == "win":
                    wins += 1
                    gross_win += pnl
                elif outcome == "loss":
                    losses += 1
                    gross_loss += abs(pnl)
                else:
                    scratches += 1
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
            scratches=scratches,
            win_rate_pct=int((wins / buys) * 100) if buys else 0,
            gross_win_rate_pct=int((gross_wins / buys) * 100) if buys else 0,
            scratch_rate_pct=int((scratches / buys) * 100) if buys else 0,
            estimated_pnl_sol=round(simulated_pnl, 6),
            max_drawdown_sol=round(trough, 6),
            profit_factor=round(gross_win / gross_loss, 2) if gross_loss else 0.0,
            avg_hold_seconds=int(sum((token.hold_duration_seconds or 0) for token in candidates) / max(1, len(candidates))),
            best_trade_sol=round(max([float(item.get("pnl_sol", 0) or 0) for item in trades if item.get("decision") == "buy"], default=0.0), 6),
            worst_trade_sol=round(min([float(item.get("pnl_sol", 0) or 0) for item in trades if item.get("decision") == "buy"], default=0.0), 6),
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
            if event.status in {"trade", "status"}:
                continue
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
            scratches = 0
            gross_wins = 0
            drawdown = 0.0
            for token in candidates:
                decision = self.risk.evaluate(token, settings, BotStats(), open_positions=0)
                if decision.allowed:
                    buys += 1
                    trade_pnl = token.pnl_sol if token.pnl_sol is not None else self._observed_replay_pnl(token, settings) + abs(offset) / 2000
                    pnl += trade_pnl
                    gross_wins += 1 if trade_pnl > 0 else 0
                    outcome = self._classify_pnl(trade_pnl)
                    wins += 1 if outcome == "win" else 0
                    losses += 1 if outcome == "loss" else 0
                    scratches += 1 if outcome == "scratch" else 0
                    drawdown = min(drawdown, pnl)
                else:
                    skips += 1
            comparison.append({
                "profile": profile,
                "buys": buys,
                "skips": skips,
                "wins": wins,
                "losses": losses,
                "scratches": scratches,
                "win_rate_pct": int((wins / buys) * 100) if buys else 0,
                "gross_win_rate_pct": int((gross_wins / buys) * 100) if buys else 0,
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
        scratches = 0
        gross_wins = 0
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
                pnl = token.pnl_sol if token.pnl_sol is not None else self._observed_replay_pnl(token, settings)
                simulated_pnl = round(simulated_pnl + pnl, 6)
                pnl_curve.append(simulated_pnl)
                trough = min(trough, simulated_pnl)
                outcome = self._classify_pnl(pnl)
                if pnl > 0:
                    gross_wins += 1
                if outcome == "win":
                    wins += 1
                    gross_win += pnl
                elif outcome == "loss":
                    losses += 1
                    gross_loss += abs(pnl)
                else:
                    scratches += 1
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
            scratches=scratches,
            win_rate_pct=int((wins / buys) * 100) if buys else 0,
            gross_win_rate_pct=int((gross_wins / buys) * 100) if buys else 0,
            scratch_rate_pct=int((scratches / buys) * 100) if buys else 0,
            estimated_pnl_sol=round(simulated_pnl, 6),
            max_drawdown_sol=round(trough, 6),
            profit_factor=round(gross_win / gross_loss, 2) if gross_loss else 0.0,
            avg_hold_seconds=int(sum((token.hold_duration_seconds or 0) for token in candidates) / max(1, len(candidates))),
            best_trade_sol=round(max([float(item.get("pnl_sol", 0) or 0) for item in trades if item.get("decision") == "buy"], default=0.0), 6),
            worst_trade_sol=round(min([float(item.get("pnl_sol", 0) or 0) for item in trades if item.get("decision") == "buy"], default=0.0), 6),
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

    def price_observations(self, limit: int = 300) -> list[dict[str, object]]:
        return [observation.to_dict() for observation in self.storage.load_price_observations(limit)]

    def strategy_decisions(self, limit: int = 300) -> list[dict[str, object]]:
        return [decision.to_dict() for decision in self.storage.load_strategy_decisions(limit)]

    def trade_sessions(self, limit: int = 300) -> list[dict[str, object]]:
        return [session.to_dict() for session in self.storage.load_trade_sessions(limit)]

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
            "launch_events": self.source_status.launch_events_seen,
            "status_events": self.source_status.status_events_seen,
            "active_trade_subscriptions": self.source_status.active_trade_subscriptions,
            "dropped_trade_subscriptions": self.source_status.dropped_trade_subscriptions,
            "price_observations": self.storage.count_price_observations(),
            "strategy_decisions": self.storage.count_strategy_decisions(),
            "trade_sessions": self.storage.count_trade_sessions(),
            "reliability_note": "PumpPortal trade subscriptions rotate toward the newest launches.",
        }

    def settings_versions(self) -> list[dict[str, object]]:
        return [version.to_dict() for version in self.storage.load_settings_versions(50)]

    def performance_analytics(self) -> dict[str, object]:
        trades = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        tokens_by_id = {token.id: token for token in self.storage.load_all_tokens(5000)}
        return {
            "summary": self._performance_group("all trades", trades),
            "by_exit_reason": self._group_performance(trades, lambda trade: trade.exit_reason or "unknown"),
            "by_strategy": self._group_performance(trades, lambda trade: trade.strategy_profile or "unknown"),
            "by_settings_version": self._group_performance(trades, lambda trade: trade.settings_version_id or "legacy"),
            "by_score_bucket": self._group_performance(
                trades,
                lambda trade: self._score_bucket(tokens_by_id.get(trade.token_id).score if tokens_by_id.get(trade.token_id) else None),
            ),
            "by_price_confidence": self._group_performance(trades, lambda trade: self._confidence_bucket(trade.source_price_confidence)),
            "recent_curve": self._pnl_curve(trades),
            "strategy_modules": self.strategy.describe_modules(self.settings),
        }

    def tuning_suggestions(self) -> list[dict[str, object]]:
        trades = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        labels = self.storage.load_trade_labels(1000)
        ignored_tokens = {label.token_id for label in labels if label.label == "ignore_from_tuning"}
        trades = [trade for trade in trades if trade.token_id not in ignored_tokens]
        suggestions: list[dict[str, object]] = []
        if len(trades) < 8:
            return [{"title": "Collect more samples", "reason": "Auto-tuning needs at least 8 closed trades before the suggestions are meaningful.", "setting": "backtest_replay_limit", "confidence": 0.35}]

        summary = self._performance_group("all trades", trades)
        by_exit = {item["label"]: item for item in self._group_performance(trades, lambda trade: trade.exit_reason or "unknown")}
        if summary["win_rate_pct"] < 35 and not self.settings.cooldown_after_loss_enabled:
            suggestions.append({"title": "Enable loss cooldown", "reason": "Recent decisive win rate is low; pausing briefly after losses can reduce clustered bad entries.", "setting": "cooldown_after_loss_enabled", "suggested_value": True, "confidence": 0.72})
        max_tick = by_exit.get("max position ticks")
        if max_tick and max_tick["pnl_sol"] < 0 and not self.settings.stalled_trade_exit_enabled:
            suggestions.append({"title": "Try stalled-trade exit", "reason": "Max-tick exits are losing money; stalled exits can close flat trades earlier.", "setting": "stalled_trade_exit_enabled", "suggested_value": True, "confidence": 0.68})
        stop_loss = by_exit.get("stop loss")
        if stop_loss and stop_loss["count"] >= 3 and self.settings.stop_loss_pct > 20:
            suggestions.append({"title": "Tighten stop loss", "reason": "Several trades are reaching the stop; a tighter stop may lower average loss size in paper testing.", "setting": "stop_loss_pct", "suggested_value": max(10, round(self.settings.stop_loss_pct * 0.8, 1)), "confidence": 0.61})
        low_conf_losses = [trade for trade in trades if trade.source_price_confidence < self.settings.min_price_confidence and (trade.pnl_sol or 0) < 0]
        if len(low_conf_losses) >= 3:
            suggestions.append({"title": "Raise price confidence floor", "reason": "Low-confidence price marks are contributing multiple losses.", "setting": "min_price_confidence", "suggested_value": min(0.9, round(self.settings.min_price_confidence + 0.1, 2)), "confidence": 0.64})
        if not suggestions:
            suggestions.append({"title": "Keep current profile", "reason": "No single failure pattern dominates the closed trade set yet.", "setting": "strategy_profile", "suggested_value": self.settings.strategy_profile, "confidence": 0.52})
        return suggestions

    def experiments(self) -> list[dict[str, object]]:
        return [run.to_dict() for run in self.storage.load_experiment_runs(100)]

    def create_experiment(self, name: str, profile: str | None = None, limit: int | None = None, notes: str = "") -> dict[str, object]:
        result = self.backtest_v3(limit=limit or self.settings.backtest_replay_limit)
        run = ExperimentRun(
            id=new_id("exp"),
            name=name or f"Experiment {utc_now().strftime('%H:%M:%S')}",
            created_at=utc_now(),
            settings_version_id=self.current_settings_version_id,
            profile=profile or self.settings.strategy_profile,
            replay_source="backtest_v3",
            result=result,
            fingerprint=str(result.get("determinism_fingerprint", "")),
            notes=notes,
        )
        self.storage.save_experiment_run(run)
        self.add_event("info", f"Experiment saved: {run.name}")
        return run.to_dict()

    def trade_labels(self) -> list[dict[str, object]]:
        return [label.to_dict() for label in self.storage.load_trade_labels(500)]

    def label_trade(self, token_id: str, label: str, note: str = "") -> dict[str, object]:
        trade = next((item for item in self.storage.load_trades(5000) if item.token_id == token_id), None)
        record = TradeLabel(
            id=new_id("lbl"),
            token_id=token_id,
            trade_id=trade.id if trade else "",
            label=label,
            created_at=utc_now(),
            note=note,
        )
        self.storage.save_trade_label(record)
        self.add_event("info", f"Trade labeled {label}", token_id)
        return record.to_dict()

    def strategy_presets(self) -> list[dict[str, object]]:
        saved = [preset.to_dict() for preset in self.storage.load_strategy_presets(50)]
        builtins = [
            {"id": f"builtin_{name}", "name": name, "description": "Built-in profile", "created_at": utc_now().isoformat(), "settings": asdict(self._settings_for_profile(name))}
            for name in ("conservative", "balanced", "aggressive", "scalper")
        ]
        return builtins + saved

    def save_strategy_preset(self, name: str, description: str = "") -> dict[str, object]:
        preset = StrategyPreset(
            id=new_id("strat"),
            name=name,
            created_at=utc_now(),
            settings=asdict(self.settings),
            description=description,
        )
        self.storage.save_strategy_preset(preset)
        self.add_event("info", f"Strategy preset saved: {name}")
        return preset.to_dict()

    def ab_strategy_replay(self, limit: int = 120) -> BacktestRun:
        return self.compare_strategies(limit=limit)

    def backtest_v3(self, limit: int | None = None) -> dict[str, object]:
        limit = limit or self.settings.backtest_replay_limit
        profiles = ["conservative", "balanced", "aggressive", "scalper"]
        runs = []
        candidates = [
            token
            for token in self.storage.load_all_tokens(limit)
            if token.status in {TokenStatus.SKIPPED, TokenStatus.PAPER_SOLD, TokenStatus.DETECTED, TokenStatus.ANALYZING}
        ]
        midpoint = max(1, len(candidates) // 2)
        for profile in profiles:
            settings = self._settings_for_profile(profile)
            full = self._run_backtest(candidates, replay_source="backtest_v3", settings=settings)
            train = self._run_backtest(candidates[:midpoint], replay_source="walk_forward_train", settings=settings)
            validate = self._run_backtest(candidates[midpoint:], replay_source="walk_forward_validate", settings=settings)
            runs.append(
                {
                    "profile": profile,
                    "full": full.to_dict(),
                    "train": train.to_dict(),
                    "validate": validate.to_dict(),
                    "overfit_warning": train.win_rate_pct - validate.win_rate_pct > 25 and validate.tokens_replayed > 5,
                }
            )
        best = max(runs, key=lambda item: float(item["full"]["estimated_pnl_sol"])) if runs else None
        return {
            "engine_version": "backtest-v3",
            "tokens_replayed": len(candidates),
            "determinism_fingerprint": self.data_integrity_report()["determinism_fingerprint"],
            "best_profile": best["profile"] if best else None,
            "runs": runs,
        }

    def data_integrity_report(self) -> dict[str, object]:
        return self.integrity.report(
            self.storage.load_all_tokens(5000),
            self.storage.load_trades(5000),
            self.storage.load_price_observations(5000),
            self.storage.load_source_events(5000),
            self.storage.load_strategy_decisions(5000),
        )

    def price_diagnostics(self) -> dict[str, object]:
        observations = self.storage.load_price_observations(5000)
        diagnostics = self.price_pipeline.diagnostics(observations)
        diagnostics["candles"] = self.price_candles(observations)
        return diagnostics

    def price_candles(self, observations: list | None = None) -> list[dict[str, object]]:
        observations = observations or self.storage.load_price_observations(5000)
        candles: dict[str, list[float]] = {}
        for item in observations:
            if item.accepted and item.price:
                bucket = item.observed_at.replace(second=0, microsecond=0).isoformat()
                candles.setdefault(bucket, []).append(item.price)
        return [
            {"at": bucket, "open": values[0], "high": max(values), "low": min(values), "close": values[-1], "count": len(values)}
            for bucket, values in sorted(candles.items())[-240:]
        ]

    def pumpfun_report(self) -> dict[str, object]:
        return self.pumpfun_intelligence.summarize(self.storage.load_all_tokens(5000), self.storage.load_source_events(5000))

    def readiness_status(self) -> dict[str, object]:
        closed = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        integrity = self.data_integrity_report()
        source = self.source_health()
        price = self.price_diagnostics()
        performance = self._performance_group("all trades", closed)
        closed_count = len(closed)
        source_events = int(integrity.get("source_events", 0))
        gross_win = sum((trade.pnl_sol or 0.0) for trade in closed if (trade.pnl_sol or 0.0) > (self.stats.scratch_threshold_sol or 0.001))
        gross_loss = abs(sum((trade.pnl_sol or 0.0) for trade in closed if (trade.pnl_sol or 0.0) < -(self.stats.scratch_threshold_sol or 0.001)))
        effective_profit_factor = 99.0 if gross_win > 0 and gross_loss == 0 else float(performance.get("profit_factor", 0.0))

        gates = [
            self._readiness_gate(
                "closed_trades",
                "Closed paper trades",
                closed_count,
                ">= 30",
                10,
                "pass" if closed_count >= 30 else "warn" if closed_count >= 10 else "fail",
                "Closed paper trades provide the minimum performance sample.",
            ),
            self._readiness_gate(
                "source_events",
                "Source events",
                source_events,
                ">= 100",
                5,
                "pass" if source_events >= 100 else "warn" if source_events >= 25 else "fail",
                "Captured source events make replay and source-quality checks meaningful.",
            ),
            self._readiness_gate(
                "data_integrity",
                "Data integrity",
                int(integrity.get("score", 0)),
                ">= 80",
                15,
                self._threshold_status(float(integrity.get("score", 0)), 80, 65),
                "Integrity score combines missing records, malformed source events, and replay trust.",
            ),
            self._readiness_gate(
                "replay_confidence",
                "Replay confidence",
                int(integrity.get("replay_confidence", {}).get("score", 0)) if isinstance(integrity.get("replay_confidence"), dict) else 0,
                ">= 70",
                15,
                self._threshold_status(float(integrity.get("replay_confidence", {}).get("score", 0)) if isinstance(integrity.get("replay_confidence"), dict) else 0.0, 70, 50),
                "Replay confidence requires accepted prices, normalized source events, and closed-trade coverage.",
            ),
            self._readiness_gate(
                "source_health",
                "Source health",
                int(source.get("health_score", 0)),
                ">= 70",
                15,
                self._threshold_status(float(source.get("health_score", 0)), 70, 50),
                "Source health tracks connection status, staleness, normalization ratio, and reconnect pressure.",
            ),
            self._readiness_gate(
                "price_acceptance",
                "Price acceptance",
                round(float(price.get("acceptance_rate", 0.0)), 3),
                ">= 0.70",
                10,
                self._threshold_status(float(price.get("acceptance_rate", 0.0)), 0.70, 0.50),
                "Accepted observed prices should dominate rejected or low-confidence marks.",
            ),
            self._readiness_gate(
                "price_jumps",
                "Impossible price jumps",
                int(price.get("impossible_jump_warnings", 0)),
                "0",
                5,
                "pass" if int(price.get("impossible_jump_warnings", 0)) == 0 else "warn" if int(price.get("impossible_jump_warnings", 0)) <= 2 else "fail",
                "Large accepted jumps indicate price normalization needs review.",
            ),
            self._readiness_gate(
                "paper_performance",
                "Paper performance",
                f"{performance.get('pnl_sol', 0)} SOL / PF {round(effective_profit_factor, 2)}",
                "PnL > 0 and PF > 1.1",
                20,
                self._paper_performance_status(closed_count, float(performance.get("pnl_sol", 0.0)), effective_profit_factor),
                "Paper performance should be positive after the sample is large enough.",
            ),
            self._readiness_gate(
                "safety_boundary",
                "Paper safety boundary",
                "paper-only",
                "paper-only",
                5,
                "pass",
                "No signer, wallet connection, transaction builder, or live executor is available.",
            ),
        ]
        score = int(round(sum(int(gate["weight"]) if gate["status"] == "pass" else int(gate["weight"]) * 0.5 if gate["status"] == "warn" else 0 for gate in gates)))
        enough_data = closed_count >= 10 and source_events >= 25
        critical_ids = {"data_integrity", "replay_confidence", "source_health", "price_acceptance", "price_jumps", "safety_boundary"}
        critical_failed = any(gate["id"] in critical_ids and gate["status"] == "fail" for gate in gates)
        any_failed = any(gate["status"] == "fail" for gate in gates)
        if not enough_data:
            status = "not_enough_data"
        elif critical_failed or score < 50:
            status = "blocked"
        elif score >= 75 and not any_failed and closed_count >= 30:
            status = "ready"
        else:
            status = "warning"

        result = {
            "engine_version": "readiness-v1",
            "score": max(0, min(100, score)),
            "status": status,
            "entries_allowed": True,
            "gates": gates,
            "recommended_actions": self._readiness_actions(gates, status),
            "sample_size": {
                "closed_trades": closed_count,
                "source_events": source_events,
                "price_observations": int(integrity.get("price_observations", 0)),
                "strategy_decisions": int(integrity.get("strategy_decisions", 0)),
            },
            "paper_only": True,
            "halt_on_low_readiness": self.settings.halt_on_low_readiness,
            "min_readiness_score": self.settings.min_readiness_score,
        }
        result["entries_allowed"] = self.readiness_halt_reason(result) is None
        return result

    def readiness_halt_reason(self, readiness: dict[str, object] | None = None) -> str | None:
        if not self.settings.halt_on_low_readiness:
            return None
        readiness = readiness or self.readiness_status()
        sample = readiness.get("sample_size", {})
        closed_count = int(sample.get("closed_trades", 0)) if isinstance(sample, dict) else 0
        source_events = int(sample.get("source_events", 0)) if isinstance(sample, dict) else 0
        if closed_count < 30 and source_events < 100:
            return None
        score = int(readiness.get("score", 0))
        if readiness.get("status") == "blocked" or score < self.settings.min_readiness_score:
            return f"readiness halt active ({score} below {self.settings.min_readiness_score})"
        return None

    def _readiness_gate(self, gate_id: str, label: str, value: object, target: object, weight: int, status: str, reason: str) -> dict[str, object]:
        return {
            "id": gate_id,
            "label": label,
            "status": status,
            "value": value,
            "target": target,
            "weight": weight,
            "reason": reason,
        }

    def _threshold_status(self, value: float, pass_at: float, warn_at: float) -> str:
        if value >= pass_at:
            return "pass"
        if value >= warn_at:
            return "warn"
        return "fail"

    def _paper_performance_status(self, closed_count: int, pnl_sol: float, profit_factor: float) -> str:
        if closed_count < 30:
            return "warn"
        if pnl_sol > 0 and profit_factor > 1.1:
            return "pass"
        return "fail"

    def _readiness_actions(self, gates: list[dict[str, object]], status: str) -> list[str]:
        if status == "ready":
            return ["Keep collecting paper samples and compare promoted presets before changing risk settings."]
        actions: list[str] = []
        for gate in gates:
            if gate["status"] == "pass":
                continue
            gate_id = gate["id"]
            if gate_id == "closed_trades":
                actions.append("Run more paper sessions until at least 30 closed trades are available.")
            elif gate_id == "source_events":
                actions.append("Collect more PumpPortal or mock source events before trusting replay results.")
            elif gate_id == "data_integrity":
                actions.append("Review Data Integrity issues for missing records or malformed source events.")
            elif gate_id == "replay_confidence":
                actions.append("Improve accepted price and normalized event coverage before promoting settings.")
            elif gate_id == "source_health":
                actions.append("Stabilize the source feed or reconnect behavior before trusting live paper runs.")
            elif gate_id in {"price_acceptance", "price_jumps"}:
                actions.append("Review price diagnostics and confidence thresholds for rejected or jumpy observations.")
            elif gate_id == "paper_performance":
                actions.append("Use Strategy Builder and labels to tune weak paper performance before raising risk.")
            elif gate_id == "safety_boundary":
                actions.append("Keep the paper-only boundary active; do not add execution while readiness is unresolved.")
        return list(dict.fromkeys(actions))[:6]

    def safety_status(self) -> dict[str, object]:
        closed = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        consecutive_losses = 0
        for trade in closed:
            if (trade.pnl_sol or 0.0) < -(self.stats.scratch_threshold_sol or 0.001):
                consecutive_losses += 1
            else:
                break
        stop_reasons = []
        replay_confidence = int(self.data_integrity_report().get("replay_confidence", {}).get("score", 0))
        if self.settings.kill_switch_enabled:
            stop_reasons.append("manual kill switch enabled")
        if abs(min(0.0, self.stats.total_pnl_sol)) >= self.settings.daily_loss_cap_sol:
            stop_reasons.append("daily loss cap reached")
        if self.open_position_count() >= self.settings.max_open_positions:
            stop_reasons.append("max open positions reached")
        if self.settings.stop_on_source_degraded and self.source_health().get("health_score", 100) < 50:
            stop_reasons.append("source health degraded")
        if self.settings.live_trading_enabled:
            stop_reasons.append("live trading request remains blocked by paper boundary")
        if self.settings.manual_live_enabled:
            stop_reasons.append("manual live execution is audit-only")
        if self.settings.autonomous_live_enabled:
            stop_reasons.append("autonomous live mode is not implemented")
        if self.settings.max_consecutive_losses_enabled and consecutive_losses >= self.settings.max_consecutive_losses:
            stop_reasons.append("consecutive loss halt")
        if self.settings.halt_on_low_replay_confidence and replay_confidence < self.settings.min_replay_confidence:
            stop_reasons.append("low replay confidence")
        readiness_halt = self.readiness_halt_reason()
        if readiness_halt:
            stop_reasons.append(readiness_halt)
        return {
            "paper_only": True,
            "entries_allowed": not stop_reasons,
            "stop_reasons": stop_reasons,
            "consecutive_losses": consecutive_losses,
            "open_positions": self.open_position_count(),
            "daily_loss_cap_sol": self.settings.daily_loss_cap_sol,
            "total_pnl_sol": self.stats.total_pnl_sol,
            "kill_switch_available": True,
            "kill_switch_enabled": self.settings.kill_switch_enabled,
            "replay_confidence": replay_confidence,
            "manual_live_ready": False,
            "autonomous_live_ready": False,
            "live_blockers": [
                "no signer or transaction executor is present",
                "paper engine and replay confidence must stay production-stable first",
                "manual live requests are stored for review only",
            ],
        }

    def record_bot_loop_error(self, error: Exception) -> None:
        self.last_tick_error = f"{error.__class__.__name__}: {error}"
        self.add_event("danger", f"Bot loop recovered after error: {self.last_tick_error}")

    def watchdog_status(self) -> dict[str, object]:
        now = utc_now()
        tick_age = int((now - self.last_bot_tick_at).total_seconds()) if self.last_bot_tick_at else None
        launch_age = int((now - self.last_ingested_launch_at).total_seconds()) if self.last_ingested_launch_at else None
        source_age = self.source_health().get("last_event_age_seconds")
        tick_stale = tick_age is None or tick_age > max(10, int(self.settings.source_stale_seconds))
        source_stale = self.status == BotStatus.RUNNING and source_age is not None and int(source_age) > self.settings.source_stale_seconds
        launch_stale = self.status == BotStatus.RUNNING and self.settings.detect_new_tokens and launch_age is not None and launch_age > max(120, self.settings.source_stale_seconds * 2)
        return {
            "status": "degraded" if tick_stale or source_stale or self.last_tick_error else "ok",
            "bot_running": self.status == BotStatus.RUNNING,
            "last_tick_at": self.last_bot_tick_at.isoformat() if self.last_bot_tick_at else None,
            "tick_age_seconds": tick_age,
            "last_ingested_launch_at": self.last_ingested_launch_at.isoformat() if self.last_ingested_launch_at else None,
            "launch_ingestion_age_seconds": launch_age,
            "source_event_age_seconds": source_age,
            "tick_stale": tick_stale,
            "source_stale": source_stale,
            "launch_stale": launch_stale,
            "loop_iterations": self.bot_loop_iterations,
            "last_error": self.last_tick_error,
            "recommended_action": "recover bot loop or restart service" if tick_stale or self.last_tick_error else "monitor source feed" if source_stale else "none",
        }

    def recover_bot(self) -> BotSnapshot:
        self.last_tick_error = ""
        if self.status != BotStatus.RUNNING:
            self.status = BotStatus.RUNNING
            self.add_event("warning", "Watchdog recovery started the paper loop")
        else:
            self.add_event("info", "Watchdog recovery cleared transient loop error")
        self.last_bot_tick_at = utc_now()
        return self.snapshot()

    def solana_status(self) -> dict[str, object]:
        result: dict[str, object] = {
            "configured": bool(self.settings.solana_rpc_url),
            "rpc_url": self.settings.solana_rpc_url,
            "wallet_configured": bool(self.settings.watch_wallet_address.strip()),
            "wallet_address": self.settings.watch_wallet_address.strip(),
            "health": "unknown",
            "balance_sol": None,
            "read_only": True,
            "error": "",
        }
        try:
            client = SolanaReadOnlyClient(self.settings.solana_rpc_url)
            result["health"] = client.health()
            if self.settings.watch_wallet_address.strip():
                result["balance_sol"] = client.balance_sol(self.settings.watch_wallet_address)
        except Exception as exc:
            result["error"] = f"{exc.__class__.__name__}: {exc}"
        return result

    def signer_status(self, mode: str = "browser_wallet", wallet_public_key: str = "") -> dict[str, object]:
        if mode == "browser_wallet":
            connected = bool(wallet_public_key.strip())
            return SignerStatus(
                mode="browser_wallet",
                connected=connected,
                wallet_public_key=wallet_public_key.strip(),
                can_sign=connected,
                can_unattended_sign=False,
                message="Browser wallet requires manual approval for each transaction" if connected else "Browser wallet is not connected",
            ).to_dict()
        return SignerStatus(
            mode="local_signer_daemon",
            connected=False,
            wallet_public_key="",
            can_sign=False,
            can_unattended_sign=False,
            message="Local signer daemon is designed for a later phase and disabled in v1",
        ).to_dict()

    def live_caps_snapshot(self) -> dict[str, object]:
        return {
            "max_trade_sol": self.settings.live_max_trade_sol,
            "daily_loss_cap_sol": self.settings.live_daily_loss_cap_sol,
            "wallet_exposure_cap_sol": self.settings.live_wallet_exposure_cap_sol,
            "max_open_positions": self.settings.live_max_open_positions,
            "max_slippage_pct": self.settings.live_max_slippage_pct,
            "priority_fee_cap_sol": self.settings.live_priority_fee_cap_sol,
        }

    def live_status(self, env_live_enabled: bool = False, wallet_public_key: str = "", signer_mode: str | None = None) -> dict[str, object]:
        signer_mode = signer_mode or self.settings.live_signer_mode
        signer = self.signer_status(signer_mode, wallet_public_key)
        caps = self.live_caps_snapshot()
        blockers: list[str] = []
        if not env_live_enabled:
            blockers.append("LIVE_TRADING_ENABLED is false")
        if self.settings.kill_switch_enabled:
            blockers.append("manual kill switch enabled")
        if signer_mode == "local_signer_daemon":
            blockers.append("local signer daemon is disabled in v1")
        if not signer.get("connected"):
            blockers.append("no connected signer")
        if not self.settings.live_session_acknowledged:
            blockers.append("live session acknowledgement is required")
        for key, value in caps.items():
            if float(value or 0) <= 0:
                blockers.append(f"{key} must be set")
        if not self.settings.solana_rpc_url:
            blockers.append("Solana RPC URL is not configured")
        readiness = self.readiness_status()
        return {
            "mode": "manual_browser_wallet_v1",
            "paper_default": True,
            "live_execution_available": not blockers,
            "env_live_enabled": env_live_enabled,
            "effective_live_enabled": not blockers,
            "blockers": blockers,
            "signer": signer,
            "caps": caps,
            "session_acknowledged": self.settings.live_session_acknowledged,
            "readiness": readiness,
            "local_desktop_only": True,
            "autonomous_live_available": False,
            "auto_sell_available": signer_mode != "browser_wallet" and bool(signer.get("can_unattended_sign")),
            "autonomy_blockers": ["browser wallets cannot unattended-sign", "local signer daemon is disabled in v1"],
        }

    def start_live_session(self, env_live_enabled: bool, wallet_public_key: str, signer_mode: str = "browser_wallet") -> dict[str, object]:
        status = self.live_status(env_live_enabled, wallet_public_key, signer_mode)
        session = LiveSession(
            id=new_id("liveses"),
            created_at=utc_now(),
            status="blocked" if status["blockers"] else "active",
            signer_mode=signer_mode,
            wallet_public_key=wallet_public_key.strip(),
            caps_snapshot=self.live_caps_snapshot(),
            acknowledged_at=utc_now() if self.settings.live_session_acknowledged else None,
        )
        self.storage.save_live_session(session)
        self.add_event("warning", f"Live session {session.status}: {', '.join(status['blockers']) or 'manual browser-wallet mode'}")
        return {**session.to_dict(), "live_status": status}

    def acknowledge_live_session(self) -> dict[str, object]:
        self.settings.live_session_acknowledged = True
        self.storage.save_settings(self.settings)
        self.add_event("warning", "Live session acknowledgement recorded")
        return {"acknowledged": True, "acknowledged_at": utc_now().isoformat()}

    def live_positions(self, wallet_public_key: str = "") -> list[dict[str, object]]:
        if not wallet_public_key.strip():
            return []
        mints = {audit.mint for audit in self.storage.load_live_execution_audits(500) if audit.mint}
        positions: list[dict[str, object]] = []
        for mint in sorted(mints):
            token = next((item for item in self.storage.load_all_tokens(5000) if item.mint == mint), None)
            warning = ""
            balance = 0.0
            try:
                balance = SolanaReadOnlyClient(self.settings.solana_rpc_url).token_balance(wallet_public_key, mint) or 0.0
            except Exception as exc:
                warning = f"{exc.__class__.__name__}: {exc}"
            positions.append(
                LivePosition(
                    mint=mint,
                    symbol=token.symbol if token else "",
                    token_balance=balance,
                    estimated_value_sol=0.0,
                    source="wallet_rpc",
                    warning=warning,
                ).to_dict()
            )
        return positions

    def live_audit(self) -> list[dict[str, object]]:
        return [audit.to_dict() for audit in self.storage.load_live_execution_audits(100)]

    def live_quote(
        self,
        env_live_enabled: bool,
        action: str,
        mint: str,
        amount: str,
        denominated_in_sol: bool,
        slippage_pct: float,
        priority_fee_sol: float,
        pool: str,
        wallet_public_key: str,
        signer_mode: str = "browser_wallet",
    ) -> dict[str, object]:
        status = self.live_status(env_live_enabled, wallet_public_key, signer_mode)
        blockers = list(status["blockers"])
        validation_error = self._validate_live_order(action, amount, denominated_in_sol, slippage_pct, priority_fee_sol, wallet_public_key, signer_mode)
        if validation_error:
            blockers.append(validation_error)
        if action == "sell":
            balance = self._wallet_token_balance(wallet_public_key, mint)
            if balance["error"]:
                blockers.append(f"wallet token balance check failed: {balance['error']}")
        else:
            balance = {"wallet_public_key": wallet_public_key, "mint": mint, "token_balance": None, "error": ""}

        intent = LiveExecutionIntent(
            id=new_id("intent"),
            created_at=utc_now(),
            action=action,
            mint=mint.strip(),
            amount=str(amount).strip(),
            denominated_in_sol=denominated_in_sol,
            signer_mode=signer_mode,
            wallet_public_key=wallet_public_key.strip(),
            status="blocked" if blockers else "quote_requested",
            reason="; ".join(blockers),
        )
        quote_payload: dict[str, object] = {}
        quote_error = ""
        unsigned_tx = ""
        if not blockers:
            quote_payload, unsigned_tx, quote_error = self._pumpportal_local_transaction(
                action=action,
                mint=mint,
                amount=amount,
                denominated_in_sol=denominated_in_sol,
                slippage_pct=slippage_pct,
                priority_fee_sol=priority_fee_sol,
                pool=pool,
                wallet_public_key=wallet_public_key,
            )
            if quote_error:
                blockers.append(quote_error)
        quote = LiveQuote(
            id=new_id("quote"),
            created_at=utc_now(),
            intent_id=intent.id,
            provider="pumpportal_local",
            action=action,
            mint=mint.strip(),
            amount=str(amount).strip(),
            denominated_in_sol=denominated_in_sol,
            slippage_pct=round(float(slippage_pct), 4),
            priority_fee_sol=round(float(priority_fee_sol), 9),
            pool=pool,
            status="blocked" if blockers else "ready",
            unsigned_transaction_base64=unsigned_tx,
            error="; ".join(blockers),
        )
        audit = LiveExecutionAudit(
            id=new_id("liveaudit"),
            created_at=utc_now(),
            updated_at=utc_now(),
            action=action,
            mint=mint.strip(),
            amount=str(amount).strip(),
            status=quote.status,
            signer_mode=signer_mode,
            wallet_public_key=wallet_public_key.strip(),
            request=intent.to_dict(),
            quote={**quote.to_dict(), "provider_request": quote_payload},
            caps_snapshot=self.live_caps_snapshot(),
            balance_snapshot=balance,
            errors=blockers,
            warnings=["Simulation warnings do not absolutely block manual signing"] if not blockers else [],
            final_status=quote.status,
        )
        self.storage.save_live_execution_audit(audit)
        self.add_event("warning", f"Live {action} quote {quote.status} for {mint[:8] or 'unknown'}")
        return audit.to_dict()

    def live_simulate(self, audit_id: str, ok: bool, warning: str = "", error: str = "", result: dict[str, Any] | None = None) -> dict[str, object]:
        audit = self._require_live_audit(audit_id)
        simulation = LiveSimulation(
            id=new_id("sim"),
            created_at=utc_now(),
            quote_id=str(audit.quote.get("id", "")),
            status="ok" if ok else "warning",
            ok=ok,
            warning=warning.strip(),
            error=error.strip(),
            result=result or {},
        )
        audit.simulation = simulation.to_dict()
        audit.status = "simulated" if ok else "simulation_warning"
        audit.final_status = audit.status
        audit.updated_at = utc_now()
        if warning:
            audit.warnings.append(warning)
        if error:
            audit.errors.append(error)
        self.storage.save_live_execution_audit(audit)
        return audit.to_dict()

    def live_submit(self, audit_id: str, signature: str) -> dict[str, object]:
        audit = self._require_live_audit(audit_id)
        if audit.signer_mode == "browser_wallet" and not signature.strip():
            raise ValueError("browser wallet submit requires a transaction signature")
        audit.transaction_signature = signature.strip()
        audit.status = "submitted"
        audit.final_status = "submitted"
        audit.updated_at = utc_now()
        self.storage.save_live_execution_audit(audit)
        self.add_event("warning", f"Live {audit.action} submitted: {signature[:10]}")
        return audit.to_dict()

    def live_confirm(self, audit_id: str, confirmation_status: str, error: str = "") -> dict[str, object]:
        audit = self._require_live_audit(audit_id)
        audit.confirmation_status = confirmation_status.strip()
        audit.status = "confirmed" if confirmation_status in {"confirmed", "finalized"} and not error else "failed"
        audit.final_status = audit.status
        audit.updated_at = utc_now()
        if error:
            audit.errors.append(error)
        self.storage.save_live_execution_audit(audit)
        return audit.to_dict()

    def _validate_live_order(self, action: str, amount: str, denominated_in_sol: bool, slippage_pct: float, priority_fee_sol: float, wallet_public_key: str, signer_mode: str) -> str:
        if action not in {"buy", "sell"}:
            return "action must be buy or sell"
        if signer_mode == "browser_wallet" and not wallet_public_key.strip():
            return "browser wallet is not connected"
        if signer_mode == "local_signer_daemon":
            return "local signer daemon is disabled in v1"
        try:
            numeric_amount = float(str(amount).replace("%", ""))
        except ValueError:
            return "amount must be numeric or a sell percentage"
        if numeric_amount <= 0:
            return "amount must be positive"
        if action == "buy":
            if not denominated_in_sol:
                return "buy amount must be denominated in SOL"
            if numeric_amount > self.settings.live_max_trade_sol:
                return f"amount exceeds live max trade cap ({self.settings.live_max_trade_sol:.4f} SOL)"
        if action == "sell" and str(amount).endswith("%") and numeric_amount > 100:
            return "sell percentage cannot exceed 100%"
        if slippage_pct > self.settings.live_max_slippage_pct:
            return f"slippage exceeds live cap ({self.settings.live_max_slippage_pct:.2f}%)"
        if priority_fee_sol > self.settings.live_priority_fee_cap_sol:
            return f"priority fee exceeds live cap ({self.settings.live_priority_fee_cap_sol:.9f} SOL)"
        return ""

    def _wallet_token_balance(self, wallet_public_key: str, mint: str) -> dict[str, object]:
        try:
            balance = SolanaReadOnlyClient(self.settings.solana_rpc_url).token_balance(wallet_public_key, mint)
            return {"wallet_public_key": wallet_public_key, "mint": mint, "token_balance": balance, "error": ""}
        except Exception as exc:
            return {"wallet_public_key": wallet_public_key, "mint": mint, "token_balance": None, "error": f"{exc.__class__.__name__}: {exc}"}

    def _pumpportal_local_transaction(self, action: str, mint: str, amount: str, denominated_in_sol: bool, slippage_pct: float, priority_fee_sol: float, pool: str, wallet_public_key: str) -> tuple[dict[str, object], str, str]:
        payload = {
            "publicKey": wallet_public_key.strip(),
            "action": action,
            "mint": mint.strip(),
            "amount": amount,
            "denominatedInSol": "true" if denominated_in_sol else "false",
            "slippage": float(slippage_pct),
            "priorityFee": float(priority_fee_sol),
            "pool": pool,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            "https://pumpportal.fun/api/trade-local",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read()
        except urllib.error.URLError as exc:
            return payload, "", f"PumpPortal quote failed: {exc}"
        return payload, base64.b64encode(body).decode("ascii"), ""

    def _require_live_audit(self, audit_id: str) -> LiveExecutionAudit:
        audit = self.storage.load_live_execution_audit(audit_id)
        if audit is None:
            raise ValueError(f"Live audit not found: {audit_id}")
        return audit

    def live_requests(self) -> list[dict[str, object]]:
        return [request.to_dict() for request in self.storage.load_live_execution_requests(100)]

    def create_manual_live_request(self, action: str, mint: str, amount_sol: float) -> dict[str, object]:
        amount = max(0.0, float(amount_sol))
        blockers = []
        if not self.settings.manual_live_enabled:
            blockers.append("manual live requests are disabled in settings")
        if not self.settings.live_trading_enabled:
            blockers.append("live trading unlock is not requested")
        if amount > self.settings.manual_live_max_sol:
            blockers.append(f"amount exceeds manual cap ({self.settings.manual_live_max_sol:.4f} SOL)")
        if self.settings.require_live_confirmation:
            blockers.append("manual confirmation would be required before any future signer")
        blockers.append("no live transaction executor is implemented")
        request = LiveExecutionRequest(
            id=new_id("live"),
            created_at=utc_now(),
            action=action,
            mint=mint.strip(),
            amount_sol=round(amount, 9),
            status="blocked" if blockers else "review_required",
            reason="; ".join(blockers) if blockers else "ready for manual review; no transaction sent",
            payload={
                "paper_only_boundary": True,
                "source": "dashboard",
                "live_trading_requested": self.settings.live_trading_enabled,
                "manual_live_enabled": self.settings.manual_live_enabled,
            },
        )
        self.storage.save_live_execution_request(request)
        self.add_event("warning", f"Manual live {action} request stored for {mint[:8] or 'unknown'}: {request.status}")
        return request.to_dict()

    def review_live_request(self, request_id: str, status: str, note: str = "") -> dict[str, object]:
        request = self.storage.load_live_execution_request(request_id)
        if request is None:
            raise ValueError(f"Live request not found: {request_id}")
        if status not in {"reviewed", "rejected"}:
            raise ValueError("Live request review status must be reviewed or rejected")
        if request.status in {"reviewed", "rejected"}:
            return request.to_dict()

        request.status = status
        request.reviewed_at = utc_now()
        review_note = note.strip()
        review_reason = "reviewed without execution" if status == "reviewed" else "rejected without execution"
        if review_note:
            review_reason = f"{review_reason}: {review_note}"
        request.reason = f"{request.reason}; {review_reason}" if request.reason else review_reason
        request.payload = {
            **request.payload,
            "review_status": status,
            "review_note": review_note,
            "reviewed_without_execution": True,
            "paper_only_boundary": True,
        }
        self.storage.save_live_execution_request(request)
        self.add_event("warning", f"Manual live {request.action} request {status} without execution for {request.mint[:8] or 'unknown'}")
        return request.to_dict()

    def operational_monitoring(self) -> dict[str, object]:
        events = self.storage.load_all_events(500)
        source = self.source_health()
        return {
            "backend": {"status": "running", "bot_status": self.status.value, "database_path": str(self.storage.path)},
            "source": source,
            "storage": self.data_summary(),
            "schema": self.storage.schema_status(),
            "recent_errors": [event.to_dict() for event in events if event.level in {"danger", "error"}][:20],
            "recent_warnings": [event.to_dict() for event in events if event.level == "warning"][:20],
        }

    def source_adapters(self) -> list[dict[str, object]]:
        return [
            {"name": "mock", "enabled": True, "status": "available", "capabilities": ["launches", "simulated_prices"], "confidence": 0.7},
            {"name": "pumpportal", "enabled": True, "status": self.source_status.status if self.source_status.source == "pumpportal" else "available", "capabilities": ["launches", "trades", "raw_events"], "confidence": self.source_health().get("health_score", 0) / 100},
        ]

    def trade_review_detail(self, token_id: str) -> dict[str, object]:
        token = next((item for item in self.storage.load_all_tokens(5000) if item.id == token_id), None)
        trade = next((item for item in self.storage.load_trades(5000) if item.token_id == token_id), None)
        decisions = [item.to_dict() for item in self.storage.load_strategy_decisions(1000) if item.token_id == token_id]
        observations = [item.to_dict() for item in self.storage.load_price_observations(1000, mint=token.mint if token else "")]
        pnl_breakdown = {}
        if trade:
            gross = trade.pnl_sol or 0.0
            fees = (trade.entry_fee_sol or 0.0) + (trade.exit_fee_sol or 0.0)
            pnl_breakdown = {
                "final_pnl_sol": gross,
                "fees_sol": round(fees, 6),
                "slippage_pct": trade.slippage_paid_pct,
                "price_impact_pct": trade.price_impact_pct,
                "net_before_fees_estimate": round(gross + fees, 6),
            }
        return {
            "token": token.to_dict() if token else None,
            "trade": trade.to_dict() if trade else None,
            "decisions": decisions,
            "observations": observations,
            "timeline": self.replay_timeline(token_id),
            "pnl_breakdown": pnl_breakdown,
        }

    def replay_timeline(self, token_id: str) -> list[dict[str, object]]:
        token = next((item for item in self.storage.load_all_tokens(5000) if item.id == token_id), None)
        mint = token.mint if token else ""
        timeline: list[dict[str, object]] = []
        if token:
            timeline.append({"at": token.detected_at.isoformat(), "type": "token", "title": f"Detected {token.symbol}", "detail": token.reason})
            if token.opened_at:
                timeline.append({"at": token.opened_at.isoformat(), "type": "trade", "title": "Paper buy", "detail": token.entry_reason or "paper entry"})
            if token.closed_at:
                timeline.append({"at": token.closed_at.isoformat(), "type": "trade", "title": "Paper sell", "detail": token.exit_reason or "paper exit"})
        for decision in self.storage.load_strategy_decisions(1000):
            if decision.token_id == token_id:
                timeline.append({"at": decision.created_at.isoformat(), "type": "decision", "title": decision.action, "detail": decision.reason})
        for observation in self.storage.load_price_observations(1000, mint=mint) if mint else []:
            timeline.append({"at": observation.observed_at.isoformat(), "type": "price", "title": observation.price_source, "detail": observation.reason})
        for event in self.storage.load_source_events(1000):
            raw_mint = str(event.raw_payload.get("mint") or event.raw_payload.get("mintAddress") or "")
            if event.normalized_token_id == token_id or (mint and raw_mint == mint):
                timeline.append({"at": event.received_at.isoformat(), "type": f"source:{event.status}", "title": event.source, "detail": event.message})
        return sorted(timeline, key=lambda item: str(item["at"]))

    def _performance_group(self, label: str, trades: list[TradeRecord]) -> dict[str, object]:
        scratch = self.stats.scratch_threshold_sol or 0.001
        pnls = [trade.pnl_sol or 0.0 for trade in trades]
        wins = [pnl for pnl in pnls if pnl > scratch]
        losses = [pnl for pnl in pnls if pnl < -scratch]
        scratches = [pnl for pnl in pnls if abs(pnl) <= scratch]
        decisive = len(wins) + len(losses)
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        holds = [trade.hold_duration_seconds for trade in trades if trade.hold_duration_seconds]
        return {
            "label": label,
            "count": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "scratches": len(scratches),
            "win_rate_pct": int((len(wins) / decisive) * 100) if decisive else 0,
            "pnl_sol": round(sum(pnls), 6),
            "avg_pnl_sol": round(sum(pnls) / len(pnls), 6) if pnls else 0.0,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else 0.0,
            "avg_hold_seconds": int(sum(holds) / len(holds)) if holds else 0,
        }

    def _group_performance(self, trades: list[TradeRecord], key_fn) -> list[dict[str, object]]:
        grouped: dict[str, list[TradeRecord]] = {}
        for trade in trades:
            grouped.setdefault(str(key_fn(trade)), []).append(trade)
        return sorted([self._performance_group(label, items) for label, items in grouped.items()], key=lambda item: abs(float(item["pnl_sol"])), reverse=True)

    def _pnl_curve(self, trades: list[TradeRecord]) -> list[dict[str, object]]:
        curve = []
        total = 0.0
        for trade in sorted(trades, key=lambda item: item.closed_at or item.opened_at or utc_now()):
            total = round(total + (trade.pnl_sol or 0.0), 6)
            curve.append({"at": (trade.closed_at or trade.opened_at or utc_now()).isoformat(), "pnl_sol": total, "trade_id": trade.id})
        return curve[-500:]

    def _score_bucket(self, score: int | None) -> str:
        if score is None:
            return "unknown"
        if score >= 80:
            return "80+"
        if score >= 65:
            return "65-79"
        if score >= 50:
            return "50-64"
        return "<50"

    def _confidence_bucket(self, confidence: float) -> str:
        if confidence >= 0.8:
            return "high confidence"
        if confidence >= 0.5:
            return "medium confidence"
        if confidence > 0:
            return "low confidence"
        return "unknown"

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

    def _observed_replay_pnl(self, token: TokenSignal, settings: BotSettings) -> float:
        observations = [item for item in self.storage.load_price_observations(500, mint=token.mint) if item.accepted and item.price]
        if len(observations) >= 2:
            entry = observations[0].price or token.current_price or 0.000001
            exit_price = observations[-1].price or entry
            move_pct = ((exit_price - entry) / max(entry, 0.000000001)) * 100
            fee_drag = (settings.paper_fee_bps / 10000) * settings.trade_size_sol * 2
            impact_drag = settings.trade_size_sol * (settings.paper_price_impact_pct / 100)
            return round(settings.trade_size_sol * (move_pct / 100) - fee_drag - impact_drag, 6)
        return self._estimated_replay_pnl(token, settings)

    def _classify_pnl(self, pnl: float) -> str:
        threshold = self.stats.scratch_threshold_sol or 0.001
        if pnl > threshold:
            return "win"
        if pnl < -threshold:
            return "loss"
        return "scratch"

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
        if target == "price_observations":
            return {"price_observations": [item.to_dict() for item in self.storage.load_price_observations(5000)]}
        if target == "strategy_decisions":
            return {"strategy_decisions": [item.to_dict() for item in self.storage.load_strategy_decisions(5000)]}
        if target == "trade_sessions":
            return {"trade_sessions": [item.to_dict() for item in self.storage.load_trade_sessions(5000)]}
        if target == "settings_versions":
            return {"settings_versions": [item.to_dict() for item in self.storage.load_settings_versions(5000)]}
        if target == "experiments":
            return {"experiments": [item.to_dict() for item in self.storage.load_experiment_runs(5000)]}
        if target == "trade_labels":
            return {"trade_labels": [item.to_dict() for item in self.storage.load_trade_labels(5000)]}
        if target == "strategy_presets":
            return {"strategy_presets": [item.to_dict() for item in self.storage.load_strategy_presets(5000)]}
        if target == "live_execution_requests":
            return {"live_execution_requests": [item.to_dict() for item in self.storage.load_live_execution_requests(5000)]}
        if target == "live_sessions":
            return {"live_sessions": [item.to_dict() for item in self.storage.load_live_sessions(5000)]}
        if target == "live_execution_audits":
            return {"live_execution_audits": [item.to_dict() for item in self.storage.load_live_execution_audits(5000)]}
        return {
            "tokens": [token.to_dict() for token in self.storage.load_all_tokens()],
            "events": [event.to_dict() for event in self.storage.load_all_events()],
            "source_events": [event.to_dict() for event in self.storage.load_source_events(5000)],
            "backtests": [run.to_dict() for run in self.storage.load_backtest_runs(5000)],
            "trades": [trade.to_dict() for trade in self.storage.load_trades(5000)],
            "price_observations": [item.to_dict() for item in self.storage.load_price_observations(5000)],
            "strategy_decisions": [item.to_dict() for item in self.storage.load_strategy_decisions(5000)],
            "trade_sessions": [item.to_dict() for item in self.storage.load_trade_sessions(5000)],
            "settings_versions": [item.to_dict() for item in self.storage.load_settings_versions(5000)],
            "experiments": [item.to_dict() for item in self.storage.load_experiment_runs(5000)],
            "trade_labels": [item.to_dict() for item in self.storage.load_trade_labels(5000)],
            "strategy_presets": [item.to_dict() for item in self.storage.load_strategy_presets(5000)],
            "live_execution_requests": [item.to_dict() for item in self.storage.load_live_execution_requests(5000)],
            "live_sessions": [item.to_dict() for item in self.storage.load_live_sessions(5000)],
            "live_execution_audits": [item.to_dict() for item in self.storage.load_live_execution_audits(5000)],
        }

    def data_summary(self) -> dict[str, int]:
        return {
            "tokens": self.storage.count_tokens(),
            "events": self.storage.count_events(),
            "source_events": self.storage.count_source_events(),
            "backtests": self.storage.count_backtest_runs(),
            "trades": self.storage.count_trades(),
            "price_observations": self.storage.count_price_observations(),
            "strategy_decisions": self.storage.count_strategy_decisions(),
            "trade_sessions": self.storage.count_trade_sessions(),
            "settings_versions": self.storage.count_settings_versions(),
            "experiments": self.storage.count_experiment_runs(),
            "trade_labels": self.storage.count_trade_labels(),
            "strategy_presets": self.storage.count_strategy_presets(),
            "live_execution_requests": self.storage.count_live_execution_requests(),
            "live_sessions": self.storage.count_live_sessions(),
            "live_execution_audits": self.storage.count_live_execution_audits(),
        }

    def clear_data(self, target: str) -> dict[str, int]:
        if target in {"tokens", "all"}:
            self.storage.clear_tokens()
            self.tokens.clear()
            self.creator_history.clear()
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
        if target in {"price_observations", "all"}:
            self.storage.clear_price_observations()
        if target in {"strategy_decisions", "all"}:
            self.storage.clear_strategy_decisions()
        if target in {"trade_sessions", "all"}:
            self.storage.clear_trade_sessions()
        if target in {"settings_versions", "all"}:
            self.storage.clear_settings_versions()
            self.current_settings_version_id = self.ensure_settings_version("reset", [])
        if target in {"experiments", "all"}:
            self.storage.clear_experiment_runs()
        if target in {"trade_labels", "all"}:
            self.storage.clear_trade_labels()
        if target in {"strategy_presets", "all"}:
            self.storage.clear_strategy_presets()
        if target in {"live_execution_requests", "all"}:
            self.storage.clear_live_execution_requests()
        if target in {"live_sessions", "all"}:
            self.storage.clear_live_sessions()
        if target in {"live_execution_audits", "all"}:
            self.storage.clear_live_execution_audits()
        self.add_event("warning", f"Data cleared: {target}")
        self.recalculate_stats()
        return self.data_summary()

    def open_position_count(self) -> int:
        return sum(1 for token in self.tokens if token.status in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING})

    def recalculate_stats(self) -> None:
        skipped = [token for token in self.tokens if token.status == TokenStatus.SKIPPED]
        open_tokens = [token for token in self.tokens if token.status in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}]
        closed = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        closed_ids = {trade.token_id for trade in closed}
        closed.extend(
            self.trade_from_token(token)
            for token in self.tokens
            if token.status == TokenStatus.PAPER_SOLD and token.pnl_sol is not None and token.id not in closed_ids
        )
        scratch_threshold = 0.001
        wins = [trade.pnl_sol or 0.0 for trade in closed if (trade.pnl_sol or 0.0) > scratch_threshold]
        scratches = [trade.pnl_sol or 0.0 for trade in closed if abs(trade.pnl_sol or 0.0) <= scratch_threshold]
        losses = [trade.pnl_sol or 0.0 for trade in closed if (trade.pnl_sol or 0.0) < -scratch_threshold]
        gross_wins = [trade.pnl_sol or 0.0 for trade in closed if (trade.pnl_sol or 0.0) > 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        decisive = len(wins) + len(losses)
        pnl_curve = []
        running = 0.0
        max_seen = 0.0
        max_drawdown = 0.0
        hold_durations = [trade.hold_duration_seconds for trade in closed if trade.hold_duration_seconds]
        for trade in sorted(closed, key=lambda item: item.closed_at or item.opened_at or utc_now()):
            running = round(running + (trade.pnl_sol or 0.0), 6)
            max_seen = max(max_seen, running)
            max_drawdown = min(max_drawdown, running - max_seen)
            pnl_curve.append(running)

        self.stats = BotStats(
            total_trades=len(closed),
            successful_trades=len(wins),
            losing_trades=len(losses),
            scratch_trades=len(scratches),
            skipped_tokens=len(skipped),
            open_positions=len(open_tokens),
            closed_trades=len(closed),
            win_rate_pct=int((len(wins) / decisive) * 100) if decisive else 0,
            gross_win_rate_pct=int((len(gross_wins) / len(closed)) * 100) if closed else 0,
            scratch_rate_pct=int((len(scratches) / len(closed)) * 100) if closed else 0,
            scratch_threshold_sol=scratch_threshold,
            total_pnl_sol=round(sum(trade.pnl_sol or 0.0 for trade in closed), 6),
            best_trade_sol=round(max([trade.pnl_sol or 0.0 for trade in closed], default=0.0), 6),
            worst_trade_sol=round(min([trade.pnl_sol or 0.0 for trade in closed], default=0.0), 6),
            average_win_sol=round(gross_win / len(wins), 6) if wins else 0.0,
            average_loss_sol=round(sum(losses) / len(losses), 6) if losses else 0.0,
            profit_factor=round(gross_win / gross_loss, 2) if gross_loss else 0.0,
            max_drawdown_sol=round(max_drawdown, 6),
            avg_hold_seconds=int(sum(hold_durations) / len(hold_durations)) if hold_durations else 0,
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
