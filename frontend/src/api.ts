import type { BacktestResult, BacktestV3Result, BotSnapshot, DataIntegrityReport, DataSummary, ExperimentRun, LiveExecutionAudit, LiveExecutionRequest, LivePosition, LiveStatus, OperationalMonitoring, PerformanceAnalytics, PriceDiagnostics, PriceObservation, PumpFunReport, ReadinessStatus, ReplayTimelineEvent, SafetyStatus, SecurityStatus, SettingsVersion, SignerStatus, SolanaStatus, SourceAdapterStatus, SourceEvent, SourceHealth, StrategyDecisionRecord, StrategyPreset, TradeLabel, TradeRecord, TradeReviewDetail, TradeSession, TuningSuggestion, WatchdogStatus } from "./types";

const configuredApiBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
const localDevApiBase = `${window.location.protocol}//${window.location.hostname}:8000`;
const API_BASE = configuredApiBase ?? (window.location.port === "5173" ? localDevApiBase : "");
let authToken = window.localStorage.getItem("cryptoarc_token") || "";

function headers(extra?: HeadersInit): HeadersInit {
  return authToken ? { ...extra, Authorization: `Bearer ${authToken}` } : { ...extra };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers: headers(init.headers) });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function authStatus(): Promise<{ enabled: boolean; totp_enabled: boolean }> {
  return request("/api/auth/status");
}

export async function login(password: string, code: string): Promise<void> {
  const result = await request<{ token: string }>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password, code })
  });
  authToken = result.token;
  window.localStorage.setItem("cryptoarc_token", authToken);
}

export function logout(): void {
  authToken = "";
  window.localStorage.removeItem("cryptoarc_token");
}

export async function fetchSnapshot(): Promise<BotSnapshot> {
  return request("/api/snapshot");
}

export async function startBot(): Promise<BotSnapshot> {
  return request("/api/start", { method: "POST" });
}

export async function stopBot(): Promise<BotSnapshot> {
  return request("/api/stop", { method: "POST" });
}

export async function patchSettings(patch: Record<string, number | boolean | string>): Promise<BotSnapshot> {
  return request("/api/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch)
  });
}

export interface BacktestOptions {
  limit?: number;
  profile?: string;
  date_from?: string;
  date_to?: string;
  replay_speed?: number;
}

export async function runReplayBacktest(options?: BacktestOptions): Promise<BacktestResult> {
  return request("/api/backtest/replay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options ?? {})
  });
}

export async function runRawReplayBacktest(options?: BacktestOptions): Promise<BacktestResult> {
  return request("/api/backtest/raw-replay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options ?? {})
  });
}

export async function runStrategyComparison(): Promise<BacktestResult> {
  return request("/api/backtest/compare", { method: "POST" });
}

export async function runABStrategyReplay(options?: BacktestOptions): Promise<BacktestResult> {
  return request("/api/backtest/ab-replay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options ?? {})
  });
}

export async function runBacktestV3(options?: BacktestOptions): Promise<BacktestV3Result> {
  return request("/api/backtest/v3", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options ?? {})
  });
}

export async function fetchBacktests(): Promise<BacktestResult[]> {
  return request("/api/backtests");
}

export async function fetchSourceEvents(): Promise<SourceEvent[]> {
  return request("/api/source-events");
}

export async function fetchTrades(): Promise<TradeRecord[]> {
  return request("/api/trades");
}

export async function fetchPriceObservations(): Promise<PriceObservation[]> {
  return request("/api/price-observations");
}

export async function fetchStrategyDecisions(): Promise<StrategyDecisionRecord[]> {
  return request("/api/strategy-decisions");
}

export async function fetchTradeSessions(): Promise<TradeSession[]> {
  return request("/api/trade-sessions");
}

export async function fetchSettingsVersions(): Promise<SettingsVersion[]> {
  return request("/api/settings/versions");
}

export async function fetchPerformanceAnalytics(): Promise<PerformanceAnalytics> {
  return request("/api/analytics/performance");
}

