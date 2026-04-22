import React, { Suspense } from "react";
import { motion } from "framer-motion";
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
  armLiveBackend,
  clearData,
  clearHotWallet,
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
  fetchHotWalletStatus,
  fetchDataIntegrity,
  fetchMonitorPnlSummary,
  fetchOperationalMonitoring,
  fetchPerformanceAnalytics,
  fetchPriceDiagnostics,
  fetchPriceObservations,
  fetchPumpFunReport,
  applyTuningSuggestion,
  fetchReadinessStatus,
  fetchReplayTimeline,
  fetchSafetyStatus,
  fetchSolanaStatus,
  fetchSnapshot,
  fetchSourceEvents,
  fetchSourceHealth,
  fetchSecurityStatus,
  fetchSettingsVersions,
  fetchSolUsdPrice,
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
  lockHotWallet,
  logout,
  openSnapshotSocket,
  patchSettings,
  quoteLiveIntent,
  recoverLiveAudit,
  recoverUnresolvedLiveAudit,
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
  startLiveSession,
  stopBot,
  importHotWallet,
  setupTotp,
  saveStrategyPreset,
  disarmLiveBackend,
  unlockHotWallet,
  updatePassword,
  verifyTotp
} from "./api";
import type { BacktestResult, BacktestV3Result, BotSnapshot, BotSettings, DataIntegrityReport, DataSummary, ExperimentRun, HotWalletStatus, LiveExecutionAudit, LiveExecutionRequest, LiveIntent, LiveLedger, LivePosition, LiveStatus, MonitorPnlSummary, OperationalMonitoring, PerformanceAnalytics, PriceDiagnostics, PriceObservation, PumpFunReport, ReadinessStatus, ReplayTimelineEvent, SafetyStatus, SecurityStatus, SettingsVersion, SolanaStatus, SourceAdapterStatus, SourceEvent, SourceHealth, StrategyDecisionRecord, StrategyPreset, TokenSignal, TradeEvent, TradeLabel, TradeRecord, TradeReviewDetail, TradeSession, TuningSuggestion, WatchdogStatus } from "./types";
import "./styles.css";

import { AppLayout } from "./components/AppLayout";
import { Skeleton } from "./components/Skeleton";
import { MonitorPage } from "./pages/MonitorPage";
import type { DataClearTarget } from "./pages/DataPage";
import { Modal } from "./components/Modal";

const AnalysisPage = React.lazy(() => import("./pages/AnalysisPage").then((module) => ({ default: module.AnalysisPage })));
const BacktestsPage = React.lazy(() => import("./pages/BacktestsPage").then((module) => ({ default: module.BacktestsPage })));
const ReviewPage = React.lazy(() => import("./pages/ReviewPage").then((module) => ({ default: module.ReviewPage })));
const DataPage = React.lazy(() => import("./pages/DataPage").then((module) => ({ default: module.DataPage })));
const SettingsModal = React.lazy(() => import("./components/SettingsModal").then((module) => ({ default: module.SettingsModal })));
const NewTokenDetail = React.lazy(() => import("./components/TokenDetail").then((module) => ({ default: module.TokenDetail })));

type BrowserSolanaProvider = {
  isPhantom?: boolean;
  publicKey?: { toString(): string };
  connect: () => Promise<{ publicKey: { toString(): string } }>;
  disconnect?: () => Promise<void>;
  signAndSendTransaction?: (transaction: any) => Promise<{ signature: string }>;
  signTransaction?: (transaction: any) => Promise<any>;
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
    launch_source: "pumpportal",
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
    live_signer_mode: "browser_wallet",
    live_active_backend_armed: false,
    live_active_wallet_public_key: "",
    live_hot_wallet_enabled: false,
    live_hot_wallet_public_key: "",
    live_hot_wallet_label: ""
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
    source: "pumpportal",
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

function dateTimeLocalToIso(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

type PnlTimeframe = "5m" | "15m" | "1h" | "24h" | "all";
type QueueFilter = "all" | "open" | "profitable" | "losses";
type QueueSort = "newest" | "score" | "pnl" | "creator";
type WorkspacePage = "monitor" | "analysis" | "backtests" | "review" | "data";
type LiveWalletMethod = "browser_wallet" | "local_hot_wallet" | "local_signer_daemon";
type PnlWalletScope = "paper" | string;
type PnlCurrency = "SOL" | "USD";
type BotActionStatus = "starting" | "stopping" | "";

const pnlTimeframes: Array<{ label: string; value: PnlTimeframe; millis: number | null }> = [
  { label: "5m", value: "5m", millis: 5 * 60 * 1000 },
  { label: "15m", value: "15m", millis: 15 * 60 * 1000 },
  { label: "1h", value: "1h", millis: 60 * 60 * 1000 },
  { label: "24h", value: "24h", millis: 24 * 60 * 60 * 1000 },
  { label: "All", value: "all", millis: null }
];

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
  if (!ledger?.positions.length) return [0];

  const selectedFrame = pnlTimeframes.find((item) => item.value === timeframe) ?? pnlTimeframes[pnlTimeframes.length - 1];
  if (selectedFrame.millis !== null) {
    const cutoff = Date.now() - selectedFrame.millis;
    const hasRecentFill = ledger.positions.some((position) =>
      (position.fills ?? []).some((fill) => new Date(fill.created_at).getTime() >= cutoff)
    );
    if (!hasRecentFill) return [0, current];
  }

  return [0, current];
}

function simpleEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    if (left.length !== right.length) return false;
    for (let index = 0; index < left.length; index += 1) {
      if (!simpleEqual(left[index], right[index])) return false;
    }
    return true;
  }
  if (left && right && typeof left === "object" && typeof right === "object") {
    const leftEntries = Object.entries(left as Record<string, unknown>);
    const rightEntries = Object.entries(right as Record<string, unknown>);
    if (leftEntries.length !== rightEntries.length) return false;
    for (const [key, value] of leftEntries) {
      if (!simpleEqual(value, (right as Record<string, unknown>)[key])) return false;
    }
    return true;
  }
  return false;
}

function tokensEquivalent(left: TokenSignal, right: TokenSignal): boolean {
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  for (const key of keys) {
    if (key === "age_seconds") continue;
    if (!simpleEqual((left as unknown as Record<string, unknown>)[key], (right as unknown as Record<string, unknown>)[key])) {
      return false;
    }
  }
  return true;
}

function mergeMonitorTokens(current: TokenSignal[], incoming: TokenSignal[]): TokenSignal[] {
  const currentById = new Map(current.map((token) => [token.id, token]));
  const byId = new Map<string, TokenSignal>();
  for (const token of incoming) {
    const existing = currentById.get(token.id);
    byId.set(token.id, existing && tokensEquivalent(existing, token) ? existing : token);
  }
  for (const token of current) {
    if (token.status !== "skipped" && !byId.has(token.id)) byId.set(token.id, token);
  }
  const merged = [...byId.values()].sort((left, right) => new Date(right.detected_at).getTime() - new Date(left.detected_at).getTime());
  if (merged.length === current.length && merged.every((token, index) => token === current[index])) {
    return current;
  }
  return merged;
}

function mergeSnapshotState(current: BotSnapshot, incoming: BotSnapshot): BotSnapshot {
  const mergedTokens = mergeMonitorTokens(current.tokens, incoming.tokens);
  const sameEvents =
    current.events.length === incoming.events.length &&
    current.events.every((event, index) => simpleEqual(event, incoming.events[index]));
  const sameStats = simpleEqual(current.stats, incoming.stats);
  const sameSettings = simpleEqual(current.settings, incoming.settings);
  const sameSource = simpleEqual(current.source_status, incoming.source_status);
  const sameStatus = current.status === incoming.status;
  if (sameStatus && sameSettings && sameStats && sameSource && sameEvents && mergedTokens === current.tokens) {
    return current;
  }
  return {
    ...incoming,
    tokens: mergedTokens,
    events: sameEvents ? current.events : incoming.events,
    stats: sameStats ? current.stats : incoming.stats,
    settings: sameSettings ? current.settings : incoming.settings,
    source_status: sameSource ? current.source_status : incoming.source_status,
  };
}

