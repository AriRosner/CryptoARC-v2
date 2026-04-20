import React from "react";
import { createRoot } from "react-dom/client";
import { Connection, PublicKey, VersionedTransaction } from "@solana/web3.js";
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
  stopBot,
  setupTotp,
  saveStrategyPreset,
  updatePassword,
  verifyTotp
} from "./api";
import type { BacktestResult, BacktestV3Result, BotSnapshot, BotSettings, DataIntegrityReport, DataSummary, ExperimentRun, LiveExecutionAudit, LiveExecutionRequest, LiveIntent, LiveLedger, LivePosition, LiveStatus, OperationalMonitoring, PerformanceAnalytics, PriceDiagnostics, PriceObservation, PumpFunReport, ReadinessStatus, ReplayTimelineEvent, SafetyStatus, SecurityStatus, SettingsVersion, SolanaStatus, SourceAdapterStatus, SourceEvent, SourceHealth, StrategyDecisionRecord, StrategyPreset, TokenSignal, TradeEvent, TradeLabel, TradeRecord, TradeReviewDetail, TradeSession, TuningSuggestion, WatchdogStatus } from "./types";
import "./styles.css";

import { AppLayout } from "./components/AppLayout";
import { MonitorPage } from "./pages/MonitorPage";
import { DataPage, type DataClearTarget } from "./pages/DataPage";
import { AnalysisPage } from "./pages/AnalysisPage";
import { BacktestsPage } from "./pages/BacktestsPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SettingsModal } from "./components/SettingsModal";
import { TokenDetail as NewTokenDetail } from "./components/TokenDetail";

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
type LiveWalletMethod = "browser_wallet" | "local_signer_daemon";
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