export async function fetchTuningSuggestions(): Promise<TuningSuggestion[]> {
  return request("/api/analytics/suggestions");
}

export async function fetchReplayTimeline(tokenId: string): Promise<ReplayTimelineEvent[]> {
  return request(`/api/replay/timeline/${encodeURIComponent(tokenId)}`);
}

export async function fetchTradeReviewDetail(tokenId: string): Promise<TradeReviewDetail> {
  return request(`/api/trade-review/${encodeURIComponent(tokenId)}`);
}

export async function fetchDataIntegrity(): Promise<DataIntegrityReport> {
  return request("/api/data/integrity");
}

export async function fetchPriceDiagnostics(): Promise<PriceDiagnostics> {
  return request("/api/price/diagnostics");
}

export async function fetchPumpFunReport(): Promise<PumpFunReport> {
  return request("/api/pumpfun/intelligence");
}

export async function fetchSafetyStatus(): Promise<SafetyStatus> {
  return request("/api/safety/status");
}

export async function fetchReadinessStatus(): Promise<ReadinessStatus> {
  return request("/api/readiness/status");
}

export async function fetchWatchdogStatus(): Promise<WatchdogStatus> {
  return request("/api/watchdog/status");
}

export async function recoverWatchdog(): Promise<BotSnapshot> {
  return request("/api/watchdog/recover", { method: "POST" });
}

export async function fetchSolanaStatus(): Promise<SolanaStatus> {
  return request("/api/solana/status");
}

export async function fetchLiveRequests(): Promise<LiveExecutionRequest[]> {
  return request("/api/live/requests");
}

export async function fetchLiveStatus(walletPublicKey = "", signerMode = "browser_wallet"): Promise<LiveStatus> {
  return request(`/api/live/status?wallet_public_key=${encodeURIComponent(walletPublicKey)}&signer_mode=${encodeURIComponent(signerMode)}`);
}

export async function fetchLiveWalletStatus(walletPublicKey = "", signerMode = "browser_wallet"): Promise<SignerStatus> {
  return request(`/api/live/wallet/status?wallet_public_key=${encodeURIComponent(walletPublicKey)}&signer_mode=${encodeURIComponent(signerMode)}`);
}

export async function acknowledgeLiveSession(): Promise<{ acknowledged: boolean; acknowledged_at: string }> {
  return request("/api/live/session/acknowledge", { method: "POST" });
}

export async function startLiveSession(wallet_public_key: string, signer_mode = "browser_wallet"): Promise<Record<string, unknown>> {
  return request("/api/live/session/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ wallet_public_key, signer_mode })
  });
}

export interface LiveQuoteRequest {
  action: "buy" | "sell";
  mint: string;
  amount: string;
  denominated_in_sol: boolean;
  slippage_pct: number;
  priority_fee_sol: number;
  pool: string;
  wallet_public_key: string;
  signer_mode: string;
}

export async function createLiveQuote(payload: LiveQuoteRequest): Promise<LiveExecutionAudit> {
  return request("/api/live/quote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function recordLiveSimulation(audit_id: string, ok: boolean, warning = "", error = "", result: Record<string, unknown> = {}): Promise<LiveExecutionAudit> {
  return request("/api/live/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audit_id, ok, warning, error, result })
  });
}

export async function submitLiveAudit(audit_id: string, signature: string): Promise<LiveExecutionAudit> {
  return request("/api/live/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audit_id, signature })
  });
}

export async function confirmLiveAudit(audit_id: string, confirmation_status: string, error = ""): Promise<LiveExecutionAudit> {
  return request("/api/live/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audit_id, confirmation_status, error })
  });
}

export async function fetchLivePositions(walletPublicKey = ""): Promise<LivePosition[]> {
  return request(`/api/live/positions?wallet_public_key=${encodeURIComponent(walletPublicKey)}`);
}

export async function fetchLiveAudit(): Promise<LiveExecutionAudit[]> {
  return request("/api/live/audit");
}

