from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import time
import uuid
import urllib.error
import urllib.request
from collections import Counter, deque
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

from app.core.models import (
    BacktestRun,
    BotSettings,
    BotSnapshot,
    BotStats,
    BotStatus,
    ExperimentRun,
    LiveExecutionAudit,
    LiveExecutionIntent,
    LiveFill,
    LiveLedgerPosition,
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
from app.core.alerts import AlertRouter
from app.core.paper_trader import PaperTrader
from app.core.price_pipeline import PricePipeline
from app.core.integrity import DataIntegrityAnalyzer
from app.core.hot_wallet import HotWalletVault
from app.core.pumpfun_intelligence import PumpFunIntelligence
from app.core.risk import RiskEngine
from app.core.scoring import ScoringEngine
from app.core.simulator import LaunchSimulator
from app.core.solana_readonly import SolanaReadOnlyClient
from app.core.storage import Storage
from app.core.sources import LaunchEvent, PUMPPORTAL_NON_LAUNCH_MINTS, normalize_pumpportal_new_token
from app.mobile.contracts import MobileScope

LAMPORTS_PER_SOL = 1_000_000_000
SOLANA_SIGNATURE_BASE_FEE_LAMPORTS = 5_000
LIVE_BUY_TOKEN_ACCOUNT_SETUP_RENT_SOL = 0.00391848
LIVE_BUY_PROGRAM_FEE_BUFFER_SOL = 0.00002
SPL_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
SPL_TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
from app.core.strategy import DecisionPipeline


LOGGER = logging.getLogger(__name__)


class BotState:
    MOBILE_MONITOR_SCOPE = MobileScope.MONITOR
    MOBILE_CONTROL_SCOPE = MobileScope.CONTROL
    MOBILE_DEFAULT_SCOPES = (MOBILE_MONITOR_SCOPE, MOBILE_CONTROL_SCOPE)
    MOBILE_ALLOWED_SCOPES = frozenset(
        {
            MobileScope.MONITOR,
            MobileScope.CONTROL,
            MobileScope.PORTFOLIO_READ,
            MobileScope.TRADE_REVIEW,
            MobileScope.TRADE_EXECUTE,
            MobileScope.WALLET_READ,
            MobileScope.TREASURY_REQUEST,
            MobileScope.ALERTS,
            MobileScope.DIAGNOSTICS,
        }
    )
    MOBILE_PAIRING_TTL_SECONDS = 300
    MOBILE_PAIRING_MAX_FAILED_ATTEMPTS = 5
    MOBILE_TOKEN_TTL_DAYS = 30
    READINESS_CACHE_TTL_SECONDS = 5.0
    live_recovery_max_attempts = 3
    PAPER_STRATEGY_FINGERPRINT_SCHEMA = "paper-strategy-v1"
    STRATEGY_PROMOTION_EVIDENCE_WINDOW_HOURS = 168
    LIVE_CAP_SETTING_KEYS = (
        "live_max_trade_sol",
        "live_daily_loss_cap_sol",
        "live_wallet_exposure_cap_sol",
        "live_max_open_positions",
        "live_max_slippage_pct",
        "live_priority_fee_cap_sol",
    )
    PAPER_STRATEGY_IGNORED_SETTING_KEYS = frozenset(
        {
            "mode",
            "require_live_confirmation",
            "detect_new_tokens",
            "auto_refresh",
            "backtest_replay_limit",
            "raw_replay_limit",
            "enable_trade_toasts",
            "compact_table_mode",
            "kill_switch_enabled",
            "solana_rpc_url",
            "watch_wallet_address",
            "manual_live_enabled",
            "manual_live_max_sol",
            "autonomous_live_enabled",
            "live_trading_enabled",
            "live_max_trade_sol",
            "live_daily_loss_cap_sol",
            "live_wallet_exposure_cap_sol",
            "live_max_open_positions",
            "live_max_slippage_pct",
            "live_priority_fee_cap_sol",
            "live_session_acknowledged",
            "live_signer_mode",
            "live_active_backend_armed",
            "live_active_wallet_public_key",
            "live_hot_wallet_enabled",
            "live_hot_wallet_public_key",
            "live_hot_wallet_label",
            "profit_sweep_enabled",
            "profit_sweep_mode",
            "profit_sweep_threshold_sol",
            "profit_sweep_amount_sol",
            "profit_sweep_percentage",
            "profit_sweep_min_profit_sol",
            "profit_sweep_destination_wallet",
            "profit_sweep_min_reserve_sol",
            "profit_sweep_cooldown_seconds",
            "profit_sweep_max_per_day",
        }
    )

    def __init__(
        self,
        database_path: str = "data/cryptoarc.db",
        default_source: str = "pumpportal",
        default_solana_rpc_url: str = "",
        default_solana_wss_endpoint: str = "",
        default_solana_logs_mentions_address: str = "",
        default_watch_wallet_address: str = "",
        signer_daemon_url: str = "http://127.0.0.1:8799",
        signer_daemon_auth_token: str = "",
        alert_router: AlertRouter | None = None,
    ) -> None:
        self.storage = Storage(database_path)
        database_file = self.storage.path
        self.hot_wallet = HotWalletVault(str(database_file.with_suffix(".hotwallet.json")))
        self.solana_wss_endpoint = default_solana_wss_endpoint.strip()
        self.solana_logs_mentions_address = default_solana_logs_mentions_address.strip()
        self.solana_logs_status = SourceStatus(source="solana_logs", status="offline", message="Solana logs verifier is idle")
        self.signer_daemon_url = signer_daemon_url.strip()
        self.signer_daemon_auth_token = signer_daemon_auth_token.strip()
        self.alerts = alert_router or AlertRouter()
        self.active_live_session_id = ""
        self._cached_signer_status: dict[str, object] | None = None
        self._cached_signer_status_at: datetime | None = None
        self._cached_readiness_status: dict[str, object] | None = None
        self._cached_readiness_status_at = 0.0
        self.status = BotStatus.STOPPED
        has_saved_settings = self.storage.has_settings()
        self.settings = self.storage.load_settings()
        if self.settings.max_position_ticks == 12:
            self.settings.max_position_ticks = 40
            self.storage.save_settings(self.settings)
        if self.settings.paper_fee_bps == 25.0:
            self.settings.paper_fee_bps = 50.0
            self.storage.save_settings(self.settings)
        if self.settings.live_signer_mode not in {"browser_wallet", "local_hot_wallet", "local_signer_daemon"}:
            self.settings.live_signer_mode = "browser_wallet"
        self._sync_hot_wallet_settings(self.hot_wallet.status())
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
        self.tokens: deque[TokenSignal] = deque(self._hydrate_active_tokens(), maxlen=80)
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
        self._recover_orphaned_open_tokens()
        self.last_bot_tick_at: datetime | None = None
        self.last_ingested_launch_at: datetime | None = None
        self.last_tick_error: str = ""
        self.last_tick_tokens_seen = 0
        self.last_tick_active_tokens = 0
        self.last_tick_closed = 0
        self.last_tick_completed_at: datetime | None = None
        self.bot_loop_iterations = 0
        self.live_last_poll_at: datetime | None = None
        self.live_last_poll_summary: dict[str, object] = {"checked": 0, "updated": 0, "skipped": True, "reason": "not run"}
        self.sol_usd_price = 0.0
        self.sol_usd_price_updated_at: datetime | None = None
        self.recalculate_stats()

    def start(self) -> BotSnapshot:
        self.status = BotStatus.RUNNING
        self.add_event("info", "Paper trading loop started", subsystem="paper")
        return self.snapshot()

    def stop(self) -> BotSnapshot:
        self.status = BotStatus.STOPPED
        self.add_event("warning", "Paper trading loop stopped", subsystem="paper")
        return self.snapshot()

    def create_mobile_pairing(
        self,
        api_base_url: str = "",
        scopes: list[str] | None = None,
        ttl_seconds: int = MOBILE_PAIRING_TTL_SECONDS,
    ) -> dict[str, object]:
        now = utc_now()
        expires_at = now + timedelta(seconds=max(60, min(1800, int(ttl_seconds or self.MOBILE_PAIRING_TTL_SECONDS))))
        code = str(secrets.randbelow(900000) + 100000)
        pairing_id = new_id("mpair")
        requested_scopes = self._normalize_mobile_scopes(scopes)
        payload: dict[str, object] = {
            "id": pairing_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "claimed_at": "",
            "claimed_device_id": "",
            "api_base_url": api_base_url.strip(),
            "scopes": requested_scopes,
            "code_hash": self._hash_mobile_secret(code),
            "failed_attempts": 0,
            "max_failed_attempts": self.MOBILE_PAIRING_MAX_FAILED_ATTEMPTS,
        }
        self.storage.save_mobile_pairing_request(payload)
        self.add_event(
            "info",
            "Mobile pairing code created",
            subsystem="security",
            operator_action="Pair only over the private tunnel and revoke unknown devices immediately.",
        )
        return {
            "id": pairing_id,
            "code": code,
            "manual_code": code,
            "api_base_url": payload["api_base_url"],
            "expires_at": payload["expires_at"],
            "scopes": requested_scopes,
            "qr_payload": {
                "artifact_type": "cryptoarc_mobile_pairing",
                "format_version": 1,
                "pairing_id": pairing_id,
                "code": code,
                "api_base_url": payload["api_base_url"],
                "expires_at": payload["expires_at"],
                "scopes": requested_scopes,
            },
        }

    def claim_mobile_pairing(self, pairing_id: str, code: str, device_name: str, platform: str = "android") -> dict[str, object]:
        pairing = self.storage.load_mobile_pairing_request(pairing_id.strip())
        now = utc_now()
        if not pairing:
            raise ValueError("Invalid or expired mobile pairing code")
        if str(pairing.get("claimed_at") or ""):
            raise ValueError("Mobile pairing code has already been claimed")
        if self._parse_mobile_time(pairing.get("expires_at")) <= now:
            raise ValueError("Mobile pairing code has expired")
        failed_attempts = int(pairing.get("failed_attempts") or 0)
        max_failed_attempts = int(pairing.get("max_failed_attempts") or self.MOBILE_PAIRING_MAX_FAILED_ATTEMPTS)
        if failed_attempts >= max_failed_attempts:
            raise ValueError("Mobile pairing code has too many failed attempts")
        if not secrets.compare_digest(self._hash_mobile_secret(code.strip()), str(pairing.get("code_hash") or "")):
            pairing["failed_attempts"] = failed_attempts + 1
            self.storage.save_mobile_pairing_request(pairing)
            raise ValueError("Invalid or expired mobile pairing code")

        token = secrets.token_urlsafe(32)
        device_id = new_id("mdev")
        token_expires_at = now + timedelta(days=self.MOBILE_TOKEN_TTL_DAYS)
        scopes = self._normalize_mobile_scopes(list(pairing.get("scopes") or []))
        device: dict[str, object] = {
            "id": device_id,
            "name": self._clean_mobile_label(device_name, "Mobile device", 80),
            "platform": self._clean_mobile_label(platform, "unknown", 40).lower(),
            "scopes": scopes,
            "created_at": now.isoformat(),
            "last_seen_at": now.isoformat(),
            "expires_at": token_expires_at.isoformat(),
            "revoked_at": "",
            "token_hash": self._hash_mobile_secret(token),
            "paired_from_pairing_id": pairing["id"],
        }
        pairing["claimed_at"] = now.isoformat()
        pairing["claimed_device_id"] = device_id
        self.storage.save_mobile_device(device)
        self.storage.save_mobile_pairing_request(pairing)
        self.add_event(
            "warning",
            f"Mobile device paired: {device['name']}",
            subsystem="security",
            operator_action="Confirm the device is expected and revoke it from Settings if not.",
        )
        return {"token": token, "device": self._public_mobile_device(device), "scopes": scopes, "expires_at": device["expires_at"]}

    def validate_mobile_token(self, token: str, required_scope: str = MOBILE_MONITOR_SCOPE) -> dict[str, object] | None:
        if not token.strip():
            return None
        now = utc_now()
        token_hash = self._hash_mobile_secret(token.strip())
        device = self.storage.load_mobile_device_by_token_hash(token_hash)
        if not device:
            return None
        if str(device.get("revoked_at") or ""):
            return None
        if self._parse_mobile_time(device.get("expires_at")) <= now:
            return None
        scopes = [str(scope) for scope in device.get("scopes") or []]
        if required_scope and required_scope not in scopes:
            return None
        device = self.storage.touch_active_mobile_device_by_token_hash(token_hash, now.isoformat())
        if not device:
            return None
        if str(device.get("revoked_at") or ""):
            return None
        if self._parse_mobile_time(device.get("expires_at")) <= now:
            return None
        scopes = [str(scope) for scope in device.get("scopes") or []]
        if required_scope and required_scope not in scopes:
            return None
        return self._public_mobile_device(device)

    def revoke_mobile_device(self, device_id: str) -> dict[str, object]:
        result = self.storage.revoke_mobile_device_and_push_registrations(
            device_id.strip(),
            utc_now().isoformat(),
        )
        if not result:
            raise ValueError("Mobile device was not found")
        device, newly_revoked = result
        if newly_revoked:
            self.add_event(
                "warning",
                f"Mobile device revoked: {device.get('name') or device_id}",
                subsystem="security",
                operator_action="Reconnect trusted devices with a fresh private-tunnel pairing code.",
            )
        return self._public_mobile_device(device)

    def mobile_devices(self, include_revoked: bool = False) -> list[dict[str, object]]:
        return [self._public_mobile_device(device) for device in self.storage.load_mobile_devices(include_revoked=include_revoked, limit=200)]

    def mobile_feed(self, level: str = "", subsystem: str = "", limit: int = 100) -> dict[str, object]:
        report = self.operator_logs_report(timeframe="7d", level=level, subsystem=subsystem, limit=limit)
        return {
            "artifact_type": "cryptoarc_mobile_feed",
            "format_version": 1,
            "generated_at": report.get("generated_at"),
            "filters": report.get("filters", {}),
            "summary": report.get("summary", {}),
            "events": report.get("events", []),
            "action_items": report.get("action_items", []),
        }

    def mobile_cockpit(
        self,
        live_trading_enabled: bool = False,
        local_auth_enabled: bool = False,
        device: dict[str, object] | None = None,
    ) -> dict[str, object]:
        snapshot = self.snapshot()
        source = self.source_health()
        readiness = self._recent_readiness_status()
        live = self.live_status(live_trading_enabled, local_auth_enabled=local_auth_enabled)
        events = self.storage.load_all_events(80)
        latest_alerts = [
            event.to_dict()
            for event in events
            if event.level in {"warning", "danger", "error"} or event.operator_action
        ][:12]
        live_pnl = live.get("live_pnl") if isinstance(live.get("live_pnl"), dict) else {}
        readiness_actions = readiness.get("recommended_actions", []) if isinstance(readiness.get("recommended_actions"), list) else []
        live_blockers = live.get("blockers", []) if isinstance(live.get("blockers"), list) else []
        source_action = str(source.get("operator_action") or "")
        next_operator_action = (
            str(readiness_actions[0])
            if readiness_actions
            else source_action
            if source_action
            else f"Resolve live blocker: {live_blockers[0]}"
            if live_blockers
            else "Monitor the paper run and keep the private tunnel connected."
        )
        mode = self.settings.mode.value if hasattr(self.settings.mode, "value") else str(self.settings.mode)
        start_allowed = snapshot.status == BotStatus.STOPPED and mode != "live_locked" and not self.settings.live_trading_enabled
        stop_allowed = snapshot.status == BotStatus.RUNNING
        return {
            "artifact_type": "cryptoarc_mobile_cockpit",
            "format_version": 1,
            "server_time": utc_now().isoformat(),
            "device": device or {},
            "connection": {
                "state": "connected",
                "api": "ok",
                "websocket": "available",
                "private_tunnel_required": True,
            },
            "bot": {
                "status": snapshot.status.value,
                "mode": mode,
                "launch_source": self.settings.launch_source,
                "detected_tokens": len(snapshot.tokens),
                "auto_refresh": self.settings.auto_refresh,
            },
            "source": {
                "status": source.get("status"),
                "status_message": source.get("status_message"),
                "health_score": source.get("health_score"),
                "trust_state": source.get("trust_state"),
                "events_per_minute": source.get("events_per_minute"),
                "last_event_age_seconds": source.get("last_event_age_seconds"),
                "live_entry_blocked": source.get("live_entry_blocked"),
                "operator_action": source_action,
            },
            "readiness": {
                "status": readiness.get("status"),
                "score": readiness.get("score"),
                "entries_allowed": readiness.get("entries_allowed"),
                "blockers": [
                    gate
                    for gate in readiness.get("gates", [])
                    if isinstance(gate, dict) and gate.get("status") == "fail"
                ],
                "warnings": readiness_actions,
                "sample_size": readiness.get("sample_size", {}),
                "paper_only": readiness.get("paper_only", True),
            },
            "live": {
                "kill_switch_enabled": self.settings.kill_switch_enabled,
                "blockers": live_blockers,
                "autonomy_blockers": live.get("autonomy_blockers", []),
                "mode_visibility": live.get("mode_visibility", {}),
                "full_sniper_gate": live.get("full_sniper_gate", {}),
                "active_intent_count": live.get("active_intent_count", 0),
                "unresolved_audit_count": live.get("unresolved_audit_count", 0),
                "recoverable_audit_count": live.get("recoverable_audit_count", 0),
                "paper_default": live.get("paper_default", True),
            },
            "open_risk": {
                "paper_open_positions": self.stats.open_positions,
                "live_open_positions": int(live_pnl.get("open_positions", 0) or 0),
                "active_live_intents": live.get("active_intent_count", 0),
                "unresolved_live_audits": live.get("unresolved_audit_count", 0),
                "risk_blockers": live_blockers[:8],
            },
            "pnl": {
                "paper": {
                    "total_pnl_sol": self.stats.total_pnl_sol,
                    "win_rate_pct": self.stats.win_rate_pct,
                    "closed_trades": self.stats.closed_trades,
                    "open_positions": self.stats.open_positions,
                    "max_drawdown_sol": self.stats.max_drawdown_sol,
                },
                "live": {
                    "realized_pnl_sol": float(live_pnl.get("realized_pnl_sol", 0.0) or 0.0),
                    "unrealized_pnl_sol": float(live_pnl.get("unrealized_pnl_sol", 0.0) or 0.0),
                    "cost_basis_sol": float(live_pnl.get("cost_basis_sol", 0.0) or 0.0),
                    "open_positions": int(live_pnl.get("open_positions", 0) or 0),
                    "approximate": bool(live_pnl.get("approximate", True)),
                },
            },
            "alerts": {
                "telegram": self.alerts.status(),
                "latest": latest_alerts,
            },
            "allowed_actions": {
                "start": start_allowed,
                "stop": stop_allowed,
                "kill_switch": True,
                "clear_kill_switch": True,
                "live_backend_arm": False,
                "live_submit": False,
                "hot_wallet_import": False,
            },
            "next_operator_action": next_operator_action,
        }

    def mobile_portfolio(self, timeframe: str) -> dict[str, object]:
        timeframe_windows = {
            "1d": timedelta(days=1),
            "1w": timedelta(weeks=1),
            "1m": timedelta(days=30),
            "all": None,
        }
        if timeframe not in timeframe_windows:
            raise ValueError("Unsupported portfolio timeframe")
        now = utc_now()
        cutoff = now - timeframe_windows[timeframe] if timeframe_windows[timeframe] else None
        closed = [
            trade
            for trade in self.storage.load_trades(5000)
            if trade.closed_at
            and trade.pnl_sol is not None
            and (cutoff is None or trade.closed_at >= cutoff)
        ]
        paper_performance = self._performance_group(timeframe, closed)
        paper_curve = self._pnl_curve(closed)
        live_positions = self._live_ledger_positions("")
        positions = self._mobile_position_summaries(now, live_positions=live_positions)
        open_live_positions = [
            position for position in live_positions if position.status == "open"
        ]
        live_realized = round(
            sum(position.realized_pnl_sol for position in open_live_positions),
            9,
        )
        live_unrealized = round(
            sum(position.unrealized_pnl_sol for position in open_live_positions),
            9,
        )
        paper_positions = [position for position in positions if position["mode"] == "paper"]
        selected_period_realized = round(
            float(paper_performance["pnl_sol"]),
            9,
        )
        current_paper_realized = round(
            sum(float(position["realized_pnl_sol"]) for position in paper_positions),
            9,
        )
        paper_unrealized = round(
            sum(float(position["unrealized_pnl_sol"]) for position in paper_positions),
            9,
        )
        open_positions = [position for position in positions if position["status"] == "open"]
        cost_basis = round(sum(float(position["cost_basis_sol"]) for position in open_positions), 9)
        allocation = self._mobile_allocation(open_positions)
        tracked_value = round(
            sum(float(item["value_sol"]) for item in allocation),
            9,
        )
        live_net = round(live_realized + live_unrealized, 9)
        paper_net = round(current_paper_realized + paper_unrealized, 9)
        current_net = round(paper_net + live_net, 9)
        series = [
            {
                "at": point["at"],
                "paper_pnl_sol": float(point["pnl_sol"]),
                "live_pnl_sol": 0.0,
                "net_pnl_sol": float(point["pnl_sol"]),
                "current_snapshot": False,
                "approximate": False,
            }
            for point in paper_curve
        ]
        freshness = self._mobile_positions_freshness(positions, now)
        source = self.source_health()
        return {
            "artifact_type": "cryptoarc_mobile_portfolio",
            "format_version": 1,
            "generated_at": now.isoformat(),
            "timeframe": timeframe,
            "freshness": freshness,
            "summary": {
                "equity_sol": None,
                "tracked_value_sol": tracked_value,
                "cost_basis_sol": cost_basis,
                "net_pnl_sol": selected_period_realized,
                "realized_pnl_sol": selected_period_realized,
                "unrealized_pnl_sol": 0.0,
                "selected_period_realized_pnl_sol": selected_period_realized,
                "win_rate_pct": int(paper_performance["win_rate_pct"]),
                "health_score": int(source.get("health_score", 0) or 0),
                "open_positions": len(open_positions),
                "closed_trades": len(closed),
            },
            "current_snapshot": {
                "generated_at": now.isoformat(),
                "tracked_value_sol": tracked_value,
                "cost_basis_sol": cost_basis,
                "realized_pnl_sol": round(current_paper_realized + live_realized, 9),
                "unrealized_pnl_sol": round(paper_unrealized + live_unrealized, 9),
                "net_pnl_sol": current_net,
                "paper_pnl_sol": paper_net,
                "live_pnl_sol": live_net,
                "open_positions": len(open_positions),
                "approximate": any(
                    bool(position["pnl_approximate"]) for position in open_positions
                ),
            },
            "series": series,
            "allocation": allocation,
            "positions": positions,
        }

    def mobile_positions(self) -> dict[str, object]:
        now = utc_now()
        positions = self._mobile_position_summaries(now)
        return {
            "artifact_type": "cryptoarc_mobile_positions",
            "format_version": 1,
            "generated_at": now.isoformat(),
            "freshness": self._mobile_positions_freshness(positions, now),
            "positions": positions,
        }

    def _pending_mobile_treasury_reservation(
        self,
        wallet_public_key: str,
        asset: str,
        *,
        exclude_action_id: str = "",
    ) -> Decimal:
        reserved = Decimal("0")
        for receipt in self.storage.load_pending_mobile_treasury_receipts(
            wallet_public_key=wallet_public_key,
            asset=asset,
            exclude_action_id=exclude_action_id,
        ):
            try:
                if receipt.action_type != "rent_recovery":
                    reserved += Decimal(
                        str(receipt.payload.get("amount") or "0")
                    )
                reserved += Decimal(
                    str(receipt.payload.get("expected_fee_sol") or "0")
                )
            except (ArithmeticError, ValueError):
                return Decimal("Infinity")
        return reserved

    def mobile_wallet(self) -> dict[str, object]:
        now = utc_now()
        wallet = (
            self.settings.live_active_wallet_public_key.strip()
            or self.settings.live_hot_wallet_public_key.strip()
        )
        balance = (
            self.live_wallet_balance(wallet)
            if wallet
            else {
                "wallet_public_key": "",
                "balance_sol": 0.0,
                "error": "armed wallet public key is required",
            }
        )
        balance_sol = float(balance.get("balance_sol") or 0.0)
        balance_error = str(balance.get("error") or "")
        positions = [
            position
            for position in self.storage.load_live_ledger_positions(500)
            if position.wallet_public_key == wallet and position.status == "open"
        ]
        pending_reserved = self._pending_mobile_treasury_reservation(
            wallet,
            "SOL",
        )
        configured_reserve = Decimal(
            str(self.settings.profit_sweep_min_reserve_sol or "0")
        )
        total_reserved = pending_reserved + configured_reserve
        reserved_sol = min(
            Decimal(str(max(0.0, balance_sol))),
            max(Decimal("0"), total_reserved),
        )
        available_sol = max(
            Decimal("0"),
            Decimal(str(balance_sol)) - reserved_sol,
        )
        committed_rows = []
        for position in positions:
            value_sol = max(
                0.0,
                float(position.cost_basis_sol or 0.0)
                + float(position.unrealized_pnl_sol or 0.0),
            )
            committed_rows.append(
                {
                    "asset": position.symbol or position.mint[:8] or "TOKEN",
                    "total": round(value_sol, 9),
                    "committed": round(value_sol, 9),
                    "available": 0.0,
                    "reserved": 0.0,
                    "approximate": True,
                }
            )
        balances = [
            {
                "asset": "SOL",
                "total": round(balance_sol, 9),
                "committed": 0.0,
                "available": round(float(available_sol), 9),
                "reserved": round(float(reserved_sol), 9),
                "approximate": bool(balance_error),
            },
            *committed_rows,
        ]
        total_value_sol = sum(float(row["total"]) for row in balances)
        allocation = [
            {
                "asset": str(row["asset"]),
                "value_sol": float(row["total"]),
                "percentage": round(
                    (float(row["total"]) / total_value_sol) * 100, 1
                )
                if total_value_sol > 0
                else 0.0,
            }
            for row in balances
            if float(row["total"]) > 0
        ]
        fees = sum(float(position.total_fees_sol or 0.0) for position in positions)
        priority_fees = sum(
            float(position.total_priority_fees_sol or 0.0)
            for position in positions
        )
        realized = sum(
            float(position.realized_pnl_sol or 0.0) for position in positions
        )
        unrealized = sum(
            float(position.unrealized_pnl_sol or 0.0) for position in positions
        )
        reconciliation_statuses = [
            str(position.reconciliation_status or "pending")
            for position in positions
        ]
        reconciliation_status = (
            "matched"
            if reconciliation_statuses
            and all(status == "matched" for status in reconciliation_statuses)
            else "pending"
            if not reconciliation_statuses
            else "needs_review"
        )
        reconciled_at = max(
            (
                position.balance_verified_at or position.updated_at
                for position in positions
            ),
            default=None,
        )
        try:
            rent = self.live_rent_recovery_scan(wallet) if wallet else {}
            rent_status = "ready" if rent.get("eligible_count") else "clear"
            rent_error = ""
        except Exception as exc:
            rent = {}
            rent_status = "unavailable"
            rent_error = f"{exc.__class__.__name__}: {exc}"
        signer = self.signer_status(
            self.settings.live_signer_mode,
            wallet,
        )
        readiness = self._recent_readiness_status()
        approximate = bool(
            balance_error
            or reconciliation_status != "matched"
            or committed_rows
        )
        return {
            "artifact_type": "cryptoarc_mobile_wallet",
            "format_version": 1,
            "generated_at": now.isoformat(),
            "wallet_public_key": wallet,
            "total_value_sol": round(total_value_sol, 9),
            "freshness": {
                "status": "unavailable" if balance_error else "fresh",
                "generated_at": now.isoformat(),
                "age_seconds": 0,
                "stale_after_seconds": 30,
                "approximate": approximate,
            },
            "balances": balances,
            "allocation": allocation,
            "pnl": {
                "realized_sol": round(realized, 9),
                "unrealized_sol": round(unrealized, 9),
                "approximate": True,
            },
            "fees": {
                "network_sol": round(max(0.0, fees - priority_fees), 9),
                "priority_sol": round(priority_fees, 9),
                "total_sol": round(fees, 9),
                "approximate": reconciliation_status != "matched",
            },
            "rent": {
                "recoverable_sol": round(
                    float(rent.get("recoverable_rent_sol") or 0.0), 9
                ),
                "eligible_accounts": int(rent.get("eligible_count") or 0),
                "eligible_token_accounts": [
                    str(row.get("token_account") or "")
                    for row in rent.get("eligible_accounts", [])
                    if isinstance(row, dict)
                    and str(row.get("token_account") or "")
                ],
                "status": rent_status,
                "approximate": bool(rent_error),
            },
            "reconciliation": {
                "status": reconciliation_status,
                "last_reconciled_at": (
                    reconciled_at.isoformat() if reconciled_at else None
                ),
                "approximate": reconciliation_status != "matched",
            },
            "health": {
                "rpc": "unavailable" if balance_error else "healthy",
                "signer": (
                    "healthy"
                    if signer.get("connected")
                    and signer.get("healthy")
                    and signer.get("can_sign")
                    else "unavailable"
                ),
                "backend": (
                    "armed"
                    if self.settings.live_active_backend_armed
                    else "disarmed"
                ),
                "readiness": str(readiness.get("status") or "unknown"),
                "kill_switch": (
                    "enabled"
                    if self.settings.kill_switch_enabled
                    else "clear"
                ),
            },
        }

    def mobile_wallet_transactions(self) -> dict[str, object]:
        receipts = [
            receipt
            for receipt in self.storage.load_mobile_action_receipts(limit=500)
            if receipt.action_type
            in {"withdrawal", "profit_sweep", "rent_recovery"}
        ]
        return {
            "artifact_type": "cryptoarc_mobile_wallet_transactions",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "transactions": [
                {
                    "id": receipt.id,
                    "action": receipt.action_type,
                    "asset": str(receipt.payload.get("asset") or ""),
                    "amount": str(receipt.payload.get("amount") or ""),
                    "destination": str(
                        receipt.payload.get("address") or ""
                    ),
                    "status": receipt.status,
                    "created_at": receipt.created_at.isoformat(),
                    "transaction_signature": str(
                        receipt.payload.get("transaction_signature") or ""
                    ),
                }
                for receipt in receipts
            ],
        }

    def _mobile_treasury_signer_blockers(
        self,
        wallet_public_key: str,
    ) -> list[str]:
        blockers: list[str] = []
        signer = self.signer_status("local_hot_wallet", wallet_public_key)
        hot_wallet = self.hot_wallet.status()
        signer_wallet = str(signer.get("wallet_public_key") or "")
        unlocked_wallet = str(hot_wallet.get("wallet_public_key") or "")
        if not hot_wallet.get("imported"):
            blockers.append("no local hot wallet is imported")
        if not hot_wallet.get("unlocked"):
            blockers.append("local hot wallet is locked")
        if not (
            signer.get("connected")
            and signer.get("healthy")
            and signer.get("can_sign")
        ):
            blockers.append(
                str(signer.get("disabled_reason") or "signer is unhealthy")
            )
        if (
            not wallet_public_key
            or signer_wallet != wallet_public_key
            or unlocked_wallet != wallet_public_key
        ):
            blockers.append(
                "armed wallet does not match unlocked local hot wallet"
            )
        return list(dict.fromkeys(blockers))

    def _require_mobile_treasury_signer(
        self,
        wallet_public_key: str,
    ) -> None:
        blockers = self._mobile_treasury_signer_blockers(
            wallet_public_key
        )
        if blockers:
            raise ValueError("; ".join(blockers))

    def _mobile_treasury_readiness(
        self,
        wallet_public_key: str,
    ) -> dict[str, object]:
        readiness = self._recent_readiness_status()
        strategy = (
            readiness.get("strategy_promotion")
            if isinstance(readiness.get("strategy_promotion"), dict)
            else {}
        )
        execution = self._execution_readiness_status(
            source=self.source_health(),
            strategy_promotion=strategy,
            env_live_enabled=True,
            wallet_public_key=wallet_public_key,
            signer_mode="local_hot_wallet",
        )
        all_audits = self._normalize_live_audits(
            self.storage.load_live_execution_audits(None)
        )
        unresolved = [
            audit for audit in all_audits if self._is_unresolved_live_audit(audit)
        ]
        backup = self._pre_run_backup_status()
        manual = self._manual_live_verification_status(
            wallet_public_key,
            "local_hot_wallet",
        )
        blockers: list[str] = []
        if not execution.get("can_live_submit"):
            detail = "; ".join(
                str(value)
                for value in execution.get("blockers", [])
                if value
            )
            blockers.append(
                "live execution readiness is blocked"
                + (f": {detail}" if detail else "")
            )
        if unresolved:
            blockers.append(
                f"unresolved live audit recovery debt: {len(unresolved)}"
            )
        if not backup.get("fresh"):
            blockers.append(
                str(
                    backup.get("blocker")
                    or "fresh pre-run backup is required"
                )
            )
        if not manual.get("verified"):
            blockers.append(
                str(
                    manual.get("blocker")
                    or "recent manual live proof is required"
                )
            )
        return {
            "blockers": list(dict.fromkeys(blockers)),
            "execution_readiness": execution,
            "unresolved_audits": len(unresolved),
            "pre_run_backup": backup,
            "manual_live_verification": manual,
        }

    def _profit_sweep_policy_evaluation(
        self,
        *,
        wallet_public_key: str,
        destination: str,
        balance_sol: Decimal,
        pending_reserved_sol: Decimal = Decimal("0"),
        expected_fee_sol: Decimal = Decimal("0"),
    ) -> dict[str, object]:
        blockers: list[str] = []
        if not self.settings.profit_sweep_enabled:
            blockers.append("profit sweep is disabled")
        configured_destination = (
            self.settings.profit_sweep_destination_wallet.strip()
        )
        if destination != configured_destination:
            blockers.append(
                "profit sweep destination does not match desktop settings"
            )
        mode = (
            self.settings.profit_sweep_mode
            if self.settings.profit_sweep_mode
            in {"fixed_sol", "percentage"}
            else "fixed_sol"
        )
        minimum_profit = Decimal(
            str(self.settings.profit_sweep_min_profit_sol or "0")
        )
        legacy_threshold = Decimal(
            str(self.settings.profit_sweep_threshold_sol or "0")
        )
        threshold = (
            minimum_profit if minimum_profit > 0 else legacy_threshold
        )
        fixed_amount = Decimal(
            str(self.settings.profit_sweep_amount_sol or "0")
        )
        percentage = Decimal(
            str(self.settings.profit_sweep_percentage or "0")
        )
        if threshold <= 0:
            blockers.append(
                "minimum profit to sweep must be greater than zero"
            )
        if mode == "fixed_sol" and fixed_amount <= 0:
            blockers.append("profit sweep amount must be greater than zero")
        if mode == "percentage" and not (
            Decimal("0") < percentage <= Decimal("100")
        ):
            blockers.append(
                "profit sweep percentage must be greater than zero and no more than 100"
            )
        ledger = self.live_ledger(wallet_public_key)
        summary = ledger.get("summary", {}) if isinstance(ledger, dict) else {}
        realized = Decimal(
            str(
                summary.get("realized_pnl_sol", "0")
                if isinstance(summary, dict)
                else "0"
            )
        )
        if realized < threshold:
            blockers.append(
                "realized live profit is below minimum profit to sweep"
            )
        expected_amount = fixed_amount
        if mode == "percentage":
            expected_amount = (
                realized * percentage / Decimal("100")
            ).quantize(Decimal("0.000000001"))
            if expected_amount <= 0:
                blockers.append("percentage sweep amount resolved to zero")
        now = utc_now()
        sweeps = [
            audit
            for audit in self.storage.load_live_execution_audits(None)
            if audit.action == "profit_sweep"
            and audit.wallet_public_key == wallet_public_key
            and audit.final_status
            in {"submitted", "confirmed", "reconciled"}
        ]
        recent_sweeps = [
            audit
            for audit in sweeps
            if (now - audit.created_at).total_seconds() < 86400
        ]
        max_per_day = int(self.settings.profit_sweep_max_per_day or 0)
        if max_per_day > 0 and len(recent_sweeps) >= max_per_day:
            blockers.append("daily sweep cap reached")
        cooldown_seconds = int(
            self.settings.profit_sweep_cooldown_seconds or 0
        )
        last_sweep = max(
            sweeps,
            key=lambda audit: audit.created_at,
            default=None,
        )
        cooldown_age_seconds: int | None = None
        if last_sweep and cooldown_seconds > 0:
            cooldown_age_seconds = int(
                (now - last_sweep.created_at).total_seconds()
            )
            if cooldown_age_seconds < cooldown_seconds:
                blockers.append("profit sweep cooldown active")
        reserve = Decimal(
            str(self.settings.profit_sweep_min_reserve_sol or "0")
        )
        remaining = (
            balance_sol
            - pending_reserved_sol
            - expected_amount
            - expected_fee_sol
        )
        if remaining < reserve:
            blockers.append("profit sweep would breach minimum reserve")
        return {
            "blockers": list(dict.fromkeys(blockers)),
            "expected_amount_sol": expected_amount,
            "realized_pnl_sol": realized,
            "minimum_profit_sol": threshold,
            "sweep_mode": mode,
            "sweep_percentage": percentage,
            "minimum_reserve_sol": reserve,
            "remaining_balance_sol": remaining,
            "sweeps_today": len(recent_sweeps),
            "max_per_day": max_per_day,
            "cooldown_seconds": cooldown_seconds,
            "cooldown_age_seconds": cooldown_age_seconds,
        }

    def mobile_treasury_preflight(
        self,
        *,
        action: str,
        address: str,
        asset: str,
        amount: Decimal,
        token_accounts: list[str],
        exclude_action_id: str = "",
    ) -> dict[str, object]:
        blockers: list[str] = []
        wallet = self.settings.live_active_wallet_public_key.strip()
        if action not in {"withdrawal", "profit_sweep", "rent_recovery"}:
            blockers.append("treasury action is not supported")
        if self.settings.kill_switch_enabled:
            blockers.append("kill switch is enabled")
        if not self.settings.live_active_backend_armed:
            blockers.append("treasury backend is not armed")
        if self.settings.live_signer_mode != "local_hot_wallet":
            blockers.append("treasury requires the local hot wallet signer")
        if not wallet:
            blockers.append("armed wallet public key is required")
        if asset != "SOL":
            blockers.append("treasury executor currently supports SOL only")
        blockers.extend(self._mobile_treasury_signer_blockers(wallet))
        readiness = self._mobile_treasury_readiness(wallet)
        blockers.extend(
            str(value) for value in readiness.get("blockers", [])
        )
        balance = self.live_wallet_balance(wallet)
        balance_error = str(balance.get("error") or "")
        if balance_error:
            blockers.append(
                f"RPC wallet health is unavailable: {balance_error}"
            )
        balance_sol = Decimal(str(balance.get("balance_sol") or "0"))
        expected_fee = Decimal(SOLANA_SIGNATURE_BASE_FEE_LAMPORTS) / Decimal(
            LAMPORTS_PER_SOL
        )
        pending_reserved = self._pending_mobile_treasury_reservation(
            wallet,
            asset,
            exclude_action_id=exclude_action_id,
        )
        if not pending_reserved.is_finite():
            blockers.append("pending treasury reservation is invalid")
            pending_reserved = balance_sol
        configured_reserve = Decimal(
            str(self.settings.profit_sweep_min_reserve_sol or "0")
        )
        available = balance_sol - pending_reserved
        warnings = [
            "Treasury movement requires fresh biometric authentication and a deliberate hold."
        ]
        profit_sweep_policy: dict[str, object] = {}
        if action == "rent_recovery":
            if address != wallet:
                blockers.append(
                    "rent recovery destination must be the armed wallet"
                )
            try:
                scan = self.live_rent_recovery_scan(wallet) if wallet else {}
            except Exception as exc:
                scan = {}
                blockers.append(
                    f"rent recovery RPC scan failed: {exc.__class__.__name__}: {exc}"
                )
            eligible = {
                str(row.get("token_account") or ""): row
                for row in scan.get("eligible_accounts", [])
                if isinstance(row, dict)
            }
            if not token_accounts:
                blockers.append("rent recovery requires eligible token accounts")
            if any(account not in eligible for account in token_accounts):
                blockers.append(
                    "rent recovery contains an ineligible token account"
                )
            recoverable = sum(
                Decimal(str(eligible[account].get("rent_sol") or "0"))
                for account in token_accounts
                if account in eligible
            )
            if recoverable != amount:
                blockers.append(
                    "rent recovery amount does not match eligible rent"
                )
            if available < expected_fee:
                blockers.append(
                    "insufficient available balance for rent recovery fees"
                )
            remaining = balance_sol + recoverable - expected_fee
        elif action == "profit_sweep":
            if address == wallet:
                blockers.append(
                    "treasury destination must differ from the armed wallet"
                )
            profit_sweep_policy = self._profit_sweep_policy_evaluation(
                wallet_public_key=wallet,
                destination=address,
                balance_sol=balance_sol,
                pending_reserved_sol=pending_reserved,
                expected_fee_sol=expected_fee,
            )
            blockers.extend(
                str(value)
                for value in profit_sweep_policy.get("blockers", [])
            )
            expected_amount = Decimal(
                str(profit_sweep_policy.get("expected_amount_sol") or "0")
            )
            if amount != expected_amount:
                blockers.append(
                    "profit sweep amount does not match configured policy"
                )
            remaining = available - amount - expected_fee
        else:
            if address == wallet:
                blockers.append(
                    "treasury destination must differ from the armed wallet"
                )
            remaining = available - amount - expected_fee
            if remaining < configured_reserve:
                blockers.append(
                    "insufficient available balance after reserves and fees"
                )
        return {
            "blockers": list(dict.fromkeys(blockers)),
            "expected_fee_sol": expected_fee,
            "remaining_balance_sol": remaining,
            "warnings": warnings,
            "wallet_public_key": wallet,
            "token_accounts": list(token_accounts),
            "readiness": readiness,
            "profit_sweep_policy": profit_sweep_policy,
        }

    def execute_mobile_treasury(
        self,
        *,
        action_id: str,
        action: str,
        source_wallet_public_key: str,
        address: str,
        asset: str,
        amount: Decimal,
        token_accounts: list[str],
    ) -> dict[str, object]:
        receipt = self.storage.load_mobile_action_receipt(action_id)
        if receipt is None or receipt.action_type != action:
            raise ValueError("Durable treasury action receipt is required")
        bound_source = str(
            receipt.payload.get("source_wallet_public_key") or ""
        )
        if (
            not source_wallet_public_key
            or bound_source != source_wallet_public_key
            or self.settings.live_active_wallet_public_key.strip()
            != source_wallet_public_key
        ):
            raise ValueError(
                "Treasury source wallet binding does not match armed wallet"
            )
        preflight = self.mobile_treasury_preflight(
            action=action,
            address=address,
            asset=asset,
            amount=amount,
            token_accounts=token_accounts,
            exclude_action_id=action_id,
        )
        blockers = [str(value) for value in preflight.get("blockers", [])]
        if blockers:
            raise ValueError("; ".join(blockers))
        if action == "withdrawal":
            self._require_mobile_treasury_signer(
                source_wallet_public_key
            )
            result = self.hot_wallet.transfer_sol(
                address,
                float(amount),
                self.settings.solana_rpc_url,
            )
        elif action == "profit_sweep":
            policy = preflight.get("profit_sweep_policy", {})
            audit = self._mobile_treasury_audit(
                action_id=action_id,
                action=action,
                source_wallet_public_key=source_wallet_public_key,
                amount=amount,
                destination=address,
                summary={
                    "provider": "local_hot_wallet_profit_sweep",
                    "policy_enforced": True,
                    "sweep_mode": (
                        policy.get("sweep_mode")
                        if isinstance(policy, dict)
                        else ""
                    ),
                    "realized_pnl_sol": (
                        policy.get("realized_pnl_sol")
                        if isinstance(policy, dict)
                        else "0"
                    ),
                    "minimum_profit_sol": (
                        policy.get("minimum_profit_sol")
                        if isinstance(policy, dict)
                        else "0"
                    ),
                },
            )
            self._require_mobile_treasury_signer(
                source_wallet_public_key
            )
            result = self.hot_wallet.transfer_sol(
                address,
                float(amount),
                self.settings.solana_rpc_url,
            )
            self._complete_mobile_treasury_audit(audit, result)
        else:
            generated = self._build_mobile_rent_recovery_transaction(
                source_wallet_public_key,
                token_accounts,
            )
            unsigned = str(generated.get("unsigned_transaction_base64") or "")
            if not unsigned:
                raise ValueError(
                    "rent recovery transaction generation failed"
                )
            audit = self._mobile_treasury_audit(
                action_id=action_id,
                action=action,
                source_wallet_public_key=source_wallet_public_key,
                amount=amount,
                destination=address,
                summary={
                    "provider": "local_hot_wallet_rent_recovery",
                    "selected_count": int(
                        generated.get("selected_count") or 0
                    ),
                    "recoverable_rent_sol": str(
                        generated.get("recoverable_rent_sol") or amount
                    ),
                    "transaction_material_persisted": False,
                },
            )
            self._require_mobile_treasury_signer(
                source_wallet_public_key
            )
            result = self.hot_wallet.simulate_and_submit(
                unsigned,
                self.settings.solana_rpc_url,
            )
            self._complete_mobile_treasury_audit(audit, result)
        return {
            "status": "submitted",
            "operator_message": "Treasury transaction submitted; verifying outcome",
            "transaction_signature": str(
                result.get("signature")
                or result.get("transaction_signature")
                or ""
            ),
        }

    def _mobile_treasury_audit(
        self,
        *,
        action_id: str,
        action: str,
        source_wallet_public_key: str,
        amount: Decimal,
        destination: str,
        summary: dict[str, object],
    ) -> LiveExecutionAudit:
        now = utc_now()
        audit = LiveExecutionAudit(
            id=new_id("treasuryaudit"),
            created_at=now,
            updated_at=now,
            action=action,
            mint="SOL" if action == "profit_sweep" else "rent_recovery",
            amount=str(amount),
            status="submitting",
            signer_mode="local_hot_wallet",
            wallet_public_key=source_wallet_public_key,
            quote={
                **summary,
                "destination_wallet": destination,
                "source_wallet_public_key": source_wallet_public_key,
            },
            request={
                "source": "mobile_treasury",
                "mobile_action_id": action_id,
                "signer_mode": "local_hot_wallet",
            },
            final_status="submitting",
            recommended_action=(
                "Reconcile the public transaction signature; do not resubmit "
                "while the outcome is unknown."
            ),
        )
        self.storage.save_live_execution_audit(audit)
        return audit

    def _complete_mobile_treasury_audit(
        self,
        audit: LiveExecutionAudit,
        result: dict[str, object],
    ) -> None:
        audit.transaction_signature = str(
            result.get("signature")
            or result.get("transaction_signature")
            or ""
        )
        audit.status = "submitted"
        audit.final_status = "submitted"
        audit.updated_at = utc_now()
        simulation = result.get("simulation")
        if isinstance(simulation, dict):
            audit.simulation = {
                "source": "local_hot_wallet",
                "status": (
                    "ok"
                    if simulation.get("ok")
                    else "warning"
                    if simulation.get("warning")
                    else "error"
                ),
                "ok": bool(simulation.get("ok")),
                "warning": str(simulation.get("warning") or ""),
                "error": str(simulation.get("error") or ""),
            }
        self.storage.save_live_execution_audit(audit)

    def _build_mobile_rent_recovery_transaction(
        self,
        wallet_public_key: str,
        token_accounts: list[str],
    ) -> dict[str, object]:
        wallet = wallet_public_key.strip()
        selected = [
            account.strip() for account in token_accounts if account.strip()
        ]
        scan = self.live_rent_recovery_scan(wallet)
        eligible_by_account = {
            str(item["token_account"]): item
            for item in scan["eligible_accounts"]
        }
        missing = [
            account for account in selected if account not in eligible_by_account
        ]
        if missing:
            raise ValueError(
                "selected token accounts are not eligible: "
                + ", ".join(missing[:5])
            )
        blockhash = SolanaReadOnlyClient(
            self.settings.solana_rpc_url
        ).latest_blockhash()
        payer = Pubkey.from_string(wallet)
        instructions = [
            self._close_token_account_instruction(
                token_account=account,
                destination_wallet=wallet,
                owner_wallet=wallet,
                program_id=str(eligible_by_account[account]["program_id"]),
            )
            for account in selected
        ]
        message = MessageV0.try_compile(
            payer,
            instructions,
            [],
            Hash.from_string(blockhash),
        )
        transaction = VersionedTransaction.populate(message, [])
        recoverable = sum(
            Decimal(str(eligible_by_account[account].get("rent_sol") or "0"))
            for account in selected
        )
        return {
            "unsigned_transaction_base64": base64.b64encode(
                bytes(transaction)
            ).decode("utf-8"),
            "selected_count": len(selected),
            "recoverable_rent_sol": str(recoverable),
        }

    def reconcile_mobile_treasury_action(
        self,
        receipt: object,
    ) -> dict[str, object]:
        payload = getattr(receipt, "payload", {})
        signature = (
            str(payload.get("transaction_signature") or "")
            if isinstance(payload, dict)
            else ""
        )
        if not signature:
            return {
                "status": "review_required",
                "operator_message": (
                    "Treasury dispatch has no transaction signature; review locally "
                    "and do not resubmit."
                ),
            }
        status = self._signature_status(signature)
        if not status.get("ok"):
            return {
                "status": "review_required",
                "operator_message": "RPC reconciliation failed; review locally",
            }
        if status.get("err"):
            return {
                "status": "failed",
                "operator_message": "Treasury transaction failed on chain",
            }
        confirmation = str(status.get("confirmation_status") or "")
        if confirmation in {"confirmed", "finalized"}:
            return {
                "status": "confirmed",
                "operator_message": "Treasury transaction confirmed",
            }
        return {
            "status": "verifying",
            "operator_message": "Verifying treasury outcome",
        }

    def mobile_position(self, position_id: str) -> dict[str, object] | None:
        now = utc_now()
        if position_id.startswith("paper:"):
            token_id = position_id.removeprefix("paper:")
            token = next(
                (item for item in self.storage.load_all_tokens(5000) if item.id == token_id),
                None,
            )
            return self._mobile_paper_position_detail(token, now) if token else None
        position = self.storage.load_live_ledger_position(position_id)
        if position is None:
            return None
        previous_status = position.status
        self._normalize_live_position_status(position)
        if position.status != previous_status:
            position.version += 1
            position.updated_at = utc_now()
        self._refresh_live_position_estimate(position)
        self.storage.save_live_ledger_position(position)
        return self._mobile_live_position_detail(position, now)

    def mobile_adjust_position_exit(
        self,
        *,
        position_id: str,
        expected_version: int,
        stop_pct: float,
        target_pct: float,
        mobile_action_id: str = "",
    ) -> dict[str, object]:
        position = self.storage.load_live_ledger_position(position_id)
        if position is None:
            raise LookupError("Mobile live position not found")
        if int(position.version) != int(expected_version):
            raise ValueError("Position version conflict")
        if position.status != "open" or position.token_balance <= 0:
            raise ValueError("Only an open live position can change exit controls")
        if not (0 < float(stop_pct) <= 100) or not (0 < float(target_pct) <= 100):
            raise ValueError("Exit controls are outside backend bounds")
        position.stop_pct = round(float(stop_pct), 4)
        position.target_pct = round(float(target_pct), 4)
        position.last_mobile_action_id = mobile_action_id
        position.version += 1
        position.updated_at = utc_now()
        self.storage.save_live_ledger_position(position)
        self.add_event(
            "warning",
            f"Mobile exit controls updated for {position.symbol or position.mint[:8]}",
            subsystem="mobile",
            operator_action="Review the position and live exit signals after changing its bounds.",
        )
        return self._mobile_live_position_detail(position, utc_now())

    def mobile_live_execution_blockers(
        self,
        intent: LiveExecutionIntent,
    ) -> list[str]:
        blockers = self._live_execution_blockers(
            True,
            intent.action,
            intent.wallet_public_key,
            intent.signer_mode,
            autonomous=False,
        )
        readiness_halt = self.readiness_halt_reason()
        if readiness_halt:
            blockers.append(readiness_halt)
        if intent.action == "buy":
            backup = self._pre_run_backup_status()
            if backup.get("blocks_live_entries"):
                blockers.append(
                    str(
                        backup.get("blocker")
                        or "pre-run backup is required before live entries"
                    )
                )
        return list(dict.fromkeys(blockers))

    def _mobile_position_summaries(
        self,
        now: datetime,
        *,
        live_positions: list[LiveLedgerPosition] | None = None,
    ) -> list[dict[str, object]]:
        paper = [
            self._mobile_paper_position_summary(token, now)
            for token in self.storage.load_all_tokens(5000)
            if token.status
            in {
                TokenStatus.PAPER_BOUGHT,
                TokenStatus.MONITORING,
            }
        ]
        live = [
            self._mobile_live_position_summary(position, now)
            for position in (
                live_positions
                if live_positions is not None
                else self._live_ledger_positions("")
            )
        ]
        return sorted(
            [*paper, *live],
            key=lambda position: str(position["updated_at"]),
            reverse=True,
        )

    def _mobile_paper_position_summary(
        self,
        token: TokenSignal,
        now: datetime,
    ) -> dict[str, object]:
        observed_at = token.last_observed_trade_at or token.detected_at
        age = self._mobile_mark_age(observed_at, now)
        cost_basis = float(token.amount_sol or 0.0) * float(token.remaining_fraction)
        realized = float(token.realized_pnl_sol or 0.0)
        unrealized = float(token.pnl_sol or 0.0) - realized
        return {
            "id": f"paper:{token.id}",
            "mode": "paper",
            "symbol": token.symbol or token.name or "Unknown",
            "mint": token.mint,
            "status": "open",
            "opened_at": (token.opened_at or token.detected_at).isoformat(),
            "updated_at": observed_at.isoformat(),
            "cost_basis_sol": cost_basis,
            "value_sol": round(cost_basis + unrealized, 9),
            "realized_pnl_sol": realized,
            "unrealized_pnl_sol": unrealized,
            "pnl_pct": round((unrealized / cost_basis) * 100, 2)
            if cost_basis
            else 0.0,
            "pnl_approximate": True,
            "mark_fresh": age is not None
            and age <= self.settings.source_stale_seconds,
            "mark_age_seconds": age,
            "mark_source": token.price_source or "paper_model",
        }

    def _mobile_live_position_summary(
        self,
        position: LiveLedgerPosition,
        now: datetime,
    ) -> dict[str, object]:
        age = self._mobile_mark_age(position.mark_price_at, now)
        cost_basis = float(position.cost_basis_sol)
        return {
            "id": position.id,
            "mode": "live",
            "symbol": position.symbol or "Unknown",
            "mint": position.mint,
            "status": position.status,
            "opened_at": position.created_at.isoformat(),
            "updated_at": position.updated_at.isoformat(),
            "cost_basis_sol": cost_basis,
            "value_sol": round(cost_basis + float(position.unrealized_pnl_sol), 9),
            "realized_pnl_sol": float(position.realized_pnl_sol),
            "unrealized_pnl_sol": float(position.unrealized_pnl_sol),
            "pnl_pct": round(
                (float(position.unrealized_pnl_sol) / cost_basis) * 100,
                2,
            )
            if cost_basis
            else 0.0,
            "pnl_approximate": position.realized_pnl_confidence != "audited"
            or position.unrealized_pnl_confidence not in {"none", "audited"},
            "mark_fresh": age is not None
            and age <= self.settings.source_stale_seconds,
            "mark_age_seconds": age,
            "mark_source": position.mark_price_source,
        }

    def _mobile_paper_position_detail(
        self,
        token: TokenSignal,
        now: datetime,
    ) -> dict[str, object]:
        summary = self._mobile_paper_position_summary(token, now)
        observed_at = token.last_observed_trade_at or token.detected_at
        realized = float(token.realized_pnl_sol or 0.0)
        unrealized = float(token.pnl_sol or 0.0) - realized
        total = realized + unrealized
        return {
            **summary,
            "wallet_label": "Paper model",
            "token_balance": 0.0,
            "mark": {
                "price_sol": float(token.current_price or token.entry_price or 0.0),
                "source": token.price_source or "paper_model",
                "confidence": float(token.price_confidence or 0.0),
                "observed_at": observed_at.isoformat(),
                "age_seconds": summary["mark_age_seconds"],
                "fresh": summary["mark_fresh"],
            },
            "pnl": {
                "realized_sol": realized,
                "unrealized_sol": unrealized,
                "total_sol": total,
                "percentage": summary["pnl_pct"],
                "approximate": True,
                "confidence": "paper_model",
                "notes": ["Paper PnL is simulated and is not account equity."],
            },
            "reconciliation_status": "paper_model",
            "version": 1,
            "stop_pct": float(self.settings.stop_loss_pct),
            "target_pct": float(self.settings.take_profit_pct),
            "prepared_close": None,
            "allowed_actions": {
                "adjust_exit": False,
                "close": False,
                "reason": "Guarded position actions are available in the review flow.",
            },
        }

    def _mobile_live_position_detail(
        self,
        position: LiveLedgerPosition,
        now: datetime,
    ) -> dict[str, object]:
        summary = self._mobile_live_position_summary(position, now)
        total = float(position.realized_pnl_sol + position.unrealized_pnl_sol)
        wallet = position.wallet_public_key
        wallet_label = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 12 else wallet or "Unknown wallet"
        prepared_close = next(
            (
                intent
                for intent in self.storage.load_live_intents(200)
                if intent.action == "sell"
                and intent.amount == "100%"
                and intent.mint == position.mint
                and intent.wallet_public_key == position.wallet_public_key
                and intent.generated_from_position
                and intent.generated_position_id == position.id
                and int(intent.generated_position_version)
                == int(position.version)
                and abs(
                    float(intent.generated_position_token_balance)
                    - float(position.token_balance)
                )
                <= 1e-12
                and intent.status == "simulated"
                and not intent.stale
                and (
                    intent.expires_at is None
                    or intent.expires_at > now
                )
            ),
            None,
        )
        prepared_close_audit = (
            self.storage.load_live_execution_audit(prepared_close.audit_id)
            if prepared_close is not None
            else None
        )
        if (
            prepared_close_audit is None
            or prepared_close_audit.status != "simulated"
            or prepared_close_audit.final_status != "simulated"
            or bool(prepared_close_audit.guarded_action_id)
            or prepared_close_audit.action != "sell"
            or prepared_close_audit.amount != "100%"
            or str(prepared_close_audit.quote.get("status") or "") != "ready"
            or bool(prepared_close_audit.quote.get("shadow_only"))
            or float(prepared_close_audit.quote.get("slippage_pct") or 0) <= 0
            or (
                self._parse_iso_datetime(
                    str(prepared_close_audit.quote.get("expires_at") or "")
                )
                or now
            )
            <= now
        ):
            prepared_close = None
            prepared_close_audit = None
        controls_available = (
            position.status == "open"
            and position.token_balance > 0
            and position.reconciliation_status != "needs_review"
        )
        return {
            **summary,
            "wallet_label": wallet_label,
            "token_balance": float(position.token_balance),
            "mark": {
                "price_sol": float(position.mark_price_sol),
                "source": position.mark_price_source,
                "confidence": float(position.mark_price_confidence),
                "observed_at": position.mark_price_at.isoformat() if position.mark_price_at else None,
                "age_seconds": summary["mark_age_seconds"],
                "fresh": summary["mark_fresh"],
            },
            "pnl": {
                "realized_sol": float(position.realized_pnl_sol),
                "unrealized_sol": float(position.unrealized_pnl_sol),
                "total_sol": total,
                "percentage": summary["pnl_pct"],
                "approximate": summary["pnl_approximate"],
                "confidence": position.unrealized_pnl_confidence,
                "notes": list(position.pnl_confidence_notes),
            },
            "reconciliation_status": position.reconciliation_status,
            "version": int(position.version),
            "stop_pct": float(
                position.stop_pct
                if position.stop_pct is not None
                else self.settings.stop_loss_pct
            ),
            "target_pct": float(
                position.target_pct
                if position.target_pct is not None
                else self.settings.take_profit_pct
            ),
            "prepared_close": (
                {
                    "intent_id": prepared_close.id,
                    "intent_version": int(prepared_close.version),
                    "position_version": int(position.version),
                    "amount": "100%",
                    "slippage_pct": float(
                        prepared_close_audit.quote.get("slippage_pct") or 0
                    ),
                    "expires_at": prepared_close.expires_at.isoformat()
                    if prepared_close.expires_at
                    else None,
                }
                if prepared_close is not None
                else None
            ),
            "allowed_actions": {
                "adjust_exit": controls_available,
                "close": controls_available and prepared_close is not None,
                "reason": (
                    "A simulated sell intent is ready for guarded close review."
                    if controls_available and prepared_close is not None
                    else "Prepare and simulate a matching sell intent before closing from mobile."
                    if controls_available
                    else "Resolve position reconciliation before changing live controls."
                ),
            },
        }

    def _mobile_positions_freshness(
        self,
        positions: list[dict[str, object]],
        now: datetime,
    ) -> dict[str, object]:
        ages = [
            int(position["mark_age_seconds"])
            for position in positions
            if position.get("mark_age_seconds") is not None
        ]
        age = max(ages, default=0)
        if not positions or not ages:
            status = "unavailable"
        elif any(not bool(position["mark_fresh"]) for position in positions):
            status = "stale"
        else:
            status = "fresh"
        return {
            "status": status,
            "generated_at": now.isoformat(),
            "age_seconds": age,
            "stale_after_seconds": self.settings.source_stale_seconds,
            "approximate_pnl": any(
                bool(position["pnl_approximate"]) for position in positions
            ),
        }

    @staticmethod
    def _mobile_mark_age(
        observed_at: datetime | None,
        now: datetime,
    ) -> int | None:
        if (
            observed_at is None
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
            or observed_at > now
        ):
            return None
        return int((now - observed_at).total_seconds())

    @staticmethod
    def _mobile_allocation(
        positions: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        included = [
            (position, Decimal(str(float(position["value_sol"]))))
            for position in positions
            if float(position["value_sol"]) > 0
        ]
        total_value = sum((value for _, value in included), Decimal("0"))
        if total_value <= 0:
            return []
        exact_basis_points = [
            (value / total_value) * Decimal("10000")
            for _, value in included
        ]
        basis_points = [
            int(value.quantize(Decimal("1"), rounding=ROUND_DOWN))
            for value in exact_basis_points
        ]
        remainder = 10000 - sum(basis_points)
        remainder_order = sorted(
            range(len(included)),
            key=lambda index: (
                -(exact_basis_points[index] - Decimal(basis_points[index])),
                str(included[index][0]["id"]),
            ),
        )
        for index in remainder_order[:remainder]:
            basis_points[index] += 1
        return [
            {
                "key": str(position["id"]),
                "label": str(position["symbol"]),
                "value_sol": float(value),
                "percentage": basis_points[index] / 100,
                "mode": str(position["mode"]),
            }
            for index, (position, value) in enumerate(included)
        ]

    def mobile_start_bot(self, live_trading_enabled: bool = False, local_auth_enabled: bool = False) -> dict[str, object]:
        self.start()
        self.add_event("info", "Mobile cockpit started bot", subsystem="mobile")
        return self.mobile_cockpit(live_trading_enabled=live_trading_enabled, local_auth_enabled=local_auth_enabled)

    def mobile_stop_bot(self, live_trading_enabled: bool = False, local_auth_enabled: bool = False) -> dict[str, object]:
        self.stop()
        self.add_event("warning", "Mobile cockpit stopped bot", subsystem="mobile")
        return self.mobile_cockpit(live_trading_enabled=live_trading_enabled, local_auth_enabled=local_auth_enabled)

    def mobile_set_kill_switch(
        self,
        enabled: bool,
        reason: str = "",
        live_trading_enabled: bool = False,
        local_auth_enabled: bool = False,
    ) -> dict[str, object]:
        self.set_live_kill_switch(enabled, reason)
        self.add_event(
            "danger" if enabled else "warning",
            f"Mobile cockpit {'enabled' if enabled else 'disabled'} kill switch",
            subsystem="mobile",
            operator_action=reason.strip(),
        )
        return self.mobile_cockpit(live_trading_enabled=live_trading_enabled, local_auth_enabled=local_auth_enabled)

    def _normalize_mobile_scopes(self, scopes: list[str] | None) -> list[str]:
        requested = scopes or list(self.MOBILE_DEFAULT_SCOPES)
        clean = [scope for scope in requested if scope in self.MOBILE_ALLOWED_SCOPES]
        if self.MOBILE_MONITOR_SCOPE not in clean:
            clean.insert(0, self.MOBILE_MONITOR_SCOPE)
        return list(dict.fromkeys(clean))

    def _hash_mobile_secret(self, value: str) -> str:
        return hashlib.sha256(f"cryptoarc-mobile-v1:{value}".encode("utf-8")).hexdigest()

    def _parse_mobile_time(self, value: object) -> datetime:
        if not value:
            return datetime.min.replace(tzinfo=utc_now().tzinfo)
        text = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return datetime.min.replace(tzinfo=utc_now().tzinfo)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=utc_now().tzinfo)
        return parsed

    def _clean_mobile_label(self, value: str, fallback: str, limit: int) -> str:
        cleaned = re.sub(r"\s+", " ", str(value or "").strip())
        cleaned = re.sub(r"[^A-Za-z0-9 .:_()/-]", "", cleaned)
        return (cleaned or fallback)[:limit]

    def _public_mobile_device(self, device: dict[str, object]) -> dict[str, object]:
        return {key: value for key, value in device.items() if key != "token_hash"}

    def _hydrate_active_tokens(self) -> list[TokenSignal]:
        recent = self.storage.load_tokens()
        open_statuses = {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}
        open_tokens = [token for token in self.storage.load_all_tokens(5000) if token.status in open_statuses]
        open_by_id: dict[str, TokenSignal] = {token.id: token for token in sorted(open_tokens, key=lambda token: token.detected_at, reverse=True)}
        recent_without_open = [token for token in recent if token.id not in open_by_id]
        keep_recent = max(0, 80 - len(open_by_id))
        tokens = [*recent_without_open[:keep_recent], *open_by_id.values()]
        return sorted(tokens, key=lambda token: token.detected_at, reverse=True)

    def _load_open_storage_tokens(self) -> list[TokenSignal]:
        open_statuses = {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}
        return [
            token
            for token in self.storage.load_all_tokens(5000)
            if token.status in open_statuses or (token.opened_at is not None and token.closed_at is None and token.amount_sol is not None)
        ]

    def _ensure_active_tokens_loaded(self) -> None:
        open_by_id = {token.id: token for token in self._load_open_storage_tokens()}
        if not open_by_id:
            return

        current_by_id = {token.id: token for token in self.tokens}
        merged_by_id = dict(current_by_id)
        for token_id, token in open_by_id.items():
            if token_id not in merged_by_id:
                merged_by_id[token_id] = token

        active_tokens = sorted(
            [merged_by_id[token_id] for token_id in open_by_id if token_id in merged_by_id],
            key=lambda token: token.detected_at,
            reverse=True,
        )
        active_ids = {token.id for token in active_tokens}
        remaining_slots = max(0, 80 - len(active_tokens))
        recent_non_active = [
            token
            for token in sorted(merged_by_id.values(), key=lambda token: token.detected_at, reverse=True)
            if token.id not in active_ids
        ][:remaining_slots]
        self.tokens = deque([*active_tokens, *recent_non_active], maxlen=max(80, len(active_tokens)))

    def _recover_orphaned_open_tokens(self) -> None:
        recent_ids = {token.id for token in self.storage.load_tokens()}
        recovered = 0
        for token in self.tokens:
            if token.id in recent_ids:
                continue
            if token.status not in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}:
                continue
            if token.entry_price is None or token.current_price is None:
                token.status = TokenStatus.SKIPPED
                token.reason = "orphaned state recovery"
            else:
                self.paper.close(token, self.settings, "orphaned state recovery")
                self.storage.save_trade(self.trade_from_token(token))
                self.storage.save_trade_session(self.session_from_token(token, "closed"))
            self.storage.save_token(token)
            recovered += 1
        if recovered:
            self.add_event("warning", f"Recovered {recovered} orphaned paper position{'s' if recovered != 1 else ''}")

    def update_settings(self, patch: dict[str, object]) -> BotSnapshot:
        current = asdict(self.settings)
        clean_patch = {key: value for key, value in patch.items() if key in current}
        changed_keys = sorted([key for key, value in clean_patch.items() if current.get(key) != value])
        current.update(clean_patch)
        self.settings = BotSettings(**current)
        self.source_status.source = self.settings.launch_source
        self.storage.save_settings(self.settings)
        self._invalidate_readiness_cache()
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

    def _event_context(self, subsystem: str = "app") -> tuple[str, dict[str, object]]:
        session_id = self.active_live_session_id if subsystem == "live" or self.active_live_session_id else ""
        context: dict[str, object] = {}
        if session_id:
            context["session_id"] = session_id
        if subsystem == "live" or session_id:
            context["active_backend"] = self._active_backend_snapshot()
            context["live_session_acknowledged"] = self.settings.live_session_acknowledged
            context["kill_switch_enabled"] = self.settings.kill_switch_enabled
        return session_id, context

    def add_event(self, level: str, message: str, token_id: str | None = None, subsystem: str = "app", operator_action: str = "") -> None:
        session_id, context = self._event_context(subsystem)
        event = TradeEvent(
            id=new_id("evt"),
            created_at=utc_now(),
            level=level,
            message=message,
            token_id=token_id,
            subsystem=subsystem,
            operator_action=operator_action,
            session_id=session_id,
            context=context,
        )
        self.events.appendleft(event)
        self.storage.save_event(event)
        self.alerts.alert_event(level, subsystem, message, operator_action)

    def _reload_from_storage(self, persist_settings_version: bool = True) -> None:
        self.settings = self.storage.load_settings()
        self._sync_hot_wallet_settings(self.hot_wallet.status())
        self.tokens = deque(self._hydrate_active_tokens(), maxlen=80)
        self.events = deque(self.storage.load_events(), maxlen=30)
        self.backtest_runs = deque(self.storage.load_backtest_runs(), maxlen=20)
        self.source_status.source = self.settings.launch_source
        self.creator_history = Counter(token.creator for token in self.storage.load_all_tokens())
        if persist_settings_version:
            self.current_settings_version_id = self.ensure_settings_version("restore reload", [])
        else:
            settings_versions = self.storage.load_settings_versions(1)
            self.current_settings_version_id = settings_versions[0].id if settings_versions else ""
        self.recalculate_stats()

    def record_source_event(self, source: str, raw_payload: dict[str, object], token: TokenSignal | None, message: str = "", status: str | None = None) -> None:
        if token:
            self.last_ingested_launch_at = utc_now()
        stored_payload = dict(raw_payload)
        if token and not any(str(stored_payload.get(key) or "").strip() for key in ("mint", "tokenMint", "token", "ca", "normalized_mint")):
            stored_payload["normalized_mint"] = token.mint
            stored_payload["normalized_symbol"] = token.symbol
            stored_payload["normalized_source"] = source
        event = SourceEvent(
            id=new_id("src"),
            source=source,
            received_at=utc_now(),
            raw_payload=stored_payload,
            normalized_token_id=token.id if token else None,
            status=status or ("normalized" if token else "raw"),
            message=message,
        )
        self.storage.save_source_event(event)

    def ingest_source_event(self, event: LaunchEvent, *, active_tokens_loaded: bool = False) -> None:
        if event.kind == "trade":
            if event.source == "pumpportal" and self.source_status.pumpportal_funding_blocked:
                self.source_status.pumpportal_funding_blocked = False
                self.source_status.pumpportal_funding_message = ""
                self.source_status.pumpportal_funding_blocked_at = None
            self.record_source_event(event.source, event.raw_payload, None, event.message, status="trade")
            self.apply_observed_trade(event, active_tokens_loaded=active_tokens_loaded)
            return
        if event.kind in {"verification", "verification_status"}:
            token = self._direct_solana_token_from_event(event) if event.kind == "verification" else None
            self.record_source_event(event.source, event.raw_payload, token, event.message, status="status" if event.kind == "verification_status" else ("normalized" if token else "raw"))
            if token:
                self.ingest_launch(token)
            return
        self._handle_source_status_message(event)
        event_status = None
        if event.token is None:
            if self._is_pumpportal_ignored_non_launch(event.raw_payload):
                event_status = "ignored"
            elif event.message or self._is_pumpportal_funding_message(event.raw_payload, event.message):
                event_status = "status"
        self.record_source_event(event.source, event.raw_payload, event.token, event.message, status=event_status)
        if event.token:
            self.ingest_launch(event.token)

    def _handle_source_status_message(self, event: LaunchEvent) -> None:
        if event.source != "pumpportal" or not self._is_pumpportal_funding_message(event.raw_payload, event.message):
            return
        already_blocked = self.source_status.pumpportal_funding_blocked
        message = event.message or str(event.raw_payload.get("message") or "PumpPortal API wallet appears unfunded.")
        self.source_status.pumpportal_funding_blocked = True
        self.source_status.pumpportal_funding_message = message[:500]
        self.source_status.pumpportal_funding_blocked_at = event.received_at
        if already_blocked:
            return
        self.add_event(
            "warning",
            "PumpPortal API wallet appears unfunded; paid trade-stream evidence may have stopped.",
            subsystem="source",
            operator_action="Refill the PumpPortal API wallet or lower Max Trade Subscriptions before trusting paper/shadow price evidence.",
        )

    def _is_pumpportal_funding_message(self, payload: dict[str, object], message: str = "") -> bool:
        text = f"{message} {json.dumps(payload, default=str)}".lower()
        mentions_trade_stream = (
            "subscribetokentrade" in text
            or "subscribeaccounttrade" in text
            or "trade subscription" in text
            or "pumpswap websocket data" in text
            or "websocket data" in text
        )
        mentions_funding = (
            "funded" in text
            or "0.02" in text
            or "insufficient" in text
            or "balance" in text
            or "wallet" in text
            or "minimum balance" in text
        )
        return mentions_trade_stream and mentions_funding

    def _is_pumpportal_ignored_non_launch(self, payload: dict[str, object]) -> bool:
        mint = str(payload.get("mint") or payload.get("tokenMint") or payload.get("token") or payload.get("ca") or "").strip()
        return mint in PUMPPORTAL_NON_LAUNCH_MINTS

    def apply_observed_trade(self, event: LaunchEvent, *, active_tokens_loaded: bool = False) -> None:
        if not self.settings.use_observed_prices or not event.mint:
            return
        if not active_tokens_loaded:
            self._ensure_active_tokens_loaded()
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
                    self.paper.mark_to_market(token, self.settings)
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
                self.paper.mark_to_market(token, self.settings)
            token.decision_log.append(f"Observed {event.trade_side} trade updated price from {old_price:.8f} to {observed_price:.8f} ({observation.price_source}, {observation.confidence:.2f})")
            self.storage.save_token(token)
            self.storage.save_price_observation(observation)
            break

    def tick(self, *, build_snapshot: bool = True) -> BotSnapshot | None:
        self._ensure_active_tokens_loaded()
        self.last_bot_tick_at = utc_now()
        self.last_tick_error = ""
        self.bot_loop_iterations += 1
        tokens_seen = 0
        active_tokens = 0
        closed_tokens = 0
        for token in list(self.tokens):
            tokens_seen += 1
            token.age_seconds = max(0, int((utc_now() - token.detected_at).total_seconds()))
            if token.status not in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}:
                self.storage.save_token(token)
                continue

            active_tokens += 1
            uses_observed_price = self.settings.use_observed_prices and token.observed_price_updates > 0
            delta_pct = 0.0 if uses_observed_price else self.simulator.price_delta_pct(token, self.settings.paper_price_volatility_pct)
            if self.settings.max_rejected_price_streak_enabled and self.settings.max_rejected_price_streak and token.rejected_price_streak >= self.settings.max_rejected_price_streak:
                self.paper.close(token, self.settings, "price quality guard")
                closed = True
            else:
                closed = self.paper.tick(token, self.settings, delta_pct)
            self.storage.save_token(token)
            if closed:
                closed_tokens += 1
                pnl = token.pnl_sol or 0.0
                outcome = self._classify_pnl(pnl)
                level = "success" if outcome == "win" else "warning"
                reason = f" ({token.exit_reason})" if token.exit_reason else ""
                label = "scratch " if outcome == "scratch" else ""
                self.add_event(level, f"Paper sold {token.symbol} at {pnl:+.4f} SOL {label}{reason}".replace("  ", " "), token.id)
                self.storage.save_trade(self.trade_from_token(token))
                self.storage.save_trade_session(self.session_from_token(token, "closed"))

        self.recalculate_stats()
        snapshot = self.snapshot() if build_snapshot else None
        completed_at = utc_now()
        self.last_tick_tokens_seen = tokens_seen
        self.last_tick_active_tokens = active_tokens
        self.last_tick_closed = closed_tokens
        self.last_tick_completed_at = completed_at
        return snapshot

    def recover_open_paper_positions(self, note: str = "") -> dict[str, object]:
        clean_note = (note or "operator recovery").strip()[:160] or "operator recovery"
        exit_reason = f"paper recovery: {clean_note}"
        open_statuses = {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}
        tokens_by_id = {token.id: token for token in self.storage.load_all_tokens(5000)}
        for token in self.tokens:
            tokens_by_id[token.id] = token

        open_tokens = [
            token
            for token in tokens_by_id.values()
            if token.status in open_statuses or (token.opened_at is not None and token.closed_at is None and token.amount_sol is not None)
        ]
        closed_tokens: list[TokenSignal] = []
        total_pnl = 0.0
        closed_at = utc_now()

        for token in open_tokens:
            if token.entry_price and token.current_price and token.pnl_sol is None:
                self.paper.mark_to_market(token, self.settings)
            token.status = TokenStatus.PAPER_SOLD
            token.exit_price = token.current_price or token.entry_price
            token.closed_at = closed_at
            token.exit_reason = exit_reason
            if token.opened_at:
                token.hold_duration_seconds = max(0, int((closed_at - token.opened_at).total_seconds()))
            token.realized_pnl_sol = token.pnl_sol or 0.0
            token.remaining_fraction = 0.0
            token.decision_log.append(f"Paper position recovered closed: {clean_note}; final P&L {token.pnl_sol or 0.0:+.6f} SOL")
            self.storage.save_token(token)
            self.storage.save_trade(self.trade_from_token(token))
            self.storage.save_trade_session(self.session_from_token(token, "closed"))
            total_pnl = round(total_pnl + (token.pnl_sol or 0.0), 6)
            closed_tokens.append(token)

        if closed_tokens:
            self.tokens = deque(sorted(tokens_by_id.values(), key=lambda item: item.detected_at, reverse=True), maxlen=80)
            self.add_event(
                "warning",
                f"Recovered {len(closed_tokens)} open paper position{'s' if len(closed_tokens) != 1 else ''} ({clean_note})",
                subsystem="paper",
                operator_action="Review recovered paper positions before using this run for promotion evidence.",
            )
        else:
            self.add_event("info", "No open paper positions to recover", subsystem="paper")

        self.recalculate_stats()
        return {
            "closed_positions": len(closed_tokens),
            "total_recovered_pnl_sol": total_pnl,
            "exit_reason": exit_reason,
            "token_ids": [token.id for token in closed_tokens],
            "status": "recovered" if closed_tokens else "clear",
            "operator_action": "Review recovered paper positions before the next paper run." if closed_tokens else "No recovery action was needed.",
        }

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
        tags: list[str] = list(token.intelligence_tags)

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
        paper_model_cost = self._paper_model_cost_sol(token)
        shadow_quote_cost = round(float(token.quote_shadow_total_cost_sol or 0.0), 9)
        quote_adjustment = round(max(0.0, shadow_quote_cost - paper_model_cost), 9)
        quote_adjusted_pnl = None
        accuracy_status = "paper_only"
        if token.pnl_sol is not None and shadow_quote_cost > 0:
            quote_adjusted_pnl = round(float(token.pnl_sol or 0.0) - quote_adjustment, 9)
            accuracy_status = "quote_adjusted"
        elif token.quote_shadow_status:
            accuracy_status = str(token.quote_shadow_status)
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
            exit_fee_sol=token.exit_fee_sol if token.closed_at and token.exit_fee_sol else ((token.amount_sol or self.settings.trade_size_sol) * (self.settings.paper_fee_bps / 10000) if token.closed_at else 0.0),
            entry_provider_fee_sol=token.entry_provider_fee_sol,
            exit_provider_fee_sol=token.exit_provider_fee_sol if token.closed_at else 0.0,
            entry_network_fee_sol=token.entry_network_fee_sol,
            exit_network_fee_sol=token.exit_network_fee_sol if token.closed_at else 0.0,
            entry_priority_fee_sol=token.entry_priority_fee_sol,
            exit_priority_fee_sol=token.exit_priority_fee_sol if token.closed_at else 0.0,
            entry_slippage_cost_sol=token.entry_slippage_cost_sol,
            entry_price_impact_cost_sol=token.entry_price_impact_cost_sol,
            price_impact_pct=token.price_impact_pct,
            slippage_paid_pct=token.slippage_paid_pct,
            paper_model_cost_sol=paper_model_cost,
            shadow_quote_cost_sol=shadow_quote_cost,
            quote_adjustment_sol=quote_adjustment,
            quote_adjusted_pnl_sol=quote_adjusted_pnl,
            simulation_accuracy_status=accuracy_status,
            source_price_confidence=token.price_confidence,
            settings_version_id=token.settings_version_id,
        )

    def _paper_model_cost_sol(self, token: TokenSignal) -> float:
        return round(
            float(token.fee_paid_sol or 0.0)
            + float(token.exit_fee_sol or 0.0)
            + float(token.entry_slippage_cost_sol or 0.0)
            + float(token.entry_price_impact_cost_sol or 0.0),
            9,
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
        self._ensure_active_tokens_loaded()
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
        trades: list[dict[str, object]] = []
        for token in candidates:
            replay_token = self._replay_launch_candidate(token)
            decision = self.risk.evaluate(replay_token, settings, replay_stats, open_positions=0)
            if decision.allowed:
                buys += 1
                pnl = replay_token.pnl_sol if replay_token.pnl_sol is not None else self._observed_replay_pnl(replay_token, settings)
                simulated_pnl = round(simulated_pnl + pnl, 6)
                pnl_curve.append(simulated_pnl)
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
                        "reason": replay_token.reason,
                        "score": replay_token.score,
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
            max_drawdown_sol=self._peak_to_trough_drawdown_sol(
                [float(item.get("pnl_sol", 0.0) or 0.0) for item in trades if item.get("decision") == "buy"]
            ),
            profit_factor=round(gross_win / gross_loss, 2) if gross_loss else 0.0,
            avg_hold_seconds=int(sum((token.hold_duration_seconds or 0) for token in candidates) / max(1, len(candidates))),
            best_trade_sol=round(max([float(item.get("pnl_sol", 0) or 0) for item in trades if item.get("decision") == "buy"], default=0.0), 6),
            worst_trade_sol=round(min([float(item.get("pnl_sol", 0) or 0) for item in trades if item.get("decision") == "buy"], default=0.0), 6),
            pnl_curve=pnl_curve[-80:],
            trades=trades[:80],
            comparison=[{"date_from": date_from or "any", "date_to": date_to or "any", "replay_speed": replay_speed}],
        )
        run.determinism_fingerprint = self._backtest_run_fingerprint(run, candidates, settings)
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
        run.determinism_fingerprint = self._backtest_run_fingerprint(run, candidates[:limit], self._settings_for_profile(profile))
        self.storage.save_backtest_run(run)
        return run

    def source_parser_replay_report(
        self,
        limit: int | None = None,
        profile: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, object]:
        limit = max(1, min(5000, int(limit or self.settings.raw_replay_limit)))
        events = self._filter_source_events_by_date(self.storage.load_source_events(limit), date_from, date_to)
        candidates: list[TokenSignal] = []
        rows: list[dict[str, object]] = []
        counts: Counter[str] = Counter()

        for event in events:
            event_payload = event.to_dict()
            event_kind = str(event_payload.get("event_kind") or "unknown")
            parser_result = str(event_payload.get("parser_result") or "unknown")
            mint = self._source_event_mint(event)
            counts[f"status:{event.status}"] += 1
            counts[f"kind:{event_kind}"] += 1
            counts[f"parser:{parser_result}"] += 1
            token: TokenSignal | None = None
            replay_result = parser_result
            failure_reason = ""
            replay_action = "inspect"

            if event.status == "trade" or event_kind in {"buy", "sell", "trade"}:
                replay_result = "trade_event"
                replay_action = "use_for_price_context"
                counts["trade_events"] += 1
            elif not mint:
                replay_result = "missing_mint"
                failure_reason = "raw event does not expose a mint/token address"
                replay_action = "inspect_raw_payload"
                counts["normalization_failures"] += 1
            elif event.source == "pumpportal":
                token = normalize_pumpportal_new_token(event.raw_payload, event.received_at)
                if token:
                    replay_result = "normalized"
                    replay_action = "eligible_for_replay"
                    candidates.append(token)
                    counts["normalized"] += 1
                else:
                    replay_result = "unsupported_shape"
                    failure_reason = "PumpPortal event did not match supported create/new-token shape"
                    replay_action = "inspect_parser_shape"
                    counts["normalization_failures"] += 1
            else:
                token = TokenSignal(
                    id=new_id("replay"),
                    symbol=str(event.raw_payload.get("symbol") or "MOCK")[:12].upper(),
                    name=str(event.raw_payload.get("symbol") or "Mock Replay"),
                    mint=mint,
                    creator=str(event.raw_payload.get("creator") or "unknown"),
                    detected_at=event.received_at,
                    current_price=0.00003,
                    metadata_score=0.65,
                    buy_velocity=0.45,
                    sell_pressure=0.2,
                )
                replay_result = "normalized"
                replay_action = "eligible_for_replay"
                candidates.append(token)
                counts["normalized"] += 1

            rows.append(
                {
                    "event_id": event.id,
                    "received_at": event.received_at.isoformat(),
                    "source": event.source,
                    "status": event.status,
                    "event_kind": event_kind,
                    "parser_result": replay_result,
                    "mint": mint,
                    "normalized_token_id": token.id if token else event.normalized_token_id,
                    "symbol": token.symbol if token else "",
                    "failure_reason": failure_reason,
                    "replay_action": replay_action,
                    "message": event.message,
                }
            )

        launch_candidates = counts["normalized"] + counts["normalization_failures"]
        normalization_rate = round(counts["normalized"] / max(1, launch_candidates), 3)
        dry_backtest = self._run_backtest(
            candidates[:limit],
            replay_source="source_parser_replay_report",
            settings=self._settings_for_profile(profile),
            persist=False,
        )
        failures = [row for row in rows if row["parser_result"] in {"missing_mint", "unsupported_shape"}]
        return {
            "artifact_type": "cryptoarc_source_parser_replay",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "limit": limit,
            "profile": profile or self.settings.strategy_profile,
            "date_from": date_from or "any",
            "date_to": date_to or "any",
            "summary": {
                "raw_events": len(events),
                "launch_candidates": launch_candidates,
                "normalized": counts["normalized"],
                "normalization_failures": counts["normalization_failures"],
                "trade_events": counts["trade_events"],
                "normalization_rate": normalization_rate,
                "parser_counts": {key.replace("parser:", ""): value for key, value in counts.items() if key.startswith("parser:")},
                "event_kind_counts": {key.replace("kind:", ""): value for key, value in counts.items() if key.startswith("kind:")},
            },
            "dry_backtest": {
                "tokens_replayed": dry_backtest.tokens_replayed,
                "paper_buys": dry_backtest.paper_buys,
                "skips": dry_backtest.skips,
                "estimated_pnl_sol": dry_backtest.estimated_pnl_sol,
                "win_rate_pct": dry_backtest.win_rate_pct,
                "profit_factor": dry_backtest.profit_factor,
                "replay_source": dry_backtest.replay_source,
            },
            "failures": failures[:50],
            "events": rows[:200],
            "operator_action": "Review parser failures and malformed source events before trusting source replay or strategy promotion.",
            "privacy_note": "Report contains raw source metadata and parser evidence only. It must not contain seed phrases, private keys, or Telegram tokens.",
        }

    def solana_logs_verification_report(self, limit: int | None = None) -> dict[str, object]:
        limit = max(1, min(5000, int(limit or 500)))
        events = self.storage.load_source_events(limit)
        direct_events = [event for event in events if event.source in {"solana_logs", "solana_logs_subscribe", "solana"}]
        portal_events = [event for event in events if event.source == "pumpportal"]
        direct_rows = [self._solana_log_evidence(event) for event in direct_events]
        portal_rows = [self._portal_source_evidence(event) for event in portal_events]
        portal_by_mint: dict[str, list[dict[str, object]]] = {}
        portal_by_signature: dict[str, list[dict[str, object]]] = {}
        for row in portal_rows:
            for mint in row["mints"]:
                portal_by_mint.setdefault(str(mint), []).append(row)
            signature = str(row.get("signature") or "")
            if signature:
                portal_by_signature.setdefault(signature, []).append(row)

        matches: list[dict[str, object]] = []
        conflicts: list[dict[str, object]] = []
        unmatched_direct: list[dict[str, object]] = []
        for row in direct_rows:
            signature = str(row.get("signature") or "")
            mints = [str(mint) for mint in row.get("mints", [])]
            signature_matches = portal_by_signature.get(signature, []) if signature else []
            mint_matches = [match for mint in mints for match in portal_by_mint.get(mint, [])]
            unique_matches = {str(match["event_id"]): match for match in [*signature_matches, *mint_matches]}
            if unique_matches:
                earliest_portal = min(unique_matches.values(), key=lambda item: str(item["received_at"]))
                lag_ms = self._iso_lag_ms(str(row["received_at"]), str(earliest_portal["received_at"]))
                matches.append(
                    {
                        "direct_event_id": row["event_id"],
                        "portal_event_ids": list(unique_matches.keys())[:10],
                        "signature": signature,
                        "mints": mints,
                        "slot": row["slot"],
                        "direct_received_at": row["received_at"],
                        "first_portal_received_at": earliest_portal["received_at"],
                        "direct_minus_portal_ms": lag_ms,
                        "match_type": "signature" if signature_matches else "mint",
                    }
                )
            elif row.get("create_hint") or mints or signature:
                unmatched_direct.append(row)
            if row.get("err"):
                conflicts.append(
                    {
                        "event_id": row["event_id"],
                        "signature": signature,
                        "slot": row["slot"],
                        "reason": "logsSubscribe notification includes a transaction error",
                        "error": row["err"],
                    }
                )

        unmatched_portal = [
            row
            for row in portal_rows
            if row["mints"] and not any(str(mint) in {candidate for direct in direct_rows for candidate in direct.get("mints", [])} for mint in row["mints"])
        ][:50]
        status = "unknown"
        if not self.solana_wss_endpoint:
            status = "not_configured"
        elif not self.solana_logs_mentions_address:
            status = "missing_mentions_address"
        elif not direct_rows:
            status = "configured_no_events"
        elif conflicts:
            status = "review"
        elif matches and unmatched_direct:
            status = "partial"
        elif matches:
            status = "matching"
        else:
            status = "no_matches"

        direct_create_hints = [row for row in direct_rows if row.get("create_hint")]
        decoded_create_rows = [row for row in direct_rows if row.get("create_evidence", {}).get("field_count", 0)]
        action_items: list[str] = []
        if not self.solana_wss_endpoint:
            action_items.append("Set SOLANA_WSS_ENDPOINT before collecting direct-chain verification evidence.")
        if self.solana_wss_endpoint and not self.solana_logs_mentions_address:
            action_items.append("Set SOLANA_LOGS_MENTIONS_ADDRESS to the Pump.fun program or related address before opening logsSubscribe.")
        if self.solana_wss_endpoint and not direct_rows:
            action_items.append("Archive solana_logs source events from logsSubscribe before comparing sources.")
        if unmatched_direct:
            action_items.append("Inspect direct Solana log events that do not match PumpPortal mints or signatures.")
        if unmatched_portal:
            action_items.append("Inspect PumpPortal launches that do not yet have direct Solana log evidence.")
        if conflicts:
            action_items.append("Review direct-chain error notifications before trusting those launches.")
        if matches:
            action_items.append("Use matched direct/PumpPortal timing as source-soak evidence, not as live execution permission by itself.")
        if direct_create_hints and not decoded_create_rows:
            action_items.append("Collect or decode Program data fields for direct create events before treating them as rich launch evidence.")

        return {
            "artifact_type": "cryptoarc_solana_logs_verification",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "limit": limit,
            "status": status,
            "configured": bool(self.solana_wss_endpoint and self.solana_logs_mentions_address),
            "wss_configured": bool(self.solana_wss_endpoint),
            "mentions_address_configured": bool(self.solana_logs_mentions_address),
            "summary": {
                "direct_events": len(direct_rows),
                "pumpportal_events": len(portal_rows),
                "direct_create_hints": len(direct_create_hints),
                "decoded_create_events": len(decoded_create_rows),
                "matches": len(matches),
                "unmatched_direct": len(unmatched_direct),
                "unmatched_pumpportal": len(unmatched_portal),
                "conflicts": len(conflicts),
            },
            "matches": matches[:50],
            "unmatched_direct": unmatched_direct[:50],
            "unmatched_pumpportal": unmatched_portal,
            "conflicts": conflicts[:50],
            "direct_events": direct_rows[:100],
            "source_soak": self._source_soak_from_verification(
                len(direct_rows),
                len(portal_rows),
                len(direct_create_hints),
                len(decoded_create_rows),
                len(matches),
                len(unmatched_direct),
                len(unmatched_portal),
                len(conflicts),
            ),
            "operator_action": "Collect direct logsSubscribe evidence and compare it with PumpPortal before using source verification for live promotion.",
            "action_items": list(dict.fromkeys(action_items)),
            "docs": {
                "solana_logs_subscribe": "https://solana.com/docs/rpc/websocket/logssubscribe",
                "subscription_limit": "one address in mentions per subscription",
            },
            "privacy_note": "Report contains public Solana signatures, slots, logs, mints, and local source timing evidence only. It must not contain seed phrases, private keys, or Telegram tokens.",
        }

    def source_soak_acceptance_report(self, limit: int | None = None, include_history: bool = True) -> dict[str, object]:
        verification = self.solana_logs_verification_report(limit=limit or 500)
        source = self.source_health()
        source_events = self.storage.count_source_events()
        soak = verification.get("source_soak", {}) if isinstance(verification.get("source_soak"), dict) else {}
        gates = [
            self._promotion_gate(
                "source_events",
                "Raw source events",
                source_events,
                ">= 100",
                source_events >= 100,
                "Collect enough raw source evidence for parser replay and soak review.",
            ),
            self._promotion_gate(
                "source_trust",
                "Source trust",
                source.get("trust_state", "unknown"),
                "trusted",
                source.get("trust_state") == "trusted",
                "Primary source trust must be trusted before source promotion.",
            ),
            self._promotion_gate(
                "direct_config",
                "Direct verifier config",
                "configured" if verification.get("configured") else verification.get("status", "not_configured"),
                "configured",
                bool(verification.get("configured")),
                "Configure SOLANA_WSS_ENDPOINT and SOLANA_LOGS_MENTIONS_ADDRESS for hybrid source verification.",
            ),
            self._promotion_gate(
                "direct_samples",
                "Direct log samples",
                verification.get("summary", {}).get("direct_events", 0),
                ">= 20",
                int(verification.get("summary", {}).get("direct_events", 0) or 0) >= 20,
                "Collect enough direct Solana log notifications for source-soak confidence.",
            ),
            self._promotion_gate(
                "direct_matches",
                "Direct/PumpPortal matches",
                f"{soak.get('matches', 0)} / {soak.get('match_rate', 0)}",
                ">= 10 and >= 60%",
                int(soak.get("matches", 0) or 0) >= 10 and float(soak.get("match_rate", 0.0) or 0.0) >= 0.6,
                "Direct Solana logs should match enough PumpPortal events by signature or mint.",
            ),
            self._promotion_gate(
                "decoded_coverage",
                "Decoded create coverage",
                soak.get("decoded_create_rate", 0.0),
                ">= 50%",
                float(soak.get("decoded_create_rate", 0.0) or 0.0) >= 0.5,
                "At least half of direct create hints should expose rich decoded create evidence.",
            ),
            self._promotion_gate(
                "direct_conflicts",
                "Direct conflicts",
                verification.get("summary", {}).get("conflicts", 0),
                "0",
                int(verification.get("summary", {}).get("conflicts", 0) or 0) == 0,
                "Direct-chain error notifications or conflicts must be reviewed before source promotion.",
            ),
        ]
        hard_required = bool(verification.get("configured")) or int(verification.get("summary", {}).get("direct_events", 0) or 0) > 0
        blockers = [str(gate["reason"]) for gate in gates if gate["status"] == "fail" and (hard_required or gate["id"] in {"source_events", "source_trust"})]
        status = "ready" if not blockers and all(gate["status"] == "pass" for gate in gates) else ("blocked" if blockers else "not_configured")
        report: dict[str, object] = {
            "artifact_type": "cryptoarc_source_soak_acceptance",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "status": status,
            "ready": status == "ready",
            "hard_required": hard_required,
            "gates": gates,
            "blockers": list(dict.fromkeys(blockers)),
            "summary": soak,
            "verification_status": verification.get("status", "unknown"),
            "operator_action": "Source-soak gate is clear for hybrid source promotion." if status == "ready" else "Collect matched direct/PumpPortal evidence before relying on hybrid source verification.",
            "privacy_note": "Source-soak acceptance contains public source timing, signature, mint, and local quality evidence only. It must not contain seed phrases, private keys, or Telegram tokens.",
        }
        if include_history:
            history = self.storage.load_source_soak_history(20)
            report["history"] = history
            report["history_summary"] = self._source_soak_history_summary(history)
        return report

    def record_source_soak_snapshot(self, limit: int | None = None) -> dict[str, object]:
        report = self.source_soak_acceptance_report(limit=limit or 500, include_history=False)
        created_at = str(report.get("generated_at") or utc_now().isoformat())
        snapshot = {
            **report,
            "id": f"source_soak_{created_at.replace(':', '').replace('.', '').replace('+', 'Z')}",
            "created_at": created_at,
            "operator_action": "Source-soak snapshot saved. Use the history trend to prove sustained direct/PumpPortal agreement before promotion.",
        }
        self.storage.save_source_soak_snapshot(snapshot)
        history = self.storage.load_source_soak_history(20)
        snapshot["history"] = history
        snapshot["history_summary"] = self._source_soak_history_summary(history)
        self.add_event("info", f"Source-soak snapshot recorded: {snapshot.get('status', 'unknown')}")
        return snapshot

    def _source_soak_history_summary(self, history: list[dict[str, object]]) -> dict[str, object]:
        recent_ready_window_hours = 24.0
        ready_sessions = [item for item in history if bool(item.get("ready"))]
        blocked_sessions = [item for item in history if str(item.get("status", "")) == "blocked"]
        match_rates: list[float] = []
        decoded_rates: list[float] = []
        direct_events = 0
        for item in history:
            summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
            try:
                match_rates.append(float(summary.get("match_rate", 0.0) or 0.0))
            except (TypeError, ValueError):
                match_rates.append(0.0)
            try:
                decoded_rates.append(float(summary.get("decoded_create_rate", 0.0) or 0.0))
            except (TypeError, ValueError):
                decoded_rates.append(0.0)
            try:
                direct_events += int(summary.get("direct_events", 0) or 0)
            except (TypeError, ValueError):
                direct_events += 0
        latest = history[0] if history else None
        latest_ready = ready_sessions[0] if ready_sessions else None
        latest_ready_created_at = str(latest_ready.get("created_at") or latest_ready.get("generated_at") or "") if latest_ready else ""
        latest_ready_at = self._parse_iso_datetime(latest_ready_created_at) if latest_ready_created_at else None
        latest_ready_age_hours = round(max(0.0, (utc_now() - latest_ready_at).total_seconds() / 3600), 2) if latest_ready_at else None
        latest_ready_recent = latest_ready_age_hours is not None and latest_ready_age_hours <= recent_ready_window_hours
        return {
            "snapshots": len(history),
            "ready_snapshots": len(ready_sessions),
            "blocked_snapshots": len(blocked_sessions),
            "latest_status": latest.get("status") if latest else "none",
            "latest_ready": bool(latest.get("ready")) if latest else False,
            "latest_created_at": latest.get("created_at") if latest else None,
            "latest_ready_created_at": latest_ready_created_at or None,
            "latest_ready_age_hours": latest_ready_age_hours,
            "latest_ready_recent": latest_ready_recent,
            "recent_ready_window_hours": recent_ready_window_hours,
            "average_match_rate": round(sum(match_rates) / max(1, len(match_rates)), 3) if match_rates else 0.0,
            "average_decoded_create_rate": round(sum(decoded_rates) / max(1, len(decoded_rates)), 3) if decoded_rates else 0.0,
            "direct_events_recorded": direct_events,
            "operator_action": "Record snapshots after meaningful soak windows so acceptance can be audited across sessions.",
        }

    def _source_soak_from_verification(
        self,
        direct_events: int,
        pumpportal_events: int,
        direct_create_hints: int,
        decoded_create_events: int,
        matches: int,
        unmatched_direct: int,
        unmatched_pumpportal: int,
        conflicts: int,
    ) -> dict[str, object]:
        match_rate = round(matches / max(1, direct_events), 3) if direct_events else 0.0
        decoded_rate = round(decoded_create_events / max(1, direct_create_hints), 3) if direct_create_hints else 0.0
        return {
            "direct_events": direct_events,
            "pumpportal_events": pumpportal_events,
            "direct_create_hints": direct_create_hints,
            "decoded_create_events": decoded_create_events,
            "matches": matches,
            "match_rate": match_rate,
            "decoded_create_rate": decoded_rate,
            "unmatched_direct": unmatched_direct,
            "unmatched_pumpportal": unmatched_pumpportal,
            "conflicts": conflicts,
            "target": {
                "direct_events": ">= 20",
                "matches": ">= 10",
                "match_rate": ">= 0.60",
                "decoded_create_rate": ">= 0.50",
                "conflicts": 0,
            },
        }

    def _solana_log_evidence(self, event: SourceEvent) -> dict[str, object]:
        payload = event.raw_payload or {}
        params = payload.get("params")
        result = params.get("result", {}) if isinstance(params, dict) else payload.get("result", {})
        if not isinstance(result, dict):
            result = payload
        payload_context = payload.get("context", {})
        context = result.get("context", {}) if isinstance(result.get("context"), dict) else payload_context
        value = result.get("value", {}) if isinstance(result.get("value"), dict) else payload.get("value", {})
        if not isinstance(value, dict):
            value = payload
        logs = value.get("logs") or payload.get("logs") or []
        if not isinstance(logs, list):
            logs = [str(logs)]
        log_rows = [str(log) for log in logs]
        signature = str(value.get("signature") or payload.get("signature") or payload.get("transaction_signature") or "").strip()
        slot = context.get("slot") if isinstance(context, dict) else payload.get("slot")
        err = value.get("err") if "err" in value else payload.get("err")
        mints = list(dict.fromkeys([*self._candidate_mints_from_payload(payload), *self._candidate_mints_from_text("\n".join(log_rows))]))
        create_hint = self._logs_have_create_hint(log_rows)
        create_evidence = self._solana_create_evidence(payload, log_rows, mints)
        return {
            "event_id": event.id,
            "received_at": event.received_at.isoformat(),
            "signature": signature,
            "slot": slot or "",
            "err": err,
            "mints": mints,
            "create_hint": create_hint,
            "create_evidence": create_evidence,
            "logs_count": len(log_rows),
            "logs_excerpt": log_rows[:8],
            "parser_result": "create_hint" if create_hint else ("signature_only" if signature else "unclassified"),
            "message": event.message,
        }

    def _portal_source_evidence(self, event: SourceEvent) -> dict[str, object]:
        payload = event.raw_payload or {}
        signature = str(payload.get("signature") or payload.get("txSignature") or payload.get("tx") or payload.get("transaction_signature") or "").strip()
        return {
            "event_id": event.id,
            "received_at": event.received_at.isoformat(),
            "signature": signature,
            "mints": self._candidate_mints_from_payload(payload),
            "status": event.status,
            "event_kind": event.to_dict().get("event_kind", "unknown"),
        }

    def _candidate_mints_from_payload(self, payload: dict[str, object]) -> list[str]:
        mints: list[str] = []
        for key in ("mint", "tokenMint", "token", "ca", "normalized_mint"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                mints.append(value.strip())
        text_parts: list[str] = []
        for key in ("logs", "message", "log", "instruction"):
            value = payload.get(key)
            if isinstance(value, list):
                text_parts.extend(str(item) for item in value)
            elif value:
                text_parts.append(str(value))
        text = "\n".join(text_parts)
        for match in re.finditer(r"(?i)(?:mint|tokenMint|token|ca)\s*[:= ]\s*([1-9A-HJ-NP-Za-km-z]{8,64})", text):
            mints.append(match.group(1))
        return list(dict.fromkeys(mints))

    def _candidate_mints_from_text(self, text: str) -> list[str]:
        return list(
            dict.fromkeys(
                match.group(1)
                for match in re.finditer(r"(?i)(?:mint|tokenMint|token|ca)\s*[:= ]\s*([1-9A-HJ-NP-Za-km-z]{8,64})", text)
            )
        )

    def _solana_create_evidence(self, payload: dict[str, object], logs: list[str], mints: list[str]) -> dict[str, object]:
        text = "\n".join(logs)
        decoded_program_data = self._decoded_program_data_strings(logs)
        combined = "\n".join([text, *decoded_program_data])
        fields: dict[str, str] = {}
        patterns = {
            "name": r"(?i)(?:name|tokenName)\s*[:=]\s*([^\n\r,|]{2,80}?)(?=\s+(?:symbol|ticker|uri|metadataUri|metadata_uri|creator|user|owner|traderPublicKey|bondingCurveKey|bondingCurve|bonding_curve|mint|tokenMint)\s*[:=]|\s*$)",
            "symbol": r"(?i)(?:symbol|ticker)\s*[:=]\s*([A-Za-z0-9_$.-]{1,16})",
            "metadata_uri": r"(?i)(?:uri|metadataUri|metadata_uri)\s*[:=]\s*(https?://[^\s,|]+|ipfs://[^\s,|]+)",
            "creator": r"(?i)(?:creator|user|owner|traderPublicKey)\s*[:= ]\s*([1-9A-HJ-NP-Za-km-z]{8,64})",
            "bonding_curve": r"(?i)(?:bondingCurveKey|bondingCurve|bonding_curve)\s*[:= ]\s*([1-9A-HJ-NP-Za-km-z]{8,64})",
            "mint": r"(?i)(?:mint|tokenMint|token|ca)\s*[:= ]\s*([1-9A-HJ-NP-Za-km-z]{8,64})",
        }
        for field, pattern in patterns.items():
            match = re.search(pattern, combined)
            if match:
                fields[field] = match.group(1).strip().strip('"').strip("'")
        if mints and "mint" not in fields:
            fields["mint"] = mints[0]
        field_count = len(fields)
        confidence = round(min(1.0, 0.2 + field_count * 0.16 + (0.12 if decoded_program_data else 0.0)), 2) if field_count else 0.0
        missing = [field for field in ("mint", "name", "symbol", "metadata_uri", "creator", "bonding_curve") if field not in fields]
        return {
            "fields": fields,
            "field_count": field_count,
            "missing_fields": missing,
            "confidence": confidence,
            "program_data_decoded": bool(decoded_program_data),
            "program_data_text": decoded_program_data[:3],
            "operator_action": "Direct create metadata is rich enough for comparison." if confidence >= 0.65 else "Keep direct create evidence as a timing/log hint until more fields decode.",
        }

    def _decoded_program_data_strings(self, logs: list[str]) -> list[str]:
        decoded: list[str] = []
        for log in logs:
            match = re.search(r"(?i)Program data:\s*([A-Za-z0-9+/=_-]{12,})", log)
            if not match:
                continue
            encoded = match.group(1).strip()
            variants = [encoded]
            if "-" in encoded or "_" in encoded:
                variants.append(encoded.replace("-", "+").replace("_", "/"))
            for variant in variants:
                padded = variant + ("=" * ((4 - len(variant) % 4) % 4))
                try:
                    raw = base64.b64decode(padded, validate=False)
                except Exception:
                    continue
                text = raw.decode("utf-8", errors="ignore")
                cleaned = "".join(char if char.isprintable() or char in "\n\r\t" else " " for char in text)
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                if cleaned:
                    decoded.append(cleaned[:500])
                    break
        return decoded

    def _logs_have_create_hint(self, logs: list[str]) -> bool:
        text = "\n".join(logs).lower()
        return any(marker in text for marker in ("initialize mint", "create", "mintto", "createpool", "create pool", "instruction: create"))

    def _direct_solana_token_from_event(self, event: LaunchEvent) -> TokenSignal | None:
        if event.source not in {"solana_logs", "solana_logs_subscribe", "solana"}:
            return None
        if not self.settings.direct_solana_paper_enabled:
            return None
        synthetic = SourceEvent(
            id="src_direct_candidate",
            source=event.source,
            received_at=event.received_at,
            raw_payload=event.raw_payload,
            status="raw",
            message=event.message,
        )
        evidence = self._solana_log_evidence(synthetic)
        if evidence.get("err"):
            return None
        if not evidence.get("create_hint"):
            return None
        create_evidence = evidence.get("create_evidence") if isinstance(evidence.get("create_evidence"), dict) else {}
        fields = create_evidence.get("fields") if isinstance(create_evidence.get("fields"), dict) else {}
        confidence = float(create_evidence.get("confidence", 0.0) or 0.0)
        if confidence < self.settings.direct_solana_min_confidence:
            return None
        mint = str(fields.get("mint") or next(iter(evidence.get("mints", []) or []), "")).strip()
        if not mint:
            return None
        if any(existing.mint == mint for existing in self.storage.load_all_tokens(5000)):
            return None
        symbol = str(fields.get("symbol") or mint[:5]).strip().upper()[:12]
        name = str(fields.get("name") or symbol).strip()[:80]
        creator = str(fields.get("creator") or "unknown").strip()[:80]
        metadata_uri = str(fields.get("metadata_uri") or "").strip()
        bonding_curve = str(fields.get("bonding_curve") or "").strip()
        metadata_score = round(min(1.0, max(0.35, confidence)), 2)
        token = TokenSignal(
            id=new_id("tok"),
            symbol=symbol or mint[:5].upper(),
            name=name or symbol or mint[:5].upper(),
            mint=mint,
            creator=creator or "unknown",
            detected_at=event.received_at,
            status=TokenStatus.DETECTED,
            age_seconds=0,
            buy_velocity=0.25,
            sell_pressure=0.08,
            metadata_score=metadata_score,
            current_price=0.00003,
        )
        token.bonding_curve = bonding_curve
        token.metadata_uri = metadata_uri
        token.price_source = "direct_solana_derived"
        token.price_confidence = round(min(0.7, confidence), 2)
        token.intelligence_tags.extend(["direct solana create", "paper-only source"])
        token.decision_log.append(
            f"Normalized from direct Solana logsSubscribe create evidence at confidence {confidence:.2f}; paper-only until source-soak gates pass."
        )
        return token

    def _iso_lag_ms(self, later_iso: str, earlier_iso: str) -> int | None:
        try:
            later = datetime.fromisoformat(later_iso)
            earlier = datetime.fromisoformat(earlier_iso)
        except ValueError:
            return None
        return int((later - earlier).total_seconds() * 1000)

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
            profile_pnls: list[float] = []
            for token in candidates:
                decision = self.risk.evaluate(token, settings, BotStats(), open_positions=0)
                if decision.allowed:
                    buys += 1
                    trade_pnl = token.pnl_sol if token.pnl_sol is not None else self._observed_replay_pnl(token, settings) + abs(offset) / 2000
                    pnl += trade_pnl
                    profile_pnls.append(trade_pnl)
                    gross_wins += 1 if trade_pnl > 0 else 0
                    outcome = self._classify_pnl(trade_pnl)
                    wins += 1 if outcome == "win" else 0
                    losses += 1 if outcome == "loss" else 0
                    scratches += 1 if outcome == "scratch" else 0
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
                "max_drawdown_sol": self._peak_to_trough_drawdown_sol(profile_pnls),
                "estimated_pnl_sol": round(pnl, 6),
            })
        run.comparison = comparison
        run.determinism_fingerprint = self._backtest_run_fingerprint(run, candidates, settings)
        self.storage.save_backtest_run(run)
        return run

    def _run_backtest(self, candidates: list[TokenSignal], replay_source: str, settings: BotSettings | None = None, persist: bool = True) -> BacktestRun:
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
        trades: list[dict[str, object]] = []
        for token in candidates:
            replay_token = self._replay_launch_candidate(token)
            if not replay_token.score:
                self.enrich_token_intelligence(replay_token)
                score = self.scoring.score(replay_token, settings)
                replay_token.score = score.score
                replay_token.reason = score.reason
                replay_token.score_breakdown = score.breakdown
            decision = self.risk.evaluate(replay_token, settings, replay_stats, open_positions=0)
            if decision.allowed:
                buys += 1
                pnl = replay_token.pnl_sol if replay_token.pnl_sol is not None else self._observed_replay_pnl(replay_token, settings)
                simulated_pnl = round(simulated_pnl + pnl, 6)
                pnl_curve.append(simulated_pnl)
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
                trades.append({"token_id": token.id, "symbol": token.symbol, "decision": "buy", "reason": replay_token.reason, "score": replay_token.score, "pnl_sol": round(pnl, 6)})
            else:
                skips += 1
                trades.append({"token_id": token.id, "symbol": token.symbol, "decision": "skip", "reason": decision.reason, "score": replay_token.score, "pnl_sol": 0})
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
            max_drawdown_sol=self._peak_to_trough_drawdown_sol(
                [float(item.get("pnl_sol", 0.0) or 0.0) for item in trades if item.get("decision") == "buy"]
            ),
            profit_factor=round(gross_win / gross_loss, 2) if gross_loss else 0.0,
            avg_hold_seconds=int(sum((token.hold_duration_seconds or 0) for token in candidates) / max(1, len(candidates))),
            best_trade_sol=round(max([float(item.get("pnl_sol", 0) or 0) for item in trades if item.get("decision") == "buy"], default=0.0), 6),
            worst_trade_sol=round(min([float(item.get("pnl_sol", 0) or 0) for item in trades if item.get("decision") == "buy"], default=0.0), 6),
            pnl_curve=pnl_curve[-120:],
            trades=trades[:120],
            replay_source=replay_source,
        )
        run.determinism_fingerprint = self._backtest_run_fingerprint(run, candidates, settings)
        if persist:
            self.backtest_runs.appendleft(run)
            self.storage.save_backtest_run(run)
        return run

    def _replay_launch_candidate(self, token: TokenSignal) -> TokenSignal:
        return replace(token, age_seconds=0)

    def _backtest_run_fingerprint(self, run: BacktestRun, candidates: list[TokenSignal], settings: BotSettings) -> str:
        candidate_rows = [
            {
                "mint": token.mint,
                "symbol": token.symbol,
                "creator": token.creator,
                "detected_at": token.detected_at.isoformat(),
                "status": str(token.status),
                "score": token.score,
                "reason": token.reason,
                "pnl_sol": round(float(token.pnl_sol or 0.0), 9) if token.pnl_sol is not None else None,
                "current_price": round(float(token.current_price or 0.0), 12),
                "metadata_score": round(float(token.metadata_score or 0.0), 6),
                "buy_velocity": round(float(token.buy_velocity or 0.0), 6),
                "sell_pressure": round(float(token.sell_pressure or 0.0), 6),
                "hold_duration_seconds": token.hold_duration_seconds,
            }
            for token in candidates
        ]
        trade_rows = [
            {
                "symbol": item.get("symbol"),
                "decision": item.get("decision"),
                "reason": item.get("reason"),
                "score": item.get("score"),
                "pnl_sol": item.get("pnl_sol"),
            }
            for item in run.trades
        ]
        payload = {
            "engine": "cryptoarc-backtest-v1",
            "profile": run.profile,
            "risk_tolerance": run.risk_tolerance,
            "replay_source": run.replay_source,
            "settings": {
                "strategy_profile": settings.strategy_profile,
                "risk_tolerance": settings.risk_tolerance,
                "score_threshold": settings.score_threshold,
                "take_profit_pct": settings.take_profit_pct,
                "stop_loss_pct": settings.stop_loss_pct,
                "max_hold_time_seconds": settings.max_hold_time_seconds,
                "minimum_hold_time_seconds": settings.minimum_hold_time_seconds,
                "paper_fee_bps": settings.paper_fee_bps,
                "paper_price_impact_pct": settings.paper_price_impact_pct,
                "paper_failed_fill_pct": settings.paper_failed_fill_pct,
                "trailing_stop_enabled": settings.trailing_stop_enabled,
                "trailing_stop_pct": settings.trailing_stop_pct,
            },
            "metrics": {
                "tokens_replayed": run.tokens_replayed,
                "paper_buys": run.paper_buys,
                "skips": run.skips,
                "wins": run.wins,
                "losses": run.losses,
                "scratches": run.scratches,
                "estimated_pnl_sol": run.estimated_pnl_sol,
                "max_drawdown_sol": run.max_drawdown_sol,
                "profit_factor": run.profit_factor,
                "pnl_curve": run.pnl_curve,
            },
            "comparison": run.comparison,
            "candidates": candidate_rows,
            "trades": trade_rows,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def backtests(self) -> list[dict[str, object]]:
        return [run.to_dict() for run in self.backtest_runs]

    def source_events(self, limit: int = 80, status: str = "", mint: str = "", source: str = "", event_kind: str = "", parser_result: str = "") -> list[dict[str, object]]:
        events = self.storage.load_source_events(max(1, min(1000, limit)))
        normalized_status = status.strip().lower()
        normalized_mint = mint.strip().lower()
        normalized_source = source.strip().lower()
        normalized_kind = event_kind.strip().lower()
        normalized_parser = parser_result.strip().lower()
        if normalized_status:
            events = [event for event in events if event.status.lower() == normalized_status]
        if normalized_source:
            events = [event for event in events if event.source.lower() == normalized_source]
        if normalized_mint:
            events = [event for event in events if normalized_mint in (self._source_event_mint(event).lower())]
        rows = [event.to_dict() for event in events]
        if normalized_kind:
            rows = [event for event in rows if str(event.get("event_kind", "")).lower() == normalized_kind]
        if normalized_parser:
            rows = [event for event in rows if str(event.get("parser_result", "")).lower() == normalized_parser]
        return rows

    def trades(self, limit: int = 300) -> list[dict[str, object]]:
        return [trade.to_dict() for trade in self.storage.load_trades(limit)]

    def monitor_tokens(self) -> list[dict[str, object]]:
        return [token.to_dict() for token in self._snapshot_tokens()]

    def market_sol_usd(self) -> dict[str, object]:
        now = utc_now()
        if self.sol_usd_price > 0 and self.sol_usd_price_updated_at and (now - self.sol_usd_price_updated_at).total_seconds() < 60:
            return {
                "symbol": "SOL",
                "currency": "USD",
                "price": round(self.sol_usd_price, 4),
                "updated_at": self.sol_usd_price_updated_at.isoformat(),
                "source": "coingecko",
                "stale": False,
                "error": "",
            }
        sources = [
            (
                "coingecko",
                "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
                lambda body: float((body.get("solana") or {}).get("usd") or 0.0),
            ),
            (
                "coinbase",
                "https://api.coinbase.com/v2/prices/SOL-USD/spot",
                lambda body: float((body.get("data") or {}).get("amount") or 0.0),
            ),
            (
                "binance",
                "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT",
                lambda body: float(body.get("price") or 0.0),
            ),
        ]
        errors: list[str] = []
        for source, url, parser in sources:
            try:
                request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "CryptoARC-v2"})
                with urllib.request.urlopen(request, timeout=4) as response:
                    body = json.loads(response.read().decode("utf-8"))
                price = parser(body)
                if price <= 0:
                    raise RuntimeError("SOL/USD price unavailable")
                self.sol_usd_price = price
                self.sol_usd_price_updated_at = now
                return {
                    "symbol": "SOL",
                    "currency": "USD",
                    "price": round(price, 4),
                    "updated_at": now.isoformat(),
                    "source": source,
                    "stale": False,
                    "error": "",
                }
            except Exception as exc:
                errors.append(f"{source}: {exc.__class__.__name__}: {exc}")
        return {
            "symbol": "SOL",
            "currency": "USD",
            "price": round(self.sol_usd_price, 4),
            "updated_at": self.sol_usd_price_updated_at.isoformat() if self.sol_usd_price_updated_at else None,
            "source": "cache" if self.sol_usd_price > 0 else "unavailable",
            "stale": True,
            "error": "; ".join(errors),
        }

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
        quality_events = len(normalized) + failures
        now = utc_now()
        last_age = None
        if self.source_status.last_event_at:
            last_age = max(0, int((now - self.source_status.last_event_at).total_seconds()))
        requested_at = self.source_status.connection_requested_at
        connected_at = self.source_status.connected_at
        first_event_at = self.source_status.first_event_at
        if requested_at and first_event_at and first_event_at < requested_at:
            first_event_at = None
        startup_ms = None
        if requested_at and connected_at:
            startup_ms = max(0, int((connected_at - requested_at).total_seconds() * 1000))
        elif requested_at and self.source_status.status in {"connecting", "reconnecting"}:
            startup_ms = max(0, int((now - requested_at).total_seconds() * 1000))
        first_event_ms = None
        if requested_at and first_event_at:
            first_event_ms = max(0, int((first_event_at - requested_at).total_seconds() * 1000))
        ratio = len(normalized) / max(1, quality_events)
        expects_live_source = self.status.value == "running" and self.settings.detect_new_tokens
        source_is_idle = (
            self.source_status.status == "offline"
            and self.source_status.message == "Source is idle"
            and not expects_live_source
        )
        recent_source_fresh = (
            expects_live_source
            and last_age is not None
            and last_age <= self.settings.source_stale_seconds
        )
        source_is_starting = (
            expects_live_source
            and self.source_status.status in {"connecting", "reconnecting"}
            and self.source_status.last_event_at is None
            and self.source_status.reconnect_attempts <= self.settings.source_max_reconnects
        )
        health = 100
        if self.source_status.status != "connected" and not source_is_idle:
            health -= 15 if recent_source_fresh or source_is_starting else 35
        if expects_live_source and last_age is not None and last_age > self.settings.source_stale_seconds:
            health -= 25
        if quality_events and ratio < 0.35:
            health -= 20
        reconnect_attempts_for_score = self.source_status.reconnect_attempts if self.source_status.status != "connected" and not recent_source_fresh else 0
        health -= min(20, max(0, reconnect_attempts_for_score - self.settings.source_max_reconnects) * 4)
        if source_is_idle and not expects_live_source:
            health = 100
        newest_normalized = normalized[0] if normalized else None
        cutoff = utc_now() - timedelta(minutes=1)
        recent_events = [event for event in events if event.received_at >= cutoff]
        recent_normalized = [event for event in recent_events if event.status == "normalized"]
        recent_raw = [event for event in recent_events if event.status == "raw" and not self._source_event_is_operational_status(event)]
        status_message = "healthy"
        if source_is_idle:
            status_message = "idle"
        if health < 50:
            status_message = "degraded"
        if self.source_status.status != "connected" and not source_is_idle and source_is_starting:
            status_message = "connecting"
        elif self.source_status.status != "connected" and not source_is_idle and recent_source_fresh:
            status_message = "reconnecting"
        elif self.source_status.status != "connected" and not source_is_idle:
            status_message = "offline"
        trust = self._source_trust_snapshot(
            events=events,
            health_score=max(0, min(100, health)),
            normalized_ratio=ratio,
            last_age=last_age,
            source_is_idle=source_is_idle,
            expects_live_source=expects_live_source,
            status_message=status_message,
        )
        return {
            "status": self.source_status.status,
            "events_per_minute": round(len(recent_events), 2),
            "normalized_ratio": round(ratio, 3),
            "recent_normalized_ratio": round(len(recent_normalized) / max(1, len(recent_normalized) + len(recent_raw)), 3),
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
            "connection": {
                "state": self.source_status.status,
                "requested_at": requested_at.isoformat() if requested_at else None,
                "connected_at": connected_at.isoformat() if connected_at else None,
                "first_event_at": first_event_at.isoformat() if first_event_at else None,
                "startup_ms": startup_ms,
                "first_event_ms": first_event_ms,
                "message": self.source_status.message,
            },
            "price_observations": self.storage.count_price_observations(),
            "strategy_decisions": self.storage.count_strategy_decisions(),
            "trade_sessions": self.storage.count_trade_sessions(),
            "reliability_note": "PumpPortal trade subscriptions rotate toward the newest launches.",
            **trust,
        }

    def source_health_report(self, limit: int = 300) -> dict[str, object]:
        limit = max(1, min(5000, int(limit or 300)))
        health = self.source_health()
        events = self.storage.load_source_events(limit)
        history = list(health.get("quality_history", [])) if isinstance(health.get("quality_history"), list) else []
        populated = [bucket for bucket in history if int(bucket.get("events", 0) or 0) > 0]
        degraded = [bucket for bucket in populated if str(bucket.get("trust_state", "")) in {"degraded", "conflicting"}]
        status_counts = Counter(event.status for event in events)
        source_counts = Counter(event.source for event in events)
        parser_counts = Counter(str(event.to_dict().get("parser_result") or "unknown") for event in events)
        first_event = min((event.received_at for event in events), default=None)
        last_event = max((event.received_at for event in events), default=None)
        source_events = [event for event in self.storage.load_events(200) if event.subsystem == "source" or "source" in event.message.lower()]
        recent_rows = []
        for event in events[:50]:
            row = event.to_dict()
            row["mint"] = self._source_event_mint(event)
            recent_rows.append(row)
        status = str(health.get("trust_state") or "unknown")
        return {
            "artifact_type": "cryptoarc_source_health_history",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "limit": limit,
            "status": status,
            "ready": status == "trusted" and not health.get("live_entry_blocked"),
            "current": health,
            "history_summary": {
                "buckets": len(history),
                "active_buckets": len(populated),
                "trusted_buckets": len([bucket for bucket in populated if bucket.get("trust_state") == "trusted"]),
                "degraded_buckets": len(degraded),
                "empty_buckets": len([bucket for bucket in history if bucket.get("trust_state") == "empty"]),
                "average_normalized_ratio": round(sum(float(bucket.get("normalized_ratio", 0.0) or 0.0) for bucket in populated) / max(1, len(populated)), 3),
                "total_events": sum(int(bucket.get("events", 0) or 0) for bucket in history),
                "malformed_events": sum(int(bucket.get("malformed", 0) or 0) for bucket in history),
            },
            "event_window": {
                "first_event_at": first_event.isoformat() if first_event else None,
                "last_event_at": last_event.isoformat() if last_event else None,
                "source_event_count": len(events),
                "status_counts": dict(status_counts),
                "source_counts": dict(source_counts),
                "parser_counts": dict(parser_counts),
            },
            "recent_source_events": recent_rows,
            "recent_operator_events": [event.to_dict() for event in source_events[:30]],
            "operator_action": str(health.get("operator_action") or "Inspect source history before promotion."),
            "privacy_note": "Source health history contains raw source metadata, public mint/source evidence, and local operator events only. It must not contain seed phrases, private keys, Telegram tokens, or auth secrets.",
        }

    def _source_quality_history(self, events: list[SourceEvent], bucket_minutes: int = 15, buckets: int = 12) -> list[dict[str, object]]:
        if bucket_minutes <= 0 or buckets <= 0:
            return []
        now = utc_now()
        span = timedelta(minutes=bucket_minutes)
        start = now - span * buckets
        rows: list[dict[str, object]] = []
        for index in range(buckets):
            bucket_start = start + span * index
            bucket_end = bucket_start + span
            bucket_events = [event for event in events if bucket_start <= event.received_at < bucket_end]
            normalized = [event for event in bucket_events if event.status == "normalized"]
            raw = [event for event in bucket_events if event.status == "raw" and not self._source_event_is_operational_status(event)]
            trade = [event for event in bucket_events if event.status == "trade"]
            malformed = len(
                [
                    event
                    for event in bucket_events
                    if event.status in {"raw", "normalized", "trade"}
                    and not self._source_event_is_operational_status(event)
                    and not self._source_event_mint(event)
                ]
            )
            unique_mints = len(
                {
                    self._source_event_mint(event)
                    for event in bucket_events
                    if self._source_event_mint(event) and self._source_event_mint(event) not in PUMPPORTAL_NON_LAUNCH_MINTS
                }
            )
            quality_events = len(normalized) + len(raw)
            ratio = round(len(normalized) / max(1, quality_events), 3)
            if not bucket_events:
                trust_state = "empty"
            elif quality_events >= 10 and ratio < 0.35:
                trust_state = "conflicting"
            elif malformed:
                trust_state = "degraded"
            else:
                trust_state = "trusted"
            rows.append(
                {
                    "bucket_start": bucket_start.isoformat(),
                    "bucket_end": bucket_end.isoformat(),
                    "events": len(bucket_events),
                    "normalized": len(normalized),
                    "raw": len(raw),
                    "trade": len(trade),
                    "malformed": malformed,
                    "unique_mints": unique_mints,
                    "normalized_ratio": ratio,
                    "trust_state": trust_state,
                }
            )
        return rows

    def _source_trust_snapshot(
        self,
        events: list[SourceEvent],
        health_score: int,
        normalized_ratio: float,
        last_age: int | None,
        source_is_idle: bool,
        expects_live_source: bool,
        status_message: str,
    ) -> dict[str, object]:
        status_counts: dict[str, int] = {}
        source_counts: dict[str, int] = {}
        mint_counts: dict[str, int] = {}
        malformed = 0
        for event in events:
            status_counts[event.status] = status_counts.get(event.status, 0) + 1
            source_counts[event.source] = source_counts.get(event.source, 0) + 1
            if event.status == "trade":
                continue
            mint = self._source_event_mint(event)
            if mint in PUMPPORTAL_NON_LAUNCH_MINTS:
                continue
            if mint:
                mint_counts[mint] = mint_counts.get(mint, 0) + 1
            elif event.status in {"raw", "normalized", "trade"} and not self._source_event_is_operational_status(event):
                malformed += 1

        duplicate_mints = sorted([mint for mint, count in mint_counts.items() if count > 1])[:10]
        blockers: list[str] = []
        warnings: list[str] = []
        trust_state = "trusted"

        if source_is_idle and not events:
            trust_state = "unknown"
            warnings.append("source has not collected events yet")
        recent_source_fresh = (
            expects_live_source
            and last_age is not None
            and last_age <= self.settings.source_stale_seconds
        )
        source_is_starting = (
            expects_live_source
            and self.source_status.status in {"connecting", "reconnecting"}
            and self.source_status.last_event_at is None
            and self.source_status.reconnect_attempts <= self.settings.source_max_reconnects
        )
        if self.source_status.status != "connected" and not source_is_idle and source_is_starting:
            warnings.append("source is still in startup connection grace")
        elif self.source_status.status != "connected" and not source_is_idle and recent_source_fresh:
            warnings.append("source is reconnecting but recent events are fresh")
        elif self.source_status.status != "connected" and not source_is_idle:
            trust_state = "degraded"
            blockers.append("source is not connected")
        if expects_live_source and last_age is not None and last_age > self.settings.source_stale_seconds:
            trust_state = "stale"
            blockers.append(f"last source event is older than {self.settings.source_stale_seconds}s")
        if normalized_ratio < 0.35 and (status_counts.get("normalized", 0) + status_counts.get("raw", 0)) >= 10:
            trust_state = "conflicting" if trust_state == "trusted" else trust_state
            blockers.append("normalization ratio is below 35%")
        if health_score < 50 and trust_state == "trusted":
            trust_state = "degraded"
            blockers.append("source health score is below 50")
        if self.source_status.status != "connected" and self.source_status.reconnect_attempts > self.settings.source_max_reconnects:
            warnings.append("source reconnect attempts exceed configured tolerance")
        if malformed:
            warnings.append(f"{malformed} recent source events are missing a mint")
        if duplicate_mints:
            warnings.append("recent duplicate mint events detected")
        trade_subscription_funding_message = self.source_status.pumpportal_funding_blocked or any(
            self._is_pumpportal_funding_message(event.raw_payload, event.message)
            for event in events
        )
        if trade_subscription_funding_message:
            if self.source_status.pumpportal_funding_blocked:
                trust_state = "degraded"
                blockers.append("PumpPortal API wallet appears unfunded")
            warnings.append("PumpPortal trade subscriptions require a funded API key before shadow price observations can evaluate.")
        if trust_state == "trusted" and health_score < 70:
            trust_state = "degraded"
            warnings.append("source health score is below preferred trust threshold")
        if status_message == "idle" and events:
            warnings.append("source is idle; trust is based on historical event quality")

        live_entry_blocked = trust_state in {"degraded", "stale", "conflicting", "unknown"} and not source_is_idle
        paper_collection_allowed = trust_state in {"trusted", "degraded", "stale", "conflicting", "unknown"}
        if trust_state == "trusted":
            operator_action = "source is usable for paper collection and readiness evidence"
        elif trust_state == "unknown":
            operator_action = "collect source events before trusting strategy or live readiness"
        elif trust_state == "stale":
            operator_action = "restart or recover the source feed before live entries"
        elif trust_state == "conflicting":
            operator_action = "inspect raw source events and parser failures before promotion"
        else:
            operator_action = "stabilize source health before promotion"

        return {
            "trust_state": trust_state,
            "trust_blockers": blockers,
            "trust_warnings": warnings,
            "pumpportal_funding_blocked": trade_subscription_funding_message,
            "pumpportal_funding_message": self.source_status.pumpportal_funding_message,
            "pumpportal_funding_blocked_at": self.source_status.pumpportal_funding_blocked_at.isoformat() if self.source_status.pumpportal_funding_blocked_at else None,
            "shadow_price_observations_blocked": trade_subscription_funding_message,
            "live_entry_blocked": live_entry_blocked,
            "paper_collection_allowed": paper_collection_allowed,
            "operator_action": operator_action,
            "raw_event_inspection": {
                "recent_events": len(events),
                "status_counts": status_counts,
                "source_counts": source_counts,
                "unique_mints": len(mint_counts),
                "duplicate_mints": duplicate_mints,
                "malformed_events": malformed,
                "filterable_fields": ["limit", "status", "mint", "source", "event_kind", "parser_result"],
            },
            "quality_history": self._source_quality_history(events),
        }

    def _source_event_mint(self, event: SourceEvent) -> str:
        payload = event.raw_payload or {}
        for key in ("mint", "tokenMint", "token", "ca"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _source_event_is_operational_status(self, event: SourceEvent) -> bool:
        return event.status in {"raw", "status"} and event.source == "pumpportal" and self._is_pumpportal_funding_message(event.raw_payload, event.message)

    def settings_versions(self) -> list[dict[str, object]]:
        return [version.to_dict() for version in self.storage.load_settings_versions(50)]

    def performance_analytics(self) -> dict[str, object]:
        trades = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        tokens_by_id = {token.id: token for token in self.storage.load_all_tokens(5000)}
        paper_summary = self._performance_group("all trades", trades)
        wallet_analytics = self._wallet_performance_analytics()
        execution = self._execution_readiness_status(source=self.source_health(), strategy_promotion=None)
        execution_metrics = execution.get("metrics", {}) if isinstance(execution.get("metrics"), dict) else {}
        latest_replay = next(iter(self.storage.load_backtest_runs(1)), None)
        return {
            "summary": paper_summary,
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
            "wallets": wallet_analytics["wallets"],
            "wallet_summary": wallet_analytics["summary"],
            "mode_comparison": {
                "paper": {
                    "mode": "paper",
                    "pnl_sol": paper_summary["pnl_sol"],
                    "samples": paper_summary["count"],
                    "confidence": "paper",
                    "source": "closed paper trades",
                },
                "replay": {
                    "mode": "replay",
                    "pnl_sol": round(float(latest_replay.estimated_pnl_sol if latest_replay else 0.0), 6),
                    "samples": int(latest_replay.tokens_replayed if latest_replay else 0),
                    "confidence": "fingerprinted" if latest_replay and latest_replay.determinism_fingerprint else "missing",
                    "source": latest_replay.replay_source if latest_replay else "no replay runs",
                },
                "shadow": {
                    "mode": "shadow",
                    "pnl_sol": round(float(execution_metrics.get("shadow_estimated_pnl_sol", 0.0) or 0.0), 6),
                    "samples": int(execution_metrics.get("shadow_evaluated", 0) or 0),
                    "confidence": "shadow" if int(execution_metrics.get("shadow_evaluated", 0) or 0) else "missing",
                    "source": "dry-run live quote comparisons",
                },
                "live": {
                    "mode": "live",
                    "pnl_sol": wallet_analytics["summary"]["total_pnl_sol"],
                    "samples": wallet_analytics["summary"]["positions"],
                    "confidence": wallet_analytics["summary"]["pnl_confidence"],
                    "source": "wallet-scoped live ledger",
                },
            },
        }

    def simulation_accuracy_report(self, wallet_public_key: str = "") -> dict[str, object]:
        trades = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        quote_adjusted = [trade for trade in trades if trade.quote_adjusted_pnl_sol is not None]
        audits = self._refresh_shadow_comparisons(self._normalize_live_audits(self.storage.load_live_execution_audits(500)))
        shadow_audits = [audit for audit in audits if isinstance(audit.quote, dict) and bool(audit.quote.get("shadow_only"))]
        shadow_evaluated = [audit for audit in shadow_audits if isinstance(audit.shadow_comparison, dict) and audit.shadow_comparison.get("status") == "evaluated"]
        shadow_failed = [
            audit
            for audit in shadow_audits
            if audit.status != "ready" or audit.final_status in {"blocked", "failed"} or bool(audit.errors)
        ]
        live_ledger = self.live_ledger(wallet_public_key)
        live_positions_count = len(live_ledger.get("positions", [])) if isinstance(live_ledger.get("positions"), list) else 0
        paper_pnl = round(sum(float(trade.pnl_sol or 0.0) for trade in trades), 6)
        quote_adjusted_pnl = round(sum(float(trade.quote_adjusted_pnl_sol if trade.quote_adjusted_pnl_sol is not None else trade.pnl_sol or 0.0) for trade in trades), 6)
        shadow_pnl = round(sum(float(audit.shadow_comparison.get("estimated_pnl_sol", 0.0) or 0.0) for audit in shadow_evaluated), 6)
        live_pnl = round(float(live_ledger.get("summary", {}).get("net_pnl_sol", live_ledger.get("summary", {}).get("total_pnl_sol", 0.0)) or 0.0), 6)
        avg_shadow_latency = 0
        if shadow_evaluated:
            avg_shadow_latency = int(
                sum(float(audit.shadow_comparison.get("latency_ms", 0.0) or 0.0) for audit in shadow_evaluated) / len(shadow_evaluated)
            )
        paper_minus_shadow = round(quote_adjusted_pnl - shadow_pnl, 6) if shadow_evaluated else None
        shadow_minus_live = round(shadow_pnl - live_pnl, 6) if shadow_evaluated and live_positions_count else None
        return {
            "artifact_type": "cryptoarc_simulation_accuracy_report",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "wallet_public_key": wallet_public_key.strip(),
            "paper": {
                "samples": len(trades),
                "pnl_sol": paper_pnl,
                "quote_adjusted_samples": len(quote_adjusted),
                "quote_adjusted_pnl_sol": quote_adjusted_pnl,
                "quote_adjustment_sol": round(sum(float(trade.quote_adjustment_sol or 0.0) for trade in trades), 6),
                "shadow_quote_cost_sol": round(sum(float(trade.shadow_quote_cost_sol or 0.0) for trade in trades), 6),
            },
            "shadow": {
                "samples": len(shadow_evaluated),
                "attempts": len(shadow_audits),
                "failures": len(shadow_failed),
                "failure_rate_pct": round((len(shadow_failed) / len(shadow_audits) * 100) if shadow_audits else 0.0, 2),
                "estimated_pnl_sol": shadow_pnl,
                "avg_quote_latency_ms": avg_shadow_latency,
            },
            "live": {
                "samples": live_positions_count,
                "pnl_sol": live_pnl,
                "total_fees_sol": round(float(live_ledger.get("summary", {}).get("total_fees_sol", 0.0) or 0.0), 9),
                "pnl_confidence": str(live_ledger.get("summary", {}).get("pnl_confidence", "none")),
            },
            "error": {
                "paper_minus_shadow_sol": paper_minus_shadow,
                "shadow_minus_live_sol": shadow_minus_live,
                "paper_minus_live_sol": round(quote_adjusted_pnl - live_pnl, 6) if live_positions_count else None,
            },
            "operator_action": "Use quote-adjusted paper and shadow-vs-live error before raising real-money size.",
        }

    def _wallet_performance_analytics(self) -> dict[str, object]:
        positions = self._live_ledger_positions("")
        grouped: dict[str, list[LiveLedgerPosition]] = {}
        for position in positions:
            wallet = position.wallet_public_key or "unknown"
            grouped.setdefault(wallet, []).append(position)

        def summarize_wallet(wallet: str, items: list[LiveLedgerPosition]) -> dict[str, object]:
            scratch = self.stats.scratch_threshold_sol or 0.001
            realized = round(sum(position.realized_pnl_sol for position in items), 9)
            unrealized = round(sum(position.unrealized_pnl_sol for position in items), 9)
            total = round(realized + unrealized, 9)
            closed = [position for position in items if position.status == "closed"]
            open_positions = [position for position in items if position.status == "open"]
            pnl_samples = [position.realized_pnl_sol + position.unrealized_pnl_sol for position in items]
            wins = [pnl for pnl in pnl_samples if pnl > scratch]
            losses = [pnl for pnl in pnl_samples if pnl < -scratch]
            decisive = len(wins) + len(losses)
            needs_review = len([position for position in items if position.reconciliation_status == "needs_review"])
            stale_balance = len([position for position in items if position.status == "open" and position.balance_age_seconds is None])
            confidence_counts: dict[str, int] = {}
            for position in items:
                label = position.unrealized_pnl_confidence if position.status == "open" else position.realized_pnl_confidence
                confidence_counts[label or "unknown"] = confidence_counts.get(label or "unknown", 0) + 1
            if needs_review or stale_balance:
                confidence = "needs_review"
            elif any(label in {"estimated", "unknown"} for label in confidence_counts):
                confidence = "estimated"
            else:
                confidence = "audited"
            return {
                "wallet_public_key": wallet,
                "label": wallet[-6:] if wallet != "unknown" else wallet,
                "positions": len(items),
                "open_positions": len(open_positions),
                "closed_positions": len(closed),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate_pct": int((len(wins) / decisive) * 100) if decisive else 0,
                "cost_basis_sol": round(sum(position.cost_basis_sol for position in items), 9),
                "realized_pnl_sol": realized,
                "unrealized_pnl_sol": unrealized,
                "total_pnl_sol": total,
                "fees_sol": round(sum(position.total_fees_sol for position in items), 9),
                "priority_fees_sol": round(sum(position.total_priority_fees_sol for position in items), 9),
                "needs_review_positions": needs_review,
                "stale_balance_positions": stale_balance,
                "pnl_confidence": confidence,
                "confidence_counts": confidence_counts,
                "operator_action": "Review reconciliation and balance evidence before using this wallet for unattended entries." if confidence == "needs_review" else "Wallet performance is usable for live comparison.",
            }

        wallets = [summarize_wallet(wallet, items) for wallet, items in grouped.items()]
        wallets.sort(key=lambda item: abs(float(item["total_pnl_sol"])), reverse=True)
        total_realized = round(sum(float(item["realized_pnl_sol"]) for item in wallets), 9)
        total_unrealized = round(sum(float(item["unrealized_pnl_sol"]) for item in wallets), 9)
        total_needs_review = sum(int(item["needs_review_positions"]) for item in wallets)
        total_stale = sum(int(item["stale_balance_positions"]) for item in wallets)
        summary_confidence = "needs_review" if total_needs_review or total_stale else "estimated" if wallets else "missing"
        return {
            "wallets": wallets,
            "summary": {
                "wallets": len(wallets),
                "positions": sum(int(item["positions"]) for item in wallets),
                "open_positions": sum(int(item["open_positions"]) for item in wallets),
                "closed_positions": sum(int(item["closed_positions"]) for item in wallets),
                "realized_pnl_sol": total_realized,
                "unrealized_pnl_sol": total_unrealized,
                "total_pnl_sol": round(total_realized + total_unrealized, 9),
                "needs_review_positions": total_needs_review,
                "stale_balance_positions": total_stale,
                "pnl_confidence": summary_confidence,
            },
        }

    def tuning_suggestions(self) -> list[dict[str, object]]:
        trades = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        labels = self.storage.load_trade_labels(1000)
        ignored_tokens = {label.token_id for label in labels if label.label == "ignore_from_tuning"}
        trades = [trade for trade in trades if trade.token_id not in ignored_tokens]
        suggestions: list[dict[str, object]] = []
        if len(trades) < 8:
            return [
                self._tuning_suggestion(
                    "Collect more samples",
                    "Auto-tuning needs at least 8 closed trades before the suggestions are meaningful.",
                    "backtest_replay_limit",
                    None,
                    0.35,
                    trades,
                    evidence_trades=trades,
                    expected_benefit="Avoids overfitting settings to a tiny paper sample.",
                    overfit_risk="high",
                )
            ]

        summary = self._performance_group("all trades", trades)
        by_exit = {item["label"]: item for item in self._group_performance(trades, lambda trade: trade.exit_reason or "unknown")}
        if summary["win_rate_pct"] < 35 and not self.settings.cooldown_after_loss_enabled:
            losses = [trade for trade in trades if (trade.pnl_sol or 0) < 0]
            suggestions.append(self._tuning_suggestion("Enable loss cooldown", "Recent decisive win rate is low; pausing briefly after losses can reduce clustered bad entries.", "cooldown_after_loss_enabled", True, 0.72, trades, evidence_trades=losses, expected_benefit=f"Targets {len(losses)} recent loss samples and may reduce clustered re-entry losses.", overfit_risk="medium"))
        max_tick = by_exit.get("max position ticks")
        if max_tick and max_tick["pnl_sol"] < 0 and not self.settings.stalled_trade_exit_enabled:
            evidence = [trade for trade in trades if (trade.exit_reason or "unknown") == "max position ticks"]
            suggestions.append(self._tuning_suggestion("Try stalled-trade exit", "Max-tick exits are losing money; stalled exits can close flat trades earlier.", "stalled_trade_exit_enabled", True, 0.68, trades, evidence_trades=evidence, expected_benefit=f"Targets {max_tick['count']} max-tick exits with {float(max_tick['pnl_sol']):.6f} SOL paper PnL.", overfit_risk="medium"))
        stop_loss = by_exit.get("stop loss")
        if stop_loss and stop_loss["count"] >= 3 and self.settings.stop_loss_pct > 20:
            evidence = [trade for trade in trades if (trade.exit_reason or "unknown") == "stop loss"]
            suggestions.append(self._tuning_suggestion("Tighten stop loss", "Several trades are reaching the stop; a tighter stop may lower average loss size in paper testing.", "stop_loss_pct", max(10, round(self.settings.stop_loss_pct * 0.8, 1)), 0.61, trades, evidence_trades=evidence, expected_benefit=f"Targets {stop_loss['count']} stop-loss exits; validate lower average loss before live promotion.", overfit_risk="medium"))
        low_conf_losses = [trade for trade in trades if trade.source_price_confidence < self.settings.min_price_confidence and (trade.pnl_sol or 0) < 0]
        if len(low_conf_losses) >= 3:
            suggestions.append(self._tuning_suggestion("Raise price confidence floor", "Low-confidence price marks are contributing multiple losses.", "min_price_confidence", min(0.9, round(self.settings.min_price_confidence + 0.1, 2)), 0.64, trades, evidence_trades=low_conf_losses, expected_benefit=f"Filters {len(low_conf_losses)} low-confidence losing price samples from future entries.", overfit_risk="low"))
        if not suggestions:
            suggestions.append(self._tuning_suggestion("Keep current profile", "No single failure pattern dominates the closed trade set yet.", "strategy_profile", self.settings.strategy_profile, 0.52, trades, evidence_trades=trades, expected_benefit="Preserves the current profile until a clearer paper or shadow edge appears.", overfit_risk="medium"))
        return suggestions

    def _tuning_suggestion(
        self,
        title: str,
        reason: str,
        setting: str,
        suggested_value: object,
        confidence: float,
        all_trades: list[TradeRecord],
        *,
        evidence_trades: list[TradeRecord],
        expected_benefit: str,
        overfit_risk: str,
    ) -> dict[str, object]:
        sample_size = len(evidence_trades)
        closed_count = len(all_trades)
        evidence_pnl = round(sum(float(trade.pnl_sol or 0.0) for trade in evidence_trades), 6)
        payload: dict[str, object] = {
            "title": title,
            "reason": reason,
            "setting": setting,
            "confidence": confidence,
            "expected_benefit": expected_benefit,
            "supporting_sample_size": sample_size,
            "supporting_closed_trades": closed_count,
            "supporting_pnl_sol": evidence_pnl,
            "overfit_risk": overfit_risk,
            "requires_operator_review": True,
            "review_note": "Applying this creates a settings version and updates local settings only; review labels, sample size, and shadow evidence before live promotion.",
        }
        if suggested_value is not None:
            payload["suggested_value"] = suggested_value
        return payload

    def apply_tuning_suggestion(self, setting: str, suggested_value: object) -> dict[str, object]:
        current = asdict(self.settings)
        if setting not in current:
            raise ValueError(f"unknown setting: {setting}")
        coerced_value = self._coerce_setting_value(setting, suggested_value, current[setting])
        snapshot = self.update_settings({setting: coerced_value})
        self.add_event("info", f"Applied tuning suggestion: {setting} -> {coerced_value}")
        return {
            "setting": setting,
            "suggested_value": coerced_value,
            "snapshot": snapshot.to_dict(),
        }

    def experiments(self) -> list[dict[str, object]]:
        return [run.to_dict() for run in self.storage.load_experiment_runs(100)]

    def create_experiment(self, name: str, profile: str | None = None, limit: int | None = None, notes: str = "") -> dict[str, object]:
        clean_name = name.strip() or f"Experiment {utc_now().strftime('%H:%M:%S')}"
        result = self.backtest_v3(limit=limit or self.settings.backtest_replay_limit)
        run = ExperimentRun(
            id=new_id("exp"),
            name=clean_name,
            created_at=utc_now(),
            settings_version_id=self.current_settings_version_id,
            profile=profile or self.settings.strategy_profile,
            replay_source="backtest_v3",
            result=result,
            fingerprint=str(result.get("determinism_fingerprint", "")),
            notes=notes.strip(),
        )
        self.storage.save_experiment_run(run)
        self.add_event("info", f"Experiment saved: {run.name}")
        return run.to_dict()

    def trade_labels(self) -> list[dict[str, object]]:
        return [label.to_dict() for label in self.storage.load_trade_labels(500)]

    def trade_review_queue(self) -> dict[str, object]:
        closed = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        labels = self.storage.load_trade_labels(5000)
        latest_label_by_token: dict[str, TradeLabel] = {}
        for label in sorted(labels, key=lambda item: item.created_at):
            latest_label_by_token[label.token_id] = label
        decisions = self.storage.load_strategy_decisions(5000)
        observations = self.storage.load_price_observations(5000)
        decisions_by_token: dict[str, list[StrategyDecisionRecord]] = {}
        observations_by_token: dict[str, list[PriceObservation]] = {}
        for decision in decisions:
            decisions_by_token.setdefault(decision.token_id, []).append(decision)
        for observation in observations:
            if observation.token_id:
                observations_by_token.setdefault(observation.token_id, []).append(observation)

        def queue_item(queue_id: str, label: str, trades: list[TradeRecord], reason: str) -> dict[str, object]:
            sorted_trades = sorted(trades, key=lambda trade: trade.closed_at or trade.opened_at or utc_now(), reverse=True)
            return {
                "id": queue_id,
                "label": label,
                "count": len(sorted_trades),
                "sample_token_ids": [trade.token_id for trade in sorted_trades[:8]],
                "sample_trade_ids": [trade.id for trade in sorted_trades[:8]],
                "reason": reason,
            }

        unlabeled = [trade for trade in closed if trade.token_id not in latest_label_by_token]
        losses = [trade for trade in closed if (trade.pnl_sol or 0.0) < 0]
        bad_price = [
            trade
            for trade in closed
            if trade.source_price_confidence < 0.65
            or any(not observation.accepted for observation in observations_by_token.get(trade.token_id, []))
        ]
        long_holds = [trade for trade in closed if int(trade.hold_duration_seconds or 0) >= max(300, int(self.settings.minimum_hold_time_seconds or 0) * 3)]
        no_decision = [trade for trade in closed if not decisions_by_token.get(trade.token_id)]
        excluded = [trade for trade in closed if latest_label_by_token.get(trade.token_id) and latest_label_by_token[trade.token_id].label == "ignore_from_tuning"]
        label_counts: dict[str, int] = {}
        for label in latest_label_by_token.values():
            label_counts[label.label] = label_counts.get(label.label, 0) + 1
        queues = [
            queue_item("unlabeled", "Unlabeled", unlabeled, "Closed trades that still need an operator label."),
            queue_item("losses", "Losses", losses, "Negative-PnL trades should be reviewed before trusting tuning suggestions."),
            queue_item("bad_price_data", "Price Evidence", bad_price, "Trades with rejected or low-confidence price evidence."),
            queue_item("long_holds", "Long Holds", long_holds, "Trades whose hold time may indicate exit-rule tuning opportunities."),
            queue_item("missing_decision", "Missing Decisions", no_decision, "Trades without attached strategy decision records."),
            queue_item("ignored_from_tuning", "Ignored", excluded, "Trades intentionally excluded from tuning evidence."),
        ]
        return {
            "total_closed": len(closed),
            "labeled": len([trade for trade in closed if trade.token_id in latest_label_by_token]),
            "unlabeled": len(unlabeled),
            "label_counts": label_counts,
            "queues": queues,
            "next_queue_id": next((queue["id"] for queue in queues if int(queue["count"]) > 0 and queue["id"] != "ignored_from_tuning"), ""),
            "next_token_id": next((str(queue["sample_token_ids"][0]) for queue in queues if int(queue["count"]) > 0 and queue["sample_token_ids"] and queue["id"] != "ignored_from_tuning"), ""),
            "operator_action": "Start with unlabeled losses or bad price evidence, then apply labels before accepting tuning changes.",
            "generated_at": utc_now().isoformat(),
        }

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
        clean_name = name.strip() or f"Preset {utc_now().strftime('%H:%M:%S')}"
        preset = StrategyPreset(
            id=new_id("strat"),
            name=clean_name,
            created_at=utc_now(),
            settings=asdict(self.settings),
            description=description.strip(),
        )
        self.storage.save_strategy_preset(preset)
        self.add_event("info", f"Strategy preset saved: {clean_name}")
        return preset.to_dict()

    def monitor_pnl_summary(self, timeframe: str = "all") -> dict[str, object]:
        closed = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        filtered = self._filter_trades_by_timeframe(closed, timeframe)
        curve = self._pnl_curve(filtered)
        history = [0.0, *[float(point["pnl_sol"]) for point in curve]]
        if len(history) > 40:
            history = [0.0, *history[-39:]]
        pnl_sol = round(sum((trade.pnl_sol or 0.0) for trade in filtered), 6)
        entry_fees = round(sum(float(trade.entry_fee_sol or 0.0) for trade in filtered), 9)
        exit_fees = round(sum(float(trade.exit_fee_sol or 0.0) for trade in filtered), 9)
        return {
            "timeframe": timeframe,
            "closed_trade_count": len(filtered),
            "pnl_sol": pnl_sol,
            "entry_fees_sol": entry_fees,
            "exit_fees_sol": exit_fees,
            "total_fees_sol": round(entry_fees + exit_fees, 9),
            "history": history if history else [0.0],
        }

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
            self.storage.load_all_tokens(10000),
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
        return self.pumpfun_intelligence.summarize(
            self.storage.load_all_tokens(5000),
            self.storage.load_source_events(5000),
            self.storage.load_trades(5000),
            self.storage.load_trade_labels(5000),
        )

    def readiness_status(self) -> dict[str, object]:
        closed = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        integrity = self.data_integrity_report()
        source = self.source_health()
        price = self.price_diagnostics()
        performance = self._performance_group("all trades", closed)
        source_soak = self.source_soak_acceptance_report()
        closed_count = len(closed)
        source_events = int(integrity.get("source_events", 0))
        source_trust_blocks_entries = bool(source.get("live_entry_blocked")) or source.get("trust_state") in {"degraded", "stale", "conflicting"}
        gross_win = sum((trade.pnl_sol or 0.0) for trade in closed if (trade.pnl_sol or 0.0) > (self.stats.scratch_threshold_sol or 0.001))
        gross_loss = abs(sum((trade.pnl_sol or 0.0) for trade in closed if (trade.pnl_sol or 0.0) < -(self.stats.scratch_threshold_sol or 0.001)))
        effective_profit_factor = 99.0 if gross_win > 0 and gross_loss == 0 else float(performance.get("profit_factor", 0.0))
        out_of_sample = self._out_of_sample_strategy_evidence(self.settings.strategy_profile)

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
                "fail" if source_trust_blocks_entries else self._threshold_status(float(source.get("health_score", 0)), 70, 50),
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
                "Paper readiness does not submit transactions; live execution stays behind separate local live/autonomy gates.",
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
            "strategy_promotion": self._strategy_promotion_status(
                closed=closed,
                source_events=source_events,
                replay_confidence=int(integrity.get("replay_confidence", {}).get("score", 0)) if isinstance(integrity.get("replay_confidence"), dict) else 0,
                source=source,
                price=price,
                performance=performance,
                profit_factor=effective_profit_factor,
                out_of_sample=out_of_sample,
                source_soak=source_soak,
            ),
            "sample_size": {
                "closed_trades": closed_count,
                "source_events": source_events,
                "price_observations": int(integrity.get("price_observations", 0)),
                "strategy_decisions": int(integrity.get("strategy_decisions", 0)),
            },
            "source_soak": source_soak,
            "paper_only": True,
            "halt_on_low_readiness": self.settings.halt_on_low_readiness,
            "min_readiness_score": self.settings.min_readiness_score,
        }
        result["execution_readiness"] = self._execution_readiness_status(
            source=source,
            strategy_promotion=result["strategy_promotion"],
        )
        result["entries_allowed"] = self.readiness_halt_reason(result) is None
        return result

    def _invalidate_readiness_cache(self) -> None:
        self._cached_readiness_status = None
        self._cached_readiness_status_at = 0.0

    def _recent_readiness_status(self) -> dict[str, object]:
        now = time.perf_counter()
        cached = self._cached_readiness_status
        if cached is not None and now - self._cached_readiness_status_at <= self.READINESS_CACHE_TTL_SECONDS:
            return cached
        refreshed = self.readiness_status()
        self._cached_readiness_status = refreshed
        self._cached_readiness_status_at = time.perf_counter()
        return refreshed

    def _execution_readiness_status(
        self,
        source: dict[str, object] | None = None,
        strategy_promotion: dict[str, object] | None = None,
        env_live_enabled: bool | None = None,
        wallet_public_key: str = "",
        signer_mode: str | None = None,
    ) -> dict[str, object]:
        source = source or self.source_health()
        signer_mode = signer_mode or self.settings.live_signer_mode
        wallet_public_key = self._resolve_backend_wallet(signer_mode, wallet_public_key)
        now = utc_now()
        quote_evidence_window_hours = 24.0
        quote_evidence_cutoff = now - timedelta(hours=quote_evidence_window_hours)
        audit_history_limit = 500
        loaded_audit_rows = self.storage.load_live_execution_audits(audit_history_limit + 1)
        audit_history_truncated = len(loaded_audit_rows) > audit_history_limit
        audit_history_complete = not audit_history_truncated
        normalized_audits = self._normalize_live_audits(loaded_audit_rows[:audit_history_limit])
        calibration = self._live_landing_calibration(normalized_audits)
        audits = self._refresh_shadow_comparisons(normalized_audits)
        pipeline_latency = self._execution_pipeline_latency(audits)
        latency_summary = self._execution_latency_summary(pipeline_latency, calibration)
        all_history_quote_audits = [audit for audit in audits if isinstance(audit.quote, dict) and audit.quote.get("id")]
        current_quote_audits: list[LiveExecutionAudit] = []
        excluded_ambiguous_timestamp_quote_audits = 0
        excluded_future_timestamp_quote_audits = 0
        for audit in all_history_quote_audits:
            created_at = audit.created_at
            if created_at.tzinfo is None or created_at.utcoffset() is None:
                excluded_ambiguous_timestamp_quote_audits += 1
                continue
            if created_at > now:
                excluded_future_timestamp_quote_audits += 1
                continue
            if created_at >= quote_evidence_cutoff:
                current_quote_audits.append(audit)
        current_calibration = self._live_landing_calibration(current_quote_audits)
        current_pipeline_latency = self._execution_pipeline_latency(current_quote_audits)
        current_latency_summary = self._execution_latency_summary(current_pipeline_latency, current_calibration)
        shadow_audits = [
            audit
            for audit in all_history_quote_audits
            if isinstance(audit.shadow_comparison, dict) and audit.shadow_comparison
        ]
        current_shadow_audits = [
            audit
            for audit in current_quote_audits
            if isinstance(audit.shadow_comparison, dict) and audit.shadow_comparison
        ]
        shadow_evaluated = [audit for audit in shadow_audits if audit.shadow_comparison.get("status") == "evaluated"]
        current_shadow_evaluated = [audit for audit in current_shadow_audits if audit.shadow_comparison.get("status") == "evaluated"]
        recent_shadow_window_hours = quote_evidence_window_hours
        recent_shadow_evaluated = current_shadow_evaluated
        shadow_winners = [audit for audit in shadow_evaluated if str(audit.shadow_comparison.get("outcome", "")) == "win"]
        recent_shadow_winners = [audit for audit in recent_shadow_evaluated if str(audit.shadow_comparison.get("outcome", "")) == "win"]
        shadow_pnls = [float(audit.shadow_comparison.get("estimated_pnl_sol", 0.0) or 0.0) for audit in shadow_evaluated]
        recent_shadow_pnls = [float(audit.shadow_comparison.get("estimated_pnl_sol", 0.0) or 0.0) for audit in recent_shadow_evaluated]
        shadow_windows = [
            window
            for audit in shadow_audits
            for window in audit.shadow_comparison.get("landing_windows", [])
            if isinstance(window, dict)
        ]
        current_shadow_windows = [
            window
            for audit in current_shadow_audits
            for window in audit.shadow_comparison.get("landing_windows", [])
            if isinstance(window, dict)
        ]
        shadow_window_evaluated = [window for window in shadow_windows if window.get("status") == "evaluated"]
        shadow_window_winners = [window for window in shadow_window_evaluated if str(window.get("outcome", "")) == "win"]
        shadow_window_pnls = [float(window.get("estimated_pnl_sol", 0.0) or 0.0) for window in shadow_window_evaluated]
        submittable_quote_audits = [audit for audit in all_history_quote_audits if not bool(audit.quote.get("shadow_only"))]
        stale_quotes = [
            audit
            for audit in submittable_quote_audits
            if audit.status == "stale" or bool(audit.quote.get("stale"))
        ]
        blocked_quotes = [audit for audit in submittable_quote_audits if audit.status == "blocked"]
        ready_quotes = [
            audit
            for audit in submittable_quote_audits
            if audit.status in {"ready", "simulated", "simulation_warning"}
        ]
        submitted = [
            audit
            for audit in all_history_quote_audits
            if audit.transaction_signature or audit.status in {"submitted", "confirmed", "reconciled", "needs_review", "failed"}
        ]
        quote_health_sample = submittable_quote_audits or all_history_quote_audits
        stale_rate = round(len(stale_quotes) / len(quote_health_sample), 3) if quote_health_sample else 0.0
        blocked_rate = round(len(blocked_quotes) / len(quote_health_sample), 3) if quote_health_sample else 0.0
        current_submittable_quote_audits = [
            audit for audit in current_quote_audits if not bool(audit.quote.get("shadow_only"))
        ]
        current_quote_health_sample = current_quote_audits
        current_quote_health_sample_kind = "current_quote_audits"
        current_health = {
            audit.id: self._current_quote_health_flags(audit)
            for audit in current_quote_health_sample
        }
        current_stale_quotes = [audit for audit in current_quote_health_sample if current_health[audit.id][1]]
        current_blocked_quotes = [audit for audit in current_quote_health_sample if current_health[audit.id][2]]
        current_ready_quotes = [audit for audit in current_quote_health_sample if current_health[audit.id][3]]
        current_failed_quotes = [audit for audit in current_quote_health_sample if current_health[audit.id][4]]
        current_unhealthy_quotes = [
            audit
            for audit in current_quote_health_sample
            if current_health[audit.id][2] or current_health[audit.id][4]
        ]
        current_submittable_health = {
            audit.id: self._current_quote_health_flags(audit)
            for audit in current_submittable_quote_audits
        }
        current_submittable_stale_quotes = [
            audit
            for audit in current_submittable_quote_audits
            if current_submittable_health[audit.id][1]
        ]
        current_submittable_ready_quotes = [
            audit
            for audit in current_submittable_quote_audits
            if current_submittable_health[audit.id][3]
        ]
        current_submittable_unhealthy_quotes = [
            audit
            for audit in current_submittable_quote_audits
            if current_submittable_health[audit.id][2] or current_submittable_health[audit.id][4]
        ]
        current_submitted = [
            audit
            for audit in current_quote_audits
            if audit.transaction_signature or audit.status in {"submitted", "confirmed", "reconciled", "needs_review", "failed"}
        ]
        unresolved = [audit for audit in audits if self._is_unresolved_live_audit(audit)]
        quote_issues = self._quote_issue_taxonomy(all_history_quote_audits)
        failure_stages = self._execution_failure_stage_taxonomy(all_history_quote_audits)
        current_quote_issues = self._quote_issue_taxonomy(current_quote_health_sample, current_health=True)
        current_failure_stages = self._execution_failure_stage_taxonomy(
            current_quote_health_sample,
            current_health=True,
        )
        aware_quote_audits = [
            audit
            for audit in all_history_quote_audits
            if audit.created_at.tzinfo is not None and audit.created_at.utcoffset() is not None
        ]
        latest_quote_at = max((audit.created_at for audit in aware_quote_audits), default=None)
        latest_quote_age_seconds = round((now - latest_quote_at).total_seconds(), 3) if latest_quote_at else None
        current_latest_quote_at = max((audit.created_at for audit in current_quote_audits), default=None)
        current_latest_quote_age_seconds = (
            round((now - current_latest_quote_at).total_seconds(), 3)
            if current_latest_quote_at
            else None
        )
        current_stale_rate = (
            round(len(current_stale_quotes) / len(current_quote_health_sample), 3)
            if current_quote_health_sample
            else 0.0
        )
        current_blocked_rate = (
            round(len(current_blocked_quotes) / len(current_quote_health_sample), 3)
            if current_quote_health_sample
            else 0.0
        )
        current_unhealthy_rate = (
            round(len(current_unhealthy_quotes) / len(current_quote_health_sample), 3)
            if current_quote_health_sample
            else 0.0
        )
        current_submittable_stale_rate = (
            round(len(current_submittable_stale_quotes) / len(current_submittable_quote_audits), 3)
            if current_submittable_quote_audits
            else 0.0
        )
        current_submittable_unhealthy_rate = (
            round(len(current_submittable_unhealthy_quotes) / len(current_submittable_quote_audits), 3)
            if current_submittable_quote_audits
            else 0.0
        )
        live_submit_quote_evidence_ready = bool(
            len(current_submittable_ready_quotes) >= 5
            and current_submittable_stale_rate <= 0.25
            and current_submittable_unhealthy_rate <= 0.25
        )
        policy_blockers = self._execution_policy_blockers()
        signer = self.signer_status(signer_mode, wallet_public_key)
        strategy_can_shadow = bool(strategy_promotion.get("can_promote")) if isinstance(strategy_promotion, dict) else False
        shadow_price_observations_blocked = bool(source.get("shadow_price_observations_blocked"))
        live_blockers = self._live_execution_blockers(bool(env_live_enabled), "buy", wallet_public_key, signer_mode, autonomous=False) if env_live_enabled is not None else []
        policy_recommendation = self._execution_policy_recommendation(
            stale_rate=current_stale_rate,
            blocked_rate=current_blocked_rate,
            unhealthy_rate=current_unhealthy_rate,
            quote_issues=current_quote_issues,
            calibration=current_calibration,
            shadow_windows=current_shadow_windows,
            policy_blockers=policy_blockers,
        )
        gates = [
            self._promotion_gate("dry_run_quote_path", "Dry-run quote path", "available", "quote without submit", True, "PumpPortal local transaction quotes are stored as audits before signing or submit."),
            self._promotion_gate("quote_audit_sample", "Quote audit sample", len(current_quote_audits), ">= 5 within 24h", len(current_quote_audits) >= 5, "Collect at least five current quote attempts before speed tuning."),
            self._promotion_gate("quote_freshness", "Quote freshness", f"{round(current_stale_rate * 100, 1)}% stale", "<= 25%", bool(current_quote_health_sample) and current_stale_rate <= 0.25, "Current stale quote frequency must be low enough for fast entries."),
            self._promotion_gate("failed_quote_rate", "Failed quote rate", f"{round(current_unhealthy_rate * 100, 1)}% unhealthy", "<= 25%", bool(current_quote_health_sample) and current_unhealthy_rate <= 0.25, "Current blocked, failed, review-required, and quote-error outcomes should be rare before live shadow runs."),
            self._promotion_gate("execution_policy_caps", "Execution policy caps", "configured" if not policy_blockers else "incomplete", "caps set", not policy_blockers, "Trade size, slippage, priority fee, loss, exposure, and position caps must be explicit."),
            self._promotion_gate("source_trust", "Source trust", str(source.get("trust_state", "unknown")), "trusted", not bool(source.get("live_entry_blocked")), "Live entries need trusted or explicitly non-blocking source state."),
            self._promotion_gate("shadow_price_observations", "Shadow price observations", "blocked" if shadow_price_observations_blocked else "available", "available", not shadow_price_observations_blocked, "PumpPortal trade subscriptions require a funded API key before shadow price observations can evaluate."),
            self._promotion_gate("strategy_shadow_gate", "Strategy shadow gate", "eligible" if strategy_can_shadow else "blocked", "eligible", strategy_can_shadow, "Strategy promotion gates should pass before comparing fast live-entry shadows."),
            self._promotion_gate("signer_boundary", "Signer boundary", signer_mode, "local signer known", bool(signer.get("connected")) if wallet_public_key else True, "Execution keeps local signing boundaries visible before any submit path."),
            self._promotion_gate("audit_history_complete", "Audit history completeness", "complete" if audit_history_complete else f"truncated at {audit_history_limit}", "complete", audit_history_complete, "Audit history truncation may hide current quote failures or recovery debt, so readiness fails closed."),
            self._promotion_gate("recovery_queue", "Recovery queue", len(unresolved), "0 unresolved", len(unresolved) == 0, "Unresolved live audits must be cleared before speed tuning."),
        ]
        blockers = [str(gate["reason"]) for gate in gates if gate["status"] == "fail"]
        blockers.extend(policy_blockers)
        if live_blockers:
            blockers.extend([f"Live blocker: {blocker}" for blocker in live_blockers])
        can_shadow = not blockers
        return {
            "status": "shadow_ready" if can_shadow else "not_enough_quote_data" if not current_quote_audits else "blocked",
            "can_shadow": can_shadow,
            "can_live_submit": (
                bool(env_live_enabled)
                and can_shadow
                and live_submit_quote_evidence_ready
                and bool(signer.get("connected"))
                and not live_blockers
            ),
            "live_submit_quote_evidence_ready": live_submit_quote_evidence_ready,
            "mode": "dry_run_to_shadow",
            "quote_ttl_seconds": 30,
            "quote_evidence_window_hours": quote_evidence_window_hours,
            "audit_history_limit": audit_history_limit,
            "audit_history_truncated": audit_history_truncated,
            "audit_history_complete": audit_history_complete,
            "latest_quote_age_seconds": latest_quote_age_seconds,
            "current_latest_quote_age_seconds": current_latest_quote_age_seconds,
            "metrics": {
                "quote_attempts": len(all_history_quote_audits),
                "ready_quotes": len(ready_quotes),
                "blocked_quotes": len(blocked_quotes),
                "stale_quotes": len(stale_quotes),
                "submitted_audits": len(submitted),
                "unresolved_audits": len(unresolved),
                "stale_quote_rate": stale_rate,
                "blocked_quote_rate": blocked_rate,
                "shadow_samples": len(shadow_audits),
                "current_quote_attempts": len(current_quote_audits),
                "recent_submittable_quote_attempts": len(current_submittable_quote_audits),
                "current_quote_health_sample": len(current_quote_health_sample),
                "current_quote_health_sample_kind": current_quote_health_sample_kind,
                "current_ready_quotes": len(current_ready_quotes),
                "current_blocked_quotes": len(current_blocked_quotes),
                "current_failed_quotes": len(current_failed_quotes),
                "current_unhealthy_quotes": len(current_unhealthy_quotes),
                "current_stale_quotes": len(current_stale_quotes),
                "current_submitted_audits": len(current_submitted),
                "current_stale_quote_rate": current_stale_rate,
                "current_blocked_quote_rate": current_blocked_rate,
                "current_unhealthy_quote_rate": current_unhealthy_rate,
                "current_live_submit_quote_evidence_ready": live_submit_quote_evidence_ready,
                "current_shadow_samples": len(current_shadow_audits),
                "current_submittable_quote_health_sample": len(current_submittable_quote_audits),
                "current_submittable_ready_quotes": len(current_submittable_ready_quotes),
                "current_submittable_stale_quotes": len(current_submittable_stale_quotes),
                "current_submittable_unhealthy_quotes": len(current_submittable_unhealthy_quotes),
                "current_submittable_stale_quote_rate": current_submittable_stale_rate,
                "current_submittable_unhealthy_quote_rate": current_submittable_unhealthy_rate,
                "excluded_ambiguous_timestamp_quote_audits": excluded_ambiguous_timestamp_quote_audits,
                "excluded_future_timestamp_quote_audits": excluded_future_timestamp_quote_audits,
                "loaded_history_quote_attempts": len(all_history_quote_audits),
                "loaded_history_submittable_quote_attempts": len(submittable_quote_audits),
                "loaded_history_ready_quotes": len(ready_quotes),
                "loaded_history_blocked_quotes": len(blocked_quotes),
                "loaded_history_stale_quotes": len(stale_quotes),
                "loaded_history_submitted_audits": len(submitted),
                "loaded_history_stale_quote_rate": stale_rate,
                "loaded_history_blocked_quote_rate": blocked_rate,
                "loaded_history_shadow_samples": len(shadow_audits),
                "loaded_history_shadow_evaluated": len(shadow_evaluated),
                "loaded_history_shadow_win_rate_pct": int((len(shadow_winners) / len(shadow_evaluated)) * 100) if shadow_evaluated else 0,
                "loaded_history_shadow_estimated_pnl_sol": round(sum(shadow_pnls), 6),
                "loaded_history_shadow_landing_windows": len(shadow_windows),
                "loaded_history_shadow_landing_evaluated": len(shadow_window_evaluated),
                "loaded_history_shadow_landing_win_rate_pct": int((len(shadow_window_winners) / len(shadow_window_evaluated)) * 100) if shadow_window_evaluated else 0,
                "loaded_history_shadow_landing_best_pnl_sol": round(max(shadow_window_pnls), 6) if shadow_window_pnls else 0.0,
                "loaded_history_shadow_landing_worst_pnl_sol": round(min(shadow_window_pnls), 6) if shadow_window_pnls else 0.0,
                "shadow_evaluated": len(shadow_evaluated),
                "recent_shadow_evaluated": len(recent_shadow_evaluated),
                "recent_shadow_window_hours": recent_shadow_window_hours,
                "shadow_win_rate_pct": int((len(shadow_winners) / len(shadow_evaluated)) * 100) if shadow_evaluated else 0,
                "shadow_estimated_pnl_sol": round(sum(shadow_pnls), 6),
                "recent_shadow_win_rate_pct": int((len(recent_shadow_winners) / len(recent_shadow_evaluated)) * 100) if recent_shadow_evaluated else 0,
                "recent_shadow_estimated_pnl_sol": round(sum(recent_shadow_pnls), 6),
                "shadow_landing_windows": len(shadow_windows),
                "shadow_landing_evaluated": len(shadow_window_evaluated),
                "shadow_landing_win_rate_pct": int((len(shadow_window_winners) / len(shadow_window_evaluated)) * 100) if shadow_window_evaluated else 0,
                "shadow_landing_best_pnl_sol": round(max(shadow_window_pnls), 6) if shadow_window_pnls else 0.0,
                "shadow_landing_worst_pnl_sol": round(min(shadow_window_pnls), 6) if shadow_window_pnls else 0.0,
                "live_landing_samples": int(calibration["samples"]),
                "live_quote_to_submit_p50_ms": int(calibration["quote_to_submit_p50_ms"]),
                "live_quote_to_submit_p90_ms": int(calibration["quote_to_submit_p90_ms"]),
                "live_quote_to_submit_p99_ms": int(calibration["quote_to_submit_p99_ms"]),
                "live_submit_to_confirm_p50_ms": int(calibration["submit_to_confirm_p50_ms"]),
                "live_submit_to_confirm_p90_ms": int(calibration["submit_to_confirm_p90_ms"]),
                "live_submit_to_confirm_p99_ms": int(calibration["submit_to_confirm_p99_ms"]),
                "pipeline_samples": int(pipeline_latency["samples"]),
                "signal_to_quote_p50_ms": int(pipeline_latency["totals"]["signal_to_quote_ms"]["p50_ms"]),
                "signal_to_quote_p90_ms": int(pipeline_latency["totals"]["signal_to_quote_ms"]["p90_ms"]),
                "intent_to_quote_p50_ms": int(pipeline_latency["totals"]["intent_to_quote_ms"]["p50_ms"]),
                "intent_to_quote_p90_ms": int(pipeline_latency["totals"]["intent_to_quote_ms"]["p90_ms"]),
                "current_live_landing_samples": int(current_calibration["samples"]),
                "current_live_quote_to_submit_p50_ms": int(current_calibration["quote_to_submit_p50_ms"]),
                "current_live_quote_to_submit_p90_ms": int(current_calibration["quote_to_submit_p90_ms"]),
                "current_live_quote_to_submit_p99_ms": int(current_calibration["quote_to_submit_p99_ms"]),
                "current_live_submit_to_confirm_p50_ms": int(current_calibration["submit_to_confirm_p50_ms"]),
                "current_live_submit_to_confirm_p90_ms": int(current_calibration["submit_to_confirm_p90_ms"]),
                "current_live_submit_to_confirm_p99_ms": int(current_calibration["submit_to_confirm_p99_ms"]),
                "current_pipeline_samples": int(current_pipeline_latency["samples"]),
                "current_signal_to_quote_p50_ms": int(current_pipeline_latency["totals"]["signal_to_quote_ms"]["p50_ms"]),
                "current_signal_to_quote_p90_ms": int(current_pipeline_latency["totals"]["signal_to_quote_ms"]["p90_ms"]),
                "current_intent_to_quote_p50_ms": int(current_pipeline_latency["totals"]["intent_to_quote_ms"]["p50_ms"]),
                "current_intent_to_quote_p90_ms": int(current_pipeline_latency["totals"]["intent_to_quote_ms"]["p90_ms"]),
            },
            "policy": {
                "max_trade_sol": self.settings.live_max_trade_sol,
                "max_slippage_pct": self.settings.live_max_slippage_pct,
                "priority_fee_cap_sol": self.settings.live_priority_fee_cap_sol,
                "daily_loss_cap_sol": self.settings.live_daily_loss_cap_sol,
                "wallet_exposure_cap_sol": self.settings.live_wallet_exposure_cap_sol,
                "max_open_positions": self.settings.live_max_open_positions,
                "suggested_slippage_pct": policy_recommendation["suggested_slippage_pct"],
                "suggested_priority_fee_sol": policy_recommendation["suggested_priority_fee_sol"],
                "recommendation": policy_recommendation,
                "blockers": policy_blockers,
            },
            "latency_summary": latency_summary,
            "pipeline_latency": pipeline_latency,
            "quote_issues": quote_issues,
            "failure_stages": failure_stages,
            "landing_calibration": calibration,
            "current_latency_summary": current_latency_summary,
            "current_pipeline_latency": current_pipeline_latency,
            "current_quote_issues": current_quote_issues,
            "current_failure_stages": current_failure_stages,
            "current_landing_calibration": current_calibration,
            "gates": gates,
            "shadow_comparisons": [audit.shadow_comparison for audit in shadow_audits[:10]],
            "current_shadow_comparisons": [audit.shadow_comparison for audit in current_shadow_audits[:10]],
            "blockers": list(dict.fromkeys(blockers)),
            "operator_action": "Run dry-run quotes until the quote sample, freshness, policy, source, and recovery gates pass.",
            "generated_at": now.isoformat(),
        }

    def _execution_latency_summary(self, pipeline_latency: dict[str, object], calibration: dict[str, object]) -> dict[str, object]:
        totals = pipeline_latency.get("totals", {}) if isinstance(pipeline_latency, dict) else {}
        signal = totals.get("signal_to_quote_ms", {}) if isinstance(totals, dict) else {}
        intent = totals.get("intent_to_quote_ms", {}) if isinstance(totals, dict) else {}
        quote_submit = totals.get("quote_to_submit_ms", {}) if isinstance(totals, dict) else {}
        quote_to_submit_p50 = int(quote_submit.get("p50_ms", 0) or calibration.get("quote_to_submit_p50_ms", 0) or 0) if isinstance(quote_submit, dict) else int(calibration.get("quote_to_submit_p50_ms", 0) or 0)
        quote_to_submit_p90 = int(quote_submit.get("p90_ms", 0) or calibration.get("quote_to_submit_p90_ms", 0) or 0) if isinstance(quote_submit, dict) else int(calibration.get("quote_to_submit_p90_ms", 0) or 0)
        signal_p90 = int(signal.get("p90_ms", 0) or 0) if isinstance(signal, dict) else 0
        quote_submit_samples = int(quote_submit.get("samples", 0) or calibration.get("samples", 0) or 0) if isinstance(quote_submit, dict) else int(calibration.get("samples", 0) or 0)
        issues: list[str] = []
        if int(pipeline_latency.get("samples", 0) or 0) == 0:
            issues.append("No linked source-to-quote latency samples yet")
        if quote_submit_samples == 0:
            issues.append("No quote-to-submit timing samples yet")
        if signal_p90 and signal_p90 > 1500:
            issues.append("Signal-to-quote p90 is above 1500ms")
        if quote_to_submit_p90 and quote_to_submit_p90 > 2500:
            issues.append("Quote-to-submit p90 is above 2500ms")
        if issues:
            status = "needs_samples" if any("No " in issue for issue in issues) else "slow"
        elif signal_p90 <= 750 and quote_to_submit_p90 <= 1000:
            status = "fast"
        else:
            status = "watch"
        return {
            "status": status,
            "samples": int(pipeline_latency.get("samples", 0) or 0),
            "signal_to_quote_p50_ms": int(signal.get("p50_ms", 0) or 0) if isinstance(signal, dict) else 0,
            "signal_to_quote_p90_ms": signal_p90,
            "intent_to_quote_p50_ms": int(intent.get("p50_ms", 0) or 0) if isinstance(intent, dict) else 0,
            "intent_to_quote_p90_ms": int(intent.get("p90_ms", 0) or 0) if isinstance(intent, dict) else 0,
            "quote_to_submit_p50_ms": quote_to_submit_p50,
            "quote_to_submit_p90_ms": quote_to_submit_p90,
            "quote_to_submit_samples": quote_submit_samples,
            "issues": issues,
            "operator_action": "Collect linked source, decision, intent, quote, and submit evidence until the latency summary is fast or watch.",
        }

    def _current_quote_health_flags(self, audit: LiveExecutionAudit) -> tuple[str, bool, bool, bool, bool]:
        quote = audit.quote if isinstance(audit.quote, dict) else {}
        audit_status = str(audit.status or "").lower()
        final_status = str(audit.final_status or "").lower()
        quote_status = str(quote.get("status") or "").lower()
        audit_statuses = {
            audit_status,
            final_status,
            quote_status,
        }
        lifecycle_statuses = {
            audit_status,
            final_status,
        }
        terminal_success = bool(
            lifecycle_statuses.intersection({"confirmed", "reconciled"})
            or audit.reconciliation_status == "matched"
        )
        explicit_ready = bool(
            {audit_status, final_status}.intersection({"ready", "simulated", "simulation_warning"})
        )
        shadow_ttl_stale = bool(
            quote.get("shadow_only")
            and ("stale" in audit_statuses or bool(quote.get("stale")))
        )
        if terminal_success:
            status = "reconciled" if "reconciled" in audit_statuses or audit.reconciliation_status == "matched" else "confirmed"
        elif audit_statuses.intersection({"failed", "needs_review"}):
            status = "needs_review" if "needs_review" in audit_statuses else "failed"
        elif "blocked" in audit_statuses:
            status = "blocked"
        elif "stale" in audit_statuses or bool(quote.get("stale")):
            status = "stale"
        else:
            status = next(
                (
                    candidate
                    for candidate in (final_status, audit_status, quote_status)
                    if candidate and candidate != "pending"
                ),
                final_status or audit_status or quote_status,
            )
        is_stale = bool(
            not terminal_success
            and not bool(quote.get("shadow_only"))
            and ("stale" in audit_statuses or bool(quote.get("stale")))
        )
        is_blocked = bool(
            not terminal_success
            and "blocked" in audit_statuses
        )
        quote_error = str(quote.get("error") or "").strip()
        is_failed = bool(
            not terminal_success
            and (
                audit_statuses.intersection({"failed", "needs_review"})
                or quote_error
                or (
                    not explicit_ready
                    and not is_stale
                    and not is_blocked
                    and not shadow_ttl_stale
                )
            )
        )
        is_ready = bool(
            not is_stale
            and not is_blocked
            and not is_failed
            and (
                explicit_ready
                or terminal_success
            )
        )
        return status, is_stale, is_blocked, is_ready, is_failed

    def _quote_issue_taxonomy(
        self,
        audits: list[LiveExecutionAudit],
        *,
        current_health: bool = False,
    ) -> dict[str, object]:
        categories: dict[str, dict[str, object]] = {}
        recent: list[dict[str, object]] = []
        stale_count = 0
        blocked_count = 0
        failed_count = 0
        for audit in audits:
            quote = audit.quote if isinstance(audit.quote, dict) else {}
            if current_health:
                status, is_stale, is_blocked, _, is_failed = self._current_quote_health_flags(audit)
            else:
                status = str(audit.status or quote.get("status") or "")
                is_stale = status == "stale" or bool(quote.get("stale"))
                is_blocked = status == "blocked" or str(quote.get("status", "")) == "blocked"
                is_failed = status in {"failed", "needs_review"}
            quote_error = str(quote.get("error") or "").strip()
            reasons = [str(error).strip() for error in audit.errors if str(error).strip()]
            if quote_error:
                reasons.append(quote_error)
            if audit.last_recovery_error:
                reasons.append(audit.last_recovery_error)
            reasons = list(dict.fromkeys(reasons))
            if not current_health:
                is_failed = is_failed or bool(
                    quote_error
                    and not is_stale
                    and not is_blocked
                    and status not in {"ready", "simulated", "simulation_warning", "submitted", "confirmed", "reconciled"}
                )
            if not (is_stale or is_blocked or is_failed):
                continue
            if is_stale:
                stale_count += 1
            if is_blocked:
                blocked_count += 1
            if is_failed:
                failed_count += 1
            if not reasons:
                if is_stale:
                    reasons = ["quote expired before signing or submit"]
                elif is_blocked:
                    reasons = ["quote blocked without a recorded reason"]
                else:
                    reasons = ["quote failed without a recorded reason"]
            category = self._quote_issue_category(reasons[0], audit, is_stale=is_stale, is_blocked=is_blocked, is_failed=is_failed)
            bucket = categories.setdefault(
                category,
                {
                    "category": category,
                    "count": 0,
                    "latest_at": "",
                    "reasons": [],
                    "audit_ids": [],
                },
            )
            bucket["count"] = int(bucket["count"]) + 1
            bucket["latest_at"] = max(str(bucket["latest_at"]), audit.created_at.isoformat())
            bucket["reasons"] = list(dict.fromkeys([*bucket["reasons"], *reasons]))[:5]
            bucket["audit_ids"] = list(dict.fromkeys([*bucket["audit_ids"], audit.id]))[:10]
            recent.append(
                {
                    "audit_id": audit.id,
                    "mint": audit.mint,
                    "status": status or "unknown",
                    "category": category,
                    "reason": reasons[0],
                    "created_at": audit.created_at.isoformat(),
                }
            )
        sorted_categories = sorted(categories.values(), key=lambda item: (-int(item["count"]), str(item["category"])))
        recent.sort(key=lambda item: str(item["created_at"]), reverse=True)
        return {
            "total_issues": len(recent),
            "stale_count": stale_count,
            "blocked_count": blocked_count,
            "failed_count": failed_count,
            "categories": sorted_categories,
            "recent": recent[:10],
            "operator_action": "Review the top quote issue category before raising caps, slippage, priority fees, or signer automation.",
        }

    def _execution_failure_stage_taxonomy(
        self,
        audits: list[LiveExecutionAudit],
        *,
        current_health: bool = False,
    ) -> dict[str, object]:
        stage_order = ["quote", "simulation", "submit", "confirmation", "reconciliation"]
        stages: dict[str, dict[str, object]] = {
            stage: {"stage": stage, "count": 0, "latest_at": "", "categories": {}, "audit_ids": [], "reasons": []}
            for stage in stage_order
        }
        recent: list[dict[str, object]] = []
        for audit in audits:
            if current_health:
                status, _, _, is_ready, _ = self._current_quote_health_flags(audit)
                if is_ready and status in {"confirmed", "reconciled"}:
                    continue
            stage, reason = self._execution_failure_stage(audit)
            if not stage:
                continue
            category = self._execution_stage_failure_category(stage, reason, audit)
            bucket = stages[stage]
            bucket["count"] = int(bucket["count"]) + 1
            bucket["latest_at"] = max(str(bucket["latest_at"]), audit.created_at.isoformat())
            bucket["audit_ids"] = list(dict.fromkeys([*bucket["audit_ids"], audit.id]))[:10]
            bucket["reasons"] = list(dict.fromkeys([*bucket["reasons"], reason]))[:5]
            categories = bucket["categories"] if isinstance(bucket["categories"], dict) else {}
            categories[category] = int(categories.get(category, 0)) + 1
            bucket["categories"] = categories
            recent.append(
                {
                    "audit_id": audit.id,
                    "mint": audit.mint,
                    "action": audit.action,
                    "stage": stage,
                    "category": category,
                    "reason": reason,
                    "status": audit.final_status or audit.status,
                    "created_at": audit.created_at.isoformat(),
                }
            )

        rows: list[dict[str, object]] = []
        for stage in stage_order:
            row = stages[stage]
            categories = row["categories"] if isinstance(row["categories"], dict) else {}
            rows.append(
                {
                    **row,
                    "categories": [
                        {"category": category, "count": count}
                        for category, count in sorted(categories.items(), key=lambda item: (-int(item[1]), item[0]))
                    ],
                }
            )
        total = sum(int(row["count"]) for row in rows)
        recent.sort(key=lambda item: str(item["created_at"]), reverse=True)
        top_stage = next((row for row in rows if int(row["count"]) > 0), None)
        return {
            "total_failures": total,
            "stages": rows,
            "recent": recent[:10],
            "operator_action": (
                f"Start with the {str(top_stage['stage']).replace('_', ' ')} stage before changing execution policy."
                if top_stage
                else "No stage-level execution failures are recorded in recent audits."
            ),
        }

    def _execution_failure_stage(self, audit: LiveExecutionAudit) -> tuple[str, str]:
        quote = audit.quote if isinstance(audit.quote, dict) else {}
        simulation = audit.simulation if isinstance(audit.simulation, dict) else {}
        timing = self._audit_execution_timing(audit)
        reasons = [str(error).strip() for error in audit.errors if str(error).strip()]
        quote_error = str(quote.get("error") or "").strip()
        if quote_error:
            reasons.append(quote_error)
        if audit.last_recovery_error:
            reasons.append(audit.last_recovery_error)
        reason = next((item for item in reasons if item), "")
        status = str(audit.final_status or audit.status or quote.get("status") or "").lower()
        quote_status = str(quote.get("status") or "").lower()
        simulation_status = str(simulation.get("status") or "").lower()
        simulation_error = str(simulation.get("error") or simulation.get("warning") or "").strip()

        if status == "stale" or bool(quote.get("stale")):
            return "quote", reason or "quote expired before signing or submit"
        if status == "blocked" or quote_status == "blocked":
            return "quote", reason or "quote blocked before transaction preparation"
        if quote_error and status not in {"ready", "simulated", "simulation_warning", "submitted", "confirmed", "reconciled"}:
            return "quote", quote_error
        if simulation and (simulation_status in {"warning", "error"} or simulation_error):
            return "simulation", simulation_error or reason or "simulation returned warning or error"
        if status == "failed" and not audit.transaction_signature:
            return "submit", reason or "transaction submit failed before signature was recorded"
        if status in {"failed", "needs_review"} and audit.transaction_signature and not timing.get("confirmed_at"):
            return "confirmation", reason or "submitted transaction could not be confirmed"
        if audit.reconciliation_status == "needs_review" or (status in {"failed", "needs_review"} and timing.get("confirmed_at")):
            return "reconciliation", reason or "confirmed transaction needs ledger reconciliation review"
        return "", ""

    def _execution_stage_failure_category(self, stage: str, reason: str, audit: LiveExecutionAudit) -> str:
        text = " ".join([stage, reason, audit.status, audit.final_status, audit.reconciliation_status]).lower()
        if "stale" in text or "expired" in text:
            return "stale_or_expired"
        if "slippage" in text:
            return "slippage"
        if "priority fee" in text or "priority_fee" in text:
            return "priority_fee"
        if any(term in text for term in ("cap", "daily loss", "wallet exposure", "open position", "max trade", "amount exceeds")):
            return "cap_or_policy"
        if any(term in text for term in ("signer", "wallet", "session acknowledgement", "backend", "unattended")):
            return "signer_or_wallet"
        if "source" in text:
            return "source_trust"
        if any(term in text for term in ("rpc", "provider", "pumpportal", "http", "timeout")):
            return "provider_or_rpc"
        if stage == "simulation":
            return "simulation_warning"
        if stage == "confirmation":
            return "confirmation_unknown"
        if stage == "reconciliation":
            return "ledger_reconciliation"
        return "unknown"

    def _quote_issue_category(self, reason: str, audit: LiveExecutionAudit, *, is_stale: bool, is_blocked: bool, is_failed: bool) -> str:
        text = " ".join(
            [
                reason,
                audit.status,
                str(audit.quote.get("status", "")) if isinstance(audit.quote, dict) else "",
            ]
        ).lower()
        if is_stale or "stale" in text or "expired" in text:
            return "stale_quote"
        if "slippage" in text:
            return "slippage_policy"
        if "priority fee" in text or "priority_fee" in text:
            return "priority_fee_policy"
        if any(term in text for term in ("amount exceeds", "cap", "daily loss", "wallet exposure", "open position", "max trade")):
            return "cap_policy"
        if any(term in text for term in ("signer", "wallet", "session acknowledgement", "live_trading_enabled", "live trading enabled", "unattended", "backend")):
            return "signer_or_live_gate"
        if "source trust" in text or "source health" in text:
            return "source_trust"
        if any(term in text for term in ("pumpportal", "provider", "rpc", "http", "transaction")):
            return "provider_or_rpc"
        if "simulation" in text:
            return "simulation"
        if is_blocked:
            return "blocked_quote"
        if is_failed:
            return "failed_quote"
        return "unknown"

    def _execution_pipeline_latency(self, audits: list[LiveExecutionAudit]) -> dict[str, object]:
        tokens = self.storage.load_all_tokens(5000)
        tokens_by_mint: dict[str, list[TokenSignal]] = {}
        tokens_by_id = {token.id: token for token in tokens}
        for token in tokens:
            tokens_by_mint.setdefault(token.mint, []).append(token)
        source_events = self.storage.load_source_events(5000)
        source_by_mint: dict[str, list[SourceEvent]] = {}
        for event in source_events:
            mint = self._source_event_mint(event)
            if mint:
                source_by_mint.setdefault(mint, []).append(event)
            if event.normalized_token_id and event.normalized_token_id in tokens_by_id:
                source_by_mint.setdefault(tokens_by_id[event.normalized_token_id].mint, []).append(event)
        decisions_by_mint: dict[str, list[StrategyDecisionRecord]] = {}
        for decision in self.storage.load_strategy_decisions(5000):
            decisions_by_mint.setdefault(decision.mint, []).append(decision)
        intents_by_id = {intent.id: intent for intent in self.storage.load_live_intents(5000)}

        stages: dict[str, list[int]] = {
            "source_to_token_ms": [],
            "token_to_decision_ms": [],
            "decision_to_intent_ms": [],
            "intent_to_quote_ms": [],
            "quote_to_submit_ms": [],
            "submit_to_confirm_ms": [],
            "confirm_to_reconcile_ms": [],
            "signal_to_quote_ms": [],
            "signal_to_confirm_ms": [],
        }
        samples: list[dict[str, object]] = []
        for audit in audits:
            quote_at = self._parse_iso_datetime(str(audit.quote.get("created_at") or "")) if isinstance(audit.quote, dict) else None
            quote_at = quote_at or audit.created_at
            intent = intents_by_id.get(audit.intent_id)
            intent_at = intent.created_at if intent else self._parse_iso_datetime(str((audit.request or {}).get("created_at") or "")) if isinstance(audit.request, dict) else None
            token = self._nearest_token_for_audit(audit, tokens_by_mint.get(audit.mint, []), quote_at)
            source_event = self._nearest_source_event_for_audit(source_by_mint.get(audit.mint, []), token, quote_at)
            decision = self._nearest_decision_for_audit(decisions_by_mint.get(audit.mint, []), quote_at)
            timing = self._audit_execution_timing(audit)
            submitted_at = self._parse_iso_datetime(str(timing.get("submitted_at") or ""))
            confirmed_at = self._parse_iso_datetime(str(timing.get("confirmed_at") or ""))
            reconciled_at = audit.updated_at if audit.reconciliation_status == "matched" else None
            stage_values = {
                "source_to_token_ms": self._stage_ms(source_event.received_at if source_event else None, token.detected_at if token else None),
                "token_to_decision_ms": self._stage_ms(token.detected_at if token else None, decision.created_at if decision else None),
                "decision_to_intent_ms": self._stage_ms(decision.created_at if decision else None, intent_at),
                "intent_to_quote_ms": self._stage_ms(intent_at, quote_at),
                "quote_to_submit_ms": self._stage_ms(quote_at, submitted_at),
                "submit_to_confirm_ms": self._stage_ms(submitted_at, confirmed_at),
                "confirm_to_reconcile_ms": self._stage_ms(confirmed_at, reconciled_at),
                "signal_to_quote_ms": self._stage_ms(source_event.received_at if source_event else token.detected_at if token else None, quote_at),
                "signal_to_confirm_ms": self._stage_ms(source_event.received_at if source_event else token.detected_at if token else None, confirmed_at),
            }
            for stage, value in stage_values.items():
                if isinstance(value, int):
                    stages[stage].append(value)
            if any(isinstance(value, int) for value in stage_values.values()):
                samples.append(
                    {
                        "audit_id": audit.id,
                        "mint": audit.mint,
                        "action": audit.action,
                        "status": audit.final_status or audit.status,
                        "quoted_at": quote_at.isoformat(),
                        "source_event_id": source_event.id if source_event else "",
                        "token_id": token.id if token else "",
                        "decision_id": decision.id if decision else "",
                        "intent_id": audit.intent_id,
                        "stages": stage_values,
                    }
                )
        return {
            "samples": len(samples),
            "totals": {stage: self._latency_stage_summary(values) for stage, values in stages.items()},
            "recent_samples": samples[:10],
            "missing_evidence": {
                "source_events": len([sample for sample in samples if not sample.get("source_event_id")]),
                "tokens": len([sample for sample in samples if not sample.get("token_id")]),
                "decisions": len([sample for sample in samples if not sample.get("decision_id")]),
                "intents": len([sample for sample in samples if not sample.get("intent_id")]),
            },
        }

    def _nearest_token_for_audit(self, audit: LiveExecutionAudit, candidates: list[TokenSignal], at: datetime) -> TokenSignal | None:
        prior = [token for token in candidates if token.detected_at <= at]
        if prior:
            return max(prior, key=lambda token: token.detected_at)
        return min(candidates, key=lambda token: abs((token.detected_at - at).total_seconds()), default=None)

    def _nearest_source_event_for_audit(self, candidates: list[SourceEvent], token: TokenSignal | None, at: datetime) -> SourceEvent | None:
        if token:
            direct = [event for event in candidates if event.normalized_token_id == token.id]
            if direct:
                candidates = direct
        prior = [event for event in candidates if event.received_at <= at]
        if prior:
            return max(prior, key=lambda event: event.received_at)
        return min(candidates, key=lambda event: abs((event.received_at - at).total_seconds()), default=None)

    def _nearest_decision_for_audit(self, candidates: list[StrategyDecisionRecord], at: datetime) -> StrategyDecisionRecord | None:
        prior = [decision for decision in candidates if decision.created_at <= at]
        if prior:
            return max(prior, key=lambda decision: decision.created_at)
        return min(candidates, key=lambda decision: abs((decision.created_at - at).total_seconds()), default=None)

    def _stage_ms(self, start: datetime | None, end: datetime | None) -> int | None:
        if not start or not end:
            return None
        return max(0, int((end - start).total_seconds() * 1000))

    def _latency_stage_summary(self, values: list[int]) -> dict[str, object]:
        return {
            "samples": len(values),
            "p50_ms": self._percentile_ms(values, 0.5),
            "p90_ms": self._percentile_ms(values, 0.9),
            "p99_ms": self._percentile_ms(values, 0.99),
            "max_ms": max(values) if values else 0,
        }

    def _refresh_shadow_comparisons(self, audits: list[LiveExecutionAudit]) -> list[LiveExecutionAudit]:
        for audit in audits:
            original = json.dumps(audit.shadow_comparison, sort_keys=True) if audit.shadow_comparison else ""
            if not audit.shadow_comparison:
                audit.shadow_comparison = self._build_shadow_comparison(audit)
            if audit.shadow_comparison:
                audit.shadow_comparison = self._evaluate_shadow_comparison(audit)
            updated = json.dumps(audit.shadow_comparison, sort_keys=True) if audit.shadow_comparison else ""
            if updated != original:
                audit.updated_at = utc_now()
                self.storage.save_live_execution_audit(audit)
        return audits

    def _shadow_quote_cost_breakdown(self, audit: LiveExecutionAudit, amount_sol: float) -> dict[str, float]:
        priority_fee = float(audit.quote.get("priority_fee_sol", 0.0) or 0.0) if isinstance(audit.quote, dict) else 0.0
        fee_rate = float(self.settings.paper_fee_bps or 0.0) / 10000
        entry_fee = amount_sol * fee_rate
        exit_fee = amount_sol * fee_rate
        impact_drag = amount_sol * (float(self.settings.paper_price_impact_pct or 0.0) / 100)
        total_fee_drag = entry_fee + exit_fee
        return {
            "amount_sol": round(amount_sol, 9),
            "entry_fee_sol": round(entry_fee, 9),
            "exit_fee_sol": round(exit_fee, 9),
            "paper_fee_drag_sol": round(total_fee_drag, 9),
            "price_impact_drag_sol": round(impact_drag, 9),
            "priority_fee_sol": round(priority_fee, 9),
            "slippage_pct": round(float(audit.quote.get("slippage_pct", 0.0) or 0.0), 4) if isinstance(audit.quote, dict) else 0.0,
            "total_cost_sol": round(total_fee_drag + impact_drag + priority_fee, 9),
        }

    def _build_shadow_comparison(self, audit: LiveExecutionAudit) -> dict[str, object]:
        if audit.action != "buy" or audit.status != "ready":
            return {}
        amount_sol = self._audit_amount_sol(audit)
        costs = self._shadow_quote_cost_breakdown(audit, amount_sol)
        entry_price, entry_source, entry_at = self._shadow_price_at_or_before(audit.mint, audit.created_at)
        comparison = {
            "mode": "dry_run_shadow",
            "status": "waiting_for_price",
            "evaluation_model": "exit_rules_v1",
            "audit_id": audit.id,
            "intent_id": audit.intent_id,
            "mint": audit.mint,
            "quoted_at": audit.created_at.isoformat(),
            "would_submit_at": audit.created_at.isoformat(),
            "amount_sol": amount_sol,
            "entry_price": entry_price,
            "entry_price_source": entry_source,
            "entry_observed_at": entry_at.isoformat() if entry_at else None,
            "latest_price": None,
            "latest_price_source": "",
            "latest_observed_at": None,
            "exit_price": None,
            "exit_price_source": "",
            "exit_observed_at": None,
            "exit_reason": "",
            "hold_duration_seconds": 0,
            "landing_windows": [],
            "move_pct": None,
            "costs": costs,
            "gross_pnl_sol": 0.0,
            "cost_adjusted_pnl_sol": 0.0,
            "estimated_pnl_sol": 0.0,
            "outcome": "pending",
            "latency_ms": self._quote_latency_ms(audit),
            "rules": self._shadow_rule_snapshot(),
            "reason": "Waiting for accepted price observations after the dry-run quote.",
        }
        if not entry_price:
            comparison["status"] = "missing_entry_price"
            comparison["reason"] = "No accepted entry price is available for shadow comparison."
        return comparison

    def _evaluate_shadow_comparison(self, audit: LiveExecutionAudit) -> dict[str, object]:
        comparison = dict(audit.shadow_comparison or {})
        if not comparison or comparison.get("mode") != "dry_run_shadow":
            return comparison
        entry_price = float(comparison.get("entry_price") or 0.0)
        if entry_price <= 0:
            return comparison
        quoted_at = self._parse_iso_datetime(str(comparison.get("quoted_at") or "")) or audit.created_at
        observations = self._shadow_observations_after(audit.mint, quoted_at)
        latest_price, latest_source, latest_at = self._shadow_price_from_observation(observations[-1]) if observations else (None, "", None)
        if not latest_price or not latest_at:
            comparison["status"] = "waiting_for_price"
            comparison["reason"] = "Waiting for accepted price observations after the dry-run quote."
            return comparison
        amount_sol = float(comparison.get("amount_sol") or self._audit_amount_sol(audit))
        exit_price, exit_source, exit_at, exit_reason, partial_realized = self._shadow_exit_from_observations(entry_price, quoted_at, observations, amount_sol)
        if not exit_price or not exit_at:
            exit_price, exit_source, exit_at, exit_reason = latest_price, latest_source, latest_at, "latest observed price"
        move_pct = ((exit_price - entry_price) / max(entry_price, 0.000000001)) * 100
        costs = self._shadow_quote_cost_breakdown(audit, amount_sol)
        gross_pnl = round(partial_realized + amount_sol * (move_pct / 100), 6)
        estimated_pnl = round(gross_pnl - float(costs["total_cost_sol"]), 6)
        comparison.update(
            {
                "status": "evaluated",
                "latest_price": latest_price,
                "latest_price_source": latest_source,
                "latest_observed_at": latest_at.isoformat(),
                "exit_price": exit_price,
                "exit_price_source": exit_source,
                "exit_observed_at": exit_at.isoformat(),
                "exit_reason": exit_reason,
                "hold_duration_seconds": max(0, int((exit_at - quoted_at).total_seconds())),
                "move_pct": round(move_pct, 3),
                "costs": costs,
                "gross_pnl_sol": gross_pnl,
                "cost_adjusted_pnl_sol": estimated_pnl,
                "estimated_pnl_sol": estimated_pnl,
                "outcome": self._classify_pnl(estimated_pnl),
                "landing_windows": self._shadow_landing_windows(audit, entry_price, quoted_at),
                "reason": "Shadow outcome estimated from accepted price observations and configured exit rules; no transaction was submitted.",
            }
        )
        return comparison

    def _shadow_landing_windows(self, audit: LiveExecutionAudit, immediate_entry_price: float, quoted_at: datetime) -> list[dict[str, object]]:
        windows = []
        for delay_ms in self._shadow_delay_windows_ms():
            landing_at = quoted_at + timedelta(milliseconds=delay_ms)
            windows.append(self._shadow_landing_window(audit, immediate_entry_price, quoted_at, landing_at, delay_ms))
        return windows

    def _shadow_delay_windows_ms(self) -> list[int]:
        calibration = self._live_landing_calibration(self.storage.load_live_execution_audits(200))
        calibrated = calibration.get("suggested_delay_windows_ms", []) if isinstance(calibration, dict) else []
        return sorted({0, 250, 500, 1000, 2000, *[int(value) for value in calibrated if int(value) >= 0]})

    def _live_landing_calibration(self, audits: list[LiveExecutionAudit]) -> dict[str, object]:
        quote_to_submit: list[int] = []
        submit_to_confirm: list[int] = []
        quote_to_confirm: list[int] = []
        by_signer: dict[str, dict[str, list[int]]] = {}
        by_pool: dict[str, dict[str, list[int]]] = {}
        by_quote_source: dict[str, dict[str, list[int]]] = {}
        for audit in audits:
            timing = self._audit_execution_timing(audit)
            buckets = [
                by_signer.setdefault(str(audit.signer_mode or "unknown"), self._empty_timing_group()),
                by_pool.setdefault(self._audit_quote_pool(audit), self._empty_timing_group()),
                by_quote_source.setdefault(self._audit_quote_source(audit), self._empty_timing_group()),
            ]
            qts = timing.get("quote_to_submit_ms")
            stc = timing.get("submit_to_confirm_ms")
            qtc = timing.get("quote_to_confirm_ms")
            if isinstance(qts, int) and qts >= 0:
                quote_to_submit.append(qts)
                for bucket in buckets:
                    bucket["quote_to_submit"].append(qts)
            if isinstance(stc, int) and stc >= 0:
                submit_to_confirm.append(stc)
                for bucket in buckets:
                    bucket["submit_to_confirm"].append(stc)
            if isinstance(qtc, int) and qtc >= 0:
                quote_to_confirm.append(qtc)
                for bucket in buckets:
                    bucket["quote_to_confirm"].append(qtc)
        p50_submit = self._percentile_ms(quote_to_submit, 0.5)
        p90_submit = self._percentile_ms(quote_to_submit, 0.9)
        p99_submit = self._percentile_ms(quote_to_submit, 0.99)
        p50_confirm = self._percentile_ms(submit_to_confirm, 0.5)
        p90_confirm = self._percentile_ms(submit_to_confirm, 0.9)
        p99_confirm = self._percentile_ms(submit_to_confirm, 0.99)
        suggested = sorted({0, 250, 500, 1000, 2000, *[value for value in (p50_submit, p90_submit) if value > 0]})
        return {
            "samples": len(quote_to_submit),
            "quote_to_submit_p50_ms": p50_submit,
            "quote_to_submit_p90_ms": p90_submit,
            "quote_to_submit_p99_ms": p99_submit,
            "submit_to_confirm_p50_ms": p50_confirm,
            "submit_to_confirm_p90_ms": p90_confirm,
            "submit_to_confirm_p99_ms": p99_confirm,
            "quote_to_confirm_p50_ms": self._percentile_ms(quote_to_confirm, 0.5),
            "quote_to_confirm_p90_ms": self._percentile_ms(quote_to_confirm, 0.9),
            "quote_to_confirm_p99_ms": self._percentile_ms(quote_to_confirm, 0.99),
            "by_signer_mode": {
                signer_mode: self._timing_group_summary(groups)
                for signer_mode, groups in sorted(by_signer.items())
                if groups["quote_to_submit"] or groups["submit_to_confirm"] or groups["quote_to_confirm"]
            },
            "by_pool": {
                pool: self._timing_group_summary(groups)
                for pool, groups in sorted(by_pool.items())
                if groups["quote_to_submit"] or groups["submit_to_confirm"] or groups["quote_to_confirm"]
            },
            "by_quote_source": {
                source: self._timing_group_summary(groups)
                for source, groups in sorted(by_quote_source.items())
                if groups["quote_to_submit"] or groups["submit_to_confirm"] or groups["quote_to_confirm"]
            },
            "suggested_delay_windows_ms": suggested,
            "source": "live_audits" if quote_to_submit else "fixed_defaults",
        }

    def _empty_timing_group(self) -> dict[str, list[int]]:
        return {"quote_to_submit": [], "submit_to_confirm": [], "quote_to_confirm": []}

    def _timing_group_summary(self, groups: dict[str, list[int]]) -> dict[str, object]:
        quote_to_submit = groups.get("quote_to_submit", [])
        submit_to_confirm = groups.get("submit_to_confirm", [])
        quote_to_confirm = groups.get("quote_to_confirm", [])
        return {
            "samples": len(quote_to_submit),
            "quote_to_submit_p50_ms": self._percentile_ms(quote_to_submit, 0.5),
            "quote_to_submit_p90_ms": self._percentile_ms(quote_to_submit, 0.9),
            "quote_to_submit_p99_ms": self._percentile_ms(quote_to_submit, 0.99),
            "submit_to_confirm_p50_ms": self._percentile_ms(submit_to_confirm, 0.5),
            "submit_to_confirm_p90_ms": self._percentile_ms(submit_to_confirm, 0.9),
            "submit_to_confirm_p99_ms": self._percentile_ms(submit_to_confirm, 0.99),
            "quote_to_confirm_p50_ms": self._percentile_ms(quote_to_confirm, 0.5),
            "quote_to_confirm_p90_ms": self._percentile_ms(quote_to_confirm, 0.9),
            "quote_to_confirm_p99_ms": self._percentile_ms(quote_to_confirm, 0.99),
        }

    def _audit_quote_pool(self, audit: LiveExecutionAudit) -> str:
        quote = audit.quote if isinstance(audit.quote, dict) else {}
        pool = str(quote.get("pool") or "").strip()
        return pool or "unknown"

    def _audit_quote_source(self, audit: LiveExecutionAudit) -> str:
        quote = audit.quote if isinstance(audit.quote, dict) else {}
        provider = str(quote.get("provider") or quote.get("source") or "").strip()
        if provider:
            return provider
        provider_request = quote.get("provider_request")
        if isinstance(provider_request, dict) and provider_request:
            return "pumpportal_local"
        return "unknown"

    def _audit_execution_timing(self, audit: LiveExecutionAudit) -> dict[str, object]:
        timing = dict(audit.execution_timing or {})
        quote = audit.quote if isinstance(audit.quote, dict) else {}
        quote_at = self._parse_iso_datetime(str(quote.get("created_at") or "")) or audit.created_at
        submitted_at = self._parse_iso_datetime(str(timing.get("submitted_at") or ""))
        confirmed_at = self._parse_iso_datetime(str(timing.get("confirmed_at") or ""))
        if not submitted_at and audit.transaction_signature and audit.status in {"submitted", "confirmed", "reconciled", "needs_review", "failed"}:
            submitted_at = audit.updated_at
        if not confirmed_at and audit.confirmation_checked_at and audit.confirmation_status in {"confirmed", "finalized"}:
            confirmed_at = audit.confirmation_checked_at
        if submitted_at:
            timing["submitted_at"] = submitted_at.isoformat()
            if "quote_to_submit_ms" not in timing:
                timing["quote_to_submit_ms"] = max(0, int((submitted_at - quote_at).total_seconds() * 1000))
        if confirmed_at:
            timing["confirmed_at"] = confirmed_at.isoformat()
            if "quote_to_confirm_ms" not in timing:
                timing["quote_to_confirm_ms"] = max(0, int((confirmed_at - quote_at).total_seconds() * 1000))
            if submitted_at and "submit_to_confirm_ms" not in timing:
                timing["submit_to_confirm_ms"] = max(0, int((confirmed_at - submitted_at).total_seconds() * 1000))
        return timing

    def _percentile_ms(self, values: list[int], percentile: float) -> int:
        if not values:
            return 0
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
        return int(ordered[index])

    def _shadow_landing_window(
        self,
        audit: LiveExecutionAudit,
        immediate_entry_price: float,
        quoted_at: datetime,
        landing_at: datetime,
        delay_ms: int,
    ) -> dict[str, object]:
        quote_expires_at = self._parse_iso_datetime(str(audit.quote.get("expires_at") or "")) if isinstance(audit.quote, dict) else None
        window = {
            "delay_ms": delay_ms,
            "landing_at": landing_at.isoformat(),
            "status": "waiting_for_fill",
            "entry_price": None,
            "entry_price_source": "",
            "entry_observed_at": None,
            "exit_price": None,
            "exit_price_source": "",
            "exit_observed_at": None,
            "exit_reason": "",
            "hold_duration_seconds": 0,
            "move_pct": None,
            "costs": self._shadow_quote_cost_breakdown(audit, self._audit_amount_sol(audit)),
            "gross_pnl_sol": 0.0,
            "cost_adjusted_pnl_sol": 0.0,
            "estimated_pnl_sol": 0.0,
            "outcome": "pending",
            "fill_status": "pending",
            "reason": "Waiting for accepted price observations at or after landing delay.",
        }
        if quote_expires_at and landing_at >= quote_expires_at:
            window.update({"status": "stale_quote", "fill_status": "missed", "outcome": "missed", "reason": "Landing delay is beyond quote expiry."})
            return window
        observations = self._shadow_observations_after(audit.mint, landing_at - timedelta(microseconds=1))
        if delay_ms == 0:
            entry_price = immediate_entry_price
            entry_source = "immediate_quote_entry"
            entry_at = quoted_at
            path = self._shadow_observations_after(audit.mint, quoted_at)
        elif observations:
            entry = observations[0]
            entry_price = float(entry.price or 0.0)
            entry_source = entry.price_source
            entry_at = entry.observed_at
            path = [item for item in observations if item.observed_at > entry_at]
        else:
            window.update({"status": "missed_fill", "fill_status": "missed", "outcome": "missed", "reason": "No accepted price observation was available at or after the landing delay."})
            return window
        if entry_price <= 0:
            window.update({"status": "missed_fill", "fill_status": "missed", "outcome": "missed", "reason": "Landing price was unavailable or invalid."})
            return window
        amount_sol = self._audit_amount_sol(audit)
        exit_price, exit_source, exit_at, exit_reason, partial_realized = self._shadow_exit_from_observations(entry_price, entry_at, path, amount_sol)
        if not exit_price or not exit_at:
            latest_price, latest_source, latest_at = self._shadow_price_from_observation(path[-1]) if path else (entry_price, entry_source, entry_at)
            exit_price, exit_source, exit_at, exit_reason = latest_price, latest_source, latest_at, "latest observed price"
        move_pct = ((float(exit_price) - entry_price) / max(entry_price, 0.000000001)) * 100
        costs = self._shadow_quote_cost_breakdown(audit, amount_sol)
        gross_pnl = round(partial_realized + amount_sol * (move_pct / 100), 6)
        estimated_pnl = round(gross_pnl - float(costs["total_cost_sol"]), 6)
        window.update(
            {
                "status": "evaluated",
                "fill_status": "filled",
                "entry_price": entry_price,
                "entry_price_source": entry_source,
                "entry_observed_at": entry_at.isoformat(),
                "exit_price": exit_price,
                "exit_price_source": exit_source,
                "exit_observed_at": exit_at.isoformat(),
                "exit_reason": exit_reason,
                "hold_duration_seconds": max(0, int((exit_at - entry_at).total_seconds())),
                "move_pct": round(move_pct, 3),
                "costs": costs,
                "gross_pnl_sol": gross_pnl,
                "cost_adjusted_pnl_sol": estimated_pnl,
                "estimated_pnl_sol": estimated_pnl,
                "outcome": self._classify_pnl(estimated_pnl),
                "reason": "Delayed landing window evaluated with configured exit rules.",
            }
        )
        return window

    def _shadow_rule_snapshot(self) -> dict[str, object]:
        return {
            "take_profit_pct": self.settings.take_profit_pct,
            "stop_loss_pct": self.settings.stop_loss_pct,
            "minimum_hold_time_seconds": self.settings.minimum_hold_time_seconds,
            "max_hold_time_seconds": self.settings.max_hold_time_seconds,
            "max_position_ticks": self.settings.max_position_ticks,
            "trailing_stop_enabled": self.settings.trailing_stop_enabled,
            "trailing_stop_pct": self.settings.trailing_stop_pct,
            "break_even_stop_enabled": self.settings.break_even_stop_enabled,
            "break_even_after_profit_pct": self.settings.break_even_after_profit_pct,
            "stalled_trade_exit_enabled": self.settings.stalled_trade_exit_enabled,
            "stalled_trade_seconds": self.settings.stalled_trade_seconds,
            "stalled_trade_min_move_pct": self.settings.stalled_trade_min_move_pct,
            "partial_take_profit_enabled": self.settings.partial_take_profit_enabled,
            "partial_take_profit_pct": self.settings.partial_take_profit_pct,
            "partial_take_profit_fraction": self.settings.partial_take_profit_fraction,
        }

    def _shadow_exit_from_observations(
        self,
        entry_price: float,
        quoted_at: datetime,
        observations: list[PriceObservation],
        amount_sol: float,
    ) -> tuple[float | None, str, datetime | None, str, float]:
        highest_move = 0.0
        partial_realized = 0.0
        partial_taken = False
        ticks = 0
        latest: PriceObservation | None = None
        for observation in observations:
            latest = observation
            ticks += 1
            price = float(observation.price or 0.0)
            if price <= 0:
                continue
            move_pct = ((price - entry_price) / max(entry_price, 0.000000001)) * 100
            highest_move = max(highest_move, move_pct)
            hold_seconds = max(0, int((observation.observed_at - quoted_at).total_seconds()))
            if self.settings.partial_take_profit_enabled and not partial_taken and move_pct >= self.settings.partial_take_profit_pct:
                fraction = max(0.0, min(1.0, self.settings.partial_take_profit_fraction))
                partial_realized = round(amount_sol * (move_pct / 100) * fraction, 6)
                partial_taken = True
            if hold_seconds < self.settings.minimum_hold_time_seconds:
                continue
            reason = ""
            if move_pct >= self.settings.take_profit_pct:
                reason = "take profit"
            elif self.settings.trailing_stop_enabled and highest_move >= self.settings.partial_take_profit_pct and move_pct <= highest_move - self.settings.trailing_stop_pct:
                reason = "trailing stop"
            elif self.settings.break_even_stop_enabled and highest_move >= self.settings.break_even_after_profit_pct and move_pct <= 0:
                reason = "break-even stop"
            elif self.settings.stalled_trade_exit_enabled and hold_seconds >= self.settings.stalled_trade_seconds and abs(move_pct) <= self.settings.stalled_trade_min_move_pct:
                reason = "stalled trade"
            elif move_pct <= -abs(self.settings.stop_loss_pct):
                reason = "stop loss"
            elif hold_seconds >= self.settings.max_hold_time_seconds:
                reason = "max hold time"
            elif ticks >= self.settings.max_position_ticks:
                reason = "max position ticks"
            if reason:
                return price, observation.price_source, observation.observed_at, reason, partial_realized
        if latest:
            return float(latest.price or 0.0), latest.price_source, latest.observed_at, "latest observed price", partial_realized
        return None, "", None, "", partial_realized

    def _audit_amount_sol(self, audit: LiveExecutionAudit) -> float:
        try:
            if audit.action == "buy" and not str(audit.amount).endswith("%"):
                return max(0.0, float(audit.amount))
        except ValueError:
            return 0.0
        return 0.0

    def _quote_latency_ms(self, audit: LiveExecutionAudit) -> int:
        request = audit.request if isinstance(audit.request, dict) else {}
        quote = audit.quote if isinstance(audit.quote, dict) else {}
        requested_at = self._parse_iso_datetime(str(request.get("created_at") or ""))
        quoted_at = self._parse_iso_datetime(str(quote.get("created_at") or "")) or audit.created_at
        if not requested_at:
            return 0
        return max(0, int((quoted_at - requested_at).total_seconds() * 1000))

    def _shadow_price_at_or_before(self, mint: str, at: datetime) -> tuple[float | None, str, datetime | None]:
        observations = [item for item in self.storage.load_price_observations(1000, mint=mint) if item.accepted and item.price and item.observed_at <= at]
        if observations:
            latest = observations[-1]
            return float(latest.price or 0.0), latest.price_source, latest.observed_at
        token = next((item for item in self.storage.load_all_tokens(5000) if item.mint == mint), None)
        if token and token.current_price:
            return float(token.current_price), "token_current_price", token.detected_at
        return None, "", None

    def _shadow_price_after(self, mint: str, at: datetime) -> tuple[float | None, str, datetime | None]:
        observations = self._shadow_observations_after(mint, at)
        if not observations:
            return None, "", None
        return self._shadow_price_from_observation(observations[-1])

    def _shadow_observations_after(self, mint: str, at: datetime) -> list[PriceObservation]:
        return [item for item in self.storage.load_price_observations(1000, mint=mint) if item.accepted and item.price and item.observed_at > at]

    def _shadow_price_from_observation(self, observation: PriceObservation) -> tuple[float | None, str, datetime | None]:
        return float(observation.price or 0.0), observation.price_source, observation.observed_at

    def _parse_iso_datetime(self, value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=utc_now().tzinfo)

    def _execution_policy_blockers(self) -> list[str]:
        blockers: list[str] = []
        if float(self.settings.live_max_trade_sol or 0) <= 0:
            blockers.append("live max trade cap must be set")
        if float(self.settings.live_daily_loss_cap_sol or 0) <= 0:
            blockers.append("live daily loss cap must be set")
        if float(self.settings.live_wallet_exposure_cap_sol or 0) <= 0:
            blockers.append("live wallet exposure cap must be set")
        if int(self.settings.live_max_open_positions or 0) <= 0:
            blockers.append("live max open positions must be set")
        if float(self.settings.live_max_slippage_pct or 0) <= 0:
            blockers.append("live max slippage cap must be set")
        if float(self.settings.live_max_slippage_pct or 0) > 10:
            blockers.append("live max slippage cap should be 10% or lower for the pilot")
        if float(self.settings.live_priority_fee_cap_sol or 0) <= 0:
            blockers.append("live priority fee cap must be set")
        if float(self.settings.live_priority_fee_cap_sol or 0) > 0.001:
            blockers.append("live priority fee cap should be 0.001 SOL or lower for the pilot")
        if not blockers:
            cap_intent = self._live_cap_operator_intent_status()
            if not cap_intent["visible"]:
                blockers.append(str(cap_intent["blocker"]))
        return blockers

    def _live_cap_operator_intent_status(self) -> dict[str, object]:
        current_settings = asdict(self.settings)
        cap_snapshot = {key: current_settings.get(key) for key in self.LIVE_CAP_SETTING_KEYS}
        for version in self.storage.load_settings_versions(100):
            cap_changed_keys = sorted(set(version.changed_keys).intersection(self.LIVE_CAP_SETTING_KEYS))
            if not cap_changed_keys:
                continue
            if all(version.settings.get(key) == value for key, value in cap_snapshot.items()):
                return {
                    "visible": True,
                    "settings_version_id": version.id,
                    "recorded_at": version.created_at.isoformat(),
                    "changed_keys": cap_changed_keys,
                    "blocker": "",
                    "operator_action": "Live cap settings have visible settings-version evidence.",
                }
        return {
            "visible": False,
            "settings_version_id": "",
            "recorded_at": None,
            "changed_keys": [],
            "blocker": "live cap changes require visible operator intent via settings version evidence",
            "operator_action": "Save live cap settings through the operator settings flow before a real-money pilot.",
        }

    def _execution_policy_recommendation(
        self,
        *,
        stale_rate: float,
        blocked_rate: float,
        unhealthy_rate: float,
        quote_issues: dict[str, object],
        calibration: dict[str, object],
        shadow_windows: list[dict[str, object]],
        policy_blockers: list[str],
    ) -> dict[str, object]:
        slippage_cap = float(self.settings.live_max_slippage_pct or 0.0)
        fee_cap = float(self.settings.live_priority_fee_cap_sol or 0.0)
        base_slippage = min(max(slippage_cap if slippage_cap > 0 else 1.0, 0.5), 10.0)
        base_fee = min(max(fee_cap if fee_cap > 0 else 0.00001, 0.00001), 0.001)
        categories = {str(item.get("category")): item for item in quote_issues.get("categories", []) if isinstance(item, dict)}
        stale_pressure = stale_rate > 0.25 or "stale_quote" in categories
        slippage_pressure = "slippage_policy" in categories
        provider_pressure = "provider_or_rpc" in categories
        cap_pressure = "cap_policy" in categories
        missed_windows = [window for window in shadow_windows if str(window.get("fill_status", "")) == "missed" or str(window.get("status", "")) in {"missed_fill", "stale_quote"}]
        evaluated_windows = [window for window in shadow_windows if str(window.get("status", "")) == "evaluated"]
        missed_rate = round(len(missed_windows) / max(1, len(shadow_windows)), 3) if shadow_windows else 0.0
        quote_to_submit_p90 = int(calibration.get("quote_to_submit_p90_ms", 0) or 0)

        slippage_delta = 0.0
        if slippage_pressure:
            slippage_delta += 0.5
        if stale_pressure or missed_rate > 0.25:
            slippage_delta += 0.25
        if unhealthy_rate > 0.25 and not cap_pressure:
            slippage_delta += 0.25
        suggested_slippage = base_slippage + slippage_delta
        if slippage_cap > 0:
            suggested_slippage = min(suggested_slippage, slippage_cap)
        suggested_slippage = round(min(max(suggested_slippage, 0.5), 10.0), 2)

        fee_multiplier = 0.35
        if stale_pressure:
            fee_multiplier += 0.25
        if provider_pressure:
            fee_multiplier += 0.15
        if quote_to_submit_p90 > 1500:
            fee_multiplier += 0.15
        if missed_rate > 0.25:
            fee_multiplier += 0.1
        suggested_fee = round(min(max(base_fee * fee_multiplier, 0.00001), fee_cap if fee_cap > 0 else base_fee), 9)

        reasons: list[str] = []
        if stale_pressure:
            reasons.append("stale quote pressure suggests paying for faster landing before increasing size")
        if slippage_pressure:
            reasons.append("recent quotes hit slippage policy")
        if provider_pressure:
            reasons.append("provider/RPC quote issues are present; do not solve these with caps alone")
        if cap_pressure:
            reasons.append("cap-policy blocks mean the requested order exceeds configured safety limits")
        if missed_rate > 0.25:
            reasons.append("shadow landing windows show delayed fills missing or going stale")
        if quote_to_submit_p90 > 1500:
            reasons.append("quote-to-submit p90 is slow enough to justify a cautious priority-fee bump")
        if policy_blockers:
            reasons.append("configure live policy caps before applying dynamic suggestions")
        status = "blocked" if policy_blockers else ("raise_priority_fee" if stale_pressure or quote_to_submit_p90 > 1500 else ("review_slippage" if slippage_pressure or missed_rate > 0.25 else "stable"))
        return {
            "status": status,
            "suggested_slippage_pct": suggested_slippage,
            "suggested_priority_fee_sol": suggested_fee,
            "cap_room": {
                "slippage_pct": round(max(0.0, slippage_cap - suggested_slippage), 4) if slippage_cap > 0 else 0.0,
                "priority_fee_sol": round(max(0.0, fee_cap - suggested_fee), 9) if fee_cap > 0 else 0.0,
            },
            "inputs": {
                "stale_quote_rate": stale_rate,
                "blocked_quote_rate": blocked_rate,
                "unhealthy_quote_rate": unhealthy_rate,
                "missed_landing_rate": missed_rate,
                "landing_windows": len(shadow_windows),
                "evaluated_landing_windows": len(evaluated_windows),
                "quote_to_submit_p90_ms": quote_to_submit_p90,
                "issue_categories": list(categories.keys()),
            },
            "reasons": reasons or ["recent quote policy evidence is stable"],
            "operator_action": "Apply only within caps after reviewing quote issues and shadow landing evidence.",
        }

    def _strategy_promotion_status(
        self,
        closed: list[TradeRecord],
        source_events: int,
        replay_confidence: int,
        source: dict[str, object],
        price: dict[str, object],
        performance: dict[str, object],
        profit_factor: float,
        out_of_sample: dict[str, object] | None = None,
        source_soak: dict[str, object] | None = None,
    ) -> dict[str, object]:
        strategy_fingerprint = self._paper_strategy_fingerprint(self.settings)
        matching_settings_version_ids = sorted(
            version.id
            for version in self.storage.load_settings_versions(5000)
            if self._paper_strategy_fingerprint(version.settings) == strategy_fingerprint
        )
        matching_ids = set(matching_settings_version_ids)
        matching_closed = [
            trade
            for trade in closed
            if trade.mode == "paper" and trade.settings_version_id in matching_ids
        ]
        evidence_now = utc_now()
        evidence_cutoff = evidence_now - timedelta(hours=self.STRATEGY_PROMOTION_EVIDENCE_WINDOW_HOURS)
        recent_matching_closed: list[TradeRecord] = []
        excluded_ambiguous_timestamp_trades = 0
        excluded_future_timestamp_trades = 0
        for trade in matching_closed:
            closed_at = trade.closed_at
            if closed_at is None or closed_at.tzinfo is None or closed_at.utcoffset() is None:
                excluded_ambiguous_timestamp_trades += 1
                continue
            if closed_at > evidence_now:
                excluded_future_timestamp_trades += 1
                continue
            if closed_at >= evidence_cutoff:
                recent_matching_closed.append(trade)
        recent_matching_closed.sort(key=self._trade_timestamp_sort_key)
        closed_count = len(recent_matching_closed)
        cohort_performance = self._performance_group("current paper strategy (recent)", recent_matching_closed)
        all_matching_strategy_performance = self._performance_group("current paper strategy (all time)", matching_closed)
        pnl_sol = float(cohort_performance.get("pnl_sol", 0.0))
        cohort_wins = int(cohort_performance.get("wins", 0) or 0)
        cohort_losses = int(cohort_performance.get("losses", 0) or 0)
        cohort_profit_factor = 99.0 if cohort_wins > 0 and cohort_losses == 0 else float(cohort_performance.get("profit_factor", 0.0))
        max_drawdown = self._max_drawdown_sol(recent_matching_closed)
        all_matching_strategy_drawdown = self._max_drawdown_sol(matching_closed)
        all_history_drawdown = self._max_drawdown_sol(closed)
        out_of_sample = out_of_sample or self._out_of_sample_strategy_evidence(self.settings.strategy_profile)
        source_soak = source_soak or self.source_soak_acceptance_report()
        source_soak_required = bool(source_soak.get("hard_required"))
        source_soak_ready = bool(source_soak.get("ready"))
        validate = out_of_sample.get("validate", {}) if isinstance(out_of_sample.get("validate"), dict) else {}
        validate_tokens = int(validate.get("tokens_replayed", 0) or 0)
        validate_pnl = float(validate.get("estimated_pnl_sol", 0.0) or 0.0)
        validate_profit_factor = float(validate.get("profit_factor", 0.0) or 0.0)
        collapse = bool(out_of_sample.get("collapse_warning"))
        gates = [
            self._promotion_gate("closed_trades", "Recent closed paper trades (current strategy)", closed_count, ">= 30 within 168h", closed_count >= 30, "Collect at least 30 closed paper trades under the current strategy within the fixed seven-day evidence window."),
            self._promotion_gate("source_events", "Source event sample", source_events, ">= 100", source_events >= 100, "Collect enough source events for replay and parser confidence."),
            self._promotion_gate("replay_confidence", "Replay confidence", replay_confidence, ">= 70", replay_confidence >= 70, "Replay confidence needs accepted price and normalized event coverage."),
            self._promotion_gate("source_trust", "Source trust", str(source.get("trust_state", "unknown")), "trusted", source.get("trust_state") == "trusted", "Source trust must be trusted before strategy promotion."),
            self._promotion_gate("source_soak", "Hybrid source soak", source_soak.get("status", "unknown"), "ready when direct verifier is configured", (not source_soak_required) or source_soak_ready, "Direct/PumpPortal soak must pass once the direct verifier is configured or direct events are collected."),
            self._promotion_gate("price_acceptance", "Price acceptance", round(float(price.get("acceptance_rate", 0.0)), 3), ">= 0.70", float(price.get("acceptance_rate", 0.0)) >= 0.70, "Accepted prices should dominate rejected marks."),
            self._promotion_gate("paper_profitability", "Paper profitability (current strategy)", f"{round(pnl_sol, 6)} SOL / PF {round(cohort_profit_factor, 2)}", "PnL > 0 and PF > 1.1", pnl_sol > 0 and cohort_profit_factor > 1.1, "Paper performance under the current strategy must be positive with profit factor above 1.1."),
            self._promotion_gate("drawdown", "Max drawdown", round(max_drawdown, 6), "<= 0.05 SOL", max_drawdown <= 0.05, "Drawdown must fit the tiny-pilot risk envelope."),
            self._promotion_gate("out_of_sample", "Out-of-sample replay", f"{round(validate_pnl, 6)} SOL / PF {round(validate_profit_factor, 2)} / {validate_tokens} tokens", "validate PnL > 0, PF > 1.0, >= 10 tokens", validate_tokens >= 10 and validate_pnl > 0 and validate_profit_factor > 1.0, "Validation replay must stay profitable on held-out tokens."),
            self._promotion_gate("strategy_drift", "Strategy drift", "collapse" if collapse else "stable", "stable", not collapse, "Validation performance must not collapse versus training performance."),
            self._promotion_gate("safety_boundary", "Safety boundary", "paper-first", "paper-first", True, "Strategy promotion cannot bypass paper-first and live-control-plane boundaries."),
        ]
        blockers = [str(gate["reason"]) for gate in gates if gate["status"] == "fail"]
        can_promote = not blockers
        return {
            "can_promote": can_promote,
            "status": "eligible" if can_promote else "blocked" if closed_count >= 10 or source_events >= 25 else "not_enough_data",
            "mode": "paper_to_shadow",
            "gates": gates,
            "blockers": blockers,
            "summary": "Strategy can be promoted to shadow comparison." if can_promote else "Strategy needs more evidence before promotion.",
            "requires_operator_review": True,
            "out_of_sample": out_of_sample,
            "source_soak": source_soak,
            "strategy_fingerprint_schema": self.PAPER_STRATEGY_FINGERPRINT_SCHEMA,
            "strategy_fingerprint": strategy_fingerprint,
            "matching_settings_version_ids": matching_settings_version_ids,
            "strategy_evidence_window_hours": self.STRATEGY_PROMOTION_EVIDENCE_WINDOW_HOURS,
            "matching_closed_trades": len(matching_closed),
            "recent_matching_closed_trades": closed_count,
            "recent_oldest_closed_at": self._timestamp_for_deterministic_ordering(recent_matching_closed[0].closed_at).isoformat() if recent_matching_closed else None,
            "recent_newest_closed_at": self._timestamp_for_deterministic_ordering(recent_matching_closed[-1].closed_at).isoformat() if recent_matching_closed else None,
            "excluded_ambiguous_timestamp_trades": excluded_ambiguous_timestamp_trades,
            "excluded_future_timestamp_trades": excluded_future_timestamp_trades,
            "all_matching_strategy_closed_trades": len(matching_closed),
            "all_matching_strategy_performance": all_matching_strategy_performance,
            "all_matching_strategy_drawdown_sol": all_matching_strategy_drawdown,
            "all_history_closed_trades": len(closed),
            "cohort_performance": cohort_performance,
            "all_history_performance": {**performance, "profit_factor": profit_factor},
            "all_history_drawdown_sol": all_history_drawdown,
            "generated_at": evidence_now.isoformat(),
        }

    def _out_of_sample_strategy_evidence(self, profile: str | None = None, limit: int | None = None) -> dict[str, object]:
        selected_profile = profile or self.settings.strategy_profile
        candidates = [
            token
            for token in self.storage.load_all_tokens(limit or self.settings.backtest_replay_limit)
            if token.status in {TokenStatus.SKIPPED, TokenStatus.PAPER_SOLD, TokenStatus.DETECTED, TokenStatus.ANALYZING}
        ]
        midpoint = max(1, len(candidates) // 2)
        settings = self._settings_for_profile(selected_profile)
        train = self._run_backtest(candidates[:midpoint], replay_source="promotion_train", settings=settings, persist=False)
        validate = self._run_backtest(candidates[midpoint:], replay_source="promotion_validate", settings=settings, persist=False)
        train_profit_factor = self._effective_backtest_profit_factor(train)
        validate_profit_factor = self._effective_backtest_profit_factor(validate)
        collapse_warning = (
            validate.tokens_replayed >= 10
            and train.paper_buys > 0
            and validate.paper_buys > 0
            and (
                validate.estimated_pnl_sol <= 0
                or train.win_rate_pct - validate.win_rate_pct > 25
                or (train_profit_factor > 1.5 and validate_profit_factor <= 1.0)
            )
        )
        return {
            "engine_version": "promotion-walk-forward-v1",
            "profile": settings.strategy_profile,
            "sample_size": len(candidates),
            "split": {"train_tokens": train.tokens_replayed, "validate_tokens": validate.tokens_replayed},
            "train": {**train.to_dict(), "profit_factor": train_profit_factor},
            "validate": {**validate.to_dict(), "profit_factor": validate_profit_factor},
            "collapse_warning": collapse_warning,
            "determinism_fingerprint": self.data_integrity_report()["determinism_fingerprint"],
        }

    def _effective_backtest_profit_factor(self, run: BacktestRun) -> float:
        if run.profit_factor > 0:
            return float(run.profit_factor)
        if run.wins > 0 and run.losses == 0:
            return 99.0
        return 0.0

    def _promotion_gate(self, gate_id: str, label: str, value: object, target: object, passed: bool, reason: str) -> dict[str, object]:
        return {
            "id": gate_id,
            "label": label,
            "status": "pass" if passed else "fail",
            "value": value,
            "target": target,
            "reason": reason,
        }

    def _paper_strategy_fingerprint(self, settings: BotSettings | dict[str, object]) -> str:
        recorded = asdict(settings) if isinstance(settings, BotSettings) else dict(settings)
        normalized = asdict(BotSettings())
        normalized.update({key: value for key, value in recorded.items() if key in normalized})
        strategy_settings = {
            key: value
            for key, value in normalized.items()
            if key not in self.PAPER_STRATEGY_IGNORED_SETTING_KEYS
            and not key.startswith(("live_", "manual_live_", "profit_sweep_"))
        }
        encoded = json.dumps(
            {
                "schema": self.PAPER_STRATEGY_FINGERPRINT_SCHEMA,
                "settings": strategy_settings,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _peak_to_trough_drawdown_sol(self, pnls: list[float]) -> float:
        running = 0.0
        peak = 0.0
        drawdown = 0.0
        for pnl in pnls:
            running = round(running + pnl, 6)
            peak = max(peak, running)
            drawdown = max(drawdown, peak - running)
        return round(drawdown, 6)

    def _max_drawdown_sol(self, trades: list[TradeRecord]) -> float:
        ordered = sorted(trades, key=self._trade_timestamp_sort_key)
        return self._peak_to_trough_drawdown_sol([float(trade.pnl_sol or 0.0) for trade in ordered])

    def _trade_timestamp_sort_key(self, trade: TradeRecord) -> tuple[datetime, str]:
        timestamp = trade.closed_at or trade.opened_at
        return self._timestamp_for_deterministic_ordering(timestamp), trade.id

    def _timestamp_for_deterministic_ordering(self, timestamp: datetime | None) -> datetime:
        """Normalize only for reporting order; naive legacy values assume UTC but never pass freshness gates."""
        if timestamp is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)

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
        live_runtime_enabled = self.settings.manual_live_enabled or self.settings.autonomous_live_enabled
        if live_runtime_enabled and not self.settings.live_session_acknowledged:
            stop_reasons.append("live session acknowledgement is required")
        if self.settings.max_consecutive_losses_enabled and consecutive_losses >= self.settings.max_consecutive_losses:
            stop_reasons.append("consecutive loss halt")
        if self.settings.halt_on_low_replay_confidence and replay_confidence < self.settings.min_replay_confidence:
            stop_reasons.append("low replay confidence")
        readiness_halt = self.readiness_halt_reason()
        if readiness_halt:
            stop_reasons.append(readiness_halt)
        return {
            "paper_only": not live_runtime_enabled,
            "entries_allowed": not stop_reasons,
            "stop_reasons": stop_reasons,
            "consecutive_losses": consecutive_losses,
            "open_positions": self.open_position_count(),
            "daily_loss_cap_sol": self.settings.daily_loss_cap_sol,
            "total_pnl_sol": self.stats.total_pnl_sol,
            "kill_switch_available": True,
            "kill_switch_enabled": self.settings.kill_switch_enabled,
            "replay_confidence": replay_confidence,
            "manual_live_ready": self.settings.live_session_acknowledged,
            "autonomous_live_ready": self.settings.autonomous_live_enabled and self.settings.live_active_backend_armed,
            "live_blockers": [
                "configure Solana RPC, live caps, and wallet backend before turning on execution",
                "manual kill switch and wallet-scoped caps still apply to live entries",
                "browser wallet autonomy is capability-based and may remain assisted/manual",
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
            "last_tick_tokens_seen": self.last_tick_tokens_seen,
            "last_tick_active_tokens": self.last_tick_active_tokens,
            "last_tick_closed": self.last_tick_closed,
            "last_tick_completed_at": self.last_tick_completed_at.isoformat() if self.last_tick_completed_at else None,
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
            self.add_event("warning", "Watchdog recovery started the paper loop", subsystem="source", operator_action="Verify source health before resuming normal operation.")
        else:
            self.add_event("info", "Watchdog recovery cleared transient loop error", subsystem="source")
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
                healthy=connected,
                can_sign=connected,
                can_unattended_sign=False,
                supports_auto_sell=False,
                supports_auto_buy=False,
                disabled_reason="Browser wallets support manual signing only",
                message="Browser wallet requires manual approval for each transaction" if connected else "Browser wallet is not connected",
                transport="browser_extension",
            ).to_dict()
        if mode == "local_hot_wallet":
            hot_wallet = self.hot_wallet.status()
            imported = bool(hot_wallet["imported"])
            unlocked = bool(hot_wallet["unlocked"])
            return SignerStatus(
                mode="local_hot_wallet",
                connected=imported,
                wallet_public_key=str(hot_wallet["wallet_public_key"] or ""),
                healthy=imported,
                can_sign=unlocked,
                can_unattended_sign=unlocked,
                supports_auto_sell=unlocked,
                supports_auto_buy=unlocked,
                disabled_reason="" if unlocked else "Unlock the encrypted local hot wallet to enable unattended execution." if imported else "Import an encrypted local hot wallet first.",
                message="Encrypted local hot wallet is unlocked and ready." if unlocked else "Encrypted local hot wallet is imported but locked." if imported else "No local hot wallet is imported.",
                transport="encrypted_local_file",
                version="v1",
                last_heartbeat_at=str(hot_wallet["last_unlock_at"] or ""),
            ).to_dict()
        return self._local_signer_daemon_status()

    def _local_signer_daemon_status(self) -> dict[str, object]:
        now = utc_now()
        if self._cached_signer_status and self._cached_signer_status_at and (now - self._cached_signer_status_at).total_seconds() < 10:
            return self._cached_signer_status
        endpoint = self.signer_daemon_url or "http://127.0.0.1:8799"
        parsed = urlparse(endpoint)
        auth_configured = bool(self.signer_daemon_auth_token)
        base = SignerStatus(
            mode="local_signer_daemon",
            connected=False,
            wallet_public_key="",
            healthy=False,
            can_sign=False,
            can_unattended_sign=False,
            supports_auto_sell=False,
            supports_auto_buy=False,
            disabled_reason="Local signer daemon is not connected or not ready.",
            message="Local signer daemon is not connected.",
            endpoint=endpoint,
            transport="localhost_http",
            auth_configured=auth_configured,
        )
        if not self._local_signer_daemon_endpoint_allowed(endpoint):
            base.disabled_reason = "Signer daemon endpoint must stay localhost-only"
            base.message = "Local signer daemon endpoint is invalid for this safety boundary."
            result = base.to_dict()
            self._cached_signer_status = result
            self._cached_signer_status_at = now
            return result
        request = urllib.request.Request(
            endpoint.rstrip("/") + "/health",
            headers={"Authorization": f"Bearer {self.signer_daemon_auth_token}"} if auth_configured else {},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=1.5) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
            base.connected = bool(payload.get("connected", True))
            base.ready_to_submit = payload.get("ready_to_submit") is True
            base.healthy = base.ready_to_submit and bool(payload.get("healthy", False))
            base.wallet_public_key = str(payload.get("wallet_public_key") or "")
            base.can_sign = base.ready_to_submit and bool(payload.get("can_sign", False))
            base.can_unattended_sign = base.ready_to_submit and bool(payload.get("can_unattended_sign", False))
            base.supports_auto_sell = base.ready_to_submit and bool(payload.get("supports_auto_sell", False))
            base.supports_auto_buy = base.ready_to_submit and bool(payload.get("supports_auto_buy", False))
            base.disabled_reason = str(payload.get("disabled_reason") or "")
            base.message = str(payload.get("message") or "Local signer daemon responded.")
            base.version = str(payload.get("version") or "")
            base.last_heartbeat_at = str(payload.get("last_heartbeat_at") or now.isoformat())
            if not base.ready_to_submit:
                base.disabled_reason = base.disabled_reason or "Local signer daemon health response requires ready_to_submit=true."
                base.message = "Local signer daemon is connected but not ready to submit."
            if not auth_configured:
                base.healthy = False
                base.can_sign = False
                base.can_unattended_sign = False
                base.supports_auto_sell = False
                base.supports_auto_buy = False
                base.ready_to_submit = False
                base.disabled_reason = "Local signer daemon auth token is not configured."
                base.message = "Local signer daemon cannot be armed without authenticated health checks."
        except Exception as exc:
            base.disabled_reason = "Local signer daemon is unavailable."
            base.message = f"Daemon status check failed: {exc.__class__.__name__}"
        result = base.to_dict()
        self._cached_signer_status = result
        self._cached_signer_status_at = now
        return result

    def _local_signer_daemon_endpoint_allowed(self, endpoint: str) -> bool:
        parsed = urlparse(endpoint or "http://127.0.0.1:8799")
        return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"}

    def hot_wallet_status(self) -> dict[str, object]:
        status = self.hot_wallet.status()
        self._sync_hot_wallet_settings(status)
        return status

    def _sync_hot_wallet_settings(self, status: dict[str, object], save: bool = True) -> None:
        previous = (
            self.settings.live_hot_wallet_enabled,
            self.settings.live_hot_wallet_public_key,
            self.settings.live_hot_wallet_label,
            self.settings.live_active_backend_armed,
            self.settings.live_active_wallet_public_key,
        )
        imported = bool(status.get("imported"))
        self.settings.live_hot_wallet_enabled = imported
        self.settings.live_hot_wallet_public_key = str(status.get("wallet_public_key") or "") if imported else ""
        self.settings.live_hot_wallet_label = str(status.get("label") or "") if imported else ""
        if not imported and self.settings.live_signer_mode == "local_hot_wallet":
            self.settings.live_active_backend_armed = False
            self.settings.live_active_wallet_public_key = ""
        current = (
            self.settings.live_hot_wallet_enabled,
            self.settings.live_hot_wallet_public_key,
            self.settings.live_hot_wallet_label,
            self.settings.live_active_backend_armed,
            self.settings.live_active_wallet_public_key,
        )
        if save and current != previous:
            self.storage.save_settings(self.settings)

    def import_hot_wallet(self, private_key: str, password: str, label: str = "") -> dict[str, object]:
        status = self.hot_wallet.import_private_key(private_key, password, label)
        self.settings.live_hot_wallet_enabled = True
        self.settings.live_hot_wallet_public_key = str(status["wallet_public_key"] or "")
        self.settings.live_hot_wallet_label = str(status["label"] or "")
        self.settings.live_signer_mode = "local_hot_wallet"
        self.storage.save_settings(self.settings)
        self.add_event("warning", "Encrypted local hot wallet imported and unlocked", subsystem="live", operator_action="Verify caps and arm the backend before unattended execution.")
        return status

    def unlock_hot_wallet(self, password: str) -> dict[str, object]:
        status = self.hot_wallet.unlock(password)
        self.settings.live_hot_wallet_enabled = bool(status["imported"])
        self.settings.live_hot_wallet_public_key = str(status["wallet_public_key"] or "")
        self.storage.save_settings(self.settings)
        self.add_event("info", "Encrypted local hot wallet unlocked for this app session", subsystem="live")
        return status

    def lock_hot_wallet(self) -> dict[str, object]:
        status = self.hot_wallet.lock()
        if self.settings.live_signer_mode == "local_hot_wallet" and self.settings.live_active_backend_armed:
            self.settings.live_active_backend_armed = False
            self.settings.live_active_wallet_public_key = ""
        self.storage.save_settings(self.settings)
        self.add_event("warning", "Encrypted local hot wallet locked", subsystem="live")
        return status

    def clear_hot_wallet(self) -> dict[str, object]:
        previous_wallet = self.settings.live_hot_wallet_public_key
        status = self.hot_wallet.clear()
        self.settings.live_hot_wallet_enabled = False
        self.settings.live_hot_wallet_public_key = ""
        self.settings.live_hot_wallet_label = ""
        if self.settings.live_signer_mode == "local_hot_wallet":
            self.settings.live_signer_mode = "browser_wallet"
        if self.settings.live_active_backend_armed and self.settings.live_active_wallet_public_key == previous_wallet:
            self.settings.live_active_backend_armed = False
            self.settings.live_active_wallet_public_key = ""
        self.storage.save_settings(self.settings)
        self.add_event("warning", "Encrypted local hot wallet cleared from local storage", subsystem="live")
        return status

    def arm_live_backend(
        self,
        env_live_enabled: bool,
        signer_mode: str,
        wallet_public_key: str = "",
        *,
        local_auth_enabled: bool = False,
    ) -> dict[str, object]:
        if not local_auth_enabled:
            raise ValueError("dashboard password/local auth is required before arming the live backend")
        wallet = self._resolve_backend_wallet(signer_mode, wallet_public_key)
        status = self.live_status(env_live_enabled, wallet, signer_mode, local_auth_enabled=local_auth_enabled)
        blockers = list(status.get("blockers") or [])
        if blockers:
            raise ValueError(", ".join(blockers))
        self.settings.live_signer_mode = signer_mode
        self.settings.live_active_backend_armed = True
        self.settings.live_active_wallet_public_key = wallet
        self.storage.save_settings(self.settings)
        session = LiveSession(
            id=new_id("liveses"),
            created_at=utc_now(),
            status="armed",
            signer_mode=signer_mode,
            wallet_public_key=wallet,
            caps_snapshot=self.live_caps_snapshot(),
            acknowledged_at=utc_now() if self.settings.live_session_acknowledged else None,
        )
        self.storage.save_live_session(session)
        self.active_live_session_id = session.id
        self.add_event("warning", f"Live backend armed: {signer_mode} / {wallet}", subsystem="live", operator_action="Use the kill switch or disarm control to halt new autonomous entries.")
        return {
            "armed": True,
            "wallet_public_key": wallet,
            "signer_mode": signer_mode,
            "live_status": self.live_status(
                env_live_enabled,
                wallet,
                signer_mode,
                local_auth_enabled=local_auth_enabled,
            ),
        }

    def disarm_live_backend(self) -> dict[str, object]:
        mode = self.settings.live_signer_mode
        wallet = self.settings.live_active_wallet_public_key
        self.settings.live_active_backend_armed = False
        self.settings.live_active_wallet_public_key = ""
        self.storage.save_settings(self.settings)
        self.add_event("warning", f"Live backend disarmed: {mode} / {wallet or 'no wallet'}", subsystem="live", operator_action="Protective exits can still be handled manually if needed.")
        self.active_live_session_id = ""
        return {"armed": False, "wallet_public_key": wallet, "signer_mode": mode}

    def enforce_live_auth_startup_policy(self, local_auth_enabled: bool) -> dict[str, object]:
        if local_auth_enabled or not self.settings.live_active_backend_armed:
            return {"disarmed": False, "reason": ""}
        mode = self.settings.live_signer_mode
        wallet = self.settings.live_active_wallet_public_key
        self.settings.live_active_backend_armed = False
        self.settings.live_active_wallet_public_key = ""
        self.storage.save_settings(self.settings)
        self.active_live_session_id = ""
        reason = "Persisted live backend disarmed at startup because dashboard local auth is disabled"
        self.add_event(
            "warning",
            reason,
            subsystem="live",
            operator_action="Configure a dashboard password before arming a live backend.",
        )
        return {"disarmed": True, "reason": reason, "wallet_public_key": wallet, "signer_mode": mode}

    def live_caps_snapshot(self) -> dict[str, object]:
        return {
            "max_trade_sol": self.settings.live_max_trade_sol,
            "daily_loss_cap_sol": self.settings.live_daily_loss_cap_sol,
            "wallet_exposure_cap_sol": self.settings.live_wallet_exposure_cap_sol,
            "max_open_positions": self.settings.live_max_open_positions,
            "max_slippage_pct": self.settings.live_max_slippage_pct,
            "priority_fee_cap_sol": self.settings.live_priority_fee_cap_sol,
            "operator_intent": self._live_cap_operator_intent_status(),
        }

    def _resolve_backend_wallet(self, signer_mode: str, wallet_public_key: str = "") -> str:
        wallet = wallet_public_key.strip()
        if signer_mode == "local_hot_wallet":
            return wallet or self.hot_wallet.wallet_public_key() or self.settings.live_hot_wallet_public_key
        if signer_mode == "local_signer_daemon":
            signer = self._local_signer_daemon_status()
            return wallet or str(signer.get("wallet_public_key") or "")
        return wallet

    def _wallet_live_metrics(self, wallet_public_key: str) -> dict[str, float]:
        positions = self._live_ledger_positions(wallet_public_key)
        realized = round(sum(position.realized_pnl_sol for position in positions), 6)
        unrealized = round(sum(position.unrealized_pnl_sol for position in positions), 6)
        cost_basis = round(sum(position.cost_basis_sol for position in positions), 6)
        open_positions = len([position for position in positions if position.status == "open"])
        return {
            "realized_pnl_sol": realized,
            "unrealized_pnl_sol": unrealized,
            "cost_basis_sol": cost_basis,
            "open_positions": float(open_positions),
        }

    def _pre_run_backup_status(self, max_age_hours: int = 24) -> dict[str, object]:
        status = self.storage.backup_restore_status()
        latest_backup = status.get("latest_backup") if isinstance(status, dict) else None
        latest_restore = status.get("latest_restore") if isinstance(status, dict) else None
        now = utc_now()

        def parse_created_at(item: object) -> datetime | None:
            if not isinstance(item, dict):
                return None
            value = item.get("created_at")
            if not isinstance(value, str) or not value:
                return None
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None

        backup_at = parse_created_at(latest_backup)
        restore_at = parse_created_at(latest_restore)
        max_age_seconds = max(1, int(max_age_hours) * 3600)
        age_seconds = int((now - backup_at).total_seconds()) if backup_at else None
        backup_after_restore = bool(backup_at and (not restore_at or backup_at >= restore_at))
        fresh = bool(backup_at and age_seconds is not None and age_seconds <= max_age_seconds and backup_after_restore)
        if not backup_at:
            state = "missing"
            blocker = "pre-run backup artifact is required before live entries"
            operator_action = "Create a backup artifact from the Data workspace before starting a real-money session."
        elif not backup_after_restore:
            state = "superseded_by_restore"
            blocker = "pre-run backup is older than the latest restore"
            operator_action = "Create a new backup artifact after the latest restore before live entries."
        elif age_seconds is not None and age_seconds > max_age_seconds:
            state = "stale"
            blocker = f"pre-run backup is older than {max_age_hours}h"
            operator_action = "Create a fresh backup artifact before starting this real-money session."
        else:
            state = "fresh"
            blocker = ""
            operator_action = "Pre-run backup is fresh enough for a live session."
        return {
            "required": True,
            "state": state,
            "fresh": fresh,
            "max_age_hours": max_age_hours,
            "age_seconds": age_seconds,
            "latest_backup": latest_backup,
            "latest_restore": latest_restore,
            "backup_after_restore": backup_after_restore,
            "blocks_live_entries": not fresh,
            "blocker": blocker,
            "operator_action": operator_action,
        }

    def _live_execution_blockers(
        self,
        env_live_enabled: bool,
        action: str,
        wallet_public_key: str,
        signer_mode: str,
        autonomous: bool = False,
        signer: dict[str, object] | None = None,
        caps: dict[str, object] | None = None,
        wallet_metrics: dict[str, object] | None = None,
        unresolved: list[LiveExecutionAudit] | None = None,
        source_health: dict[str, object] | None = None,
        backup: dict[str, object] | None = None,
        stale_balance_positions: list[LiveLedgerPosition] | None = None,
        readiness_halt: str | None = None,
        confirmed_buy_spend_over_trade_cap: bool | None = None,
        wallet_balance: dict[str, object] | None = None,
    ) -> list[str]:
        signer = signer if signer is not None else self.signer_status(signer_mode, wallet_public_key)
        caps = caps if caps is not None else self.live_caps_snapshot()
        blockers: list[str] = []
        if not env_live_enabled:
            blockers.append("LIVE_TRADING_ENABLED is false")
        if not wallet_public_key.strip():
            blockers.append("wallet public key is required")
        if not signer.get("connected"):
            blockers.append("no connected signer")
        if not self.settings.live_session_acknowledged:
            blockers.append("live session acknowledgement is required")
        for key, value in caps.items():
            if key == "operator_intent":
                continue
            if float(value or 0) <= 0:
                blockers.append(f"{key} must be set")
        if not self.settings.solana_rpc_url:
            blockers.append("Solana RPC URL is not configured")
        if signer_mode != "browser_wallet" and not signer.get("can_sign"):
            blockers.append(str(signer.get("disabled_reason") or f"{signer_mode.replace('_', ' ')} cannot sign transactions right now"))
        if signer_mode == "local_signer_daemon" and signer.get("ready_to_submit") is not True:
            blockers.append(str(signer.get("disabled_reason") or "local signer daemon requires ready_to_submit=true"))

        wallet_metrics = wallet_metrics if wallet_metrics is not None else self._wallet_live_metrics(wallet_public_key)
        if action == "buy":
            wallet_balance = wallet_balance if wallet_balance is not None else self._entry_wallet_balance_status(wallet_public_key)
            balance_error = str(wallet_balance.get("error") or "") if isinstance(wallet_balance, dict) else ""
            if balance_error:
                blockers.append(f"wallet SOL balance check failed: {balance_error}")
            unresolved = unresolved if unresolved is not None else [audit for audit in self._normalize_live_audits(self.storage.load_live_execution_audits(200)) if self._is_unresolved_live_audit(audit)]
            if unresolved:
                blockers.append("unresolved live audit recovery debt blocks new entries")
            source_health = source_health if source_health is not None else self.source_health()
            source_blocker = self._source_live_entry_blocker(source_health)
            if source_blocker:
                blockers.append(source_blocker)
            replay_halt = self.replay_confidence_halt_reason()
            if replay_halt:
                blockers.append(replay_halt)
            if self.settings.kill_switch_enabled:
                blockers.append("manual kill switch enabled")
            if not signer.get("healthy"):
                blockers.append(f"{signer_mode.replace('_', ' ')} is unhealthy")
            if wallet_metrics["cost_basis_sol"] >= float(self.settings.live_wallet_exposure_cap_sol or 0):
                blockers.append("wallet exposure cap reached")
            if confirmed_buy_spend_over_trade_cap if confirmed_buy_spend_over_trade_cap is not None else self._has_confirmed_buy_spend_over_trade_cap(wallet_public_key):
                blockers.append("confirmed live buy spend exceeded max trade cap; review cap/rent exposure before new buys")
            if wallet_metrics["realized_pnl_sol"] + wallet_metrics["unrealized_pnl_sol"] <= -abs(float(self.settings.live_daily_loss_cap_sol or 0)):
                blockers.append("wallet daily loss cap reached")
            if wallet_metrics["open_positions"] >= float(self.settings.live_max_open_positions or 0):
                blockers.append("wallet max open positions reached")
        else:
            if not signer.get("can_sign"):
                blockers.append(f"{signer_mode.replace('_', ' ')} cannot execute protective exits")

        if autonomous:
            if action == "buy":
                backup = backup if backup is not None else self._pre_run_backup_status()
                if backup.get("blocks_live_entries"):
                    blockers.append(str(backup.get("blocker") or "pre-run backup is required before live entries"))
            stale_balance_positions = stale_balance_positions if stale_balance_positions is not None else self._stale_balance_positions(wallet_public_key)
            if stale_balance_positions:
                blockers.append(f"stale token-balance verification blocks autonomy for {len(stale_balance_positions)} position{'s' if len(stale_balance_positions) != 1 else ''}")
            if not self.settings.autonomous_live_enabled:
                blockers.append("autonomous live is disabled in settings")
            if not self.settings.live_active_backend_armed:
                blockers.append("no active backend is armed")
            if self.settings.live_signer_mode != signer_mode:
                blockers.append("requested backend is not the active live backend")
            if self.settings.live_active_wallet_public_key != wallet_public_key:
                blockers.append("requested wallet is not the armed live wallet")
            if not signer.get("can_unattended_sign"):
                blockers.append(str(signer.get("disabled_reason") or "backend cannot sign unattended transactions"))
            if action == "buy" and not signer.get("supports_auto_buy"):
                blockers.append("active backend does not support autonomous entries")
            if action == "sell" and not signer.get("supports_auto_sell"):
                blockers.append("active backend does not support protective exits")
            readiness_halt = readiness_halt if readiness_halt is not None else self.readiness_halt_reason()
            if readiness_halt and action == "buy":
                blockers.append(readiness_halt)

        return list(dict.fromkeys(blockers))

    def _source_live_entry_blocker(self, source_health: dict[str, object] | None = None) -> str:
        source = source_health or self.source_health()
        status = str(source.get("status") or "unknown")
        trust_state = str(source.get("trust_state") or "unknown")
        last_age = source.get("last_event_age_seconds")
        if status != "connected":
            return "source trust requires PumpPortal source connected before live entries"
        if not isinstance(last_age, (int, float)):
            return "source trust requires a recent PumpPortal source event before live entries"
        if float(last_age) > float(self.settings.source_stale_seconds):
            return f"source trust blocks live entries because the latest source event is older than {self.settings.source_stale_seconds}s"
        if source.get("live_entry_blocked"):
            return f"source trust {trust_state} blocks live entries"
        return ""

    def _source_archive_blocker(self, source_health: dict[str, object] | None = None) -> str:
        source = source_health or self.source_health()
        inspection = source.get("raw_event_inspection", {}) if isinstance(source, dict) else {}
        source_counts = inspection.get("source_counts", {}) if isinstance(inspection, dict) else {}
        pumpportal_events = int(source_counts.get("pumpportal", 0) or 0) if isinstance(source_counts, dict) else 0
        if pumpportal_events <= 0:
            return "archived PumpPortal source events are required before live entries"
        return ""

    def _valid_solana_public_key(self, wallet_public_key: str) -> bool:
        try:
            Pubkey.from_string(wallet_public_key.strip())
            return True
        except Exception:
            return False

    def _entry_wallet_balance_status(self, wallet_public_key: str) -> dict[str, object]:
        wallet = wallet_public_key.strip()
        if not wallet or not self._valid_solana_public_key(wallet):
            return {"wallet_public_key": wallet, "balance_sol": 0.0, "error": "", "checked": False}
        result = self._wallet_sol_balance(wallet)
        return {
            "wallet_public_key": str(result.get("wallet_public_key") or wallet),
            "balance_sol": float(result.get("balance_sol") or 0.0),
            "error": str(result.get("error") or ""),
            "checked": True,
        }

    def _runtime_connectivity_status(
        self,
        *,
        source_health: dict[str, object],
        signer: dict[str, object],
        wallet_balance: dict[str, object],
        unresolved: list[LiveExecutionAudit],
        blockers: list[str],
    ) -> dict[str, object]:
        source_blocker = self._source_live_entry_blocker(source_health)
        balance_error = str(wallet_balance.get("error") or "")
        runtime_blockers = list(dict.fromkeys([
            *([source_blocker] if source_blocker else []),
            *([f"wallet SOL balance check failed: {balance_error}"] if balance_error else []),
            *([str(signer.get("disabled_reason") or "signer is unavailable")] if not signer.get("connected") or not signer.get("healthy") else []),
            *(["unresolved live audit recovery debt blocks new entries"] if unresolved else []),
            *[blocker for blocker in blockers if any(term in blocker.lower() for term in ("source", "rpc", "signer", "recovery", "wallet sol balance", "kill switch"))],
        ]))
        balance_checked = bool(wallet_balance.get("checked"))
        return {
            "source_connected": not source_blocker,
            "rpc_available": not balance_error if balance_checked else True,
            "rpc_balance_checked": balance_checked,
            "signer_available": bool(signer.get("connected")) and bool(signer.get("healthy")) and bool(signer.get("can_sign")),
            "recovery_debt_clear": not unresolved,
            "safe_for_new_entry": not runtime_blockers,
            "blockers": runtime_blockers,
            "operator_action": "Runtime connectivity is clear for a new live entry." if not runtime_blockers else "Resolve runtime connectivity blockers before a new live buy.",
        }

    def replay_confidence_halt_reason(self) -> str | None:
        if not self.settings.halt_on_low_replay_confidence:
            return None
        replay_confidence = int(self.data_integrity_report().get("replay_confidence", {}).get("score", 0))
        if replay_confidence < int(self.settings.min_replay_confidence):
            return f"low replay confidence halt active ({replay_confidence} below {self.settings.min_replay_confidence})"
        return None

    def _active_backend_snapshot(self) -> dict[str, object]:
        return {
            "armed": self.settings.live_active_backend_armed,
            "mode": self.settings.live_signer_mode,
            "wallet_public_key": self.settings.live_active_wallet_public_key,
        }

    def _autonomy_gate_state(
        self,
        action: str,
        blockers: list[str],
        active_backend_matches: bool,
        unresolved_count: int,
    ) -> dict[str, object]:
        action_label = "entry" if action == "buy" else "protective_exit"
        stage = "stage_4_tiny_real_money_pilot" if action == "buy" else "stage_3_protective_exit_automation"
        return {
            "action": action,
            "label": action_label,
            "stage": stage,
            "available": not blockers,
            "blockers": blockers,
            "active_backend_matches": active_backend_matches,
            "recovery_debt_blocks_entries": action == "buy" and unresolved_count > 0,
            "operator_action": "Autonomy can run on the armed backend." if not blockers else "Resolve blockers before unattended execution.",
        }

    def _autonomy_override_status(self, local_auth_enabled: bool = False) -> dict[str, object]:
        return {
            "available": bool(local_auth_enabled),
            "local_auth_enabled": bool(local_auth_enabled),
            "local_only": True,
            "bypass_enabled": False,
            "supported_targets": ["entry_autonomy", "exit_autonomy", "source_trust", "recovery_debt", "signer_boundary"],
            "operator_action": "Override requests are audit-only; they do not bypass live blockers.",
            "disabled_reason": "" if local_auth_enabled else "dashboard password/local auth is not configured",
        }

    def _source_degraded_mode(
        self,
        source: dict[str, object],
        *,
        env_live_enabled: bool,
        sell_blockers: list[str],
    ) -> dict[str, object]:
        trust_state = str(source.get("trust_state") or "unknown")
        live_entry_blocked = bool(source.get("live_entry_blocked"))
        paper_collection_allowed = bool(source.get("paper_collection_allowed", True))
        protective_exits_available = bool(env_live_enabled and not sell_blockers)
        if live_entry_blocked and protective_exits_available:
            mode = "exit_only"
            state = "degraded"
            operator_action = "Source trust blocks new live entries; protective exits can still be prepared through the selected backend."
        elif live_entry_blocked:
            mode = "paper_only"
            state = "degraded"
            operator_action = "Source trust blocks live entries; keep collecting paper evidence and resolve source blockers."
        else:
            mode = "normal"
            state = "ready" if trust_state == "trusted" else "review"
            operator_action = "Source trust does not currently force paper-only or exit-only operation."
        return {
            "mode": mode,
            "state": state,
            "trust_state": trust_state,
            "live_entries_allowed": not live_entry_blocked,
            "paper_collection_allowed": paper_collection_allowed,
            "protective_exits_available": protective_exits_available,
            "entry_blockers": list(source.get("trust_blockers", [])) if isinstance(source.get("trust_blockers"), list) else [],
            "exit_blockers": sell_blockers,
            "operator_action": operator_action,
        }

    def _full_sniper_gate(
        self,
        *,
        autonomy: dict[str, object],
        source_mode: dict[str, object],
        pre_run_backup: dict[str, object],
        manual_live_verification: dict[str, object],
    ) -> dict[str, object]:
        entry = autonomy.get("entry", {}) if isinstance(autonomy, dict) else {}
        exit_gate = autonomy.get("exit", {}) if isinstance(autonomy, dict) else {}
        active_backend_matches = bool(autonomy.get("active_backend_matches")) if isinstance(autonomy, dict) else False
        entry_available = bool(entry.get("available")) if isinstance(entry, dict) else False
        exit_available = bool(exit_gate.get("available")) if isinstance(exit_gate, dict) else False
        source_normal = source_mode.get("mode") == "normal" if isinstance(source_mode, dict) else False
        backup_fresh = bool(pre_run_backup.get("fresh")) if isinstance(pre_run_backup, dict) else False
        manual_live_verified = bool(manual_live_verification.get("verified")) if isinstance(manual_live_verification, dict) else False
        override = autonomy.get("override", {}) if isinstance(autonomy, dict) else {}
        blockers: list[str] = []
        if not active_backend_matches:
            blockers.append("active backend does not match selected wallet")
        if not entry_available:
            blockers.extend(str(item) for item in entry.get("blockers", [])[:5] if isinstance(entry, dict))
        if not exit_available:
            blockers.extend(str(item) for item in exit_gate.get("blockers", [])[:5] if isinstance(exit_gate, dict))
        if not source_normal:
            blockers.append(f"source mode is {source_mode.get('mode', 'unknown') if isinstance(source_mode, dict) else 'unknown'}")
        if not backup_fresh:
            blockers.append(str(pre_run_backup.get("blocker") or "fresh pre-run backup is required"))
        if not manual_live_verified:
            blockers.append(str(manual_live_verification.get("blocker") or "recent manual live verification is required before full sniper automation"))
        blockers = list(dict.fromkeys([blocker for blocker in blockers if blocker]))
        ready = not blockers
        return {
            "mode": "full_sniper",
            "ready": ready,
            "state": "ready" if ready else "blocked",
            "entry_ready": entry_available,
            "exit_ready": exit_available,
            "active_backend_matches": active_backend_matches,
            "source_mode": str(source_mode.get("mode", "unknown") if isinstance(source_mode, dict) else "unknown"),
            "pre_run_backup_fresh": backup_fresh,
            "manual_live_verified": manual_live_verified,
            "manual_live_audit_id": str(manual_live_verification.get("audit_id") or "") if isinstance(manual_live_verification, dict) else "",
            "manual_live_verified_at": manual_live_verification.get("verified_at") if isinstance(manual_live_verification, dict) else None,
            "manual_live_window_hours": manual_live_verification.get("window_hours") if isinstance(manual_live_verification, dict) else None,
            "audited_override_active": False,
            "override_effect": str(override.get("operator_action") or "Override records are audit-only and do not bypass full-sniper blockers.") if isinstance(override, dict) else "Override records are audit-only and do not bypass full-sniper blockers.",
            "blockers": blockers,
            "operator_action": "Full sniper automation can run on the armed local backend." if ready else "Resolve every full-sniper blocker before unattended buys and sells.",
        }

    def _manual_live_verification_status(self, wallet_public_key: str = "", signer_mode: str = "browser_wallet") -> dict[str, object]:
        wallet = wallet_public_key.strip()
        required_signer_mode = signer_mode or "browser_wallet"
        window_hours = 24.0
        cutoff = utc_now() - timedelta(hours=window_hours)
        audits = [
            audit
            for audit in self._normalize_live_audits(self.storage.load_live_execution_audits(500))
            if audit.signer_mode == required_signer_mode
            and audit.created_at >= cutoff
            and (not wallet or audit.wallet_public_key == wallet)
            and (audit.final_status == "reconciled" or audit.status == "reconciled")
            and audit.transaction_signature
            and audit.reconciliation_status == "matched"
            and not audit.errors
        ]
        latest = max(audits, key=lambda audit: audit.created_at, default=None)
        if latest:
            return {
                "verified": True,
                "audit_id": latest.id,
                "verified_at": latest.created_at.isoformat(),
                "window_hours": window_hours,
                "wallet_public_key": latest.wallet_public_key,
                "signer_mode": required_signer_mode,
                "blocker": "",
                "operator_action": f"Recent confirmed and reconciled {required_signer_mode} manual live execution is verified for full-sniper promotion.",
            }
        return {
            "verified": False,
            "audit_id": "",
            "verified_at": None,
            "window_hours": window_hours,
            "wallet_public_key": wallet,
            "signer_mode": required_signer_mode,
            "blocker": f"recent confirmed and reconciled {required_signer_mode} manual live proof is required before full sniper automation",
            "operator_action": f"Complete and reconcile a {required_signer_mode} manual live buy or sell within 24 hours before unattended full-sniper mode.",
        }

    def record_expert_override(
        self,
        local_auth_enabled: bool,
        target_gate: str,
        action: str,
        reason: str,
        wallet_public_key: str = "",
        signer_mode: str | None = None,
    ) -> dict[str, object]:
        override = self._autonomy_override_status(local_auth_enabled)
        if not override["available"]:
            raise ValueError(str(override["disabled_reason"]))
        target_gate = target_gate.strip()
        action = action.strip() or "buy"
        if target_gate not in override["supported_targets"]:
            raise ValueError("unsupported override target")
        if action not in {"buy", "sell"}:
            raise ValueError("override action must be buy or sell")
        reason = reason.strip()
        if len(reason) < 12:
            raise ValueError("override reason must be at least 12 characters")
        signer_mode = signer_mode or self.settings.live_signer_mode
        wallet = self._resolve_backend_wallet(signer_mode, wallet_public_key)
        blockers = self._live_execution_blockers(True, action, wallet, signer_mode, autonomous=True)
        event = {
            "target_gate": target_gate,
            "action": action,
            "wallet_public_key": wallet,
            "signer_mode": signer_mode,
            "reason": reason,
            "risk_state": {
                "blockers": blockers,
                "active_backend": self._active_backend_snapshot(),
                "kill_switch_enabled": self.settings.kill_switch_enabled,
                "caps": self.live_caps_snapshot(),
            },
            "recorded_at": utc_now().isoformat(),
            "effect": "audit_only_no_gate_bypass",
        }
        self.add_event(
            "warning",
            f"Expert override recorded for {target_gate} / {action}",
            subsystem="live",
            operator_action=json.dumps(event, sort_keys=True),
        )
        return event

    def live_status(self, env_live_enabled: bool = False, wallet_public_key: str = "", signer_mode: str | None = None, local_auth_enabled: bool = False) -> dict[str, object]:
        signer_mode = signer_mode or self.settings.live_signer_mode
        wallet_public_key = self._resolve_backend_wallet(signer_mode, wallet_public_key)
        signer = self.signer_status(signer_mode, wallet_public_key)
        caps = self.live_caps_snapshot()
        readiness = self._recent_readiness_status()
        source_health = self.source_health()
        wallet_metrics = self._wallet_live_metrics(wallet_public_key)
        audit_rows = self._normalize_live_audits(self.storage.load_live_execution_audits(200))
        unresolved = [audit for audit in audit_rows if self._is_unresolved_live_audit(audit)]
        backup = self._pre_run_backup_status()
        stale_balance_positions = self._stale_balance_positions(wallet_public_key)
        readiness_halt = self.readiness_halt_reason(readiness)
        confirmed_buy_spend_over_trade_cap = self._has_confirmed_buy_spend_over_trade_cap(wallet_public_key)
        wallet_balance = self._entry_wallet_balance_status(wallet_public_key)
        blocker_context = {
            "signer": signer,
            "caps": caps,
            "wallet_metrics": wallet_metrics,
            "unresolved": unresolved,
            "source_health": source_health,
            "backup": backup,
            "stale_balance_positions": stale_balance_positions,
            "readiness_halt": readiness_halt,
            "confirmed_buy_spend_over_trade_cap": confirmed_buy_spend_over_trade_cap,
            "wallet_balance": wallet_balance,
        }
        blockers = self._live_execution_blockers(env_live_enabled, "buy", wallet_public_key, signer_mode, autonomous=False, **blocker_context)
        sell_blockers = self._live_execution_blockers(env_live_enabled, "sell", wallet_public_key, signer_mode, autonomous=False, **blocker_context)
        autonomy_buy_blockers = self._live_execution_blockers(env_live_enabled, "buy", wallet_public_key, signer_mode, autonomous=True, **blocker_context)
        autonomy_sell_blockers = self._live_execution_blockers(env_live_enabled, "sell", wallet_public_key, signer_mode, autonomous=True, **blocker_context)
        execution_readiness = readiness.get("execution_readiness") if isinstance(readiness.get("execution_readiness"), dict) else self._execution_readiness_status(
            source=source_health,
            strategy_promotion=readiness.get("strategy_promotion") if isinstance(readiness, dict) else None,
            env_live_enabled=env_live_enabled,
            wallet_public_key=wallet_public_key,
            signer_mode=signer_mode,
        )
        intents = self._decorate_live_intents(self._mark_stale_live_intents(self.storage.load_live_intents(200)), readiness)
        ledger = self._live_ledger_positions(wallet_public_key)
        recoverable = [audit for audit in unresolved if audit.transaction_signature]
        stale_quotes = sum(1 for intent in intents if intent.stale and intent.quote_id)
        latest_reconciliation = next((position.reconciliation_status for position in ledger), "pending")
        autonomy_blockers = list(dict.fromkeys([*autonomy_buy_blockers, *autonomy_sell_blockers]))
        active_backend = self._active_backend_snapshot()
        active_backend_matches = (
            bool(active_backend["armed"])
            and active_backend["mode"] == signer_mode
            and active_backend["wallet_public_key"] == wallet_public_key
        )
        autonomy = {
            "entry": self._autonomy_gate_state("buy", autonomy_buy_blockers, active_backend_matches, len(unresolved)),
            "exit": self._autonomy_gate_state("sell", autonomy_sell_blockers, active_backend_matches, len(unresolved)),
            "active_backend_matches": active_backend_matches,
            "recovery_debt": {
                "unresolved_audits": len(unresolved),
                "recoverable_audits": len(recoverable),
                "blocks_new_entries": len(unresolved) > 0,
            },
            "override": self._autonomy_override_status(local_auth_enabled),
        }
        mode_visibility = self._live_mode_visibility(
            env_live_enabled=env_live_enabled,
            blockers=blockers,
            execution_readiness=execution_readiness,
            signer=signer,
            autonomy=autonomy,
            active_backend=active_backend,
        )
        live_pnl = {**wallet_metrics, "open_positions": int(wallet_metrics["open_positions"]), "approximate": True}
        pre_run_backup = backup
        source_degraded_mode = self._source_degraded_mode(source_health, env_live_enabled=env_live_enabled, sell_blockers=sell_blockers)
        runtime_connectivity = self._runtime_connectivity_status(
            source_health=source_health,
            signer=signer,
            wallet_balance=wallet_balance,
            unresolved=unresolved,
            blockers=blockers,
        )
        manual_live_verification = self._manual_live_verification_status(wallet_public_key, signer_mode)
        full_sniper_gate = self._full_sniper_gate(
            autonomy=autonomy,
            source_mode=source_degraded_mode,
            pre_run_backup=pre_run_backup,
            manual_live_verification=manual_live_verification,
        )
        backend_capabilities = {
            "browser_wallet": self.signer_status("browser_wallet", wallet_public_key if signer_mode == "browser_wallet" else ""),
            "local_hot_wallet": self.signer_status("local_hot_wallet", self.hot_wallet.wallet_public_key()),
            "local_signer_daemon": self.signer_status("local_signer_daemon", ""),
        }
        execution_backend = self._execution_backend_status(
            signer_mode=signer_mode,
            signer=signer,
            env_live_enabled=env_live_enabled,
            active_backend_matches=active_backend_matches,
        )
        return {
            "mode": "autonomous_live_v1",
            "paper_default": False,
            "live_execution_available": not blockers,
            "env_live_enabled": env_live_enabled,
            "effective_live_enabled": not blockers,
            "blockers": blockers,
            "signer": signer,
            "caps": caps,
            "session_acknowledged": self.settings.live_session_acknowledged,
            "readiness": readiness,
            "execution_readiness": execution_readiness,
            "local_desktop_only": True,
            "autonomous_live_available": not autonomy_buy_blockers or not autonomy_sell_blockers,
            "auto_sell_available": not autonomy_sell_blockers,
            "auto_buy_available": not autonomy_buy_blockers,
            "autonomy_blockers": autonomy_blockers,
            "autonomy": autonomy,
            "mode_visibility": mode_visibility,
            "source_degraded_mode": source_degraded_mode,
            "runtime_connectivity": runtime_connectivity,
            "full_sniper_gate": full_sniper_gate,
            "manual_live_verification": manual_live_verification,
            "pre_run_backup": pre_run_backup,
            "active_intent_count": len([intent for intent in intents if intent.status not in {"cancelled", "executed", "expired"}]),
            "stale_quote_count": stale_quotes,
            "unresolved_audit_count": len(unresolved),
            "recoverable_audit_count": len(recoverable),
            "last_live_poll_at": self.live_last_poll_at.isoformat() if self.live_last_poll_at else None,
            "poller_status": "enabled" if env_live_enabled else "disabled",
            "recovery_summary": self.live_last_poll_summary,
            "latest_reconciliation_status": latest_reconciliation,
            "wallet_adapter": {
                "mode": signer_mode,
                "manual_approval_required": signer_mode == "browser_wallet",
                "can_sign": bool(signer.get("can_sign")),
                "can_unattended_sign": bool(signer.get("can_unattended_sign")),
                "supports_auto_sell": bool(signer.get("supports_auto_sell")),
                "supports_auto_buy": bool(signer.get("supports_auto_buy")),
                "disabled_reason": str(signer.get("disabled_reason") or ""),
            },
            "execution_backend": execution_backend,
            "signer_readiness": {
                "mode": signer_mode,
                "healthy": bool(signer.get("healthy")),
                "ready_to_submit": signer.get("ready_to_submit") is True,
                "endpoint": str(signer.get("endpoint") or ""),
                "transport": str(signer.get("transport") or ""),
                "auth_configured": bool(signer.get("auth_configured")),
            },
            "live_pnl": live_pnl,
            "readiness_warnings": readiness.get("recommended_actions", []) if readiness.get("status") != "ready" else [],
            "hot_wallet": self.hot_wallet.status(),
            "active_backend": active_backend,
            "backend_capabilities": backend_capabilities,
            "entry_autonomy_available": not autonomy_buy_blockers,
            "exit_autonomy_available": not autonomy_sell_blockers,
        }

    def _execution_backend_status(self, signer_mode: str, signer: dict[str, object], env_live_enabled: bool, active_backend_matches: bool) -> dict[str, object]:
        if signer_mode == "browser_wallet":
            submit_path = "browser_wallet_manual_signature"
            implemented = True
            local_only = True
            manual_approval_required = True
            unattended_submit = False
            operator_action = "Use browser wallet approval for each manual live submit."
        elif signer_mode == "local_hot_wallet":
            submit_path = "encrypted_local_hot_wallet"
            implemented = True
            local_only = True
            manual_approval_required = False
            unattended_submit = bool(signer.get("can_unattended_sign"))
            operator_action = "Keep the encrypted hot wallet unlocked only for the local session and use tiny caps."
        elif signer_mode == "local_signer_daemon":
            submit_path = "localhost_signer_daemon"
            implemented = signer.get("ready_to_submit") is True and bool(signer.get("can_sign"))
            local_only = str(signer.get("transport") or "") == "localhost_http"
            manual_approval_required = False
            unattended_submit = signer.get("ready_to_submit") is True and bool(signer.get("can_unattended_sign"))
            operator_action = "Run a localhost-only signer daemon with auth before selecting this backend."
        else:
            submit_path = "unsupported"
            implemented = False
            local_only = False
            manual_approval_required = True
            unattended_submit = False
            operator_action = "Select browser_wallet or local_hot_wallet before live execution."

        blockers: list[str] = []
        if not env_live_enabled:
            blockers.append("LIVE_TRADING_ENABLED is false")
        if not implemented:
            blockers.append(f"{signer_mode} submit path is not implemented or not connected")
        if not bool(signer.get("can_sign")):
            blockers.append(str(signer.get("disabled_reason") or f"{signer_mode.replace('_', ' ')} cannot sign transactions"))
        if signer_mode == "local_signer_daemon" and signer.get("ready_to_submit") is not True:
            blockers.append(str(signer.get("disabled_reason") or "local signer daemon requires ready_to_submit=true"))
        if not local_only:
            blockers.append("execution backend must stay localhost/local-file only")
        if signer_mode != "browser_wallet" and not active_backend_matches:
            blockers.append("backend must be armed for this wallet before unattended submit")
        return {
            "mode": signer_mode,
            "submit_path": submit_path,
            "implemented": implemented,
            "local_only": local_only,
            "manual_approval_required": manual_approval_required,
            "unattended_submit_available": unattended_submit and implemented and not blockers,
            "can_submit_now": implemented and bool(signer.get("can_sign")) and env_live_enabled and local_only and (signer_mode == "browser_wallet" or active_backend_matches),
            "blockers": list(dict.fromkeys(blockers)),
            "operator_action": operator_action,
        }

    def _live_mode_visibility(
        self,
        *,
        env_live_enabled: bool,
        blockers: list[str],
        execution_readiness: dict[str, object],
        signer: dict[str, object],
        autonomy: dict[str, object],
        active_backend: dict[str, object],
    ) -> list[dict[str, object]]:
        paper_mode = self.settings.mode.value if hasattr(self.settings.mode, "value") else str(self.settings.mode)
        shadow_ready = bool(execution_readiness.get("can_shadow")) if isinstance(execution_readiness, dict) else False
        manual_available = env_live_enabled and not blockers and bool(signer.get("can_sign"))
        active_backend_matches = bool(autonomy.get("active_backend_matches")) if isinstance(autonomy, dict) else False
        entry = autonomy.get("entry", {}) if isinstance(autonomy, dict) else {}
        exit_gate = autonomy.get("exit", {}) if isinstance(autonomy, dict) else {}
        auto_buy = bool(entry.get("available")) if isinstance(entry, dict) else False
        auto_sell = bool(exit_gate.get("available")) if isinstance(exit_gate, dict) else False
        armed = bool(active_backend.get("armed")) if isinstance(active_backend, dict) else False
        return [
            {
                "id": "paper",
                "label": "Paper",
                "state": "active" if paper_mode == "paper" else "available",
                "tone": "emerald",
                "summary": "Default simulated trading and evidence collection.",
                "blockers": [],
            },
            {
                "id": "shadow",
                "label": "Shadow",
                "state": "ready" if shadow_ready else "blocked",
                "tone": "sky",
                "summary": "Would-have-traded comparison without submitting transactions.",
                "blockers": [] if shadow_ready else list(execution_readiness.get("blockers", []))[:3] if isinstance(execution_readiness, dict) else [],
            },
            {
                "id": "manual_live",
                "label": "Manual Live",
                "state": "ready" if manual_available else "blocked",
                "tone": "amber",
                "summary": "Quote, simulate, and submit only with local operator approval.",
                "blockers": blockers[:3],
            },
            {
                "id": "autonomous_live",
                "label": "Autonomous Live",
                "state": "ready" if armed and active_backend_matches and (auto_buy or auto_sell) else "blocked",
                "tone": "rose",
                "summary": "Unattended entry or exit execution through the armed local backend.",
                "blockers": list(dict.fromkeys([
                    *(["backend is not armed"] if not armed else []),
                    *(["active backend does not match selected wallet"] if armed and not active_backend_matches else []),
                    *(entry.get("blockers", []) if isinstance(entry, dict) else []),
                    *(exit_gate.get("blockers", []) if isinstance(exit_gate, dict) else []),
                ]))[:3],
            },
        ]

    def start_live_session(self, env_live_enabled: bool, wallet_public_key: str, signer_mode: str = "browser_wallet") -> dict[str, object]:
        wallet_public_key = self._resolve_backend_wallet(signer_mode, wallet_public_key)
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
        self.active_live_session_id = session.id
        self.add_event(
            "warning",
            f"Live session {session.status}: {', '.join(status['blockers']) or f'{signer_mode} ready'}",
            subsystem="live",
            operator_action="Resolve live blockers, then arm the backend if you want autonomous execution.",
        )
        return {**session.to_dict(), "live_status": status}

    def acknowledge_live_session(self) -> dict[str, object]:
        self.settings.live_session_acknowledged = True
        self.storage.save_settings(self.settings)
        acknowledged_at = utc_now().isoformat()
        self.add_event(
            "warning",
            "Live session acknowledgement recorded",
            subsystem="live",
            operator_action=json.dumps(
                {
                    "acknowledged_at": acknowledged_at,
                    "caps": self.live_caps_snapshot(),
                    "active_backend": self._active_backend_snapshot(),
                    "kill_switch_enabled": self.settings.kill_switch_enabled,
                    "effect": "session_risk_acknowledged",
                },
                sort_keys=True,
            ),
        )
        return {"acknowledged": True, "acknowledged_at": acknowledged_at, "risk_state": self.live_risk_state()}

    def set_live_kill_switch(self, enabled: bool, reason: str = "") -> dict[str, object]:
        previous = self.settings.kill_switch_enabled
        self.settings.kill_switch_enabled = bool(enabled)
        self.storage.save_settings(self.settings)
        changed_at = utc_now().isoformat()
        risk_state = self.live_risk_state()
        self.add_event(
            "danger" if enabled else "warning",
            f"Live kill switch {'enabled' if enabled else 'disabled'}",
            subsystem="live",
            operator_action=json.dumps(
                {
                    "previous": previous,
                    "enabled": bool(enabled),
                    "changed_at": changed_at,
                    "reason": reason.strip(),
                    "risk_state": risk_state,
                    "effect": "blocks_new_entries" if enabled else "allows_entries_when_other_gates_pass",
                },
                sort_keys=True,
            ),
        )
        return {"kill_switch_enabled": self.settings.kill_switch_enabled, "changed_at": changed_at, "previous": previous, "risk_state": risk_state}

    def live_risk_state(self) -> dict[str, object]:
        return {
            "session_acknowledged": self.settings.live_session_acknowledged,
            "kill_switch_enabled": self.settings.kill_switch_enabled,
            "autonomous_live_enabled": self.settings.autonomous_live_enabled,
            "active_backend": self._active_backend_snapshot(),
            "caps": self.live_caps_snapshot(),
            "source_trust": self.source_health().get("trust_state", "unknown"),
            "unresolved_audit_count": len([audit for audit in self.storage.load_live_execution_audits(200) if self._is_unresolved_live_audit(audit)]),
        }

    def live_positions(self, wallet_public_key: str = "") -> list[dict[str, object]]:
        if not wallet_public_key.strip():
            return []
        wallet = wallet_public_key.strip()
        mints = {
            position.mint
            for position in self.storage.load_live_ledger_positions(500)
            if position.wallet_public_key == wallet and position.status == "open" and position.token_balance > 0 and position.mint
        }
        positions: list[dict[str, object]] = []
        for mint in sorted(mints):
            token = next((item for item in self.storage.load_all_tokens(5000) if item.mint == mint), None)
            warning = ""
            balance = 0.0
            try:
                balance = SolanaReadOnlyClient(self.settings.solana_rpc_url).token_balance(wallet, mint) or 0.0
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
        return [audit.to_dict() for audit in self._refresh_shadow_comparisons(self._normalize_live_audits(self.storage.load_live_execution_audits(100)))]

    def profit_sweep_history(self, limit: int = 100) -> list[dict[str, object]]:
        normalized = self._refresh_shadow_comparisons(self._normalize_live_audits(self.storage.load_live_execution_audits(500)))
        audits = [audit for audit in normalized if audit.action == "profit_sweep"]
        audits.sort(key=lambda audit: audit.created_at, reverse=True)
        return [audit.to_dict() for audit in audits[: max(1, int(limit or 100))]]

    def _normalize_live_audits(self, audits: list[LiveExecutionAudit]) -> list[LiveExecutionAudit]:
        now = utc_now()
        for audit in audits:
            expires_at = audit.quote.get("expires_at") if isinstance(audit.quote, dict) else None
            if expires_at and audit.status in {"ready", "simulated", "simulation_warning"} and not audit.transaction_signature:
                try:
                    if datetime.fromisoformat(str(expires_at)) < now:
                        audit.status = "stale"
                        audit.final_status = "stale"
                        audit.recommended_action = "Regenerate the quote before signing."
                        audit.updated_at = now
                        if isinstance(audit.quote, dict):
                            audit.quote["stale"] = True
                        self.storage.save_live_execution_audit(audit)
                except ValueError:
                    audit.status = "needs_review"
                    audit.final_status = "needs_review"
                    audit.last_recovery_error = "Quote expiry timestamp is invalid"
                    audit.recommended_action = "Review the audit record and regenerate the quote."
                    audit.updated_at = now
                    self.storage.save_live_execution_audit(audit)
        return audits

    def _is_unresolved_live_audit(self, audit: LiveExecutionAudit) -> bool:
        if isinstance(audit.quote, dict) and audit.quote.get("shadow_only"):
            return False
        if audit.status == "stale" and not audit.transaction_signature:
            return False
        if audit.status in {"submitting", "submitted", "needs_review", "failed", "stale"}:
            return True
        if audit.transaction_signature and audit.status not in {"reconciled"} and audit.reconciliation_status != "matched":
            return True
        return False

    def live_intents(self) -> list[dict[str, object]]:
        intents = self._decorate_live_intents(self._mark_stale_live_intents(self.storage.load_live_intents(200)))
        return [intent.to_dict() for intent in self._rank_live_intents(intents)[:100]]

    def live_ledger(self, wallet_public_key: str = "") -> dict[str, object]:
        positions = self._live_ledger_positions(wallet_public_key)
        confidence_counts: dict[str, int] = {}
        stale_marks = 0
        needs_review = 0
        for position in positions:
            confidence_counts[position.unrealized_pnl_confidence] = confidence_counts.get(position.unrealized_pnl_confidence, 0) + 1
            if position.mark_price_age_seconds is not None and position.mark_price_age_seconds > self.settings.source_stale_seconds:
                stale_marks += 1
            if position.reconciliation_status == "needs_review":
                needs_review += 1
        stale_balance_positions = self._stale_balance_positions(wallet_public_key)
        realized_pnl = round(sum(position.realized_pnl_sol for position in positions), 6)
        unrealized_pnl = round(sum(position.unrealized_pnl_sol for position in positions), 6)
        total_pnl = round(realized_pnl + unrealized_pnl, 6)
        recent_fills = self._recent_live_fills(positions)
        return {
            "positions": [position.to_dict() for position in positions],
            "recent_fills": recent_fills,
            "summary": {
                "realized_pnl_sol": realized_pnl,
                "unrealized_pnl_sol": unrealized_pnl,
                "net_pnl_sol": total_pnl,
                "total_pnl_sol": total_pnl,
                "cost_basis_sol": round(sum(position.cost_basis_sol for position in positions), 6),
                "total_fees_sol": round(sum(position.total_fees_sol for position in positions), 9),
                "total_priority_fees_sol": round(sum(position.total_priority_fees_sol for position in positions), 9),
                "open_positions": len([position for position in positions if position.status == "open"]),
                "approximate": True,
                "pnl_confidence": "needs_review" if needs_review else "stale" if stale_marks else "estimated" if positions else "none",
                "confidence_counts": confidence_counts,
                "stale_mark_positions": stale_marks,
                "stale_balance_positions": len(stale_balance_positions),
                "needs_review_positions": needs_review,
                "pnl_note": "Live PnL is approximate until wallet balances, fills, and mark prices are reconciled.",
                "wallet_public_key": wallet_public_key,
            },
        }

    def _recent_live_fills(self, positions: list[LiveLedgerPosition], limit: int = 12) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for position in positions:
            for fill in position.fills:
                accounting = fill.get("accounting") if isinstance(fill.get("accounting"), dict) else {}
                rows.append(
                    {
                        "id": fill.get("id", ""),
                        "created_at": fill.get("created_at", ""),
                        "position_id": position.id,
                        "wallet_public_key": position.wallet_public_key,
                        "mint": position.mint,
                        "symbol": position.symbol,
                        "action": fill.get("action", ""),
                        "amount": fill.get("amount", ""),
                        "signature": fill.get("signature", ""),
                        "fee_sol": round(float(fill.get("fee_sol", 0.0) or 0.0), 9),
                        "priority_fee_sol": round(float(fill.get("priority_fee_sol", 0.0) or 0.0), 9),
                        "wallet_sol_delta_sol": round(float(accounting.get("wallet_sol_delta_sol", 0.0) or 0.0), 9),
                        "wallet_sol_received_sol": round(float(accounting.get("wallet_sol_received_sol", 0.0) or 0.0), 9),
                        "wallet_sol_spent_sol": round(float(accounting.get("wallet_sol_spent_sol", 0.0) or 0.0), 9),
                        "token_delta": round(float(accounting.get("token_delta", 0.0) or 0.0), 9),
                        "realized_pnl_delta_sol": round(float(accounting.get("realized_pnl_delta_sol", 0.0) or 0.0), 9),
                        "provenance": accounting.get("provenance", "estimated"),
                        "reconciliation_status": position.reconciliation_status,
                    }
                )
        return sorted(rows, key=lambda row: str(row.get("created_at") or ""), reverse=True)[:limit]

    def create_live_intent(
        self,
        action: str,
        mint: str,
        amount: str,
        denominated_in_sol: bool,
        wallet_public_key: str,
        signer_mode: str = "browser_wallet",
        source: str = "manual",
        reason: str = "",
        symbol: str = "",
        score: int = 0,
    ) -> dict[str, object]:
        if action not in {"buy", "sell"}:
            raise ValueError("action must be buy or sell")
        wallet_public_key = self._resolve_backend_wallet(signer_mode, wallet_public_key)
        now = utc_now()
        intent = LiveExecutionIntent(
            id=new_id("intent"),
            created_at=now,
            updated_at=now,
            action=action,
            mint=mint.strip(),
            amount=str(amount).strip(),
            denominated_in_sol=denominated_in_sol,
            signer_mode=signer_mode,
            wallet_public_key=wallet_public_key.strip(),
            status="open",
            reason=reason.strip() or f"{source} live intent",
            source=source,
            symbol=symbol,
            score=int(score or 0),
            priority=float(score or 0),
            expires_at=now + timedelta(seconds=30),
            priority_reason=f"{source} intent",
        )
        self._decorate_live_intent(intent)
        self.storage.save_live_intent(intent)
        return intent.to_dict()

    def generate_live_intents(self, wallet_public_key: str, signer_mode: str = "browser_wallet", include_watchlist: list[str] | None = None) -> list[dict[str, object]]:
        wallet_public_key = self._resolve_backend_wallet(signer_mode, wallet_public_key)
        existing = [intent for intent in self.storage.load_live_intents(200) if intent.status in {"open", "quoted", "simulation_warning", "simulated"}]
        existing_keys = {(intent.action, intent.mint) for intent in existing}
        candidates: list[LiveExecutionIntent] = []
        now = utc_now()
        readiness = self.readiness_status()
        for token in self.tokens:
            if len(existing) + len(candidates) >= 10:
                break
            if token.mint and token.score >= self.settings.score_threshold and ("buy", token.mint) not in existing_keys:
                candidates.append(
                    LiveExecutionIntent(
                        id=new_id("intent"),
                        created_at=now,
                        updated_at=now,
                        action="buy",
                        mint=token.mint,
                        amount=str(min(max(self.settings.live_max_trade_sol or self.settings.trade_size_sol, 0.0), self.settings.trade_size_sol)),
                        denominated_in_sol=True,
                        signer_mode=signer_mode,
                        wallet_public_key=wallet_public_key.strip(),
                        status="open",
                        reason=f"Promoted paper decision: score {token.score}",
                        source="paper_promoted",
                        symbol=token.symbol,
                        score=token.score,
                        priority=float(token.score) + float(token.price_confidence or 0) * 10,
                        expires_at=now + timedelta(seconds=30),
                        priority_reason=f"Paper edge score {token.score} with price confidence {float(token.price_confidence or 0):.2f}",
                    )
                )
        for mint in include_watchlist or []:
            if len(existing) + len(candidates) >= 10:
                break
            if mint and ("buy", mint) not in existing_keys:
                candidates.append(
                    LiveExecutionIntent(
                        id=new_id("intent"),
                        created_at=now,
                        updated_at=now,
                        action="buy",
                        mint=mint.strip(),
                        amount=str(self.settings.live_max_trade_sol or self.settings.trade_size_sol),
                        denominated_in_sol=True,
                        signer_mode=signer_mode,
                        wallet_public_key=wallet_public_key.strip(),
                        status="open",
                        reason="Watchlist/manual mint candidate",
                        source="watchlist",
                        score=0,
                        priority=0,
                        expires_at=now + timedelta(seconds=30),
                        priority_reason="Operator watchlist candidate",
                    )
                )
        for position in self.storage.load_live_ledger_positions(200):
            if len(existing) + len(candidates) >= 10:
                break
            if position.status == "open" and position.token_balance > 0 and ("sell", position.mint) not in existing_keys:
                exit_signals = self._live_position_exit_signals(position)
                if not exit_signals:
                    continue
                top_signal = exit_signals[0]
                candidates.append(
                    LiveExecutionIntent(
                        id=new_id("intent"),
                        created_at=now,
                        updated_at=now,
                        action="sell",
                        mint=position.mint,
                        amount="100%",
                        denominated_in_sol=False,
                        signer_mode=signer_mode,
                        wallet_public_key=wallet_public_key.strip(),
                        status="open",
                        reason=str(top_signal["reason"]),
                        source="live_position_rules",
                        symbol=position.symbol,
                        score=int(top_signal["score"]),
                        priority=float(top_signal["priority"]),
                        expires_at=now + timedelta(seconds=30),
                        priority_reason=str(top_signal["priority_reason"]),
                        generated_from_position=True,
                        generated_position_id=position.id,
                        generated_position_version=int(position.version),
                        generated_position_token_balance=float(
                            position.token_balance
                        ),
                        operator_recommendation="Review the triggered risk condition, then use manual quote/sign if you want to exit now.",
                    )
                )
        updated_candidates: list[LiveExecutionIntent] = []
        for intent in candidates:
            self._decorate_live_intent(intent, readiness)
            self.storage.save_live_intent(intent)
            if intent.source == "paper_promoted":
                try:
                    self.quote_live_intent(
                        False,
                        intent.id,
                        self.settings.live_max_slippage_pct,
                        self.settings.live_priority_fee_cap_sol,
                        "pump",
                        shadow_only=True,
                    )
                    updated_candidates.append(self.storage.load_live_intent(intent.id) or intent)
                except Exception as exc:
                    intent.warnings.append(f"Automatic shadow quote failed: {exc}")
                    intent.updated_at = utc_now()
                    self.storage.save_live_intent(intent)
                    self._record_shadow_quote_failure_for_token(intent.mint, str(exc))
                    updated_candidates.append(intent)
            else:
                updated_candidates.append(intent)
        ranked = self._rank_live_intents(self._decorate_live_intents(existing + updated_candidates, readiness))[:10]
        return [intent.to_dict() for intent in ranked]

    def cancel_live_intent(self, intent_id: str) -> dict[str, object]:
        intent = self._require_live_intent(intent_id)
        intent.status = "cancelled"
        intent.updated_at = utc_now()
        intent.version += 1
        self.storage.save_live_intent(intent)
        return intent.to_dict()

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
        shadow_only: bool = False,
    ) -> dict[str, object]:
        wallet_public_key = self._resolve_backend_wallet(signer_mode, wallet_public_key)
        status = self.live_status(env_live_enabled, wallet_public_key, signer_mode)
        quote_env_enabled = bool(env_live_enabled) or bool(shadow_only)
        blockers = [] if shadow_only else self._live_execution_blockers(quote_env_enabled, action, wallet_public_key, signer_mode, autonomous=False)
        validation_error = self._validate_live_order(action, amount, denominated_in_sol, slippage_pct, priority_fee_sol, wallet_public_key, signer_mode, shadow_only=shadow_only)
        if validation_error:
            blockers.append(validation_error)
        wallet_spend_estimate: dict[str, object] = {}
        if action == "buy" and denominated_in_sol:
            wallet_spend_estimate = self._estimate_live_buy_wallet_spend(amount, priority_fee_sol)
            if not shadow_only and wallet_spend_estimate.get("exceeds_max_trade_cap"):
                blockers.append(
                    f"estimated wallet spend exceeds live max trade cap ({wallet_spend_estimate['estimated_wallet_spend_sol']:.6f} SOL > {wallet_spend_estimate['max_trade_cap_sol']:.6f} SOL)"
                )
        preflight_checks = self._live_order_preflight_checks(
            env_live_enabled=quote_env_enabled,
            action=action,
            mint=mint,
            amount=amount,
            denominated_in_sol=denominated_in_sol,
            slippage_pct=slippage_pct,
            priority_fee_sol=priority_fee_sol,
            pool=pool,
            wallet_public_key=wallet_public_key,
            signer_mode=signer_mode,
            blockers=blockers,
            shadow_only=shadow_only,
        )
        if wallet_spend_estimate:
            preflight_checks.append(
                self._preflight_check(
                    "estimated_wallet_spend",
                    "Estimated Wallet Spend",
                    "fail" if wallet_spend_estimate.get("exceeds_max_trade_cap") and not shadow_only else "pass",
                    wallet_spend_estimate,
                    "<= live max trade cap",
                    "Buy previews must estimate full wallet spend, including first-token account setup rent and network fees.",
                )
            )
            if wallet_spend_estimate.get("rent_dominates_trade"):
                preflight_checks.append(
                    self._preflight_check(
                        "rent_dominance",
                        "Setup Rent Dominance",
                        "warn" if not shadow_only else "pass",
                        wallet_spend_estimate.get("wallet_spend_to_trade_ratio"),
                        "<= 2x requested buy",
                        "Token-account setup rent dominates this dust buy; use a larger proof size or an existing token account if practical.",
                    )
                )
        if action == "sell":
            balance = self._wallet_token_balance(wallet_public_key, mint)
            if balance["error"]:
                blockers.append(f"wallet token balance check failed: {balance['error']}")
                preflight_checks.append(self._preflight_check("wallet_token_balance", "Wallet Token Balance", "fail", "checked", "available for sell", str(balance["error"])))
        else:
            balance = {"wallet_public_key": wallet_public_key, "mint": mint, "token_balance": None, "error": ""}

        intent = LiveExecutionIntent(
            id=new_id("intent"),
            created_at=utc_now(),
            updated_at=utc_now(),
            action=action,
            mint=mint.strip(),
            amount=str(amount).strip(),
            denominated_in_sol=denominated_in_sol,
            signer_mode=signer_mode,
            wallet_public_key=wallet_public_key.strip(),
            status="blocked" if blockers else "quote_requested",
            reason="; ".join(blockers),
            expires_at=utc_now() + timedelta(seconds=30),
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
            expires_at=utc_now() + timedelta(seconds=30),
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
            preflight_checks=preflight_checks,
            quote={**quote.to_dict(), "provider_request": quote_payload},
            caps_snapshot=self.live_caps_snapshot(),
            balance_snapshot=balance,
            errors=blockers,
            warnings=(
                ["Shadow-only quote is evidence-only and cannot be submitted"] if shadow_only and not env_live_enabled else ["Simulation warnings do not absolutely block manual signing"] if not blockers else []
            )
            + (["Token-account setup rent dominates this buy; review total wallet spend before signing."] if wallet_spend_estimate.get("rent_dominates_trade") and not blockers else []),
            final_status=quote.status,
            intent_id=intent.id,
        )
        audit.quote["shadow_only"] = bool(shadow_only)
        audit.quote["live_env_enabled_at_quote"] = bool(env_live_enabled)
        if wallet_spend_estimate:
            audit.quote["wallet_spend_estimate"] = wallet_spend_estimate
        audit.shadow_comparison = self._build_shadow_comparison(audit)
        intent.quote_id = quote.id
        intent.audit_id = audit.id
        intent.status = "blocked" if blockers else "quoted"
        intent.reason = "; ".join(blockers) if blockers else "Quote preview ready"
        self.storage.save_live_intent(intent)
        self.storage.save_live_execution_audit(audit)
        self.add_event("warning", f"Live {action} quote {quote.status} for {mint[:8] or 'unknown'}", subsystem="live")
        return audit.to_dict()

    def _estimate_live_buy_wallet_spend(self, amount: str, priority_fee_sol: float) -> dict[str, object]:
        try:
            requested_amount = max(0.0, float(str(amount).replace("%", "")))
        except ValueError:
            requested_amount = 0.0
        priority_fee = max(0.0, float(priority_fee_sol or 0.0))
        base_fee = round(SOLANA_SIGNATURE_BASE_FEE_LAMPORTS / LAMPORTS_PER_SOL, 9)
        network_fee = round(base_fee + priority_fee, 9)
        setup_rent = LIVE_BUY_TOKEN_ACCOUNT_SETUP_RENT_SOL
        program_fee_buffer = LIVE_BUY_PROGRAM_FEE_BUFFER_SOL
        estimated = round(requested_amount + network_fee + setup_rent + program_fee_buffer, 9)
        cap = round(float(self.settings.live_max_trade_sol or 0.0), 9)
        spend_ratio = round(estimated / requested_amount, 4) if requested_amount > 0 else 0.0
        rent_ratio = round(setup_rent / requested_amount, 4) if requested_amount > 0 else 0.0
        return {
            "estimated_wallet_spend_sol": estimated,
            "requested_amount_sol": round(requested_amount, 9),
            "max_trade_cap_sol": cap,
            "exceeds_max_trade_cap": bool(cap > 0 and estimated > cap),
            "wallet_spend_to_trade_ratio": spend_ratio,
            "setup_rent_to_trade_ratio": rent_ratio,
            "rent_dominates_trade": bool(requested_amount > 0 and spend_ratio > 2.0),
            "confidence": "conservative_static_estimate",
            "components": {
                "requested_amount_sol": round(requested_amount, 9),
                "token_account_setup_rent_sol": setup_rent,
                "network_fee_sol": network_fee,
                "base_signature_fee_sol": base_fee,
                "priority_fee_sol": round(priority_fee, 9),
                "program_fee_buffer_sol": program_fee_buffer,
            },
            "assumptions": [
                "first buy for a mint may create wallet token and pump program accounts",
                "estimate is intentionally conservative before signing",
                "confirmed transaction metadata remains the accounting source of truth after submission",
            ],
        }

    def quote_live_intent(self, env_live_enabled: bool, intent_id: str, slippage_pct: float, priority_fee_sol: float, pool: str, shadow_only: bool = False) -> dict[str, object]:
        intent = self._require_live_intent(intent_id)
        if intent.status == "cancelled":
            raise ValueError("cannot quote a cancelled intent")
        audit = self.live_quote(
            env_live_enabled=env_live_enabled,
            action=intent.action,
            mint=intent.mint,
            amount=intent.amount,
            denominated_in_sol=intent.denominated_in_sol,
            slippage_pct=slippage_pct,
            priority_fee_sol=priority_fee_sol,
            pool=pool,
            wallet_public_key=intent.wallet_public_key,
            signer_mode=intent.signer_mode,
            shadow_only=shadow_only,
        )
        stored_audit = self.storage.load_live_execution_audit(str(audit.get("id", "")))
        if stored_audit:
            generated_intent_id = str(stored_audit.request.get("id", "")) if isinstance(stored_audit.request, dict) else ""
            if generated_intent_id and generated_intent_id != intent.id:
                generated = self.storage.load_live_intent(generated_intent_id)
                if generated:
                    generated.status = "cancelled"
                    generated.reason = "Superseded by quoted workbench intent"
                    generated.updated_at = utc_now()
                    self.storage.save_live_intent(generated)
            stored_audit.intent_id = intent.id
            stored_audit.request = intent.to_dict()
            stored_audit.quote = {**stored_audit.quote, "intent_id": intent.id}
            self.storage.save_live_execution_audit(stored_audit)
            audit = stored_audit.to_dict()
        intent.quote_id = str(audit.get("quote", {}).get("id", ""))
        intent.audit_id = str(audit.get("id", ""))
        intent.status = "quoted" if audit.get("status") == "ready" else "blocked"
        intent.reason = str(audit.get("final_status", ""))
        intent.updated_at = utc_now()
        intent.expires_at = utc_now() + timedelta(seconds=30)
        intent.stale = False
        intent.version += 1
        self.storage.save_live_intent(intent)
        if shadow_only and intent.source == "paper_promoted":
            stored_audit = self.storage.load_live_execution_audit(str(audit.get("id", "")))
            if stored_audit:
                self._apply_shadow_quote_costs_to_token(intent.mint, stored_audit)
        audit["intent"] = intent.to_dict()
        return audit

    def _apply_shadow_quote_costs_to_token(self, mint: str, audit: LiveExecutionAudit) -> None:
        comparison = audit.shadow_comparison or self._build_shadow_comparison(audit)
        costs = comparison.get("costs", {}) if isinstance(comparison, dict) else {}
        if not isinstance(costs, dict):
            return
        updated = False
        for token in self.tokens:
            if token.mint != mint:
                continue
            token.quote_shadow_fee_sol = float(costs.get("paper_fee_drag_sol", 0.0) or 0.0)
            token.quote_shadow_priority_fee_sol = float(costs.get("priority_fee_sol", 0.0) or 0.0)
            token.quote_shadow_impact_sol = float(costs.get("price_impact_drag_sol", 0.0) or 0.0)
            token.quote_shadow_total_cost_sol = float(costs.get("total_cost_sol", 0.0) or 0.0)
            token.quote_shadow_slippage_pct = float(costs.get("slippage_pct", 0.0) or 0.0)
            token.quote_shadow_status = str(audit.status or audit.final_status or "")
            token.decision_log.append(
                f"Shadow quote cost model: fees {token.quote_shadow_fee_sol:.9f} SOL; priority {token.quote_shadow_priority_fee_sol:.9f} SOL; impact {token.quote_shadow_impact_sol:.9f} SOL"
            )
            self.storage.save_token(token)
            updated = True
        if not updated:
            stored_tokens = [token for token in self.storage.load_tokens(300) if token.mint == mint]
            for token in stored_tokens:
                token.quote_shadow_fee_sol = float(costs.get("paper_fee_drag_sol", 0.0) or 0.0)
                token.quote_shadow_priority_fee_sol = float(costs.get("priority_fee_sol", 0.0) or 0.0)
                token.quote_shadow_impact_sol = float(costs.get("price_impact_drag_sol", 0.0) or 0.0)
                token.quote_shadow_total_cost_sol = float(costs.get("total_cost_sol", 0.0) or 0.0)
                token.quote_shadow_slippage_pct = float(costs.get("slippage_pct", 0.0) or 0.0)
                token.quote_shadow_status = str(audit.status or audit.final_status or "")
                self.storage.save_token(token)

    def _record_shadow_quote_failure_for_token(self, mint: str, reason: str) -> None:
        message = f"Shadow quote failed: {reason}"
        updated = False
        for token in self.tokens:
            if token.mint != mint:
                continue
            token.quote_shadow_status = "quote_failed"
            token.decision_log.append(message)
            self.storage.save_token(token)
            updated = True
        if not updated:
            for token in [item for item in self.storage.load_tokens(300) if item.mint == mint]:
                token.quote_shadow_status = "quote_failed"
                token.decision_log.append(message)
                self.storage.save_token(token)

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
        if audit.intent_id:
            intent = self.storage.load_live_intent(audit.intent_id)
            if intent:
                intent.status = audit.status
                intent.updated_at = utc_now()
                intent.version += 1
                self.storage.save_live_intent(intent)
        return audit.to_dict()

    def live_submit(
        self,
        audit_id: str,
        signature: str,
        *,
        guarded_action_id: str = "",
    ) -> dict[str, object]:
        if guarded_action_id:
            claimed = self.storage.begin_mobile_execution_dispatch(
                audit_id=audit_id,
                action_id=guarded_action_id,
            )
            if claimed is None:
                return self._require_live_audit(audit_id).to_dict()
            audit = claimed
        else:
            audit = self._require_live_audit(audit_id)
            if audit.guarded_action_id:
                raise ValueError(
                    "guarded execution audits require their owning mobile action"
                )
        if audit.quote.get("shadow_only"):
            raise ValueError("shadow-only quote cannot be submitted")
        if not str(audit.quote.get("unsigned_transaction_base64", "")).strip():
            raise ValueError("cannot submit a live audit without a ready unsigned transaction")
        preflight_blockers = self._live_audit_preflight_blockers(
            audit,
            require_exact=bool(guarded_action_id),
        )
        if preflight_blockers:
            raise ValueError(f"cannot submit live audit with failed preflight checks: {'; '.join(preflight_blockers[:4])}")
        if audit.action == "buy":
            if self.settings.kill_switch_enabled:
                raise ValueError("manual kill switch enabled")
            submit_blockers = self._live_execution_blockers(
                bool(audit.quote.get("live_env_enabled_at_quote")),
                audit.action,
                audit.wallet_public_key,
                audit.signer_mode,
                autonomous=False,
            )
            if submit_blockers:
                raise ValueError(f"cannot submit live buy after entry policy changed: {'; '.join(submit_blockers[:4])}")
            backup = self._pre_run_backup_status()
            if backup.get("blocks_live_entries"):
                raise ValueError(str(backup.get("blocker") or "pre-run backup is required before live entries"))
        expires_at = audit.quote.get("expires_at")
        if expires_at and datetime.fromisoformat(str(expires_at)) < utc_now():
            raise ValueError("cannot submit a stale live quote")
        if audit.signer_mode == "browser_wallet":
            if not signature.strip():
                raise ValueError("browser wallet submit requires a transaction signature")
            audit.transaction_signature = signature.strip()
        else:
            audit.status = "submitting"
            audit.final_status = "submitting"
            audit.updated_at = utc_now()
            timing = self._audit_execution_timing(audit)
            timing["submitting_at"] = audit.updated_at.isoformat()
            audit.execution_timing = timing
            self._append_unique(audit.warnings, "backend executor started")
            self.storage.save_live_execution_audit(audit)
            execution = self._execute_backend_audit(audit)
            audit.transaction_signature = str(execution.get("signature") or execution.get("transaction_signature") or "")
            simulation = execution.get("simulation")
            if isinstance(simulation, dict):
                audit.simulation = {
                    "source": audit.signer_mode,
                    "status": "ok" if simulation.get("ok") else "warning" if simulation.get("warning") else "error",
                    "ok": bool(simulation.get("ok")),
                    "warning": str(simulation.get("warning") or ""),
                    "error": str(simulation.get("error") or ""),
                    "result": simulation.get("result") or {},
                }
                if simulation.get("warning"):
                    self._append_unique(audit.warnings, str(simulation.get("warning")))
                if simulation.get("error"):
                    self._append_unique(audit.errors, str(simulation.get("error")))
        submitted_at = utc_now()
        timing = self._audit_execution_timing(audit)
        quote_created_at = self._parse_iso_datetime(str(audit.quote.get("created_at") or "")) if isinstance(audit.quote, dict) else None
        timing["submitted_at"] = submitted_at.isoformat()
        timing["quote_to_submit_ms"] = max(0, int((submitted_at - (quote_created_at or audit.created_at)).total_seconds() * 1000))
        audit.execution_timing = timing
        audit.status = "submitted"
        audit.final_status = "submitted"
        audit.updated_at = submitted_at
        self.storage.save_live_execution_audit(audit)
        if audit.intent_id:
            intent = self.storage.load_live_intent(audit.intent_id)
            if intent:
                intent.status = "submitted"
                intent.updated_at = utc_now()
                intent.version += 1
                self.storage.save_live_intent(intent)
        self.add_event("warning", f"Live {audit.action} submitted: {audit.transaction_signature[:10]}")
        if audit.signer_mode != "browser_wallet":
            return self.recover_live_audit(audit.id)
        return audit.to_dict()

    def live_confirm(self, audit_id: str, confirmation_status: str, error: str = "") -> dict[str, object]:
        audit = self._require_live_audit(audit_id)
        confirmed_at = utc_now()
        audit.confirmation_status = confirmation_status.strip()
        audit.confirmation = {"source": "frontend", "confirmation_status": audit.confirmation_status, "error": error.strip()}
        audit.confirmation_checked_at = confirmed_at
        timing = self._audit_execution_timing(audit)
        submitted_at = self._parse_iso_datetime(str(timing.get("submitted_at") or ""))
        quote_created_at = self._parse_iso_datetime(str(audit.quote.get("created_at") or "")) if isinstance(audit.quote, dict) else None
        timing["confirmed_at"] = confirmed_at.isoformat()
        timing["quote_to_confirm_ms"] = max(0, int((confirmed_at - (quote_created_at or audit.created_at)).total_seconds() * 1000))
        if submitted_at:
            timing["submit_to_confirm_ms"] = max(0, int((confirmed_at - submitted_at).total_seconds() * 1000))
        audit.execution_timing = timing
        audit.status = "confirmed" if confirmation_status in {"confirmed", "finalized"} and not error else "failed"
        audit.final_status = audit.status
        audit.updated_at = confirmed_at
        if error:
            self._append_unique(audit.errors, error)
        self.storage.save_live_execution_audit(audit)
        if audit.intent_id:
            intent = self.storage.load_live_intent(audit.intent_id)
            if intent:
                intent.status = "executed" if audit.status == "confirmed" else "needs_review"
                intent.updated_at = utc_now()
                intent.version += 1
                self.storage.save_live_intent(intent)
        if audit.status == "confirmed":
            position = self._record_live_fill(audit)
            if audit.reconciliation_status == "matched":
                audit.status = "reconciled"
                audit.final_status = "reconciled"
                audit.recommended_action = "No action needed."
            elif position is not None:
                audit.status = "needs_review"
                audit.final_status = "needs_review"
                audit.recommended_action = "Review wallet/RPC balance reconciliation."
            audit.updated_at = utc_now()
            self.storage.save_live_execution_audit(audit)
            self._maybe_run_profit_sweep_after_ledger_update()
        return audit.to_dict()

    def _execute_backend_audit(self, audit: LiveExecutionAudit) -> dict[str, object]:
        unsigned_transaction_base64 = str(audit.quote.get("unsigned_transaction_base64") or "")
        if audit.signer_mode == "local_hot_wallet":
            return self.hot_wallet.simulate_and_submit(unsigned_transaction_base64, self.settings.solana_rpc_url)
        if audit.signer_mode == "local_signer_daemon":
            base_endpoint = self.signer_daemon_url or "http://127.0.0.1:8799"
            if not self._local_signer_daemon_endpoint_allowed(base_endpoint):
                raise ValueError("Signer daemon endpoint must stay localhost-only")
            endpoint = base_endpoint.rstrip("/") + "/execute"
            payload = json.dumps(
                {
                    "unsigned_transaction_base64": unsigned_transaction_base64,
                    "mint": audit.mint,
                    "action": audit.action,
                    "amount": audit.amount,
                    "amount_sol": self._audit_amount_sol(audit),
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    **({"Authorization": f"Bearer {self.signer_daemon_auth_token}"} if self.signer_daemon_auth_token else {}),
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        raise ValueError(f"unsupported backend execution mode: {audit.signer_mode}")

    def recover_unresolved_live_audits(self, limit: int = 25) -> dict[str, object]:
        audits = [audit for audit in self._normalize_live_audits(self.storage.load_live_execution_audits(500)) if self._is_unresolved_live_audit(audit)]
        checked = 0
        updated = 0
        errors: list[str] = []
        recovered: list[dict[str, object]] = []
        for audit in audits[: max(1, int(limit or 25))]:
            try:
                before = (audit.status, audit.reconciliation_status, audit.recovery_attempts)
                result = self.recover_live_audit(audit.id)
                checked += 1
                after = (str(result.get("status", "")), str(result.get("reconciliation_status", "")), int(result.get("recovery_attempts", 0)))
                if after != before:
                    updated += 1
                recovered.append(result)
            except Exception as exc:
                checked += 1
                errors.append(f"{audit.id}: {exc.__class__.__name__}: {exc}")
        summary = {
            "checked": checked,
            "updated": updated,
            "needs_review": len([audit for audit in recovered if str(audit.get("status", "")) == "needs_review"]),
            "max_recovery_attempts": self.live_recovery_max_attempts,
            "errors": errors,
            "skipped": checked == 0,
            "reason": "no unresolved audits" if checked == 0 else "",
        }
        self.live_last_poll_at = utc_now()
        self.live_last_poll_summary = summary
        return {"summary": summary, "audits": recovered}

    def poll_live_audits(self, env_live_enabled: bool, limit: int = 25) -> dict[str, object]:
        if not env_live_enabled:
            summary = {"checked": 0, "updated": 0, "needs_review": 0, "max_recovery_attempts": self.live_recovery_max_attempts, "errors": [], "skipped": True, "reason": "LIVE_TRADING_ENABLED is false"}
            self.live_last_poll_at = utc_now()
            self.live_last_poll_summary = summary
            return summary
        unresolved = [
            audit
            for audit in self._normalize_live_audits(self.storage.load_live_execution_audits(500))
            if audit.transaction_signature and audit.status in {"submitted", "needs_review", "failed"} and not self._recovery_retry_limit_reached(audit)
        ]
        if not unresolved:
            summary = {"checked": 0, "updated": 0, "needs_review": 0, "max_recovery_attempts": self.live_recovery_max_attempts, "errors": [], "skipped": True, "reason": "no unresolved submitted audits"}
            self.live_last_poll_at = utc_now()
            self.live_last_poll_summary = summary
            return summary
        checked = 0
        updated = 0
        errors: list[str] = []
        needs_review = 0
        for audit in unresolved[: max(1, int(limit or 25))]:
            try:
                before = (audit.status, audit.reconciliation_status, audit.recovery_attempts)
                result = self.recover_live_audit(audit.id)
                checked += 1
                after = (str(result.get("status", "")), str(result.get("reconciliation_status", "")), int(result.get("recovery_attempts", 0)))
                if after != before:
                    updated += 1
                if str(result.get("status", "")) == "needs_review":
                    needs_review += 1
            except Exception as exc:
                checked += 1
                errors.append(f"{audit.id}: {exc.__class__.__name__}: {exc}")
        summary = {"checked": checked, "updated": updated, "needs_review": needs_review, "max_recovery_attempts": self.live_recovery_max_attempts, "errors": errors, "skipped": checked == 0, "reason": ""}
        self.live_last_poll_at = utc_now()
        self.live_last_poll_summary = summary
        return summary

    def _recovery_retry_limit_reached(self, audit: LiveExecutionAudit) -> bool:
        return audit.status == "needs_review" and audit.recovery_attempts >= self.live_recovery_max_attempts

    def run_live_autonomy(self, env_live_enabled: bool, *, local_auth_enabled: bool = False) -> dict[str, object]:
        if not local_auth_enabled:
            return {"status": "disabled", "reason": "dashboard password/local auth is required for live autonomy"}
        if not env_live_enabled:
            return {"status": "disabled", "reason": "LIVE_TRADING_ENABLED is false"}
        if not self.settings.live_active_backend_armed:
            return {"status": "idle", "reason": "no active backend armed"}
        wallet = self.settings.live_active_wallet_public_key
        signer_mode = self.settings.live_signer_mode
        if not wallet:
            return {"status": "idle", "reason": "no armed live wallet"}
        generated = self.generate_live_intents(wallet, signer_mode)
        intents = [
            intent
            for intent in self._rank_live_intents(self._decorate_live_intents(self._mark_stale_live_intents(self.storage.load_live_intents(200))))
            if intent.wallet_public_key == wallet and intent.signer_mode == signer_mode and intent.status in {"open", "quoted", "simulated", "simulation_warning"}
        ]
        executed = []
        for intent in intents[:3]:
            blockers = self._live_execution_blockers(env_live_enabled, intent.action, wallet, signer_mode, autonomous=True)
            if blockers:
                intent.autonomy_blocked = True
                intent.autonomy_blockers = blockers
                intent.updated_at = utc_now()
                self.storage.save_live_intent(intent)
                self.add_event(
                    "warning",
                    f"Autonomous {intent.action} blocked for {intent.symbol or intent.mint[:8]}: {'; '.join(blockers[:3])}",
                    subsystem="live",
                    operator_action="Review autonomy blockers before trying unattended execution.",
                )
                continue
            try:
                audit = self.quote_live_intent(env_live_enabled, intent.id, self.settings.live_max_slippage_pct, self.settings.live_priority_fee_cap_sol, "pump")
                stored_audit = self.storage.load_live_execution_audit(str(audit.get("id") or ""))
                preflight_blockers = self._live_audit_preflight_blockers(stored_audit) if stored_audit else ["missing live audit preflight evidence"]
                if preflight_blockers:
                    intent.autonomy_blocked = True
                    intent.autonomy_blockers = preflight_blockers
                    intent.status = "blocked"
                    intent.reason = "Autonomous preflight failed: " + "; ".join(preflight_blockers[:4])
                    intent.updated_at = utc_now()
                    self.storage.save_live_intent(intent)
                    self.add_event(
                        "warning",
                        f"Autonomous {intent.action} preflight blocked for {intent.symbol or intent.mint[:8]}: {'; '.join(preflight_blockers[:3])}",
                        subsystem="live",
                        operator_action="Review live audit preflight evidence before unattended execution.",
                    )
                    continue
                result = self.live_submit(str(audit["id"]), "")
                executed.append({"intent_id": intent.id, "audit_id": str(result.get("id") or audit["id"]), "status": str(result.get("status") or "")})
                if intent.action == "buy":
                    break
            except Exception as exc:
                self.add_event("warning", f"Autonomous {intent.action} failed for {intent.symbol or intent.mint[:8]}: {exc}", subsystem="live")
        return {"status": "ok", "generated": len(generated), "executed": executed}

    def recover_live_audit(self, audit_id: str) -> dict[str, object]:
        audit = self._require_live_audit(audit_id)
        if self._recovery_retry_limit_reached(audit):
            audit.recommended_action = "Recovery retry limit reached. Review the signature manually before taking further action."
            self.storage.save_live_execution_audit(audit)
            return audit.to_dict()
        checked_at = utc_now()
        audit.recovery_attempts += 1
        audit.confirmation_checked_at = checked_at
        audit.updated_at = checked_at
        if not audit.transaction_signature:
            if audit.status in {"ready", "simulated", "simulation_warning", "stale"}:
                audit.status = "stale"
                audit.final_status = "stale"
                audit.recommended_action = "Regenerate the quote before signing."
            else:
                audit.status = "needs_review"
                audit.final_status = "needs_review"
                audit.recommended_action = "No transaction signature is recorded. Review the wallet and audit trail."
            audit.last_recovery_error = "missing transaction signature"
            self.storage.save_live_execution_audit(audit)
            return audit.to_dict()

        status = self._signature_status(audit.transaction_signature)
        audit.confirmation = status
        audit.confirmation_status = str(status.get("confirmation_status") or status.get("status") or "")
        if not status.get("ok", False):
            error = str(status.get("error") or "RPC status check failed")
            audit.status = "needs_review"
            audit.final_status = "needs_review"
            audit.last_recovery_error = error
            audit.recommended_action = "Retry confirmation later and inspect the signature in Solscan."
            self._append_unique(audit.warnings, error)
            self.storage.save_live_execution_audit(audit)
            return audit.to_dict()

        if not status.get("found", False):
            if audit.recovery_attempts >= self.live_recovery_max_attempts:
                error = f"signature not found after {audit.recovery_attempts} recovery attempts"
                audit.status = "needs_review"
                audit.final_status = "needs_review"
                audit.last_recovery_error = error
                audit.recommended_action = "Recovery retry limit reached. Inspect the signature manually before continuing."
                self._append_unique(audit.warnings, error)
                self._mark_live_intent_review(audit)
            else:
                audit.status = "submitted"
                audit.final_status = "submitted"
                audit.last_recovery_error = ""
                audit.recommended_action = "Signature is not visible to RPC yet. Wait, then retry confirmation."
            self.storage.save_live_execution_audit(audit)
            return audit.to_dict()

        if status.get("err"):
            error = f"Transaction error: {status.get('err')}"
            audit.status = "failed"
            audit.final_status = "failed"
            audit.last_recovery_error = error
            audit.recommended_action = "Review the wallet transaction details. Do not resubmit automatically."
            self._append_unique(audit.errors, error)
            self._mark_live_intent_review(audit)
            self.storage.save_live_execution_audit(audit)
            return audit.to_dict()

        if audit.confirmation_status in {"confirmed", "finalized"}:
            timing = self._audit_execution_timing(audit)
            submitted_at = self._parse_iso_datetime(str(timing.get("submitted_at") or ""))
            quote_created_at = self._parse_iso_datetime(str(audit.quote.get("created_at") or "")) if isinstance(audit.quote, dict) else None
            timing["confirmed_at"] = checked_at.isoformat()
            timing["quote_to_confirm_ms"] = max(0, int((checked_at - (quote_created_at or audit.created_at)).total_seconds() * 1000))
            if submitted_at:
                timing["submit_to_confirm_ms"] = max(0, int((checked_at - submitted_at).total_seconds() * 1000))
            audit.execution_timing = timing
            audit.status = "confirmed"
            audit.final_status = "confirmed"
            audit.last_recovery_error = ""
            audit.recommended_action = "Confirmed by RPC. Reconciliation is running."
            self.storage.save_live_execution_audit(audit)
            position = self._record_live_fill(audit)
            if audit.reconciliation_status == "matched":
                audit.status = "reconciled"
                audit.final_status = "reconciled"
                audit.recommended_action = "No action needed."
                self.add_event(
                    "info",
                    f"Live recovery complete and reconciled for {audit.mint[:8] or 'unknown'}",
                    subsystem="live",
                )
                if audit.intent_id:
                    intent = self.storage.load_live_intent(audit.intent_id)
                    if intent:
                        intent.status = "executed"
                        intent.updated_at = utc_now()
                        self.storage.save_live_intent(intent)
            elif position is not None:
                audit.status = "needs_review"
                audit.final_status = "needs_review"
                audit.recommended_action = "Review wallet/RPC balance reconciliation."
                self._mark_live_intent_review(audit)
            audit.updated_at = utc_now()
            self.storage.save_live_execution_audit(audit)
            self._maybe_run_profit_sweep_after_ledger_update()
            return audit.to_dict()

        audit.status = "submitted"
        audit.final_status = "submitted"
        audit.last_recovery_error = ""
        audit.recommended_action = "RPC has not confirmed the transaction yet. Retry confirmation later."
        self.storage.save_live_execution_audit(audit)
        return audit.to_dict()

    def _maybe_run_profit_sweep_after_ledger_update(self) -> None:
        result = self.maybe_run_profit_sweep()
        if result.get("status") == "failed":
            self.add_event("warning", f"Profit sweep failed: {result.get('reason')}", subsystem="live")

    def maybe_run_profit_sweep(self) -> dict[str, object]:
        if not self.settings.profit_sweep_enabled:
            return {"status": "idle", "reason": "profit sweep disabled"}
        blockers: list[str] = []
        if self.settings.kill_switch_enabled:
            blockers.append("manual kill switch enabled")
        if self.settings.live_signer_mode != "local_hot_wallet":
            blockers.append("profit sweep requires local_hot_wallet signer mode")
        if not self.settings.live_active_backend_armed:
            blockers.append("local hot-wallet backend is not armed")
        wallet = self.settings.live_active_wallet_public_key or self.hot_wallet.wallet_public_key()
        hot_wallet = self.hot_wallet.status()
        hot_wallet_public_key = str(hot_wallet.get("wallet_public_key") or "")
        if not hot_wallet.get("imported"):
            blockers.append("no local hot wallet is imported")
        if not hot_wallet.get("unlocked"):
            blockers.append("local hot wallet is locked")
        if wallet and hot_wallet_public_key and wallet != hot_wallet_public_key:
            blockers.append("armed wallet does not match imported local hot wallet")
        destination = self.settings.profit_sweep_destination_wallet.strip()
        if not destination:
            blockers.append("profit sweep destination wallet is required")
        if destination and wallet and destination == wallet:
            blockers.append("profit sweep destination must differ from the trading wallet")
        if not wallet:
            blockers.append("armed live wallet is required")
        if blockers:
            reason = "; ".join(blockers)
            return {"status": "blocked", "reason": reason, "blockers": blockers}
        balance = self._wallet_sol_balance(wallet)
        balance_sol = Decimal(str(balance.get("balance_sol", 0.0) or 0.0))
        if balance.get("error"):
            return {
                "status": "blocked",
                "reason": f"wallet SOL balance check failed: {balance['error']}",
                "balance_snapshot": balance,
            }
        policy = self._profit_sweep_policy_evaluation(
            wallet_public_key=wallet,
            destination=destination,
            balance_sol=balance_sol,
        )
        policy_blockers = [
            str(value) for value in policy.get("blockers", [])
        ]
        realized_pnl = float(policy["realized_pnl_sol"])
        threshold = float(policy["minimum_profit_sol"])
        if (
            "realized live profit is below minimum profit to sweep"
            in policy_blockers
        ):
            return {
                "status": "idle",
                "reason": "realized live profit is below minimum profit to sweep",
                "realized_pnl_sol": round(realized_pnl, 9),
                "minimum_profit_sol": round(threshold, 9),
            }
        if policy_blockers:
            return {
                "status": "blocked",
                "reason": "; ".join(policy_blockers),
                "blockers": policy_blockers,
                "policy": policy,
            }
        now = utc_now()
        amount = float(policy["expected_amount_sol"])
        reserve = float(policy["minimum_reserve_sol"])
        sweep_mode = str(policy["sweep_mode"])
        sweep_percentage = float(policy["sweep_percentage"])
        max_per_day = int(policy["max_per_day"])
        cooldown_seconds = int(policy["cooldown_seconds"])
        sweeps_today = int(policy["sweeps_today"])
        balance_sol_float = float(balance_sol)

        audit = LiveExecutionAudit(
            id=new_id("liveaudit"),
            created_at=now,
            updated_at=now,
            action="profit_sweep",
            mint="SOL",
            amount=str(round(amount, 9)),
            status="ready",
            signer_mode="local_hot_wallet",
            wallet_public_key=wallet,
            quote={
                "provider": "local_system_transfer",
                "destination_wallet": destination,
                "amount_sol": round(amount, 9),
                "minimum_profit_sol": round(threshold, 9),
                "threshold_sol": round(threshold, 9),
                "realized_pnl_sol": round(realized_pnl, 9),
                "sweep_mode": sweep_mode,
                "sweep_percentage": round(sweep_percentage, 4) if sweep_mode == "percentage" else 0.0,
            },
            request={
                "source": "profit_sweep",
                "reason": "realized live profit reached minimum profit to sweep",
                "destination_wallet": destination,
                "amount_sol": round(amount, 9),
                "minimum_profit_sol": round(threshold, 9),
                "threshold_sol": round(threshold, 9),
                "sweep_mode": sweep_mode,
                "sweep_percentage": round(sweep_percentage, 4) if sweep_mode == "percentage" else 0.0,
            },
            preflight_checks=[
                self._preflight_check("minimum_profit", "Minimum Profit", "pass", round(realized_pnl, 9), f">= {round(threshold, 9)} SOL", ""),
                self._preflight_check("minimum_reserve", "Minimum Reserve", "pass", round(balance_sol_float - amount, 9), f">= {round(reserve, 9)} SOL", ""),
                self._preflight_check("local_hot_wallet", "Local Hot Wallet", "pass", "unlocked", "unlocked and armed", ""),
            ],
            caps_snapshot={
                "profit_sweep_max_per_day": max_per_day,
                "profit_sweep_cooldown_seconds": cooldown_seconds,
                "profit_sweep_mode": sweep_mode,
                "profit_sweep_percentage": round(sweep_percentage, 4) if sweep_mode == "percentage" else 0.0,
                "profit_sweep_min_profit_sol": round(threshold, 9),
                "sweeps_today": sweeps_today,
            },
            balance_snapshot=balance,
            final_status="ready",
            recommended_action="Review the sweep audit and vault wallet receipt.",
        )
        self.storage.save_live_execution_audit(audit)
        try:
            execution = self.hot_wallet.transfer_sol(destination, amount, self.settings.solana_rpc_url)
            audit.transaction_signature = str(execution.get("signature") or execution.get("transaction_signature") or "")
            simulation = execution.get("simulation")
            if isinstance(simulation, dict):
                audit.simulation = {
                    "source": "local_hot_wallet",
                    "status": "ok" if simulation.get("ok") else "warning" if simulation.get("warning") else "error",
                    "ok": bool(simulation.get("ok")),
                    "warning": str(simulation.get("warning") or ""),
                    "error": str(simulation.get("error") or ""),
                    "result": simulation.get("result") or {},
                }
                if simulation.get("warning"):
                    self._append_unique(audit.warnings, str(simulation.get("warning")))
                if simulation.get("error"):
                    self._append_unique(audit.errors, str(simulation.get("error")))
            audit.status = "submitted"
            audit.final_status = "submitted"
            audit.updated_at = utc_now()
            self.storage.save_live_execution_audit(audit)
            self.add_event("warning", f"Profit sweep submitted: {amount:.6f} SOL to {destination[:8]}...", subsystem="live")
            return {
                "status": "submitted",
                "audit": audit.to_dict(),
                "signature": audit.transaction_signature,
                "amount_sol": round(amount, 9),
                "destination_wallet": destination,
                "realized_pnl_sol": round(realized_pnl, 9),
            }
        except Exception as exc:
            audit.status = "failed"
            audit.final_status = "failed"
            audit.errors.append(f"{exc.__class__.__name__}: {exc}")
            audit.recommended_action = "Review the local hot wallet, destination, RPC, and vault sweep settings before retrying."
            audit.updated_at = utc_now()
            self.storage.save_live_execution_audit(audit)
            return {"status": "failed", "reason": f"{exc.__class__.__name__}: {exc}", "audit": audit.to_dict()}

    def _wallet_sol_balance(self, wallet_public_key: str) -> dict[str, object]:
        try:
            balance = SolanaReadOnlyClient(self.settings.solana_rpc_url).balance_sol(wallet_public_key)
            return {"wallet_public_key": wallet_public_key, "balance_sol": float(balance or 0.0), "error": ""}
        except Exception as exc:
            return {"wallet_public_key": wallet_public_key, "balance_sol": 0.0, "error": f"{exc.__class__.__name__}: {exc}"}

    def live_wallet_balance(self, wallet_public_key: str) -> dict[str, object]:
        wallet = wallet_public_key.strip()
        if not wallet:
            return {"wallet_public_key": "", "balance_sol": 0.0, "error": "wallet public key is required"}
        result = self._wallet_sol_balance(wallet)
        return {
            "wallet_public_key": str(result.get("wallet_public_key") or wallet),
            "balance_sol": float(result.get("balance_sol") or 0.0),
            "error": str(result.get("error") or ""),
        }

    def reconcile_live_intent(self, intent_id: str) -> dict[str, object]:
        intent = self._require_live_intent(intent_id)
        audit = self.storage.load_live_execution_audit(intent.audit_id) if intent.audit_id else None
        if audit is None:
            intent.status = "needs_review"
            intent.warnings.append("No execution audit exists for reconciliation")
            intent.updated_at = utc_now()
            self.storage.save_live_intent(intent)
            return intent.to_dict()
        position = self._reconcile_live_audit(audit)
        return {"intent": intent.to_dict(), "audit": audit.to_dict(), "position": position.to_dict() if position else None}

    def _validate_live_order(self, action: str, amount: str, denominated_in_sol: bool, slippage_pct: float, priority_fee_sol: float, wallet_public_key: str, signer_mode: str, shadow_only: bool = False) -> str:
        if action not in {"buy", "sell"}:
            return "action must be buy or sell"
        if not wallet_public_key.strip():
            return "wallet public key is required"
        signer = self.signer_status(signer_mode, wallet_public_key)
        if not shadow_only and not signer.get("connected"):
            return str(signer.get("disabled_reason") or "selected live backend is not connected")
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

    def _live_order_preflight_checks(
        self,
        *,
        env_live_enabled: bool,
        action: str,
        mint: str,
        amount: str,
        denominated_in_sol: bool,
        slippage_pct: float,
        priority_fee_sol: float,
        pool: str,
        wallet_public_key: str,
        signer_mode: str,
        blockers: list[str],
        shadow_only: bool = False,
    ) -> list[dict[str, object]]:
        signer = self.signer_status(signer_mode, wallet_public_key)
        caps = self.live_caps_snapshot()
        try:
            numeric_amount = float(str(amount).replace("%", ""))
        except ValueError:
            numeric_amount = -1.0
        mint_ready = bool(mint.strip())
        wallet_ready = bool(wallet_public_key.strip())
        cap_trade = float(caps.get("max_trade_sol", 0.0) or 0.0)
        cap_slippage = float(caps.get("max_slippage_pct", 0.0) or 0.0)
        cap_priority = float(caps.get("priority_fee_cap_sol", 0.0) or 0.0)
        amount_ready = numeric_amount > 0 and (action != "buy" or (denominated_in_sol and numeric_amount <= cap_trade))
        slippage_ready = float(slippage_pct or 0.0) > 0 and float(slippage_pct or 0.0) <= cap_slippage
        priority_ready = float(priority_fee_sol or 0.0) >= 0 and float(priority_fee_sol or 0.0) <= cap_priority
        pool_ready = bool(str(pool or "").strip())
        signer_ready = bool(wallet_public_key.strip()) if shadow_only else (bool(signer.get("connected")) and bool(signer.get("can_sign")))
        signer_target = "wallet public key for shadow quote" if shadow_only else "connected signer with can_sign"
        signer_reason = "Shadow-only quotes are not submitted and do not require signer connection." if shadow_only else str(signer.get("disabled_reason") or "Signer must be connected and able to sign.")
        checks = [
            self._preflight_check("environment", "Live Environment", "pass" if env_live_enabled else "fail", bool(env_live_enabled), True, "LIVE_TRADING_ENABLED must be enabled for quotes." if not shadow_only else "Shadow-only quote mode allows quote evidence without live trading enabled."),
            self._preflight_check("mint", "Mint", "pass" if mint_ready else "fail", mint.strip() or "missing", "non-empty mint", "Mint is required before requesting a local transaction."),
            self._preflight_check("wallet", "Wallet", "pass" if wallet_ready else "fail", wallet_public_key.strip() or "missing", "connected wallet", "Wallet public key is required."),
            self._preflight_check("signer", "Signer", "pass" if signer_ready else "fail", signer_mode, signer_target, signer_reason),
            self._preflight_check("amount", "Amount", "pass" if amount_ready else "fail", amount, f"positive{' and <= live max trade cap' if action == 'buy' else ''}", "Amount must be positive and within configured caps."),
            self._preflight_check("slippage", "Slippage", "pass" if slippage_ready else "fail", round(float(slippage_pct or 0.0), 4), f"<= {cap_slippage:.4f}%", "Slippage must stay within the live cap."),
            self._preflight_check("priority_fee", "Priority Fee", "pass" if priority_ready else "fail", round(float(priority_fee_sol or 0.0), 9), f"<= {cap_priority:.9f} SOL", "Priority fee must stay within the live cap."),
            self._preflight_check("pool", "Pool", "pass" if pool_ready else "fail", pool or "missing", "selected pool", "Pool must be selected before quote."),
            self._preflight_check("caps", "Live Caps", "pass" if all(float(caps.get(key) or 0) > 0 for key in ("max_trade_sol", "daily_loss_cap_sol", "wallet_exposure_cap_sol", "max_open_positions", "max_slippage_pct", "priority_fee_cap_sol")) else "fail", caps, "all numeric caps > 0", "All live caps must be configured."),
        ]
        if blockers:
            checks.append(self._preflight_check("blockers", "Aggregate Blockers", "fail", len(blockers), 0, "; ".join(blockers[:6])))
        else:
            checks.append(self._preflight_check("blockers", "Aggregate Blockers", "pass", 0, 0, "No pre-quote blockers detected."))
        return checks

    def _preflight_check(self, check_id: str, label: str, status: str, value: object, target: object, reason: str) -> dict[str, object]:
        return {
            "id": check_id,
            "label": label,
            "status": status,
            "value": value,
            "target": target,
            "reason": reason,
        }

    def _live_audit_preflight_blockers(
        self,
        audit: LiveExecutionAudit | None,
        *,
        require_exact: bool = False,
    ) -> list[str]:
        if audit is None:
            return ["missing live audit"]
        rows = audit.preflight_checks or []
        if not rows:
            return ["missing preflight inventory"] if require_exact else []
        required_ids = {
            "environment",
            "mint",
            "wallet",
            "signer",
            "amount",
            "slippage",
            "priority_fee",
            "pool",
            "caps",
            "blockers",
        }
        optional_ids = {
            "estimated_wallet_spend",
            "rent_dominance",
            "wallet_token_balance",
        }
        blockers = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                if require_exact:
                    blockers.append("malformed preflight row")
                continue
            check_id = str(row.get("id") or "").strip()
            label = str(row.get("label") or "").strip()
            reason = str(row.get("reason") or "").strip()
            status = str(row.get("status") or "").lower()
            if not check_id or not label or not reason:
                if require_exact:
                    blockers.append("malformed preflight row")
                continue
            if check_id in seen:
                if require_exact:
                    blockers.append(f"duplicate preflight check: {check_id}")
                continue
            seen.add(check_id)
            if require_exact and check_id not in required_ids | optional_ids:
                blockers.append(f"unknown preflight check: {check_id}")
            if status == "fail" or (require_exact and status != "pass"):
                blockers.append(f"{label}: {reason or 'not passing'}")
        missing = sorted(required_ids - seen) if require_exact else []
        if require_exact and missing:
            blockers.append("missing preflight checks: " + ", ".join(missing))
        return blockers

    def _wallet_token_balance(self, wallet_public_key: str, mint: str) -> dict[str, object]:
        checked_at = utc_now().isoformat()
        try:
            balance = SolanaReadOnlyClient(self.settings.solana_rpc_url).token_balance(wallet_public_key, mint)
            return {"wallet_public_key": wallet_public_key, "mint": mint, "token_balance": balance, "error": "", "checked_at": checked_at}
        except Exception as exc:
            return {"wallet_public_key": wallet_public_key, "mint": mint, "token_balance": None, "error": f"{exc.__class__.__name__}: {exc}", "checked_at": checked_at}

    def live_rent_recovery_scan(self, wallet_public_key: str) -> dict[str, object]:
        wallet = wallet_public_key.strip()
        if not wallet:
            raise ValueError("wallet public key is required")
        accounts = SolanaReadOnlyClient(self.settings.solana_rpc_url).token_accounts(wallet)
        open_mints = {
            position.mint
            for position in self.storage.load_live_ledger_positions(500)
            if position.wallet_public_key == wallet and position.status == "open" and position.mint
        }
        eligible: list[dict[str, object]] = []
        ineligible: list[dict[str, object]] = []
        for account in accounts:
            normalized = {
                "token_account": str(account.get("token_account") or ""),
                "mint": str(account.get("mint") or ""),
                "owner": str(account.get("owner") or wallet),
                "program_id": str(account.get("program_id") or SPL_TOKEN_PROGRAM_ID),
                "token_amount": float(account.get("token_amount") or 0.0),
                "token_amount_raw": str(account.get("token_amount_raw") or "0"),
                "decimals": int(account.get("decimals") or 0),
                "lamports": int(account.get("lamports") or 0),
                "rent_sol": round(float(account.get("rent_sol") or 0.0), 9),
            }
            reason = ""
            if not normalized["token_account"] or not normalized["mint"]:
                reason = "token account or mint is missing"
            elif normalized["owner"] != wallet:
                reason = "token account owner does not match selected wallet"
            elif normalized["program_id"] not in {SPL_TOKEN_PROGRAM_ID, SPL_TOKEN_2022_PROGRAM_ID}:
                reason = "unsupported token program"
            elif str(normalized["token_amount_raw"]) not in {"", "0"} or float(normalized["token_amount"] or 0.0) != 0.0:
                reason = "non-zero token balance"
            elif normalized["mint"] in open_mints:
                reason = "mint has an open live position"
            elif int(normalized["lamports"] or 0) <= 0:
                reason = "no recoverable rent lamports"
            if reason:
                ineligible.append({**normalized, "eligible": False, "reason": reason})
            else:
                eligible.append({**normalized, "eligible": True, "reason": "zero-balance token account"})
        recoverable = round(sum(float(item.get("rent_sol") or 0.0) for item in eligible), 9)
        return {
            "wallet_public_key": wallet,
            "eligible_accounts": eligible,
            "ineligible_accounts": ineligible,
            "eligible_count": len(eligible),
            "ineligible_count": len(ineligible),
            "recoverable_rent_sol": recoverable,
            "manual_approval_required": True,
            "operator_action": "Review eligible zero-balance token accounts, then create a close-account preview for wallet signing.",
        }

    def live_rent_recovery_preview(self, wallet_public_key: str, token_accounts: list[str]) -> dict[str, object]:
        wallet = wallet_public_key.strip()
        selected = [account.strip() for account in token_accounts if account.strip()]
        if not wallet:
            raise ValueError("wallet public key is required")
        if not selected:
            raise ValueError("at least one token account is required")
        scan = self.live_rent_recovery_scan(wallet)
        eligible_by_account = {str(item["token_account"]): item for item in scan["eligible_accounts"]}
        missing = [account for account in selected if account not in eligible_by_account]
        if missing:
            raise ValueError(f"selected token accounts are not eligible: {', '.join(missing[:5])}")
        client = SolanaReadOnlyClient(self.settings.solana_rpc_url)
        blockhash = client.latest_blockhash()
        payer = Pubkey.from_string(wallet)
        instructions = [
            self._close_token_account_instruction(
                token_account=str(eligible_by_account[account]["token_account"]),
                destination_wallet=wallet,
                owner_wallet=wallet,
                program_id=str(eligible_by_account[account]["program_id"]),
            )
            for account in selected
        ]
        message = MessageV0.try_compile(payer, instructions, [], Hash.from_string(blockhash))
        transaction = VersionedTransaction.populate(message, [])
        selected_accounts = [eligible_by_account[account] for account in selected]
        recoverable = round(sum(float(item.get("rent_sol") or 0.0) for item in selected_accounts), 9)
        audit = LiveExecutionAudit(
            id=f"rent_{uuid.uuid4().hex[:12]}",
            created_at=utc_now(),
            updated_at=utc_now(),
            action="rent_recovery",
            mint="rent_recovery",
            amount=str(recoverable),
            status="ready",
            signer_mode="browser_wallet",
            wallet_public_key=wallet,
            quote={
                "unsigned_transaction_base64": base64.b64encode(bytes(transaction)).decode("utf-8"),
                "selected_accounts": selected_accounts,
                "selected_count": len(selected_accounts),
                "recoverable_rent_sol": recoverable,
                "manual_approval_required": True,
                "created_at": utc_now().isoformat(),
            },
            request={"token_accounts": selected},
            final_status="ready",
            recommended_action="Review the browser wallet prompt, then submit the returned signature for audit recovery.",
        )
        self.storage.save_live_execution_audit(audit)
        return {
            "audit_id": audit.id,
            "wallet_public_key": wallet,
            "selected_accounts": selected_accounts,
            "selected_count": len(selected_accounts),
            "recoverable_rent_sol": recoverable,
            "unsigned_transaction_base64": audit.quote["unsigned_transaction_base64"],
            "manual_approval_required": True,
            "status": "ready_for_signature",
            "warnings": [
                "Only zero-balance token accounts are included.",
                "Closing a token account is permanent; recreating it later requires paying rent again.",
            ],
        }

    def _close_token_account_instruction(self, token_account: str, destination_wallet: str, owner_wallet: str, program_id: str) -> Instruction:
        return Instruction(
            Pubkey.from_string(program_id),
            bytes([9]),
            [
                AccountMeta(Pubkey.from_string(token_account), False, True),
                AccountMeta(Pubkey.from_string(destination_wallet), False, True),
                AccountMeta(Pubkey.from_string(owner_wallet), True, False),
            ],
        )

    def _signature_status(self, signature: str) -> dict[str, object]:
        signature = signature.strip()
        if not signature:
            return {"ok": False, "found": False, "confirmation_status": "", "error": "missing transaction signature"}
        try:
            response = SolanaReadOnlyClient(self.settings.solana_rpc_url).rpc(
                "getSignatureStatuses",
                [[signature], {"searchTransactionHistory": True}],
            )
            values = (response.get("result") or {}).get("value") or []
            status = values[0] if values else None
            if not status:
                return {"ok": True, "found": False, "confirmation_status": "not_found", "signature": signature}
            confirmation_status = str(status.get("confirmationStatus") or ("finalized" if status.get("confirmations") is None else "processed"))
            return {
                "ok": True,
                "found": True,
                "signature": signature,
                "confirmation_status": confirmation_status,
                "slot": status.get("slot"),
                "confirmations": status.get("confirmations"),
                "err": status.get("err"),
            }
        except Exception as exc:
            return {"ok": False, "found": False, "confirmation_status": "", "signature": signature, "error": f"{exc.__class__.__name__}: {exc}"}

    def _transaction_details(self, signature: str) -> dict[str, object]:
        signature = signature.strip()
        if not signature:
            return {"ok": False, "found": False, "signature": "", "error": "missing transaction signature"}
        try:
            response = SolanaReadOnlyClient(self.settings.solana_rpc_url).rpc(
                "getTransaction",
                [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "maxSupportedTransactionVersion": 0,
                        "commitment": "confirmed",
                    },
                ],
            )
            transaction = response.get("result")
            if not transaction:
                return {"ok": True, "found": False, "signature": signature, "error": "transaction not found"}
            return {"ok": True, "found": True, "signature": signature, "transaction": transaction}
        except Exception as exc:
            return {"ok": False, "found": False, "signature": signature, "error": f"{exc.__class__.__name__}: {exc}"}

    def _append_unique(self, values: list[str], value: str) -> None:
        clean = str(value or "").strip()
        if clean and clean not in values:
            values.append(clean)

    def _mark_live_intent_review(self, audit: LiveExecutionAudit) -> None:
        if not audit.intent_id:
            return
        intent = self.storage.load_live_intent(audit.intent_id)
        if not intent:
            return
        intent.status = "needs_review"
        intent.updated_at = utc_now()
        self.storage.save_live_intent(intent)

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

    def _require_live_intent(self, intent_id: str) -> LiveExecutionIntent:
        intent = self.storage.load_live_intent(intent_id)
        if intent is None:
            raise ValueError(f"Live intent not found: {intent_id}")
        return intent

    def _mark_stale_live_intents(self, intents: list[LiveExecutionIntent]) -> list[LiveExecutionIntent]:
        now = utc_now()
        for intent in intents:
            if intent.expires_at and intent.expires_at < now and intent.status in {"open", "quoted", "simulated", "simulation_warning"}:
                intent.stale = True
                if intent.quote_id:
                    intent.status = "expired"
                intent.updated_at = now
                self.storage.save_live_intent(intent)
        return intents

    def _future_autonomy_blockers(self, signer: dict[str, object], readiness: dict[str, object]) -> list[str]:
        wallet = str(signer.get("wallet_public_key") or self.settings.live_active_wallet_public_key or "")
        mode = str(signer.get("mode") or self.settings.live_signer_mode or "browser_wallet")
        return list(
            dict.fromkeys(
                [
                    *self._live_execution_blockers(True, "buy", wallet, mode, autonomous=True),
                    *self._live_execution_blockers(True, "sell", wallet, mode, autonomous=True),
                ]
            )
        )

    def _decorate_live_intents(self, intents: list[LiveExecutionIntent], readiness: dict[str, object] | None = None) -> list[LiveExecutionIntent]:
        shared_readiness = readiness or self.readiness_status()
        blocker_cache: dict[tuple[str, str, str], list[str]] = {}
        for intent in intents:
            key = (intent.action, intent.wallet_public_key, intent.signer_mode)
            if key not in blocker_cache:
                blocker_cache[key] = self._live_execution_blockers(True, intent.action, intent.wallet_public_key, intent.signer_mode, autonomous=True)
            self._decorate_live_intent(intent, shared_readiness, autonomy_blockers=blocker_cache[key])
        return intents

    def _decorate_live_intent(self, intent: LiveExecutionIntent, readiness: dict[str, object] | None = None, autonomy_blockers: list[str] | None = None) -> LiveExecutionIntent:
        readiness = readiness or self.readiness_status()
        blockers = autonomy_blockers if autonomy_blockers is not None else self._live_execution_blockers(True, intent.action, intent.wallet_public_key, intent.signer_mode, autonomous=True)
        previous_blocked = intent.autonomy_blocked
        previous_blockers = list(intent.autonomy_blockers)
        previous_recommendation = intent.operator_recommendation
        intent.autonomy_blocked = bool(blockers)
        intent.autonomy_blockers = list(dict.fromkeys(blockers))
        if not intent.operator_recommendation.strip():
            intent.operator_recommendation = (
                "Manual quote/sign remains available while this intent is blocked from autonomous execution."
                if intent.autonomy_blocked
                else "Intent is eligible for autonomous execution on the armed backend."
            )
        changed = (
            previous_blocked != intent.autonomy_blocked
            or previous_blockers != intent.autonomy_blockers
            or previous_recommendation != intent.operator_recommendation
        )
        if changed:
            self.storage.save_live_intent(intent)
        return intent

    def _rank_live_intents(self, intents: list[LiveExecutionIntent]) -> list[LiveExecutionIntent]:
        return sorted(
            intents,
            key=lambda intent: (
                1 if intent.status in {"open", "quoted", "simulated", "simulation_warning"} else 0,
                1 if intent.action == "sell" and intent.generated_from_position else 0,
                float(intent.priority or 0),
                int(intent.score or 0),
                intent.created_at.timestamp(),
            ),
            reverse=True,
        )

    def _live_position_exit_signals(self, position: LiveLedgerPosition) -> list[dict[str, object]]:
        token = next((item for item in self.storage.load_all_tokens(5000) if item.mint == position.mint), None)
        if token is None:
            return []
        price = self._latest_live_mark_price(position.mint)
        entry_price = float(position.average_entry_price_sol or 0.0)
        current_pct = 0.0
        if price > 0 and entry_price > 0:
            current_pct = ((price - entry_price) / entry_price) * 100
        signals: list[dict[str, object]] = []
        stop_pct = (
            float(position.stop_pct)
            if position.stop_pct is not None
            else float(self.settings.stop_loss_pct)
        )
        if stop_pct > 0 and current_pct <= -abs(stop_pct):
            signals.append(
                {
                    "signal": "stop_loss",
                    "reason": f"Stop-loss triggered at {current_pct:.2f}% versus -{abs(stop_pct):.2f}%",
                    "priority_reason": f"Risk exit: stop-loss breach {current_pct:.2f}%",
                    "priority": 1000 + abs(current_pct),
                    "score": 100,
                }
            )
        target_pct = (
            float(position.target_pct)
            if position.target_pct is not None
            else float(self.settings.take_profit_pct)
        )
        if target_pct > 0 and current_pct >= target_pct:
            signals.append(
                {
                    "signal": "take_profit",
                    "reason": f"Take-profit triggered at {current_pct:.2f}% versus {target_pct:.2f}%",
                    "priority_reason": f"Profit exit: target reached at {current_pct:.2f}%",
                    "priority": 980 + current_pct,
                    "score": 98,
                }
            )
        if self.settings.break_even_stop_enabled and token.highest_unrealized_pct >= self.settings.break_even_after_profit_pct and current_pct <= 0:
            signals.append(
                {
                    "signal": "break_even_stop",
                    "reason": f"Break-even stop triggered after {token.highest_unrealized_pct:.2f}% peak gains rolled back to {current_pct:.2f}%",
                    "priority_reason": f"Risk exit: break-even protection after {token.highest_unrealized_pct:.2f}% peak",
                    "priority": 960 + token.highest_unrealized_pct,
                    "score": 96,
                }
            )
        if self.settings.stalled_trade_exit_enabled and token.hold_duration_seconds >= self.settings.stalled_trade_seconds and abs(current_pct) <= self.settings.stalled_trade_min_move_pct:
            signals.append(
                {
                    "signal": "stalled_trade_exit",
                    "reason": f"Stalled-trade exit triggered after {token.hold_duration_seconds}s with only {current_pct:.2f}% move",
                    "priority_reason": f"Risk exit: stalled trade for {token.hold_duration_seconds}s",
                    "priority": 920 + min(token.hold_duration_seconds / 10, 50),
                    "score": 92,
                }
            )
        if self.settings.sell_pressure_exit_enabled and token.sell_pressure >= self.settings.sell_pressure_exit_threshold:
            signals.append(
                {
                    "signal": "sell_pressure_exit",
                    "reason": f"Sell-pressure exit triggered at {token.sell_pressure:.2f} versus {self.settings.sell_pressure_exit_threshold:.2f}",
                    "priority_reason": f"Risk exit: sell pressure {token.sell_pressure:.2f}",
                    "priority": 900 + (token.sell_pressure * 100),
                    "score": 90,
                }
            )
        return sorted(signals, key=lambda signal: float(signal["priority"]), reverse=True)

    def _record_live_fill(self, audit: LiveExecutionAudit) -> LiveLedgerPosition | None:
        wallet = audit.wallet_public_key
        if not wallet:
            return None
        existing = next((position for position in self.storage.load_live_ledger_positions(500) if position.mint == audit.mint and position.wallet_public_key == wallet), None)
        now = utc_now()
        token = next((item for item in self.storage.load_all_tokens(5000) if item.mint == audit.mint), None)
        if token and token.wallet_public_key != wallet:
            token.wallet_public_key = wallet
            self.storage.save_token(token)
        position = existing or LiveLedgerPosition(
            id=new_id("livepos"),
            created_at=now,
            updated_at=now,
            mint=audit.mint,
            wallet_public_key=wallet,
            symbol=token.symbol if token else "",
        )
        if any(fill.get("audit_id") == audit.id for fill in position.fills):
            return self._reconcile_live_audit(audit)
        amount_sol = 0.0
        token_amount = 0.0
        denominated_in_sol = bool(audit.request.get("denominated_in_sol")) if isinstance(audit.request, dict) else False
        try:
            if audit.action == "buy" and not str(audit.amount).endswith("%"):
                amount_sol = float(audit.amount)
            elif audit.action == "sell" and not denominated_in_sol and not str(audit.amount).endswith("%"):
                token_amount = float(audit.amount)
        except ValueError:
            amount_sol = 0.0
            token_amount = 0.0
        priority_fee = float(audit.quote.get("priority_fee_sol", 0.0) or 0.0) if isinstance(audit.quote, dict) else 0.0
        fill = LiveFill(
            id=new_id("fill"),
            created_at=now,
            audit_id=audit.id,
            intent_id=audit.intent_id,
            action=audit.action,
            mint=audit.mint,
            amount=audit.amount,
            amount_sol=amount_sol,
            token_amount=token_amount,
            fee_sol=0.0,
            priority_fee_sol=priority_fee,
            signature=audit.transaction_signature,
        ).to_dict()
        position.fills.append(fill)
        position.total_priority_fees_sol = round(position.total_priority_fees_sol + priority_fee, 9)
        mark_price = self._latest_live_mark_price(audit.mint)
        if audit.action == "buy":
            position.cost_basis_sol = round(position.cost_basis_sol + amount_sol + priority_fee, 9)
            position.status = "open"
            authorization = (
                audit.guarded_authorization
                if isinstance(audit.guarded_authorization, dict)
                else {}
            )
            if not authorization and isinstance(audit.request, dict):
                candidate = audit.request.get("mobile_authorization")
                authorization = candidate if isinstance(candidate, dict) else {}
            if authorization:
                try:
                    stop_pct = float(authorization.get("stop_pct"))
                    target_pct = float(authorization.get("target_pct"))
                except (TypeError, ValueError):
                    stop_pct = 0.0
                    target_pct = 0.0
                if not (0 < stop_pct <= 100 and 0 < target_pct <= 100):
                    raise ValueError(
                        "guarded buy authorization is missing bounded exit controls"
                    )
                position.stop_pct = round(stop_pct, 4)
                position.target_pct = round(target_pct, 4)
                position.last_mobile_action_id = str(
                    authorization.get("action_id") or ""
                )
            fill["accounting"] = {
                "type": "buy",
                "method": position.cost_basis_method,
                "amount_sol": round(amount_sol, 9),
                "priority_fee_sol": round(priority_fee, 9),
                "cost_basis_added_sol": round(amount_sol + priority_fee, 9),
                "cost_basis_after_sol": position.cost_basis_sol,
            }
        else:
            sale_fraction = self._live_sale_fraction(position, audit, token_amount, denominated_in_sol)
            realized_basis = position.cost_basis_sol * sale_fraction
            estimated_proceeds = (position.token_balance * mark_price * sale_fraction) if mark_price > 0 and position.token_balance > 0 else 0.0
            realized_delta = round(estimated_proceeds - realized_basis - priority_fee, 9)
            position.realized_pnl_sol = round(position.realized_pnl_sol + realized_delta, 9)
            position.cost_basis_sol = round(max(0.0, position.cost_basis_sol - realized_basis), 9)
            accounting_event = {
                "type": "sell",
                "audit_id": audit.id,
                "recorded_at": now.isoformat(),
                "method": position.cost_basis_method,
                "sale_fraction": round(sale_fraction, 6),
                "token_balance_before": position.token_balance,
                "mark_price_sol": round(mark_price, 12),
                "mark_price_source": self._latest_live_mark_price_snapshot(audit.mint).get("source", ""),
                "estimated_proceeds_sol": round(estimated_proceeds, 9),
                "cost_basis_consumed_sol": round(realized_basis, 9),
                "priority_fee_sol": round(priority_fee, 9),
                "realized_pnl_delta_sol": realized_delta,
                "cost_basis_after_sol": position.cost_basis_sol,
                "provenance": "estimated from reconciled token balance and latest accepted mark price; confirmed wallet proceeds are not yet available",
            }
            fill["accounting"] = accounting_event
            position.realized_pnl_events.append(accounting_event)
            position.realized_pnl_events = position.realized_pnl_events[-25:]
            if sale_fraction >= 0.999:
                position.status = "closed"
        position.cost_basis_breakdown = self._live_cost_basis_breakdown(position)
        position.updated_at = now
        position.reconciliation_status = "pending"
        position.version += 1
        self.storage.save_live_ledger_position(position)
        return self._reconcile_live_audit(audit)

    def _account_key_pubkey(self, account_key: object) -> str:
        if isinstance(account_key, dict):
            return str(account_key.get("pubkey") or account_key.get("account") or "")
        return str(account_key or "")

    def _ui_token_amount(self, token_amount: dict[str, object]) -> float:
        ui_amount = token_amount.get("uiAmount")
        if ui_amount is not None:
            return float(ui_amount or 0.0)
        raw_amount = token_amount.get("amount")
        decimals = int(token_amount.get("decimals") or 0)
        if raw_amount is None:
            return 0.0
        return float(raw_amount or 0.0) / (10**decimals)

    def _token_balance_total_from_meta(self, balances: object, mint: str, wallet: str) -> float:
        total = 0.0
        if not isinstance(balances, list):
            return total
        for row in balances:
            if not isinstance(row, dict):
                continue
            if str(row.get("mint") or "") != mint:
                continue
            owner = str(row.get("owner") or "")
            if owner and owner != wallet:
                continue
            token_amount = row.get("uiTokenAmount")
            if isinstance(token_amount, dict):
                total += self._ui_token_amount(token_amount)
        return round(total, 9)

    def _live_transaction_effects(self, audit: LiveExecutionAudit, transaction_details: dict[str, object]) -> dict[str, object]:
        transaction = transaction_details.get("transaction")
        if not isinstance(transaction, dict):
            return {"ok": False, "error": str(transaction_details.get("error") or "missing transaction metadata")}
        meta = transaction.get("meta")
        tx = transaction.get("transaction")
        if not isinstance(meta, dict) or not isinstance(tx, dict):
            return {"ok": False, "error": "transaction metadata is incomplete"}
        message = tx.get("message") if isinstance(tx.get("message"), dict) else {}
        account_keys = message.get("accountKeys") if isinstance(message, dict) else []
        wallet_index = None
        if isinstance(account_keys, list):
            for index, account_key in enumerate(account_keys):
                if self._account_key_pubkey(account_key) == audit.wallet_public_key:
                    wallet_index = index
                    break
        pre_balances = meta.get("preBalances") if isinstance(meta.get("preBalances"), list) else []
        post_balances = meta.get("postBalances") if isinstance(meta.get("postBalances"), list) else []
        wallet_sol_delta = 0.0
        if wallet_index is not None and wallet_index < len(pre_balances) and wallet_index < len(post_balances):
            wallet_sol_delta = round((float(post_balances[wallet_index]) - float(pre_balances[wallet_index])) / LAMPORTS_PER_SOL, 9)
        positive_deltas = []
        account_creation_lamports = 0
        if isinstance(account_keys, list):
            for index, (pre_balance, post_balance) in enumerate(zip(pre_balances, post_balances)):
                if index == wallet_index:
                    continue
                delta = int(post_balance) - int(pre_balance)
                if delta <= 0:
                    continue
                positive_deltas.append(
                    {
                        "index": index,
                        "pubkey": self._account_key_pubkey(account_keys[index]) if index < len(account_keys) else "",
                        "pre_lamports": int(pre_balance),
                        "post_lamports": int(post_balance),
                        "delta_sol": round(delta / LAMPORTS_PER_SOL, 9),
                        "likely_account_creation": int(pre_balance) == 0,
                    }
                )
                if int(pre_balance) == 0:
                    account_creation_lamports += delta
        pre_tokens = self._token_balance_total_from_meta(meta.get("preTokenBalances"), audit.mint, audit.wallet_public_key)
        post_tokens = self._token_balance_total_from_meta(meta.get("postTokenBalances"), audit.mint, audit.wallet_public_key)
        token_delta = round(post_tokens - pre_tokens, 9)
        signatures = tx.get("signatures") if isinstance(tx.get("signatures"), list) else []
        signature_count = max(1, len(signatures))
        network_fee_sol = round(float(meta.get("fee") or 0.0) / LAMPORTS_PER_SOL, 9)
        base_fee_sol = round((signature_count * SOLANA_SIGNATURE_BASE_FEE_LAMPORTS) / LAMPORTS_PER_SOL, 9)
        priority_fee_sol = round(max(0.0, network_fee_sol - base_fee_sol), 9)
        wallet_spent = round(max(0.0, -wallet_sol_delta), 9)
        account_creation_sol = round(account_creation_lamports / LAMPORTS_PER_SOL, 9)
        spend_breakdown = {
            "wallet_spent_sol": wallet_spent,
            "network_fee_sol": network_fee_sol,
            "net_account_creation_sol": account_creation_sol,
            "net_trade_and_program_sol": round(max(0.0, wallet_spent - network_fee_sol - account_creation_sol), 9),
            "positive_account_deltas": positive_deltas,
        }
        return {
            "ok": True,
            "source": "getTransaction",
            "signature": audit.transaction_signature,
            "wallet_index": wallet_index,
            "wallet_sol_delta_sol": wallet_sol_delta,
            "pre_token_balance": pre_tokens,
            "post_token_balance": post_tokens,
            "token_delta": token_delta,
            "network_fee_sol": network_fee_sol,
            "base_fee_sol": base_fee_sol,
            "priority_fee_sol": priority_fee_sol,
            "spend_breakdown": spend_breakdown,
        }

    def _apply_live_transaction_effects(self, audit: LiveExecutionAudit, position: LiveLedgerPosition, effects: dict[str, object]) -> None:
        if not effects.get("ok"):
            return
        fill = next((row for row in position.fills if row.get("audit_id") == audit.id), None)
        if fill is None:
            return
        wallet_sol_delta = float(effects.get("wallet_sol_delta_sol", 0.0) or 0.0)
        token_delta = float(effects.get("token_delta", 0.0) or 0.0)
        network_fee_sol = float(effects.get("network_fee_sol", 0.0) or 0.0)
        base_fee_sol = float(effects.get("base_fee_sol", 0.0) or 0.0)
        priority_fee_sol = float(effects.get("priority_fee_sol", 0.0) or 0.0)
        fill["fee_sol"] = round(network_fee_sol, 9)
        fill["priority_fee_sol"] = round(priority_fee_sol, 9)
        if audit.action == "buy":
            wallet_spent = round(max(0.0, -wallet_sol_delta), 9)
            try:
                requested_amount = float(audit.amount)
            except ValueError:
                requested_amount = 0.0
            spend_breakdown = effects.get("spend_breakdown") if isinstance(effects.get("spend_breakdown"), dict) else {}
            fill["token_amount"] = round(max(token_delta, 0.0), 9)
            fill["accounting"] = {
                "type": "buy",
                "method": position.cost_basis_method,
                "provenance": "transaction_meta",
                "wallet_sol_delta_sol": round(wallet_sol_delta, 9),
                "wallet_sol_spent_sol": wallet_spent,
                "requested_amount_sol": round(requested_amount, 9),
                "confirmed_spend_over_request_sol": round(max(0.0, wallet_spent - requested_amount), 9),
                "token_delta": round(token_delta, 9),
                "network_fee_sol": round(network_fee_sol, 9),
                "base_fee_sol": round(base_fee_sol, 9),
                "priority_fee_sol": round(priority_fee_sol, 9),
                "cost_basis_added_sol": wallet_spent,
                "spend_breakdown": spend_breakdown,
            }
            if requested_amount > 0 and wallet_spent > requested_amount + 0.000001:
                position.review_notes = self._append_review_note(position.review_notes, "confirmed wallet spend exceeded requested amount")
        else:
            wallet_received = round(max(0.0, wallet_sol_delta), 9)
            fill["token_amount"] = round(abs(min(token_delta, 0.0)), 9)
            fill["accounting"] = {
                "type": "sell",
                "audit_id": audit.id,
                "recorded_at": utc_now().isoformat(),
                "method": position.cost_basis_method,
                "provenance": "transaction_meta",
                "wallet_sol_delta_sol": round(wallet_sol_delta, 9),
                "wallet_sol_received_sol": wallet_received,
                "token_delta": round(token_delta, 9),
                "network_fee_sol": round(network_fee_sol, 9),
                "base_fee_sol": round(base_fee_sol, 9),
                "priority_fee_sol": round(priority_fee_sol, 9),
            }
        self._recompute_live_position_accounting(position)

    def _append_review_note(self, current: str, note: str) -> str:
        notes = [item.strip() for item in str(current or "").split(";") if item.strip()]
        if note not in notes:
            notes.append(note)
        return "; ".join(notes)

    def _has_confirmed_buy_spend_over_trade_cap(self, wallet_public_key: str) -> bool:
        wallet = wallet_public_key.strip()
        cap = float(self.settings.live_max_trade_sol or 0.0)
        if not wallet or cap <= 0:
            return False
        for position in self.storage.load_live_ledger_positions(500):
            if position.wallet_public_key != wallet:
                continue
            for fill in position.fills:
                if str(fill.get("action") or "").lower() != "buy":
                    continue
                accounting = fill.get("accounting") if isinstance(fill.get("accounting"), dict) else {}
                if accounting.get("provenance") != "transaction_meta":
                    continue
                spent = float(accounting.get("wallet_sol_spent_sol", 0.0) or 0.0)
                if spent > cap + 0.000001:
                    return True
        return False

    def _recompute_live_position_accounting(self, position: LiveLedgerPosition) -> None:
        cost_basis = 0.0
        realized_pnl = 0.0
        total_fees = 0.0
        total_priority = 0.0
        accounting_token_balance = 0.0
        realized_events: list[dict[str, object]] = []
        for fill in position.fills:
            action = str(fill.get("action") or "").lower()
            accounting = fill.get("accounting") if isinstance(fill.get("accounting"), dict) else {}
            exact = accounting.get("provenance") == "transaction_meta"
            fee_sol = float(accounting.get("network_fee_sol", fill.get("fee_sol", 0.0)) or 0.0)
            priority_fee_sol = float(accounting.get("priority_fee_sol", fill.get("priority_fee_sol", 0.0)) or 0.0)
            total_fees += fee_sol
            total_priority += priority_fee_sol
            if action == "buy":
                if exact:
                    token_delta = max(0.0, float(accounting.get("token_delta", 0.0) or 0.0))
                    cost_added = float(accounting.get("wallet_sol_spent_sol", 0.0) or 0.0)
                else:
                    token_delta = max(0.0, float(fill.get("token_amount", 0.0) or 0.0))
                    cost_added = float(fill.get("amount_sol", 0.0) or 0.0) + priority_fee_sol
                accounting_token_balance += token_delta
                cost_basis += cost_added
                accounting["cost_basis_added_sol"] = round(cost_added, 9)
                accounting["cost_basis_after_sol"] = round(cost_basis, 9)
                fill["accounting"] = accounting
            elif action == "sell":
                if exact:
                    token_delta = float(accounting.get("token_delta", 0.0) or 0.0)
                    sold_tokens = abs(min(token_delta, 0.0))
                    token_balance_before = accounting_token_balance if accounting_token_balance > 0 else max(position.token_balance, sold_tokens)
                    sale_fraction = min(1.0, max(0.0, sold_tokens / token_balance_before)) if token_balance_before > 0 else 1.0
                    proceeds = float(accounting.get("wallet_sol_received_sol", 0.0) or 0.0)
                else:
                    sale_fraction = float(accounting.get("sale_fraction", 0.0) or 0.0)
                    proceeds = float(accounting.get("estimated_proceeds_sol", 0.0) or 0.0)
                    token_balance_before = accounting_token_balance if accounting_token_balance > 0 else position.token_balance
                    sold_tokens = token_balance_before * sale_fraction
                consumed_basis = min(cost_basis, cost_basis * sale_fraction)
                realized_delta = proceeds - consumed_basis
                cost_basis = max(0.0, cost_basis - consumed_basis)
                accounting_token_balance = max(0.0, accounting_token_balance - sold_tokens)
                accounting["sale_fraction"] = round(sale_fraction, 6)
                accounting["token_balance_before"] = round(token_balance_before, 9)
                accounting["cost_basis_consumed_sol"] = round(consumed_basis, 9)
                if exact:
                    accounting["realized_proceeds_sol"] = round(proceeds, 9)
                else:
                    accounting["estimated_proceeds_sol"] = round(proceeds, 9)
                accounting["realized_pnl_delta_sol"] = round(realized_delta, 9)
                accounting["cost_basis_after_sol"] = round(cost_basis, 9)
                fill["accounting"] = accounting
                realized_pnl += realized_delta
                realized_events.append(accounting)
        position.cost_basis_sol = round(cost_basis, 9)
        position.realized_pnl_sol = round(realized_pnl, 9)
        position.total_fees_sol = round(total_fees, 9)
        position.total_priority_fees_sol = round(total_priority, 9)
        position.realized_pnl_events = realized_events[-25:]
        if position.token_balance <= 0 and any(str(fill.get("action", "")).lower() == "sell" for fill in position.fills):
            position.status = "closed"
        elif position.fills:
            position.status = "open"
        position.cost_basis_breakdown = self._live_cost_basis_breakdown(position)

    def _reconcile_live_audit(self, audit: LiveExecutionAudit) -> LiveLedgerPosition | None:
        wallet = audit.wallet_public_key
        position = next((item for item in self.storage.load_live_ledger_positions(500) if item.mint == audit.mint and item.wallet_public_key == wallet), None)
        if position is None:
            return None
        material_before = (
            position.status,
            float(position.token_balance),
            position.reconciliation_status,
            len(position.fills),
        )
        balance = self._wallet_token_balance(wallet, audit.mint)
        if not balance.get("checked_at"):
            balance["checked_at"] = utc_now().isoformat()
        transaction_reconciliation: dict[str, object] = {}
        transaction_effects_applied = False
        if audit.transaction_signature:
            transaction_details = self._transaction_details(audit.transaction_signature)
            transaction_reconciliation = {
                "ok": bool(transaction_details.get("ok")),
                "found": bool(transaction_details.get("found")),
                "signature": audit.transaction_signature,
                "error": str(transaction_details.get("error") or ""),
            }
            if transaction_details.get("ok") and transaction_details.get("found"):
                effects = self._live_transaction_effects(audit, transaction_details)
                transaction_reconciliation = {**transaction_reconciliation, **effects}
                if effects.get("ok"):
                    self._apply_live_transaction_effects(audit, position, effects)
                    transaction_effects_applied = True
            elif transaction_details.get("error"):
                self._append_unique(audit.warnings, f"Transaction metadata reconciliation skipped: {transaction_details['error']}")
        if transaction_reconciliation:
            balance["transaction"] = transaction_reconciliation
        position.reconciliation = balance
        audit.reconciliation = balance
        checked_at = self._parse_iso_datetime(str(balance.get("checked_at") or ""))
        position.balance_verified_at = checked_at
        position.balance_age_seconds = 0 if checked_at else None
        if balance.get("error"):
            position.reconciliation_status = "needs_review"
            audit.reconciliation_status = "needs_review"
            audit.status = "needs_review"
            audit.final_status = "needs_review"
            audit.recommended_action = "Review wallet/RPC balance reconciliation."
            self._append_unique(audit.warnings, f"Reconciliation needs review: {balance['error']}")
        else:
            position.token_balance = float(balance.get("token_balance") or 0.0)
            position.reconciliation_status = "matched"
            audit.reconciliation_status = "matched"
            self._normalize_live_position_status(position)
            if transaction_effects_applied:
                self._recompute_live_position_accounting(position)
        self._refresh_live_position_estimate(position)
        position.updated_at = utc_now()
        material_after = (
            position.status,
            float(position.token_balance),
            position.reconciliation_status,
            len(position.fills),
        )
        if material_after != material_before:
            position.version += 1
        audit.updated_at = utc_now()
        self.storage.save_live_ledger_position(position)
        self.storage.save_live_execution_audit(audit)
        return position

    def _live_ledger_positions(self, wallet_public_key: str = "") -> list[LiveLedgerPosition]:
        positions = self.storage.load_live_ledger_positions(500)
        if wallet_public_key.strip():
            positions = [position for position in positions if position.wallet_public_key == wallet_public_key.strip()]
        refreshed: list[LiveLedgerPosition] = []
        for position in positions:
            previous_status = position.status
            self._normalize_live_position_status(position)
            if position.status != previous_status:
                position.version += 1
                position.updated_at = utc_now()
            self._refresh_live_position_estimate(position)
            self.storage.save_live_ledger_position(position)
            refreshed.append(position)
        return refreshed

    def _refresh_live_position_estimate(self, position: LiveLedgerPosition) -> None:
        mark = self._latest_live_mark_price_snapshot(position.mint)
        observed_at = (
            mark.get("observed_at")
            if isinstance(mark.get("observed_at"), datetime)
            else None
        )
        now = utc_now()
        mark_age = self._mobile_mark_age(observed_at, now)
        price = (
            float(mark.get("price", 0.0) or 0.0)
            if mark_age is not None
            else 0.0
        )
        position.mark_price_sol = price
        position.mark_price_source = str(mark.get("source", ""))
        position.mark_price_confidence = (
            float(mark.get("confidence", 0.0) or 0.0)
            if mark_age is not None
            else 0.0
        )
        position.mark_price_at = observed_at if mark_age is not None else None
        position.mark_price_age_seconds = mark_age
        if price > 0 and position.token_balance > 0:
            estimated_value = position.token_balance * price
            position.unrealized_pnl_sol = round(estimated_value - position.cost_basis_sol, 9)
            position.average_entry_price_sol = round(position.cost_basis_sol / position.token_balance, 12) if position.token_balance else 0.0
        elif position.status == "closed" or position.token_balance <= 0:
            position.unrealized_pnl_sol = 0.0
        position.cost_basis_breakdown = self._live_cost_basis_breakdown(position)
        self._annotate_live_position_pnl_confidence(position)

    def _live_cost_basis_breakdown(self, position: LiveLedgerPosition) -> dict[str, object]:
        buy_fills = [fill for fill in position.fills if str(fill.get("action", "")).lower() == "buy"]
        sell_fills = [fill for fill in position.fills if str(fill.get("action", "")).lower() == "sell"]
        gross_buy_sol = round(sum(float(fill.get("amount_sol", 0.0) or 0.0) for fill in buy_fills), 9)
        priority_fees_sol = round(sum(float(fill.get("priority_fee_sol", 0.0) or 0.0) for fill in position.fills), 9)
        realized_events = position.realized_pnl_events or [
            accounting
            for fill in sell_fills
            if isinstance((accounting := fill.get("accounting")), dict)
        ]
        consumed_basis = round(sum(float(event.get("cost_basis_consumed_sol", 0.0) or 0.0) for event in realized_events), 9)
        estimated_proceeds = round(sum(float(event.get("estimated_proceeds_sol", 0.0) or 0.0) for event in realized_events), 9)
        realized_proceeds = round(sum(float(event.get("realized_proceeds_sol", 0.0) or 0.0) for event in realized_events), 9)
        realized_delta = round(sum(float(event.get("realized_pnl_delta_sol", 0.0) or 0.0) for event in realized_events), 9)
        uses_transaction_meta = any(isinstance(fill.get("accounting"), dict) and fill["accounting"].get("provenance") == "transaction_meta" for fill in position.fills)
        return {
            "method": position.cost_basis_method,
            "buy_fills": len(buy_fills),
            "sell_fills": len(sell_fills),
            "gross_buy_sol": gross_buy_sol,
            "priority_fees_sol": priority_fees_sol,
            "consumed_basis_sol": consumed_basis,
            "remaining_basis_sol": round(position.cost_basis_sol, 9),
            "estimated_proceeds_sol": estimated_proceeds,
            "realized_proceeds_sol": realized_proceeds,
            "realized_pnl_from_events_sol": realized_delta,
            "average_entry_price_sol": position.average_entry_price_sol,
            "explanation": "Weighted-average live cost basis from confirmed wallet deltas when transaction metadata is available." if uses_transaction_meta else "Weighted-average live cost basis. Sell proceeds are estimated from latest mark price until wallet/RPC proceeds are available.",
        }

    def _stale_balance_positions(self, wallet_public_key: str = "") -> list[LiveLedgerPosition]:
        positions = self._live_ledger_positions(wallet_public_key)
        stale: list[LiveLedgerPosition] = []
        for position in positions:
            if position.status != "open" or position.token_balance <= 0:
                continue
            if position.reconciliation_status != "matched":
                stale.append(position)
                continue
            if position.balance_age_seconds is None or position.balance_age_seconds > self.settings.source_stale_seconds:
                stale.append(position)
        return stale

    def _annotate_live_position_pnl_confidence(self, position: LiveLedgerPosition) -> None:
        notes: list[str] = []
        mark_age = position.mark_price_age_seconds
        mark_is_stale = mark_age is not None and mark_age > self.settings.source_stale_seconds
        if position.balance_verified_at:
            position.balance_age_seconds = max(0, int((utc_now() - position.balance_verified_at).total_seconds()))
        elif position.reconciliation_status == "matched":
            position.balance_age_seconds = None
        if position.reconciliation_status == "needs_review":
            realized = "needs_review"
            unrealized = "needs_review"
            notes.append("wallet/RPC reconciliation needs review")
        else:
            realized = "audited" if position.reconciliation_status == "matched" else "estimated"
            if position.status == "closed" or position.token_balance <= 0:
                unrealized = "none"
            elif position.mark_price_sol <= 0:
                unrealized = "unknown"
                notes.append("no accepted mark price is available")
            elif mark_is_stale:
                unrealized = "stale"
                notes.append(f"mark price is older than {self.settings.source_stale_seconds}s")
            elif position.mark_price_confidence >= self.settings.min_price_confidence:
                unrealized = "estimated"
            else:
                unrealized = "low_confidence"
                notes.append("mark price confidence is below the configured floor")
        if position.reconciliation_status != "matched":
            notes.append("token balance has not been fully reconciled")
        elif position.balance_age_seconds is None:
            notes.append("token balance verification age is unknown")
        elif position.balance_age_seconds > self.settings.source_stale_seconds:
            notes.append(f"token balance verification is older than {self.settings.source_stale_seconds}s")
        if position.mark_price_source:
            notes.append(f"mark source: {position.mark_price_source}")
        position.realized_pnl_confidence = realized
        position.unrealized_pnl_confidence = unrealized
        position.pnl_confidence_notes = list(dict.fromkeys(notes))

    def _live_sale_fraction(self, position: LiveLedgerPosition, audit: LiveExecutionAudit, token_amount: float, denominated_in_sol: bool) -> float:
        amount_text = str(audit.amount).strip()
        if amount_text.endswith("%"):
            try:
                return min(1.0, max(0.0, float(amount_text.replace("%", "")) / 100))
            except ValueError:
                return 1.0
        if not denominated_in_sol and token_amount > 0 and position.token_balance > 0:
            return min(1.0, max(0.0, token_amount / position.token_balance))
        return 0.0

    def _normalize_live_position_status(self, position: LiveLedgerPosition) -> None:
        has_sell_fill = any(str(fill.get("action", "")).lower() == "sell" for fill in position.fills)
        if position.token_balance <= 0:
            position.token_balance = 0.0
            if has_sell_fill:
                position.status = "closed"
        elif position.fills:
            position.status = "open"

    def _latest_live_mark_price(self, mint: str) -> float:
        return float(self._latest_live_mark_price_snapshot(mint).get("price", 0.0) or 0.0)

    def _latest_live_mark_price_snapshot(self, mint: str) -> dict[str, object]:
        token = next((item for item in self.storage.load_all_tokens(5000) if item.mint == mint), None)
        now = utc_now()
        for observation in self.storage.load_price_observations_newest_first(100, mint=mint):
            if (
                observation.accepted
                and self._mobile_mark_age(observation.observed_at, now) is not None
            ):
                for key, value in (
                    ("selected_price", observation.selected_price),
                    ("price", observation.price),
                    ("direct_price", observation.direct_price),
                    ("market_cap_price", observation.market_cap_price),
                ):
                    price = float(value or 0.0)
                    if price > 0:
                        return {
                            "price": price,
                            "source": f"{observation.source}:{observation.price_source or key}",
                            "confidence": float(observation.confidence or 0.0),
                            "observed_at": observation.observed_at,
                        }
        if token and self._mobile_mark_age(token.detected_at, now) is not None:
            for source, value in (("token_current_price", token.current_price), ("token_exit_price", token.exit_price), ("token_entry_price", token.entry_price)):
                price = float(value or 0.0)
                if price > 0:
                    return {
                        "price": price,
                        "source": source,
                        "confidence": float(token.price_confidence or 0.0),
                        "observed_at": token.detected_at,
                    }
        return {"price": 0.0, "source": "", "confidence": 0.0, "observed_at": None}

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
        blockers.append("legacy manual live request capture is audit-only; use the live intent quote/submit path for implemented local execution")
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
        signer = self.signer_status(self.settings.live_signer_mode, "")
        grouped: dict[str, list[dict[str, object]]] = {}
        for event in events:
            grouped.setdefault(event.subsystem or "app", []).append(event.to_dict())
        live_recovery = {
            "last_poll_at": self.live_last_poll_at.isoformat() if self.live_last_poll_at else None,
            "summary": self.live_last_poll_summary,
            "unresolved_audits": len([audit for audit in self.storage.load_live_execution_audits(200) if self._is_unresolved_live_audit(audit)]),
        }
        return {
            "backend": {"status": "running", "bot_status": self.status.value, "database_path": str(self.storage.path)},
            "source": source,
            "storage": self.data_summary(),
            "schema": self.storage.schema_status(),
            "backup_restore": self.storage.backup_restore_status(),
            "signer_daemon": signer,
            "live_recovery": live_recovery,
            "recent_errors": [event.to_dict() for event in events if event.level in {"danger", "error"}][:20],
            "recent_warnings": [event.to_dict() for event in events if event.level == "warning"][:20],
            "events_by_subsystem": {key: value[:10] for key, value in grouped.items()},
            "observability": self._observability_summary(events, source, signer, live_recovery),
        }

    def operator_logs_report(
        self,
        timeframe: str = "24h",
        level: str = "",
        subsystem: str = "",
        limit: int = 200,
    ) -> dict[str, object]:
        cutoff = self._timeframe_cutoff(timeframe)
        level_filter = level.strip().lower()
        subsystem_filter = subsystem.strip().lower()
        bounded_limit = max(1, min(1000, int(limit or 200)))
        events = self.storage.load_all_events(5000)
        filtered: list[TradeEvent] = []
        for event in events:
            if cutoff and event.created_at < cutoff:
                continue
            if level_filter and event.level.lower() != level_filter:
                continue
            if subsystem_filter and (event.subsystem or "app").lower() != subsystem_filter:
                continue
            filtered.append(event)

        level_counts: dict[str, int] = {}
        subsystem_counts: dict[str, int] = {}
        session_counts: dict[str, int] = {}
        recovery_keywords = ("recovery", "restore", "backup", "reconcile", "unresolved", "needs_review")
        source_keywords = ("source", "pumpportal", "solana", "parser", "replay", "soak")
        live_keywords = ("live", "intent", "quote", "simulation", "sign", "wallet", "kill switch")
        recovery_events = 0
        source_events = 0
        live_events = 0
        action_items: list[str] = []
        for event in filtered:
            level_counts[event.level] = level_counts.get(event.level, 0) + 1
            subsystem_name = event.subsystem or "app"
            subsystem_counts[subsystem_name] = subsystem_counts.get(subsystem_name, 0) + 1
            if event.session_id:
                session_counts[event.session_id] = session_counts.get(event.session_id, 0) + 1
            text = f"{event.subsystem} {event.message} {event.operator_action}".lower()
            if any(keyword in text for keyword in recovery_keywords):
                recovery_events += 1
            if any(keyword in text for keyword in source_keywords):
                source_events += 1
            if any(keyword in text for keyword in live_keywords):
                live_events += 1
            if event.operator_action and event.level in {"warning", "danger", "error"}:
                action_items.append(event.operator_action)

        recent = filtered[:bounded_limit]
        errors = level_counts.get("error", 0) + level_counts.get("danger", 0)
        warnings = level_counts.get("warning", 0)
        return {
            "artifact_type": "cryptoarc_operator_logs",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "timeframe": timeframe,
            "filters": {
                "level": level_filter,
                "subsystem": subsystem_filter,
                "limit": bounded_limit,
            },
            "summary": {
                "total_events": len(filtered),
                "returned_events": len(recent),
                "warnings": warnings,
                "errors": errors,
                "subsystems": len(subsystem_counts),
                "sessions": len(session_counts),
                "recovery_related_events": recovery_events,
                "source_related_events": source_events,
                "live_related_events": live_events,
            },
            "level_counts": level_counts,
            "subsystem_counts": [
                {"subsystem": name, "events": count}
                for name, count in sorted(subsystem_counts.items(), key=lambda item: (-item[1], item[0]))[:25]
            ],
            "session_counts": [
                {"session_id": session_id, "events": count}
                for session_id, count in sorted(session_counts.items(), key=lambda item: (-item[1], item[0]))[:25]
            ],
            "events": [event.to_dict() for event in recent],
            "action_items": list(dict.fromkeys(action_items))[:10],
            "operator_action": (
                "Review danger/error events and export this artifact before the next live session."
                if errors
                else "Review warning-heavy subsystems before increasing autonomy."
                if warnings
                else "Structured local logs are clean for the selected window."
            ),
            "privacy_note": "Local event logs may include wallet public keys, transaction signatures, mints, and operational context; they never intentionally include seed phrases.",
        }

    def _observability_summary(
        self,
        events: list[TradeEvent],
        source: dict[str, object],
        signer: dict[str, object],
        live_recovery: dict[str, object],
    ) -> dict[str, object]:
        level_counts: dict[str, int] = {}
        subsystem_counts: dict[str, dict[str, object]] = {}
        readiness_keywords = ("readiness", "promotion", "shadow", "source trust", "live blocker", "blocked", "kill switch")
        readiness_events: list[TradeEvent] = []
        session_counts: dict[str, int] = {}
        for event in events:
            level_counts[event.level] = level_counts.get(event.level, 0) + 1
            if event.session_id:
                session_counts[event.session_id] = session_counts.get(event.session_id, 0) + 1
            subsystem = event.subsystem or "app"
            row = subsystem_counts.setdefault(
                subsystem,
                {
                    "subsystem": subsystem,
                    "events": 0,
                    "warnings": 0,
                    "errors": 0,
                    "latest_at": "",
                    "latest_message": "",
                },
            )
            row["events"] = int(row["events"]) + 1
            if event.level == "warning":
                row["warnings"] = int(row["warnings"]) + 1
            if event.level in {"danger", "error"}:
                row["errors"] = int(row["errors"]) + 1
            if event.created_at.isoformat() > str(row["latest_at"]):
                row["latest_at"] = event.created_at.isoformat()
                row["latest_message"] = event.message
            text = f"{event.message} {event.operator_action}".lower()
            if any(keyword in text for keyword in readiness_keywords):
                readiness_events.append(event)
        high_severity = [event for event in events if event.level in {"danger", "error", "warning"}]
        source_metrics = {
            "status": source.get("status"),
            "trust_state": source.get("trust_state"),
            "events_per_minute": source.get("events_per_minute"),
            "health_score": source.get("health_score"),
            "reconnect_attempts": source.get("reconnect_attempts"),
            "live_entry_blocked": source.get("live_entry_blocked"),
        }
        signer_metrics = {
            "mode": signer.get("mode"),
            "connected": signer.get("connected"),
            "healthy": signer.get("healthy"),
            "can_sign": signer.get("can_sign"),
            "can_unattended_sign": signer.get("can_unattended_sign"),
            "disabled_reason": signer.get("disabled_reason"),
        }
        return {
            "generated_at": utc_now().isoformat(),
            "event_count": len(events),
            "level_counts": level_counts,
            "session_metrics": {
                "active_session_id": self.active_live_session_id,
                "session_event_count": sum(session_counts.values()),
                "sessions_seen": len(session_counts),
                "top_sessions": [
                    {"session_id": session_id, "events": count}
                    for session_id, count in sorted(session_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
                ],
            },
            "subsystems": sorted(subsystem_counts.values(), key=lambda item: (-int(item["errors"]), -int(item["warnings"]), str(item["subsystem"]))),
            "high_severity": [event.to_dict() for event in high_severity[:20]],
            "readiness_changes": [event.to_dict() for event in readiness_events[:20]],
            "source_metrics": source_metrics,
            "signer_metrics": signer_metrics,
            "recovery_metrics": live_recovery,
            "operator_action": "Review high-severity events first, then subsystem rows with warnings/errors before real-money operation.",
        }

    def operator_session_report(self, timeframe: str = "24h", wallet_public_key: str = "") -> dict[str, object]:
        events = self.storage.load_all_events(500)
        live_audits = self._normalize_live_audits(self.storage.load_live_execution_audits(500))
        unresolved = [audit for audit in live_audits if self._is_unresolved_live_audit(audit)]
        wallet = wallet_public_key.strip() or self.settings.live_active_wallet_public_key or self.settings.live_hot_wallet_public_key
        live_ledger = self.live_ledger(wallet) if wallet else self.live_ledger("")
        open_risk = self._open_risk_report(wallet, live_ledger, unresolved)
        source = self.source_health()
        source_quality = self._session_source_quality(source)
        performance = self.performance_analytics()
        readiness = self.readiness_status()
        action_items: list[str] = []
        action_items.extend(str(item) for item in readiness.get("recommended_actions", [])[:5])
        action_items.extend(str(item) for item in open_risk.get("action_items", [])[:5])
        if source.get("live_entry_blocked"):
            action_items.append(str(source.get("operator_action") or "Review source health before live entries."))
        if unresolved:
            action_items.append(f"Review or recover {len(unresolved)} unresolved live audit{'s' if len(unresolved) != 1 else ''}.")
        if self.settings.kill_switch_enabled:
            action_items.append("Kill switch is enabled; clear it only after reviewing live blockers.")
        if not self.storage.backup_restore_status().get("latest_backup"):
            action_items.append("Create a backup artifact before real-money operation.")
        return {
            "artifact_type": "cryptoarc_operator_session_report",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "timeframe": timeframe,
            "wallet_public_key": wallet,
            "bot": {"status": self.status.value, "mode": self.settings.mode.value if hasattr(self.settings.mode, "value") else self.settings.mode},
            "paper_pnl": self.monitor_pnl_summary(timeframe),
            "mode_comparison": performance.get("mode_comparison", {}),
            "live_ledger": live_ledger,
            "open_risk": open_risk,
            "source": source,
            "source_quality": source_quality,
            "readiness": {
                "status": readiness.get("status"),
                "score": readiness.get("score"),
                "entries_allowed": readiness.get("entries_allowed"),
                "strategy_promotion": readiness.get("strategy_promotion"),
                "execution_readiness": readiness.get("execution_readiness"),
            },
            "live_recovery": {
                "last_poll_at": self.live_last_poll_at.isoformat() if self.live_last_poll_at else None,
                "summary": self.live_last_poll_summary,
                "unresolved_audits": [audit.to_dict() for audit in unresolved[:25]],
            },
            "alerts": self.alerts.status(),
            "backup_restore": self.storage.backup_restore_status(),
            "recent_events": [event.to_dict() for event in events[:50]],
            "action_items": list(dict.fromkeys(action_items)),
        }

    def evidence_mode_separation_report(self) -> dict[str, object]:
        trades = [trade for trade in self.storage.load_trades(5000) if trade.closed_at and trade.pnl_sol is not None]
        backtests = self.storage.load_backtest_runs(200)
        audits = self._refresh_shadow_comparisons(self._normalize_live_audits(self.storage.load_live_execution_audits(500)))
        intents_by_id = {intent.id: intent for intent in self.storage.load_live_intents(500)}
        ledger_summary = self._wallet_performance_analytics()["summary"]

        shadow_audits = [audit for audit in audits if isinstance(audit.shadow_comparison, dict) and audit.shadow_comparison]
        shadow_evaluated = [audit for audit in shadow_audits if audit.shadow_comparison.get("status") == "evaluated"]
        shadow_pnl = round(sum(float(audit.shadow_comparison.get("estimated_pnl_sol", 0.0) or 0.0) for audit in shadow_evaluated), 6)

        live_audits = [audit for audit in audits if not (isinstance(audit.shadow_comparison, dict) and audit.shadow_comparison)]
        autonomous_sources = {"paper_promoted", "watchlist", "live_position_rules"}
        autonomous_audits = [
            audit
            for audit in live_audits
            if (intents_by_id.get(audit.intent_id) and intents_by_id[audit.intent_id].source in autonomous_sources)
            or str(audit.request.get("source", "")) in autonomous_sources
        ]
        autonomous_ids = {audit.id for audit in autonomous_audits}
        manual_audits = [audit for audit in live_audits if audit.id not in autonomous_ids]

        paper_pnl = round(sum(float(trade.pnl_sol or 0.0) for trade in trades), 6)
        replay_pnl = round(sum(float(run.estimated_pnl_sol or 0.0) for run in backtests), 6)
        live_pnl = round(float(ledger_summary.get("total_pnl_sol", 0.0) or 0.0), 6)
        contamination_warnings: list[str] = []
        if any(audit.request.get("source") in autonomous_sources and audit.id not in autonomous_ids for audit in live_audits):
            contamination_warnings.append("some live audits have automated request sources that could not be joined to stored intents")
        if shadow_audits and any(audit.transaction_signature for audit in shadow_audits):
            contamination_warnings.append("shadow audits include transaction signatures; verify they were not submitted as real-money trades")
        if live_audits and any(not audit.wallet_public_key for audit in live_audits):
            contamination_warnings.append("some live audits are missing wallet public keys")
        if trades and any(str(getattr(trade, "price_source", "") or "").lower() in {"wallet_rpc", "live"} for trade in trades):
            contamination_warnings.append("paper trade rows reference live-looking price sources")

        modes = [
            self._evidence_mode_row(
                "paper",
                "Closed paper trades",
                len(trades),
                paper_pnl,
                "paper trades",
                "closed trade records only",
                "clear" if trades else "missing",
                "Use for strategy review; do not treat as live execution evidence.",
                newest=[trade.closed_at for trade in trades if trade.closed_at],
            ),
            self._evidence_mode_row(
                "replay",
                "Backtests and parser replay",
                len(backtests),
                replay_pnl,
                "stored backtest runs",
                "backtest result fingerprints and replay sources",
                "clear" if backtests else "missing",
                "Run replay/backtests before promotion if this row is missing.",
                newest=[run.created_at for run in backtests],
                extra={"fingerprinted": len([run for run in backtests if getattr(run, "fingerprint", "")])},
            ),
            self._evidence_mode_row(
                "shadow",
                "Dry-run shadow quotes",
                len(shadow_audits),
                shadow_pnl,
                "live quote audits with shadow_comparison",
                "non-submitting quote comparison only",
                "clear" if shadow_evaluated else "missing" if not shadow_audits else "review",
                "Collect evaluated shadow comparisons before tiny real-money pilot.",
                newest=[audit.updated_at for audit in shadow_audits],
                extra={"evaluated": len(shadow_evaluated), "pending": max(0, len(shadow_audits) - len(shadow_evaluated))},
            ),
            self._evidence_mode_row(
                "manual_live",
                "Manual live",
                len(manual_audits),
                live_pnl,
                "submitted or blocked live audits without automated intent source",
                "wallet-scoped ledger and audit records",
                "clear" if manual_audits else "missing",
                "Manual live evidence must stay separate from paper and shadow evidence.",
                newest=[audit.updated_at for audit in manual_audits],
                extra={"submitted": len([audit for audit in manual_audits if audit.transaction_signature])},
            ),
            self._evidence_mode_row(
                "autonomous_live",
                "Autonomous live",
                len(autonomous_audits),
                live_pnl if autonomous_audits else 0.0,
                "live audits joined to automated intent sources",
                "paper_promoted, watchlist, or live_position_rules intents",
                "clear" if autonomous_audits else "missing",
                "Autonomous live evidence should appear only after every full-sniper gate passes.",
                newest=[audit.updated_at for audit in autonomous_audits],
                extra={"sources": sorted({(intents_by_id.get(audit.intent_id).source if intents_by_id.get(audit.intent_id) else str(audit.request.get("source", ""))) or "unknown" for audit in autonomous_audits})},
            ),
        ]
        ready = not contamination_warnings
        return {
            "artifact_type": "cryptoarc_evidence_mode_separation",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "status": "clear" if ready else "review",
            "ready": ready,
            "modes": modes,
            "contamination_warnings": contamination_warnings,
            "operator_action": "Evidence modes are separated for review." if ready else "Review contamination warnings before using evidence for promotion or live decisions.",
            "privacy_note": "Mode separation evidence contains local paper, replay, shadow, live audit, and public wallet evidence only. It must not contain seed phrases or private keys.",
        }

    def _evidence_mode_row(
        self,
        mode: str,
        label: str,
        samples: int,
        pnl_sol: float,
        source: str,
        boundary: str,
        status: str,
        operator_action: str,
        *,
        newest: list[datetime],
        extra: dict[str, object] | None = None,
    ) -> dict[str, object]:
        latest = max(newest).isoformat() if newest else None
        return {
            "mode": mode,
            "label": label,
            "samples": samples,
            "pnl_sol": round(float(pnl_sol or 0.0), 6),
            "source": source,
            "boundary": boundary,
            "status": status,
            "latest_at": latest,
            "operator_action": operator_action,
            **(extra or {}),
        }

    def _session_source_quality(self, source: dict[str, object]) -> dict[str, object]:
        history = source.get("quality_history", []) if isinstance(source, dict) else []
        buckets = history if isinstance(history, list) else []
        populated = [bucket for bucket in buckets if int(bucket.get("events", 0) or 0) > 0]
        events = sum(int(bucket.get("events", 0) or 0) for bucket in buckets)
        normalized = sum(int(bucket.get("normalized", 0) or 0) for bucket in buckets)
        malformed = sum(int(bucket.get("malformed", 0) or 0) for bucket in buckets)
        trade = sum(int(bucket.get("trade", 0) or 0) for bucket in buckets)
        degraded = [
            bucket
            for bucket in populated
            if str(bucket.get("trust_state", "")) in {"degraded", "conflicting", "stale"}
        ]
        normalized_ratio = round(normalized / max(1, normalized + malformed), 3) if events else 0.0
        status = "clear"
        warnings: list[str] = []
        if not events:
            status = "unknown"
            warnings.append("no source-quality buckets contain events yet")
        elif degraded:
            status = "review"
            warnings.append(f"{len(degraded)} source-quality bucket{'s' if len(degraded) != 1 else ''} need review")
        elif malformed:
            status = "review"
            warnings.append("malformed source events were seen in recent buckets")
        return {
            "status": status,
            "trust_state": source.get("trust_state", "unknown") if isinstance(source, dict) else "unknown",
            "health_score": source.get("health_score", 0) if isinstance(source, dict) else 0,
            "events": events,
            "normalized": normalized,
            "trade_events": trade,
            "malformed": malformed,
            "normalized_ratio": normalized_ratio,
            "degraded_buckets": len(degraded),
            "bucket_count": len(buckets),
            "warnings": warnings,
            "operator_action": "Collect source events before trusting replay." if status == "unknown" else "Review degraded source buckets before promotion." if status == "review" else "Source quality is clean for this session window.",
        }

    def _open_risk_report(self, wallet_public_key: str, live_ledger: dict[str, object] | None = None, unresolved: list[LiveExecutionAudit] | None = None) -> dict[str, object]:
        wallet = wallet_public_key.strip()
        ledger = live_ledger or self.live_ledger(wallet)
        summary = ledger.get("summary", {}) if isinstance(ledger, dict) else {}
        positions = ledger.get("positions", []) if isinstance(ledger, dict) else []
        open_positions = [position for position in positions if str(position.get("status", "")) == "open"] if isinstance(positions, list) else []
        active_intents = [
            intent
            for intent in self._decorate_live_intents(self._mark_stale_live_intents(self.storage.load_live_intents(200)))
            if intent.status in {"open", "quoted", "simulation_warning", "simulated"} and (not wallet or intent.wallet_public_key == wallet)
        ]
        unresolved = unresolved if unresolved is not None else [audit for audit in self._normalize_live_audits(self.storage.load_live_execution_audits(500)) if self._is_unresolved_live_audit(audit)]
        unresolved_for_wallet = [audit for audit in unresolved if not wallet or audit.wallet_public_key == wallet]
        cost_basis = float(summary.get("cost_basis_sol", 0.0) or 0.0)
        unrealized = float(summary.get("unrealized_pnl_sol", 0.0) or 0.0)
        realized = float(summary.get("realized_pnl_sol", 0.0) or 0.0)
        exposure_cap = float(self.settings.live_wallet_exposure_cap_sol or 0.0)
        daily_loss_cap = float(self.settings.live_daily_loss_cap_sol or 0.0)
        exposure_ratio = round(cost_basis / exposure_cap, 3) if exposure_cap > 0 else None
        pnl_total = round(realized + unrealized, 9)
        daily_loss_used = round(abs(min(0.0, pnl_total)) / daily_loss_cap, 3) if daily_loss_cap > 0 else None
        stale_balance_positions = int(summary.get("stale_balance_positions", 0) or 0)
        needs_review_positions = int(summary.get("needs_review_positions", 0) or 0)
        blockers: list[str] = []
        warnings: list[str] = []
        action_items: list[str] = []
        if unresolved_for_wallet:
            blockers.append("unresolved live audit recovery debt")
            action_items.append(f"Recover or inspect {len(unresolved_for_wallet)} unresolved live audit{'s' if len(unresolved_for_wallet) != 1 else ''}.")
        if needs_review_positions:
            blockers.append("live ledger positions need review")
            action_items.append("Review live ledger reconciliation before new entries.")
        if stale_balance_positions:
            blockers.append("stale live token-balance evidence")
            action_items.append("Refresh wallet balance reconciliation before unattended execution.")
        if exposure_cap <= 0:
            warnings.append("wallet exposure cap is not configured")
            action_items.append("Set a live wallet exposure cap before pilot mode.")
        elif exposure_ratio is not None and exposure_ratio >= 0.8:
            warnings.append("wallet exposure is near the configured cap")
            action_items.append("Reduce open exposure or raise the cap only after review.")
        if daily_loss_cap <= 0:
            warnings.append("daily loss cap is not configured")
            action_items.append("Set a live daily loss cap before pilot mode.")
        elif daily_loss_used is not None and daily_loss_used >= 0.8:
            warnings.append("daily loss usage is near the configured cap")
            action_items.append("Pause live entries and review loss exposure.")
        if active_intents:
            warnings.append("active live intents are still open")
            action_items.append(f"Resolve {len(active_intents)} active live intent{'s' if len(active_intents) != 1 else ''} before ending the session.")
        status = "blocked" if blockers else "warning" if warnings else "clear"
        return {
            "status": status,
            "wallet_public_key": wallet,
            "open_positions": len(open_positions),
            "active_intents": len(active_intents),
            "unresolved_audits": len(unresolved_for_wallet),
            "cost_basis_sol": round(cost_basis, 9),
            "unrealized_pnl_sol": round(unrealized, 9),
            "realized_pnl_sol": round(realized, 9),
            "total_live_pnl_sol": pnl_total,
            "wallet_exposure_cap_sol": exposure_cap,
            "exposure_ratio": exposure_ratio,
            "daily_loss_cap_sol": daily_loss_cap,
            "daily_loss_used_ratio": daily_loss_used,
            "stale_balance_positions": stale_balance_positions,
            "needs_review_positions": needs_review_positions,
            "pnl_confidence": summary.get("pnl_confidence", "none"),
            "blockers": blockers,
            "warnings": warnings,
            "action_items": list(dict.fromkeys(action_items)),
            "operator_action": "Resolve open risk blockers before new live entries." if blockers else "Review open risk warnings before ending the session." if warnings else "Open risk is clear for this wallet.",
        }

    def post_run_review_report(self, timeframe: str = "24h", wallet_public_key: str = "") -> dict[str, object]:
        wallet = wallet_public_key.strip() or self.settings.live_active_wallet_public_key or self.settings.live_hot_wallet_public_key
        now = utc_now()
        hours = 24
        if timeframe.endswith("h"):
            try:
                hours = max(1, min(168, int(timeframe[:-1])))
            except ValueError:
                hours = 24
        cutoff = now - timedelta(hours=hours)
        audits = [
            audit
            for audit in self._normalize_live_audits(self.storage.load_live_execution_audits(500))
            if audit.created_at >= cutoff and (not wallet or audit.wallet_public_key == wallet)
            and not (isinstance(audit.quote, dict) and audit.quote.get("shadow_only"))
        ]
        review_statuses = {"failed", "needs_review", "stale", "blocked"}
        unresolved = [audit for audit in audits if self._is_unresolved_live_audit(audit)]
        needs_review = [
            audit
            for audit in audits
            if audit.final_status in review_statuses
            or audit.status in review_statuses
            or bool(audit.errors)
            or audit.reconciliation_status == "needs_review"
        ]
        confirmed = [audit for audit in audits if audit.final_status in {"confirmed", "reconciled"} or audit.status in {"confirmed", "reconciled"}]
        incident_candidates = list({audit.id: audit for audit in [*needs_review, *unresolved]}.values())
        incident_reviews = self._incident_export_review_evidence(incident_candidates)
        pending_incident_candidates = [audit for audit in incident_candidates if not incident_reviews.get(audit.id, {}).get("reviewed")]
        audits_missing_caps_snapshot = len([audit for audit in audits if not isinstance(audit.caps_snapshot, dict) or not audit.caps_snapshot])
        kill_switch_events = [
            event.to_dict()
            for event in self.storage.load_all_events(500)
            if event.created_at >= cutoff and ("kill switch" in event.message.lower() or "kill_switch" in json.dumps(event.context, default=str).lower())
        ][:20]
        cap_and_stop_ready = bool(audits) and audits_missing_caps_snapshot == 0
        checklist = [
            {
                "id": "live_audit_inventory",
                "label": "Live audit inventory",
                "status": "pass" if audits else "empty",
                "value": len(audits),
                "target": "all recent live audits counted",
                "reason": "Every post-run review starts from durable live audit records.",
            },
            {
                "id": "unresolved_recovery",
                "label": "Unresolved recovery",
                "status": "pass" if not unresolved else "fail",
                "value": len(unresolved),
                "target": 0,
                "reason": "Submitted live audits must be confirmed, reconciled, failed, or explicitly moved to needs_review.",
            },
            {
                "id": "incident_exports",
                "label": "Incident exports",
                "status": "pass" if not pending_incident_candidates else "review",
                "value": len(pending_incident_candidates),
                "target": "0 pending or exported for review",
                "reason": "Failed, stale, blocked, or needs-review audits should be exported before ending a pilot session.",
            },
            {
                "id": "ledger_confidence",
                "label": "Ledger confidence",
                "status": "pass" if not self.live_ledger(wallet).get("summary", {}).get("needs_review_positions") else "fail",
                "value": self.live_ledger(wallet).get("summary", {}).get("pnl_confidence", "unknown"),
                "target": "no needs_review positions",
                "reason": "Post-run review should not leave wallet-scoped live PnL in an unresolved state.",
            },
            {
                "id": "cap_and_stop_evidence",
                "label": "Cap and stop evidence",
                "status": "pass" if cap_and_stop_ready else "empty" if not audits else "fail",
                "value": {
                    "audits_missing_caps_snapshot": audits_missing_caps_snapshot,
                    "kill_switch_enabled": self.settings.kill_switch_enabled,
                    "kill_switch_events": len(kill_switch_events),
                },
                "target": "each live audit has caps snapshot and kill-switch state is visible",
                "reason": "Post-run review must show cap decisions and kill-switch state for the pilot window.",
            },
        ]
        action_items: list[str] = []
        if unresolved:
            action_items.append(f"Recover or inspect {len(unresolved)} unresolved submitted audit{'s' if len(unresolved) != 1 else ''}.")
        if pending_incident_candidates:
            action_items.append(f"Export {len(pending_incident_candidates)} live incident bundle{'s' if len(pending_incident_candidates) != 1 else ''} for post-run review.")
        if not audits:
            action_items.append("No live audits were found for this timeframe; run review after a live or shadow-live session.")
        if audits_missing_caps_snapshot:
            action_items.append(f"Review {audits_missing_caps_snapshot} live audit{'s' if audits_missing_caps_snapshot != 1 else ''} without cap-snapshot evidence.")
        ledger_summary = self.live_ledger(wallet).get("summary", {})
        ledger_needs_review = bool(ledger_summary.get("needs_review_positions"))
        ready = bool(audits) and not unresolved and not pending_incident_candidates and not ledger_needs_review and cap_and_stop_ready
        return {
            "artifact_type": "cryptoarc_post_run_review",
            "format_version": 1,
            "generated_at": now.isoformat(),
            "timeframe": timeframe,
            "wallet_public_key": wallet,
            "status": "clear" if ready else "missing_evidence" if not audits else "review_required",
            "ready": ready,
            "summary": {
                "audits": len(audits),
                "confirmed_or_reconciled": len(confirmed),
                "unresolved": len(unresolved),
                "needs_review": len(needs_review),
                "incident_export_candidates": len(incident_candidates),
                "pending_incident_exports": len(pending_incident_candidates),
            },
            "checklist": checklist,
            "run_controls": {
                "kill_switch_enabled": self.settings.kill_switch_enabled,
                "kill_switch_events": kill_switch_events,
                "caps": self.live_caps_snapshot(),
                "audits_missing_caps_snapshot": audits_missing_caps_snapshot,
                "audit_caps_snapshots": [
                    {
                        "audit_id": audit.id,
                        "mint": audit.mint,
                        "action": audit.action,
                        "caps_snapshot": audit.caps_snapshot,
                    }
                    for audit in audits[:50]
                ],
            },
            "incident_exports": [
                {
                    **incident_reviews.get(audit.id, {"reviewed": False, "review_event_id": "", "reviewed_at": None}),
                    "audit_id": audit.id,
                    "mint": audit.mint,
                    "action": audit.action,
                    "status": audit.status,
                    "final_status": audit.final_status,
                    "wallet_public_key": audit.wallet_public_key,
                    "reason": audit.recommended_action or "; ".join(audit.errors or audit.warnings) or "Review live audit evidence.",
                    "export_path": f"/api/live/audit/{audit.id}/incident-export",
                }
                for audit in incident_candidates[:25]
            ],
            "recent_live_audits": [audit.to_dict() for audit in audits[:50]],
            "action_items": list(dict.fromkeys(action_items)),
            "operator_action": "Post-run review is clear." if ready else "Complete the post-run review items before the next real-money pilot.",
            "privacy_note": "Export contains public wallet, live audit, recovery, and ledger-review status only. It must not contain seed phrases or private keys.",
        }

    def record_incident_export_review(
        self,
        audit_id: str,
        exported: bool,
        reviewed: bool,
        note: str = "",
    ) -> dict[str, object]:
        audit = next((item for item in self._normalize_live_audits(self.storage.load_live_execution_audits(1000)) if item.id == audit_id), None)
        if not audit:
            raise ValueError(f"Live audit not found: {audit_id}")
        clean_note = note.strip()[:500]
        recorded_at = utc_now()
        complete = bool(exported and reviewed)
        context: dict[str, object] = {
            "artifact_type": "cryptoarc_incident_export_review",
            "audit_id": audit.id,
            "mint": audit.mint,
            "wallet_public_key": audit.wallet_public_key,
            "exported": bool(exported),
            "reviewed": bool(reviewed),
            "complete": complete,
        }
        if clean_note:
            context["note"] = clean_note
        event = TradeEvent(
            id=new_id("evt"),
            created_at=recorded_at,
            level="info" if complete else "warning",
            message=f"Incident export review recorded for {audit.id}",
            subsystem="live",
            operator_action=clean_note or "Incident export review recorded.",
            context=context,
        )
        self.events.appendleft(event)
        self.storage.save_event(event)
        self.alerts.alert_event(event.level, event.subsystem, event.message, event.operator_action)
        return {
            **context,
            "event_id": event.id,
            "recorded_at": recorded_at.isoformat(),
            "status": "reviewed" if complete else "incomplete",
            "privacy_note": "Incident export review records audit id, public mint/wallet, checklist booleans, and operator notes only. Do not enter seed phrases, private keys, or Telegram tokens.",
        }

    def _incident_export_review_evidence(self, audits: list[LiveExecutionAudit]) -> dict[str, dict[str, object]]:
        audit_ids = {audit.id for audit in audits}
        if not audit_ids:
            return {}
        evidence: dict[str, dict[str, object]] = {}
        for event in self.storage.load_all_events(1000):
            context = event.context if isinstance(event.context, dict) else {}
            if context.get("artifact_type") != "cryptoarc_incident_export_review":
                continue
            audit_id = str(context.get("audit_id") or "")
            if audit_id not in audit_ids or audit_id in evidence:
                continue
            reviewed = bool(context.get("exported")) and bool(context.get("reviewed"))
            evidence[audit_id] = {
                "reviewed": reviewed,
                "exported": bool(context.get("exported")),
                "review_event_id": event.id,
                "reviewed_at": event.created_at.isoformat(),
                "review_note": str(context.get("note") or event.operator_action or ""),
            }
        return evidence

    def outcome_explanations_report(self, timeframe: str = "24h", limit: int = 80) -> dict[str, object]:
        cutoff = self._timeframe_cutoff(timeframe)
        limit = max(1, min(250, int(limit or 80)))
        tokens = self.storage.load_all_tokens(5000)
        tokens_by_id = {token.id: token for token in tokens}
        tokens_by_mint = {token.mint: token for token in tokens if token.mint}
        rows: list[dict[str, object]] = []

        def include(at: datetime | None) -> bool:
            return at is not None and (cutoff is None or at >= cutoff)

        def token_label(token: TokenSignal | None, mint: str = "") -> str:
            if token and token.symbol:
                return token.symbol
            return (mint or (token.mint if token else ""))[:8] or "unknown"

        for decision in self.storage.load_strategy_decisions(2000):
            if not include(decision.created_at):
                continue
            token = tokens_by_id.get(decision.token_id)
            outcome_type = "buy" if decision.allowed or "buy" in decision.action.lower() else "skip"
            reason_parts = [decision.reason]
            if decision.risk_reason and decision.risk_reason != decision.reason:
                reason_parts.append(decision.risk_reason)
            rows.append(
                {
                    "id": f"decision:{decision.id}",
                    "at": decision.created_at.isoformat(),
                    "outcome_type": outcome_type,
                    "status": "allowed" if decision.allowed else "blocked",
                    "subject": token_label(token, decision.mint),
                    "mint": decision.mint,
                    "token_id": decision.token_id,
                    "reason": "; ".join(part for part in reason_parts if part),
                    "recommended_action": "Paper buy is explainable from the strategy decision." if decision.allowed else "Review the risk reason before changing filters.",
                    "evidence": {
                        "decision_id": decision.id,
                        "engine_version": decision.engine_version,
                        "profile": decision.profile,
                        "score": decision.score,
                        "action": decision.action,
                        "settings_version_id": decision.settings_version_id,
                        "score_breakdown": decision.score_breakdown,
                        "decision_log": decision.decision_log,
                    },
                }
            )

        for token in tokens:
            status = token.status.value if isinstance(token.status, TokenStatus) else str(token.status)
            if include(token.opened_at):
                rows.append(
                    {
                        "id": f"token-buy:{token.id}",
                        "at": token.opened_at.isoformat() if token.opened_at else token.detected_at.isoformat(),
                        "outcome_type": "buy",
                        "status": "paper_opened",
                        "subject": token_label(token),
                        "mint": token.mint,
                        "token_id": token.id,
                        "reason": token.entry_reason or token.reason or "Paper position opened.",
                        "recommended_action": "Monitor exit evidence and price confidence.",
                        "evidence": {
                            "token_id": token.id,
                            "status": status,
                            "entry_price": token.entry_price,
                            "amount_sol": token.amount_sol,
                            "strategy_profile": token.entry_strategy_profile,
                            "risk_filters": token.entry_risk_filters,
                        },
                    }
                )
            if include(token.closed_at):
                rows.append(
                    {
                        "id": f"token-sell:{token.id}",
                        "at": token.closed_at.isoformat() if token.closed_at else token.detected_at.isoformat(),
                        "outcome_type": "sell",
                        "status": "paper_closed",
                        "subject": token_label(token),
                        "mint": token.mint,
                        "token_id": token.id,
                        "reason": token.exit_reason or "Paper exit completed.",
                        "recommended_action": "Review PnL and label the trade if it should influence tuning.",
                        "evidence": {
                            "token_id": token.id,
                            "exit_price": token.exit_price,
                            "pnl_sol": token.pnl_sol,
                            "realized_pnl_sol": token.realized_pnl_sol,
                            "hold_duration_seconds": token.hold_duration_seconds,
                            "highest_unrealized_pct": token.highest_unrealized_pct,
                            "lowest_unrealized_pct": token.lowest_unrealized_pct,
                        },
                    }
                )
            if token.status == TokenStatus.SKIPPED and include(token.detected_at):
                rows.append(
                    {
                        "id": f"token-skip:{token.id}",
                        "at": token.detected_at.isoformat(),
                        "outcome_type": "skip",
                        "status": "skipped",
                        "subject": token_label(token),
                        "mint": token.mint,
                        "token_id": token.id,
                        "reason": token.reason or "Token skipped by filters.",
                        "recommended_action": "Inspect score breakdown before relaxing filters.",
                        "evidence": {
                            "token_id": token.id,
                            "score": token.score,
                            "score_breakdown": token.score_breakdown,
                            "decision_log": token.decision_log,
                            "creator": token.creator,
                            "creator_hold_pct": token.creator_hold_pct,
                        },
                    }
                )

        for audit in self._normalize_live_audits(self.storage.load_live_execution_audits(1000)):
            if not include(audit.created_at):
                continue
            token = tokens_by_mint.get(audit.mint)
            blocked = audit.status == "blocked" or audit.final_status == "blocked" or bool(audit.errors)
            recovery = audit.recovery_attempts > 0 or audit.reconciliation_status in {"needs_review", "matched"} or bool(audit.last_recovery_error)
            outcome_type = "block" if blocked else "recovery" if recovery else audit.action
            reason = "; ".join(audit.errors or audit.warnings) or audit.recommended_action or str(audit.quote.get("error") or "") or f"Live {audit.action} audit recorded."
            rows.append(
                {
                    "id": f"live-audit:{audit.id}",
                    "at": audit.created_at.isoformat(),
                    "outcome_type": outcome_type,
                    "status": audit.final_status or audit.status,
                    "subject": token_label(token, audit.mint),
                    "mint": audit.mint,
                    "token_id": token.id if token else "",
                    "reason": reason,
                    "recommended_action": audit.recommended_action or ("Resolve blockers before retrying." if blocked else "Keep audit evidence with the session report."),
                    "evidence": {
                        "audit_id": audit.id,
                        "intent_id": audit.intent_id,
                        "action": audit.action,
                        "signer_mode": audit.signer_mode,
                        "wallet_public_key": audit.wallet_public_key,
                        "transaction_signature": audit.transaction_signature,
                        "reconciliation_status": audit.reconciliation_status,
                        "recovery_attempts": audit.recovery_attempts,
                        "quote_status": audit.quote.get("status") if isinstance(audit.quote, dict) else "",
                    },
                }
            )

        for request in self.storage.load_live_execution_requests(500):
            if not include(request.created_at):
                continue
            rows.append(
                {
                    "id": f"manual-request:{request.id}",
                    "at": request.created_at.isoformat(),
                    "outcome_type": "block" if request.status == "blocked" else "override",
                    "status": request.status,
                    "subject": request.mint[:8] or "manual",
                    "mint": request.mint,
                    "token_id": "",
                    "reason": request.reason,
                    "recommended_action": "Manual live request is audit-only until live execution gates are satisfied.",
                    "evidence": {
                        "request_id": request.id,
                        "action": request.action,
                        "amount_sol": request.amount_sol,
                        "mode": request.mode,
                        "reviewed_at": request.reviewed_at.isoformat() if request.reviewed_at else None,
                    },
                }
            )

        for event in self.storage.load_all_events(1000):
            if not include(event.created_at):
                continue
            payload: dict[str, object] = {}
            if event.operator_action:
                try:
                    decoded = json.loads(event.operator_action)
                    if isinstance(decoded, dict):
                        payload = decoded
                except json.JSONDecodeError:
                    payload = {}
            is_override = "override" in event.message.lower() or payload.get("effect") == "audit_only_no_gate_bypass"
            is_recovery = event.subsystem == "live" and "recover" in event.message.lower()
            if not is_override and not is_recovery:
                continue
            rows.append(
                {
                    "id": f"event:{event.id}",
                    "at": event.created_at.isoformat(),
                    "outcome_type": "override" if is_override else "recovery",
                    "status": event.level,
                    "subject": str(payload.get("target_gate") or event.subsystem),
                    "mint": "",
                    "token_id": event.token_id or "",
                    "reason": str(payload.get("reason") or event.message),
                    "recommended_action": "Override is audit-only and does not bypass blockers." if payload else event.operator_action,
                    "evidence": {
                        "event_id": event.id,
                        "subsystem": event.subsystem,
                        "session_id": event.session_id,
                        "payload": payload,
                    },
                }
            )

        deduped = {str(row["id"]): row for row in rows}
        ordered = sorted(deduped.values(), key=lambda row: str(row["at"]), reverse=True)[:limit]
        type_counts = Counter(str(row["outcome_type"]) for row in ordered)
        status_counts = Counter(str(row["status"]) for row in ordered)
        action_items: list[str] = []
        if not ordered:
            action_items.append("No recent explainable outcomes found for this timeframe; collect paper, shadow, or live evidence.")
        if type_counts.get("block", 0):
            action_items.append("Review blocked outcomes before changing live or strategy settings.")
        if type_counts.get("recovery", 0):
            action_items.append("Export recovery or incident evidence before the next real-money pilot.")
        return {
            "artifact_type": "cryptoarc_outcome_explanations",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "timeframe": timeframe,
            "limit": limit,
            "summary": {
                "total": len(ordered),
                "by_type": dict(type_counts),
                "by_status": dict(status_counts),
            },
            "outcomes": ordered,
            "action_items": action_items,
            "operator_action": "Use this report to answer why the bot bought, skipped, sold, blocked, overrode, or recovered before changing settings.",
            "privacy_note": "Report contains local decision, audit, and public wallet evidence only. It must not contain seed phrases, private keys, or Telegram tokens.",
        }

    def setup_readiness_report(self, env_live_enabled: bool = False, local_auth_enabled: bool = False) -> dict[str, object]:
        source = self.source_health()
        summary = self.data_summary()
        schema = self.storage.schema_status()
        backup = self.storage.backup_restore_status()
        mode = self.settings.mode.value if hasattr(self.settings.mode, "value") else str(self.settings.mode)
        source_name = self.settings.launch_source.strip() or "unknown"
        source_known = source_name in {"pumpportal", "mock"}
        paper_trade_ready = self.settings.trade_size_sol > 0 and self.settings.max_open_positions > 0
        gates = [
            self._setup_gate(
                "mode",
                "Paper mode",
                mode,
                "paper or preview",
                "pass" if mode in {"paper", "preview"} else "fail",
                "Set the bot to paper or preview before first-run monitoring.",
            ),
            self._setup_gate(
                "source_selection",
                "Launch source",
                source_name,
                "pumpportal or mock",
                "pass" if source_known else "fail",
                "Choose a supported launch source before starting the source loop.",
            ),
            self._setup_gate(
                "source_detection",
                "Source detection",
                bool(self.settings.detect_new_tokens),
                True,
                "pass" if self.settings.detect_new_tokens else "fail",
                "Enable new-token detection to start paper monitoring.",
            ),
            self._setup_gate(
                "schema",
                "Local database",
                f"{schema.get('current_version', 0)}/{schema.get('expected_version', 0)}",
                "current schema",
                "pass" if schema.get("current_version") == schema.get("expected_version") else "fail",
                "Run migrations or bootstrap before relying on local state.",
            ),
            self._setup_gate(
                "paper_settings",
                "Paper settings",
                f"{self.settings.trade_size_sol} SOL / {self.settings.max_open_positions} max open",
                "trade size > 0 and max open > 0",
                "pass" if paper_trade_ready else "fail",
                "Set a positive paper trade size and at least one max open position.",
            ),
            self._setup_gate(
                "source_health",
                "Source health",
                source.get("trust_state", "unknown"),
                "not conflicting",
                "fail" if source.get("trust_state") == "conflicting" else ("warn" if source.get("trust_state") in {"unknown", "stale", "degraded"} else "pass"),
                "Inspect source health if trust is unknown, stale, degraded, or conflicting.",
            ),
            self._setup_gate(
                "auth",
                "Local auth",
                bool(local_auth_enabled),
                True,
                "pass" if local_auth_enabled else "warn",
                "Enable local auth before live work; paper monitoring can start without it on a trusted workstation.",
            ),
            self._setup_gate(
                "backup",
                "Backup artifact",
                "present" if backup.get("latest_backup") else "missing",
                "present",
                "pass" if backup.get("latest_backup") else "warn",
                "Create a backup artifact before upgrades, restore testing, or any live phase.",
            ),
            self._setup_gate(
                "live_disabled",
                "Live disabled",
                not (env_live_enabled or self.settings.live_trading_enabled or self.settings.autonomous_live_enabled),
                True,
                "pass" if not (env_live_enabled or self.settings.live_trading_enabled or self.settings.autonomous_live_enabled) else "warn",
                "Keep live execution disabled during first-run paper setup unless you are intentionally reviewing live gates.",
            ),
        ]
        blockers = [str(gate["reason"]) for gate in gates if gate["status"] == "fail"]
        warnings = [str(gate["reason"]) for gate in gates if gate["status"] == "warn"]
        ready_for_paper = not blockers
        return {
            "artifact_type": "cryptoarc_setup_readiness",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "status": "ready" if ready_for_paper and not warnings else ("review" if ready_for_paper else "blocked"),
            "ready_for_paper": ready_for_paper,
            "gates": gates,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "operator_action": "Start paper monitoring, then collect source and paper evidence." if ready_for_paper else "Resolve setup blockers before starting paper monitoring.",
            "next_steps": self._setup_next_steps(gates, ready_for_paper),
            "evidence": {
                "bot": {"status": self.status.value, "mode": mode},
                "source": source,
                "storage": summary,
                "schema": schema,
                "backup_restore": backup,
                "live_requested": bool(self.settings.live_trading_enabled or self.settings.autonomous_live_enabled),
                "env_live_enabled": bool(env_live_enabled),
                "local_auth_enabled": bool(local_auth_enabled),
            },
            "privacy_note": "Setup readiness contains local status, source, schema, backup, and settings evidence only. It must not contain seed phrases, private keys, or Telegram tokens.",
        }

    def _setup_gate(self, gate_id: str, label: str, value: object, target: object, status: str, reason: str) -> dict[str, object]:
        return {
            "id": gate_id,
            "label": label,
            "status": status,
            "value": value,
            "target": target,
            "reason": reason,
        }

    def _setup_next_steps(self, gates: list[dict[str, object]], ready_for_paper: bool) -> list[str]:
        actions: list[str] = []
        for gate in gates:
            if gate["status"] == "pass":
                continue
            gate_id = gate["id"]
            if gate_id == "mode":
                actions.append("Switch mode to paper or preview.")
            elif gate_id == "source_selection":
                actions.append("Select PumpPortal for real launches or mock for local practice.")
            elif gate_id == "source_detection":
                actions.append("Enable new-token detection before starting the source.")
            elif gate_id == "schema":
                actions.append("Run the bootstrap or verify script to bring migrations current.")
            elif gate_id == "paper_settings":
                actions.append("Set a positive paper trade size and max-open-position limit.")
            elif gate_id == "source_health":
                actions.append("Start the source and inspect raw events until source trust improves.")
            elif gate_id == "auth":
                actions.append("Configure local auth before live trading or shared workstation use.")
            elif gate_id == "backup":
                actions.append("Create a backup artifact from the Data workspace.")
            elif gate_id == "live_disabled":
                actions.append("Keep live mode disabled while completing first-run paper setup.")
        if ready_for_paper:
            actions.append("Start paper monitoring and collect enough source events for readiness scoring.")
        return list(dict.fromkeys(actions))

    def release_readiness_report(
        self,
        app_version: str = "0.1.0",
        env_live_enabled: bool = False,
        local_auth_enabled: bool = False,
    ) -> dict[str, object]:
        repo_root = Path(__file__).resolve().parents[3]
        docs_dir = repo_root / "docs"
        changelog_path = docs_dir / "CHANGELOG.md"
        checklist_path = docs_dir / "RELEASE_CHECKLIST.md"
        verify_path = repo_root / "scripts" / "verify.ps1"
        bootstrap_path = repo_root / "scripts" / "bootstrap.ps1"
        doctor_path = repo_root / "scripts" / "doctor.ps1"
        audit_frontend_path = repo_root / "scripts" / "audit-frontend.ps1"
        package_path = repo_root / "frontend" / "package.json"
        frontend_version = self._frontend_package_version(package_path)
        dependency_audit = self._frontend_dependency_audit_policy(repo_root, audit_frontend_path)
        release_verification = self._release_verification_evidence(app_version)
        schema = self.storage.schema_status()
        backup = self.storage.backup_restore_status()
        source = self.source_health()
        unresolved = [
            audit
            for audit in self._normalize_live_audits(self.storage.load_live_execution_audits(500))
            if self._is_unresolved_live_audit(audit)
        ]
        live_requested = bool(env_live_enabled or self.settings.live_trading_enabled or self.settings.autonomous_live_enabled)
        version_match = bool(frontend_version) and frontend_version == app_version
        gates = [
            self._setup_gate("changelog", "Versioned changelog", changelog_path.exists(), True, "pass" if changelog_path.exists() else "fail", "Create docs/CHANGELOG.md before tagging or handing off a release."),
            self._setup_gate("release_checklist", "Release checklist", checklist_path.exists(), True, "pass" if checklist_path.exists() else "fail", "Keep docs/RELEASE_CHECKLIST.md available for local release and live-safety gates."),
            self._setup_gate("verify_script", "Verify script", verify_path.exists(), True, "pass" if verify_path.exists() else "fail", "Use scripts/verify.ps1 as the canonical local release check."),
            self._setup_gate("bootstrap_script", "Bootstrap script", bootstrap_path.exists(), True, "pass" if bootstrap_path.exists() else "fail", "Use scripts/bootstrap.ps1 for reproducible local setup."),
            self._setup_gate("doctor_script", "Setup diagnostics", doctor_path.exists(), True, "pass" if doctor_path.exists() else "fail", "Use scripts/doctor.ps1 to diagnose Python, Node, dependency, and Solana package readiness."),
            self._setup_gate("frontend_audit", "Frontend audit policy", dependency_audit["status"], "ready or acknowledged review", "fail" if dependency_audit["status"] == "blocked" else ("warn" if dependency_audit["status"] == "review" else "pass"), str(dependency_audit["operator_action"])),
            self._setup_gate("schema", "Local database", f"{schema.get('current_version', 0)}/{schema.get('expected_version', 0)}", "current schema", "pass" if schema.get("current_version") == schema.get("expected_version") else "fail", "Run migrations or bootstrap before preparing a release."),
            self._setup_gate("frontend_version", "Frontend version", frontend_version or "missing", app_version, "pass" if version_match else "warn", "Align frontend/package.json with the API release version before tagging."),
            self._setup_gate("backup", "Backup artifact", "present" if backup.get("latest_backup") else "missing", "present", "pass" if backup.get("latest_backup") else "warn", "Create a backup artifact before live testing or handoff."),
            self._setup_gate("source_trust", "Source trust", source.get("trust_state", "unknown"), "not conflicting", "fail" if source.get("trust_state") == "conflicting" else ("warn" if source.get("trust_state") in {"unknown", "stale", "degraded"} else "pass"), "Inspect source health if trust is unknown, stale, degraded, or conflicting."),
            self._setup_gate("live_disabled", "Live disabled", not live_requested, True, "pass" if not live_requested else "fail", "Keep live execution disabled unless this release is an intentional local live-test build."),
            self._setup_gate("recovery_debt", "Recovery debt", len(unresolved), 0, "pass" if not unresolved else "fail", "Recover, review, or export unresolved live audits before releasing."),
            self._setup_gate("local_auth", "Local auth", bool(local_auth_enabled), True, "pass" if local_auth_enabled else "warn", "Enable local auth before live operation or shared-workstation handoff."),
            self._setup_gate("manual_verification", "Manual verification", release_verification["status"], "recent scripts/verify.ps1 pass + git diff review", "pass" if release_verification["verified"] else "warn", str(release_verification["operator_action"])),
        ]
        blockers = [str(gate["reason"]) for gate in gates if gate["status"] == "fail"]
        warnings = [str(gate["reason"]) for gate in gates if gate["status"] == "warn"]
        status = "blocked" if blockers else ("review" if warnings else "ready")
        return {
            "artifact_type": "cryptoarc_release_readiness",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "app_version": app_version,
            "frontend_version": frontend_version,
            "status": status,
            "ready": status == "ready",
            "gates": gates,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_steps": self._release_next_steps(gates, status),
            "operator_action": "Release readiness is clear after recording the verifier result." if status == "ready" else "Resolve release blockers and warnings before tagging, live testing, or handoff.",
            "evidence": {
                "docs": {
                    "changelog": str(changelog_path.relative_to(repo_root)),
                    "release_checklist": str(checklist_path.relative_to(repo_root)),
                    "changelog_present": changelog_path.exists(),
                    "release_checklist_present": checklist_path.exists(),
                },
                "scripts": {
                    "bootstrap": str(bootstrap_path.relative_to(repo_root)),
                    "verify": str(verify_path.relative_to(repo_root)),
                    "doctor": str(doctor_path.relative_to(repo_root)),
                    "frontend_audit": str(audit_frontend_path.relative_to(repo_root)),
                    "bootstrap_present": bootstrap_path.exists(),
                    "verify_present": verify_path.exists(),
                    "doctor_present": doctor_path.exists(),
                    "frontend_audit_present": audit_frontend_path.exists(),
                },
                "dependency_audit": dependency_audit,
                "schema": schema,
                "backup_restore": backup,
                "source": source,
                "live_requested": live_requested,
                "env_live_enabled": bool(env_live_enabled),
                "local_auth_enabled": bool(local_auth_enabled),
                "unresolved_audits": [audit.to_dict() for audit in unresolved[:25]],
                "release_verification": release_verification,
            },
            "privacy_note": "Release readiness contains local docs, script, schema, backup, source, and public live-audit evidence only. It must not contain seed phrases, private keys, or Telegram tokens.",
        }

    def record_release_verification(
        self,
        app_version: str,
        verify_passed: bool,
        diff_reviewed: bool,
        docs_reviewed: bool,
        note: str = "",
    ) -> dict[str, object]:
        clean_version = (app_version or "0.1.0").strip()
        clean_note = note.strip()[:500]
        verified = bool(verify_passed and diff_reviewed and docs_reviewed)
        recorded_at = utc_now()
        context: dict[str, object] = {
            "artifact_type": "cryptoarc_release_verification",
            "app_version": clean_version,
            "verify_passed": bool(verify_passed),
            "diff_reviewed": bool(diff_reviewed),
            "docs_reviewed": bool(docs_reviewed),
            "verified": verified,
        }
        if clean_note:
            context["note"] = clean_note
        event = TradeEvent(
            id=new_id("evt"),
            created_at=recorded_at,
            level="info" if verified else "warning",
            message=f"Release verification recorded for {clean_version}",
            subsystem="release",
            operator_action=clean_note or "Local verifier attestation recorded.",
            context=context,
        )
        self.events.appendleft(event)
        self.storage.save_event(event)
        self.alerts.alert_event(event.level, event.subsystem, event.message, event.operator_action)
        return {
            **context,
            "event_id": event.id,
            "recorded_at": recorded_at.isoformat(),
            "status": "verified" if verified else "incomplete",
            "privacy_note": "Release verification records local checklist booleans and operator notes only. Do not enter seed phrases, private keys, or Telegram tokens.",
        }

    def _release_verification_evidence(self, app_version: str) -> dict[str, object]:
        window_hours = 24.0
        events = [
            event
            for event in self.storage.load_all_events(500)
            if event.subsystem == "release" and isinstance(event.context, dict) and event.context.get("artifact_type") == "cryptoarc_release_verification"
        ]
        for event in events:
            context = event.context
            age_hours = round(max(0.0, (utc_now() - event.created_at).total_seconds() / 3600), 2)
            same_version = str(context.get("app_version") or "") == app_version
            checks_passed = bool(context.get("verify_passed")) and bool(context.get("diff_reviewed")) and bool(context.get("docs_reviewed"))
            recent = age_hours <= window_hours
            if same_version and checks_passed and recent:
                return {
                    "status": "verified",
                    "verified": True,
                    "event_id": event.id,
                    "recorded_at": event.created_at.isoformat(),
                    "age_hours": age_hours,
                    "window_hours": window_hours,
                    "app_version": app_version,
                    "verify_passed": True,
                    "diff_reviewed": True,
                    "docs_reviewed": True,
                    "operator_action": "Recent local verification attestation is recorded for this app version.",
                }
        latest = events[0] if events else None
        if latest:
            context = latest.context
            latest_age_hours = round(max(0.0, (utc_now() - latest.created_at).total_seconds() / 3600), 2)
            status = "stale" if latest_age_hours > window_hours else "incomplete"
            if str(context.get("app_version") or "") != app_version:
                status = "version_mismatch"
            return {
                "status": status,
                "verified": False,
                "event_id": latest.id,
                "recorded_at": latest.created_at.isoformat(),
                "age_hours": latest_age_hours,
                "window_hours": window_hours,
                "app_version": str(context.get("app_version") or ""),
                "verify_passed": bool(context.get("verify_passed")),
                "diff_reviewed": bool(context.get("diff_reviewed")),
                "docs_reviewed": bool(context.get("docs_reviewed")),
                "operator_action": "Run scripts/verify.ps1, review git diff and release docs, then record a fresh verifier attestation for this app version.",
            }
        return {
            "status": "missing",
            "verified": False,
            "event_id": "",
            "recorded_at": None,
            "age_hours": None,
            "window_hours": window_hours,
            "app_version": app_version,
            "verify_passed": False,
            "diff_reviewed": False,
            "docs_reviewed": False,
            "operator_action": "Run scripts/verify.ps1, review git diff and release docs, then record a verifier attestation before tagging or handoff.",
        }

    def _frontend_package_version(self, package_path: Path) -> str:
        try:
            payload = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        return str(payload.get("version") or "")

    def _frontend_dependency_audit_policy(self, repo_root: Path, audit_script_path: Path) -> dict[str, object]:
        package_lock = repo_root / "frontend" / "package-lock.json"
        package_lock_present = package_lock.exists()
        try:
            package_lock_payload = json.loads(package_lock.read_text(encoding="utf-8"))
            package_lock_valid = isinstance(package_lock_payload, dict) and isinstance(package_lock_payload.get("packages"), dict)
        except (OSError, json.JSONDecodeError):
            package_lock_payload = {}
            package_lock_valid = False
        solana_version = self._package_lock_dependency_version(package_lock, "node_modules/@solana/web3.js")
        jayson_version = self._package_lock_dependency_version(package_lock, "node_modules/jayson")
        uuid_version = self._package_lock_dependency_version(package_lock, "node_modules/uuid")
        script_present = audit_script_path.exists()
        semver_pattern = r"(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
        required_versions = (solana_version, jayson_version, uuid_version)
        required_versions_present = all(required_versions)
        required_versions_valid = required_versions_present and all(re.fullmatch(semver_pattern, version) for version in required_versions)
        package_entries = package_lock_payload.get("packages", {}) if package_lock_valid else {}
        uuid_package_entries = [
            item
            for dependency_path, item in package_entries.items()
            if re.search(r"(?:^|/)node_modules/uuid$", str(dependency_path))
        ]
        uuid_versions = [
            str(item.get("version") or "") if isinstance(item, dict) else ""
            for item in uuid_package_entries
        ]
        uuid_versions_valid = bool(uuid_package_entries) and all(
            isinstance(item, dict)
            and bool(item.get("version"))
            and re.fullmatch(semver_pattern, str(item.get("version")))
            for item in uuid_package_entries
        )
        uuid_advisory_present = False
        for installed_uuid_version in uuid_versions:
            uuid_match = re.fullmatch(semver_pattern, installed_uuid_version)
            uuid_semver = tuple(int(part) for part in uuid_match.groups()[:3]) if uuid_match else ()
            uuid_prerelease = bool(uuid_match and uuid_match.group(4))
            if uuid_semver and (
                uuid_semver < (11, 1, 1)
                or (12, 0, 0) <= uuid_semver < (12, 0, 1)
                or (13, 0, 0) <= uuid_semver < (13, 0, 1)
                or (uuid_prerelease and uuid_semver in {(11, 1, 1), (12, 0, 1), (13, 0, 1)})
            ):
                uuid_advisory_present = True
                break
        known_chain_present = bool(solana_version and jayson_version and uuid_advisory_present)
        status = "ready"
        blockers: list[str] = []
        warnings: list[str] = []
        if not script_present:
            blockers.append("scripts/audit-frontend.ps1 is missing.")
        if not package_lock_present:
            blockers.append("frontend/package-lock.json is missing.")
        elif not package_lock_valid:
            blockers.append("frontend/package-lock.json is invalid.")
        elif not required_versions_present:
            blockers.append("frontend/package-lock.json is missing required dependency metadata.")
        elif not required_versions_valid:
            blockers.append("frontend/package-lock.json does not contain valid semantic versions for required dependencies.")
        elif not uuid_versions_valid:
            blockers.append("frontend/package-lock.json contains invalid semantic version metadata for an installed uuid package.")
        if blockers:
            status = "blocked"
        elif known_chain_present:
            status = "review"
            warnings.append("Known moderate @solana/web3.js -> jayson -> uuid advisory remains acknowledged; npm's available fix downgrades @solana/web3.js to 0.0.3.")
        if status == "ready":
            operator_action = "Frontend audit policy is present; run scripts/audit-frontend.ps1 -Strict before release."
        elif status == "review":
            operator_action = "Run scripts/audit-frontend.ps1 -Strict and review the recognized advisory before release."
        else:
            actions: list[str] = []
            if not script_present:
                actions.append("Restore scripts/audit-frontend.ps1.")
            if not package_lock_present:
                actions.append("Restore frontend/package-lock.json.")
            elif not package_lock_valid:
                actions.append("Regenerate a valid frontend/package-lock.json.")
            elif not required_versions_present:
                actions.append("Regenerate frontend/package-lock.json with the required dependency metadata.")
            elif not required_versions_valid:
                actions.append("Regenerate frontend/package-lock.json with valid semantic versions.")
            elif not uuid_versions_valid:
                actions.append("Regenerate frontend/package-lock.json with valid installed uuid versions.")
            actions.append("Then run scripts/audit-frontend.ps1 -Strict.")
            operator_action = " ".join(actions)
        return {
            "status": status,
            "script": str(audit_script_path.relative_to(repo_root)),
            "script_present": script_present,
            "package_lock_present": package_lock_present,
            "package_lock_valid": package_lock_valid,
            "known_chain_present": known_chain_present,
            "packages": {
                "@solana/web3.js": solana_version,
                "jayson": jayson_version,
                "uuid": uuid_version,
                "uuid_versions": uuid_versions,
                "uuid_versions_valid": uuid_versions_valid,
            },
            "acknowledged_exception": "moderate @solana/web3.js -> jayson -> uuid advisory; do not apply npm's breaking @solana/web3.js@0.0.3 audit fix without a compatibility plan" if known_chain_present else None,
            "blockers": blockers,
            "warnings": warnings,
            "operator_action": operator_action,
        }

    def _package_lock_dependency_version(self, package_lock_path: Path, dependency_path: str) -> str:
        try:
            payload = json.loads(package_lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        packages = payload.get("packages", {})
        if not isinstance(packages, dict):
            return ""
        item = packages.get(dependency_path, {})
        if not isinstance(item, dict):
            return ""
        return str(item.get("version") or "")

    def _release_next_steps(self, gates: list[dict[str, object]], status: str) -> list[str]:
        actions: list[str] = []
        for gate in gates:
            if gate["status"] == "pass":
                continue
            gate_id = gate["id"]
            if gate_id == "changelog":
                actions.append("Add or update docs/CHANGELOG.md with the pending release notes.")
            elif gate_id == "release_checklist":
                actions.append("Restore docs/RELEASE_CHECKLIST.md and review every required local gate.")
            elif gate_id in {"verify_script", "bootstrap_script", "doctor_script"}:
                actions.append("Restore the local setup and verification scripts before handoff.")
            elif gate_id == "frontend_audit":
                actions.append("Run scripts/audit-frontend.ps1 -Strict and resolve reported blockers or review items before release.")
            elif gate_id == "schema":
                actions.append("Run bootstrap or startup migrations until schema status is current.")
            elif gate_id == "frontend_version":
                actions.append("Align frontend/package.json version with the API release version.")
            elif gate_id == "backup":
                actions.append("Create a backup artifact and run the restore smoke test before live work.")
            elif gate_id == "source_trust":
                actions.append("Collect source evidence and inspect source health before release promotion.")
            elif gate_id == "live_disabled":
                actions.append("Disable live execution for normal release prep or document the intentional live-test scope.")
            elif gate_id == "recovery_debt":
                actions.append("Recover or export unresolved live audits before the next tagged release.")
            elif gate_id == "local_auth":
                actions.append("Enable local auth before shared workstation use or real-money operation.")
            elif gate_id == "manual_verification":
                actions.append("Run scripts/verify.ps1, review git diff, and record the result in release notes.")
        if status != "blocked":
            actions.append("Update the changelog date and tag only after local verification passes.")
        return list(dict.fromkeys(actions))

    def pilot_readiness_report(
        self,
        env_live_enabled: bool = False,
        wallet_public_key: str = "",
        signer_mode: str | None = None,
        local_auth_enabled: bool = False,
    ) -> dict[str, object]:
        signer_mode = signer_mode or self.settings.live_signer_mode
        wallet = self._resolve_backend_wallet(signer_mode, wallet_public_key)
        source = self.source_health()
        source_soak = self.source_soak_acceptance_report()
        readiness = self.readiness_status()
        strategy = readiness.get("strategy_promotion") if isinstance(readiness, dict) else {}
        execution = readiness.get("execution_readiness") if isinstance(readiness, dict) else {}
        live = self.live_status(env_live_enabled, wallet, signer_mode, local_auth_enabled)
        ledger = self.live_ledger(wallet)
        backup = self.storage.backup_restore_status()
        pre_run_backup = self._pre_run_backup_status()
        caps = self.live_caps_snapshot()
        unresolved_count = int(live.get("unresolved_audit_count", 0) or 0)
        policy_blockers = self._execution_policy_blockers()
        source_soak_required = bool(source_soak.get("hard_required"))
        source_soak_ready = bool(source_soak.get("ready"))
        source_soak_history = source_soak.get("history_summary", {}) if isinstance(source_soak.get("history_summary"), dict) else {}
        source_soak_history_ready = (not source_soak_required) or bool(source_soak_history.get("latest_ready_recent"))
        source_live_blocker = self._source_live_entry_blocker(source)
        source_archive_blocker = self._source_archive_blocker(source)
        source_ready_for_live = not bool(source_live_blocker or source_archive_blocker)
        ledger_summary = ledger.get("summary", {}) if isinstance(ledger.get("summary"), dict) else {}
        execution_metrics = execution.get("metrics", {}) if isinstance(execution, dict) and isinstance(execution.get("metrics"), dict) else {}
        recent_shadow_evaluated = int(execution_metrics.get("recent_shadow_evaluated", 0) or 0)
        recent_shadow_pnl = float(execution_metrics.get("recent_shadow_estimated_pnl_sol", 0.0) or 0.0)
        execution_blockers = [str(item) for item in execution.get("blockers", []) if item] if isinstance(execution, dict) else []
        execution_shadow_reason = "Dry-run quote and shadow evidence must be ready."
        for blocker in execution_blockers:
            if "PumpPortal trade subscriptions require a funded API key" in blocker:
                execution_shadow_reason = blocker
                break
        manual_live = live.get("manual_live_verification", {}) if isinstance(live.get("manual_live_verification"), dict) else {}
        gates = [
            self._promotion_gate("env_live_enabled", "Live env", bool(live.get("env_live_enabled")), True, bool(live.get("env_live_enabled")), "LIVE_TRADING_ENABLED must be explicitly enabled for a real-money pilot."),
            self._promotion_gate("local_auth", "Local auth", bool(local_auth_enabled), True, bool(local_auth_enabled), "Configure a dashboard password/local auth before starting a real-money pilot."),
            self._promotion_gate("session_acknowledged", "Session acknowledgement", bool(live.get("session_acknowledged")), True, bool(live.get("session_acknowledged")), "Operator must acknowledge the live session risk state."),
            self._promotion_gate("source_trust", "Source trust", f"{source.get('status', 'unknown')}/{source.get('trust_state', 'unknown')}", "connected, recent, trusted, archived", source_ready_for_live, source_live_blocker or source_archive_blocker or "PumpPortal source must be connected, recent, trusted, and archived before live entries."),
            self._promotion_gate("source_soak", "Hybrid source soak", source_soak.get("status", "unknown"), "ready when direct verifier is configured", (not source_soak_required) or source_soak_ready, "Hybrid direct/PumpPortal source-soak gate must pass before a real-money pilot when direct verification is configured or direct events exist."),
            self._promotion_gate("source_soak_history", "Source-soak history", source_soak_history.get("latest_ready_age_hours"), "<= 24h ready snapshot when direct soak is required", source_soak_history_ready, "Record a ready source-soak snapshot from a meaningful direct/PumpPortal soak window within 24 hours before a real-money pilot."),
            self._promotion_gate("strategy_promotion", "Strategy promotion", strategy.get("status", "unknown") if isinstance(strategy, dict) else "unknown", "eligible", bool(strategy.get("can_promote")) if isinstance(strategy, dict) else False, "Paper strategy must pass sample, replay, drawdown, and profitability gates."),
            self._promotion_gate("execution_shadow", "Shadow execution", execution.get("status", "unknown") if isinstance(execution, dict) else "unknown", "shadow_ready", bool(execution.get("can_shadow")) if isinstance(execution, dict) else False, execution_shadow_reason),
            self._promotion_gate("shadow_samples", "Shadow samples", recent_shadow_evaluated, ">= 5 evaluated in 24h", recent_shadow_evaluated >= 5, "Pilot requires at least five evaluated shadow comparisons from the last 24 hours to avoid guessing from stale evidence."),
            self._promotion_gate("shadow_pnl", "Shadow PnL", round(recent_shadow_pnl, 6), ">= 0 SOL in 24h", recent_shadow_pnl >= 0 and recent_shadow_evaluated > 0, "Recent shadow evidence from the last 24 hours should not be net negative."),
            self._promotion_gate("policy_caps", "Policy caps", "configured" if not policy_blockers else "blocked", "tiny capped", not policy_blockers, "Trade, loss, exposure, slippage, priority-fee, and position caps must be configured conservatively."),
            self._promotion_gate("signer_health", "Signer health", live.get("signer", {}).get("status", "unknown") if isinstance(live.get("signer"), dict) else "unknown", "connected", not bool(live.get("signer", {}).get("disabled_reason")) if isinstance(live.get("signer"), dict) else False, "The selected signer must be connected and healthy."),
            self._promotion_gate("manual_live_proof", "Manual-live wallet proof", bool(manual_live.get("verified")), True, bool(manual_live.get("verified")), str(manual_live.get("blocker") or "Selected wallet needs a confirmed and reconciled manual-live proof from the last 24 hours.")),
            self._promotion_gate("autonomy_entry", "Entry autonomy", bool(live.get("auto_buy_available")), True, bool(live.get("auto_buy_available")), "Capped pilot entries require clear autonomy gates on the armed backend."),
            self._promotion_gate("autonomy_exit", "Exit autonomy", bool(live.get("auto_sell_available")), True, bool(live.get("auto_sell_available")), "Protective exits must be available before automated buys."),
            self._promotion_gate("recovery_debt", "Recovery debt", unresolved_count, 0, unresolved_count == 0, "Unresolved live audits must be recovered or reviewed before a pilot."),
            self._promotion_gate("ledger_confidence", "Ledger confidence", ledger_summary.get("pnl_confidence", "unknown"), "no needs_review/stale", not ledger_summary.get("needs_review_positions") and not ledger_summary.get("stale_balance_positions"), "Ledger positions must not have stale balance evidence or needs-review reconciliation."),
            self._promotion_gate("backup", "Pre-run backup", pre_run_backup.get("state", "missing"), "fresh", bool(pre_run_backup.get("fresh")), str(pre_run_backup.get("operator_action") or "Create a fresh local backup artifact before the first pilot session.")),
            self._promotion_gate("kill_switch", "Kill switch", bool(self.settings.kill_switch_enabled), False, not self.settings.kill_switch_enabled, "Kill switch must be clear before starting a pilot."),
        ]
        blockers = [str(gate["reason"]) for gate in gates if gate["status"] != "pass"]
        blockers.extend(str(item) for item in live.get("autonomy_blockers", []) if item)
        blockers.extend(policy_blockers)
        blockers = list(dict.fromkeys(blockers))
        runbook_checklist = self._pilot_runbook_checklist(gates, live)
        return {
            "artifact_type": "cryptoarc_tiny_pilot_readiness",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "wallet_public_key": wallet,
            "signer_mode": signer_mode,
            "status": "ready" if not blockers else "blocked",
            "ready": not blockers,
            "stage": "tiny_real_money_pilot",
            "gates": gates,
            "blockers": blockers,
            "runbook_checklist": runbook_checklist,
            "operator_action": "Pilot gate is clear for tiny capped real-money execution." if not blockers else "Resolve every blocker before starting a real-money pilot.",
            "evidence": {
                "source": source,
                "source_soak": source_soak,
                "readiness": {
                    "status": readiness.get("status") if isinstance(readiness, dict) else "unknown",
                    "score": readiness.get("score") if isinstance(readiness, dict) else 0,
                    "strategy_promotion": strategy,
                    "execution_readiness": execution,
                },
                "live_status": live,
                "live_ledger": ledger,
                "backup_restore": backup,
                "pre_run_backup": pre_run_backup,
                "caps": caps,
            },
            "privacy_note": "Export contains public wallet, source/readiness, ledger, cap, signer, and backup status evidence only. It must not contain seed phrases or private keys.",
        }

    def _pilot_runbook_checklist(self, gates: list[dict[str, object]], live: dict[str, object]) -> list[dict[str, object]]:
        gate_by_id = {str(gate.get("id")): gate for gate in gates}

        def blockers_for(gate_ids: list[str]) -> list[str]:
            return [
                str(gate.get("reason") or gate.get("label") or gate_id)
                for gate_id in gate_ids
                for gate in [gate_by_id.get(gate_id)]
                if gate and gate.get("status") != "pass"
            ]

        def stage(id_: str, label: str, gate_ids: list[str], actions: list[dict[str, str]], ready_action: str) -> dict[str, object]:
            blockers = blockers_for(gate_ids)
            return {
                "id": id_,
                "label": label,
                "status": "ready" if not blockers else "blocked",
                "blockers": blockers,
                "actions": actions,
                "operator_action": ready_action if not blockers else "Resolve this stage's blockers before continuing.",
            }

        full_sniper_gate = live.get("full_sniper_gate", {}) if isinstance(live.get("full_sniper_gate"), dict) else {}
        run_blockers = blockers_for(["autonomy_entry", "autonomy_exit", "kill_switch"])
        run_blockers.extend(str(item) for item in full_sniper_gate.get("blockers", []) if item)
        run_blockers = list(dict.fromkeys(run_blockers))
        recover_blockers = blockers_for(["recovery_debt", "ledger_confidence", "backup"])
        return [
            stage(
                "launch",
                "Launch",
                [
                    "env_live_enabled",
                    "local_auth",
                    "session_acknowledged",
                    "source_trust",
                    "source_soak",
                    "source_soak_history",
                    "strategy_promotion",
                    "execution_shadow",
                    "shadow_samples",
                    "shadow_pnl",
                    "policy_caps",
                    "signer_health",
                    "manual_live_proof",
                    "backup",
                ],
                [
                    {"label": "Run full local verification.", "command": "scripts\\verify.ps1"},
                    {"label": "Confirm PumpPortal source health and raw-event archive are acceptable."},
                    {"label": "Confirm fresh paper/shadow evidence and recent manual-live wallet proof."},
                    {"label": "Acknowledge live session risk and tiny caps before arming."},
                ],
                "Launch prerequisites are clear; arm only the selected local backend.",
            ),
            {
                "id": "run",
                "label": "Run",
                "status": "ready" if not run_blockers else "blocked",
                "blockers": run_blockers,
                "actions": [
                    {"label": "Arm the local backend for the selected wallet."},
                    {"label": "Confirm full_sniper_gate is ready before autonomous buy/sell flow."},
                    {"label": "Run only under the configured tiny trade, loss, exposure, position, slippage, and fee caps."},
                ],
                "operator_action": "Run the tiny autonomous pilot and watch live audit, ledger, and cap evidence." if not run_blockers else "Resolve run blockers before autonomous execution.",
            },
            {
                "id": "stop",
                "label": "Stop",
                "status": "ready",
                "blockers": [],
                "actions": [
                    {"label": "Enable the live kill switch to stop new entries immediately."},
                    {"label": "Disarm the active backend after the run or on any blocker."},
                    {"label": "Stop the bot if source, ledger, wallet, cap, or audit state becomes unsafe."},
                ],
                "operator_action": "Kill switch and disarm controls are the immediate stop path.",
            },
            {
                "id": "recover",
                "label": "Recover",
                "status": "ready" if not recover_blockers else "blocked",
                "blockers": recover_blockers,
                "actions": [
                    {"label": "Recover unresolved live audits before the next entry."},
                    {"label": "Resolve stale or needs-review ledger confidence."},
                    {"label": "Use the latest pre-run backup and restore preview if local state needs recovery."},
                ],
                "operator_action": "Recovery state is clear." if not recover_blockers else "Clear recovery and accounting debt before the next run.",
            },
            {
                "id": "review",
                "label": "Review",
                "status": "ready",
                "blockers": [],
                "actions": [
                    {"label": "Open the post-run review report after every pilot."},
                    {"label": "Export incident bundles for failed, stale, blocked, or needs-review audits."},
                    {"label": "Confirm every live action has audit, transaction, ledger, cap, kill-switch, and PnL evidence."},
                ],
                "operator_action": "Post-run review is mandatory after live or shadow-live operation.",
            },
        ]

    def incident_export(self, audit_id: str) -> dict[str, object]:
        audit = self.storage.load_live_execution_audit(audit_id)
        if audit is None:
            raise ValueError(f"Live audit not found: {audit_id}")
        intent = self.storage.load_live_intent(audit.intent_id) if audit.intent_id else None
        token = next((item for item in self.storage.load_all_tokens(5000) if item.mint == audit.mint), None)
        source_events = [
            event.to_dict()
            for event in self.storage.load_source_events(5000)
            if self._source_event_mint(event) == audit.mint or (token and event.normalized_token_id == token.id)
        ][:100]
        operator_events = [
            event.to_dict()
            for event in self.storage.load_all_events(1000)
            if event.subsystem in {"live", "source", "backup_restore"} or audit.id in event.message or audit.mint[:8] in event.message
        ][:100]
        position = next((item for item in self.storage.load_live_ledger_positions(500) if item.mint == audit.mint and item.wallet_public_key == audit.wallet_public_key), None)
        return {
            "artifact_type": "cryptoarc_live_incident_export",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "audit_id": audit.id,
            "audit": audit.to_dict(),
            "intent": intent.to_dict() if intent else None,
            "quote": audit.quote,
            "simulation": audit.simulation,
            "signature_status": audit.confirmation,
            "balance_snapshot": audit.balance_snapshot,
            "ledger_position": position.to_dict() if position else None,
            "token": token.to_dict() if token else None,
            "source_events": source_events,
            "operator_events": operator_events,
            "recovery_state": {
                "status": audit.status,
                "final_status": audit.final_status,
                "reconciliation_status": audit.reconciliation_status,
                "recovery_attempts": audit.recovery_attempts,
                "last_recovery_error": audit.last_recovery_error,
                "recommended_action": audit.recommended_action,
            },
            "privacy_note": "Export contains public wallet, transaction, token, quote, and local operator evidence only. It must not contain seed phrases or private keys.",
        }

    def backup_artifact(self) -> dict[str, object]:
        artifact = self.storage.create_backup_artifact()
        filename = f"cryptoarc-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        self.add_event(
            "info",
            "Created full local backup artifact",
            subsystem="backup_restore",
            operator_action="Download and store the restore artifact before making risky changes.",
        )
        return {"filename": filename, "artifact": artifact}

    def preview_restore_artifact(self, artifact: dict[str, object]) -> dict[str, object]:
        preview = self.storage.preview_restore_artifact(artifact)
        self.add_event(
            "warning",
            "Previewed restore artifact compatibility",
            subsystem="backup_restore",
            operator_action="Confirm the warnings before restoring local state.",
        )
        return preview

    def confirm_restore_artifact(self, artifact: dict[str, object]) -> dict[str, object]:
        self._require_destructive_operation_prerequisites()
        try:
            result = self.storage.restore_backup_artifact(artifact, post_swap_validator=self._reload_from_storage)
            self.status = BotStatus.STOPPED
        except Exception:
            try:
                self._reload_from_storage(persist_settings_version=False)
            except Exception as recovery_error:
                LOGGER.error(
                    "Restore recovery reload failed after restore rejection; recovery_error=%s",
                    recovery_error.__class__.__name__,
                )
            self.status = BotStatus.STOPPED
            self.settings.live_active_backend_armed = False
            self.settings.kill_switch_enabled = True
            raise
        self.add_event(
            "warning",
            "Local database restored from artifact",
            subsystem="backup_restore",
            operator_action="Review migration, source, and live-wallet status after restore.",
        )
        return result

    def restore_smoke_test(self) -> dict[str, object]:
        artifact = self.storage.create_backup_artifact()
        preview = self.storage.preview_restore_artifact(artifact)
        passed = bool(preview.get("compatible")) and str(preview.get("integrity_check", "")).lower() == "ok"
        status = "pass" if passed else "review"
        operator_action = (
            "Backup artifact can be previewed and passes SQLite integrity checks."
            if passed
            else "Review restore smoke test warnings before any real-money session."
        )
        result = {
            "artifact_type": "cryptoarc_restore_smoke_test",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "status": status,
            "passed": passed,
            "backup_artifact_created_at": artifact.get("created_at"),
            "schema_version": preview.get("schema_version"),
            "current_schema_version": preview.get("current_schema_version"),
            "database_name": preview.get("database_name"),
            "payload_bytes": preview.get("payload_bytes"),
            "integrity_check": preview.get("integrity_check"),
            "risk_level": preview.get("risk_level"),
            "changed_tables": preview.get("changed_tables", []),
            "table_deltas": preview.get("table_deltas", {}),
            "summary": preview.get("summary", {}),
            "current_summary": preview.get("current_summary", {}),
            "warnings": preview.get("warnings", []),
            "recommended_actions": preview.get("recommended_actions", []),
            "operator_action": operator_action,
            "privacy_note": "Smoke test returns restore metadata only. It does not return the embedded database payload, seed phrases, private keys, or Telegram tokens.",
        }
        self.add_event(
            "info" if passed else "warning",
            "Restore smoke test completed",
            subsystem="backup_restore",
            operator_action=operator_action,
        )
        return result

    def backup_restore_export(self, entry_id: str = "") -> dict[str, object]:
        history = self.storage.load_backup_restore_history(100)
        selected = None
        if entry_id.strip():
            selected = next((item for item in history if str(item.get("id", "")) == entry_id.strip()), None)
            if selected is None:
                raise ValueError(f"Backup/restore history entry not found: {entry_id}")
        status = self.storage.backup_restore_status()
        return {
            "artifact_type": "cryptoarc_backup_restore_evidence",
            "format_version": 1,
            "generated_at": utc_now().isoformat(),
            "entry_id": entry_id.strip() or None,
            "selected_entry": selected,
            "status": status,
            "schema": self.storage.schema_status(),
            "data_summary": self.data_summary(),
            "source": self.source_health(),
            "readiness": self.readiness_status(),
            "live_recovery": {
                "last_poll_at": self.live_last_poll_at.isoformat() if self.live_last_poll_at else None,
                "summary": self.live_last_poll_summary,
                "unresolved_audits": [
                    audit.to_dict()
                    for audit in self._normalize_live_audits(self.storage.load_live_execution_audits(200))
                    if self._is_unresolved_live_audit(audit)
                ][:25],
            },
            "operator_events": [
                event.to_dict()
                for event in self.storage.load_all_events(500)
                if event.subsystem in {"backup_restore", "live", "source"} or "restore" in event.message.lower() or "backup" in event.message.lower()
            ][:100],
            "privacy_note": "Export contains local database path, schema, restore history, public wallet/audit evidence, and operator events. It must not contain seed phrases or private keys.",
        }

    def source_adapters(self) -> list[dict[str, object]]:
        source = self.source_health()
        solana_configured = bool(self.solana_wss_endpoint)
        solana_mentions_configured = bool(self.solana_logs_mentions_address.strip())
        solana_ready = solana_configured and solana_mentions_configured
        solana_status = self.solana_logs_status.status if solana_ready else ("missing_mentions_address" if solana_configured else "not_configured")
        return [
            {"name": "mock", "enabled": True, "status": "available", "capabilities": ["launches", "simulated_prices"], "confidence": 0.7},
            {
                "name": "pumpportal",
                "enabled": True,
                "status": self.source_status.status if self.source_status.source == "pumpportal" else "available",
                "capabilities": ["launches", "trades", "raw_events"],
                "confidence": source.get("health_score", 0) / 100,
                "details": {
                    "role": "fast_path",
                    "cost_profile": "free_launch_streams_bounded_trade_subscriptions",
                    "operator_action": "Keep one WebSocket connection and inspect raw event quality before promotion.",
                },
            },
            {
                "name": "solana_logs",
                "enabled": solana_ready,
                "status": solana_status,
                "capabilities": ["logsSubscribe", "single_address_mentions_filter", "direct_chain_verification", "raw_event_archive", "paper_create_normalization"],
                "confidence": 0.7 if self.solana_logs_status.status == "connected" else (0.5 if solana_ready else 0.0),
                "details": {
                    "role": "verification_path",
                    "wss_configured": solana_configured,
                    "mentions_address_configured": solana_mentions_configured,
                    "paper_normalization_enabled": self.settings.direct_solana_paper_enabled,
                    "paper_normalization_min_confidence": self.settings.direct_solana_min_confidence,
                    "mentions_address": self.solana_logs_mentions_address,
                    "endpoint_configured": solana_configured,
                    "filter": "mentions",
                    "subscription_limit": "one address per logsSubscribe subscription",
                    "last_event_at": self.solana_logs_status.last_event_at.isoformat() if self.solana_logs_status.last_event_at else "",
                    "reconnect_attempts": self.solana_logs_status.reconnect_attempts,
                    "operator_action": "Set SOLANA_WSS_ENDPOINT and SOLANA_LOGS_MENTIONS_ADDRESS to archive direct-chain logs for PumpPortal comparison." if not solana_ready else "Direct-chain verifier archives logsSubscribe notifications for source-soak comparison.",
                },
            },
        ]

    def trade_review_detail(self, token_id: str) -> dict[str, object]:
        token = next((item for item in self.storage.load_all_tokens(5000) if item.id == token_id), None)
        trade = next((item for item in self.storage.load_trades(5000) if item.token_id == token_id), None)
        decisions = [item.to_dict() for item in self.storage.load_strategy_decisions(1000) if item.token_id == token_id]
        observations = [
            item.to_dict()
            for item in self.storage.load_price_observations(1000, mint=token.mint if token else "")
            if item.token_id == token_id or (token and item.mint == token.mint)
        ]
        source_events = [
            event
            for event in self.storage.load_source_events(1000)
            if event.normalized_token_id == token_id
            or (token and token.mint and self._source_event_mint(event) == token.mint)
        ]
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
            "review_workflow": self._trade_review_workflow(token_id, trade, decisions, observations, source_events),
        }

    def _trade_review_workflow(
        self,
        token_id: str,
        trade: TradeRecord | None,
        decisions: list[dict[str, object]],
        observations: list[dict[str, object]],
        source_events: list[SourceEvent],
    ) -> dict[str, object]:
        closed = sorted(
            [item for item in self.storage.load_trades(5000) if item.closed_at and item.pnl_sol is not None],
            key=lambda item: item.closed_at or item.opened_at or utc_now(),
            reverse=True,
        )
        token_ids = [item.token_id for item in closed]
        index = token_ids.index(token_id) if token_id in token_ids else -1
        labels = self.storage.load_trade_labels(5000)
        latest_label = next((label for label in sorted(labels, key=lambda item: item.created_at, reverse=True) if label.token_id == token_id), None)
        rejected_prices = [item for item in observations if not bool(item.get("accepted"))]
        accepted_prices = [item for item in observations if bool(item.get("accepted"))]
        suggested_labels: list[str] = []
        if trade:
            if trade.source_price_confidence < 0.65 or rejected_prices:
                suggested_labels.append("bad_price_data")
            if (trade.pnl_sol or 0.0) < 0:
                suggested_labels.append("bad_entry")
            if int(trade.hold_duration_seconds or 0) >= max(300, int(self.settings.minimum_hold_time_seconds or 0) * 3):
                suggested_labels.append("held_too_long")
            if (trade.pnl_sol or 0.0) >= 0 and not suggested_labels:
                suggested_labels.append("good_entry")
            if trade.exit_reason and "too early" in trade.exit_reason.lower():
                suggested_labels.append("exited_too_early")
        checklist = [
            {
                "id": "source_events",
                "label": "Source events",
                "status": "pass" if source_events else "missing",
                "count": len(source_events),
                "ids": [event.id for event in source_events[:8]],
                "operator_action": "Open the timeline source rows before labeling the entry." if source_events else "Find or replay raw source evidence before trusting this trade.",
            },
            {
                "id": "decisions",
                "label": "Strategy decisions",
                "status": "pass" if decisions else "missing",
                "count": len(decisions),
                "ids": [str(item.get("id", "")) for item in decisions[:8]],
                "operator_action": "Review the decision stack and score breakdown." if decisions else "Missing decisions should be labeled or excluded from tuning.",
            },
            {
                "id": "price_observations",
                "label": "Price observations",
                "status": "warn" if rejected_prices else ("pass" if accepted_prices else "missing"),
                "count": len(observations),
                "ids": [str(item.get("id", "")) for item in observations[:8]],
                "operator_action": "Rejected price observations need bad-price review." if rejected_prices else "Accepted price observations support PnL review.",
            },
            {
                "id": "pnl",
                "label": "PnL evidence",
                "status": "pass" if trade and trade.pnl_sol is not None else "missing",
                "count": 1 if trade and trade.pnl_sol is not None else 0,
                "ids": [trade.id] if trade else [],
                "operator_action": "Compare net PnL with fees, slippage, hold time, and exit reason.",
            },
        ]
        return {
            "current_index": index,
            "total_closed": len(closed),
            "previous_token_id": token_ids[index - 1] if index > 0 else "",
            "next_token_id": token_ids[index + 1] if index >= 0 and index + 1 < len(token_ids) else "",
            "selected_label": latest_label.label if latest_label else "",
            "suggested_labels": list(dict.fromkeys(suggested_labels)),
            "checklist": checklist,
            "operator_action": "Use the checklist, apply a label, then move to the next trade in the queue.",
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

    def _coerce_setting_value(self, setting: str, value: object, current_value: object) -> object:
        if isinstance(current_value, bool):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "1", "yes", "on"}:
                    return True
                if lowered in {"false", "0", "no", "off"}:
                    return False
            raise ValueError(f"invalid boolean value for {setting}")
        if isinstance(current_value, int) and not isinstance(current_value, bool):
            if isinstance(value, (int, float, str)):
                return int(float(value))
            raise ValueError(f"invalid integer value for {setting}")
        if isinstance(current_value, float):
            if isinstance(value, (int, float, str)):
                return float(value)
            raise ValueError(f"invalid numeric value for {setting}")
        if isinstance(current_value, str):
            return str(value)
        return value

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

    def _filter_trades_by_timeframe(self, trades: list[TradeRecord], timeframe: str) -> list[TradeRecord]:
        timeframe_windows = {
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "1h": timedelta(hours=1),
            "24h": timedelta(hours=24),
        }
        window = timeframe_windows.get(str(timeframe))
        if window is None:
            return trades
        cutoff = utc_now() - window
        return [trade for trade in trades if (trade.closed_at or trade.opened_at or utc_now()) >= cutoff]

    def _timeframe_cutoff(self, timeframe: str) -> datetime | None:
        timeframe = str(timeframe or "all").strip().lower()
        if timeframe in {"all", "any", ""}:
            return None
        if timeframe.endswith("m"):
            try:
                return utc_now() - timedelta(minutes=max(1, min(10080, int(timeframe[:-1]))))
            except ValueError:
                return utc_now() - timedelta(hours=24)
        if timeframe.endswith("h"):
            try:
                return utc_now() - timedelta(hours=max(1, min(168, int(timeframe[:-1]))))
            except ValueError:
                return utc_now() - timedelta(hours=24)
        if timeframe.endswith("d"):
            try:
                return utc_now() - timedelta(days=max(1, min(30, int(timeframe[:-1]))))
            except ValueError:
                return utc_now() - timedelta(hours=24)
        return utc_now() - timedelta(hours=24)

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
        if target == "live_intents":
            return {"live_intents": [item.to_dict() for item in self.storage.load_live_intents(5000)]}
        if target == "live_ledger_positions":
            return {"live_ledger_positions": [item.to_dict() for item in self.storage.load_live_ledger_positions(5000)]}
        if target == "source_soak_history":
            return {"source_soak_history": self.storage.load_source_soak_history(5000)}
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
            "live_intents": [item.to_dict() for item in self.storage.load_live_intents(5000)],
            "live_ledger_positions": [item.to_dict() for item in self.storage.load_live_ledger_positions(5000)],
            "source_soak_history": self.storage.load_source_soak_history(5000),
        }

    def data_summary(self) -> dict[str, int]:
        return self.storage.data_summary_counts()

    def _require_destructive_operation_prerequisites(self) -> None:
        blockers: list[str] = []
        if (
            self.status != BotStatus.STOPPED
            or self.source_status.status != "offline"
            or self.solana_logs_status.status != "offline"
        ):
            blockers.append("bot and source tasks must be stopped")
        if self.settings.live_active_backend_armed:
            blockers.append("live backend must be disarmed")
        if not self.settings.kill_switch_enabled:
            blockers.append("live kill switch must be engaged")
        try:
            audit_count = self.storage.count_live_execution_audits()
            audits = self.storage.load_live_execution_audits(max(1, audit_count + 1))
            if len(audits) != audit_count:
                blockers.append("live audit debt could not be verified")
            elif any(self._is_unresolved_live_audit(audit) for audit in audits):
                blockers.append("unresolved live audit debt must be zero")
        except Exception:
            blockers.append("live audit debt could not be verified")
        if blockers:
            raise ValueError(f"Destructive operation blocked; unmet prerequisites: {'; '.join(blockers)}")

    def clear_data(self, target: str) -> dict[str, int]:
        self._require_destructive_operation_prerequisites()
        if target == "all":
            reset_version = SettingsVersion(
                id=new_id("set"),
                created_at=utc_now(),
                settings=asdict(self.settings),
                label="reset",
                changed_keys=[],
            )
            self.storage.clear_all_data(reset_version)
            self.tokens.clear()
            self.creator_history.clear()
            self.events.clear()
            self.backtest_runs.clear()
            self.current_settings_version_id = reset_version.id
            self.add_event("warning", "Data cleared: all")
            self.recalculate_stats()
            return self.data_summary()
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
        if target in {"live_intents", "all"}:
            self.storage.clear_live_intents()
        if target in {"live_ledger_positions", "all"}:
            self.storage.clear_live_ledger_positions()
        if target in {"source_soak_history", "all"}:
            self.storage.clear_source_soak_history()
        self.add_event("warning", f"Data cleared: {target}")
        self.recalculate_stats()
        return self.data_summary()

    def open_position_count(self) -> int:
        open_ids = {token.id for token in self._load_open_storage_tokens()}
        open_ids.update(token.id for token in self.tokens if token.status in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING})
        return len(open_ids)

    def recalculate_stats(self) -> None:
        self._ensure_active_tokens_loaded()
        self._normalize_active_tokens()
        skipped = [token for token in self.tokens if token.status == TokenStatus.SKIPPED]
        open_tokens = self._load_open_storage_tokens()
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
        open_entry_fees = sum(float(token.fee_paid_sol or 0.0) for token in open_tokens if token.id not in closed_ids)
        closed_entry_fees = sum(float(trade.entry_fee_sol or 0.0) for trade in closed)
        closed_exit_fees = sum(float(trade.exit_fee_sol or 0.0) for trade in closed)
        entry_fees = round(closed_entry_fees + open_entry_fees, 9)
        exit_fees = round(closed_exit_fees, 9)
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
            entry_fees_sol=entry_fees,
            exit_fees_sol=exit_fees,
            total_fees_sol=round(entry_fees + exit_fees, 9),
            best_trade_sol=round(max([trade.pnl_sol or 0.0 for trade in closed], default=0.0), 6),
            worst_trade_sol=round(min([trade.pnl_sol or 0.0 for trade in closed], default=0.0), 6),
            average_win_sol=round(gross_win / len(wins), 6) if wins else 0.0,
            average_loss_sol=round(sum(losses) / len(losses), 6) if losses else 0.0,
            profit_factor=round(gross_win / gross_loss, 2) if gross_loss else 0.0,
            max_drawdown_sol=round(max_drawdown, 6),
            avg_hold_seconds=int(sum(hold_durations) / len(hold_durations)) if hold_durations else 0,
        )

    def _normalize_active_tokens(self) -> None:
        changed = False
        for token in self.tokens:
            if token.status not in {TokenStatus.BUYING, TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING}:
                continue
            if token.closed_at is not None:
                token.status = TokenStatus.PAPER_SOLD
                changed = True
                self.storage.save_token(token)
        if changed:
            self.tokens = deque(sorted(self.tokens, key=lambda token: token.detected_at, reverse=True), maxlen=80)

    def snapshot(self, *, include_tokens: bool = True) -> BotSnapshot:
        return BotSnapshot(
            status=self.status,
            settings=self.settings,
            tokens=self._snapshot_tokens() if include_tokens else [],
            events=list(self.events),
            stats=self.stats,
            source_status=self.source_status,
        )

    def _snapshot_tokens(self, limit: int = 300) -> list[TokenSignal]:
        current = list(self.tokens)
        by_id = {token.id: token for token in current}
        for token in self.storage.load_tokens(limit):
            if token.status != TokenStatus.SKIPPED:
                by_id[token.id] = token
        return sorted(by_id.values(), key=lambda token: token.detected_at, reverse=True)[:limit]
