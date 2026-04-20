import React from "react";
import { createRoot } from "react-dom/client";
import { Connection, PublicKey, VersionedTransaction } from "@solana/web3.js";
import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  Clock,
  Database,
  Download,
  Filter,
  Gauge,
  Pause,
  Play,
  RotateCcw,
  Save,
  Search,
  Shield,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Target,
  Wallet,
  X
} from "lucide-react";
import {
  backupDatabase,
  acknowledgeLiveSession,
  clearData,
  confirmLiveAudit,
  cancelLiveIntent,
  createLiveIntent,
  createLiveQuote,
  createExperiment,
  disableTotp,
  authStatus,
  exportUrl,
  fetchBacktests,
  fetchDataSummary,
  fetchExperiments,
  fetchLiveRequests,
  fetchLiveAudit,
  fetchLiveIntents,
  fetchLiveLedger,
  fetchLivePositions,
  fetchLiveStatus,
  fetchDataIntegrity,
  fetchOperationalMonitoring,
  fetchPerformanceAnalytics,
  fetchPriceDiagnostics,
  fetchPriceObservations,
  fetchPumpFunReport,
  fetchReadinessStatus,
  fetchReplayTimeline,
  fetchSafetyStatus,
  fetchSolanaStatus,
  fetchSnapshot,
  fetchSourceEvents,
  fetchSourceHealth,
  fetchSecurityStatus,
  fetchSettingsVersions,
  fetchSourceAdapters,
  fetchStrategyDecisions,
  fetchStrategyPresets,
  fetchTrades,
  fetchTradeSessions,
  fetchTradeReviewDetail,
  fetchTradeLabels,
  fetchTuningSuggestions,
  fetchWatchdogStatus,
  login,
  logout,
  openSnapshotSocket,
  patchSettings,
  quoteLiveIntent,
  recoverWatchdog,
  reconcileLiveIntent,
  recordLiveSimulation,
  reviewLiveRequest,
  generateLiveIntents,
  submitLiveAudit,
  labelTrade,
  runABStrategyReplay,
  runBacktestV3,
  runRawReplayBacktest,
  runReplayBacktest,
  runStrategyComparison,
  startBot,
  stopBot,
  setupTotp,
  saveStrategyPreset,
  updatePassword,
  verifyTotp
} from "./api";
import type { BacktestResult, BacktestV3Result, BotSnapshot, BotSettings, DataIntegrityReport, DataSummary, ExperimentRun, LiveExecutionAudit, LiveExecutionRequest, LiveIntent, LiveLedger, LivePosition, LiveStatus, OperationalMonitoring, PerformanceAnalytics, PriceDiagnostics, PriceObservation, PumpFunReport, ReadinessStatus, ReplayTimelineEvent, SafetyStatus, SecurityStatus, SettingsVersion, SolanaStatus, SourceAdapterStatus, SourceEvent, SourceHealth, StrategyDecisionRecord, StrategyPreset, TokenSignal, TradeEvent, TradeLabel, TradeRecord, TradeReviewDetail, TradeSession, TuningSuggestion, WatchdogStatus } from "./types";
import "./styles.css";

type BrowserSolanaProvider = {
  isPhantom?: boolean;
  publicKey?: { toString(): string };
  connect: () => Promise<{ publicKey: { toString(): string } }>;
  disconnect?: () => Promise<void>;
  signAndSendTransaction?: (transaction: VersionedTransaction) => Promise<{ signature: string }>;
  signTransaction?: (transaction: VersionedTransaction) => Promise<VersionedTransaction>;
};

declare global {
  interface Window {
    solana?: BrowserSolanaProvider;
  }
}

const fallbackSnapshot: BotSnapshot = {
  status: "stopped",
  settings: {
    mode: "paper",
    launch_source: "mock",
    strategy_profile: "balanced",
    trade_size_sol: 0.1,
    slippage_tolerance_pct: 1,
    take_profit_pct: 50,
    stop_loss_pct: 30,
    daily_loss_cap_sol: 1,
    wallet_balance_cap_sol: 1,
    max_creator_hold_pct: 10,
    trading_speed: "normal",
    max_hold_time_seconds: 600,
    minimum_hold_time_seconds: 0,
    risk_tolerance: "medium",
    score_threshold: 62,
    max_open_positions: 3,
    launch_interval_seconds: 2,
    paper_price_volatility_pct: 18,
    max_position_ticks: 40,
    require_live_confirmation: true,
    detect_new_tokens: true,
    auto_refresh: true,
    filter_honeypots: true,
    filter_rug_risk: true,
    live_trading_enabled: false,
    min_buy_velocity: 0,
    max_sell_pressure: 1,
    min_metadata_score: 0,
    max_token_age_seconds: 120,
    source_stale_seconds: 60,
    source_max_reconnects: 5,
    backtest_replay_limit: 80,
    raw_replay_limit: 120,
    enable_trade_toasts: true,
    compact_table_mode: false,
    paper_fill_delay_ticks: 0,
    paper_fee_bps: 25,
    paper_price_impact_pct: 0.15,
    paper_failed_fill_pct: 0,
    duplicate_symbol_penalty: true,
    strict_metadata_checks: false,
    use_observed_prices: true,
    max_trade_subscriptions: 60,
    min_price_confidence: 0.45,
    max_first_observed_move_pct: 500,
    prefer_market_cap_price: true,
    trailing_stop_enabled: false,
    trailing_stop_pct: 18,
    partial_take_profit_enabled: false,
    partial_take_profit_pct: 25,
    partial_take_profit_fraction: 0.5,
    cooldown_after_loss_enabled: false,
    cooldown_after_loss_seconds: 0,
    max_trades_per_hour_enabled: true,
    max_trades_per_hour: 30,
    velocity_slippage_enabled: true,
    max_same_creator_buys_enabled: true,
    max_same_creator_buys: 3,
    stop_on_source_degraded: false,
    max_rejected_price_streak_enabled: true,
    max_rejected_price_streak: 5,
    strategy_weight_metadata: 1,
    strategy_weight_momentum: 1,
    strategy_weight_pressure: 1,
    strategy_weight_creator: 1,
    break_even_stop_enabled: false,
    break_even_after_profit_pct: 15,
    stalled_trade_exit_enabled: false,
    stalled_trade_seconds: 90,
    stalled_trade_min_move_pct: 3,
    sell_pressure_exit_enabled: false,
    sell_pressure_exit_threshold: 0.65,
    kill_switch_enabled: false,
    max_consecutive_losses_enabled: false,
    max_consecutive_losses: 5,
    halt_on_low_replay_confidence: false,
    min_replay_confidence: 50,
    halt_on_low_readiness: false,
    min_readiness_score: 70,
    solana_rpc_url: "https://api.mainnet-beta.solana.com",
    watch_wallet_address: "",
    manual_live_enabled: false,
    manual_live_max_sol: 0.05,
    autonomous_live_enabled: false,
    live_max_trade_sol: 0,
    live_daily_loss_cap_sol: 0,
    live_wallet_exposure_cap_sol: 0,
    live_max_open_positions: 0,
    live_max_slippage_pct: 0,
    live_priority_fee_cap_sol: 0,
    live_session_acknowledged: false,
    live_signer_mode: "browser_wallet"
  },
  tokens: [],
  events: [],
  stats: {
    total_trades: 0,
    successful_trades: 0,
    losing_trades: 0,
    scratch_trades: 0,
    skipped_tokens: 0,
    open_positions: 0,
    closed_trades: 0,
    win_rate_pct: 0,
    gross_win_rate_pct: 0,
    scratch_rate_pct: 0,
    scratch_threshold_sol: 0.001,
    total_pnl_sol: 0,
    best_trade_sol: 0,
    worst_trade_sol: 0,
    average_win_sol: 0,
    average_loss_sol: 0,
    profit_factor: 0,
    max_drawdown_sol: 0,
    avg_hold_seconds: 0
  },
  source_status: {
    source: "mock",
    status: "offline",
    message: "Source is idle",
    events_received: 0,
    last_event_at: null,
    reconnect_attempts: 0,
    raw_events_seen: 0,
    normalized_events: 0,
    normalization_failures: 0,
    events_per_minute: 0,
    last_event_age_seconds: null,
    health_score: 0,
    launch_events_seen: 0,
    trade_events_seen: 0,
    status_events_seen: 0,
    active_trade_subscriptions: 0,
    dropped_trade_subscriptions: 0
  }
};

function statusLabel(status: TokenSignal["status"]): string {
  return status.replace("_", " ");
}

function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m`;
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h`;
}

function shortAddress(value: string): string {
  return value ? `${value.slice(0, 6)}...${value.slice(-4)}` : "not connected";
}