export async function createManualLiveRequest(action: "buy" | "sell", mint: string, amount_sol: number): Promise<LiveExecutionRequest> {
  return request("/api/live/manual-request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, mint, amount_sol })
  });
}

export async function reviewLiveRequest(requestId: string, status: "reviewed" | "rejected", note = ""): Promise<LiveExecutionRequest> {
  return request(`/api/live/requests/${encodeURIComponent(requestId)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, note })
  });
}

export async function fetchOperationalMonitoring(): Promise<OperationalMonitoring> {
  return request("/api/monitoring/ops");
}

export async function fetchExperiments(): Promise<ExperimentRun[]> {
  return request("/api/experiments");
}

export async function createExperiment(name: string, profile?: string, limit?: number, notes = ""): Promise<ExperimentRun> {
  return request("/api/experiments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, profile, limit, notes })
  });
}

export async function fetchTradeLabels(): Promise<TradeLabel[]> {
  return request("/api/trade-labels");
}

export async function labelTrade(tokenId: string, label: string, note = ""): Promise<TradeLabel> {
  return request(`/api/trade-labels/${encodeURIComponent(tokenId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, note })
  });
}

export async function fetchStrategyPresets(): Promise<StrategyPreset[]> {
  return request("/api/strategy-presets");
}

export async function saveStrategyPreset(name: string, description = ""): Promise<StrategyPreset> {
  return request("/api/strategy-presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description })
  });
}

export async function fetchSourceAdapters(): Promise<SourceAdapterStatus[]> {
  return request("/api/source-adapters");
}

export async function backupDatabase(): Promise<{ status: string; path: string }> {
  return request("/api/data/backup", { method: "POST" });
}

export async function fetchSourceHealth(): Promise<SourceHealth> {
  return request("/api/source-health");
}

export async function fetchSecurityStatus(): Promise<SecurityStatus> {
  return request("/api/security/status");
}

export async function updatePassword(current_password: string, new_password: string): Promise<void> {
  await request("/api/security/password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password, new_password })
  });
  logout();
}

export async function setupTotp(): Promise<{ secret: string; otpauth_url: string }> {
  return request("/api/security/totp/setup", { method: "POST" });
}

export async function verifyTotp(secret: string, code: string): Promise<void> {
  await request("/api/security/totp/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ secret, code })
  });
  logout();
}

export async function disableTotp(): Promise<void> {
  await request("/api/security/totp/disable", { method: "POST" });
  logout();
}

export async function fetchDataSummary(): Promise<DataSummary> {
  return request("/api/data/summary");
}

export async function clearData(target: "tokens" | "events" | "source_events" | "backtests" | "trades" | "price_observations" | "strategy_decisions" | "trade_sessions" | "settings_versions" | "experiments" | "trade_labels" | "strategy_presets" | "live_execution_requests" | "live_sessions" | "live_execution_audits" | "all"): Promise<DataSummary> {
  return request(`/api/data/clear/${target}`, { method: "POST" });
}

export function exportUrl(target: "tokens" | "source_events" | "backtests" | "trades" | "price_observations" | "strategy_decisions" | "trade_sessions" | "settings_versions" | "experiments" | "trade_labels" | "strategy_presets" | "live_execution_requests" | "live_sessions" | "live_execution_audits" | "all"): string {
  return `${API_BASE}/api/export/${target}${authToken ? `?token=${encodeURIComponent(authToken)}` : ""}`;
}

export function openSnapshotSocket(onSnapshot: (snapshot: BotSnapshot) => void): WebSocket {
  const apiUrl = API_BASE ? new URL(API_BASE, window.location.origin) : new URL(window.location.origin);
  apiUrl.protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
  apiUrl.pathname = "/ws";
  apiUrl.search = authToken ? `?token=${encodeURIComponent(authToken)}` : "";
  const socket = new WebSocket(apiUrl.toString());
  socket.addEventListener("message", (event) => {
    onSnapshot(JSON.parse(event.data));
  });
  return socket;
}