function App() {
  const [snapshot, setSnapshot] = React.useState<BotSnapshot>(fallbackSnapshot);
  const [apiState, setApiState] = React.useState("connecting");
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [selectedTokenId, setSelectedTokenId] = React.useState<string | null>(null);
  const [pnlTimeframe, setPnlTimeframe] = React.useState<PnlTimeframe>("all");
  const [pnlCurrency, setPnlCurrency] = React.useState<PnlCurrency>(() => (window.localStorage.getItem("cryptoarc_pnl_currency") === "USD" ? "USD" : "SOL"));
  const [solUsdPrice, setSolUsdPrice] = React.useState(0);
  const [solUsdStale, setSolUsdStale] = React.useState(false);
  const [botActionStatus, setBotActionStatus] = React.useState<BotActionStatus>("");
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
  const researchRefreshTimer = React.useRef<number | null>(null);
  const pnlRefreshInFlight = React.useRef(false);

  function scheduleResearchRefresh() {
    if (researchRefreshTimer.current !== null) return;
    researchRefreshTimer.current = window.setTimeout(() => {
      researchRefreshTimer.current = null;
      refreshResearchData().catch(() => undefined);
    }, 750);
  }

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
          scheduleResearchRefresh();
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
      if (researchRefreshTimer.current !== null) {
        window.clearTimeout(researchRefreshTimer.current);
      }
      socket?.close();
    };
  }, []);

  const settings = snapshot.settings;
  const stats = snapshot.stats;
  const selectedLivePnlWallet = pnlWalletScope === "paper" ? "" : pnlWalletScope;
  const selectedToken = snapshot.tokens.find((token) => token.id === selectedTokenId) ?? null;
  const watchSet = React.useMemo(() => new Set(watchlist), [watchlist]);
  const timeframeTrades = React.useMemo(() => timeframeClosedTrades(trades, pnlTimeframe), [pnlTimeframe, trades]);
  const paperTimeframePnl = timeframeTrades.reduce((total, token) => total + (token.pnl_sol || 0), 0);
  const liveTimeframePnl = Number(((liveLedger?.summary.realized_pnl_sol ?? 0) + (liveLedger?.summary.unrealized_pnl_sol ?? 0)).toFixed(6));
  const timeframePnlSol = pnlWalletScope === "paper" ? paperTimeframePnl : liveTimeframePnl;
  const effectivePnlCurrency: PnlCurrency = pnlCurrency === "USD" && solUsdPrice > 0 ? "USD" : "SOL";
  const pnlDisplayMultiplier = effectivePnlCurrency === "USD" ? solUsdPrice : 1;
  const displayPnlValue = Number((timeframePnlSol * pnlDisplayMultiplier).toFixed(effectivePnlCurrency === "USD" ? 2 : 6));
  const paperPnlHistory = React.useMemo(() => {
    const history = buildPnlHistory(trades, pnlTimeframe);
    if (history.length) return history;
    if (stats.closed_trades > 0 || stats.total_pnl_sol !== 0) {
      return [0, Number(stats.total_pnl_sol.toFixed(6))];
    }
    return [0, 0];
  }, [trades, pnlTimeframe, stats.closed_trades, stats.total_pnl_sol]);
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
      : "USD price loading"
    : "SOL display";
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

  React.useEffect(() => {
    if (pnlWalletScope !== "live") return;
    const replacement = walletPublicKey || liveWallets[0] || "paper";
    setPnlWalletScope(replacement);
    window.localStorage.setItem("cryptoarc_pnl_wallet_scope", replacement);
  }, [liveWallets, pnlWalletScope, walletPublicKey]);

  function toggleWatchlist(token: TokenSignal) {
    const next = watchSet.has(token.mint) ? watchlist.filter((mint) => mint !== token.mint) : [...watchlist, token.mint];
    setWatchlist(next);
    window.localStorage.setItem("cryptoarc_watchlist", JSON.stringify(next));
  }

  function updatePnlWalletScope(scope: PnlWalletScope) {
    setPnlWalletScope(scope);
    window.localStorage.setItem("cryptoarc_pnl_wallet_scope", scope);
  }

  function togglePnlCurrency() {
    setPnlCurrency((current) => {
      const next = current === "SOL" ? "USD" : "SOL";
      window.localStorage.setItem("cryptoarc_pnl_currency", next);
      if (next === "USD" && solUsdPrice <= 0) {
        refreshSolUsdPrice().catch(() => undefined);
      }
      return next;
    });
  }

  async function refreshSolUsdPrice() {
    const quote = await fetchSolUsdPrice();
    setSolUsdPrice(Number(quote.price || 0));
    setSolUsdStale(Boolean(quote.stale));
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
      await refreshPnlData();
      setApiError("");
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

  async function refreshPnlData() {
    if (pnlRefreshInFlight.current) return;
    pnlRefreshInFlight.current = true;
    try {
      const [tradeRows, ledgerState] = await Promise.all([
        fetchTrades(),
        fetchLiveLedger(selectedLivePnlWallet)
      ]);
      setTrades(tradeRows);
      setLiveLedger(ledgerState);
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

  async function refreshLiveExecutionSurfaces() {
    const [status, audits, positions, intents, ledger] = await Promise.all([
      fetchLiveStatus(walletPublicKey),
      fetchLiveAudit(),
      fetchLivePositions(walletPublicKey),
      fetchLiveIntents(),
      fetchLiveLedger(selectedLivePnlWallet)
    ]);
    setLiveStatus(status);
    setLiveAudit(audits);
    setLivePositions(positions);
    setLiveIntents(intents);
    setLiveLedger(ledger);
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
    refreshResearchData().catch(() => undefined);
  }, []);

  React.useEffect(() => {
    refreshPnlData().catch(() => undefined);
  }, [selectedLivePnlWallet]);

  React.useEffect(() => {
    const interval = window.setInterval(() => {
      refreshPnlData().catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(interval);
  }, [selectedLivePnlWallet]);

  React.useEffect(() => {
    const interval = window.setInterval(() => {
      refreshSolUsdPrice().catch(() => undefined);
    }, 60000);
    return () => window.clearInterval(interval);
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
      onLiveWalletOpen={() => setLiveWalletOpen(true)}
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
            ? `${timeframeTrades.length} closed paper trades in selected range`
            : `${liveLedger?.summary.open_positions ?? 0} live positions / ${(liveLedger?.summary.approximate ?? true) ? "approximate" : "confirmed"} P&L`}
          liveWallets={liveWallets}
          walletPublicKey={walletPublicKey}
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
          apiState={apiState}
        />
      )}

      {workspacePage === "analysis" && (
        <AnalysisPage
          tokens={snapshot.tokens}
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
        />
      )}

      {workspacePage === "backtests" && (
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
      )}

      {workspacePage === "review" && (
        <ReviewPage
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

      {settingsOpen && (
        <SettingsModal
          isOpen={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          settings={settings}
          onSave={saveSettings}
          sourceStatus={snapshot.source_status}
          serverStrategyPresets={strategyPresetsRemote}
          onSaveStrategyPreset={saveCurrentStrategyPreset}
        />
      )}

      {selectedToken && (
        <NewTokenDetail
          token={selectedToken}
          isOpen={!!selectedToken}
          onClose={() => setSelectedTokenId(null)}
        />
      )}

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
          onRecoverAllLiveAudits={recoverAllLiveAudits}
          onRecoverLiveAudit={recoverSingleLiveAudit}
        />
      )}
    </AppLayout>
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
  const quoteBlocked = !envEnabled || method !== "browser_wallet";
  const blockers = liveStatus?.blockers?.length ? liveStatus.blockers : envEnabled ? [] : ["Live environment flag is disabled"];
  const activeQuoteStale = activeLiveAudit?.status === "stale" || Boolean(activeLiveAudit?.quote?.stale);
  const recoverableAuditStatuses = new Set(["submitted", "failed", "needs_review", "stale"]);
  const reviewAudits = liveAudit.filter((audit) => recoverableAuditStatuses.has(audit.status) || audit.reconciliation_status === "needs_review");
  const recoverySummary = liveStatus?.recovery_summary;

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
                Manual browser-wallet buy and sell flow with quote previews, wallet approval, and audit records.
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
          <div className="grid gap-4 lg:grid-cols-2">
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
                <span className="rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-emerald-300">Active</span>
              </div>
              <span className="mt-2 block text-xs leading-5 text-zinc-400">Manual approval through Phantom, Solflare, or a compatible Solana wallet.</span>
            </button>
            <button
              className="cursor-not-allowed rounded-xl border border-white/10 bg-white/[0.02] p-4 text-left opacity-60"
              disabled
              onClick={() => onMethodChange("local_signer_daemon")}
            >
              <div className="flex items-center justify-between gap-3">
                <strong className="text-sm font-black uppercase tracking-widest text-white">Local signer daemon</strong>
                <span className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-zinc-400">Coming later</span>
              </div>
              <span className="mt-2 block text-xs leading-5 text-zinc-500">Required for any future unattended signing capability.</span>
            </button>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[0.85fr_1.15fr]">
            <div className="space-y-4">
              <section className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-black uppercase tracking-widest text-white">Connect Wallet</h3>
                    <p className="mt-1 text-xs text-zinc-400">CryptoARC stores the public key for status checks only. Reconnect and signing still require wallet approval.</p>
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
                <div className="grid gap-2 sm:grid-cols-2">
                  {[
                    ["Wallet", shortAddress(walletPublicKey)],
                    ["SOL balance", walletBalanceSol === null ? "-" : `${walletBalanceSol.toFixed(4)} SOL`],
                    ["Live env", envEnabled ? "enabled" : "disabled"],
                    ["Caps", capsSet ? "set" : "required"],
                    ["Acknowledgement", settings.live_session_acknowledged ? "done" : "needed"],
                    ["Live gates", liveStatus?.live_execution_available ? "open" : "blocked"],
                    ["Auto-sell", liveStatus?.auto_sell_available ? "available" : "not for browser wallet"]
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
                      Manual live prerequisites are passing.
                    </article>
                  )}
                </div>
                <button
                  className="mt-4 h-10 rounded-lg border border-white/10 bg-white/5 px-4 text-xs font-black uppercase tracking-widest text-white transition hover:border-white/20 hover:bg-white/10"
                  onClick={onAcknowledgeLive}
                >
                  Acknowledge Risk
                </button>
              </section>
            </div>

            <div className="space-y-4">
              <section className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-black uppercase tracking-widest text-white">Intent Queue</h3>
                    <p className="mt-1 text-xs text-zinc-400">Paper-promoted, watchlist, manual, and live-position intents. Quotes expire after 30 seconds.</p>
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
                  <span className="rounded-lg border border-white/5 bg-black/25 p-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Recon <strong className="block truncate pt-1 text-xs text-white">{liveStatus?.latest_reconciliation_status ?? "pending"}</strong></span>
                  <span className="rounded-lg border border-white/5 bg-black/25 p-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Realized <strong className="block pt-1 text-xs text-white">{(liveLedger?.summary.realized_pnl_sol ?? liveStatus?.live_pnl?.realized_pnl_sol ?? 0).toFixed(6)} SOL</strong></span>
                </div>
                <div className="max-h-72 space-y-2 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                  {liveIntents.slice(0, 10).map((intent) => (
                    <article key={intent.id} className={`rounded-lg border p-3 ${activeLiveIntentId === intent.id ? "border-amber-500/40 bg-amber-500/10" : "border-white/5 bg-black/25"}`}>
                      <strong className="block text-xs font-black uppercase tracking-widest text-white">{intent.action} / {intent.symbol || intent.mint.slice(0, 8)} / {intent.status}</strong>
                      <span className="mt-1 block text-[10px] font-bold uppercase tracking-widest text-zinc-500">{intent.source} / score {intent.score} / expires {intent.expires_at ? new Date(intent.expires_at).toLocaleTimeString() : "-"}</span>
                      <p className="mt-2 text-xs text-zinc-400">{intent.reason || "Live intent candidate"}</p>
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
                    <p className="mt-1 text-xs text-zinc-400">Quotes use PumpPortal local transactions and stay manual. Simulation warnings are recorded for review.</p>
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
                {!envEnabled ? <p className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs font-bold text-amber-200">Live env is disabled, so quotes and signing are blocked. Wallet connection and status checks still work.</p> : null}
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

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