function dateTimeLocalToIso(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

function pnlClass(pnl: number | null | undefined, scratchThreshold = 0.001): "profit" | "loss" | "scratch" {
  const value = pnl || 0;
  if (value > scratchThreshold) return "profit";
  if (value < -scratchThreshold) return "loss";
  return "scratch";
}

type PnlTimeframe = "5m" | "15m" | "1h" | "24h" | "all";
type QueueFilter = "all" | "open" | "profitable" | "losses";
type QueueSort = "newest" | "score" | "pnl" | "creator";
type WorkspacePage = "monitor" | "analysis" | "backtests" | "review" | "data";
type SettingsPage = "source" | "strategy" | "risk" | "exits" | "simulation" | "advanced" | "security";
type LiveWalletMethod = "browser_wallet" | "local_signer_daemon";
type PnlWalletScope = "paper" | string;

const pnlTimeframes: Array<{ label: string; value: PnlTimeframe; millis: number | null }> = [
  { label: "5m", value: "5m", millis: 5 * 60 * 1000 },
  { label: "15m", value: "15m", millis: 15 * 60 * 1000 },
  { label: "1h", value: "1h", millis: 60 * 60 * 1000 },
  { label: "24h", value: "24h", millis: 24 * 60 * 60 * 1000 },
  { label: "All", value: "all", millis: null }
];

const strategyPresets: Record<string, Partial<BotSettings>> = {
  conservative: {
    trade_size_sol: 0.05,
    slippage_tolerance_pct: 0.6,
    score_threshold: 72,
    max_creator_hold_pct: 6,
    max_open_positions: 2,
    take_profit_pct: 35,
    stop_loss_pct: 18,
    max_hold_time_seconds: 420,
    risk_tolerance: "low",
    trading_speed: "slow"
  },
  balanced: {
    trade_size_sol: 0.1,
    slippage_tolerance_pct: 1,
    score_threshold: 62,
    max_creator_hold_pct: 10,
    max_open_positions: 3,
    take_profit_pct: 50,
    stop_loss_pct: 30,
    max_hold_time_seconds: 600,
    risk_tolerance: "medium",
    trading_speed: "normal"
  },
  aggressive: {
    trade_size_sol: 0.15,
    slippage_tolerance_pct: 1.8,
    score_threshold: 54,
    max_creator_hold_pct: 16,
    max_open_positions: 5,
    take_profit_pct: 70,
    stop_loss_pct: 38,
    max_hold_time_seconds: 720,
    risk_tolerance: "high",
    trading_speed: "fast"
  },
  scalper: {
    trade_size_sol: 0.08,
    slippage_tolerance_pct: 1.2,
    score_threshold: 58,
    max_creator_hold_pct: 12,
    max_open_positions: 4,
    take_profit_pct: 22,
    stop_loss_pct: 16,
    max_hold_time_seconds: 180,
    risk_tolerance: "medium",
    trading_speed: "turbo"
  }
};

function validateSettings(settings: BotSettings): string[] {
  const warnings: string[] = [];
  if (settings.trade_size_sol > settings.daily_loss_cap_sol) {
    warnings.push("Trade size is larger than the daily loss cap.");
  }
  if (settings.slippage_tolerance_pct > 5) {
    warnings.push("Slippage above 5% can make paper fills unrealistically generous.");
  }
  if (settings.risk_tolerance === "degen" && settings.trading_speed === "turbo") {
    warnings.push("Degen risk plus turbo speed is an intentionally high-risk profile.");
  }
  if (!settings.filter_honeypots || !settings.filter_rug_risk) {
    warnings.push("One or more safety filters are disabled.");
  }
  if (settings.paper_failed_fill_pct > 20) {
    warnings.push("Failed fill rate above 20% can heavily skew replay results.");
  }
  if (settings.min_price_confidence < 0.45) {
    warnings.push("Low price confidence can allow weaker PumpPortal price hints into P&L.");
  }
  if (settings.max_first_observed_move_pct > 1000) {
    warnings.push("Very high first-move limits can let unit mismatches distort P&L.");
  }
  if (settings.live_trading_enabled) {
    warnings.push("Live trading request is set, but backend execution remains blocked unless explicitly enabled by environment.");
  }
  return warnings;
}

function buildPnlHistory(trades: TradeRecord[], timeframe: PnlTimeframe): number[] {
  const selectedFrame = pnlTimeframes.find((item) => item.value === timeframe) ?? pnlTimeframes[pnlTimeframes.length - 1];
  const cutoff = selectedFrame.millis === null ? null : Date.now() - selectedFrame.millis;
  const closedTrades = trades
    .filter((trade) => trade.lifecycle_status === "closed" && trade.closed_at && trade.pnl_sol !== null)
    .filter((trade) => cutoff === null || new Date(trade.closed_at || "").getTime() >= cutoff)
    .sort((left, right) => new Date(left.closed_at || "").getTime() - new Date(right.closed_at || "").getTime());

  let cumulative = 0;
  const history = [0];
  closedTrades.forEach((trade) => {
    cumulative = Number((cumulative + (trade.pnl_sol || 0)).toFixed(6));
    history.push(cumulative);
  });
  return history.slice(-40);
}

function timeframeClosedTrades(trades: TradeRecord[], timeframe: PnlTimeframe): TradeRecord[] {
  const selectedFrame = pnlTimeframes.find((item) => item.value === timeframe) ?? pnlTimeframes[pnlTimeframes.length - 1];
  const cutoff = selectedFrame.millis === null ? null : Date.now() - selectedFrame.millis;
  return trades.filter((trade) => {
    if (trade.lifecycle_status !== "closed" || !trade.closed_at || trade.pnl_sol === null) {
      return false;
    }
    return cutoff === null || new Date(trade.closed_at).getTime() >= cutoff;
  });
}

function buildLivePnlHistory(ledger: LiveLedger | null, timeframe: PnlTimeframe): number[] {
  const summary = ledger?.summary;
  const current = Number(((summary?.realized_pnl_sol ?? 0) + (summary?.unrealized_pnl_sol ?? 0)).toFixed(6));
  const selectedFrame = pnlTimeframes.find((item) => item.value === timeframe) ?? pnlTimeframes[pnlTimeframes.length - 1];
  const cutoff = selectedFrame.millis === null ? null : Date.now() - selectedFrame.millis;
  const fills = (ledger?.positions ?? [])
    .flatMap((position) => position.fills ?? [])
    .filter((fill) => cutoff === null || new Date(fill.created_at).getTime() >= cutoff)
    .sort((left, right) => new Date(left.created_at).getTime() - new Date(right.created_at).getTime());
  if (!fills.length) return [0, current];
  const values = [0];
  fills.forEach(() => values.push(values[values.length - 1]));
  if (values[values.length - 1] !== current) values.push(current);
  return values.slice(-40);
}

function App() {
  const [snapshot, setSnapshot] = React.useState<BotSnapshot>(fallbackSnapshot);
  const [apiState, setApiState] = React.useState("connecting");
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [selectedTokenId, setSelectedTokenId] = React.useState<string | null>(null);
  const [pnlTimeframe, setPnlTimeframe] = React.useState<PnlTimeframe>("all");
  const [queueFilter, setQueueFilter] = React.useState<QueueFilter>("all");
  const [queueSort, setQueueSort] = React.useState<QueueSort>("newest");
  const [workspacePage, setWorkspacePage] = React.useState<WorkspacePage>("monitor");
  const [toasts, setToasts] = React.useState<TradeEvent[]>([]);
  const [backtestResult, setBacktestResult] = React.useState<BacktestResult | null>(null);
  const [backtests, setBacktests] = React.useState<BacktestResult[]>([]);
  const [sourceEvents, setSourceEvents] = React.useState<SourceEvent[]>([]);
  const [dataSummary, setDataSummary] = React.useState<DataSummary | null>(null);
  const [trades, setTrades] = React.useState<TradeRecord[]>([]);
  const [priceObservations, setPriceObservations] = React.useState<PriceObservation[]>([]);
  const [strategyDecisions, setStrategyDecisions] = React.useState<StrategyDecisionRecord[]>([]);
  const [tradeSessions, setTradeSessions] = React.useState<TradeSession[]>([]);
  const [settingsVersions, setSettingsVersions] = React.useState<SettingsVersion[]>([]);
  const [performanceAnalytics, setPerformanceAnalytics] = React.useState<PerformanceAnalytics | null>(null);
  const [tuningSuggestions, setTuningSuggestions] = React.useState<TuningSuggestion[]>([]);
  const [dataIntegrity, setDataIntegrity] = React.useState<DataIntegrityReport | null>(null);
  const [priceDiagnostics, setPriceDiagnostics] = React.useState<PriceDiagnostics | null>(null);
  const [pumpfunReport, setPumpfunReport] = React.useState<PumpFunReport | null>(null);
  const [safetyStatus, setSafetyStatus] = React.useState<SafetyStatus | null>(null);
  const [readinessStatus, setReadinessStatus] = React.useState<ReadinessStatus | null>(null);
  const [opsMonitoring, setOpsMonitoring] = React.useState<OperationalMonitoring | null>(null);
  const [backtestV3Result, setBacktestV3Result] = React.useState<BacktestV3Result | null>(null);
  const [experiments, setExperiments] = React.useState<ExperimentRun[]>([]);
  const [tradeLabels, setTradeLabels] = React.useState<TradeLabel[]>([]);
  const [strategyPresetsRemote, setStrategyPresetsRemote] = React.useState<StrategyPreset[]>([]);
  const [sourceAdapters, setSourceAdapters] = React.useState<SourceAdapterStatus[]>([]);
  const [selectedReviewTradeId, setSelectedReviewTradeId] = React.useState<string | null>(null);
  const [replayTimeline, setReplayTimeline] = React.useState<ReplayTimelineEvent[]>([]);
  const [tradeReviewDetail, setTradeReviewDetail] = React.useState<TradeReviewDetail | null>(null);
  const [sourceHealth, setSourceHealth] = React.useState<SourceHealth | null>(null);
  const [securityStatus, setSecurityStatus] = React.useState<SecurityStatus | null>(null);
  const [watchdogStatus, setWatchdogStatus] = React.useState<WatchdogStatus | null>(null);
  const [solanaStatus, setSolanaStatus] = React.useState<SolanaStatus | null>(null);
  const [liveRequests, setLiveRequests] = React.useState<LiveExecutionRequest[]>([]);
  const [liveStatus, setLiveStatus] = React.useState<LiveStatus | null>(null);
  const [liveAudit, setLiveAudit] = React.useState<LiveExecutionAudit[]>([]);
  const [livePositions, setLivePositions] = React.useState<LivePosition[]>([]);
  const [liveIntents, setLiveIntents] = React.useState<LiveIntent[]>([]);
  const [liveLedger, setLiveLedger] = React.useState<LiveLedger | null>(null);
  const [walletPublicKey, setWalletPublicKey] = React.useState(() => window.localStorage.getItem("cryptoarc_wallet_public_key") || "");
  const [liveWallets, setLiveWallets] = React.useState<string[]>(() => JSON.parse(window.localStorage.getItem("cryptoarc_live_wallets") || "[]"));
  const [pnlWalletScope, setPnlWalletScope] = React.useState<PnlWalletScope>(() => window.localStorage.getItem("cryptoarc_pnl_wallet_scope") || "paper");
  const [walletBalanceSol, setWalletBalanceSol] = React.useState<number | null>(null);
  const [liveWalletOpen, setLiveWalletOpen] = React.useState(false);
  const [liveWalletMethod, setLiveWalletMethod] = React.useState<LiveWalletMethod>("browser_wallet");
  const [liveAction, setLiveAction] = React.useState<"buy" | "sell">("buy");
  const [liveMint, setLiveMint] = React.useState("");
  const [liveAmount, setLiveAmount] = React.useState("0.001");
  const [liveSlippage, setLiveSlippage] = React.useState(5);
  const [livePriorityFee, setLivePriorityFee] = React.useState(0.00001);
  const [livePool, setLivePool] = React.useState("pump");
  const [activeLiveAudit, setActiveLiveAudit] = React.useState<LiveExecutionAudit | null>(null);
  const [activeLiveIntentId, setActiveLiveIntentId] = React.useState("");
  const [backtestLimit, setBacktestLimit] = React.useState(80);
  const [backtestProfile, setBacktestProfile] = React.useState<BotSettings["strategy_profile"]>("balanced");
  const [backtestDateFrom, setBacktestDateFrom] = React.useState("");
  const [backtestDateTo, setBacktestDateTo] = React.useState("");
  const [backtestSpeed, setBacktestSpeed] = React.useState(50);
  const [tokenSearch, setTokenSearch] = React.useState("");
  const [showWatchlistOnly, setShowWatchlistOnly] = React.useState(false);
  const [watchlist, setWatchlist] = React.useState<string[]>(() => JSON.parse(window.localStorage.getItem("cryptoarc_watchlist") || "[]"));
  const [apiError, setApiError] = React.useState("");
  const [authRequired, setAuthRequired] = React.useState(false);
  const [authed, setAuthed] = React.useState(false);
  const [totpRequired, setTotpRequired] = React.useState(false);
  const seenToastIds = React.useRef<Set<string>>(new Set());
  const readyForToasts = React.useRef(false);

  React.useEffect(() => {
    let closed = false;
    let retryTimer = 0;
    let retryDelay = 1000;
    let socket: WebSocket | null = null;

    authStatus()
      .then((status) => {
        setAuthRequired(status.enabled);
        setTotpRequired(status.totp_enabled);
        setAuthed(!status.enabled || Boolean(window.localStorage.getItem("cryptoarc_token")));
      })
      .catch((error) => setApiError(`Auth status failed: ${error.message}`));

    fetchSnapshot()
      .then((data) => {
        data.events.forEach((event) => seenToastIds.current.add(event.id));
        setSnapshot(data);
        setApiState("connected");
      })
      .catch((error) => {
        setApiState("offline");
        setApiError(`Snapshot failed: ${error.message}`);
      });

    function connect() {
      socket = openSnapshotSocket((data) => {
        setSnapshot(data);
        retryDelay = 1000;
        if (!readyForToasts.current) {
          data.events.forEach((event) => seenToastIds.current.add(event.id));
          readyForToasts.current = true;
          setApiState("connected");
          return;
        }
        const tradeEvents = data.events
          .filter((event) => event.message.startsWith("Paper bought") || event.message.startsWith("Paper sold"))
          .filter((event) => !seenToastIds.current.has(event.id))
          .slice(0, 3);
        if (tradeEvents.length) {
          tradeEvents.forEach((event) => seenToastIds.current.add(event.id));
          refreshResearchData().catch(() => undefined);
          if (data.settings.enable_trade_toasts) {
            setToasts((current) => [...tradeEvents, ...current].slice(0, 4));
          }
        }
        setApiState("connected");
      });
      socket.addEventListener("open", () => setApiState("connected"));
      socket.addEventListener("close", () => {
        setApiState("offline");
        if (!closed) {
          retryTimer = window.setTimeout(connect, retryDelay);
          retryDelay = Math.min(15000, retryDelay * 1.8);
        }
      });
      socket.addEventListener("error", () => setApiState("offline"));
    }

    connect();
    return () => {
      closed = true;
      window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  if (authRequired && !authed) {
    return <AuthGate totpRequired={totpRequired} onAuthed={() => setAuthed(true)} onError={setApiError} error={apiError} />;
  }

  const settings = snapshot.settings;
  const stats = snapshot.stats;
  const running = snapshot.status === "running";
  const liveCapsSet = settings.live_max_trade_sol > 0 && settings.live_daily_loss_cap_sol > 0 && settings.live_wallet_exposure_cap_sol > 0 && settings.live_max_open_positions > 0 && settings.live_max_slippage_pct > 0 && settings.live_priority_fee_cap_sol > 0;
  const latestLiveAudit = liveAudit[0] ?? null;
  const selectedLivePnlWallet = pnlWalletScope === "paper" ? "" : pnlWalletScope;
  const selectedToken = snapshot.tokens.find((token) => token.id === selectedTokenId) ?? null;
  const watchSet = React.useMemo(() => new Set(watchlist), [watchlist]);
  const timeframeTrades = React.useMemo(() => timeframeClosedTrades(trades, pnlTimeframe), [pnlTimeframe, trades]);
  const paperTimeframePnl = timeframeTrades.reduce((total, token) => total + (token.pnl_sol || 0), 0);
  const liveTimeframePnl = Number(((liveLedger?.summary.realized_pnl_sol ?? 0) + (liveLedger?.summary.unrealized_pnl_sol ?? 0)).toFixed(6));
  const timeframePnl = pnlWalletScope === "paper" ? paperTimeframePnl : liveTimeframePnl;
  const paperPnlHistory = React.useMemo(() => buildPnlHistory(trades, pnlTimeframe), [trades, pnlTimeframe]);
  const livePnlHistory = React.useMemo(() => buildLivePnlHistory(liveLedger, pnlTimeframe), [liveLedger, pnlTimeframe]);
  const pnlHistory = pnlWalletScope === "paper" ? paperPnlHistory : livePnlHistory;
  const filteredTokens = React.useMemo(() => {
    let tokens = snapshot.tokens;
    const query = tokenSearch.trim().toLowerCase();
    if (query) {
      tokens = tokens.filter((token) =>
        [token.symbol, token.name, token.mint, token.creator, token.reason, ...(token.intelligence_tags || [])]
          .join(" ")
          .toLowerCase()
          .includes(query)
      );
    }
    if (showWatchlistOnly) {
      tokens = tokens.filter((token) => watchSet.has(token.mint));
    }
    if (queueFilter === "open") {
      tokens = tokens.filter((token) => ["buying", "paper_bought", "monitoring"].includes(token.status));
    }
    const scratchThreshold = snapshot.stats.scratch_threshold_sol ?? 0.001;
    if (queueFilter === "profitable") {
      tokens = tokens.filter((token) => (token.pnl_sol || 0) > scratchThreshold);
    }
    if (queueFilter === "losses") {
      tokens = tokens.filter((token) => (token.pnl_sol || 0) < -scratchThreshold);
    }
    return [...tokens].sort((left, right) => {
      if (queueSort === "score") return right.score - left.score;
      if (queueSort === "pnl") return (right.pnl_sol || 0) - (left.pnl_sol || 0);
      if (queueSort === "creator") return (right.creator_hold_pct || 0) - (left.creator_hold_pct || 0);
      return new Date(right.detected_at).getTime() - new Date(left.detected_at).getTime();
    });
  }, [queueFilter, queueSort, snapshot.stats.scratch_threshold_sol, snapshot.tokens, tokenSearch, showWatchlistOnly, watchSet]);

  function toggleWatchlist(token: TokenSignal) {
    const next = watchSet.has(token.mint) ? watchlist.filter((mint) => mint !== token.mint) : [...watchlist, token.mint];
    setWatchlist(next);
    window.localStorage.setItem("cryptoarc_watchlist", JSON.stringify(next));
  }

  async function saveSettings(nextSettings: BotSettings) {
    try {
      const updated = await patchSettings(nextSettings as unknown as Record<string, number | boolean | string>);
      setSnapshot(updated);
      setSettingsOpen(false);
      setApiError("");
    } catch (error) {
      setApiError(`Save failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function replayBacktest() {
    try {
      const result = await runReplayBacktest({ limit: backtestLimit, profile: backtestProfile, date_from: dateTimeLocalToIso(backtestDateFrom), date_to: dateTimeLocalToIso(backtestDateTo), replay_speed: backtestSpeed });
      setBacktestResult(result);
      setBacktests(await fetchBacktests());
      setSnapshot(await fetchSnapshot());
    } catch (error) {
      setApiError(`Backtest failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function rawReplayBacktest() {
    try {
      const result = await runRawReplayBacktest({ limit: backtestLimit, profile: backtestProfile, date_from: dateTimeLocalToIso(backtestDateFrom), date_to: dateTimeLocalToIso(backtestDateTo), replay_speed: backtestSpeed });
      setBacktestResult(result);
      setBacktests(await fetchBacktests());
    } catch (error) {
      setApiError(`Raw replay failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function compareStrategies() {
    try {
      const result = await runStrategyComparison();
      setBacktestResult(result);
      setBacktests(await fetchBacktests());
    } catch (error) {
      setApiError(`Comparison failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function abReplayStrategies() {
    try {
      const result = await runABStrategyReplay({ limit: backtestLimit, profile: backtestProfile, date_from: dateTimeLocalToIso(backtestDateFrom), date_to: dateTimeLocalToIso(backtestDateTo), replay_speed: backtestSpeed });
      setBacktestResult(result);
      setBacktests(await fetchBacktests());
      setPerformanceAnalytics(await fetchPerformanceAnalytics());
    } catch (error) {
      setApiError(`A/B replay failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function runBacktestSuiteV3() {
    try {
      const result = await runBacktestV3({ limit: backtestLimit, profile: backtestProfile, date_from: dateTimeLocalToIso(backtestDateFrom), date_to: dateTimeLocalToIso(backtestDateTo), replay_speed: backtestSpeed });
      setBacktestV3Result(result);
      setBacktests(await fetchBacktests());
      setDataIntegrity(await fetchDataIntegrity());
    } catch (error) {
      setApiError(`Backtest v3 failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function saveExperimentFromDashboard() {
    try {
      const experiment = await createExperiment(`Experiment ${new Date().toLocaleString()}`, backtestProfile, backtestLimit, "Saved from dashboard");
      setExperiments((current) => [experiment, ...current].slice(0, 50));
      setBacktestV3Result(experiment.result);
    } catch (error) {
      setApiError(`Experiment save failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function saveCurrentStrategyPreset() {
    try {
      const preset = await saveStrategyPreset(`Preset ${new Date().toLocaleTimeString()}`, "Saved from Strategy Builder");
      setStrategyPresetsRemote((current) => [preset, ...current]);
    } catch (error) {
      setApiError(`Preset save failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function refreshConnectedWalletBalance(publicKey = walletPublicKey) {
    if (!publicKey) {
      setWalletBalanceSol(null);
      return;
    }
    try {
      const connection = new Connection(snapshot.settings.solana_rpc_url, "confirmed");
      const lamports = await connection.getBalance(new PublicKey(publicKey));
      setWalletBalanceSol(lamports / 1_000_000_000);
    } catch {
      setWalletBalanceSol(null);
    }
  }

  async function refreshResearchData() {
    const [runs, events, summary, tradeRows, health, security, observations, decisions, sessions, versions, analytics, suggestions, integrity, price, pumpfun, safety, readiness, ops, experimentRows, labels, presets, adapters, watchdog, solana, liveRows, liveState, auditRows, livePositionRows, intentRows, ledgerState] = await Promise.all([
      fetchBacktests(),
      fetchSourceEvents(),
      fetchDataSummary(),
      fetchTrades(),
      fetchSourceHealth(),
      fetchSecurityStatus(),
      fetchPriceObservations(),
      fetchStrategyDecisions(),
      fetchTradeSessions(),
      fetchSettingsVersions(),
      fetchPerformanceAnalytics(),
      fetchTuningSuggestions(),
      fetchDataIntegrity(),
      fetchPriceDiagnostics(),
      fetchPumpFunReport(),
      fetchSafetyStatus(),
      fetchReadinessStatus(),
      fetchOperationalMonitoring(),
      fetchExperiments(),
      fetchTradeLabels(),
      fetchStrategyPresets(),
      fetchSourceAdapters(),
      fetchWatchdogStatus(),
      fetchSolanaStatus(),
      fetchLiveRequests(),
      fetchLiveStatus(walletPublicKey),
      fetchLiveAudit(),
      fetchLivePositions(walletPublicKey),
      fetchLiveIntents(),
      fetchLiveLedger(selectedLivePnlWallet)
    ]);
    setBacktests(runs);
    setSourceEvents(events);
    setDataSummary(summary);
    setTrades(tradeRows);
    setSourceHealth(health);
    setSecurityStatus(security);
    setPriceObservations(observations);
    setStrategyDecisions(decisions);
    setTradeSessions(sessions);
    setSettingsVersions(versions);
    setPerformanceAnalytics(analytics);
    setTuningSuggestions(suggestions);
    setDataIntegrity(integrity);
    setPriceDiagnostics(price);
    setPumpfunReport(pumpfun);
    setSafetyStatus(safety);
    setReadinessStatus(readiness);
    setOpsMonitoring(ops);
    setExperiments(experimentRows);
    setTradeLabels(labels);
    setStrategyPresetsRemote(presets);
    setSourceAdapters(adapters);
    setWatchdogStatus(watchdog);
    setSolanaStatus(solana);
    setLiveRequests(liveRows);
    setLiveStatus(liveState);
    setLiveAudit(auditRows);
    setLivePositions(livePositionRows);
    setLiveIntents(intentRows);
    setLiveLedger(ledgerState);
    refreshConnectedWalletBalance().catch(() => undefined);
  }

  async function loadReplayTimeline(tokenId: string) {
    setSelectedReviewTradeId(tokenId);
    try {
      const [timeline, detail] = await Promise.all([fetchReplayTimeline(tokenId), fetchTradeReviewDetail(tokenId)]);
      setReplayTimeline(timeline);
      setTradeReviewDetail(detail);
    } catch (error) {
      setApiError(`Timeline failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function clearProjectData(target: "tokens" | "events" | "source_events" | "backtests" | "trades" | "price_observations" | "strategy_decisions" | "trade_sessions" | "settings_versions" | "experiments" | "trade_labels" | "strategy_presets" | "live_execution_requests" | "live_sessions" | "live_execution_audits" | "live_intents" | "live_ledger_positions" | "all") {
    try {
      const summary = await clearData(target);
      setDataSummary(summary);
      await refreshResearchData();
      setSnapshot(await fetchSnapshot());
    } catch (error) {
      setApiError(`Clear failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function reviewManualLiveRequest(requestId: string, status: "reviewed" | "rejected") {
    try {
      const updated = await reviewLiveRequest(requestId, status, "Dashboard audit review");
      setLiveRequests((current) => current.map((request) => request.id === requestId ? updated : request));
      await refreshResearchData();
    } catch (error) {
      setApiError(`Live request review failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function connectBrowserWallet() {
    try {
      if (!window.solana) {
        setApiError("Browser wallet not found. Install or unlock Phantom/Solflare and refresh.");
        return;
      }
      const result = await window.solana.connect();
      const publicKey = result.publicKey.toString();
      setWalletPublicKey(publicKey);
      window.localStorage.setItem("cryptoarc_wallet_public_key", publicKey);
      const nextWallets = [publicKey, ...liveWallets.filter((wallet) => wallet !== publicKey)].slice(0, 8);
      setLiveWallets(nextWallets);
      window.localStorage.setItem("cryptoarc_live_wallets", JSON.stringify(nextWallets));
      setLiveStatus(await fetchLiveStatus(publicKey));
      setLivePositions(await fetchLivePositions(publicKey));
      await refreshConnectedWalletBalance(publicKey);
      setApiError("");
    } catch (error) {
      setApiError(`Wallet connect failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function acknowledgeLiveRisk() {
    try {
      await acknowledgeLiveSession();
      const updated = await fetchSnapshot();
      setSnapshot(updated);
      setLiveStatus(await fetchLiveStatus(walletPublicKey));
    } catch (error) {
      setApiError(`Live acknowledgement failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function createLivePreview() {
    try {
      const audit = await createLiveQuote({
        action: liveAction,
        mint: liveMint,
        amount: liveAmount,
        denominated_in_sol: liveAction === "buy",
        slippage_pct: liveSlippage,
        priority_fee_sol: livePriorityFee,
        pool: livePool,
        wallet_public_key: walletPublicKey,
        signer_mode: "browser_wallet"
      });
      const simulated = await recordLiveSimulation(audit.id, false, "Browser wallet simulation must be reviewed before signing.");
      setActiveLiveAudit(simulated);
      setLiveAudit((current) => [simulated, ...current.filter((item) => item.id !== simulated.id)]);
      setApiError("");
    } catch (error) {
      setApiError(`Live quote failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function createManualIntent() {
    try {
      const intent = await createLiveIntent({
        action: liveAction,
        mint: liveMint,
        amount: liveAmount,
        denominated_in_sol: liveAction === "buy",
        wallet_public_key: walletPublicKey,
        signer_mode: "browser_wallet",
        source: "manual",
        reason: "Manual Live Wallet workbench intent"
      });
      setLiveIntents((current) => [intent, ...current.filter((item) => item.id !== intent.id)]);
      setActiveLiveIntentId(intent.id);
      setApiError("");
    } catch (error) {
      setApiError(`Live intent failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function generateWorkbenchIntents() {
    try {
      const intents = await generateLiveIntents(walletPublicKey, "browser_wallet", watchlist);
      setLiveIntents(intents);
      setApiError("");
    } catch (error) {
      setApiError(`Intent generation failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function quoteWorkbenchIntent(intentId: string) {
    try {
      const audit = await quoteLiveIntent(intentId, liveSlippage, livePriorityFee, livePool);
      setActiveLiveAudit(audit);
      setActiveLiveIntentId(intentId);
      setLiveAudit((current) => [audit, ...current.filter((item) => item.id !== audit.id)]);
      setLiveIntents(await fetchLiveIntents());
      setApiError("");
    } catch (error) {
      setApiError(`Intent quote failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function cancelWorkbenchIntent(intentId: string) {
    try {
      const intent = await cancelLiveIntent(intentId);
      setLiveIntents((current) => current.map((item) => item.id === intent.id ? intent : item));
      if (activeLiveIntentId === intentId) setActiveLiveIntentId("");
    } catch (error) {
      setApiError(`Cancel intent failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function simulateActiveLiveAudit() {
    if (!activeLiveAudit) return;
    try {
      const encoded = String(activeLiveAudit.quote.unsigned_transaction_base64 || "");
      if (!encoded) throw new Error("No unsigned transaction is available");
      const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
      const transaction = VersionedTransaction.deserialize(bytes);
      const connection = new Connection(snapshot.settings.solana_rpc_url, "confirmed");
      const simulation = await connection.simulateTransaction(transaction);
      const ok = !simulation.value.err;
      const warning = ok ? "" : `RPC simulation warning: ${JSON.stringify(simulation.value.err)}`;
      const result = {
        err: simulation.value.err,
        logs: simulation.value.logs || [],
        unitsConsumed: simulation.value.unitsConsumed || 0
      };
      const updated = await recordLiveSimulation(activeLiveAudit.id, ok, warning, "", result);
      setActiveLiveAudit(updated);
      setLiveAudit((current) => [updated, ...current.filter((item) => item.id !== updated.id)]);
      setLiveIntents(await fetchLiveIntents());
      setApiError("");
    } catch (error) {
      const updated = await recordLiveSimulation(activeLiveAudit.id, false, "RPC simulation could not complete; manual signing remains available.", error instanceof Error ? error.message : "unknown error", {});
      setActiveLiveAudit(updated);
      setLiveAudit((current) => [updated, ...current.filter((item) => item.id !== updated.id)]);
    }
  }

  async function signAndSendLiveAudit() {
    if (!activeLiveAudit) return;
    try {
      if (!window.solana) throw new Error("Browser wallet not connected");
      const encoded = String(activeLiveAudit.quote.unsigned_transaction_base64 || "");
      if (!encoded) throw new Error("No unsigned transaction is available");
      const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
      const transaction = VersionedTransaction.deserialize(bytes);
      let signature = "";
      if (window.solana.signAndSendTransaction) {
        signature = (await window.solana.signAndSendTransaction(transaction)).signature;
      } else if (window.solana.signTransaction) {
        const signed = await window.solana.signTransaction(transaction);
        const connection = new Connection(snapshot.settings.solana_rpc_url, "confirmed");
        signature = await connection.sendTransaction(signed);
      } else {
        throw new Error("Wallet does not support transaction signing");
      }
      const submitted = await submitLiveAudit(activeLiveAudit.id, signature);
      const connection = new Connection(snapshot.settings.solana_rpc_url, "confirmed");
      const confirmation = await connection.confirmTransaction(signature, "confirmed");
      const confirmed = await confirmLiveAudit(submitted.id, confirmation.value.err ? "failed" : "confirmed", confirmation.value.err ? JSON.stringify(confirmation.value.err) : "");
      setActiveLiveAudit(confirmed);
      setLiveAudit((current) => [confirmed, ...current.filter((item) => item.id !== confirmed.id)]);
      setLivePositions(await fetchLivePositions(walletPublicKey));
      setLiveLedger(await fetchLiveLedger(selectedLivePnlWallet));
      setLiveIntents(await fetchLiveIntents());
      if (activeLiveIntentId) {
        await reconcileLiveIntent(activeLiveIntentId).catch(() => undefined);
        setLiveLedger(await fetchLiveLedger(selectedLivePnlWallet));
      }
    } catch (error) {
      setApiError(`Wallet submit failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  React.useEffect(() => {
    refreshResearchData().catch(() => undefined);
  }, []);

  React.useEffect(() => {
    if (!walletPublicKey) {
      setWalletBalanceSol(null);
      return;
    }
    Promise.all([
      fetchLiveStatus(walletPublicKey).then(setLiveStatus),
      fetchLivePositions(walletPublicKey).then(setLivePositions),
      fetchLiveIntents().then(setLiveIntents),
      fetchLiveLedger(selectedLivePnlWallet).then(setLiveLedger),
      refreshConnectedWalletBalance(walletPublicKey)
    ]).catch(() => undefined);
  }, [walletPublicKey, selectedLivePnlWallet, snapshot.settings.solana_rpc_url]);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <section className="brand">
          <div className="brand-mark">CA</div>
          <div>
            <h1>CryptoARC v2</h1>
            <p>Paper sniper console</p>
          </div>
          <span className="version">v0.1</span>
        </section>

        <section className="panel">
          <div className="panel-title">
            <Wallet size={15} />
            Live Wallet
          </div>
          <button className="wallet-button" onClick={() => setLiveWalletOpen(true)}>
            {walletPublicKey ? "Manage live wallet" : "Connect wallet"}
          </button>
          <div className="wallet-summary">
            <span>Wallet <strong>{shortAddress(walletPublicKey)}</strong></span>
            <span>Balance <strong>{walletBalanceSol === null ? "-" : `${walletBalanceSol.toFixed(4)} SOL`}</strong></span>
            <span>Live env <strong>{liveStatus?.env_live_enabled ? "enabled" : "disabled"}</strong></span>
            <span>Caps <strong>{liveCapsSet ? "set" : "required"}</strong></span>
            <span>Ack <strong>{settings.live_session_acknowledged ? "done" : "needed"}</strong></span>
            <span>Gates <strong>{liveStatus?.live_execution_available ? "open" : "blocked"}</strong></span>
            <span>Latest <strong>{latestLiveAudit?.status ?? "none"}</strong></span>
          </div>
          <p className="muted">Connect and review wallet state anytime. Quotes and signing stay blocked until live mode is enabled.</p>
        </section>

        <section className="panel control-panel">
          <div className="panel-title">
            <Bot size={15} />
            Bot Control
            <span className={running ? "pill live" : "pill"}>{snapshot.status}</span>
          </div>
          <div className="button-row">
            <button className="primary" onClick={async () => setSnapshot(await startBot())}>
              <Play size={14} /> Start
            </button>
            <button className="danger" onClick={async () => setSnapshot(await stopBot())}>
              <Pause size={14} /> Stop
            </button>
          </div>
          <div className="control-summary">
            <span>Trade size</span>
            <strong>{settings.trade_size_sol.toFixed(3)} SOL</strong>
            <span>TP / SL</span>
            <strong>
              {settings.take_profit_pct}% / {settings.stop_loss_pct}%
            </strong>
            <span>Score gate</span>
            <strong>{settings.score_threshold}</strong>
          </div>
        </section>

        <section className="panel stats-grid">
          <Metric label="Open" value={stats.open_positions.toString()} />
          <Metric label="Closed" value={stats.closed_trades.toString()} />
          <Metric label="W / L / S" value={`${stats.successful_trades} / ${stats.losing_trades} / ${stats.scratch_trades}`} />
          <Metric label="Net win" value={`${stats.win_rate_pct}%`} />
          <Metric label="Gross win" value={`${stats.gross_win_rate_pct}%`} />
          <Metric label="P&L" value={`${stats.total_pnl_sol.toFixed(4)} SOL`} />
        </section>

        <section className={(timeframePnl || 0) >= 0 ? "panel pnl-panel pnl-positive" : "panel pnl-panel pnl-negative"}>
          <div className="panel-title">
            <BarChart3 size={15} />
            Live P&L
            <span className={(timeframePnl || 0) >= 0 ? "mini-profit" : "mini-loss"}>
              {timeframePnl >= 0 ? "+" : ""}
              {timeframePnl.toFixed(4)} SOL
            </span>
          </div>
          <div className="timeframe-row">
            {pnlTimeframes.map((item) => (
              <button
                key={item.value}
                className={pnlTimeframe === item.value ? "timeframe active" : "timeframe"}
                onClick={() => setPnlTimeframe(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <label className="pnl-wallet-select">
            Wallet scope
            <select
              value={pnlWalletScope}
              onChange={(event) => {
                setPnlWalletScope(event.target.value);
                window.localStorage.setItem("cryptoarc_pnl_wallet_scope", event.target.value);
              }}
            >
              <option value="paper">Paper wallet</option>
              {liveWallets.map((wallet) => (
                <option key={wallet} value={wallet}>Live {shortAddress(wallet)}</option>
              ))}
              {walletPublicKey && !liveWallets.includes(walletPublicKey) ? <option value={walletPublicKey}>Live {shortAddress(walletPublicKey)}</option> : null}
            </select>
          </label>
          <PnlAreaChart values={pnlHistory} animationKey={`${pnlHistory.length}-${pnlHistory[pnlHistory.length - 1] ?? 0}`} />
          <div className="pnl-range">
            <span>Low {Math.min(...pnlHistory).toFixed(4)}</span>
            <span>High {Math.max(...pnlHistory).toFixed(4)}</span>
          </div>
          <p className="pnl-caption">
            {pnlWalletScope === "paper"
              ? `${timeframeTrades.length} closed paper trades in selected range`
              : `${liveLedger?.summary.open_positions ?? 0} live positions / ${(liveLedger?.summary.approximate ?? true) ? "approximate" : "confirmed"} P&L`}
          </p>
        </section>

        <section className="panel replay-panel">
          <div className="panel-title">
            <RotateCcw size={15} />
            Replay Lab
          </div>
          <button className="secondary-action" onClick={replayBacktest}>
            <Sparkles size={14} /> Run replay
          </button>
          {backtestResult ? (
            <div className="replay-result">
              <span>{backtestResult.tokens_replayed} tokens replayed</span>
              <strong>
                {backtestResult.paper_buys} buys / {backtestResult.skips} skips
              </strong>
              <span>{backtestResult.estimated_pnl_sol.toFixed(4)} SOL estimated, {backtestResult.win_rate_pct}% win</span>
            </div>
          ) : (
            <p className="muted">Replay saved launches through the current paper rules.</p>
          )}
        </section>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Connection status</p>
            <strong className={apiState === "connected" ? "connected" : "offline"}>{apiState}</strong>
          </div>
          <div>
            <p className="eyebrow">Launch source</p>
            <strong className={snapshot.source_status.status === "connected" ? "connected" : "offline"}>
              {snapshot.source_status.source} / {snapshot.source_status.status}
            </strong>
          </div>
          <div className="top-actions">
            <nav className="page-tabs">
              {(["monitor", "analysis", "backtests", "review", "data"] as WorkspacePage[]).map((page) => (
                <button key={page} className={workspacePage === page ? "active" : ""} onClick={() => setWorkspacePage(page)}>
                  {page}
                </button>
              ))}
            </nav>
            <div className="mode-banner">
              <Activity size={16} />
              {securityStatus?.auth_enabled === false ? "Auth disabled / paper mode" : "Preview and paper mode only"}
            </div>
            {authRequired ? (
              <button className="settings-button" onClick={() => { logout(); setAuthed(false); }}>
                Logout
              </button>
            ) : null}
            <button className="settings-button" onClick={() => setSettingsOpen(true)}>
              <SlidersHorizontal size={16} />
              Settings
            </button>
          </div>
        </header>

        {workspacePage === "monitor" && <section className="hero-strip">
          <div>
            <h2>Live Launch Monitor</h2>
            <p>Mock Pump.fun launch stream for strategy, risk, and dashboard testing.</p>
            <p>{snapshot.source_status.message}</p>
          </div>
          <div className="hero-metrics">
            <Metric label="Skipped" value={stats.skipped_tokens.toString()} />
            <Metric label="Best" value={`${stats.best_trade_sol.toFixed(4)} SOL`} />
            <Metric label="Worst" value={`${stats.worst_trade_sol.toFixed(4)} SOL`} />
            <Metric label="Profit factor" value={stats.profit_factor.toFixed(2)} />
          </div>
        </section>}

        {workspacePage === "monitor" && <section className="content-grid">
          <div className={settings.compact_table_mode ? "token-table-wrap compact-token-panel" : "token-table-wrap"}>
            <div className="section-heading">
              <div>
                <h3>Token Queue</h3>
                <p>Every paper decision includes a reason.</p>
              </div>
              <div className="queue-tools">
                <label className="queue-search">
                  <Search size={14} />
                  <input value={tokenSearch} onChange={(event) => setTokenSearch(event.target.value)} placeholder="Search tokens" />
                </label>
                <button className={showWatchlistOnly ? "queue-filter active" : "queue-filter"} onClick={() => setShowWatchlistOnly((value) => !value)}>
                  watchlist
                </button>
                <Filter size={15} />
                {(["all", "open", "profitable", "losses"] as QueueFilter[]).map((filter) => (
                  <button
                    key={filter}
                    className={queueFilter === filter ? "queue-filter active" : "queue-filter"}
                    onClick={() => setQueueFilter(filter)}
                  >
                    {filter}
                  </button>
                ))}
                <select value={queueSort} onChange={(event) => setQueueSort(event.target.value as QueueSort)}>
                  <option value="newest">Newest</option>
                  <option value="score">Score</option>
                  <option value="pnl">P&L</option>
                  <option value="creator">Creator hold</option>
                </select>
              </div>
            </div>
            <TokenTable
              tokens={filteredTokens}
              onSelect={setSelectedTokenId}
              compact={settings.compact_table_mode}
              watchlist={watchSet}
              onToggleWatch={toggleWatchlist}
              scratchThreshold={stats.scratch_threshold_sol ?? 0.001}
            />
          </div>

          <aside className="events">
            <div className="section-heading">
              <div>
                <h3>Event Stream</h3>
                <p>Audit trail for the current session.</p>
              </div>
              <Bell size={18} />
            </div>
            {snapshot.events.map((event) => (
              <article key={event.id} className={`event ${event.level}`}>
                <span>{new Date(event.created_at).toLocaleTimeString()}</span>
                <p>{event.message}</p>
              </article>
            ))}
          </aside>
        </section>}

        {workspacePage === "backtests" && (
          <BacktestDashboard
            runs={backtests}
            latest={backtestResult}
            limit={backtestLimit}
            profile={backtestProfile}
            dateFrom={backtestDateFrom}
            dateTo={backtestDateTo}
            speed={backtestSpeed}
            onLimitChange={setBacktestLimit}
            onProfileChange={setBacktestProfile}
            onDateFromChange={setBacktestDateFrom}
            onDateToChange={setBacktestDateTo}
            onSpeedChange={setBacktestSpeed}
            onRun={replayBacktest}
            onRawReplay={rawReplayBacktest}
            onCompare={compareStrategies}
            onABReplay={abReplayStrategies}
            onRunV3={runBacktestSuiteV3}
            onSaveExperiment={saveExperimentFromDashboard}
            v3Result={backtestV3Result}
            experiments={experiments}
          />
        )}

        {workspacePage === "analysis" && (
          <AnalysisDashboard tokens={snapshot.tokens} trades={trades} stats={stats} analytics={performanceAnalytics} suggestions={tuningSuggestions} priceDiagnostics={priceDiagnostics} pumpfunReport={pumpfunReport} safetyStatus={safetyStatus} readinessStatus={readinessStatus} pnlTimeframe={pnlTimeframe} onTimeframeChange={setPnlTimeframe} />
        )}

        {workspacePage === "review" && (
          <TradeReviewPage
            trades={trades}
            versions={settingsVersions}
            analytics={performanceAnalytics}
            suggestions={tuningSuggestions}
            selectedTradeId={selectedReviewTradeId}
            timeline={replayTimeline}
            detail={tradeReviewDetail}
            labels={tradeLabels}
            onLabelTrade={async (tokenId, label) => {
              const saved = await labelTrade(tokenId, label);
              setTradeLabels((current) => [saved, ...current]);
            }}
            onSelectTrade={loadReplayTimeline}
          />
        )}

        {workspacePage === "data" && (
          <DataDashboard
            summary={dataSummary}
            sourceEvents={sourceEvents}
            sourceHealth={sourceHealth}
            securityStatus={securityStatus}
            trades={trades}
            priceObservations={priceObservations}
            strategyDecisions={strategyDecisions}
            tradeSessions={tradeSessions}
            settingsVersions={settingsVersions}
            dataIntegrity={dataIntegrity}
            priceDiagnostics={priceDiagnostics}
            pumpfunReport={pumpfunReport}
            safetyStatus={safetyStatus}
            readinessStatus={readinessStatus}
            opsMonitoring={opsMonitoring}
            sourceAdapters={sourceAdapters}
            watchdogStatus={watchdogStatus}
            solanaStatus={solanaStatus}
            liveRequests={liveRequests}
            liveAudit={liveAudit}
            auditEvents={snapshot.events}
            onRefresh={refreshResearchData}
            onRecover={async () => {
              const updated = await recoverWatchdog();
              setSnapshot(updated);
              await refreshResearchData();
            }}
            onReviewLiveRequest={reviewManualLiveRequest}
            onClear={clearProjectData}
          />
        )}
      </section>
      {apiError && <button className="api-error" onClick={() => setApiError("")}>{apiError}</button>}
      {liveWalletOpen && (
        <LiveWalletModal
          method={liveWalletMethod}
          onMethodChange={setLiveWalletMethod}
          walletPublicKey={walletPublicKey}
          walletBalanceSol={walletBalanceSol}
          settings={settings}
          liveStatus={liveStatus}
          liveAudit={liveAudit}
          livePositions={livePositions}
          liveIntents={liveIntents}
          liveLedger={liveLedger}
          liveAction={liveAction}
          liveMint={liveMint}
          liveAmount={liveAmount}
          liveSlippage={liveSlippage}
          livePriorityFee={livePriorityFee}
          livePool={livePool}
          activeLiveAudit={activeLiveAudit}
          activeLiveIntentId={activeLiveIntentId}
          onClose={() => setLiveWalletOpen(false)}
          onConnectWallet={connectBrowserWallet}
          onAcknowledgeLive={acknowledgeLiveRisk}
          onLiveActionChange={setLiveAction}
          onLiveMintChange={setLiveMint}
          onLiveAmountChange={setLiveAmount}
          onLiveSlippageChange={setLiveSlippage}
          onLivePriorityFeeChange={setLivePriorityFee}
          onLivePoolChange={setLivePool}
          onCreateLivePreview={createLivePreview}
          onCreateManualIntent={createManualIntent}
          onGenerateIntents={generateWorkbenchIntents}
          onQuoteIntent={quoteWorkbenchIntent}
          onCancelIntent={cancelWorkbenchIntent}
          onSimulateActiveAudit={simulateActiveLiveAudit}
          onSignAndSendLive={signAndSendLiveAudit}
        />
      )}
      {settingsOpen && (
        <SettingsModal
          settings={settings}
          sourceStatus={snapshot.source_status}
          serverStrategyPresets={strategyPresetsRemote}
          onSaveStrategyPreset={saveCurrentStrategyPreset}
          onClose={() => setSettingsOpen(false)}
          onSave={saveSettings}
        />
      )}
      {selectedToken && <TokenDetail token={selectedToken} onClose={() => setSelectedTokenId(null)} />}
      <ToastStack toasts={toasts} onDismiss={(id) => setToasts((current) => current.filter((toast) => toast.id !== id))} />
    </main>
  );
}

function LiveWalletModal({
  method,
  onMethodChange,
  walletPublicKey,
  walletBalanceSol,
  settings,
  liveStatus,
  liveAudit,
  livePositions,
  liveIntents,
  liveLedger,
  liveAction,
  liveMint,
  liveAmount,
  liveSlippage,
  livePriorityFee,
  livePool,
  activeLiveAudit,
  activeLiveIntentId,
  onClose,
  onConnectWallet,
  onAcknowledgeLive,
  onLiveActionChange,
  onLiveMintChange,
  onLiveAmountChange,
  onLiveSlippageChange,
  onLivePriorityFeeChange,
  onLivePoolChange,
  onCreateLivePreview,
  onCreateManualIntent,
  onGenerateIntents,
  onQuoteIntent,
  onCancelIntent,
  onSimulateActiveAudit,
  onSignAndSendLive
}: {
  method: LiveWalletMethod;
  onMethodChange: (method: LiveWalletMethod) => void;
  walletPublicKey: string;
  walletBalanceSol: number | null;
  settings: BotSettings;
  liveStatus: LiveStatus | null;
  liveAudit: LiveExecutionAudit[];
  livePositions: LivePosition[];
  liveIntents: LiveIntent[];
  liveLedger: LiveLedger | null;
  liveAction: "buy" | "sell";
  liveMint: string;
  liveAmount: string;
  liveSlippage: number;
  livePriorityFee: number;
  livePool: string;
  activeLiveAudit: LiveExecutionAudit | null;
  activeLiveIntentId: string;
  onClose: () => void;
  onConnectWallet: () => Promise<void>;
  onAcknowledgeLive: () => Promise<void>;
  onLiveActionChange: (action: "buy" | "sell") => void;
  onLiveMintChange: (mint: string) => void;
  onLiveAmountChange: (amount: string) => void;
  onLiveSlippageChange: (slippage: number) => void;
  onLivePriorityFeeChange: (fee: number) => void;
  onLivePoolChange: (pool: string) => void;
  onCreateLivePreview: () => Promise<void>;
  onCreateManualIntent: () => Promise<void>;
  onGenerateIntents: () => Promise<void>;
  onQuoteIntent: (intentId: string) => Promise<void>;
  onCancelIntent: (intentId: string) => Promise<void>;
  onSimulateActiveAudit: () => Promise<void>;
  onSignAndSendLive: () => Promise<void>;
}) {
  const capsSet = settings.live_max_trade_sol > 0 && settings.live_daily_loss_cap_sol > 0 && settings.live_wallet_exposure_cap_sol > 0 && settings.live_max_open_positions > 0 && settings.live_max_slippage_pct > 0 && settings.live_priority_fee_cap_sol > 0;
  const latestAudit = liveAudit[0] ?? null;
  const envEnabled = Boolean(liveStatus?.env_live_enabled);
  const quoteBlocked = !envEnabled || method !== "browser_wallet";
  const blockers = liveStatus?.blockers?.length ? liveStatus.blockers : envEnabled ? [] : ["Live environment flag is disabled"];

  return (
    <div className="overlay">
      <section className="modal live-wallet-modal">
        <div className="modal-heading">
          <div>
            <p className="eyebrow">Local live execution</p>
            <h3>Live Wallet</h3>
            <p>Manual browser-wallet buy and sell flow with quote previews, wallet approval, and audit records.</p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close live wallet">
            <X size={18} />
          </button>
        </div>

        <div className="wallet-method-grid">
          <button className={method === "browser_wallet" ? "wallet-method active" : "wallet-method"} onClick={() => onMethodChange("browser_wallet")}>
            <strong>Browser wallet</strong>
            <span>Manual approval through Phantom, Solflare, or a compatible Solana wallet.</span>
          </button>
          <button className="wallet-method disabled" disabled onClick={() => onMethodChange("local_signer_daemon")}>
            <strong>Local signer daemon</strong>
            <span>Coming later. Required for any future unattended signing capability.</span>
          </button>
        </div>

        <section className="live-wallet-step">
          <div className="section-heading">
            <div>
              <h3>Connect Wallet</h3>
              <p>CryptoARC stores the public key for status checks only. Reconnect and signing still require wallet approval.</p>
            </div>
            <Wallet size={18} />
          </div>
          <div className="button-row fit-row">
            <button className="secondary-action compact-action" onClick={onConnectWallet} disabled={method !== "browser_wallet"}>
              {walletPublicKey ? "Reconnect Browser Wallet" : "Connect Browser Wallet"}
            </button>
          </div>
          <div className="security-list wallet-info-grid">
            <span>Wallet: <strong>{shortAddress(walletPublicKey)}</strong></span>
            <span>SOL balance: <strong>{walletBalanceSol === null ? "-" : `${walletBalanceSol.toFixed(4)} SOL`}</strong></span>
            <span>Live env: <strong>{envEnabled ? "enabled" : "disabled"}</strong></span>
            <span>Caps: <strong>{capsSet ? "set" : "required"}</strong></span>
            <span>Acknowledgement: <strong>{settings.live_session_acknowledged ? "done" : "needed"}</strong></span>
            <span>Live gates: <strong>{liveStatus?.live_execution_available ? "open" : "blocked"}</strong></span>
            <span>Auto-sell: <strong>{liveStatus?.auto_sell_available ? "available" : "not for browser wallet"}</strong></span>
            <span>Latest audit: <strong>{latestAudit?.status ?? "none"}</strong></span>
          </div>
        </section>

        <section className="live-wallet-step">
          <div className="section-heading">
            <div>
              <h3>Blockers & Caps</h3>
              <p>Review the current gate state before creating a quote preview.</p>
            </div>
            <Shield size={18} />
          </div>
          <div className="mini-list compact-list">
            {blockers.length ? blockers.map((blocker) => (
              <article key={blocker}>
                <strong>{blocker}</strong>
              </article>
            )) : (
              <article>
                <strong>Manual live prerequisites are passing.</strong>
              </article>
            )}
          </div>
          <div className="button-row fit-row">
            <button className="secondary-action compact-action" onClick={onAcknowledgeLive}>
              Acknowledge Risk
            </button>
          </div>
        </section>

        <section className="live-wallet-step">
          <div className="section-heading">
            <div>
              <h3>Intent Queue</h3>
              <p>Paper-promoted, watchlist, manual, and live-position intents. Quotes expire after 30 seconds.</p>
            </div>
            <Sparkles size={18} />
          </div>
          <div className="button-row fit-row">
            <button className="secondary-action compact-action" onClick={onGenerateIntents}>Generate Intents</button>
            <button className="secondary-action compact-action" onClick={onCreateManualIntent}>Add Manual Intent</button>
          </div>
          <div className="readiness-summary">
            <span>Active: {liveStatus?.active_intent_count ?? liveIntents.length}</span>
            <span>Stale quotes: {liveStatus?.stale_quote_count ?? 0}</span>
            <span>Reconciliation: {liveStatus?.latest_reconciliation_status ?? "pending"}</span>
            <span>Realized PnL: {(liveLedger?.summary.realized_pnl_sol ?? liveStatus?.live_pnl?.realized_pnl_sol ?? 0).toFixed(6)} SOL</span>
          </div>
          <div className="mini-list compact-list">
            {liveIntents.slice(0, 10).map((intent) => (
              <article key={intent.id} className={activeLiveIntentId === intent.id ? "selected-row" : ""}>
                <strong>{intent.action} / {intent.symbol || intent.mint.slice(0, 8)} / {intent.status}</strong>
                <span>{intent.source} / score {intent.score} / expires {intent.expires_at ? new Date(intent.expires_at).toLocaleTimeString() : "-"}</span>
                <p>{intent.reason || "Live intent candidate"}</p>
                <div className="inline-actions">
                  <button className="secondary-action mini-action" onClick={() => onQuoteIntent(intent.id)} disabled={quoteBlocked || intent.status === "cancelled"}>
                    Quote
                  </button>
                  <button className="secondary-action mini-action" onClick={() => onCancelIntent(intent.id)}>
                    Cancel
                  </button>
                </div>
              </article>
            ))}
            {!liveIntents.length ? <p>No active live intents yet.</p> : null}
          </div>
        </section>

        <section className="live-wallet-step">
          <div className="section-heading">
            <div>
              <h3>Quote Preview</h3>
              <p>Quotes use PumpPortal local transactions and stay manual. Simulation warnings are recorded for review.</p>
            </div>
            <Target size={18} />
          </div>
          <div className="live-form">
            <label>
              Action
              <select value={liveAction} onChange={(event) => onLiveActionChange(event.target.value as "buy" | "sell")}>
                <option value="buy">buy</option>
                <option value="sell">sell</option>
              </select>
            </label>
            <label>
              Mint
              <input value={liveMint} onChange={(event) => onLiveMintChange(event.target.value)} placeholder="Pump.fun mint address" />
            </label>
            <label>
              Amount
              <input value={liveAmount} onChange={(event) => onLiveAmountChange(event.target.value)} placeholder={liveAction === "sell" ? "100%" : "0.001"} />
            </label>
            <SettingInput label="Slippage %" value={liveSlippage} step="0.1" onChange={(value) => onLiveSlippageChange(Number(value))} />
            <SettingInput label="Priority fee SOL" value={livePriorityFee} step="0.00001" onChange={(value) => onLivePriorityFeeChange(Number(value))} />
            <label>
              Pool
              <select value={livePool} onChange={(event) => onLivePoolChange(event.target.value)}>
                {["pump", "auto", "raydium", "pump-amm", "launchlab", "raydium-cpmm", "bonk"].map((pool) => <option key={pool} value={pool}>{pool}</option>)}
              </select>
            </label>
          </div>
          <div className="button-row fit-row">
            <button className="secondary-action compact-action" onClick={onCreateLivePreview} disabled={quoteBlocked}>
              Create Preview
            </button>
            <button className="secondary-action compact-action" onClick={onSimulateActiveAudit} disabled={!activeLiveAudit || !activeLiveAudit.quote.unsigned_transaction_base64}>
              Simulate
            </button>
            <button className="danger compact-action" onClick={onSignAndSendLive} disabled={quoteBlocked || !activeLiveAudit || !activeLiveAudit.quote.unsigned_transaction_base64}>
              Sign & Send
            </button>
          </div>
          {!envEnabled ? <p className="settings-note">Live env is disabled, so quotes and signing are blocked. Wallet connection and status checks still work.</p> : null}
          {activeLiveAudit ? (
            <div className="mini-list compact-list">
              <article>
                <strong>{activeLiveAudit.action} / {activeLiveAudit.amount} / {activeLiveAudit.status}</strong>
                <span>{activeLiveAudit.transaction_signature ? `Signature ${activeLiveAudit.transaction_signature}` : "No signature submitted yet"}</span>
                <span>Simulation: {String(activeLiveAudit.simulation?.status ?? "not run")} / Reconciliation: {activeLiveAudit.reconciliation_status ?? "pending"}</span>
                <p>{[...activeLiveAudit.warnings, ...activeLiveAudit.errors].join(" / ") || "Preview ready for wallet review."}</p>
              </article>
            </div>
          ) : null}
        </section>

        <section className="live-wallet-step">
          <div className="section-heading">
            <div>
              <h3>Wallet Positions</h3>
              <p>RPC token balances for mints touched by live audit records.</p>
            </div>
            <Database size={18} />
          </div>
          <div className="mini-list compact-list">
            {(liveLedger?.positions ?? []).slice(0, 6).map((position) => (
              <article key={position.id}>
                <strong>{position.symbol || position.mint.slice(0, 8)} / {position.status} / {position.token_balance}</strong>
                <span>Cost {position.cost_basis_sol.toFixed(6)} SOL / Realized {position.realized_pnl_sol.toFixed(6)} SOL / Recon {position.reconciliation_status}</span>
                <p>{position.mint}</p>
              </article>
            ))}
            {livePositions.slice(0, 6).map((position) => (
              <article key={position.mint}>
                <strong>{position.symbol || position.mint.slice(0, 8)} / {position.token_balance}</strong>
                <span>{position.mint}</span>
                {position.warning ? <p>{position.warning}</p> : null}
              </article>
            ))}
            {!livePositions.length && !(liveLedger?.positions.length) ? <p>No live wallet positions loaded.</p> : null}
          </div>
        </section>
      </section>
    </div>
  );
}

function PnlAreaChart({ values, animationKey }: { values: number[]; animationKey: string }) {
  const width = 260;
  const height = 92;
  const padded = values.length > 1 ? values : [0, values[0] ?? 0];
  const min = Math.min(...padded);
  const max = Math.max(...padded);
  const span = max - min || 1;
  const linePoints = padded
    .map((value, index) => {
      const x = (index / Math.max(1, padded.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const zeroY = height - ((0 - min) / span) * height;
  const positive = (values[values.length - 1] ?? 0) >= 0;
  const areaPoints = `0,${height} ${linePoints} ${width},${height}`;

  return (
    <svg className="pnl-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Live paper P&L chart">
      <line x1="0" y1={zeroY} x2={width} y2={zeroY} className="pnl-zero" />
      <polygon key={`${animationKey}-area`} points={areaPoints} className={positive ? "pnl-area positive-area" : "pnl-area negative-area"} />
      <polyline key={animationKey} points={linePoints} className={positive ? "pnl-line positive-line" : "pnl-line negative-line"} />
    </svg>
  );
}

function AuthGate({
  totpRequired,
  onAuthed,
  onError,
  error
}: {
  totpRequired: boolean;
  onAuthed: () => void;
  onError: (message: string) => void;
  error: string;
}) {
  const [password, setPassword] = React.useState("");
  const [code, setCode] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    try {
      await login(password, code);
      onError("");
      onAuthed();
    } catch (err) {
      onError(`Login failed: ${err instanceof Error ? err.message : "unknown error"}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-screen">
      <form className="auth-card" onSubmit={submit}>
        <div className="brand-mark">CA</div>
        <h1>CryptoARC v2</h1>
        <p>Enter your dashboard password{totpRequired ? " and authenticator code" : ""}.</p>
        <label>
          Password
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {totpRequired ? (
          <label>
            Authenticator code
            <input value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" />
          </label>
        ) : null}
        <button className="primary" disabled={loading}>{loading ? "Checking" : "Unlock"}</button>
        {error ? <p className="auth-error">{error}</p> : null}
      </form>
    </main>
  );
}

function ToastStack({ toasts, onDismiss }: { toasts: TradeEvent[]; onDismiss: (id: string) => void }) {
  React.useEffect(() => {
    if (!toasts.length) {
      return;
    }
    const timer = window.setTimeout(() => {
      onDismiss(toasts[toasts.length - 1].id);
    }, 5200);
    return () => window.clearTimeout(timer);
  }, [toasts, onDismiss]);

  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((toast) => (
        <button key={toast.id} className={`trade-toast ${toast.level}`} onClick={() => onDismiss(toast.id)}>
          <i aria-hidden="true" />
          <span>{toast.message.startsWith("Paper bought") ? "Buy" : "Sell"}</span>
          <strong>{toast.message}</strong>
          <small>{new Date(toast.created_at).toLocaleTimeString()}</small>
        </button>
      ))}
    </div>
  );
}

function TokenTable({
  tokens,
  onSelect,
  compact,
  watchlist,
  onToggleWatch,
  scratchThreshold
}: {
  tokens: TokenSignal[];
  onSelect: (id: string) => void;
  compact: boolean;
  watchlist: Set<string>;
  onToggleWatch: (token: TokenSignal) => void;
  scratchThreshold: number;
}) {
  if (tokens.length === 0) {
    return <div className="empty">Start the bot to generate paper launch events.</div>;
  }

  return (
    <table className={compact ? "compact-token-table" : ""}>
      <thead>
        <tr>
          <th>Token</th>
          <th>Watch</th>
          <th>Age</th>
          <th>Time</th>
          <th>Status</th>
          <th>Score</th>
          <th>Creator</th>
          <th>Amount</th>
          <th>P&L</th>
          <th>Reason</th>
        </tr>
      </thead>
      <tbody>
        {tokens.map((token) => (
          <tr key={token.id} className="clickable-row" onClick={() => onSelect(token.id)}>
            <td>
              <strong>{token.symbol}</strong>
              <span>{token.name}</span>
            </td>
            <td>
              <button
                className={watchlist.has(token.mint) ? "watch-button active" : "watch-button"}
                onClick={(event) => {
                  event.stopPropagation();
                  onToggleWatch(token);
                }}
              >
                {watchlist.has(token.mint) ? "Pinned" : "Pin"}
              </button>
            </td>
            <td title={`${token.age_seconds}s`}>{formatDuration(token.age_seconds)}</td>
            <td>{new Date(token.detected_at).toLocaleTimeString()}</td>
            <td>
              <span className={`status ${token.status}`}>{statusLabel(token.status)}</span>
            </td>
            <td>{token.score}</td>
            <td>
              {(token.creator_hold_pct ?? 0).toFixed(1)}%
              <span>{token.creator_launch_count ?? 0} launches</span>
            </td>
            <td>{token.amount_sol ? `${token.amount_sol.toFixed(3)} SOL` : "-"}</td>
            <td className={pnlClass(token.pnl_sol, scratchThreshold)}>
              {token.pnl_sol === null ? "-" : `${token.pnl_sol.toFixed(4)} SOL`}
            </td>
            <td>
              {token.reason}
              {(token.intelligence_tags ?? []).length ? <span>{token.intelligence_tags.join(" / ")}</span> : null}
              <span>{token.unrealized_pct.toFixed(2)}% unrealized / {token.price_source} / confidence {(token.price_confidence ?? 0).toFixed(2)}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BacktestDashboard({
  runs,
  latest,
  limit,
  profile,
  dateFrom,
  dateTo,
  speed,
  onLimitChange,
  onProfileChange,
  onDateFromChange,
  onDateToChange,
  onSpeedChange,
  onRun,
  onRawReplay,
  onCompare,
  onABReplay,
  onRunV3,
  onSaveExperiment,
  v3Result,
  experiments
}: {
  runs: BacktestResult[];
  latest: BacktestResult | null;
  limit: number;
  profile: BotSettings["strategy_profile"];
  dateFrom: string;
  dateTo: string;
  speed: number;
  onLimitChange: (limit: number) => void;
  onProfileChange: (profile: BotSettings["strategy_profile"]) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onSpeedChange: (speed: number) => void;
  onRun: () => Promise<void>;
  onRawReplay: () => Promise<void>;
  onCompare: () => Promise<void>;
  onABReplay: () => Promise<void>;
  onRunV3: () => Promise<void>;
  onSaveExperiment: () => Promise<void>;
  v3Result: BacktestV3Result | null;
  experiments: ExperimentRun[];
}) {
  const active = latest ?? runs[0] ?? null;
  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <div>
          <h2>Backtesting</h2>
          <p>Replay saved launches against the active paper strategy.</p>
        </div>
        <div className="button-row fit-row">
          <label className="inline-field">
            Limit
            <input value={limit} type="number" min={1} max={5000} onChange={(event) => onLimitChange(Number(event.target.value) || 1)} />
          </label>
          <label className="inline-field">
            Profile
            <select value={profile} onChange={(event) => onProfileChange(event.target.value as BotSettings["strategy_profile"])}>
              <option value="conservative">Conservative</option>
              <option value="balanced">Balanced</option>
              <option value="aggressive">Aggressive</option>
              <option value="scalper">Scalper</option>
              <option value="custom">Current custom</option>
            </select>
          </label>
          <label className="inline-field">
            From
            <input value={dateFrom} type="datetime-local" onChange={(event) => onDateFromChange(event.target.value)} />
          </label>
          <label className="inline-field">
            To
            <input value={dateTo} type="datetime-local" onChange={(event) => onDateToChange(event.target.value)} />
          </label>
          <label className="inline-field">
            Speed
            <input value={speed} type="number" min={1} max={1000} onChange={(event) => onSpeedChange(Number(event.target.value) || 1)} />
          </label>
          <button className="secondary-action compact-action" onClick={onRun}>
            <RotateCcw size={15} /> Token replay
          </button>
          <button className="secondary-action compact-action" onClick={onRawReplay}>
            <Database size={15} /> Raw replay
          </button>
          <button className="secondary-action compact-action" onClick={onCompare}>
            <Sparkles size={15} /> Compare
          </button>
          <button className="secondary-action compact-action" onClick={onABReplay}>
            <BarChart3 size={15} /> A/B replay
          </button>
          <button className="secondary-action compact-action" onClick={onRunV3}>
            <Shield size={15} /> Suite v3
          </button>
          <button className="secondary-action compact-action" onClick={onSaveExperiment}>
            <Save size={15} /> Save experiment
          </button>
        </div>
      </div>
      {v3Result ? (
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Backtesting v3</h3>
              <p>Deterministic replay, profile comparison, and walk-forward checks.</p>
            </div>
            <BarChart3 size={18} />
          </div>
          <div className="hero-metrics wide">
            <Metric label="Engine" value={v3Result.engine_version} />
            <Metric label="Tokens" value={v3Result.tokens_replayed.toString()} />
            <Metric label="Best profile" value={v3Result.best_profile || "-"} />
            <Metric label="Fingerprint" value={v3Result.determinism_fingerprint.slice(0, 10)} />
          </div>
          <div className="mini-list">
            {v3Result.runs.map((run) => (
              <article key={run.profile}>
                <strong>{run.profile}</strong>
                <span>Full {run.full.estimated_pnl_sol.toFixed(4)} SOL / validate {run.validate.win_rate_pct}% win</span>
                <p>{run.overfit_warning ? "Overfit warning: validation win rate trails training by more than 25 points." : "Walk-forward result is within the current warning band."}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}
      {active ? (
        <>
          <div className="hero-metrics wide">
            <Metric label="Replay P&L" value={`${active.estimated_pnl_sol.toFixed(4)} SOL`} />
            <Metric label="Net win" value={`${active.win_rate_pct}%`} />
            <Metric label="Gross win" value={`${active.gross_win_rate_pct ?? 0}%`} />
            <Metric label="Scratch" value={`${active.scratch_rate_pct ?? 0}%`} />
            <Metric label="Buys / skips" value={`${active.paper_buys} / ${active.skips}`} />
            <Metric label="Profit factor" value={active.profit_factor.toFixed(2)} />
            <Metric label="Drawdown" value={`${active.max_drawdown_sol.toFixed(4)} SOL`} />
            <Metric label="Best / worst" value={`${(active.best_trade_sol ?? 0).toFixed(4)} / ${(active.worst_trade_sol ?? 0).toFixed(4)}`} />
            <Metric label="Avg hold" value={formatDuration(active.avg_hold_seconds ?? 0)} />
          </div>
          {active.comparison?.length ? (
            <section className="research-card">
              <div className="section-heading">
                <div>
                  <h3>Strategy Comparison</h3>
                  <p>Same replay set across available profiles.</p>
                </div>
                <Sparkles size={18} />
              </div>
              <div className="run-list comparison-list">
                {active.comparison.map((item) => (
                  <article key={String(item.profile)}>
                    <strong>{item.profile}</strong>
                    <span>{item.buys} buys / {item.skips} skips / {item.wins ?? 0} W / {item.losses ?? 0} L / {item.scratches ?? 0} S / {Number(item.estimated_pnl_sol || 0).toFixed(4)} SOL</span>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
          <div className="research-grid">
            <section className="research-card">
              <div className="section-heading">
                <div>
                  <h3>P&L Curve</h3>
              <p>{active.profile} / {active.risk_tolerance} / {active.replay_source}</p>
                </div>
                <BarChart3 size={18} />
              </div>
              <PnlAreaChart values={active.pnl_curve.length ? active.pnl_curve : [0]} animationKey={active.id} />
            </section>
            <section className="research-card">
              <div className="section-heading">
                <div>
                  <h3>Replay Trades</h3>
                  <p>Most recent decisions from the run.</p>
                </div>
                <Target size={18} />
              </div>
              <div className="mini-list">
                {active.trades.slice(0, 14).map((trade, index) => (
                  <article key={`${trade.token_id}-${index}`}>
                    <strong>{trade.symbol}</strong>
                    <span>{trade.decision} / score {trade.score} / {Number(trade.pnl_sol || 0).toFixed(4)} SOL</span>
                    <p>{String(trade.reason || "")}</p>
                  </article>
                ))}
              </div>
            </section>
          </div>
        </>
      ) : (
        <div className="empty">Run a replay to create the first backtest record.</div>
      )}
      <section className="research-card">
        <div className="section-heading">
          <div>
            <h3>Saved Runs</h3>
            <p>Persistent backtest history.</p>
          </div>
          <Database size={18} />
        </div>
        <div className="run-list">
          {runs.map((run) => (
            <article key={run.id}>
              <strong>{new Date(run.created_at).toLocaleString()}</strong>
              <span>{run.profile} / {run.estimated_pnl_sol.toFixed(4)} SOL / {run.win_rate_pct}% win</span>
            </article>
          ))}
        </div>
      </section>
      <section className="research-card">
        <div className="section-heading">
          <div>
            <h3>Saved Experiments</h3>
            <p>Replay suites with settings versions and deterministic fingerprints.</p>
          </div>
          <Database size={18} />
        </div>
        <div className="run-list">
          {experiments.slice(0, 8).map((experiment) => (
            <article key={experiment.id}>
              <strong>{experiment.name}</strong>
              <span>{experiment.profile} / {experiment.fingerprint.slice(0, 10)} / {new Date(experiment.created_at).toLocaleString()}</span>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}

function AnalysisDashboard({
  tokens,
  trades,
  stats,
  analytics,
  suggestions,
  priceDiagnostics,
  pumpfunReport,
  safetyStatus,
  readinessStatus,
  pnlTimeframe,
  onTimeframeChange
}: {
  tokens: TokenSignal[];
  trades: TradeRecord[];
  stats: BotSnapshot["stats"];
  analytics: PerformanceAnalytics | null;
  suggestions: TuningSuggestion[];
  priceDiagnostics: PriceDiagnostics | null;
  pumpfunReport: PumpFunReport | null;
  safetyStatus: SafetyStatus | null;
  readinessStatus: ReadinessStatus | null;
  pnlTimeframe: PnlTimeframe;
  onTimeframeChange: (timeframe: PnlTimeframe) => void;
}) {
  const history = React.useMemo(() => buildPnlHistory(trades, pnlTimeframe), [trades, pnlTimeframe]);
  const closed = timeframeClosedTrades(trades, pnlTimeframe);
  const pnl = closed.reduce((total, token) => total + (token.pnl_sol || 0), 0);
  const scratchThreshold = stats.scratch_threshold_sol ?? 0.001;
  const wins = closed.filter((token) => (token.pnl_sol || 0) > scratchThreshold).length;
  const losses = closed.filter((token) => (token.pnl_sol || 0) < -scratchThreshold).length;
  const scratches = closed.filter((token) => Math.abs(token.pnl_sol || 0) <= scratchThreshold).length;
  const detected = tokens.filter((token) => token.status === "detected").length;
  const analyzing = tokens.filter((token) => token.status === "analyzing").length;
  const riskFlags = tokens.filter((token) => token.honeypot_risk || token.rug_risk).length;
  const observedTokens = tokens.filter((token) => (token.observed_price_updates || 0) > 0);
  const avgConfidence = observedTokens.length
    ? observedTokens.reduce((total, token) => total + (token.price_confidence || 0), 0) / observedTokens.length
    : 0;
  const avgHold = closed.length
    ? closed.reduce((total, token) => total + (token.hold_duration_seconds || 0), 0) / closed.length
    : 0;
  const priceSources = tokens.reduce<Record<string, number>>((counts, token) => {
    counts[token.price_source || "unknown"] = (counts[token.price_source || "unknown"] || 0) + 1;
    return counts;
  }, {});

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <div>
          <h2>Analysis</h2>
          <p>Full-size charts for paper P&L, decision quality, and source risk.</p>
        </div>
        <div className="timeframe-row analysis-timeframes">
          {pnlTimeframes.map((item) => (
            <button
              key={item.value}
              className={pnlTimeframe === item.value ? "timeframe active" : "timeframe"}
              onClick={() => onTimeframeChange(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      <div className="hero-metrics wide">
        <Metric label="Range P&L" value={`${pnl.toFixed(4)} SOL`} />
        <Metric label="Range trades" value={closed.length.toString()} />
        <Metric label="W / L / S" value={`${wins} / ${losses} / ${scratches}`} />
        <Metric label="Avg hold" value={formatDuration(avgHold)} />
        <Metric label="Price confidence" value={`${Math.round(avgConfidence * 100)}%`} />
        <Metric label="All-time P&L" value={`${stats.total_pnl_sol.toFixed(4)} SOL`} />
        <Metric label="Safety" value={safetyStatus?.entries_allowed ? "entries ok" : "guarded"} />
        <Metric label="Readiness" value={readinessStatus ? `${readinessStatus.score}% ${readinessStatus.status.replace(/_/g, " ")}` : "loading"} />
      </div>
      <div className="analysis-grid">
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Readiness Scorecard</h3>
              <p>Paper edge validation across data, source, price, replay, and performance.</p>
            </div>
            <Shield size={18} />
          </div>
          <div className="bar-list">
            <BarMetric label="Score" value={readinessStatus?.score ?? 0} max={100} />
            <BarMetric label="Closed trades" value={readinessStatus?.sample_size.closed_trades ?? 0} max={30} />
            <BarMetric label="Source events" value={readinessStatus?.sample_size.source_events ?? 0} max={100} />
          </div>
          <p className="settings-note">Status: <strong>{readinessStatus?.status.replace(/_/g, " ") ?? "loading"}</strong> / Halt: <strong>{readinessStatus?.halt_on_low_readiness ? "enabled" : "off"}</strong></p>
        </section>
        {analytics ? (
          <section className="research-card">
            <div className="section-heading">
              <div>
                <h3>Strategy Performance</h3>
                <p>Persistent trade records, not the live queue.</p>
              </div>
              <Target size={18} />
            </div>
            <div className="bar-list">
              {analytics.by_strategy.slice(0, 4).map((item) => (
                <BarMetric key={item.label} label={`${item.label} ${item.pnl_sol.toFixed(3)} SOL`} value={Math.max(0, item.win_rate_pct)} max={100} />
              ))}
            </div>
          </section>
        ) : null}
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Auto-Tuning</h3>
              <p>Suggested paper-only tuning experiments.</p>
            </div>
            <Sparkles size={18} />
          </div>
          <div className="mini-list">
            {suggestions.slice(0, 3).map((item) => (
              <article key={`${item.setting}-${item.title}`}>
                <strong>{item.title}</strong>
                <span>{item.setting}: {String(item.suggested_value ?? "review")} / {Math.round(item.confidence * 100)}%</span>
                <p>{item.reason}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="research-card analysis-card-large">
          <div className="section-heading">
            <div>
              <h3>P&L Area</h3>
              <p>Cumulative closed paper trades for the selected timeframe.</p>
            </div>
            <BarChart3 size={18} />
          </div>
          <PnlAreaChart values={history} animationKey={`analysis-${pnlTimeframe}-${history.length}-${history[history.length - 1] ?? 0}`} />
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Price Engine v3</h3>
              <p>Observed price quality and selected source mix.</p>
            </div>
            <Gauge size={18} />
          </div>
          <div className="bar-list">
            <BarMetric label="Acceptance %" value={Math.round((priceDiagnostics?.acceptance_rate ?? 0) * 100)} max={100} />
            <BarMetric label="Accepted" value={priceDiagnostics?.accepted ?? 0} max={priceDiagnostics?.observations || 1} />
            <BarMetric label="Rejected" value={priceDiagnostics?.rejected ?? 0} max={priceDiagnostics?.observations || 1} />
            <BarMetric label="Jump warnings" value={priceDiagnostics?.impossible_jump_warnings ?? 0} max={10} />
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Pump.fun Intelligence</h3>
              <p>Creator, metadata, and launch-field coverage.</p>
            </div>
            <Database size={18} />
          </div>
          <div className="mini-list">
            {(pumpfunReport?.research_notes ?? ["No Pump.fun report loaded yet."]).slice(0, 4).map((note) => (
              <article key={note}>
                <strong>{note}</strong>
                <span>{pumpfunReport ? `${pumpfunReport.tokens_analyzed} tokens / ${pumpfunReport.unique_creators} creators` : "waiting"}</span>
              </article>
            ))}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Decision Mix</h3>
              <p>Current token queue state.</p>
            </div>
            <Activity size={18} />
          </div>
          <div className="bar-list">
            <BarMetric label="Detected" value={detected} max={tokens.length || 1} />
            <BarMetric label="Analyzing" value={analyzing} max={tokens.length || 1} />
            <BarMetric label="Bought" value={tokens.filter((token) => token.status === "paper_bought" || token.status === "monitoring").length} max={tokens.length || 1} />
            <BarMetric label="Sold" value={tokens.filter((token) => token.status === "paper_sold").length} max={tokens.length || 1} />
            <BarMetric label="Skipped" value={tokens.filter((token) => token.status === "skipped").length} max={tokens.length || 1} />
            <BarMetric label="Risk flags" value={riskFlags} max={tokens.length || 1} />
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Price Sources</h3>
              <p>How paper positions are being marked.</p>
            </div>
            <Gauge size={18} />
          </div>
          <div className="bar-list">
            {Object.entries(priceSources).map(([source, count]) => (
              <BarMetric key={source} label={source} value={count} max={tokens.length || 1} />
            ))}
            <BarMetric label="Observed tokens" value={observedTokens.length} max={tokens.length || 1} />
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Trade Quality</h3>
              <p>Range outcomes and holding behavior.</p>
            </div>
            <Clock size={18} />
          </div>
          <div className="bar-list">
            <BarMetric label="Wins" value={wins} max={closed.length || 1} />
            <BarMetric label="Losses" value={losses} max={closed.length || 1} />
            <BarMetric label="Scratches" value={scratches} max={closed.length || 1} />
            <BarMetric label="Confidence %" value={Math.round(avgConfidence * 100)} max={100} />
          </div>
        </section>
      </div>
    </section>
  );
}

function BarMetric({ label, value, max }: { label: string; value: number; max: number }) {
  const width = Math.max(2, Math.round((value / max) * 100));
  return (
    <div className="bar-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <i style={{ width: `${width}%` }} />
    </div>
  );
}

function TradeReviewPage({
  trades,
  versions,
  analytics,
  suggestions,
  selectedTradeId,
  timeline,
  detail,
  labels,
  onLabelTrade,
  onSelectTrade
}: {
  trades: TradeRecord[];
  versions: SettingsVersion[];
  analytics: PerformanceAnalytics | null;
  suggestions: TuningSuggestion[];
  selectedTradeId: string | null;
  timeline: ReplayTimelineEvent[];
  detail: TradeReviewDetail | null;
  labels: TradeLabel[];
  onLabelTrade: (tokenId: string, label: string) => Promise<void>;
  onSelectTrade: (tokenId: string) => Promise<void>;
}) {
  const [filter, setFilter] = React.useState<"all" | "wins" | "losses" | "scratch">("all");
  const scratch = 0.001;
  const closed = trades.filter((trade) => trade.lifecycle_status === "closed" && trade.pnl_sol !== null);
  const visible = closed.filter((trade) => {
    const pnl = trade.pnl_sol || 0;
    if (filter === "wins") return pnl > scratch;
    if (filter === "losses") return pnl < -scratch;
    if (filter === "scratch") return Math.abs(pnl) <= scratch;
    return true;
  });
  const versionLabel = React.useMemo(() => {
    const lookup = new Map(versions.map((version) => [version.id, `${version.label || "settings"} ${new Date(version.created_at).toLocaleTimeString()}`]));
    return (id: string) => lookup.get(id) || (id ? id.slice(0, 10) : "legacy");
  }, [versions]);
  const selectedLabels = labels.filter((label) => label.token_id === selectedTradeId);

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <div>
          <h2>Trade Review</h2>
          <p>Closed paper trades, settings versions, and replay timeline.</p>
        </div>
        <div className="button-row fit-row">
          {(["all", "wins", "losses", "scratch"] as const).map((item) => (
            <button key={item} className={filter === item ? "secondary-action compact-action active" : "secondary-action compact-action"} onClick={() => setFilter(item)}>
              {item}
            </button>
          ))}
        </div>
      </div>
      <div className="hero-metrics wide">
        <Metric label="Reviewed trades" value={visible.length.toString()} />
        <Metric label="Closed P&L" value={`${visible.reduce((total, trade) => total + (trade.pnl_sol || 0), 0).toFixed(4)} SOL`} />
        <Metric label="Settings versions" value={versions.length.toString()} />
        <Metric label="All win rate" value={`${analytics?.summary.win_rate_pct ?? 0}%`} />
      </div>
      <section className="content-grid">
        <div className="token-table-wrap">
          <div className="section-heading">
            <div>
              <h3>Trade Records</h3>
              <p>Select a trade to load source, decision, price, and execution events.</p>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Strategy</th>
                <th>P&L</th>
                <th>Exit</th>
                <th>Hold</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {visible.slice(0, 120).map((trade) => (
                <tr key={trade.id} className={selectedTradeId === trade.token_id ? "selected-row" : ""} onClick={() => onSelectTrade(trade.token_id)}>
                  <td>{trade.closed_at ? new Date(trade.closed_at).toLocaleTimeString() : "-"}</td>
                  <td>{trade.strategy_profile}</td>
                  <td className={pnlClass(trade.pnl_sol)}>{(trade.pnl_sol || 0).toFixed(6)} SOL</td>
                  <td>{trade.exit_reason || "-"}</td>
                  <td>{formatDuration(trade.hold_duration_seconds || 0)}</td>
                  <td>{versionLabel(trade.settings_version_id)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <aside className="side-stack">
          <section className="research-card">
            <div className="section-heading">
              <div>
                <h3>P&L Breakdown</h3>
                <p>{detail?.trade?.id || "Select a closed trade."}</p>
              </div>
              <Wallet size={18} />
            </div>
            <div className="bar-list">
              <BarMetric label="Final P&L x1000" value={Math.round(Math.abs(detail?.pnl_breakdown.final_pnl_sol ?? 0) * 1000)} max={100} />
              <BarMetric label="Fees x10000" value={Math.round((detail?.pnl_breakdown.fees_sol ?? 0) * 10000)} max={20} />
              <BarMetric label="Slippage %" value={Math.round(detail?.pnl_breakdown.slippage_pct ?? 0)} max={20} />
              <BarMetric label="Impact %" value={Math.round(detail?.pnl_breakdown.price_impact_pct ?? 0)} max={20} />
            </div>
            {selectedTradeId ? (
              <div className="button-row fit-row">
                {["good_entry", "bad_entry", "bad_exit", "bad_price_data", "ignore_from_tuning"].map((label) => (
                  <button key={label} className="secondary-action compact-action" onClick={() => onLabelTrade(selectedTradeId, label)}>
                    {label.replace(/_/g, " ")}
                  </button>
                ))}
              </div>
            ) : null}
            <div className="tag-row">
              {selectedLabels.map((label) => <span key={label.id}>{label.label.replace(/_/g, " ")}</span>)}
            </div>
          </section>
          <section className="research-card">
            <div className="section-heading">
              <div>
                <h3>Decision Records</h3>
                <p>{detail?.decisions.length ?? 0} records for this trade.</p>
              </div>
              <Target size={18} />
            </div>
            <div className="mini-list">
              {(detail?.decisions ?? []).slice(0, 3).map((decision) => (
                <article key={decision.id}>
                  <strong>{decision.action} / score {decision.score}</strong>
                  <span>{decision.engine_version} / {decision.profile}</span>
                  <p>{decision.reason}</p>
                </article>
              ))}
            </div>
          </section>
          <section className="research-card">
            <div className="section-heading">
              <div>
                <h3>Replay Timeline</h3>
                <p>{selectedTradeId ? selectedTradeId : "Select a trade."}</p>
              </div>
              <Clock size={18} />
            </div>
            <div className="timeline-list">
              {timeline.length ? timeline.map((event, index) => (
                <article key={`${event.at}-${index}`}>
                  <span>{new Date(event.at).toLocaleTimeString()} / {event.type}</span>
                  <strong>{event.title}</strong>
                  <p>{event.detail || "-"}</p>
                </article>
              )) : <p>No timeline loaded yet.</p>}
            </div>
          </section>
          <section className="research-card">
            <div className="section-heading">
              <div>
                <h3>Suggestions</h3>
                <p>Use these as paper experiments.</p>
              </div>
              <Sparkles size={18} />
            </div>
            <div className="mini-list">
              {suggestions.map((item) => (
                <article key={`${item.title}-${item.setting}`}>
                  <strong>{item.title}</strong>
                  <span>{item.setting}: {String(item.suggested_value ?? "review")}</span>
                  <p>{item.reason}</p>
                </article>
              ))}
            </div>
          </section>
        </aside>
      </section>
    </section>
  );
}

function DataDashboard({
  summary,
  sourceEvents,
  sourceHealth,
  securityStatus,
  trades,
  priceObservations,
  strategyDecisions,
  tradeSessions,
  settingsVersions,
  dataIntegrity,
  priceDiagnostics,
  pumpfunReport,
  safetyStatus,
  readinessStatus,
  opsMonitoring,
  sourceAdapters,
  watchdogStatus,
  solanaStatus,
  liveRequests,
  liveAudit,
  auditEvents,
  onRefresh,
  onRecover,
  onReviewLiveRequest,
  onClear
}: {
  summary: DataSummary | null;
  sourceEvents: SourceEvent[];
  sourceHealth: SourceHealth | null;
  securityStatus: SecurityStatus | null;
  trades: TradeRecord[];
  priceObservations: PriceObservation[];
  strategyDecisions: StrategyDecisionRecord[];
  tradeSessions: TradeSession[];
  settingsVersions: SettingsVersion[];
  dataIntegrity: DataIntegrityReport | null;
  priceDiagnostics: PriceDiagnostics | null;
  pumpfunReport: PumpFunReport | null;
  safetyStatus: SafetyStatus | null;
  readinessStatus: ReadinessStatus | null;
  opsMonitoring: OperationalMonitoring | null;
  sourceAdapters: SourceAdapterStatus[];
  watchdogStatus: WatchdogStatus | null;
  solanaStatus: SolanaStatus | null;
  liveRequests: LiveExecutionRequest[];
  liveAudit: LiveExecutionAudit[];
  auditEvents: TradeEvent[];
  onRefresh: () => Promise<void>;
  onRecover: () => Promise<void>;
  onReviewLiveRequest: (requestId: string, status: "reviewed" | "rejected") => Promise<void>;
  onClear: (target: "tokens" | "events" | "source_events" | "backtests" | "trades" | "price_observations" | "strategy_decisions" | "trade_sessions" | "settings_versions" | "experiments" | "trade_labels" | "strategy_presets" | "live_execution_requests" | "live_sessions" | "live_execution_audits" | "live_intents" | "live_ledger_positions" | "all") => Promise<void>;
}) {
  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <div>
          <h2>Data & Safety</h2>
          <p>Source capture, audit logs, and local maintenance tools.</p>
        </div>
        <button className="secondary-action compact-action" onClick={onRefresh}>
          <Download size={15} /> Refresh
        </button>
        <button className="secondary-action compact-action" onClick={() => backupDatabase()}>
          <Save size={15} /> Backup DB
        </button>
      </div>
      <div className="hero-metrics wide">
        <Metric label="Tokens" value={(summary?.tokens ?? 0).toString()} />
        <Metric label="Audit events" value={(summary?.events ?? 0).toString()} />
        <Metric label="Source events" value={(summary?.source_events ?? 0).toString()} />
        <Metric label="Backtests" value={(summary?.backtests ?? 0).toString()} />
        <Metric label="Trades" value={(summary?.trades ?? 0).toString()} />
        <Metric label="Sessions" value={(summary?.trade_sessions ?? 0).toString()} />
        <Metric label="Prices" value={(summary?.price_observations ?? 0).toString()} />
        <Metric label="Decisions" value={(summary?.strategy_decisions ?? 0).toString()} />
        <Metric label="Settings versions" value={(summary?.settings_versions ?? settingsVersions.length).toString()} />
        <Metric label="Experiments" value={(summary?.experiments ?? 0).toString()} />
        <Metric label="Labels" value={(summary?.trade_labels ?? 0).toString()} />
        <Metric label="Integrity" value={`${dataIntegrity?.score ?? 0}%`} />
        <Metric label="Replay confidence" value={`${dataIntegrity?.replay_confidence.score ?? 0}%`} />
        <Metric label="Source health" value={`${sourceHealth?.health_score ?? 0}%`} />
        <Metric label="Safety boundary" value={securityStatus?.paper_only_boundary ? "paper only" : "live enabled"} />
        <Metric label="Readiness" value={readinessStatus ? `${readinessStatus.score}%` : "loading"} />
        <Metric label="Watchdog" value={watchdogStatus?.status ?? "unknown"} />
        <Metric label="Solana RPC" value={solanaStatus?.health ?? "unknown"} />
        <Metric label="Live requests" value={(summary?.live_execution_requests ?? liveRequests.length).toString()} />
      </div>
      <div className="maintenance-row">
        {(["tokens", "events", "source_events", "backtests", "trades", "price_observations", "strategy_decisions", "trade_sessions", "settings_versions", "experiments", "trade_labels", "strategy_presets", "live_execution_requests", "live_sessions", "live_execution_audits", "live_intents", "live_ledger_positions"] as const).map((target) => (
          <button key={target} className="danger outline" onClick={() => onClear(target)}>
            <Trash2 size={14} /> Clear {target.replace("_", " ")}
          </button>
        ))}
      </div>
      <div className="maintenance-row">
        {(["tokens", "source_events", "backtests", "trades", "price_observations", "strategy_decisions", "trade_sessions", "settings_versions", "experiments", "trade_labels", "strategy_presets", "live_execution_requests", "live_sessions", "live_execution_audits", "live_intents", "live_ledger_positions", "all"] as const).map((target) => (
          <a key={target} className="export-button" href={exportUrl(target)} target="_blank" rel="noreferrer">
            <Download size={14} /> Export {target.replace("_", " ")}
          </a>
        ))}
      </div>
      <div className="research-grid">
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Readiness Scorecard</h3>
              <p>Paper edge validation before raising risk.</p>
            </div>
            <Shield size={18} />
          </div>
          <div className="readiness-summary">
            <span className={`readiness-pill ${readinessStatus?.status ?? "loading"}`}>{readinessStatus?.status.replace(/_/g, " ") ?? "loading"}</span>
            <strong>{readinessStatus?.score ?? 0}%</strong>
            <span>Optional halt: {readinessStatus?.halt_on_low_readiness ? `on at ${readinessStatus.min_readiness_score}%` : "off"}</span>
            <span>Entries: {readinessStatus?.entries_allowed ? "allowed" : "halted"}</span>
          </div>
          <div className="mini-list">
            {(readinessStatus?.gates ?? []).filter((gate) => gate.status !== "pass").slice(0, 6).map((gate) => (
              <article key={gate.id}>
                <strong>{gate.label} / {gate.status}</strong>
                <span>{String(gate.value)} target {String(gate.target)} / weight {gate.weight}</span>
                <p>{gate.reason}</p>
              </article>
            ))}
            {readinessStatus && readinessStatus.gates.every((gate) => gate.status === "pass") ? <p>All readiness gates are passing.</p> : null}
          </div>
          <div className="mini-list compact-list">
            {(readinessStatus?.recommended_actions ?? ["Collect more paper data to build a readiness score."]).slice(0, 4).map((action) => (
              <article key={action}>
                <strong>{action}</strong>
              </article>
            ))}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Live Execution Audit</h3>
              <p>Quotes, simulations, signatures, confirmations, and warnings.</p>
            </div>
            <Database size={18} />
          </div>
          <div className="mini-list">
            {liveAudit.slice(0, 12).map((audit) => (
              <article key={audit.id}>
                <strong>{audit.action} / {audit.amount} / {audit.status}</strong>
                <span>{new Date(audit.created_at).toLocaleString()} / {audit.mint}</span>
                {audit.transaction_signature ? <a href={`https://solscan.io/tx/${audit.transaction_signature}`} target="_blank" rel="noreferrer">Solscan</a> : null}
                <p>{[...audit.warnings, ...audit.errors].join(" / ") || audit.final_status}</p>
              </article>
            ))}
            {!liveAudit.length ? <p>No live execution audit records yet.</p> : null}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Data Integrity</h3>
              <p>Replay confidence, determinism, and records that need review.</p>
            </div>
            <Shield size={18} />
          </div>
          <div className="mini-list">
            {(dataIntegrity?.issues ?? []).slice(0, 5).map((issue) => (
              <article key={`${issue.category}-${issue.message}`}>
                <strong>{issue.severity} / {issue.category}</strong>
                <span>{issue.count} finding{issue.count === 1 ? "" : "s"}</span>
                <p>{issue.message}</p>
              </article>
            ))}
            {dataIntegrity && !dataIntegrity.issues.length ? <p>No integrity issues detected.</p> : null}
            {dataIntegrity ? <p className="settings-note">Fingerprint: {dataIntegrity.determinism_fingerprint.slice(0, 18)}</p> : null}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Operational Monitoring</h3>
              <p>Backend, source, storage, warnings, and guard state.</p>
            </div>
            <Activity size={18} />
          </div>
          <div className="bar-list">
            <BarMetric label="Source health" value={opsMonitoring?.source.health_score ?? 0} max={100} />
            <BarMetric label="Warnings" value={opsMonitoring?.recent_warnings.length ?? 0} max={20} />
            <BarMetric label="Errors" value={opsMonitoring?.recent_errors.length ?? 0} max={20} />
            <BarMetric label="Open positions" value={safetyStatus?.open_positions ?? 0} max={25} />
          </div>
          <div className="source-diagnostics">
            <span>Watchdog: {watchdogStatus?.status ?? "unknown"} / tick age {watchdogStatus?.tick_age_seconds ?? "-"}s</span>
            <span>Launch age: {watchdogStatus?.launch_ingestion_age_seconds ?? "-"}s / source age {watchdogStatus?.source_event_age_seconds ?? "-"}s</span>
            <span>{watchdogStatus?.last_error || `Action: ${watchdogStatus?.recommended_action ?? "none"}`}</span>
          </div>
          <button className="secondary-action compact-action" onClick={onRecover}>
            <RotateCcw size={14} /> Recover Bot
          </button>
          <p className="settings-note">{safetyStatus?.entries_allowed ? "Risk controller allows new paper entries." : `Entries guarded: ${(safetyStatus?.stop_reasons ?? []).join(", ") || "review required"}`}</p>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Solana Read-Only</h3>
              <p>RPC health and watched wallet balance. No signer is loaded.</p>
            </div>
            <Wallet size={18} />
          </div>
          <div className="security-list">
            <span>RPC: <strong>{solanaStatus?.health ?? "unknown"}</strong></span>
            <span>Wallet: <strong>{solanaStatus?.wallet_configured ? "configured" : "not set"}</strong></span>
            <span>Balance: <strong>{solanaStatus?.balance_sol === null || solanaStatus?.balance_sol === undefined ? "-" : `${solanaStatus.balance_sol.toFixed(4)} SOL`}</strong></span>
            <span>Mode: <strong>{solanaStatus?.read_only ? "read only" : "review"}</strong></span>
          </div>
          {solanaStatus?.error ? <p className="settings-note">{solanaStatus.error}</p> : null}
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Source Adapters V2</h3>
              <p>Adapter capability and confidence contracts.</p>
            </div>
            <Database size={18} />
          </div>
          <div className="mini-list">
            {sourceAdapters.map((adapter) => (
              <article key={adapter.name}>
                <strong>{adapter.name} / {adapter.status}</strong>
                <span>{adapter.capabilities.join(", ")} / {Math.round(adapter.confidence * 100)}%</span>
              </article>
            ))}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Price Diagnostics</h3>
              <p>{priceDiagnostics?.engine_version ?? "price-v3"} source acceptance.</p>
            </div>
            <Gauge size={18} />
          </div>
          <div className="mini-list">
            {(priceDiagnostics?.sources ?? []).slice(0, 4).map((source) => (
              <article key={source.source}>
                <strong>{source.source}</strong>
                <span>{source.accepted}/{source.count} accepted / confidence {Math.round(source.avg_confidence * 100)}%</span>
              </article>
            ))}
            <p className="settings-note">Suggested minimum confidence: {priceDiagnostics?.recommended_min_confidence ?? 0.45}</p>
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Pump.fun Research</h3>
              <p>Field coverage for token intelligence.</p>
            </div>
            <Database size={18} />
          </div>
          <div className="bar-list">
            {Object.entries(pumpfunReport?.field_coverage ?? {}).map(([key, value]) => (
              <BarMetric key={key} label={key.replace("_", " ")} value={Math.round(value * 100)} max={100} />
            ))}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Source Quality</h3>
              <p>Feed health and normalization quality.</p>
            </div>
            <Activity size={18} />
          </div>
          <div className="bar-list">
            <BarMetric label="Health score" value={sourceHealth?.health_score ?? 0} max={100} />
            <BarMetric label="Normalized %" value={Math.round((sourceHealth?.normalized_ratio ?? 0) * 100)} max={100} />
            <BarMetric label="Recent normalized %" value={Math.round((sourceHealth?.recent_normalized_ratio ?? 0) * 100)} max={100} />
            <BarMetric label="Failures" value={sourceHealth?.normalization_failures ?? 0} max={Math.max(1, sourceEvents.length)} />
            <BarMetric label="Reconnects" value={sourceHealth?.reconnect_attempts ?? 0} max={10} />
            <BarMetric label="Active subs" value={sourceHealth?.active_trade_subscriptions ?? 0} max={100} />
            <BarMetric label="Dropped subs" value={sourceHealth?.dropped_trade_subscriptions ?? 0} max={100} />
          </div>
          <div className="source-diagnostics">
            <span>{sourceHealth?.status_message ?? "unknown"} / {sourceHealth?.events_per_minute ?? 0} events per minute</span>
            <span>Last event age: {sourceHealth?.last_event_age_seconds ?? "-"}s</span>
            <span>Launch / trade / status: {sourceHealth?.launch_events ?? 0} / {sourceHealth?.trade_events ?? 0} / {sourceHealth?.status_events ?? 0}</span>
            <span>Last valid token: {sourceHealth?.last_valid_token_id ?? "-"}</span>
            <span>{sourceHealth?.last_source_message ?? ""}</span>
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Security & Deployment</h3>
              <p>Runtime guardrails for local or hosted use.</p>
            </div>
            <Shield size={18} />
          </div>
          <div className="security-list">
            <span>Auth: <strong>{securityStatus?.auth_enabled ? "enabled" : "disabled"}</strong></span>
            <span>2FA: <strong>{securityStatus?.totp_enabled ? "enabled" : "disabled"}</strong></span>
            <span>Live env: <strong>{securityStatus?.live_trading_env_enabled ? "enabled" : "disabled"}</strong></span>
            <span>Paper boundary: <strong>{securityStatus?.paper_only_boundary ? "active" : "inactive"}</strong></span>
            <span>Manual live: <strong>{safetyStatus?.manual_live_ready ? "ready" : "blocked"}</strong></span>
            <span>Autonomous live: <strong>{safetyStatus?.autonomous_live_ready ? "ready" : "future"}</strong></span>
            <span>Origins: <strong>{securityStatus?.allowed_origins.join(", ") || "-"}</strong></span>
          </div>
          <p className="settings-note">{(safetyStatus?.live_blockers ?? []).join(" / ")}</p>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Manual Live Requests</h3>
              <p>Audit-only records for future manual execution workflows.</p>
            </div>
            <Wallet size={18} />
          </div>
          <div className="mini-list">
            {liveRequests.slice(0, 12).map((request) => (
              <article key={request.id}>
                <strong>{request.action} / {request.amount_sol.toFixed(4)} SOL / {request.status}</strong>
                <span>{new Date(request.created_at).toLocaleString()} / {request.mint}</span>
                {request.reviewed_at ? <span>Reviewed: {new Date(request.reviewed_at).toLocaleString()}</span> : null}
                <p>{request.reason}</p>
                {!["reviewed", "rejected"].includes(request.status) ? (
                  <div className="inline-actions">
                    <button className="secondary-action mini-action" onClick={() => onReviewLiveRequest(request.id, "reviewed")}>Mark reviewed</button>
                    <button className="secondary-action mini-action" onClick={() => onReviewLiveRequest(request.id, "rejected")}>Reject</button>
                  </div>
                ) : null}
              </article>
            ))}
            {!liveRequests.length ? <p>No manual live requests have been stored.</p> : null}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Trade Records</h3>
              <p>Durable paper trade table.</p>
            </div>
            <Target size={18} />
          </div>
          <div className="mini-list">
            {trades.slice(0, 18).map((trade) => (
              <article key={trade.id}>
                <strong>{trade.strategy_profile} / {trade.pnl_sol === null ? "-" : `${trade.pnl_sol.toFixed(4)} SOL`}</strong>
                <span>{trade.opened_at ? new Date(trade.opened_at).toLocaleString() : "-"} / {trade.exit_reason || "open"}</span>
                <p>{trade.entry_reason || "No entry reason recorded."}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Trade Sessions</h3>
              <p>Signal-to-close paper lifecycle records.</p>
            </div>
            <Clock size={18} />
          </div>
          <div className="mini-list">
            {tradeSessions.slice(0, 14).map((session) => (
              <article key={session.id}>
                <strong>{session.symbol} / {session.status} / {session.pnl_sol === null ? "-" : `${session.pnl_sol.toFixed(4)} SOL`}</strong>
                <span>{session.opened_at ? new Date(session.opened_at).toLocaleString() : "-"} / remaining {(session.remaining_fraction * 100).toFixed(0)}%</span>
                <p>{session.exit_reason || session.strategy_profile}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Price Observations</h3>
              <p>Accepted and rejected source price ticks.</p>
            </div>
            <Gauge size={18} />
          </div>
          <div className="mini-list">
            {priceObservations.slice(0, 14).map((observation) => (
              <article key={observation.id}>
                <strong>{observation.price_source} / {(observation.confidence * 100).toFixed(0)}% / {observation.accepted ? "accepted" : "rejected"}</strong>
                <span>{new Date(observation.observed_at).toLocaleTimeString()} / {observation.trade_side || "-"}</span>
                <p>{observation.reason}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Strategy Decisions</h3>
              <p>Persistent decision records with strategy versions.</p>
            </div>
            <Sparkles size={18} />
          </div>
          <div className="mini-list">
            {strategyDecisions.slice(0, 14).map((decision) => (
              <article key={decision.id}>
                <strong>{decision.action} / score {decision.score} / {decision.engine_version}</strong>
                <span>{new Date(decision.created_at).toLocaleString()} / {decision.profile}</span>
                <p>{decision.reason || decision.risk_reason}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Raw Source Events</h3>
              <p>Captured source payloads for replay and debugging.</p>
            </div>
            <Database size={18} />
          </div>
          <div className="mini-list">
            {sourceEvents.slice(0, 18).map((event) => (
              <article key={event.id}>
                <strong>{event.source} / {event.status}</strong>
                <span>{new Date(event.received_at).toLocaleTimeString()} / {event.normalized_token_id ?? "not normalized"}</span>
                <p>{event.message || JSON.stringify(event.raw_payload).slice(0, 140)}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="research-card">
          <div className="section-heading">
            <div>
              <h3>Persistent Audit Log</h3>
              <p>Recent bot, source, settings, and trade events.</p>
            </div>
            <Bell size={18} />
          </div>
          <div className="mini-list">
            {auditEvents.map((event) => (
              <article key={event.id}>
                <strong>{event.level}</strong>
                <span>{new Date(event.created_at).toLocaleString()}</span>
                <p>{event.message}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

function SettingsModal({
  settings,
  sourceStatus,
  serverStrategyPresets,
  onSaveStrategyPreset,
  onClose,
  onSave
}: {
  settings: BotSettings;
  sourceStatus: BotSnapshot["source_status"];
  serverStrategyPresets: StrategyPreset[];
  onSaveStrategyPreset: () => Promise<void>;
  onClose: () => void;
  onSave: (settings: BotSettings) => Promise<void>;
}) {
  const [draft, setDraft] = React.useState<BotSettings>(settings);
  const [activePage, setActivePage] = React.useState<SettingsPage>("source");
  const [settingsSearch, setSettingsSearch] = React.useState("");
  const [presetName, setPresetName] = React.useState("");
  const [savedPresets, setSavedPresets] = React.useState<Record<string, BotSettings>>(() => {
    try {
      return JSON.parse(window.localStorage.getItem("cryptoarc_settings_presets") || "{}");
    } catch {
      return {};
    }
  });
  const [saving, setSaving] = React.useState(false);
  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [totpSetup, setTotpSetup] = React.useState<{ secret: string; otpauth_url: string } | null>(null);
  const [totpCode, setTotpCode] = React.useState("");
  const [securityMessage, setSecurityMessage] = React.useState("");
  const dirty = JSON.stringify(draft) !== JSON.stringify(settings);
  const warnings = validateSettings(draft);

  function updateDraft<K extends keyof BotSettings>(key: K, value: BotSettings[K]) {
    setDraft((current) => ({
      ...current,
      [key]: value,
      strategy_profile: key === "strategy_profile" ? (value as BotSettings["strategy_profile"]) : "custom"
    }));
  }

  function updateNumber(key: keyof BotSettings, value: string) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return;
    }
    updateDraft(key, numeric as never);
  }

  function applyProfile(profile: BotSettings["strategy_profile"]) {
    const preset = strategyPresets[profile] ?? {};
    setDraft((current) => ({
      ...current,
      ...preset,
      strategy_profile: profile
    }));
  }

  function savePreset() {
    const name = presetName.trim();
    if (!name) {
      return;
    }
    const next = { ...savedPresets, [name]: draft };
    setSavedPresets(next);
    window.localStorage.setItem("cryptoarc_settings_presets", JSON.stringify(next));
    setPresetName("");
  }

  function applySavedPreset(name: string) {
    const preset = savedPresets[name];
    if (preset) {
      setDraft({ ...preset, strategy_profile: "custom" });
    }
  }

  async function saveDraft() {
    setSaving(true);
    try {
      await onSave(draft);
    } finally {
      setSaving(false);
    }
  }

  const navItems: Array<{ id: SettingsPage; label: string; icon: React.ReactNode }> = [
    { id: "source", label: "Source", icon: <Database size={15} /> },
    { id: "strategy", label: "Strategy", icon: <Target size={15} /> },
    { id: "risk", label: "Risk", icon: <Shield size={15} /> },
    { id: "exits", label: "Exits", icon: <Clock size={15} /> },
    { id: "simulation", label: "Sim", icon: <Gauge size={15} /> },
    { id: "advanced", label: "Advanced", icon: <SlidersHorizontal size={15} /> },
    { id: "security", label: "Security", icon: <Shield size={15} /> }
  ];
  const sectionKeywords: Record<SettingsPage, string> = {
    source: "source launch pumpportal mock token detect connection status normalized raw reconnect",
    strategy: "strategy profile trade size slippage trading speed max open positions entry buy",
    risk: "risk tolerance score creator hold daily loss honeypot rug buy velocity sell pressure metadata token age",
    exits: "exit take profit stop loss max hold time position ticks sell close trailing partial break even stalled sell pressure",
    simulation: "simulation safety launch interval paper volatility wallet cap live unlock toasts compact table solana rpc watch wallet manual live autonomous",
    advanced: "advanced source stale reconnect backtest replay raw limit health quality export maintenance fees fill delay failed price impact duplicate metadata observed subscriptions confidence first move market cap toasts solana rpc",
    security: "security password 2fa totp authenticator qr code deployment auth"
  };
  const searchQuery = settingsSearch.trim().toLowerCase();
  const pageVisible = (page: SettingsPage) => !searchQuery || sectionKeywords[page].includes(searchQuery) || page.includes(searchQuery);
  const shouldRender = (page: SettingsPage) => (searchQuery ? pageVisible(page) : activePage === page);
  const visibleNavItems = navItems.filter((item) => pageVisible(item.id));

  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <section className="modal settings-modal">
        <div className="modal-heading">
          <div>
            <h3>Strategy Settings</h3>
            <p>{dirty ? "Unsaved changes are staged locally." : "Saved settings are active in the paper bot."}</p>
          </div>
          <div className="modal-actions">
            <button className="save-button" onClick={saveDraft} disabled={!dirty || saving}>
              <Save size={16} />
              {saving ? "Saving" : "Save"}
            </button>
            <button className="icon-button" onClick={onClose} aria-label="Close settings">
              <X size={18} />
            </button>
          </div>
        </div>
        <div className="settings-layout">
          <nav className="settings-nav">
            <label className="settings-search">
              <Search size={15} />
              <input
                value={settingsSearch}
                onChange={(event) => setSettingsSearch(event.target.value)}
                placeholder="Search settings"
              />
            </label>
            {visibleNavItems.map((item) => (
              <button key={item.id} className={activePage === item.id ? "active" : ""} onClick={() => setActivePage(item.id)}>
                {item.icon}
                {item.label}
              </button>
            ))}
          </nav>
          <div className="settings-sections">
            {!visibleNavItems.length ? <div className="settings-empty">No settings matched that search.</div> : null}
            {warnings.length ? (
              <div className="settings-warning">
                <strong>{warnings.length} settings warning{warnings.length === 1 ? "" : "s"}</strong>
                {warnings.map((warning) => <span key={warning}>{warning}</span>)}
              </div>
            ) : null}
            {shouldRender("source") && (
              <SettingsSection title="Data Source" description="Choose where new token launches come from.">
                <label>
                  Launch source
                  <select value={draft.launch_source} onChange={(event) => updateDraft("launch_source", event.target.value as "mock" | "pumpportal")}>
                    <option value="mock">Mock launch stream</option>
                    <option value="pumpportal">PumpPortal new tokens</option>
                  </select>
                </label>
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.detect_new_tokens}
                    onChange={(event) => updateDraft("detect_new_tokens", event.target.checked)}
                  />
                  Detect new token launches
                </label>
                <div className="source-status-box inline">
                  <span>Source status</span>
                  <strong>{sourceStatus.source} / {sourceStatus.status}</strong>
                  <p>{sourceStatus.message}</p>
                  <p>
                    Events: {sourceStatus.events_received} normalized / {sourceStatus.raw_events_seen} raw, reconnects {sourceStatus.reconnect_attempts}
                  </p>
                </div>
              </SettingsSection>
            )}

            {shouldRender("strategy") && (
              <SettingsSection title="Strategy Profile" description="Start from a preset, then customize anything.">
                <label>
                  Strategy profile
                  <select value={draft.strategy_profile} onChange={(event) => applyProfile(event.target.value as BotSettings["strategy_profile"])}>
                    <option value="conservative">Conservative</option>
                    <option value="balanced">Balanced</option>
                    <option value="aggressive">Aggressive</option>
                    <option value="scalper">Scalper</option>
                    <option value="custom">Custom</option>
                  </select>
                </label>
                <SettingInput label="Trade size SOL" value={draft.trade_size_sol} step="0.001" onChange={(v) => updateNumber("trade_size_sol", v)} />
                <SettingInput label="Slippage tolerance %" value={draft.slippage_tolerance_pct} step="0.1" onChange={(v) => updateNumber("slippage_tolerance_pct", v)} />
                <label>
                  Trading speed
                  <select value={draft.trading_speed} onChange={(event) => updateDraft("trading_speed", event.target.value as BotSettings["trading_speed"])}>
                    <option value="slow">Slow</option>
                    <option value="normal">Normal</option>
                    <option value="fast">Fast</option>
                    <option value="turbo">Turbo</option>
                  </select>
                </label>
                <SettingInput label="Max open positions" value={draft.max_open_positions} onChange={(v) => updateNumber("max_open_positions", v)} />
                <div className="strategy-builder-box">
                  <strong>Strategy Builder Weights</strong>
                  <SettingInput label="Metadata weight" value={draft.strategy_weight_metadata} step="0.1" onChange={(v) => updateNumber("strategy_weight_metadata", v)} />
                  <SettingInput label="Momentum weight" value={draft.strategy_weight_momentum} step="0.1" onChange={(v) => updateNumber("strategy_weight_momentum", v)} />
                  <SettingInput label="Sell pressure weight" value={draft.strategy_weight_pressure} step="0.1" onChange={(v) => updateNumber("strategy_weight_pressure", v)} />
                  <SettingInput label="Creator weight" value={draft.strategy_weight_creator} step="0.1" onChange={(v) => updateNumber("strategy_weight_creator", v)} />
                </div>
                <div className="preset-box">
                  <label>
                    Saved preset
                    <select value="" onChange={(event) => applySavedPreset(event.target.value)}>
                      <option value="">Choose saved preset</option>
                      {Object.keys(savedPresets).map((name) => <option key={name} value={name}>{name}</option>)}
                    </select>
                  </label>
                  <label>
                    Preset name
                    <input value={presetName} onChange={(event) => setPresetName(event.target.value)} placeholder="My safe preset" />
                  </label>
                  <button className="secondary-action" onClick={savePreset}>Save preset</button>
                  <button className="secondary-action" onClick={onSaveStrategyPreset}>Save server preset</button>
                </div>
                <div className="mini-list">
                  {serverStrategyPresets.slice(0, 4).map((preset) => (
                    <article key={preset.id}>
                      <strong>{preset.name}</strong>
                      <span>{preset.description || "Strategy Builder preset"}</span>
                    </article>
                  ))}
                </div>
              </SettingsSection>
            )}

            {shouldRender("risk") && (
              <SettingsSection title="Risk Filters" description="Rules for rejecting suspicious or oversized opportunities.">
                <label>
                  Risk tolerance
                  <select value={draft.risk_tolerance} onChange={(event) => updateDraft("risk_tolerance", event.target.value as BotSettings["risk_tolerance"])}>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="degen">Degen</option>
                  </select>
                </label>
                <SettingInput label="Score threshold" value={draft.score_threshold} onChange={(v) => updateNumber("score_threshold", v)} />
                <SettingInput label="Max creator hold %" value={draft.max_creator_hold_pct} step="0.1" onChange={(v) => updateNumber("max_creator_hold_pct", v)} />
                <SettingInput label="Daily loss cap SOL" value={draft.daily_loss_cap_sol} step="0.001" onChange={(v) => updateNumber("daily_loss_cap_sol", v)} />
                <SettingInput label="Min buy velocity" value={draft.min_buy_velocity} step="0.01" onChange={(v) => updateNumber("min_buy_velocity", v)} />
                <SettingInput label="Max sell pressure" value={draft.max_sell_pressure} step="0.01" onChange={(v) => updateNumber("max_sell_pressure", v)} />
                <SettingInput label="Min metadata score" value={draft.min_metadata_score} step="0.01" onChange={(v) => updateNumber("min_metadata_score", v)} />
                <SettingInput label="Max token age seconds" value={draft.max_token_age_seconds} onChange={(v) => updateNumber("max_token_age_seconds", v)} />
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.max_trades_per_hour_enabled} onChange={(event) => updateDraft("max_trades_per_hour_enabled", event.target.checked)} />
                  Enable max trades per hour
                </label>
                <SettingInput label="Max trades per hour" value={draft.max_trades_per_hour} onChange={(v) => updateNumber("max_trades_per_hour", v)} />
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.cooldown_after_loss_enabled} onChange={(event) => updateDraft("cooldown_after_loss_enabled", event.target.checked)} />
                  Enable cooldown after loss
                </label>
                <SettingInput label="Cooldown after loss seconds" value={draft.cooldown_after_loss_seconds} onChange={(v) => updateNumber("cooldown_after_loss_seconds", v)} />
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.max_same_creator_buys_enabled} onChange={(event) => updateDraft("max_same_creator_buys_enabled", event.target.checked)} />
                  Enable same-creator buy cap
                </label>
                <SettingInput label="Max same-creator buys" value={draft.max_same_creator_buys} onChange={(v) => updateNumber("max_same_creator_buys", v)} />
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.filter_honeypots}
                    onChange={(event) => updateDraft("filter_honeypots", event.target.checked)}
                  />
                  Filter honeypot risk
                </label>
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.filter_rug_risk}
                    onChange={(event) => updateDraft("filter_rug_risk", event.target.checked)}
                  />
                  Filter rug-pull risk
                </label>
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.duplicate_symbol_penalty}
                    onChange={(event) => updateDraft("duplicate_symbol_penalty", event.target.checked)}
                  />
                  Penalize duplicate symbols
                </label>
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.strict_metadata_checks}
                    onChange={(event) => updateDraft("strict_metadata_checks", event.target.checked)}
                  />
                  Strict metadata checks
                </label>
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.stop_on_source_degraded} onChange={(event) => updateDraft("stop_on_source_degraded", event.target.checked)} />
                  Stop entries when source health is degraded
                </label>
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.kill_switch_enabled} onChange={(event) => updateDraft("kill_switch_enabled", event.target.checked)} />
                  Manual kill switch
                </label>
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.max_consecutive_losses_enabled} onChange={(event) => updateDraft("max_consecutive_losses_enabled", event.target.checked)} />
                  Enable consecutive-loss halt
                </label>
                <SettingInput label="Max consecutive losses" value={draft.max_consecutive_losses} onChange={(v) => updateNumber("max_consecutive_losses", v)} />
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.halt_on_low_replay_confidence} onChange={(event) => updateDraft("halt_on_low_replay_confidence", event.target.checked)} />
                  Halt on low replay confidence
                </label>
                <SettingInput label="Min replay confidence" value={draft.min_replay_confidence} onChange={(v) => updateNumber("min_replay_confidence", v)} />
              </SettingsSection>
            )}

            {shouldRender("exits") && (
              <SettingsSection title="Exits" description="Paper position exit controls.">
                <SettingInput label="Take profit %" value={draft.take_profit_pct} onChange={(v) => updateNumber("take_profit_pct", v)} />
                <SettingInput label="Stop loss %" value={draft.stop_loss_pct} onChange={(v) => updateNumber("stop_loss_pct", v)} />
                <SettingInput label="Minimum hold seconds" value={draft.minimum_hold_time_seconds} onChange={(v) => updateNumber("minimum_hold_time_seconds", v)} />
                <SettingInput label="Max hold time seconds" value={draft.max_hold_time_seconds} onChange={(v) => updateNumber("max_hold_time_seconds", v)} />
                <SettingInput label="Max position ticks" value={draft.max_position_ticks} onChange={(v) => updateNumber("max_position_ticks", v)} />
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.trailing_stop_enabled} onChange={(event) => updateDraft("trailing_stop_enabled", event.target.checked)} />
                  Enable trailing stop
                </label>
                <SettingInput label="Trailing stop %" value={draft.trailing_stop_pct} step="0.5" onChange={(v) => updateNumber("trailing_stop_pct", v)} />
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.partial_take_profit_enabled} onChange={(event) => updateDraft("partial_take_profit_enabled", event.target.checked)} />
                  Enable partial take profit
                </label>
                <SettingInput label="Partial TP trigger %" value={draft.partial_take_profit_pct} step="0.5" onChange={(v) => updateNumber("partial_take_profit_pct", v)} />
                <SettingInput label="Partial TP fraction" value={draft.partial_take_profit_fraction} step="0.05" onChange={(v) => updateNumber("partial_take_profit_fraction", v)} />
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.break_even_stop_enabled} onChange={(event) => updateDraft("break_even_stop_enabled", event.target.checked)} />
                  Enable break-even stop
                </label>
                <SettingInput label="Break-even after profit %" value={draft.break_even_after_profit_pct} step="0.5" onChange={(v) => updateNumber("break_even_after_profit_pct", v)} />
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.stalled_trade_exit_enabled} onChange={(event) => updateDraft("stalled_trade_exit_enabled", event.target.checked)} />
                  Enable stalled-trade exit
                </label>
                <SettingInput label="Stalled seconds" value={draft.stalled_trade_seconds} onChange={(v) => updateNumber("stalled_trade_seconds", v)} />
                <SettingInput label="Stalled max move %" value={draft.stalled_trade_min_move_pct} step="0.5" onChange={(v) => updateNumber("stalled_trade_min_move_pct", v)} />
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.sell_pressure_exit_enabled} onChange={(event) => updateDraft("sell_pressure_exit_enabled", event.target.checked)} />
                  Enable sell-pressure exit
                </label>
                <SettingInput label="Sell-pressure threshold" value={draft.sell_pressure_exit_threshold} step="0.01" onChange={(v) => updateNumber("sell_pressure_exit_threshold", v)} />
              </SettingsSection>
            )}

            {shouldRender("simulation") && (
              <SettingsSection title="Simulation & Safety" description="Local paper-feed tuning and future live-wallet limits.">
                <SettingInput label="Launch interval seconds" value={draft.launch_interval_seconds} step="0.5" onChange={(v) => updateNumber("launch_interval_seconds", v)} />
                <SettingInput label="Paper volatility %" value={draft.paper_price_volatility_pct} onChange={(v) => updateNumber("paper_price_volatility_pct", v)} />
                <SettingInput label="Future wallet cap SOL" value={draft.wallet_balance_cap_sol} step="0.001" onChange={(v) => updateNumber("wallet_balance_cap_sol", v)} />
                <label>
                  Solana RPC URL
                  <input value={draft.solana_rpc_url} onChange={(event) => updateDraft("solana_rpc_url", event.target.value)} placeholder="https://api.mainnet-beta.solana.com" />
                </label>
                <label>
                  Watched wallet address
                  <input value={draft.watch_wallet_address} onChange={(event) => updateDraft("watch_wallet_address", event.target.value)} placeholder="Wallet public key for balance checks" />
                </label>
                <SettingInput label="Manual live max SOL" value={draft.manual_live_max_sol} step="0.001" onChange={(v) => updateNumber("manual_live_max_sol", v)} />
                <SettingInput label="Live max trade SOL" value={draft.live_max_trade_sol} step="0.001" onChange={(v) => updateNumber("live_max_trade_sol", v)} />
                <SettingInput label="Live daily loss cap SOL" value={draft.live_daily_loss_cap_sol} step="0.001" onChange={(v) => updateNumber("live_daily_loss_cap_sol", v)} />
                <SettingInput label="Live wallet exposure cap SOL" value={draft.live_wallet_exposure_cap_sol} step="0.001" onChange={(v) => updateNumber("live_wallet_exposure_cap_sol", v)} />
                <SettingInput label="Live max open positions" value={draft.live_max_open_positions} onChange={(v) => updateNumber("live_max_open_positions", v)} />
                <SettingInput label="Live max slippage %" value={draft.live_max_slippage_pct} step="0.1" onChange={(v) => updateNumber("live_max_slippage_pct", v)} />
                <SettingInput label="Live priority fee cap SOL" value={draft.live_priority_fee_cap_sol} step="0.00001" onChange={(v) => updateNumber("live_priority_fee_cap_sol", v)} />
                <label>
                  Live signer mode
                  <select value={draft.live_signer_mode} onChange={(event) => updateDraft("live_signer_mode", event.target.value as BotSettings["live_signer_mode"])}>
                    <option value="browser_wallet">browser wallet</option>
                    <option value="local_signer_daemon">local signer daemon later</option>
                  </select>
                </label>
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.halt_on_low_readiness}
                    onChange={(event) => updateDraft("halt_on_low_readiness", event.target.checked)}
                  />
                  Halt paper entries on low readiness
                </label>
                <SettingInput label="Min readiness score" value={draft.min_readiness_score} onChange={(v) => updateNumber("min_readiness_score", v)} />
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.enable_trade_toasts}
                    onChange={(event) => updateDraft("enable_trade_toasts", event.target.checked)}
                  />
                  Enable buy/sell toasts
                </label>
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.compact_table_mode}
                    onChange={(event) => updateDraft("compact_table_mode", event.target.checked)}
                  />
                  Compact token table
                </label>
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.live_trading_enabled}
                    onChange={(event) => updateDraft("live_trading_enabled", event.target.checked)}
                  />
                  Request live trading unlock
                </label>
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.manual_live_enabled}
                    onChange={(event) => updateDraft("manual_live_enabled", event.target.checked)}
                  />
                  Enable manual live request capture
                </label>
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.autonomous_live_enabled}
                    onChange={(event) => updateDraft("autonomous_live_enabled", event.target.checked)}
                  />
                  Request autonomous live mode later
                </label>
                <p className="settings-note">Live execution remains blocked unless the backend environment explicitly enables it.</p>
              </SettingsSection>
            )}

            {shouldRender("advanced") && (
              <SettingsSection title="Advanced" description="Source health, replay limits, and heavier tuning controls.">
                <SettingInput label="Source stale seconds" value={draft.source_stale_seconds} onChange={(v) => updateNumber("source_stale_seconds", v)} />
                <SettingInput label="Source max reconnects" value={draft.source_max_reconnects} onChange={(v) => updateNumber("source_max_reconnects", v)} />
                <SettingInput label="Backtest replay limit" value={draft.backtest_replay_limit} onChange={(v) => updateNumber("backtest_replay_limit", v)} />
                <SettingInput label="Raw replay limit" value={draft.raw_replay_limit} onChange={(v) => updateNumber("raw_replay_limit", v)} />
                <SettingInput label="Max trade subscriptions" value={draft.max_trade_subscriptions} onChange={(v) => updateNumber("max_trade_subscriptions", v)} />
                <SettingInput label="Minimum price confidence" value={draft.min_price_confidence} step="0.05" onChange={(v) => updateNumber("min_price_confidence", v)} />
                <SettingInput label="Max first observed move %" value={draft.max_first_observed_move_pct} step="10" onChange={(v) => updateNumber("max_first_observed_move_pct", v)} />
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.max_rejected_price_streak_enabled} onChange={(event) => updateDraft("max_rejected_price_streak_enabled", event.target.checked)} />
                  Enable rejected price streak guard
                </label>
                <SettingInput label="Max rejected price streak" value={draft.max_rejected_price_streak} onChange={(v) => updateNumber("max_rejected_price_streak", v)} />
                <SettingInput label="Paper fill delay ticks" value={draft.paper_fill_delay_ticks} onChange={(v) => updateNumber("paper_fill_delay_ticks", v)} />
                <SettingInput label="Paper fee bps" value={draft.paper_fee_bps} step="1" onChange={(v) => updateNumber("paper_fee_bps", v)} />
                <SettingInput label="Paper price impact %" value={draft.paper_price_impact_pct} step="0.01" onChange={(v) => updateNumber("paper_price_impact_pct", v)} />
                <SettingInput label="Paper failed fill %" value={draft.paper_failed_fill_pct} step="0.1" onChange={(v) => updateNumber("paper_failed_fill_pct", v)} />
                <label className="toggle-line">
                  <input type="checkbox" checked={draft.velocity_slippage_enabled} onChange={(event) => updateDraft("velocity_slippage_enabled", event.target.checked)} />
                  Add slippage from buy velocity
                </label>
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.use_observed_prices}
                    onChange={(event) => updateDraft("use_observed_prices", event.target.checked)}
                  />
                  Use observed PumpPortal trade prices
                </label>
                <label className="toggle-line">
                  <input
                    type="checkbox"
                    checked={draft.prefer_market_cap_price}
                    onChange={(event) => updateDraft("prefer_market_cap_price", event.target.checked)}
                  />
                  Prefer market-cap normalized prices
                </label>
                <p className="settings-note">Higher replay limits can make local backtests slower on large event stores.</p>
              </SettingsSection>
            )}

            {shouldRender("security") && (
              <SettingsSection title="Security" description="Dashboard password and authenticator setup.">
                <label>
                  Current password
                  <input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} placeholder="Current dashboard password" />
                </label>
                <label>
                  New password
                  <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} placeholder="At least 8 characters" />
                </label>
                <button
                  className="secondary-action"
                  onClick={async () => {
                    try {
                      await updatePassword(currentPassword, newPassword);
                      setSecurityMessage("Password changed. Log in again with the new password.");
                    } catch (error) {
                      setSecurityMessage(`Password update failed: ${error instanceof Error ? error.message : "unknown error"}`);
                    }
                  }}
                >
                  Update password
                </button>
                <button
                  className="secondary-action"
                  onClick={async () => {
                    try {
                      setTotpSetup(await setupTotp());
                      setSecurityMessage("Scan the QR code, then enter a code to enable 2FA.");
                    } catch (error) {
                      setSecurityMessage(`2FA setup failed: ${error instanceof Error ? error.message : "unknown error"}`);
                    }
                  }}
                >
                  Start 2FA setup
                </button>
                {totpSetup ? (
                  <div className="source-status-box inline">
                    <span>Authenticator QR</span>
                    <img alt="Authenticator QR code" className="qr-code" src={`https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(totpSetup.otpauth_url)}`} />
                    <p>Secret: {totpSetup.secret}</p>
                    <label>
                      2FA code
                      <input value={totpCode} onChange={(event) => setTotpCode(event.target.value)} placeholder="123456" />
                    </label>
                    <button className="secondary-action" onClick={async () => {
                      try {
                        await verifyTotp(totpSetup.secret, totpCode);
                        setSecurityMessage("2FA enabled. Log in again with your authenticator code.");
                      } catch (error) {
                        setSecurityMessage(`2FA verification failed: ${error instanceof Error ? error.message : "unknown error"}`);
                      }
                    }}>Enable 2FA</button>
                  </div>
                ) : null}
                <button className="danger outline" onClick={async () => {
                  try {
                    await disableTotp();
                    setSecurityMessage("2FA disabled. Log in again.");
                  } catch (error) {
                    setSecurityMessage(`Disable 2FA failed: ${error instanceof Error ? error.message : "unknown error"}`);
                  }
                }}>Disable 2FA</button>
                <p className="settings-note">{securityMessage || "For deployment, keep secrets in environment variables when possible."}</p>
              </SettingsSection>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function SettingsSection({
  title,
  description,
  children
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="settings-section">
      <div className="settings-section-heading">
        <h4>{title}</h4>
        <p>{description}</p>
      </div>
      <div className="settings-grid-large">{children}</div>
    </section>
  );
}

function TokenDetail({ token, onClose }: { token: TokenSignal; onClose: () => void }) {
  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <section className="modal detail-modal">
        <div className="modal-heading">
          <div>
            <h3>{token.symbol}</h3>
            <p>{token.name}</p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close token details">
            <X size={18} />
          </button>
        </div>
        <div className="detail-grid">
          <Metric label="Score" value={token.score.toString()} />
          <Metric label="Success est." value={`${token.success_rate_pct}%`} />
          <Metric label="P&L" value={token.pnl_sol === null ? "-" : `${token.pnl_sol.toFixed(4)} SOL`} />
          <Metric label="Move" value={`${token.unrealized_pct.toFixed(2)}%`} />
          <Metric label="Ticks held" value={token.ticks_held.toString()} />
          <Metric label="Amount" value={token.amount_sol ? `${token.amount_sol.toFixed(3)} SOL` : "-"} />
          <Metric label="Creator hold" value={`${(token.creator_hold_pct ?? 0).toFixed(1)}%`} />
          <Metric label="Creator launches" value={(token.creator_launch_count ?? 0).toString()} />
          <Metric label="Honeypot risk" value={token.honeypot_risk ? "yes" : "no"} />
          <Metric label="Rug risk" value={token.rug_risk ? "yes" : "no"} />
          <Metric label="Hold time" value={`${token.hold_duration_seconds || 0}s`} />
          <Metric label="Slippage" value={`${(token.slippage_paid_pct || 0).toFixed(2)}%`} />
          <Metric label="Price impact" value={`${(token.price_impact_pct || 0).toFixed(2)}%`} />
          <Metric label="Fees" value={`${(token.fee_paid_sol || 0).toFixed(6)} SOL`} />
          <Metric label="Market cap" value={`${(token.market_cap_sol || 0).toFixed(2)} SOL`} />
          <Metric label="Observed ticks" value={(token.observed_price_updates || 0).toString()} />
          <Metric label="Price confidence" value={`${Math.round((token.price_confidence || 0) * 100)}%`} />
          <Metric label="Age" value={formatDuration(token.age_seconds || 0)} />
        </div>
        <div className="detail-block">
          <h4>Decision</h4>
          <p>{token.entry_reason || token.reason}</p>
          {token.exit_reason ? <p>Exit reason: {token.exit_reason}</p> : null}
        </div>
        <div className="detail-block">
          <h4>Position Detail</h4>
          <p>Strategy: {token.entry_strategy_profile || "-"}</p>
          <p>Best / worst unrealized: {(token.highest_unrealized_pct || 0).toFixed(2)}% / {(token.lowest_unrealized_pct || 0).toFixed(2)}%</p>
          <p>Price source: {token.price_source || "-"} / confidence {(token.price_confidence || 0).toFixed(2)}</p>
          {token.price_reject_reason ? <p>Last price rejection: {token.price_reject_reason}</p> : null}
          <p>Risk filters: {(token.entry_risk_filters || []).join(", ") || "-"}</p>
        </div>
        <div className="detail-block">
          <h4>Decision Log</h4>
          {(token.decision_log ?? []).length ? (
            <ol className="decision-log">
              {token.decision_log.map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ol>
          ) : (
            <p>No decision log recorded.</p>
          )}
        </div>
        <div className="detail-block decision-explorer">
          <h4>Decision Explorer</h4>
          <div>
            <span>1. Source</span>
            <strong>{token.mint ? "normalized launch event" : "missing source detail"}</strong>
          </div>
          <div>
            <span>2. Intelligence</span>
            <strong>{(token.intelligence_tags ?? []).join(", ") || "neutral"}</strong>
          </div>
          <div>
            <span>3. Score</span>
            <strong>{token.score} / {token.success_rate_pct}% success estimate</strong>
          </div>
          <div>
            <span>4. Risk</span>
            <strong>{token.entry_risk_filters?.join(", ") || token.reason}</strong>
          </div>
          <div>
            <span>5. Execution</span>
            <strong>
              {token.fill_failed ? "fill failed" : `${token.status} / impact ${(token.price_impact_pct || 0).toFixed(2)}% / fees ${(token.fee_paid_sol || 0).toFixed(6)} SOL`}
            </strong>
          </div>
          <div>
            <span>6. Exit</span>
            <strong>{token.exit_reason || "open or skipped"}</strong>
          </div>
        </div>
        <div className="detail-block">
          <h4>Token Intelligence</h4>
          {(token.intelligence_tags ?? []).length ? (
            <div className="tag-row">
              {token.intelligence_tags.map((tag) => (
                <span key={tag}>{tag}</span>
              ))}
            </div>
          ) : (
            <p>No intelligence tags recorded.</p>
          )}
        </div>
        <div className="detail-block">
          <h4>Score Breakdown</h4>
          {token.score_breakdown.length ? (
            <ul>
              {token.score_breakdown.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p>No scoring details recorded.</p>
          )}
        </div>
        <div className="detail-block compact-data">
          <span>Mint</span>
          <a className="external-link" href={`https://pump.fun/coin/${token.mint}`} target="_blank" rel="noreferrer">
            {token.mint}
          </a>
          <span>Creator</span>
          <a className="external-link" href={`https://solscan.io/account/${token.creator}`} target="_blank" rel="noreferrer">
            {token.creator}
          </a>
          <span>Buy velocity</span>
          <code>{token.buy_velocity.toFixed(2)}</code>
          <span>Sell pressure</span>
          <code>{token.sell_pressure.toFixed(2)}</code>
          <span>Metadata score</span>
          <code>{token.metadata_score.toFixed(2)}</code>
          <span>Initial buy</span>
          <code>{(token.initial_buy_sol || 0).toFixed(4)} SOL</code>
          <span>Bonding curve</span>
          <code>{token.bonding_curve || "-"}</code>
          <span>Metadata URI</span>
          <code>{token.metadata_uri || "-"}</code>
          <span>Price source</span>
          <code>{token.price_source} / {token.last_observed_trade_at ? new Date(token.last_observed_trade_at).toLocaleTimeString() : "no trade ticks"}</code>
        </div>
      </section>
    </div>
  );
}

function SettingInput({
  label,
  value,
  step = "1",
  onChange
}: {
  label: string;
  value: number;
  step?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      {label}
      <input type="number" min="0.001" step={step} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