function LazyPanelFallback({ label }: { label: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-[#10121c]/80 p-6 backdrop-blur-xl">
      <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.24em] text-[#00ffbd]">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[#00ffbd] shadow-[0_0_12px_rgba(0,255,189,0.75)]" />
        Loading {label}
      </div>
      <div className="mt-4 space-y-3">
        <Skeleton className="h-3 w-28 rounded-full" />
        <Skeleton className="h-16 rounded-xl" />
        <div className="grid grid-cols-3 gap-3">
          <Skeleton className="h-10 rounded-lg" />
          <Skeleton className="h-10 rounded-lg" />
          <Skeleton className="h-10 rounded-lg" />
        </div>
      </div>
    </div>
  );
}

async function loadSolanaWeb3() {
  return import("@solana/web3.js");
}

function App() {
  const [snapshot, setSnapshot] = React.useState<BotSnapshot>(fallbackSnapshot);
  const [apiState, setApiState] = React.useState("connecting");
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [selectedTokenId, setSelectedTokenId] = React.useState<string | null>(null);
  const [pnlTimeframe, setPnlTimeframe] = React.useState<PnlTimeframe>("all");
  const [pnlCurrency, setPnlCurrency] = React.useState<PnlCurrency>(() => (window.localStorage.getItem("cryptoarc_pnl_currency") === "USD" ? "USD" : "SOL"));
  const [solUsdPrice, setSolUsdPrice] = React.useState(0);
  const [solUsdStale, setSolUsdStale] = React.useState(false);
  const [solUsdError, setSolUsdError] = React.useState("");
  const [botActionStatus, setBotActionStatus] = React.useState<BotActionStatus>("");
  const [queueFilter, setQueueFilter] = React.useState<QueueFilter>("all");
  const [queueSort, setQueueSort] = React.useState<QueueSort>("newest");
  const [workspacePage, setWorkspacePage] = React.useState<WorkspacePage>("monitor");
  const [toasts, setToasts] = React.useState<TradeEvent[]>([]);
  const [backtestResult, setBacktestResult] = React.useState<BacktestResult | null>(null);
  const [backtests, setBacktests] = React.useState<BacktestResult[]>([]);
  const [sourceEvents, setSourceEvents] = React.useState<SourceEvent[]>([]);
  const [monitorTokens, setMonitorTokens] = React.useState<TokenSignal[]>([]);
  const [dataSummary, setDataSummary] = React.useState<DataSummary | null>(null);
  const [trades, setTrades] = React.useState<TradeRecord[]>([]);
  const [paperPnlSummary, setPaperPnlSummary] = React.useState<MonitorPnlSummary | null>(null);
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
  const [liveWalletOpenMode, setLiveWalletOpenMode] = React.useState<"setup" | "workspace">("setup");
  const [liveWalletMethod, setLiveWalletMethod] = React.useState<LiveWalletMethod>((window.localStorage.getItem("cryptoarc_live_wallet_method") as LiveWalletMethod) || "browser_wallet");
  const [hotWalletStatus, setHotWalletStatus] = React.useState<HotWalletStatus | null>(null);
  const [hotWalletPrivateKey, setHotWalletPrivateKey] = React.useState("");
  const [hotWalletPassword, setHotWalletPassword] = React.useState("");
  const [hotWalletLabel, setHotWalletLabel] = React.useState("");
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
  const [hideSkippedTokens, setHideSkippedTokens] = React.useState(() => window.localStorage.getItem("cryptoarc_hide_skipped_tokens") === "true");
  const [watchlist, setWatchlist] = React.useState<string[]>(() => JSON.parse(window.localStorage.getItem("cryptoarc_watchlist") || "[]"));
  const [apiError, setApiError] = React.useState("");
  const [pendingSuggestion, setPendingSuggestion] = React.useState<TuningSuggestion | null>(null);
  const [applyingSuggestion, setApplyingSuggestion] = React.useState(false);
  const [walletPendingRemoval, setWalletPendingRemoval] = React.useState<string | null>(null);
  const [authRequired, setAuthRequired] = React.useState(false);
  const [authed, setAuthed] = React.useState(false);
  const [totpRequired, setTotpRequired] = React.useState(false);
  const seenToastIds = React.useRef<Set<string>>(new Set());
  const readyForToasts = React.useRef(false);
  const monitorRefreshTimer = React.useRef<number | null>(null);
  const pnlRefreshInFlight = React.useRef(false);
  const analysisRefreshInFlight = React.useRef(false);
  const dataRefreshInFlight = React.useRef(false);
  const backtestsRefreshInFlight = React.useRef(false);
  const reviewRefreshInFlight = React.useRef(false);
  const strategyPresetsRefreshInFlight = React.useRef(false);
  const liveWalletCoreRefreshInFlight = React.useRef(false);
  const liveWalletDetailRefreshInFlight = React.useRef(false);

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
        setSnapshot((current) => mergeSnapshotState(current, data));
        setMonitorTokens((current) => mergeMonitorTokens(current, data.tokens));
        setApiState("connected");
      })
      .catch((error) => {
        setApiState("offline");
        setApiError(`Snapshot failed: ${error.message}`);
      });

    function connect() {
      socket = openSnapshotSocket((data) => {
        setSnapshot((current) => mergeSnapshotState(current, data));
        setMonitorTokens((current) => mergeMonitorTokens(current, data.tokens));
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
          scheduleMonitorRefresh();
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
      if (monitorRefreshTimer.current !== null) {
        window.clearTimeout(monitorRefreshTimer.current);
      }
      socket?.close();
    };
  }, []);

  const settings = snapshot.settings;
  const stats = snapshot.stats;
  const tokenSource = monitorTokens.length ? monitorTokens : snapshot.tokens;
  const monitorLoading = apiState !== "connected" && tokenSource.length === 0 && trades.length === 0;
  const pnlLoading = apiState !== "connected" && !paperPnlSummary && !liveLedger;
  const tokenLoading = apiState !== "connected" && tokenSource.length === 0;
  const selectedLivePnlWallet = pnlWalletScope === "paper" ? "" : pnlWalletScope;
  const selectedToken = tokenSource.find((token) => token.id === selectedTokenId) ?? null;
  const effectiveBotStatus = botActionStatus || snapshot.status;
  const shouldPollPnl = workspacePage === "monitor" || liveWalletOpen;
  const watchSet = React.useMemo(() => new Set(watchlist), [watchlist]);
  const paperTimeframePnl = Number((paperPnlSummary?.pnl_sol ?? stats.total_pnl_sol ?? 0).toFixed(6));
  const liveTimeframePnl = Number(((liveLedger?.summary.realized_pnl_sol ?? 0) + (liveLedger?.summary.unrealized_pnl_sol ?? 0)).toFixed(6));
  const timeframePnlSol = pnlWalletScope === "paper" ? paperTimeframePnl : liveTimeframePnl;
  const effectivePnlCurrency: PnlCurrency = pnlCurrency === "USD" && solUsdPrice > 0 ? "USD" : "SOL";
  const pnlDisplayMultiplier = effectivePnlCurrency === "USD" ? solUsdPrice : 1;
  const displayPnlValue = Number((timeframePnlSol * pnlDisplayMultiplier).toFixed(effectivePnlCurrency === "USD" ? 2 : 6));
  const paperPnlHistory = React.useMemo(() => {
    const history = paperPnlSummary?.history ?? [];
    if (history.length) return history;
    if (stats.closed_trades > 0 || stats.total_pnl_sol !== 0) {
      return [0, Number(stats.total_pnl_sol.toFixed(6))];
    }
    return [0, 0];
  }, [paperPnlSummary?.history, stats.closed_trades, stats.total_pnl_sol]);
  const livePnlHistory = React.useMemo(() => {
    const history = buildLivePnlHistory(liveLedger, pnlTimeframe);
    if (history.length) return history;
    const current = Number(((liveStatus?.live_pnl?.realized_pnl_sol ?? 0) + (liveStatus?.live_pnl?.unrealized_pnl_sol ?? 0)).toFixed(6));
    return [0, current];
  }, [liveLedger, liveStatus?.live_pnl?.realized_pnl_sol, liveStatus?.live_pnl?.unrealized_pnl_sol, pnlTimeframe]);
  const pnlHistorySol = pnlWalletScope === "paper" ? paperPnlHistory : livePnlHistory;
  const pnlHistory = React.useMemo(() => pnlHistorySol.map((value) => Number((value * pnlDisplayMultiplier).toFixed(effectivePnlCurrency === "USD" ? 2 : 6))), [pnlHistorySol, pnlDisplayMultiplier, effectivePnlCurrency]);
  const pnlCurrencyLabel = pnlCurrency === "USD"
    ? solUsdPrice > 0
      ? `USD via SOL ${solUsdStale ? "stale" : "live"} price: $${solUsdPrice.toFixed(2)}`
      : solUsdError
        ? "USD quote retrying; showing SOL"
        : "USD price loading"
    : "SOL display";
  const deferredTokenSearch = React.useDeferredValue(tokenSearch);
  const walletScopeOptions = React.useMemo(() => {
    const options = [{ value: "paper", label: "Paper Wallet" }];
    const seen = new Set<string>(["paper"]);
    const candidates = [
      walletPublicKey,
      ...liveWallets,
      hotWalletStatus?.wallet_public_key || "",
      liveStatus?.signer?.wallet_public_key || "",
      snapshot.settings.live_active_wallet_public_key || "",
    ];
    for (const wallet of candidates) {
      const clean = wallet.trim();
      if (!clean || seen.has(clean)) continue;
      seen.add(clean);
      options.push({ value: clean, label: `Live ${shortAddress(clean)}` });
    }
    return options;
  }, [hotWalletStatus?.wallet_public_key, liveStatus?.signer?.wallet_public_key, liveWallets, snapshot.settings.live_active_wallet_public_key, walletPublicKey]);
  const filteredTokens = React.useMemo(() => {
    let tokens = tokenSource;
    const query = deferredTokenSearch.trim().toLowerCase();
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
    if (hideSkippedTokens) {
      tokens = tokens.filter((token) => token.status !== "skipped");
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
  }, [deferredTokenSearch, queueFilter, queueSort, snapshot.stats.scratch_threshold_sol, tokenSource, showWatchlistOnly, hideSkippedTokens, watchSet]);

  React.useEffect(() => {
    if (pnlWalletScope !== "live") return;
    const replacement = walletPublicKey || liveWallets[0] || "paper";
    setPnlWalletScope(replacement);
    window.localStorage.setItem("cryptoarc_pnl_wallet_scope", replacement);
  }, [liveWallets, pnlWalletScope, walletPublicKey]);

  const toggleWatchlist = React.useCallback((token: TokenSignal) => {
    const next = watchSet.has(token.mint) ? watchlist.filter((mint) => mint !== token.mint) : [...watchlist, token.mint];
    setWatchlist(next);
    window.localStorage.setItem("cryptoarc_watchlist", JSON.stringify(next));
  }, [watchSet, watchlist]);

  const updatePnlWalletScope = React.useCallback((scope: PnlWalletScope) => {
    setPnlWalletScope(scope);
    window.localStorage.setItem("cryptoarc_pnl_wallet_scope", scope);
  }, []);

  const openAddWalletFlow = React.useCallback(() => {
    setLiveWalletOpenMode("setup");
    setLiveWalletOpen(true);
  }, []);

  const openManageWalletFlow = React.useCallback(() => {
    setLiveWalletOpenMode("workspace");
    setLiveWalletOpen(true);
  }, []);

  const removeTrackedWallet = React.useCallback((wallet: string) => {
    const nextWallets = liveWallets.filter((entry) => entry !== wallet);
    setLiveWallets(nextWallets);
    window.localStorage.setItem("cryptoarc_live_wallets", JSON.stringify(nextWallets));
    if (walletPublicKey === wallet) {
      setWalletPublicKey("");
      window.localStorage.removeItem("cryptoarc_wallet_public_key");
      setWalletBalanceSol(null);
    }
    if (pnlWalletScope === wallet) {
      updatePnlWalletScope("paper");
    }
  }, [liveWallets, pnlWalletScope, updatePnlWalletScope, walletPublicKey]);

  const updateHideSkippedTokens = React.useCallback((value: boolean) => {
    setHideSkippedTokens(value);
    window.localStorage.setItem("cryptoarc_hide_skipped_tokens", String(value));
  }, []);

  const togglePnlCurrency = React.useCallback(() => {
    setPnlCurrency((current) => {
      const next = current === "SOL" ? "USD" : "SOL";
      window.localStorage.setItem("cryptoarc_pnl_currency", next);
      if (next === "USD" && solUsdPrice <= 0) {
        refreshSolUsdPrice().catch(() => undefined);
      }
      return next;
    });
  }, [solUsdPrice]);

  async function refreshSolUsdPrice() {
    try {
      const quote = await fetchSolUsdPrice();
      setSolUsdPrice(Number(quote.price || 0));
      setSolUsdStale(Boolean(quote.stale));
      setSolUsdError(quote.error || "");
      if (!quote.error && Number(quote.price || 0) > 0) {
        setApiError((current) => current.startsWith("SOL/USD quote") ? "" : current);
      }
    } catch (error) {
      setSolUsdError(error instanceof Error ? error.message : "unknown error");
    }
  }

  async function handleStartBot() {
    setBotActionStatus("starting");
    try {
      setSnapshot(await startBot());
      setApiError("");
    } catch (error) {
      setApiError(`Start failed: ${error instanceof Error ? error.message : "unknown error"}`);
    } finally {
      setBotActionStatus("");
    }
  }

  async function handleStopBot() {
    setBotActionStatus("stopping");
    try {
      setSnapshot(await stopBot());
      setApiError("");
      refreshPnlData().catch(() => undefined);
      if (liveWalletOpen) {
        refreshLiveWalletCoreData().catch(() => undefined);
      }
      if (workspacePage !== "monitor") {
        refreshWorkspaceData(workspacePage).catch(() => undefined);
      }
    } catch (error) {
      setApiError(`Stop failed: ${error instanceof Error ? error.message : "unknown error"}`);
    } finally {
      setBotActionStatus("");
    }
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

  const refreshConnectedWalletBalance = React.useCallback(async (publicKey = walletPublicKey) => {
    if (!publicKey) {
      setWalletBalanceSol(null);
      return;
    }
    try {
      const { Connection, PublicKey } = await loadSolanaWeb3();
      const connection = new Connection(snapshot.settings.solana_rpc_url, "confirmed");
      const lamports = await connection.getBalance(new PublicKey(publicKey));
      setWalletBalanceSol(lamports / 1_000_000_000);
    } catch {
      setWalletBalanceSol(null);
    }
  }, [snapshot.settings.solana_rpc_url, walletPublicKey]);

  React.useEffect(() => {
    window.localStorage.setItem("cryptoarc_live_wallet_method", liveWalletMethod);
  }, [liveWalletMethod]);

  const refreshLiveWalletCoreData = React.useCallback(async (publicKey = walletPublicKey) => {
    if (!publicKey && !liveWalletOpen) return;
    if (liveWalletCoreRefreshInFlight.current) return;
    liveWalletCoreRefreshInFlight.current = true;
    try {
      const hotStatusPromise = fetchHotWalletStatus().catch(() => null);
      const requestedWallet = liveWalletMethod === "local_hot_wallet"
        ? hotWalletStatus?.wallet_public_key || snapshot.settings.live_hot_wallet_public_key || publicKey
        : publicKey;
      const status = await fetchLiveStatus(requestedWallet, liveWalletMethod);
      const hotStatus = await hotStatusPromise;
      const resolvedWallet = String(status.signer?.wallet_public_key || requestedWallet || "");
      const positions = resolvedWallet ? await fetchLivePositions(resolvedWallet) : [];
      setLiveStatus(status);
      setHotWalletStatus(hotStatus);
      setLivePositions(positions);
      if (resolvedWallet) {
        refreshConnectedWalletBalance(resolvedWallet).catch(() => undefined);
      }
    } finally {
      liveWalletCoreRefreshInFlight.current = false;
    }
  }, [hotWalletStatus?.wallet_public_key, liveWalletMethod, liveWalletOpen, refreshConnectedWalletBalance, snapshot.settings.live_hot_wallet_public_key, walletPublicKey]);

  const refreshLiveWalletDetailData = React.useCallback(async (force = false) => {
    if (!force && !liveWalletOpen) return;
    if (liveWalletDetailRefreshInFlight.current) return;
    liveWalletDetailRefreshInFlight.current = true;
    try {
      const [audits, intents, ledger] = await Promise.all([
        fetchLiveAudit(),
        fetchLiveIntents(),
        selectedLivePnlWallet ? fetchLiveLedger(selectedLivePnlWallet) : Promise.resolve(emptyLiveLedger())
      ]);
      setLiveAudit(audits);
      setLiveIntents(intents);
      setLiveLedger(ledger);
    } finally {
      liveWalletDetailRefreshInFlight.current = false;
    }
  }, [liveWalletOpen, selectedLivePnlWallet]);

  const refreshAnalysisData = React.useCallback(async () => {
    if (analysisRefreshInFlight.current) return;
    analysisRefreshInFlight.current = true;
    try {
      const [analytics, suggestions, integrity, price, pumpfun, safety, readiness] = await Promise.all([
        fetchPerformanceAnalytics(),
        fetchTuningSuggestions(),
        fetchDataIntegrity(),
        fetchPriceDiagnostics(),
        fetchPumpFunReport(),
        fetchSafetyStatus(),
        fetchReadinessStatus()
      ]);
      setPerformanceAnalytics(analytics);
      setTuningSuggestions(suggestions);
      setDataIntegrity(integrity);
      setPriceDiagnostics(price);
      setPumpfunReport(pumpfun);
      setSafetyStatus(safety);
      setReadinessStatus(readiness);
    } finally {
      analysisRefreshInFlight.current = false;
    }
  }, []);

  const refreshStrategyPresetData = React.useCallback(async () => {
    if (strategyPresetsRefreshInFlight.current) return;
    strategyPresetsRefreshInFlight.current = true;
    try {
      setStrategyPresetsRemote(await fetchStrategyPresets());
    } finally {
      strategyPresetsRefreshInFlight.current = false;
    }
  }, []);

  const refreshBacktestsData = React.useCallback(async () => {
    if (backtestsRefreshInFlight.current) return;
    backtestsRefreshInFlight.current = true;
    try {
      const [runs, experimentRows] = await Promise.all([
        fetchBacktests(),
        fetchExperiments()
      ]);
      setBacktests(runs);
      setExperiments(experimentRows);
    } finally {
      backtestsRefreshInFlight.current = false;
    }
  }, []);

  const refreshReviewData = React.useCallback(async () => {
    if (reviewRefreshInFlight.current) return;
    reviewRefreshInFlight.current = true;
    try {
      const [events, observations, decisions, sessions, versions, labels, analytics, suggestions] = await Promise.all([
        fetchSourceEvents(),
        fetchPriceObservations(),
        fetchStrategyDecisions(),
        fetchTradeSessions(),
        fetchSettingsVersions(),
        fetchTradeLabels(),
        fetchPerformanceAnalytics(),
        fetchTuningSuggestions()
      ]);
      setSourceEvents(events);
      setPriceObservations(observations);
      setStrategyDecisions(decisions);
      setTradeSessions(sessions);
      setSettingsVersions(versions);
      setTradeLabels(labels);
      setPerformanceAnalytics(analytics);
      setTuningSuggestions(suggestions);
    } finally {
      reviewRefreshInFlight.current = false;
    }
  }, []);

  const refreshDataPageData = React.useCallback(async () => {
    if (dataRefreshInFlight.current) return;
    dataRefreshInFlight.current = true;
    try {
      const [summary, health, security, integrity, price, pumpfun, safety, readiness, ops, adapters, watchdog, solana, liveRows, audits, events, observations, decisions, sessions, versions, tradeRows] = await Promise.all([
        fetchDataSummary(),
        fetchSourceHealth(),
        fetchSecurityStatus(),
        fetchDataIntegrity(),
        fetchPriceDiagnostics(),
        fetchPumpFunReport(),
        fetchSafetyStatus(),
        fetchReadinessStatus(),
        fetchOperationalMonitoring(),
        fetchSourceAdapters(),
        fetchWatchdogStatus(),
        fetchSolanaStatus(),
        fetchLiveRequests(),
        fetchLiveAudit(),
        fetchSourceEvents(),
        fetchPriceObservations(),
        fetchStrategyDecisions(),
        fetchTradeSessions(),
        fetchSettingsVersions(),
        fetchTrades()
      ]);
      setDataSummary(summary);
      setSourceHealth(health);
      setSecurityStatus(security);
      setDataIntegrity(integrity);
      setPriceDiagnostics(price);
      setPumpfunReport(pumpfun);
      setSafetyStatus(safety);
      setReadinessStatus(readiness);
      setOpsMonitoring(ops);
      setSourceAdapters(adapters);
      setWatchdogStatus(watchdog);
      setSolanaStatus(solana);
      setLiveRequests(liveRows);
      setLiveAudit(audits);
      setSourceEvents(events);
      setTrades(tradeRows);
      setPriceObservations(observations);
      setStrategyDecisions(decisions);
      setTradeSessions(sessions);
      setSettingsVersions(versions);
    } finally {
      dataRefreshInFlight.current = false;
    }
  }, []);

  const refreshWorkspaceData = React.useCallback(async (page = workspacePage) => {
    if (page === "analysis") {
      await refreshAnalysisData();
      return;
    }
    if (page === "backtests") {
      await refreshBacktestsData();
      return;
    }
    if (page === "review") {
      await refreshReviewData();
      return;
    }
    if (page === "data") {
      await refreshDataPageData();
    }
  }, [refreshAnalysisData, refreshBacktestsData, refreshDataPageData, refreshReviewData, workspacePage]);

  const refreshAfterMutation = React.useCallback(async (options?: { includeLiveWalletDetail?: boolean; includeSnapshot?: boolean; page?: WorkspacePage }) => {
    const page = options?.page ?? workspacePage;
    await Promise.all([
      refreshPnlData(),
      liveWalletOpen ? refreshLiveWalletCoreData() : Promise.resolve(),
      options?.includeLiveWalletDetail && liveWalletOpen ? refreshLiveWalletDetailData(true) : Promise.resolve(),
      page !== "monitor" ? refreshWorkspaceData(page) : Promise.resolve(),
      options?.includeSnapshot ? fetchSnapshot().then((data) => setSnapshot((current) => mergeSnapshotState(current, data))) : Promise.resolve()
    ]);
    refreshConnectedWalletBalance().catch(() => undefined);
  }, [liveWalletOpen, refreshConnectedWalletBalance, refreshLiveWalletCoreData, refreshLiveWalletDetailData, refreshPnlData, refreshWorkspaceData, workspacePage]);

  function scheduleMonitorRefresh() {
    if (monitorRefreshTimer.current !== null) return;
    monitorRefreshTimer.current = window.setTimeout(() => {
      monitorRefreshTimer.current = null;
      refreshPnlData().catch(() => undefined);
      if (liveWalletOpen) {
        refreshLiveWalletCoreData().catch(() => undefined);
      }
      if (workspacePage !== "monitor") {
        refreshWorkspaceData(workspacePage).catch(() => undefined);
      }
    }, 500);
  }

  function handleApplyTuningSuggestion(suggestion: TuningSuggestion) {
    if (suggestion.suggested_value === undefined) return Promise.resolve();
    setPendingSuggestion(suggestion);
    return Promise.resolve();
  }

  async function confirmApplyTuningSuggestion() {
    if (!pendingSuggestion || pendingSuggestion.suggested_value === undefined) return;
    setApplyingSuggestion(true);
    try {
      const result = await applyTuningSuggestion(pendingSuggestion.setting, pendingSuggestion.suggested_value);
      setSnapshot(result.snapshot);
      await refreshAfterMutation({ page: workspacePage });
      setPendingSuggestion(null);
      setApiError("");
    } catch (error) {
      setApiError(`Suggestion apply failed: ${error instanceof Error ? error.message : "unknown error"}`);
    } finally {
      setApplyingSuggestion(false);
    }
  }

  async function refreshPnlData() {
    if (pnlRefreshInFlight.current) return;
    pnlRefreshInFlight.current = true;
    try {
      if (selectedLivePnlWallet) {
        setLiveLedger(await fetchLiveLedger(selectedLivePnlWallet));
        return;
      }
      setPaperPnlSummary(await fetchMonitorPnlSummary(pnlTimeframe));
    } finally {
      pnlRefreshInFlight.current = false;
    }
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

  async function clearProjectData(target: DataClearTarget) {
    try {
      const summary = await clearData(target);
      setDataSummary(summary);
      await refreshAfterMutation({ includeSnapshot: true, page: workspacePage });
    } catch (error) {
      setApiError(`Clear failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function reviewManualLiveRequest(requestId: string, status: "reviewed" | "rejected") {
    try {
      const updated = await reviewLiveRequest(requestId, status, "Dashboard audit review");
      setLiveRequests((current) => current.map((request) => request.id === requestId ? updated : request));
      await refreshAfterMutation({ page: workspacePage });
    } catch (error) {
      setApiError(`Live request review failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function connectBrowserWallet(): Promise<boolean> {
    try {
      if (!window.solana) {
        setApiError("Browser wallet not found. Install or unlock Phantom/Solflare and refresh.");
        return false;
      }
      const result = await window.solana.connect();
      const publicKey = result.publicKey.toString();
      setWalletPublicKey(publicKey);
      window.localStorage.setItem("cryptoarc_wallet_public_key", publicKey);
      const nextWallets = [publicKey, ...liveWallets.filter((wallet) => wallet !== publicKey)].slice(0, 8);
      setLiveWallets(nextWallets);
      window.localStorage.setItem("cryptoarc_live_wallets", JSON.stringify(nextWallets));
      await Promise.all([
        refreshLiveWalletCoreData(publicKey),
        liveWalletOpen ? refreshLiveWalletDetailData(true) : Promise.resolve()
      ]);
      setApiError("");
      return true;
    } catch (error) {
      setApiError(`Wallet connect failed: ${error instanceof Error ? error.message : "unknown error"}`);
      return false;
    }
  }

  async function acknowledgeLiveRisk(): Promise<boolean> {
    try {
      await acknowledgeLiveSession();
      const updated = await fetchSnapshot();
      setSnapshot(updated);
      await refreshLiveWalletCoreData();
      return true;
    } catch (error) {
      setApiError(`Live acknowledgement failed: ${error instanceof Error ? error.message : "unknown error"}`);
      return false;
    }
  }

  async function applyLiveQuickFix(kind: "enable_env" | "configure_caps" | "disable_kill_switch"): Promise<boolean> {
    try {
      const patch: Record<string, number | boolean | string> = {};
      if (kind === "enable_env") {
        patch.live_trading_enabled = true;
        patch.manual_live_enabled = true;
      }
      if (kind === "configure_caps") {
        patch.manual_live_enabled = true;
        patch.live_max_trade_sol = settings.live_max_trade_sol > 0 ? settings.live_max_trade_sol : 0.01;
        patch.live_daily_loss_cap_sol = settings.live_daily_loss_cap_sol > 0 ? settings.live_daily_loss_cap_sol : 0.05;
        patch.live_wallet_exposure_cap_sol = settings.live_wallet_exposure_cap_sol > 0 ? settings.live_wallet_exposure_cap_sol : 0.1;
        patch.live_max_open_positions = settings.live_max_open_positions > 0 ? settings.live_max_open_positions : 2;
        patch.live_max_slippage_pct = settings.live_max_slippage_pct > 0 ? settings.live_max_slippage_pct : 5;
        patch.live_priority_fee_cap_sol = settings.live_priority_fee_cap_sol > 0 ? settings.live_priority_fee_cap_sol : 0.0001;
      }
      if (kind === "disable_kill_switch") {
        patch.kill_switch_enabled = false;
      }
      const updated = await patchSettings(patch);
      setSnapshot(updated);
      await refreshLiveExecutionSurfaces();
      setApiError("");
      return true;
    } catch (error) {
      setApiError(`Live quick fix failed: ${error instanceof Error ? error.message : "unknown error"}`);
      return false;
    }
  }

  function resolvedLiveWallet(method = liveWalletMethod): string {
    if (method === "local_hot_wallet") {
      return hotWalletStatus?.wallet_public_key || snapshot.settings.live_hot_wallet_public_key || "";
    }
    if (method === "local_signer_daemon") {
      return liveStatus?.signer?.wallet_public_key || snapshot.settings.live_active_wallet_public_key || "";
    }
    return walletPublicKey;
  }

  async function importEncryptedHotWallet(): Promise<boolean> {
    try {
      const status = await importHotWallet(hotWalletPrivateKey, hotWalletPassword, hotWalletLabel);
      setHotWalletStatus(status);
      setLiveWalletMethod("local_hot_wallet");
      setHotWalletPrivateKey("");
      await Promise.all([refreshLiveWalletCoreData(status.wallet_public_key), refreshLiveWalletDetailData(true)]);
      setApiError("");
      return true;
    } catch (error) {
      setApiError(`Hot wallet import failed: ${error instanceof Error ? error.message : "unknown error"}`);
      return false;
    }
  }

  async function unlockEncryptedHotWallet(): Promise<boolean> {
    try {
      const status = await unlockHotWallet(hotWalletPassword);
      setHotWalletStatus(status);
      setLiveWalletMethod("local_hot_wallet");
      await refreshLiveWalletCoreData(status.wallet_public_key);
      setApiError("");
      return true;
    } catch (error) {
      setApiError(`Hot wallet unlock failed: ${error instanceof Error ? error.message : "unknown error"}`);
      return false;
    }
  }

  async function lockEncryptedHotWallet(): Promise<boolean> {
    try {
      const status = await lockHotWallet();
      setHotWalletStatus(status);
      await refreshLiveWalletCoreData();
      setApiError("");
      return true;
    } catch (error) {
      setApiError(`Hot wallet lock failed: ${error instanceof Error ? error.message : "unknown error"}`);
      return false;
    }
  }

  async function clearEncryptedHotWallet(): Promise<boolean> {
    try {
      const status = await clearHotWallet();
      setHotWalletStatus(status);
      await refreshLiveWalletCoreData();
      setApiError("");
      return true;
    } catch (error) {
      setApiError(`Hot wallet clear failed: ${error instanceof Error ? error.message : "unknown error"}`);
      return false;
    }
  }

  async function armSelectedLiveBackend(): Promise<boolean> {
    try {
      const wallet = resolvedLiveWallet();
      await startLiveSession(wallet, liveWalletMethod);
      await armLiveBackend(wallet, liveWalletMethod);
      const updated = await fetchSnapshot();
      setSnapshot(updated);
      await refreshLiveExecutionSurfaces();
      setApiError("");
      return true;
    } catch (error) {
      setApiError(`Live backend arm failed: ${error instanceof Error ? error.message : "unknown error"}`);
      return false;
    }
  }

  async function disarmSelectedLiveBackend(): Promise<boolean> {
    try {
      await disarmLiveBackend();
      const updated = await fetchSnapshot();
      setSnapshot(updated);
      await refreshLiveExecutionSurfaces();
      setApiError("");
      return true;
    } catch (error) {
      setApiError(`Live backend disarm failed: ${error instanceof Error ? error.message : "unknown error"}`);
      return false;
    }
  }

  async function createLivePreview() {
    try {
      const requestWallet = resolvedLiveWallet();
      const audit = await createLiveQuote({
        action: liveAction,
        mint: liveMint,
        amount: liveAmount,
        denominated_in_sol: liveAction === "buy",
        slippage_pct: liveSlippage,
        priority_fee_sol: livePriorityFee,
        pool: livePool,
        wallet_public_key: requestWallet,
        signer_mode: liveWalletMethod
      });
      const simulated = liveWalletMethod === "browser_wallet"
        ? await recordLiveSimulation(audit.id, false, "Browser wallet simulation must be reviewed before signing.")
        : audit;
      setActiveLiveAudit(simulated);
      setLiveAudit((current) => [simulated, ...current.filter((item) => item.id !== simulated.id)]);
      setApiError("");
    } catch (error) {
      setApiError(`Live quote failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function createManualIntent() {
    try {
      const requestWallet = resolvedLiveWallet();
      const intent = await createLiveIntent({
        action: liveAction,
        mint: liveMint,
        amount: liveAmount,
        denominated_in_sol: liveAction === "buy",
        wallet_public_key: requestWallet,
        signer_mode: liveWalletMethod,
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
      const intents = await generateLiveIntents(resolvedLiveWallet(), liveWalletMethod, watchlist);
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
      refreshLiveWalletDetailData(true).catch(() => undefined);
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
      if (liveWalletMethod !== "browser_wallet") {
        const updated = await recordLiveSimulation(activeLiveAudit.id, true, "", "", { backend: liveWalletMethod, note: "Backend execution path performs its own simulation and submission checks." });
        setActiveLiveAudit(updated);
        setLiveAudit((current) => [updated, ...current.filter((item) => item.id !== updated.id)]);
        return;
      }
      const encoded = String(activeLiveAudit.quote.unsigned_transaction_base64 || "");
      if (!encoded) throw new Error("No unsigned transaction is available");
      const { Connection, VersionedTransaction } = await loadSolanaWeb3();
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
      refreshLiveWalletDetailData(true).catch(() => undefined);
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
      if (liveWalletMethod !== "browser_wallet") {
        const executed = await submitLiveAudit(activeLiveAudit.id, "");
        setActiveLiveAudit(executed);
        setLiveAudit((current) => [executed, ...current.filter((item) => item.id !== executed.id)]);
        await refreshLiveWalletCoreData();
        await refreshLiveWalletDetailData(true);
        return;
      }
      if (!window.solana) throw new Error("Browser wallet not connected");
      const encoded = String(activeLiveAudit.quote.unsigned_transaction_base64 || "");
      if (!encoded) throw new Error("No unsigned transaction is available");
      const { Connection, VersionedTransaction } = await loadSolanaWeb3();
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
      await refreshLiveWalletCoreData();
      await refreshLiveWalletDetailData(true);
      if (activeLiveIntentId) {
        await reconcileLiveIntent(activeLiveIntentId).catch(() => undefined);
        await refreshLiveWalletDetailData(true);
      }
    } catch (error) {
      setApiError(`Wallet submit failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function refreshLiveExecutionSurfaces() {
    await Promise.all([
      refreshLiveWalletCoreData(),
      refreshLiveWalletDetailData(true)
    ]);
  }
  async function recoverAllLiveAudits() {
    try {
      const result = await recoverUnresolvedLiveAudit();
      const firstAudit = result.audits?.[0];
      if (firstAudit) setActiveLiveAudit(firstAudit);
      await refreshLiveExecutionSurfaces();
      setApiError("");
    } catch (error) {
      setApiError(`Live audit recovery failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function recoverSingleLiveAudit(auditId: string) {
    try {
      const audit = await recoverLiveAudit(auditId);
      setActiveLiveAudit(audit);
      await refreshLiveExecutionSurfaces();
      setApiError("");
    } catch (error) {
      setApiError(`Live audit recovery failed: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  React.useEffect(() => {
    refreshPnlData().catch(() => undefined);
    refreshSolUsdPrice().catch(() => undefined);
    refreshStrategyPresetData().catch(() => undefined);
    if (workspacePage !== "monitor") {
      refreshWorkspaceData(workspacePage).catch(() => undefined);
    }
  }, [refreshPnlData, refreshSolUsdPrice, refreshStrategyPresetData, refreshWorkspaceData, workspacePage]);

  React.useEffect(() => {
    if (!settingsOpen) return;
    refreshStrategyPresetData().catch(() => undefined);
  }, [refreshStrategyPresetData, settingsOpen]);

  React.useEffect(() => {
    if (!shouldPollPnl && !selectedLivePnlWallet) return;
    refreshPnlData().catch(() => undefined);
  }, [pnlTimeframe, selectedLivePnlWallet, shouldPollPnl]);

  React.useEffect(() => {
    if (!shouldPollPnl) return;
    const interval = window.setInterval(() => {
      refreshPnlData().catch(() => undefined);
    }, effectiveBotStatus === "running" ? 5000 : 15000);
    return () => window.clearInterval(interval);
  }, [effectiveBotStatus, pnlTimeframe, selectedLivePnlWallet, shouldPollPnl]);

  React.useEffect(() => {
    if (workspacePage === "monitor" && !liveWalletOpen) return;
    const intervalMs = workspacePage === "monitor"
      ? (effectiveBotStatus === "running" ? 8000 : 18000)
      : (effectiveBotStatus === "running" ? 9000 : 22000);
    const interval = window.setInterval(() => {
      if (liveWalletOpen) {
        refreshLiveWalletCoreData().catch(() => undefined);
      }
      if (workspacePage !== "monitor") {
        refreshWorkspaceData(workspacePage).catch(() => undefined);
      }
    }, intervalMs);
    return () => window.clearInterval(interval);
  }, [effectiveBotStatus, liveWalletOpen, refreshLiveWalletCoreData, refreshWorkspaceData, workspacePage]);

  React.useEffect(() => {
    if (liveWalletOpen) {
      refreshLiveWalletCoreData().catch(() => undefined);
      refreshLiveWalletDetailData(true).catch(() => undefined);
    }
    if (workspacePage !== "monitor") {
      refreshWorkspaceData(workspacePage).catch(() => undefined);
    }
  }, [liveWalletOpen, refreshLiveWalletCoreData, refreshLiveWalletDetailData, refreshWorkspaceData, workspacePage]);

  React.useEffect(() => {
    if (!liveWalletOpen) return;
    const interval = window.setInterval(() => {
      refreshLiveWalletDetailData().catch(() => undefined);
    }, effectiveBotStatus === "running" ? 9000 : 20000);
    return () => window.clearInterval(interval);
  }, [effectiveBotStatus, liveWalletOpen, refreshLiveWalletDetailData]);

  React.useEffect(() => {
    const interval = window.setInterval(() => {
      refreshSolUsdPrice().catch(() => undefined);
    }, solUsdPrice > 0 ? 60000 : 10000);
    return () => window.clearInterval(interval);
  }, [solUsdPrice]);

  React.useEffect(() => {
    if (!walletPublicKey) {
      setWalletBalanceSol(null);
      return;
    }
    Promise.all([
      refreshLiveWalletCoreData(walletPublicKey),
      liveWalletOpen ? refreshLiveWalletDetailData(true) : Promise.resolve(),
    ]).catch(() => undefined);
  }, [liveWalletOpen, refreshLiveWalletCoreData, refreshLiveWalletDetailData, walletPublicKey]);

  if (authRequired && !authed) {
    return <AuthGate totpRequired={totpRequired} onAuthed={() => setAuthed(true)} onError={setApiError} error={apiError} />;
  }

  return (
    <AppLayout
      activePage={workspacePage}
      setActivePage={setWorkspacePage}
      status={botActionStatus || snapshot.status}
      apiState={apiState}
      onStart={handleStartBot}
      onStop={handleStopBot}
      onSettingsOpen={() => setSettingsOpen(true)}
      onAddWalletOpen={openAddWalletFlow}
      onManageWalletOpen={openManageWalletFlow}
      walletOptions={walletScopeOptions}
      activeWallet={pnlWalletScope}
      canRemoveActiveWallet={pnlWalletScope !== "paper" && (liveWallets.includes(pnlWalletScope) || walletPublicKey === pnlWalletScope)}
      onActiveWalletChange={updatePnlWalletScope}
      onRemoveWallet={() => setWalletPendingRemoval(pnlWalletScope === "paper" ? null : pnlWalletScope)}
      walletPublicKey={walletPublicKey}
      walletBalance={walletBalanceSol}
      toasts={toasts}
    >
      {workspacePage === "monitor" && (
        <MonitorPage
          stats={stats}
          pnlHistory={pnlHistory}
          pnlValue={displayPnlValue}
          pnlCurrency={effectivePnlCurrency}
          pnlCurrencyLabel={pnlCurrencyLabel}
          solUsdPrice={solUsdPrice}
          onTogglePnlCurrency={togglePnlCurrency}
          pnlCaption={pnlWalletScope === "paper"
            ? `${paperPnlSummary?.closed_trade_count ?? 0} closed paper trades in selected range`
            : `${liveLedger?.summary.open_positions ?? 0} live positions / ${(liveLedger?.summary.approximate ?? true) ? "approximate" : "confirmed"} P&L`}
          walletOptions={walletScopeOptions}
          timeframe={pnlTimeframe}
          setTimeframe={setPnlTimeframe}
          pnlWallet={pnlWalletScope}
          setPnlWallet={updatePnlWalletScope}
          tokens={filteredTokens}
          onSelectToken={setSelectedTokenId}
          selectedTokenId={selectedTokenId}
          watchlist={watchSet}
          onToggleWatch={toggleWatchlist}
          search={tokenSearch}
          setSearch={setTokenSearch}
          filter={queueFilter}
          setFilter={setQueueFilter}
          sort={queueSort}
          setSort={setQueueSort}
          hideSkipped={hideSkippedTokens}
          setHideSkipped={updateHideSkippedTokens}
          apiState={apiState}
          loading={monitorLoading}
          pnlLoading={pnlLoading}
          tokenLoading={tokenLoading}
        />
      )}

      {workspacePage === "analysis" && (
        <Suspense fallback={<LazyPanelFallback label="analysis" />}>
          <AnalysisPage
            tokens={tokenSource}
            trades={trades}
            stats={stats}
            analytics={performanceAnalytics}
            suggestions={tuningSuggestions}
            priceDiagnostics={priceDiagnostics}
            pumpfunReport={pumpfunReport}
            safetyStatus={safetyStatus}
            readinessStatus={readinessStatus}
            pnlTimeframe={pnlTimeframe}
            onTimeframeChange={setPnlTimeframe}
            onApplySuggestion={handleApplyTuningSuggestion}
          />
        </Suspense>
      )}

      {workspacePage === "backtests" && (
        <Suspense fallback={<LazyPanelFallback label="backtests" />}>
          <BacktestsPage
            runs={backtests}
            latest={backtestResult}
            limit={backtestLimit}
            profile={backtestProfile}
            dateFrom={backtestDateFrom}
            dateTo={backtestDateTo}
            speed={String(backtestSpeed)}
            onLimitChange={setBacktestLimit}
            onProfileChange={(p) => setBacktestProfile(p as any)}
            onDateFromChange={setBacktestDateFrom}
            onDateToChange={setBacktestDateTo}
            onSpeedChange={(s) => setBacktestSpeed(parseInt(s))}
            onRun={replayBacktest}
            onRawReplay={rawReplayBacktest}
            onCompare={compareStrategies}
            onABReplay={abReplayStrategies}
            onRunV3={runBacktestSuiteV3}
            onSaveExperiment={saveExperimentFromDashboard}
            v3Result={backtestV3Result}
            experiments={experiments}
          />
        </Suspense>
      )}

      {workspacePage === "review" && (
        <Suspense fallback={<LazyPanelFallback label="trade review" />}>
          <ReviewPage
            trades={trades}
            versions={settingsVersions}
            tokens={tokenSource}
            analytics={performanceAnalytics}
            suggestions={tuningSuggestions}
            selectedTradeId={selectedReviewTradeId}
            timeline={replayTimeline}
            detail={tradeReviewDetail}
            labels={tradeLabels}
            onApplySuggestion={handleApplyTuningSuggestion}
            onLabelTrade={async (tokenId, label) => {
              const saved = await labelTrade(tokenId, label);
              setTradeLabels((current) => [saved, ...current]);
            }}
            onSelectTrade={loadReplayTimeline}
          />
        </Suspense>
      )}

      {workspacePage === "data" && (
        <Suspense fallback={<LazyPanelFallback label="project data" />}>
          <DataPage
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
            onRefresh={() => refreshWorkspaceData("data")}
            onRecover={async () => {
              const updated = await recoverWatchdog();
              setSnapshot(updated);
              await refreshAfterMutation({ page: "data" });
            }}
            onReviewLiveRequest={reviewManualLiveRequest}
            onClear={clearProjectData}
          />
        </Suspense>
      )}

      {settingsOpen && (
        <Suspense fallback={<Modal isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} title="Settings" description="Loading settings..." className="max-w-5xl"><LazyPanelFallback label="settings" /></Modal>}>
          <SettingsModal
            isOpen={settingsOpen}
            onClose={() => setSettingsOpen(false)}
            settings={settings}
            onSave={saveSettings}
            sourceStatus={snapshot.source_status}
            serverStrategyPresets={strategyPresetsRemote}
            onSaveStrategyPreset={saveCurrentStrategyPreset}
          />
        </Suspense>
      )}

      {selectedToken && (
        <Suspense fallback={<Modal isOpen={!!selectedToken} onClose={() => setSelectedTokenId(null)} title="Token Analysis" description="Loading token detail..." className="max-w-3xl"><LazyPanelFallback label="token detail" /></Modal>}>
          <NewTokenDetail
            token={selectedToken}
            isOpen={!!selectedToken}
            onClose={() => setSelectedTokenId(null)}
          />
        </Suspense>
      )}

      {liveWalletOpen && (
        <GuidedLiveWalletModal
          initialView={liveWalletOpenMode}
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
          onArmBackend={armSelectedLiveBackend}
          onDisarmBackend={disarmSelectedLiveBackend}
          onApplyQuickFix={applyLiveQuickFix}
          hotWalletStatus={hotWalletStatus}
          hotWalletPrivateKey={hotWalletPrivateKey}
          hotWalletPassword={hotWalletPassword}
          hotWalletLabel={hotWalletLabel}
          onHotWalletPrivateKeyChange={setHotWalletPrivateKey}
          onHotWalletPasswordChange={setHotWalletPassword}
          onHotWalletLabelChange={setHotWalletLabel}
          onImportHotWallet={importEncryptedHotWallet}
          onUnlockHotWallet={unlockEncryptedHotWallet}
          onLockHotWallet={lockEncryptedHotWallet}
          onClearHotWallet={clearEncryptedHotWallet}
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
          onRecoverAllLiveAudits={recoverAllLiveAudits}
          onRecoverLiveAudit={recoverSingleLiveAudit}
        />
      )}

      <Modal
        isOpen={!!walletPendingRemoval}
        onClose={() => setWalletPendingRemoval(null)}
        title="Remove Wallet"
        description="Review the selected wallet before removing it from the dashboard selector."
        className="max-w-lg"
      >
        <div className="space-y-4">
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/[0.05] p-4">
            <p className="text-[10px] font-black uppercase tracking-[0.24em] text-zinc-500">Selected wallet</p>
            <p className="mt-2 break-all text-sm font-black text-white">{walletPendingRemoval || "-"}</p>
            <p className="mt-3 text-xs leading-5 text-zinc-300">This removes the wallet from the active selector and resets the dashboard back to paper if that wallet is currently selected. It does not delete on-chain funds.</p>
          </div>
          <div className="flex justify-end gap-3">
            <button className="rounded-lg border border-white/10 bg-white/[0.03] px-4 py-2 text-xs font-black uppercase tracking-widest text-zinc-300 transition hover:bg-white/[0.06]" onClick={() => setWalletPendingRemoval(null)}>
              Cancel
            </button>
            <button
              className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-xs font-black uppercase tracking-widest text-rose-100 transition hover:bg-rose-500/20"
              onClick={() => {
                if (!walletPendingRemoval) return;
                removeTrackedWallet(walletPendingRemoval);
                setWalletPendingRemoval(null);
              }}
            >
              Remove Wallet
            </button>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={!!pendingSuggestion}
        onClose={() => !applyingSuggestion && setPendingSuggestion(null)}
        title="Implement Tuning Suggestion"
        description="Review the exact setting change before applying it to the active dashboard configuration."
        className="max-w-xl"
      >
        <div className="space-y-4">
          <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
            <div className="text-sm font-black text-white">{pendingSuggestion?.title}</div>
            <div className="mt-2 text-sm leading-relaxed text-zinc-400">{pendingSuggestion?.reason}</div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-white/5 bg-black/30 p-4">
              <div className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Setting</div>
              <div className="mt-1 break-all text-sm font-black text-white">{pendingSuggestion?.setting || "-"}</div>
            </div>
            <div className="rounded-xl border border-white/5 bg-black/30 p-4">
              <div className="text-[10px] font-black uppercase tracking-widest text-zinc-500">New Value</div>
              <div className="mt-1 break-all text-sm font-black text-amber-300">{pendingSuggestion?.suggested_value === undefined ? "-" : String(pendingSuggestion.suggested_value)}</div>
            </div>
          </div>
          <div className="rounded-xl border border-amber-400/20 bg-amber-500/[0.04] p-4 text-[11px] leading-relaxed text-zinc-300">
            This will update the live dashboard settings immediately and refresh the research surfaces. It does not place trades or change the paper/live safety boundary.
          </div>
          <div className="flex justify-end gap-3">
            <button
              className="rounded-lg border border-white/10 bg-white/[0.03] px-4 py-2 text-xs font-black uppercase tracking-widest text-zinc-300 transition hover:bg-white/[0.06]"
              onClick={() => setPendingSuggestion(null)}
              disabled={applyingSuggestion}
            >
              Cancel
            </button>
            <button
              className="rounded-lg border border-amber-400/30 bg-amber-400 px-4 py-2 text-xs font-black uppercase tracking-widest text-[#160f08] transition hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-60"
              onClick={confirmApplyTuningSuggestion}
              disabled={applyingSuggestion || !pendingSuggestion}
            >
              {applyingSuggestion ? "Applying" : "Confirm Change"}
            </button>
          </div>
        </div>
      </Modal>
    </AppLayout>
  );
}

function GuidedLiveWalletModal({
  initialView,
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
  onArmBackend,
  onDisarmBackend,
  onApplyQuickFix,
  hotWalletStatus,
  hotWalletPrivateKey,
  hotWalletPassword,
  hotWalletLabel,
  onHotWalletPrivateKeyChange,
  onHotWalletPasswordChange,
  onHotWalletLabelChange,
  onImportHotWallet,
  onUnlockHotWallet,
  onLockHotWallet,
  onClearHotWallet,
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
  onSignAndSendLive,
  onRecoverAllLiveAudits,
  onRecoverLiveAudit
}: {
  initialView: "setup" | "workspace";
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
  onConnectWallet: () => Promise<boolean>;
  onAcknowledgeLive: () => Promise<boolean>;
  onArmBackend: () => Promise<boolean>;
  onDisarmBackend: () => Promise<boolean>;
  onApplyQuickFix: (kind: "enable_env" | "configure_caps" | "disable_kill_switch") => Promise<boolean>;
  hotWalletStatus: HotWalletStatus | null;
  hotWalletPrivateKey: string;
  hotWalletPassword: string;
  hotWalletLabel: string;
  onHotWalletPrivateKeyChange: (value: string) => void;
  onHotWalletPasswordChange: (value: string) => void;
  onHotWalletLabelChange: (value: string) => void;
  onImportHotWallet: () => Promise<boolean>;
  onUnlockHotWallet: () => Promise<boolean>;
  onLockHotWallet: () => Promise<boolean>;
  onClearHotWallet: () => Promise<boolean>;
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
  onRecoverAllLiveAudits: () => Promise<void>;
  onRecoverLiveAudit: (auditId: string) => Promise<void>;
}) {
  type WorkspaceAction = "acknowledge" | "arm" | "disarm" | "reconnect" | "lock" | "clear";

  const [stepIndex, setStepIndex] = React.useState(initialView === "workspace" ? 4 : 0);
  const [workspaceVisible, setWorkspaceVisible] = React.useState(initialView === "workspace");
  const [busyAction, setBusyAction] = React.useState("");
  const [pendingWorkspaceAction, setPendingWorkspaceAction] = React.useState<WorkspaceAction | null>(null);
  const [pendingFixBlocker, setPendingFixBlocker] = React.useState<string | null>(null);
  const [completionStamp, setCompletionStamp] = React.useState(0);

  React.useEffect(() => {
    setStepIndex(initialView === "workspace" ? 4 : 0);
    setWorkspaceVisible(initialView === "workspace");
    setPendingWorkspaceAction(null);
    setPendingFixBlocker(null);
    setBusyAction("");
    setCompletionStamp(0);
  }, [initialView]);

  const capsSet = settings.live_max_trade_sol > 0 && settings.live_daily_loss_cap_sol > 0 && settings.live_wallet_exposure_cap_sol > 0 && settings.live_max_open_positions > 0 && settings.live_max_slippage_pct > 0 && settings.live_priority_fee_cap_sol > 0;
  const envEnabled = Boolean(liveStatus?.env_live_enabled);
  const walletDisplay = method === "local_hot_wallet" ? hotWalletStatus?.wallet_public_key || settings.live_hot_wallet_public_key : liveStatus?.signer?.wallet_public_key || walletPublicKey;
  const quoteBlocked = !envEnabled;
  const blockers = liveStatus?.blockers?.length ? liveStatus.blockers : envEnabled ? [] : ["Live environment flag is disabled"];
  const activeQuoteStale = activeLiveAudit?.status === "stale" || Boolean(activeLiveAudit?.quote?.stale);
  const recoverableAuditStatuses = new Set(["submitted", "failed", "needs_review", "stale"]);
  const reviewAudits = liveAudit.filter((audit) => recoverableAuditStatuses.has(audit.status) || audit.reconciliation_status === "needs_review");
  const recoverySummary = liveStatus?.recovery_summary;
  const autonomyBlockers = liveStatus?.autonomy_blockers ?? [];
  const readinessScore = liveStatus?.readiness?.score ?? 0;
  const readinessState = liveStatus?.readiness?.status?.replace(/_/g, " ") ?? "unknown";
  const signerDisabledReason = liveStatus?.signer?.disabled_reason || liveStatus?.wallet_adapter?.disabled_reason || "";
  const signerSupportsAutoSell = Boolean(liveStatus?.signer?.supports_auto_sell);
  const signerSupportsAutoBuy = Boolean(liveStatus?.signer?.supports_auto_buy);
  const activeBackend = liveStatus?.active_backend;
  const connectionReady = method === "browser_wallet"
    ? Boolean(walletPublicKey)
    : method === "local_hot_wallet"
      ? Boolean(hotWalletStatus?.unlocked)
      : Boolean(liveStatus?.backend_capabilities?.local_signer_daemon?.healthy);
  const backendHealth = method === "browser_wallet"
    ? (walletPublicKey ? "connected" : "disconnected")
    : method === "local_hot_wallet"
      ? (hotWalletStatus?.unlocked ? "unlocked" : hotWalletStatus?.imported ? "locked" : "not imported")
      : (connectionReady ? "healthy" : "offline");
  const methodLabel = method === "browser_wallet" ? "Browser Wallet" : method === "local_hot_wallet" ? "Local Hot Wallet" : "Local Signer Daemon";
  const modeLabel = method === "browser_wallet"
    ? "Assisted approvals"
    : method === "local_hot_wallet"
      ? "Encrypted unattended signing"
      : "Daemon-backed unattended signing";
  const setupSteps = [
    "Choose Path",
    method === "browser_wallet" ? "Connect" : method === "local_hot_wallet" ? (hotWalletStatus?.imported ? "Unlock" : "Import") : "Check Daemon",
    "Review",
    "Confirm",
    "Ready"
  ];
  const setupHelper = [
    "Pick the execution path you want for this session. The control plane stays the same, but the signing experience changes by backend.",
    method === "browser_wallet"
      ? "Connect the browser wallet first, then review the exact assisted mode before entering the workspace."
      : method === "local_hot_wallet"
        ? "Import or unlock your encrypted hot wallet, then review the mode and current safety context."
        : "Check daemon health and detected wallet first, then confirm this path for the session.",
    "Review the selected backend, wallet context, readiness state, and warnings before confirming.",
    "This final confirmation records your live-session acknowledgement when needed.",
    "Setup is complete. Enter the workspace or switch paths and repeat setup."
  ];
  const setupWarnings = [...blockers, ...autonomyBlockers, ...(signerDisabledReason ? [signerDisabledReason] : [])].slice(0, 4);
  const methodTone = {
    browser_wallet: "border-emerald-400/40 bg-emerald-500/10 text-emerald-200",
    local_hot_wallet: "border-amber-400/40 bg-amber-500/10 text-amber-100",
    local_signer_daemon: "border-sky-400/40 bg-sky-500/10 text-sky-100"
  } as const;

  async function handleStepPrimary() {
    if (stepIndex === 0) {
      setStepIndex(1);
      return;
    }
    if (stepIndex === 1) {
      setBusyAction("step");
      try {
        let ok = false;
        if (method === "browser_wallet") ok = connectionReady || await onConnectWallet();
        if (method === "local_hot_wallet") ok = hotWalletStatus?.unlocked || (hotWalletStatus?.imported ? await onUnlockHotWallet() : await onImportHotWallet());
        if (method === "local_signer_daemon") ok = connectionReady;
        if (ok) setStepIndex(2);
      } finally {
        setBusyAction("");
      }
      return;
    }
    if (stepIndex === 2) {
      setStepIndex(3);
      return;
    }
    if (stepIndex === 3) {
      setBusyAction("confirm");
      try {
        const ok = settings.live_session_acknowledged ? true : await onAcknowledgeLive();
        if (ok) {
          setStepIndex(4);
          setCompletionStamp(Date.now());
        }
      } finally {
        setBusyAction("");
      }
      return;
    }
    if (stepIndex === 4) {
      setWorkspaceVisible(true);
    }
  }

  async function confirmWorkspaceAction() {
    if (!pendingWorkspaceAction) return;
    setBusyAction(pendingWorkspaceAction);
    try {
      let ok = false;
      if (pendingWorkspaceAction === "acknowledge") ok = await onAcknowledgeLive();
      if (pendingWorkspaceAction === "arm") ok = await onArmBackend();
      if (pendingWorkspaceAction === "disarm") ok = await onDisarmBackend();
      if (pendingWorkspaceAction === "reconnect") ok = await onConnectWallet();
      if (pendingWorkspaceAction === "lock") ok = await onLockHotWallet();
      if (pendingWorkspaceAction === "clear") ok = await onClearHotWallet();
      if (ok) setPendingWorkspaceAction(null);
    } finally {
      setBusyAction("");
    }
  }

  const workspaceActionMeta: Record<WorkspaceAction, { title: string; body: string; tone: string }> = {
    acknowledge: {
      title: "Confirm live-session acknowledgement",
      body: "This records that you reviewed the current live warnings and intentionally want to keep operating in the live wallet workspace.",
      tone: "border-amber-400/20 bg-amber-500/10"
    },
    arm: {
      title: "Arm active backend",
      body: "This enables the selected backend to execute under the current readiness checks, caps, and autonomy gates.",
      tone: "border-emerald-500/20 bg-emerald-500/10"
    },
    disarm: {
      title: "Disarm active backend",
      body: "This halts new autonomous execution for the current backend while leaving review and recovery tools available.",
      tone: "border-rose-500/20 bg-rose-500/10"
    },
    reconnect: {
      title: "Reconnect browser wallet",
      body: "This refreshes the assisted browser-wallet context and requests a new wallet connection if needed.",
      tone: "border-amber-400/20 bg-amber-500/10"
    },
    lock: {
      title: "Lock hot wallet",
      body: "This removes hot-wallet signing access from memory until you unlock it again.",
      tone: "border-zinc-500/20 bg-white/5"
    },
    clear: {
      title: "Clear stored hot wallet",
      body: "This removes the encrypted hot-wallet material from local storage. You will need to import it again before reuse.",
      tone: "border-rose-500/20 bg-rose-500/10"
    }
  };

  function blockerFixDescriptor(blocker: string): { label: string; title: string; body: string; tone: string; run: () => Promise<boolean> | boolean } | null {
    const lower = blocker.toLowerCase();
    if (lower.includes("live_trading_enabled is false") || lower.includes("environment flag is disabled")) {
      return {
        label: "Enable Live Env",
        title: "Enable live execution environment",
        body: "This turns on the local live-trading environment flag and manual live support so the current backend can continue through readiness checks.",
        tone: "border-amber-400/20 bg-amber-500/10",
        run: () => onApplyQuickFix("enable_env")
      };
    }
    if (lower.includes("live session acknowledgement")) {
      return {
        label: "Acknowledge",
        title: "Record live-session acknowledgement",
        body: "This records the session acknowledgement required before live execution can proceed.",
        tone: "border-amber-400/20 bg-amber-500/10",
        run: () => onAcknowledgeLive()
      };
    }
    if (lower.includes("must be set")) {
      return {
        label: "Apply Caps",
        title: "Apply recommended live caps",
        body: "This fills in missing live caps with conservative defaults so the backend can pass basic execution checks without opening the settings screen.",
        tone: "border-amber-400/20 bg-amber-500/10",
        run: () => onApplyQuickFix("configure_caps")
      };
    }
    if (lower.includes("kill switch")) {
      return {
        label: "Disable Kill Switch",
        title: "Disable manual kill switch",
        body: "This turns off the kill switch in dashboard settings so live execution can resume. Use only if you intentionally want the live backend to operate again.",
        tone: "border-rose-500/20 bg-rose-500/10",
        run: () => onApplyQuickFix("disable_kill_switch")
      };
    }
    if (lower.includes("wallet public key is required") || lower.includes("no connected signer")) {
      if (method === "browser_wallet") {
        return {
          label: "Connect Wallet",
          title: "Connect browser wallet",
          body: "This reconnects the browser wallet so the assisted path has an active public key to work with.",
          tone: "border-amber-400/20 bg-amber-500/10",
          run: () => onConnectWallet()
        };
      }
      if (method === "local_hot_wallet") {
        return {
          label: hotWalletStatus?.imported ? "Unlock Wallet" : "Finish Setup",
          title: hotWalletStatus?.imported ? "Unlock encrypted hot wallet" : "Return to wallet setup",
          body: hotWalletStatus?.imported
            ? "This unlocks the encrypted hot wallet for the current app session so the unattended path can sign again."
            : "This sends you back into the guided setup flow so you can import the hot wallet cleanly.",
          tone: "border-amber-400/20 bg-amber-500/10",
          run: () => hotWalletStatus?.imported ? onUnlockHotWallet() : (setWorkspaceVisible(false), setStepIndex(1), true)
        };
      }
      return {
        label: "Edit Setup",
        title: "Return to signer setup",
        body: "This returns you to the guided setup steps so you can review the signer path and backend health again.",
        tone: "border-zinc-500/20 bg-white/5",
        run: () => {
          setWorkspaceVisible(false);
          setStepIndex(1);
          return true;
        }
      };
    }
    if (lower.includes("unavailable") || lower.includes("localhost")) {
      return {
        label: "Edit Setup",
        title: "Review backend setup",
        body: "This takes you back to the setup steps so you can review the selected backend and choose a healthier execution path if needed.",
        tone: "border-zinc-500/20 bg-white/5",
        run: () => {
          setWorkspaceVisible(false);
          setStepIndex(1);
          return true;
        }
      };
    }
    return null;
  }

  async function confirmBlockerFix() {
    if (!pendingFixBlocker) return;
    const descriptor = blockerFixDescriptor(pendingFixBlocker);
    if (!descriptor) {
      setPendingFixBlocker(null);
      return;
    }
    setBusyAction(`fix:${pendingFixBlocker}`);
    try {
      const ok = await Promise.resolve(descriptor.run());
      if (ok) setPendingFixBlocker(null);
    } finally {
      setBusyAction("");
    }
  }

  const primaryWorkspaceButtons = [
    !settings.live_session_acknowledged ? (
      <button key="acknowledge" className="h-10 rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-amber-100 transition hover:bg-amber-500/20" onClick={() => setPendingWorkspaceAction("acknowledge")}>
        Confirm Session
      </button>
    ) : null,
    activeBackend?.armed ? (
      <button key="disarm" className="h-10 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-rose-100 transition hover:bg-rose-500/20" onClick={() => setPendingWorkspaceAction("disarm")}>
        Disarm
      </button>
    ) : (
      <button key="arm" className="h-10 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-emerald-100 transition hover:bg-emerald-500/20" onClick={() => setPendingWorkspaceAction("arm")}>
        Arm Backend
      </button>
    ),
    method === "browser_wallet" ? (
      <button key="reconnect" className="h-10 rounded-xl border border-white/10 bg-white/5 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-white transition hover:border-white/20 hover:bg-white/10" onClick={() => setPendingWorkspaceAction("reconnect")}>
        Reconnect
      </button>
    ) : null,
    method === "local_hot_wallet" && hotWalletStatus?.unlocked ? (
      <button key="lock" className="h-10 rounded-xl border border-white/10 bg-white/5 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-white transition hover:border-white/20 hover:bg-white/10" onClick={() => setPendingWorkspaceAction("lock")}>
        Lock
      </button>
    ) : null,
    method === "local_hot_wallet" && hotWalletStatus?.imported ? (
      <button key="clear" className="h-10 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-rose-100 transition hover:bg-rose-500/20" onClick={() => setPendingWorkspaceAction("clear")}>
        Clear Stored Key
      </button>
    ) : null
  ].filter(Boolean);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-md">
      <motion.section
        initial={{ opacity: 0, scale: 0.97, y: 18 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 18 }}
        transition={{ type: "spring", stiffness: 360, damping: 32 }}
        className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-white/10 bg-[#0a0c13]/95 shadow-2xl shadow-black/70"
      >
        <div className="sticky top-0 z-10 border-b border-white/10 bg-[#0d0f18]/95 px-5 py-4 backdrop-blur-xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.28em] text-amber-400">Local live execution</p>
              <h3 className="mt-1 text-2xl font-black tracking-tight text-white">{workspaceVisible ? "Live Wallet Workspace" : "Connect Wallet"}</h3>
              <p className="mt-1 max-w-3xl text-xs font-medium text-zinc-400">{workspaceVisible ? "The setup flow is complete. Operate the selected backend from one calmer workspace with clearer readiness, recovery, and execution controls." : setupHelper[stepIndex]}</p>
            </div>
            <button className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-zinc-400 transition hover:border-amber-500/40 hover:text-white" onClick={onClose} aria-label="Close live wallet">
              <X size={18} />
            </button>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className={`rounded-full border px-3 py-1 text-[10px] font-black uppercase tracking-[0.24em] ${methodTone[method]}`}>{methodLabel}</span>
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[10px] font-black uppercase tracking-[0.24em] text-zinc-300">{workspaceVisible ? "Workspace" : `Step ${stepIndex + 1} of ${setupSteps.length}`}</span>
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[10px] font-black uppercase tracking-[0.24em] text-zinc-300">{modeLabel}</span>
          </div>
          {!workspaceVisible ? (
            <div className="mt-4 grid gap-2 sm:grid-cols-5">
              {setupSteps.map((label, index) => {
                const active = index === stepIndex;
                const complete = workspaceVisible || index < stepIndex;
                return (
                  <div key={label} className={`rounded-xl border px-3 py-3 ${active ? "border-amber-400/40 bg-amber-500/10" : complete ? "border-emerald-400/30 bg-emerald-500/10" : "border-white/10 bg-white/[0.03]"}`}>
                    <div className="flex items-center gap-2">
                      <span className={`flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-black ${active ? "border-amber-400/40 bg-amber-500/10 text-amber-100" : complete ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-100" : "border-white/10 bg-black/20 text-zinc-500"}`}>{index + 1}</span>
                      <span className="text-[10px] font-black uppercase tracking-[0.22em] text-white">{label}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>

        <div className="overflow-y-auto p-5 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
          {!workspaceVisible ? (
            <div className="space-y-4">
              {stepIndex === 0 ? (
                <div className="grid gap-4 lg:grid-cols-3">
                  {[
                    ["browser_wallet", "Browser Wallet", "Assisted", "Phantom-first assisted mode. Manual approvals remain required unless the browser environment exposes true unattended signing."],
                    ["local_hot_wallet", "Local Hot Wallet", hotWalletStatus?.unlocked ? "Unlocked" : hotWalletStatus?.imported ? "Locked" : "Import", "Encrypted-at-rest local signing with password unlock each app start for unattended entries and exits."],
                    ["local_signer_daemon", "Local Signer Daemon", connectionReady && method === "local_signer_daemon" ? "Healthy" : "Daemon", "Separate localhost signer backend for unattended execution when its own health and auth contract pass."]
                  ].map(([value, title, badge, body]) => (
                    <button key={value} className={`rounded-2xl border p-5 text-left transition ${method === value ? value === "browser_wallet" ? "border-emerald-400/50 bg-emerald-500/10 shadow-lg shadow-emerald-500/10" : value === "local_hot_wallet" ? "border-amber-400/50 bg-amber-500/10 shadow-lg shadow-amber-500/10" : "border-sky-400/50 bg-sky-500/10 shadow-lg shadow-sky-500/10" : "border-white/10 bg-white/[0.03] hover:border-white/20"}`} onClick={() => onMethodChange(value as LiveWalletMethod)}>
                      <div className="flex items-center justify-between gap-3">
                        <strong className="text-sm font-black uppercase tracking-[0.18em] text-white">{title}</strong>
                        <span className={`rounded-full border px-2 py-1 text-[10px] font-black uppercase tracking-[0.2em] ${methodTone[value as LiveWalletMethod]}`}>{badge}</span>
                      </div>
                      <p className="mt-3 text-xs leading-5 text-zinc-400">{body}</p>
                    </button>
                  ))}
                </div>
              ) : null}

              {stepIndex === 1 ? (
                <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
                  <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
                    <div className="mb-4 flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Setup</p>
                        <h3 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">{setupSteps[1]}</h3>
                        <p className="mt-1 text-xs text-zinc-400">{setupHelper[1]}</p>
                      </div>
                      <Wallet size={18} className="text-amber-400" />
                    </div>
                    {method === "browser_wallet" ? (
                      <div className="rounded-2xl border border-white/5 bg-black/20 p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Browser wallet connection</p>
                        <p className="mt-2 text-xs text-zinc-400">Connect the browser wallet now. The next step will review the public key, assisted mode, and current readiness state.</p>
                        <button className="mt-4 h-10 rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-amber-100 transition hover:bg-amber-500/20" onClick={handleStepPrimary} disabled={busyAction === "step"}>
                          {busyAction === "step" ? "Connecting" : walletPublicKey ? "Continue with Connected Wallet" : "Connect Browser Wallet"}
                        </button>
                      </div>
                    ) : null}
                    {method === "local_hot_wallet" ? (
                      <div className="space-y-3 rounded-2xl border border-white/5 bg-black/20 p-4">
                        <input className="h-10 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-xs font-bold text-white placeholder-zinc-600" value={hotWalletLabel} onChange={(event) => onHotWalletLabelChange(event.target.value)} placeholder="Wallet label (optional)" />
                        {!hotWalletStatus?.imported ? <textarea className="min-h-[88px] w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-xs font-bold text-white placeholder-zinc-600" value={hotWalletPrivateKey} onChange={(event) => onHotWalletPrivateKeyChange(event.target.value)} placeholder="Base58 private key or byte array" /> : null}
                        <input className="h-10 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-xs font-bold text-white placeholder-zinc-600" type="password" value={hotWalletPassword} onChange={(event) => onHotWalletPasswordChange(event.target.value)} placeholder={hotWalletStatus?.imported ? "Unlock password" : "Encryption password"} />
                        <button className="h-10 rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-amber-100 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50" onClick={handleStepPrimary} disabled={busyAction === "step" || (!hotWalletStatus?.imported && (!hotWalletPrivateKey.trim() || !hotWalletPassword.trim())) || (hotWalletStatus?.imported && !hotWalletStatus?.unlocked && !hotWalletPassword.trim())}>
                          {busyAction === "step" ? (hotWalletStatus?.imported ? "Unlocking" : "Importing") : hotWalletStatus?.unlocked ? "Continue with Unlocked Wallet" : hotWalletStatus?.imported ? "Unlock Hot Wallet" : "Import & Encrypt"}
                        </button>
                      </div>
                    ) : null}
                    {method === "local_signer_daemon" ? (
                      <div className="rounded-2xl border border-white/5 bg-black/20 p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Signer daemon health</p>
                        <div className="mt-3 grid gap-2 sm:grid-cols-2">
                          <div className="rounded-xl border border-white/5 bg-black/25 p-3">
                            <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Endpoint</p>
                            <p className="mt-1 break-all text-xs font-bold text-white">{liveStatus?.signer?.endpoint || "not reported"}</p>
                          </div>
                          <div className="rounded-xl border border-white/5 bg-black/25 p-3">
                            <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Health</p>
                            <p className="mt-1 text-xs font-bold text-white">{connectionReady ? "healthy" : "not ready"}</p>
                          </div>
                        </div>
                        <button className="mt-4 h-10 rounded-xl border border-sky-400/30 bg-sky-500/10 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-sky-100 transition hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-50" onClick={handleStepPrimary} disabled={!connectionReady}>
                          Continue with Daemon
                        </button>
                      </div>
                    ) : null}
                  </section>
                  <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
                    <div className="mb-4 flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Current state</p>
                        <h3 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">Readiness Snapshot</h3>
                        <p className="mt-1 text-xs text-zinc-400">A compact summary before you move into review.</p>
                      </div>
                      <Shield size={18} className="text-amber-400" />
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {[
                        ["Wallet", shortAddress(walletDisplay || "")],
                        ["SOL balance", walletBalanceSol === null ? "-" : `${walletBalanceSol.toFixed(4)} SOL`],
                        ["Backend health", backendHealth],
                        ["Readiness", `${readinessScore}% / ${readinessState}`],
                        ["Live env", envEnabled ? "enabled" : "disabled"],
                        ["Caps", capsSet ? "set" : "required"],
                        ["Acknowledgement", settings.live_session_acknowledged ? "done" : "needed"],
                        ["Armed backend", activeBackend?.armed ? `${activeBackend.mode.replace(/_/g, " ")} / ${shortAddress(activeBackend.wallet_public_key)}` : "not armed"]
                      ].map(([label, value]) => (
                        <div key={label} className="rounded-xl border border-white/5 bg-black/25 p-3">
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">{label}</p>
                          <p className="mt-1 truncate text-xs font-bold text-white">{value}</p>
                        </div>
                      ))}
                    </div>
                    <div className="mt-4 space-y-2">
                      {setupWarnings.length ? setupWarnings.map((warning) => <p key={warning} className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-3 text-xs font-bold text-amber-100">{warning}</p>) : <p className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs font-bold text-emerald-100">The selected backend is ready to move into review.</p>}
                    </div>
                  </section>
                </div>
              ) : null}

              {stepIndex === 2 ? (
                <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                  <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
                    <div className="mb-4 flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Review</p>
                        <h3 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">Confirmation Card</h3>
                        <p className="mt-1 text-xs text-zinc-400">Review the backend path, wallet context, readiness, and exact action before you confirm.</p>
                      </div>
                      <Shield size={18} className="text-amber-400" />
                    </div>
                    <div className="rounded-2xl border border-amber-400/20 bg-amber-500/10 p-4">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Backend path</p>
                          <p className="mt-1 text-sm font-black uppercase tracking-[0.16em] text-white">{methodLabel}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Current mode</p>
                          <p className="mt-1 text-sm font-black uppercase tracking-[0.16em] text-white">{modeLabel}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Wallet / public key</p>
                          <p className="mt-1 break-all text-xs font-bold text-white">{walletDisplay || hotWalletLabel || "Will be confirmed by backend on connect"}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Action being confirmed</p>
                          <p className="mt-1 text-xs font-bold text-white">{method === "browser_wallet" ? "Enter assisted live review flow with the connected browser wallet" : method === "local_hot_wallet" ? "Use encrypted local signing for this live wallet session" : "Use signer daemon as the active live signing path"}</p>
                        </div>
                      </div>
                      <div className="mt-4 grid gap-2 sm:grid-cols-3">
                        <div className="rounded-xl border border-white/5 bg-black/20 p-3">
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Readiness</p>
                          <p className="mt-1 text-xs font-bold text-white">{readinessScore}% / {readinessState}</p>
                        </div>
                        <div className="rounded-xl border border-white/5 bg-black/20 p-3">
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Caps</p>
                          <p className="mt-1 text-xs font-bold text-white">{capsSet ? "Configured" : "Needs attention"}</p>
                        </div>
                        <div className="rounded-xl border border-white/5 bg-black/20 p-3">
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Session acknowledgement</p>
                          <p className="mt-1 text-xs font-bold text-white">{settings.live_session_acknowledged ? "Already recorded" : "Will confirm next"}</p>
                        </div>
                      </div>
                    </div>
                  </section>
                  <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
                    <div className="mb-4 flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Warnings</p>
                        <h3 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">What to watch</h3>
                        <p className="mt-1 text-xs text-zinc-400">These warnings stay visible through confirmation so the operator never loses the safety context.</p>
                      </div>
                      <Activity size={18} className="text-amber-400" />
                    </div>
                    <div className="space-y-2">
                      {setupWarnings.length ? setupWarnings.map((warning) => <p key={warning} className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-3 text-xs font-bold text-amber-100">{warning}</p>) : <p className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs font-bold text-emerald-100">No blocking warnings are currently reported for the selected backend.</p>}
                    </div>
                  </section>
                </div>
              ) : null}

              {stepIndex === 3 ? (
                <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
                  <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                    <div className="rounded-2xl border border-amber-400/20 bg-amber-500/10 p-5">
                      <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Final confirmation</p>
                      <h3 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">Enter Live Wallet Setup</h3>
                      <p className="mt-2 text-xs leading-5 text-zinc-300">{settings.live_session_acknowledged ? "Your live-session acknowledgement is already recorded. Confirm to move into the ready state." : "Confirm this live-session acknowledgement so the workspace can open with the current backend path and safety notes attached."}</p>
                    </div>
                    <div className="rounded-2xl border border-white/5 bg-black/20 p-5">
                      <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Confirmation summary</p>
                      <div className="mt-3 space-y-2 text-xs text-zinc-300">
                        <p>Backend: <span className="font-bold text-white">{methodLabel}</span></p>
                        <p>Wallet: <span className="font-bold text-white">{shortAddress(walletDisplay || "")}</span></p>
                        <p>Mode: <span className="font-bold text-white">{modeLabel}</span></p>
                        <p>Live gates: <span className="font-bold text-white">{liveStatus?.live_execution_available ? "open" : "blocked"}</span></p>
                      </div>
                    </div>
                  </div>
                </section>
              ) : null}

              {stepIndex === 4 ? (
                <section className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-5">
                  <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[0.28em] text-emerald-100">Ready</p>
                      <h3 className="mt-1 text-lg font-black tracking-tight text-white">Wallet setup completed</h3>
                      <p className="mt-2 text-sm text-emerald-50/90">The selected path is staged. Enter the workspace to review readiness, arm the backend, and manage quote and recovery operations from one place.</p>
                      {completionStamp ? <p className="mt-3 text-[11px] uppercase tracking-[0.2em] text-emerald-100/80">Confirmed {new Date(completionStamp).toLocaleTimeString()}</p> : null}
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                        <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Backend</p>
                        <p className="mt-1 text-xs font-bold text-white">{methodLabel}</p>
                      </div>
                      <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                        <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Wallet</p>
                        <p className="mt-1 text-xs font-bold text-white">{shortAddress(walletDisplay || "")}</p>
                      </div>
                    </div>
                  </div>
                </section>
              ) : null}
            </div>
          ) : (
            <div className="space-y-4">
              <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
                <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
                  <div>
                    <div className="mb-4 flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Operator console</p>
                        <h3 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">Connected Backend Summary</h3>
                        <p className="mt-1 text-xs text-zinc-400">Keep the critical state at the top: backend path, readiness, blockers, wallet balance, and the next action.</p>
                      </div>
                      <Wallet size={18} className="text-amber-400" />
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                      {[
                        ["Backend", methodLabel],
                        ["Wallet", shortAddress(walletDisplay || "")],
                        ["Balance", walletBalanceSol === null ? "-" : `${walletBalanceSol.toFixed(4)} SOL`],
                        ["Armed state", activeBackend?.armed ? "armed" : "disarmed"],
                        ["Readiness", `${readinessScore}% / ${readinessState}`],
                        ["Live gates", liveStatus?.live_execution_available ? "open" : "blocked"],
                        ["Auto entries", liveStatus?.entry_autonomy_available ? "enabled" : "blocked"],
                        ["Protective exits", liveStatus?.exit_autonomy_available ? "enabled" : "blocked"]
                      ].map(([label, value]) => (
                        <div key={label} className="rounded-xl border border-white/5 bg-black/25 p-3">
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">{label}</p>
                          <p className="mt-1 truncate text-xs font-bold text-white">{value}</p>
                        </div>
                      ))}
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {primaryWorkspaceButtons}
                      <button className="h-10 rounded-xl border border-white/10 bg-white/5 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-white transition hover:border-white/20 hover:bg-white/10" onClick={() => { setWorkspaceVisible(false); setStepIndex(0); }}>
                        Switch Path
                      </button>
                      <button className="h-10 rounded-xl border border-white/10 bg-white/5 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-white transition hover:border-white/20 hover:bg-white/10" onClick={() => { setWorkspaceVisible(false); setStepIndex(1); }}>
                        Edit Setup
                      </button>
                    </div>
                  </div>
                  <div className="space-y-3">
                    {pendingWorkspaceAction ? (
                      <article className={`rounded-2xl border p-4 ${workspaceActionMeta[pendingWorkspaceAction].tone}`}>
                        <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Confirm action</p>
                        <h4 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">{workspaceActionMeta[pendingWorkspaceAction].title}</h4>
                        <p className="mt-2 text-xs leading-5 text-zinc-300">{workspaceActionMeta[pendingWorkspaceAction].body}</p>
                        <div className="mt-4 grid gap-2 sm:grid-cols-2">
                          <div className="rounded-xl border border-white/5 bg-black/20 p-3">
                            <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Backend path</p>
                            <p className="mt-1 text-xs font-bold text-white">{methodLabel}</p>
                          </div>
                          <div className="rounded-xl border border-white/5 bg-black/20 p-3">
                            <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Wallet</p>
                            <p className="mt-1 text-xs font-bold text-white">{shortAddress(walletDisplay || "")}</p>
                          </div>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-2">
                          <button className="h-10 rounded-xl border border-white/10 bg-white/10 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-white transition hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50" onClick={confirmWorkspaceAction} disabled={busyAction === pendingWorkspaceAction}>
                            {busyAction === pendingWorkspaceAction ? "Working" : "Confirm"}
                          </button>
                          <button className="h-10 rounded-xl border border-white/10 bg-white/5 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-white transition hover:bg-white/10" onClick={() => setPendingWorkspaceAction(null)}>
                            Cancel
                          </button>
                        </div>
                      </article>
                    ) : pendingFixBlocker ? (
                      <article className={`rounded-2xl border p-4 ${blockerFixDescriptor(pendingFixBlocker)?.tone || "border-amber-400/20 bg-amber-500/10"}`}>
                        <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Fix blocker</p>
                        <h4 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">{blockerFixDescriptor(pendingFixBlocker)?.title || "Review blocker"}</h4>
                        <p className="mt-2 text-xs leading-5 text-zinc-300">{blockerFixDescriptor(pendingFixBlocker)?.body || pendingFixBlocker}</p>
                        <div className="mt-4 rounded-xl border border-white/5 bg-black/20 p-3">
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Current blocker</p>
                          <p className="mt-1 text-xs font-bold text-white">{pendingFixBlocker}</p>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-2">
                          <button className="h-10 rounded-xl border border-white/10 bg-white/10 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-white transition hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50" onClick={confirmBlockerFix} disabled={busyAction === `fix:${pendingFixBlocker}`}>
                            {busyAction === `fix:${pendingFixBlocker}` ? "Applying" : blockerFixDescriptor(pendingFixBlocker)?.label || "Apply"}
                          </button>
                          <button className="h-10 rounded-xl border border-white/10 bg-white/5 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-white transition hover:bg-white/10" onClick={() => setPendingFixBlocker(null)}>
                            Cancel
                          </button>
                        </div>
                      </article>
                    ) : (
                      <article className="rounded-2xl border border-white/5 bg-black/20 p-4">
                        <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Blockers & readiness</p>
                        <div className="mt-3 space-y-2">
                          {setupWarnings.length ? setupWarnings.map((warning) => {
                            const fix = blockerFixDescriptor(warning);
                            return (
                              <div key={warning} className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-3">
                                <p className="text-xs font-bold text-amber-100">{warning}</p>
                                {fix ? (
                                  <button className="mt-3 h-8 rounded-lg border border-white/10 bg-white/10 px-3 text-[10px] font-black uppercase tracking-[0.2em] text-white transition hover:bg-white/15" onClick={() => setPendingFixBlocker(warning)}>
                                    {fix.label}
                                  </button>
                                ) : null}
                              </div>
                            );
                          }) : <p className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs font-bold text-emerald-100">No current blockers are reported for this backend.</p>}
                        </div>
                      </article>
                    )}
                    <article className="rounded-2xl border border-white/5 bg-black/20 p-4">
                      <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Capability summary</p>
                      <div className="mt-3 grid gap-2 sm:grid-cols-2">
                        <div className="rounded-xl border border-white/5 bg-black/25 p-3">
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Backend health</p>
                          <p className="mt-1 text-xs font-bold text-white">{backendHealth}</p>
                        </div>
                        <div className="rounded-xl border border-white/5 bg-black/25 p-3">
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Supports auto-buy</p>
                          <p className="mt-1 text-xs font-bold text-white">{signerSupportsAutoBuy ? "yes" : "no"}</p>
                        </div>
                        <div className="rounded-xl border border-white/5 bg-black/25 p-3">
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Supports auto-sell</p>
                          <p className="mt-1 text-xs font-bold text-white">{signerSupportsAutoSell ? "yes" : "no"}</p>
                        </div>
                        <div className="rounded-xl border border-white/5 bg-black/25 p-3">
                          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Transport</p>
                          <p className="mt-1 text-xs font-bold text-white">{String(liveStatus?.signer?.transport || "localhost_http")}</p>
                        </div>
                      </div>
                    </article>
                  </div>
                </div>
              </section>

              <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
                <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
                  <div className="mb-4 flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Intent desk</p>
                      <h3 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">Queue & Intent Review</h3>
                      <p className="mt-1 text-xs text-zinc-400">Build manual candidates, generate strategy intents, then quote or cancel from one place.</p>
                    </div>
                    <Bot size={18} className="text-amber-400" />
                  </div>
                  <div className="mb-4 flex flex-wrap gap-2">
                    <button className="h-9 rounded-xl border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-[0.22em] text-white transition hover:bg-white/10" onClick={onCreateManualIntent}>Create Manual Intent</button>
                    <button className="h-9 rounded-xl border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-[0.22em] text-white transition hover:bg-white/10" onClick={onGenerateIntents}>Generate Strategy Intents</button>
                  </div>
                  <div className="max-h-[26rem] space-y-2 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                    {liveIntents.slice(0, 10).map((intent) => (
                      <article key={intent.id} className="rounded-xl border border-white/5 bg-black/25 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <strong className="block truncate text-xs font-black uppercase tracking-[0.18em] text-white">{intent.action} / {intent.symbol || intent.mint.slice(0, 8)} / {intent.status}</strong>
                            <span className="mt-1 block truncate text-[10px] font-bold uppercase tracking-[0.22em] text-zinc-500">{intent.source} / rank {intent.priority.toFixed(0)} / expires {intent.expires_at ? new Date(intent.expires_at).toLocaleTimeString() : "-"}</span>
                          </div>
                          {intent.generated_from_position ? <span className="rounded-full border border-amber-400/20 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-amber-100">Protective exit</span> : null}
                        </div>
                        <p className="mt-2 text-xs text-zinc-400">{intent.reason || "Live intent candidate"}</p>
                        {intent.autonomy_blocked ? <div className="mt-2 flex flex-wrap gap-2">{intent.autonomy_blockers.map((blocker) => <span key={blocker} className="rounded-full border border-amber-400/20 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-amber-100">{blocker}</span>)}</div> : null}
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button className="h-8 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-[0.2em] text-white disabled:cursor-not-allowed disabled:opacity-50" onClick={() => onQuoteIntent(intent.id)} disabled={quoteBlocked || intent.status === "cancelled"}>Quote</button>
                          <button className="h-8 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-[0.2em] text-white" onClick={() => onCancelIntent(intent.id)}>Cancel</button>
                        </div>
                      </article>
                    ))}
                    {!liveIntents.length ? <p className="rounded-xl border border-white/5 bg-black/25 p-3 text-xs text-zinc-500">No active live intents yet.</p> : null}
                  </div>
                </section>

                <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
                  <div className="mb-4 flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Execution</p>
                      <h3 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">Quote Preview & Submission</h3>
                      <p className="mt-1 text-xs text-zinc-400">Keep quote, simulation, and sign/send actions together with the active audit state and stale-quote warnings.</p>
                    </div>
                    <Target size={18} className="text-amber-400" />
                  </div>
                  <div className="grid gap-3 md:grid-cols-3">
                    <label className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Action<select className="dashboard-select mt-1 h-10 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-xs font-bold normal-case tracking-normal text-white" value={liveAction} onChange={(event) => onLiveActionChange(event.target.value as "buy" | "sell")}><option value="buy">buy</option><option value="sell">sell</option></select></label>
                    <label className="md:col-span-2 text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Mint<input className="mt-1 h-10 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-xs font-bold normal-case tracking-normal text-white placeholder-zinc-600" value={liveMint} onChange={(event) => onLiveMintChange(event.target.value)} placeholder="Pump.fun mint address" /></label>
                    <label className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Amount<input className="mt-1 h-10 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-xs font-bold normal-case tracking-normal text-white placeholder-zinc-600" value={liveAmount} onChange={(event) => onLiveAmountChange(event.target.value)} placeholder={liveAction === "sell" ? "100%" : "0.001"} /></label>
                    <label className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Slippage %<input className="mt-1 h-10 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-xs font-bold text-white" type="number" min="0.001" step="0.1" value={liveSlippage} onChange={(event) => onLiveSlippageChange(Number(event.target.value))} /></label>
                    <label className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Priority fee SOL<input className="mt-1 h-10 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-xs font-bold text-white" type="number" min="0.00001" step="0.00001" value={livePriorityFee} onChange={(event) => onLivePriorityFeeChange(Number(event.target.value))} /></label>
                    <label className="text-[10px] font-black uppercase tracking-[0.22em] text-zinc-500">Pool<select className="dashboard-select mt-1 h-10 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-xs font-bold normal-case tracking-normal text-white" value={livePool} onChange={(event) => onLivePoolChange(event.target.value)}>{["pump", "auto", "raydium", "pump-amm", "launchlab", "raydium-cpmm", "bonk"].map((pool) => <option key={pool} value={pool}>{pool}</option>)}</select></label>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button className="h-9 rounded-xl border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-[0.22em] text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50" onClick={onCreateLivePreview} disabled={quoteBlocked}>Create Preview</button>
                    <button className="h-9 rounded-xl border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-[0.22em] text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50" onClick={onSimulateActiveAudit} disabled={!activeLiveAudit || !activeLiveAudit.quote.unsigned_transaction_base64}>Simulate</button>
                    <button className="h-9 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 text-[10px] font-black uppercase tracking-[0.22em] text-rose-100 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-50" onClick={onSignAndSendLive} disabled={quoteBlocked || activeQuoteStale || !activeLiveAudit || !activeLiveAudit.quote.unsigned_transaction_base64}>Sign & Send</button>
                  </div>
                  {!envEnabled ? <p className="mt-3 rounded-xl border border-amber-400/20 bg-amber-500/10 p-3 text-xs font-bold text-amber-100">Live env is disabled, so quotes and signing are blocked. Wallet checks and setup still work.</p> : null}
                  {activeLiveAudit ? (
                    <article className="mt-3 rounded-xl border border-white/5 bg-black/25 p-3">
                      <strong className="block text-xs font-black uppercase tracking-[0.18em] text-white">{activeLiveAudit.action} / {activeLiveAudit.amount} / {activeLiveAudit.status}</strong>
                      <span className="mt-1 block truncate text-xs text-zinc-400">{activeLiveAudit.transaction_signature ? `Signature ${activeLiveAudit.transaction_signature}` : "No signature submitted yet"}</span>
                      <span className="mt-1 block text-xs text-zinc-400">Simulation: {String(activeLiveAudit.simulation?.status ?? "not run")} / Reconciliation: {activeLiveAudit.reconciliation_status ?? "pending"}</span>
                      <p className="mt-2 text-xs text-zinc-500">{[...activeLiveAudit.warnings, ...activeLiveAudit.errors].join(" / ") || activeLiveAudit.final_status}</p>
                      {activeQuoteStale ? <p className="mt-2 text-xs font-bold text-amber-100">This quote is stale. Refresh the preview before signing.</p> : null}
                    </article>
                  ) : <p className="mt-3 rounded-xl border border-white/5 bg-black/25 p-3 text-xs text-zinc-500">No active quote preview yet.</p>}
                </section>
              </div>

              <section className="rounded-2xl border border-amber-400/20 bg-amber-500/[0.045] p-4">
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Recovery</p>
                    <h3 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">Recovery & Review</h3>
                    <p className="mt-1 text-xs text-zinc-400">Backend-assisted confirmation only checks recorded signatures and wallet/RPC reconciliation. It never signs, sends, or resubmits.</p>
                  </div>
                  <button className="h-9 rounded-xl border border-amber-400/30 bg-amber-500/10 px-3 text-[10px] font-black uppercase tracking-[0.22em] text-amber-100 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50" onClick={onRecoverAllLiveAudits} disabled={!reviewAudits.length}>Recover Unresolved</button>
                </div>
                <div className="mb-3 grid gap-2 sm:grid-cols-4">
                  <span className="rounded-xl border border-white/5 bg-black/25 p-3 text-[10px] font-bold uppercase tracking-[0.22em] text-zinc-400">Unresolved <strong className="block pt-1 text-xs text-white">{liveStatus?.unresolved_audit_count ?? reviewAudits.length}</strong></span>
                  <span className="rounded-xl border border-white/5 bg-black/25 p-3 text-[10px] font-bold uppercase tracking-[0.22em] text-zinc-400">Recoverable <strong className="block pt-1 text-xs text-white">{liveStatus?.recoverable_audit_count ?? reviewAudits.filter((audit) => audit.transaction_signature).length}</strong></span>
                  <span className="rounded-xl border border-white/5 bg-black/25 p-3 text-[10px] font-bold uppercase tracking-[0.22em] text-zinc-400">Poller <strong className="block truncate pt-1 text-xs text-white">{liveStatus?.poller_status ?? "unknown"}</strong></span>
                  <span className="rounded-xl border border-white/5 bg-black/25 p-3 text-[10px] font-bold uppercase tracking-[0.22em] text-zinc-400">Last check <strong className="block truncate pt-1 text-xs text-white">{liveStatus?.last_live_poll_at ? new Date(liveStatus.last_live_poll_at).toLocaleTimeString() : "not run"}</strong></span>
                </div>
                <p className="mb-3 rounded-xl border border-white/5 bg-black/20 p-3 text-xs text-zinc-400">Recovery summary: checked {Number(recoverySummary?.checked ?? 0)}, updated {Number(recoverySummary?.updated ?? 0)}{recoverySummary?.reason ? ` / ${recoverySummary.reason}` : ""}</p>
                <div className="grid max-h-72 gap-2 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent lg:grid-cols-2">
                  {reviewAudits.slice(0, 8).map((audit) => (
                    <article key={audit.id} className="rounded-xl border border-white/5 bg-black/25 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <strong className="block truncate text-xs font-black uppercase tracking-[0.18em] text-white">{audit.action} / {audit.status} / {audit.reconciliation_status ?? "pending"}</strong>
                          <span className="mt-1 block truncate text-[10px] font-bold uppercase tracking-[0.22em] text-zinc-500">{audit.transaction_signature || "missing signature"}</span>
                        </div>
                        <button className="h-8 shrink-0 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-[0.2em] text-white transition hover:bg-white/10" onClick={() => onRecoverLiveAudit(audit.id)}>Retry</button>
                      </div>
                      <div className="mt-2 grid gap-2 text-[11px] text-zinc-400 sm:grid-cols-3">
                        <span>RPC: {audit.confirmation_status || String(audit.confirmation?.confirmation_status ?? "unknown")}</span>
                        <span>Attempts: {audit.recovery_attempts ?? 0}</span>
                        <span>Checked: {audit.confirmation_checked_at ? new Date(audit.confirmation_checked_at).toLocaleTimeString() : "not run"}</span>
                      </div>
                      {audit.last_recovery_error ? <p className="mt-2 text-xs text-amber-100">{audit.last_recovery_error}</p> : null}
                      <p className="mt-2 text-xs text-zinc-500">{audit.recommended_action || "Review the audit row before taking any wallet action."}</p>
                    </article>
                  ))}
                  {!reviewAudits.length ? <p className="rounded-xl border border-white/5 bg-black/25 p-3 text-xs text-zinc-500">No unresolved live audits need recovery.</p> : null}
                </div>
              </section>

              <div className="grid gap-4 lg:grid-cols-2">
                <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
                  <div className="mb-4 flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Positions</p>
                      <h3 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">Wallet Positions</h3>
                      <p className="mt-1 text-xs text-zinc-400">RPC token balances for mints touched by live audit records.</p>
                    </div>
                    <Database size={18} className="text-amber-400" />
                  </div>
                  <div className="max-h-64 space-y-2 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                    {(liveLedger?.positions ?? []).slice(0, 6).map((position) => (
                      <article key={position.id} className="rounded-xl border border-white/5 bg-black/25 p-3">
                        <strong className="block text-xs font-black uppercase tracking-[0.18em] text-white">{position.symbol || position.mint.slice(0, 8)} / {position.status} / {position.token_balance}</strong>
                        <span className="mt-1 block text-xs text-zinc-400">Cost {position.cost_basis_sol.toFixed(6)} SOL / Realized {position.realized_pnl_sol.toFixed(6)} SOL / Recon {position.reconciliation_status}</span>
                        <p className="mt-2 truncate text-xs text-zinc-500">{position.mint}</p>
                      </article>
                    ))}
                    {livePositions.slice(0, 6).map((position) => (
                      <article key={position.mint} className="rounded-xl border border-white/5 bg-black/25 p-3">
                        <strong className="block text-xs font-black uppercase tracking-[0.18em] text-white">{position.symbol || position.mint.slice(0, 8)} / {position.token_balance}</strong>
                        <span className="mt-1 block truncate text-xs text-zinc-500">{position.mint}</span>
                        {position.warning ? <p className="mt-2 text-xs text-amber-100">{position.warning}</p> : null}
                      </article>
                    ))}
                    {!livePositions.length && !(liveLedger?.positions.length) ? <p className="rounded-xl border border-white/5 bg-black/25 p-3 text-xs text-zinc-500">No live wallet positions loaded.</p> : null}
                  </div>
                </section>

                <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
                  <div className="mb-4 flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">Audit</p>
                      <h3 className="mt-1 text-sm font-black uppercase tracking-[0.18em] text-white">Latest Audit</h3>
                      <p className="mt-1 text-xs text-zinc-400">Recent quote, simulation, submission, and reconciliation records.</p>
                    </div>
                    <Activity size={18} className="text-amber-400" />
                  </div>
                  <div className="max-h-64 space-y-2 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                    {liveAudit.slice(0, 6).map((audit) => (
                      <article key={audit.id} className="rounded-xl border border-white/5 bg-black/25 p-3">
                        <strong className="block text-xs font-black uppercase tracking-[0.18em] text-white">{audit.action} / {audit.status} / {audit.reconciliation_status ?? "pending"}</strong>
                        <span className="mt-1 block truncate text-xs text-zinc-400">{audit.transaction_signature ? `Signature ${audit.transaction_signature}` : audit.wallet_public_key || "No wallet recorded"}</span>
                        <p className="mt-2 text-xs text-zinc-500">{[...audit.warnings, ...audit.errors].join(" / ") || audit.final_status}</p>
                      </article>
                    ))}
                    {!liveAudit.length ? <p className="rounded-xl border border-white/5 bg-black/25 p-3 text-xs text-zinc-500">No live audit records yet.</p> : null}
                  </div>
                </section>
              </div>
            </div>
          )}
        </div>

        {!workspaceVisible ? (
          <div className="border-t border-white/10 bg-[#0d0f18]/95 px-5 py-4 backdrop-blur-xl">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <button className="h-10 rounded-xl border border-white/10 bg-white/5 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-white transition hover:border-white/20 hover:bg-white/10" onClick={stepIndex === 0 ? onClose : () => setStepIndex((current) => Math.max(0, current - 1))}>{stepIndex === 0 ? "Cancel" : "Back"}</button>
              <div className="flex flex-wrap gap-2">
                {stepIndex === 4 ? <button className="h-10 rounded-xl border border-white/10 bg-white/5 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-white transition hover:border-white/20 hover:bg-white/10" onClick={() => setStepIndex(0)}>Switch Path</button> : null}
                <button className="h-10 rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 text-[10px] font-black uppercase tracking-[0.24em] text-amber-100 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50" onClick={handleStepPrimary} disabled={(stepIndex === 1 && method === "local_signer_daemon" && !connectionReady) || busyAction === "step" || busyAction === "confirm"}>
                  {stepIndex === 0 ? "Continue" : stepIndex === 1 ? method === "browser_wallet" ? busyAction === "step" ? "Connecting" : walletPublicKey ? "Continue" : "Connect" : method === "local_hot_wallet" ? busyAction === "step" ? hotWalletStatus?.imported ? "Unlocking" : "Importing" : hotWalletStatus?.unlocked ? "Continue" : hotWalletStatus?.imported ? "Unlock" : "Import" : "Continue" : stepIndex === 2 ? "Continue" : stepIndex === 3 ? busyAction === "confirm" ? "Confirming" : "Confirm" : "Enter Workspace"}
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </motion.section>
    </div>
  );
}

function LegacyLiveWalletModal({
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
  onArmBackend,
  onDisarmBackend,
  hotWalletStatus,
  hotWalletPrivateKey,
  hotWalletPassword,
  hotWalletLabel,
  onHotWalletPrivateKeyChange,
  onHotWalletPasswordChange,
  onHotWalletLabelChange,
  onImportHotWallet,
  onUnlockHotWallet,
  onLockHotWallet,
  onClearHotWallet,
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
  onSignAndSendLive,
  onRecoverAllLiveAudits,
  onRecoverLiveAudit
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
  onArmBackend: () => Promise<void>;
  onDisarmBackend: () => Promise<void>;
  hotWalletStatus: HotWalletStatus | null;
  hotWalletPrivateKey: string;
  hotWalletPassword: string;
  hotWalletLabel: string;
  onHotWalletPrivateKeyChange: (value: string) => void;
  onHotWalletPasswordChange: (value: string) => void;
  onHotWalletLabelChange: (value: string) => void;
  onImportHotWallet: () => Promise<void>;
  onUnlockHotWallet: () => Promise<void>;
  onLockHotWallet: () => Promise<void>;
  onClearHotWallet: () => Promise<void>;
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
  onRecoverAllLiveAudits: () => Promise<void>;
  onRecoverLiveAudit: (auditId: string) => Promise<void>;
}) {
  const capsSet = settings.live_max_trade_sol > 0 && settings.live_daily_loss_cap_sol > 0 && settings.live_wallet_exposure_cap_sol > 0 && settings.live_max_open_positions > 0 && settings.live_max_slippage_pct > 0 && settings.live_priority_fee_cap_sol > 0;
  const envEnabled = Boolean(liveStatus?.env_live_enabled);
  const walletDisplay = method === "local_hot_wallet" ? hotWalletStatus?.wallet_public_key || settings.live_hot_wallet_public_key : liveStatus?.signer?.wallet_public_key || walletPublicKey;
  const quoteBlocked = !envEnabled;
  const blockers = liveStatus?.blockers?.length ? liveStatus.blockers : envEnabled ? [] : ["Live environment flag is disabled"];
  const activeQuoteStale = activeLiveAudit?.status === "stale" || Boolean(activeLiveAudit?.quote?.stale);
  const recoverableAuditStatuses = new Set(["submitted", "failed", "needs_review", "stale"]);
  const reviewAudits = liveAudit.filter((audit) => recoverableAuditStatuses.has(audit.status) || audit.reconciliation_status === "needs_review");
  const recoverySummary = liveStatus?.recovery_summary;
  const autonomyBlockers = liveStatus?.autonomy_blockers ?? [];
  const readinessScore = liveStatus?.readiness?.score ?? 0;
  const readinessState = liveStatus?.readiness?.status?.replace(/_/g, " ") ?? "unknown";
  const signerDisabledReason = liveStatus?.signer?.disabled_reason || liveStatus?.wallet_adapter?.disabled_reason || "";
  const signerSupportsAutoSell = Boolean(liveStatus?.signer?.supports_auto_sell);
  const signerSupportsAutoBuy = Boolean(liveStatus?.signer?.supports_auto_buy);
  const activeBackend = liveStatus?.active_backend;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-md">
      <motion.section
        initial={{ opacity: 0, scale: 0.97, y: 18 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 18 }}
        transition={{ type: "spring", stiffness: 360, damping: 32 }}
        className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-white/10 bg-[#0a0c13]/95 shadow-2xl shadow-black/70"
      >
        <div className="sticky top-0 z-10 border-b border-white/10 bg-[#0d0f18]/95 px-5 py-4 backdrop-blur-xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.28em] text-amber-400">Local live execution</p>
              <h3 className="mt-1 text-2xl font-black tracking-tight text-white">Live Wallet</h3>
              <p className="mt-1 max-w-3xl text-xs font-medium text-zinc-400">
                Unified control plane for assisted browser-wallet execution, encrypted local hot wallet signing, and localhost signer-daemon autonomy.
              </p>
            </div>
            <button
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-zinc-400 transition hover:border-amber-500/40 hover:text-white"
              onClick={onClose}
              aria-label="Close live wallet"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto p-5 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
          <div className="grid gap-4 lg:grid-cols-3">
            <button
              className={`rounded-xl border p-4 text-left transition ${
                method === "browser_wallet"
                  ? "border-emerald-400/50 bg-emerald-500/10 shadow-lg shadow-emerald-500/10"
                  : "border-white/10 bg-white/[0.03] hover:border-white/20"
              }`}
              onClick={() => onMethodChange("browser_wallet")}
            >
              <div className="flex items-center justify-between gap-3">
                <strong className="text-sm font-black uppercase tracking-widest text-white">Browser wallet</strong>
                <span className="rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-emerald-300">Assisted</span>
              </div>
              <span className="mt-2 block text-xs leading-5 text-zinc-400">Phantom-first assisted mode. Manual approvals remain required unless the browser environment exposes true unattended capabilities.</span>
            </button>
            <button
              className={`rounded-xl border p-4 text-left transition ${
                method === "local_hot_wallet"
                  ? "border-amber-400/50 bg-amber-500/10 shadow-lg shadow-amber-500/10"
                  : "border-white/10 bg-white/[0.03] hover:border-white/20"
              }`}
              onClick={() => onMethodChange("local_hot_wallet")}
            >
              <div className="flex items-center justify-between gap-3">
                <strong className="text-sm font-black uppercase tracking-widest text-white">Local hot wallet</strong>
                <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-amber-200">
                  {hotWalletStatus?.unlocked ? "Unlocked" : hotWalletStatus?.imported ? "Locked" : "Import"}
                </span>
              </div>
              <span className="mt-2 block text-xs leading-5 text-zinc-400">Encrypted-at-rest local key import with password unlock per app start for unattended entries and exits.</span>
            </button>
            <button
              className={`rounded-xl border p-4 text-left transition ${
                method === "local_signer_daemon"
                  ? "border-sky-400/50 bg-sky-500/10 shadow-lg shadow-sky-500/10"
                  : "border-white/10 bg-white/[0.03] hover:border-white/20"
              }`}
              onClick={() => onMethodChange("local_signer_daemon")}
            >
              <div className="flex items-center justify-between gap-3">
                <strong className="text-sm font-black uppercase tracking-widest text-white">Local signer daemon</strong>
                <span className="rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-sky-200">
                  {liveStatus?.backend_capabilities?.local_signer_daemon?.healthy ? "Healthy" : "Daemon"}
                </span>
              </div>
              <span className="mt-2 block text-xs leading-5 text-zinc-400">Separate localhost signer backend for unattended execution when its own health/auth contract is satisfied.</span>
            </button>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[0.85fr_1.15fr]">
            <div className="space-y-4">
              <section className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-black uppercase tracking-widest text-white">Backend Access</h3>
                    <p className="mt-1 text-xs text-zinc-400">Use the wallet path that matches how you want execution to happen: assisted browser approval, encrypted local signing, or a separate localhost signer daemon.</p>
                  </div>
                  <Wallet size={18} className="text-amber-400" />
                </div>
                <button
                  className="mb-4 h-10 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 text-xs font-black uppercase tracking-widest text-amber-300 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={onConnectWallet}
                  disabled={method !== "browser_wallet"}
                >
                  {walletPublicKey ? "Reconnect Browser Wallet" : "Connect Browser Wallet"}
                </button>
                {method === "local_hot_wallet" ? (
                  <div className="mb-4 space-y-3 rounded-xl border border-white/5 bg-black/20 p-3">
                    <input className="h-10 w-full rounded-lg border border-white/10 bg-black/40 px-3 text-xs font-bold text-white placeholder-zinc-600" value={hotWalletLabel} onChange={(event) => onHotWalletLabelChange(event.target.value)} placeholder="Wallet label (optional)" />
                    {!hotWalletStatus?.imported ? (
                      <textarea className="min-h-[88px] w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-xs font-bold text-white placeholder-zinc-600" value={hotWalletPrivateKey} onChange={(event) => onHotWalletPrivateKeyChange(event.target.value)} placeholder="Base58 private key or byte array" />
                    ) : null}
                    <input className="h-10 w-full rounded-lg border border-white/10 bg-black/40 px-3 text-xs font-bold text-white placeholder-zinc-600" type="password" value={hotWalletPassword} onChange={(event) => onHotWalletPasswordChange(event.target.value)} placeholder={hotWalletStatus?.imported ? "Unlock password" : "Encryption password"} />
                    <div className="flex flex-wrap gap-2">
                      {!hotWalletStatus?.imported ? <button className="h-9 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 text-[10px] font-black uppercase tracking-widest text-amber-200" onClick={onImportHotWallet}>Import & Encrypt</button> : null}
                      {hotWalletStatus?.imported && !hotWalletStatus?.unlocked ? <button className="h-9 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 text-[10px] font-black uppercase tracking-widest text-amber-200" onClick={onUnlockHotWallet}>Unlock</button> : null}
                      {hotWalletStatus?.unlocked ? <button className="h-9 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-widest text-white" onClick={onLockHotWallet}>Lock</button> : null}
                      {hotWalletStatus?.imported ? <button className="h-9 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 text-[10px] font-black uppercase tracking-widest text-rose-200" onClick={onClearHotWallet}>Clear Stored Key</button> : null}
                    </div>
                  </div>
                ) : null}
                <div className="grid gap-2 sm:grid-cols-2">
                  {[
                    ["Wallet", shortAddress(walletDisplay || "")],
                    ["SOL balance", walletBalanceSol === null ? "-" : `${walletBalanceSol.toFixed(4)} SOL`],
                    ["Live env", envEnabled ? "enabled" : "disabled"],
                    ["Caps", capsSet ? "set" : "required"],
                    ["Acknowledgement", settings.live_session_acknowledged ? "done" : "needed"],
                    ["Live gates", liveStatus?.live_execution_available ? "open" : "blocked"],
                    ["Auto-sell", liveStatus?.auto_sell_available ? "available" : "blocked"],
                    ["Auto-buy", liveStatus?.auto_buy_available ? "available" : "blocked"]
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg border border-white/5 bg-black/25 p-3">
                      <p className="text-[10px] font-black uppercase tracking-widest text-zinc-500">{label}</p>
                      <p className="mt-1 truncate text-xs font-bold text-white">{value}</p>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-black uppercase tracking-widest text-white">Blockers & Caps</h3>
                    <p className="mt-1 text-xs text-zinc-400">Review the current gate state before creating a quote preview.</p>
                  </div>
                  <Shield size={18} className="text-amber-400" />
                </div>
                <div className="space-y-2">
                  {blockers.length ? blockers.map((blocker) => (
                    <article key={blocker} className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-3 text-xs font-bold text-rose-200">
                      {blocker}
                    </article>
                  )) : (
                    <article className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs font-bold text-emerald-200">
                      Live execution prerequisites are passing for the selected backend.
                    </article>
                  )}
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    className="h-10 rounded-lg border border-white/10 bg-white/5 px-4 text-xs font-black uppercase tracking-widest text-white transition hover:border-white/20 hover:bg-white/10"
                    onClick={onAcknowledgeLive}
                  >
                    Acknowledge Risk
                  </button>
                  <button
                    className="h-10 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-4 text-xs font-black uppercase tracking-widest text-emerald-200 transition hover:bg-emerald-500/20"
                    onClick={onArmBackend}
                  >
                    Arm Backend
                  </button>
                  <button
                    className="h-10 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 text-xs font-black uppercase tracking-widest text-rose-200 transition hover:bg-rose-500/20"
                    onClick={onDisarmBackend}
                  >
                    Disarm
                  </button>
                </div>
              </section>

              <section className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-black uppercase tracking-widest text-white">Autonomy Control Plane</h3>
                    <p className="mt-1 text-xs text-zinc-400">One backend can be armed at a time. New entries stop when gates fail; protective exits can still flow if the active backend can execute them.</p>
                  </div>
                  <Bot size={18} className="text-amber-400" />
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {[
                    ["Manual signing", liveStatus?.signer?.can_sign ? "available" : "not connected"],
                    ["Backend health", liveStatus?.signer?.healthy ? "healthy" : "degraded"],
                    ["Unattended signing", liveStatus?.signer?.can_unattended_sign ? "available" : "disabled"],
                    ["Supports auto-sell", signerSupportsAutoSell ? "yes" : "no"],
                    ["Supports auto-buy", signerSupportsAutoBuy ? "yes" : "no"],
                    ["Readiness", `${readinessScore}% / ${readinessState}`],
                    ["Signer mode", method.replace(/_/g, " ")],
                    ["Daemon transport", String(liveStatus?.signer?.transport || "localhost_http")],
                    ["Daemon auth", liveStatus?.signer?.auth_configured ? "configured" : "not set"],
                    ["Armed backend", activeBackend?.armed ? `${activeBackend.mode.replace(/_/g, " ")} / ${shortAddress(activeBackend.wallet_public_key)}` : "not armed"],
                    ["Auto entries", liveStatus?.entry_autonomy_available ? "enabled" : "blocked"],
                    ["Protective exits", liveStatus?.exit_autonomy_available ? "enabled" : "blocked"]
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg border border-white/5 bg-black/25 p-3">
                      <p className="text-[10px] font-black uppercase tracking-widest text-zinc-500">{label}</p>
                      <p className="mt-1 text-xs font-bold text-white">{value}</p>
                    </div>
                  ))}
                </div>
                {liveStatus?.signer?.endpoint ? (
                  <p className="mt-3 rounded-lg border border-white/5 bg-black/20 p-3 text-xs text-zinc-400 break-all">
                    Daemon endpoint: {liveStatus.signer.endpoint}
                  </p>
                ) : null}
                {signerDisabledReason ? (
                  <p className="mt-3 rounded-lg border border-white/5 bg-black/20 p-3 text-xs text-zinc-400">{signerDisabledReason}</p>
                ) : null}
                <div className="mt-3 space-y-2">
                  {autonomyBlockers.map((blocker) => (
                    <article key={blocker} className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs font-bold text-amber-100">
                      {blocker}
                    </article>
                  ))}
                  {!autonomyBlockers.length ? (
                    <article className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs font-bold text-emerald-200">
                      Autonomous execution gates are currently clear for the selected backend.
                    </article>
                  ) : null}
                </div>
              </section>
            </div>

            <div className="space-y-4">
              <section className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-black uppercase tracking-widest text-white">Intent Queue</h3>
                    <p className="mt-1 text-xs text-zinc-400">Paper-promoted, watchlist, manual, and risk-generated live-position intents. Quotes expire after 30 seconds.</p>
                  </div>
                  <Sparkles size={18} className="text-amber-400" />
                </div>
                <div className="mb-3 flex flex-wrap gap-2">
                  <button className="h-9 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-widest text-white transition hover:bg-white/10" onClick={onGenerateIntents}>Generate Intents</button>
                  <button className="h-9 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-widest text-white transition hover:bg-white/10" onClick={onCreateManualIntent}>Add Manual Intent</button>
                </div>
                <div className="mb-3 grid gap-2 sm:grid-cols-4">
                  <span className="rounded-lg border border-white/5 bg-black/25 p-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Active <strong className="block pt-1 text-xs text-white">{liveStatus?.active_intent_count ?? liveIntents.length}</strong></span>
                  <span className="rounded-lg border border-white/5 bg-black/25 p-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Stale <strong className="block pt-1 text-xs text-white">{liveStatus?.stale_quote_count ?? 0}</strong></span>
                  <span className="rounded-lg border border-white/5 bg-black/25 p-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Risk exits <strong className="block pt-1 text-xs text-white">{liveIntents.filter((intent) => intent.generated_from_position).length}</strong></span>
                  <span className="rounded-lg border border-white/5 bg-black/25 p-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Realized <strong className="block pt-1 text-xs text-white">{(liveLedger?.summary.realized_pnl_sol ?? liveStatus?.live_pnl?.realized_pnl_sol ?? 0).toFixed(6)} SOL</strong></span>
                </div>
                <div className="max-h-72 space-y-2 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                  {liveIntents.slice(0, 10).map((intent) => (
                    <article key={intent.id} className={`rounded-lg border p-3 ${activeLiveIntentId === intent.id ? "border-amber-500/40 bg-amber-500/10" : "border-white/5 bg-black/25"}`}>
                      <strong className="block text-xs font-black uppercase tracking-widest text-white">{intent.action} / {intent.symbol || intent.mint.slice(0, 8)} / {intent.status}</strong>
                      <span className="mt-1 block text-[10px] font-bold uppercase tracking-widest text-zinc-500">{intent.source} / rank {intent.priority.toFixed(0)} / score {intent.score} / expires {intent.expires_at ? new Date(intent.expires_at).toLocaleTimeString() : "-"}</span>
                      <p className="mt-2 text-xs text-zinc-400">{intent.reason || "Live intent candidate"}</p>
                      {intent.priority_reason ? <p className="mt-2 text-[11px] text-zinc-500">{intent.priority_reason}</p> : null}
                      {intent.generated_from_position ? (
                        <span className="mt-2 inline-flex rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-amber-100">
                          Risk-generated position exit
                        </span>
                      ) : null}
                      {intent.autonomy_blocked ? (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {intent.autonomy_blockers.map((blocker) => (
                            <span key={blocker} className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-amber-100">
                              {blocker}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {intent.operator_recommendation ? <p className="mt-2 text-xs text-zinc-500">{intent.operator_recommendation}</p> : null}
                      <div className="mt-3 flex gap-2">
                        <button className="h-8 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-widest text-white disabled:cursor-not-allowed disabled:opacity-50" onClick={() => onQuoteIntent(intent.id)} disabled={quoteBlocked || intent.status === "cancelled"}>Quote</button>
                        <button className="h-8 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-widest text-white" onClick={() => onCancelIntent(intent.id)}>Cancel</button>
                      </div>
                    </article>
                  ))}
                  {!liveIntents.length ? <p className="rounded-lg border border-white/5 bg-black/25 p-3 text-xs text-zinc-500">No active live intents yet.</p> : null}
                </div>
              </section>

              <section className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-black uppercase tracking-widest text-white">Quote Preview</h3>
                    <p className="mt-1 text-xs text-zinc-400">Quotes use PumpPortal local transactions. Browser wallet stays assisted/manual; hot wallet and daemon paths can sign, submit, and reconcile through the backend.</p>
                  </div>
                  <Target size={18} className="text-amber-400" />
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <label className="text-[10px] font-black uppercase tracking-widest text-zinc-500">
                    Action
                    <select className="dashboard-select mt-1 h-10 w-full rounded-lg border border-white/10 bg-black/40 px-3 text-xs font-bold normal-case tracking-normal text-white" value={liveAction} onChange={(event) => onLiveActionChange(event.target.value as "buy" | "sell")}>
                      <option value="buy">buy</option>
                      <option value="sell">sell</option>
                    </select>
                  </label>
                  <label className="md:col-span-2 text-[10px] font-black uppercase tracking-widest text-zinc-500">
                    Mint
                    <input className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-black/40 px-3 text-xs font-bold normal-case tracking-normal text-white placeholder-zinc-600" value={liveMint} onChange={(event) => onLiveMintChange(event.target.value)} placeholder="Pump.fun mint address" />
                  </label>
                  <label className="text-[10px] font-black uppercase tracking-widest text-zinc-500">
                    Amount
                    <input className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-black/40 px-3 text-xs font-bold normal-case tracking-normal text-white placeholder-zinc-600" value={liveAmount} onChange={(event) => onLiveAmountChange(event.target.value)} placeholder={liveAction === "sell" ? "100%" : "0.001"} />
                  </label>
                  <label className="text-[10px] font-black uppercase tracking-widest text-zinc-500">
                    Slippage %
                    <input className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-black/40 px-3 text-xs font-bold normal-case tracking-normal text-white" type="number" min="0.001" step="0.1" value={liveSlippage} onChange={(event) => onLiveSlippageChange(Number(event.target.value))} />
                  </label>
                  <label className="text-[10px] font-black uppercase tracking-widest text-zinc-500">
                    Priority fee SOL
                    <input className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-black/40 px-3 text-xs font-bold normal-case tracking-normal text-white" type="number" min="0.001" step="0.00001" value={livePriorityFee} onChange={(event) => onLivePriorityFeeChange(Number(event.target.value))} />
                  </label>
                  <label className="text-[10px] font-black uppercase tracking-widest text-zinc-500">
                    Pool
                    <select className="dashboard-select mt-1 h-10 w-full rounded-lg border border-white/10 bg-black/40 px-3 text-xs font-bold normal-case tracking-normal text-white" value={livePool} onChange={(event) => onLivePoolChange(event.target.value)}>
                      {["pump", "auto", "raydium", "pump-amm", "launchlab", "raydium-cpmm", "bonk"].map((pool) => <option key={pool} value={pool}>{pool}</option>)}
                    </select>
                  </label>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button className="h-9 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-widest text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50" onClick={onCreateLivePreview} disabled={quoteBlocked}>Create Preview</button>
                  <button className="h-9 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-widest text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50" onClick={onSimulateActiveAudit} disabled={!activeLiveAudit || !activeLiveAudit.quote.unsigned_transaction_base64}>Simulate</button>
                  <button className="h-9 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 text-[10px] font-black uppercase tracking-widest text-rose-200 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-50" onClick={onSignAndSendLive} disabled={quoteBlocked || activeQuoteStale || !activeLiveAudit || !activeLiveAudit.quote.unsigned_transaction_base64}>Sign & Send</button>
                </div>
                {!envEnabled ? <p className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs font-bold text-amber-200">Live env is disabled, so quotes and signing are blocked. Wallet connection and backend status checks still work.</p> : null}
                {liveStatus?.readiness?.status !== "ready" ? <p className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs font-bold text-amber-100">Readiness warnings now hard-block autonomous entries only when the backend gates require it. Manual/assisted flows can still be reviewed here.</p> : null}
                {activeLiveAudit ? (
                  <article className="mt-3 rounded-lg border border-white/5 bg-black/25 p-3">
                    <strong className="block text-xs font-black uppercase tracking-widest text-white">{activeLiveAudit.action} / {activeLiveAudit.amount} / {activeLiveAudit.status}</strong>
                    <span className="mt-1 block truncate text-xs text-zinc-400">{activeLiveAudit.transaction_signature ? `Signature ${activeLiveAudit.transaction_signature}` : "No signature submitted yet"}</span>
                    <span className="mt-1 block text-xs text-zinc-400">Simulation: {String(activeLiveAudit.simulation?.status ?? "not run")} / Reconciliation: {activeLiveAudit.reconciliation_status ?? "pending"}</span>
                    <p className="mt-2 text-xs text-zinc-500">{[...activeLiveAudit.warnings, ...activeLiveAudit.errors].join(" / ") || activeLiveAudit.final_status}</p>
                  </article>
                ) : null}
              </section>
            </div>
          </div>

          <section className="mt-4 rounded-xl border border-amber-400/20 bg-amber-500/[0.045] p-4">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-black uppercase tracking-widest text-white">Recovery & Review</h3>
                <p className="mt-1 text-xs text-zinc-400">Backend-assisted confirmation only checks recorded signatures and wallet/RPC reconciliation. It never signs, sends, or resubmits.</p>
              </div>
              <button
                className="h-9 rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 text-[10px] font-black uppercase tracking-widest text-amber-100 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={onRecoverAllLiveAudits}
                disabled={!reviewAudits.length}
              >
                Recover unresolved
              </button>
            </div>
            <div className="mb-3 grid gap-2 sm:grid-cols-4">
              <span className="rounded-lg border border-white/5 bg-black/25 p-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Unresolved <strong className="block pt-1 text-xs text-white">{liveStatus?.unresolved_audit_count ?? reviewAudits.length}</strong></span>
              <span className="rounded-lg border border-white/5 bg-black/25 p-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Recoverable <strong className="block pt-1 text-xs text-white">{liveStatus?.recoverable_audit_count ?? reviewAudits.filter((audit) => audit.transaction_signature).length}</strong></span>
              <span className="rounded-lg border border-white/5 bg-black/25 p-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Poller <strong className="block truncate pt-1 text-xs text-white">{liveStatus?.poller_status ?? "unknown"}</strong></span>
              <span className="rounded-lg border border-white/5 bg-black/25 p-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Last check <strong className="block truncate pt-1 text-xs text-white">{liveStatus?.last_live_poll_at ? new Date(liveStatus.last_live_poll_at).toLocaleTimeString() : "not run"}</strong></span>
            </div>
            <p className="mb-3 rounded-lg border border-white/5 bg-black/20 p-3 text-xs text-zinc-400">
              Recovery summary: checked {Number(recoverySummary?.checked ?? 0)}, updated {Number(recoverySummary?.updated ?? 0)}
              {recoverySummary?.reason ? ` / ${recoverySummary.reason}` : ""}
            </p>
            <div className="grid max-h-72 gap-2 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent lg:grid-cols-2">
              {reviewAudits.slice(0, 8).map((audit) => (
                <article key={audit.id} className="rounded-lg border border-white/5 bg-black/25 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <strong className="block truncate text-xs font-black uppercase tracking-widest text-white">{audit.action} / {audit.status} / {audit.reconciliation_status ?? "pending"}</strong>
                      <span className="mt-1 block truncate text-[10px] font-bold uppercase tracking-widest text-zinc-500">{audit.transaction_signature || "missing signature"}</span>
                    </div>
                    <button className="h-8 shrink-0 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-black uppercase tracking-widest text-white transition hover:bg-white/10" onClick={() => onRecoverLiveAudit(audit.id)}>Retry</button>
                  </div>
                  <div className="mt-2 grid gap-2 text-[11px] text-zinc-400 sm:grid-cols-3">
                    <span>RPC: {audit.confirmation_status || String(audit.confirmation?.confirmation_status ?? "unknown")}</span>
                    <span>Attempts: {audit.recovery_attempts ?? 0}</span>
                    <span>Checked: {audit.confirmation_checked_at ? new Date(audit.confirmation_checked_at).toLocaleTimeString() : "not run"}</span>
                  </div>
                  {audit.last_recovery_error ? <p className="mt-2 text-xs text-amber-200">{audit.last_recovery_error}</p> : null}
                  <p className="mt-2 text-xs text-zinc-500">{audit.recommended_action || "Review the audit row before taking any wallet action."}</p>
                </article>
              ))}
              {!reviewAudits.length ? <p className="rounded-lg border border-white/5 bg-black/25 p-3 text-xs text-zinc-500">No unresolved live audits need recovery.</p> : null}
            </div>
          </section>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <section className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-black uppercase tracking-widest text-white">Wallet Positions</h3>
                  <p className="mt-1 text-xs text-zinc-400">RPC token balances for mints touched by live audit records.</p>
                </div>
                <Database size={18} className="text-amber-400" />
              </div>
              <div className="max-h-64 space-y-2 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                {(liveLedger?.positions ?? []).slice(0, 6).map((position) => (
                  <article key={position.id} className="rounded-lg border border-white/5 bg-black/25 p-3">
                    <strong className="block text-xs font-black uppercase tracking-widest text-white">{position.symbol || position.mint.slice(0, 8)} / {position.status} / {position.token_balance}</strong>
                    <span className="mt-1 block text-xs text-zinc-400">Cost {position.cost_basis_sol.toFixed(6)} SOL / Realized {position.realized_pnl_sol.toFixed(6)} SOL / Recon {position.reconciliation_status}</span>
                    <p className="mt-2 truncate text-xs text-zinc-500">{position.mint}</p>
                  </article>
                ))}
                {livePositions.slice(0, 6).map((position) => (
                  <article key={position.mint} className="rounded-lg border border-white/5 bg-black/25 p-3">
                    <strong className="block text-xs font-black uppercase tracking-widest text-white">{position.symbol || position.mint.slice(0, 8)} / {position.token_balance}</strong>
                    <span className="mt-1 block truncate text-xs text-zinc-500">{position.mint}</span>
                    {position.warning ? <p className="mt-2 text-xs text-amber-200">{position.warning}</p> : null}
                  </article>
                ))}
                {!livePositions.length && !(liveLedger?.positions.length) ? <p className="rounded-lg border border-white/5 bg-black/25 p-3 text-xs text-zinc-500">No live wallet positions loaded.</p> : null}
              </div>
            </section>

            <section className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-black uppercase tracking-widest text-white">Latest Audit</h3>
                  <p className="mt-1 text-xs text-zinc-400">Recent quote, simulation, submission, and reconciliation records.</p>
                </div>
                <Activity size={18} className="text-amber-400" />
              </div>
              <div className="max-h-64 space-y-2 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                {liveAudit.slice(0, 6).map((audit) => (
                  <article key={audit.id} className="rounded-lg border border-white/5 bg-black/25 p-3">
                    <strong className="block text-xs font-black uppercase tracking-widest text-white">{audit.action} / {audit.status} / {audit.reconciliation_status ?? "pending"}</strong>
                    <span className="mt-1 block truncate text-xs text-zinc-400">{audit.transaction_signature ? `Signature ${audit.transaction_signature}` : audit.wallet_public_key || "No wallet recorded"}</span>
                    <p className="mt-2 text-xs text-zinc-500">{[...audit.warnings, ...audit.errors].join(" / ") || audit.final_status}</p>
                  </article>
                ))}
                {!liveAudit.length ? <p className="rounded-lg border border-white/5 bg-black/25 p-3 text-xs text-zinc-500">No live audit records yet.</p> : null}
              </div>
            </section>
          </div>
        </div>
      </motion.section>
    </div>
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

function shortAddress(value: string): string {
  return value ? `${value.slice(0, 6)}...${value.slice(-4)}` : "not connected";
}

function emptyLiveLedger(): LiveLedger {
  return {
    positions: [],
    summary: {
      realized_pnl_sol: 0,
      unrealized_pnl_sol: 0,
      cost_basis_sol: 0,
      open_positions: 0,
      approximate: true
    }
  };
}

export default App;

