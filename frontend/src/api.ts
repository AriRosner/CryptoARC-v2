import type { AlertStatus, BacktestResult, BacktestV3Result, BotSnapshot, DataIntegrityReport, DataSummary, EvidenceModeSeparationReport, ExperimentRun, HotWalletStatus, IncidentExportReviewAttestation, LatencyStatus, LiveExecutionAudit, LiveExecutionRequest, LiveIntent, LiveLedger, LivePosition, LiveStatus, MobileDevicesResponse, MobilePairingStartResponse, MonitorPnlSummary, OperationalMonitoring, OperatorLogsReport, OperatorSessionReport, OutcomeExplanationsReport, PerformanceAnalytics, PilotReadinessReport, PostRunReviewReport, PriceDiagnostics, PriceObservation, PumpFunReport, ReadinessStatus, ReleaseReadinessReport, ReleaseVerificationAttestation, RentRecoveryPreview, RentRecoveryScan, ReplayTimelineEvent, RestoreArtifactPreview, RestoreSmokeTestReport, SafetyStatus, SecurityStatus, SentinelVerdict, SettingsVersion, SetupReadinessReport, SignerStatus, SimulationAccuracyReport, SolanaLogsVerificationReport, SolanaStatus, SourceAdapterStatus, SourceEvent, SourceHealth, SourceParserReplayReport, SourceSoakAcceptanceReport, StrategyCandidate, StrategyCandidatePromotionResult, StrategyDecisionRecord, StrategyPreset, TradeGrade, TradeGradeCorrection, TradeLabel, TradeRecord, TradeReviewDetail, TradeReviewQueue, TradeSession, TuningSuggestion, WatchdogStatus, WorkloadPressure } from "./types";

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

export interface SourceEventOptions {
  limit?: number;
  status?: string;
  mint?: string;
  source?: string;
  event_kind?: string;
  parser_result?: string;
}

export async function fetchSourceEvents(options: SourceEventOptions = {}): Promise<SourceEvent[]> {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.status) params.set("status", options.status);
  if (options.mint) params.set("mint", options.mint);
  if (options.source) params.set("source", options.source);
  if (options.event_kind) params.set("event_kind", options.event_kind);
  if (options.parser_result) params.set("parser_result", options.parser_result);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/source-events${suffix}`);
}

export async function fetchSourceParserReplay(limit = 120, profile = ""): Promise<SourceParserReplayReport> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (profile) params.set("profile", profile);
  return request(`/api/source-events/parser-replay?${params.toString()}`);
}

export function sourceParserReplayExportUrl(limit = 120, profile = ""): string {
  const params = new URLSearchParams({ limit: String(limit) });
  if (profile) params.set("profile", profile);
  return `${API_BASE}/api/source-events/parser-replay/export?${params.toString()}`;
}

export async function fetchSolanaLogsVerification(limit = 500): Promise<SolanaLogsVerificationReport> {
  return request(`/api/source-events/solana-logs-verification?limit=${encodeURIComponent(String(limit))}`);
}

export async function fetchSourceSoakAcceptance(limit = 500): Promise<SourceSoakAcceptanceReport> {
  return request(`/api/source-events/source-soak?limit=${encodeURIComponent(String(limit))}`);
}

export async function recordSourceSoakSnapshot(limit = 500): Promise<SourceSoakAcceptanceReport> {
  return request(`/api/source-events/source-soak/snapshot?limit=${encodeURIComponent(String(limit))}`, { method: "POST" });
}

export function solanaLogsVerificationExportUrl(limit = 500): string {
  const params = new URLSearchParams({ limit: String(limit) });
  return `${API_BASE}/api/source-events/solana-logs-verification/export?${params.toString()}`;
}

export function sourceSoakAcceptanceExportUrl(limit = 500): string {
  const params = new URLSearchParams({ limit: String(limit) });
  return `${API_BASE}/api/source-events/source-soak/export?${params.toString()}`;
}

export async function fetchTrades(): Promise<TradeRecord[]> {
  return request("/api/trades");
}

export async function fetchMonitorTokens(): Promise<BotSnapshot["tokens"]> {
  return request("/api/tokens");
}

export async function fetchSolUsdPrice(): Promise<{ symbol: string; currency: "USD"; price: number; updated_at: string | null; source: string; stale: boolean; error: string }> {
  return request("/api/market/sol-usd");
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

export async function fetchMonitorPnlSummary(timeframe: string): Promise<MonitorPnlSummary> {
  return request(`/api/monitor/pnl?timeframe=${encodeURIComponent(timeframe)}`);
}

export async function fetchTuningSuggestions(): Promise<TuningSuggestion[]> {
  return request("/api/analytics/suggestions");
}

export async function applyTuningSuggestion(setting: string, suggested_value: string | number | boolean): Promise<{ setting: string; suggested_value: string | number | boolean; snapshot: BotSnapshot }> {
  return request("/api/analytics/suggestions/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ setting, suggested_value })
  });
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

export async function fetchTradeGrades(tradeId = "", mode = ""): Promise<TradeGrade[]> {
  const params = new URLSearchParams();
  if (tradeId) params.set("trade_id", tradeId);
  if (mode) params.set("mode", mode);
  return request(`/api/trade-grades?${params.toString()}`);
}

export async function fetchTradeGradeCorrections(tradeId: string): Promise<TradeGradeCorrection[]> {
  return request(`/api/trade-grades/${encodeURIComponent(tradeId)}/corrections`);
}

export async function correctTradeGrade(gradeId: string, operatorIntentId: string, patch: Record<string, unknown>, note = ""): Promise<TradeGradeCorrection> {
  return request(`/api/trade-grades/${encodeURIComponent(gradeId)}/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operator_intent_id: operatorIntentId, patch, note })
  });
}

export async function fetchStrategyCandidates(): Promise<StrategyCandidate[]> {
  return request("/api/strategy-candidates");
}

export async function promoteStrategyCandidate(candidateId: string, operatorIntentId: string): Promise<StrategyCandidatePromotionResult> {
  return request(`/api/strategy-candidates/${encodeURIComponent(candidateId)}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operator_intent_id: operatorIntentId })
  });
}

export async function fetchSentinelCurrent(): Promise<SentinelVerdict> {
  return request("/api/sentinel/current");
}

export async function fetchSentinelHistory(limit = 20): Promise<SentinelVerdict[]> {
  return request(`/api/sentinel/history?limit=${Math.max(1, Math.min(100, limit))}`);
}

export async function fetchPilotReadiness(walletPublicKey = "", signerMode = "browser_wallet"): Promise<PilotReadinessReport> {
  return request(`/api/reports/pilot-readiness?wallet_public_key=${encodeURIComponent(walletPublicKey)}&signer_mode=${encodeURIComponent(signerMode)}`);
}

export async function fetchSetupReadiness(): Promise<SetupReadinessReport> {
  return request("/api/reports/setup-readiness");
}

export async function fetchReleaseReadiness(): Promise<ReleaseReadinessReport> {
  return request("/api/reports/release-readiness");
}

export async function recordReleaseVerification(payload: {
  app_version?: string;
  verify_passed: boolean;
  diff_reviewed: boolean;
  docs_reviewed: boolean;
  note?: string;
}): Promise<ReleaseVerificationAttestation> {
  return request("/api/reports/release-readiness/verification", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchPostRunReview(timeframe = "24h", walletPublicKey = ""): Promise<PostRunReviewReport> {
  const params = new URLSearchParams({ timeframe });
  if (walletPublicKey) params.set("wallet_public_key", walletPublicKey);
  return request(`/api/reports/post-run-review?${params.toString()}`);
}

export async function fetchSimulationAccuracy(walletPublicKey = ""): Promise<SimulationAccuracyReport> {
  const params = new URLSearchParams();
  if (walletPublicKey) params.set("wallet_public_key", walletPublicKey);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/reports/simulation-accuracy${suffix}`);
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

export async function fetchLiveWalletBalance(walletPublicKey = ""): Promise<{ wallet_public_key: string; balance_sol: number; error: string }> {
  return request(`/api/live/wallet/balance?wallet_public_key=${encodeURIComponent(walletPublicKey)}`);
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

export async function fetchHotWalletStatus(): Promise<HotWalletStatus> {
  return request("/api/live/hot-wallet/status");
}

export async function importHotWallet(private_key: string, password: string, label = ""): Promise<HotWalletStatus> {
  return request("/api/live/hot-wallet/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ private_key, password, label })
  });
}

export async function unlockHotWallet(password: string): Promise<HotWalletStatus> {
  return request("/api/live/hot-wallet/unlock", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password })
  });
}

export async function lockHotWallet(): Promise<HotWalletStatus> {
  return request("/api/live/hot-wallet/lock", { method: "POST" });
}

export async function clearHotWallet(): Promise<HotWalletStatus> {
  return request("/api/live/hot-wallet/clear", { method: "POST" });
}

export async function armLiveBackend(wallet_public_key: string, signer_mode = "browser_wallet"): Promise<Record<string, unknown>> {
  return request("/api/live/backend/arm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ wallet_public_key, signer_mode })
  });
}

export async function disarmLiveBackend(): Promise<Record<string, unknown>> {
  return request("/api/live/backend/disarm", { method: "POST" });
}

export async function setLiveKillSwitch(enabled: boolean, reason = ""): Promise<Record<string, unknown>> {
  return request("/api/live/kill-switch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled, reason })
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

export async function fetchRentRecoveryScan(walletPublicKey: string): Promise<RentRecoveryScan> {
  return request(`/api/live/rent-recovery?wallet_public_key=${encodeURIComponent(walletPublicKey)}`);
}

export async function createRentRecoveryPreview(walletPublicKey: string, tokenAccounts: string[]): Promise<RentRecoveryPreview> {
  return request("/api/live/rent-recovery/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ wallet_public_key: walletPublicKey, token_accounts: tokenAccounts })
  });
}

export async function fetchProfitSweepHistory(limit = 100): Promise<LiveExecutionAudit[]> {
  return request(`/api/live/profit-sweeps?limit=${encodeURIComponent(String(limit))}`);
}

export async function recoverUnresolvedLiveAudit(): Promise<{ summary: Record<string, unknown>; audits: LiveExecutionAudit[] }> {
  return request("/api/live/audit/recover-unresolved", { method: "POST" });
}

export async function recoverLiveAudit(auditId: string): Promise<LiveExecutionAudit> {
  return request(`/api/live/audit/${encodeURIComponent(auditId)}/recover`, { method: "POST" });
}

export async function fetchLiveIntents(): Promise<LiveIntent[]> {
  return request("/api/live/intents");
}

export async function fetchLiveLedger(walletPublicKey = ""): Promise<LiveLedger> {
  return request(`/api/live/ledger?wallet_public_key=${encodeURIComponent(walletPublicKey)}`);
}

export async function createLiveIntent(payload: {
  action: "buy" | "sell";
  mint: string;
  amount: string;
  denominated_in_sol: boolean;
  wallet_public_key: string;
  signer_mode: string;
  source?: string;
  reason?: string;
  symbol?: string;
  score?: number;
}): Promise<LiveIntent> {
  return request("/api/live/intents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function generateLiveIntents(wallet_public_key: string, signer_mode = "browser_wallet", watchlist: string[] = []): Promise<LiveIntent[]> {
  return request("/api/live/intents/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ wallet_public_key, signer_mode, watchlist })
  });
}

export async function cancelLiveIntent(intentId: string): Promise<LiveIntent> {
  return request(`/api/live/intents/${encodeURIComponent(intentId)}/cancel`, { method: "POST" });
}

export async function quoteLiveIntent(intentId: string, slippage_pct: number, priority_fee_sol: number, pool: string): Promise<LiveExecutionAudit> {
  return request(`/api/live/intents/${encodeURIComponent(intentId)}/quote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slippage_pct, priority_fee_sol, pool })
  });
}

export async function reconcileLiveIntent(intentId: string): Promise<Record<string, unknown>> {
  return request(`/api/live/intents/${encodeURIComponent(intentId)}/reconcile`, { method: "POST" });
}

export async function recordLiveExpertOverride(payload: {
  target_gate: string;
  action: "buy" | "sell";
  reason: string;
  wallet_public_key?: string;
  signer_mode?: string;
}): Promise<Record<string, unknown>> {
  return request("/api/live/override", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
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

export async function fetchWorkloadPressure(): Promise<WorkloadPressure> {
  return request("/api/monitoring/workload-pressure");
}

export async function fetchOperatorLogs(timeframe = "24h", level = "", subsystem = "", limit = 200): Promise<OperatorLogsReport> {
  const params = new URLSearchParams({ timeframe, limit: String(limit) });
  if (level) params.set("level", level);
  if (subsystem) params.set("subsystem", subsystem);
  return request(`/api/reports/operator-logs?${params.toString()}`);
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

export async function fetchTradeReviewQueue(): Promise<TradeReviewQueue> {
  return request("/api/trade-review/queue");
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

export async function createBackupArtifact(): Promise<{ filename: string; artifact: Record<string, unknown> }> {
  return request("/api/data/backup-artifact", { method: "POST" });
}

export async function runRestoreSmokeTest(): Promise<RestoreSmokeTestReport> {
  return request("/api/data/restore/smoke-test", { method: "POST" });
}

export async function previewRestoreArtifact(artifact: Record<string, unknown>): Promise<RestoreArtifactPreview> {
  return request("/api/data/restore/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ artifact })
  });
}

export async function confirmRestoreArtifact(artifact: Record<string, unknown>): Promise<RestoreArtifactPreview> {
  return request("/api/data/restore/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ artifact })
  });
}

export async function fetchSourceHealth(): Promise<SourceHealth> {
  return request("/api/source-health");
}

export async function fetchLatencyStatus(): Promise<LatencyStatus> {
  return request("/api/latency/status");
}

export function sourceHealthExportUrl(limit = 300): string {
  return `${API_BASE}/api/source-health/export?limit=${encodeURIComponent(String(limit))}`;
}

export async function fetchSecurityStatus(): Promise<SecurityStatus> {
  return request("/api/security/status");
}

export async function fetchAlertStatus(): Promise<AlertStatus> {
  return request("/api/alerts/status");
}

export async function sendTestAlert(): Promise<Record<string, unknown>> {
  return request("/api/alerts/test", { method: "POST" });
}

export async function startMobilePairing(api_base_url: string, scopes = ["mobile:monitor", "mobile:control"]): Promise<MobilePairingStartResponse> {
  return request("/api/mobile/pairing/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_base_url, scopes })
  });
}

export async function fetchMobileDevices(include_revoked = true): Promise<MobileDevicesResponse> {
  return request(`/api/mobile/devices?include_revoked=${include_revoked ? "true" : "false"}`);
}

export async function revokeMobileDevice(deviceId: string): Promise<void> {
  await request(`/api/mobile/devices/${encodeURIComponent(deviceId)}/revoke`, { method: "POST" });
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

export async function clearData(target: "tokens" | "events" | "source_events" | "backtests" | "trades" | "price_observations" | "strategy_decisions" | "trade_sessions" | "settings_versions" | "experiments" | "trade_labels" | "strategy_presets" | "live_execution_requests" | "live_sessions" | "live_execution_audits" | "live_intents" | "live_ledger_positions" | "source_soak_history" | "all"): Promise<DataSummary> {
  return request(`/api/data/clear/${target}`, { method: "POST" });
}

export async function recoverOpenPaperPositions(note = "operator stopped run"): Promise<{ closed_positions: number; total_recovered_pnl_sol: number; exit_reason: string; token_ids: string[]; status: string; operator_action: string }> {
  return request("/api/paper/recover-open", {
    method: "POST",
    body: JSON.stringify({ note })
  });
}

export function exportUrl(target: "tokens" | "source_events" | "backtests" | "trades" | "price_observations" | "strategy_decisions" | "trade_sessions" | "settings_versions" | "experiments" | "trade_labels" | "strategy_presets" | "live_execution_requests" | "live_sessions" | "live_execution_audits" | "live_intents" | "live_ledger_positions" | "source_soak_history" | "all"): string {
  return `${API_BASE}/api/export/${target}`;
}

export function sessionReportExportUrl(timeframe = "24h", walletPublicKey = ""): string {
  const params = new URLSearchParams({ timeframe });
  if (walletPublicKey) params.set("wallet_public_key", walletPublicKey);
  return `${API_BASE}/api/reports/session/export?${params.toString()}`;
}

export async function fetchSessionReport(timeframe = "24h", walletPublicKey = ""): Promise<OperatorSessionReport> {
  const params = new URLSearchParams({ timeframe });
  if (walletPublicKey) params.set("wallet_public_key", walletPublicKey);
  return request(`/api/reports/session?${params.toString()}`);
}

export async function fetchEvidenceModeSeparation(): Promise<EvidenceModeSeparationReport> {
  return request("/api/reports/evidence-mode-separation");
}

export function evidenceModeSeparationExportUrl(): string {
  return `${API_BASE}/api/reports/evidence-mode-separation/export`;
}

export function simulationAccuracyExportUrl(walletPublicKey = ""): string {
  const params = new URLSearchParams();
  if (walletPublicKey) params.set("wallet_public_key", walletPublicKey);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `${API_BASE}/api/reports/simulation-accuracy/export${suffix}`;
}

export function operatorLogsExportUrl(timeframe = "24h", level = "", subsystem = "", limit = 200): string {
  const params = new URLSearchParams({ timeframe, limit: String(limit) });
  if (level) params.set("level", level);
  if (subsystem) params.set("subsystem", subsystem);
  return `${API_BASE}/api/reports/operator-logs/export?${params.toString()}`;
}

export function pilotReadinessExportUrl(walletPublicKey = "", signerMode = "browser_wallet"): string {
  const params = new URLSearchParams({ signer_mode: signerMode });
  if (walletPublicKey) params.set("wallet_public_key", walletPublicKey);
  return `${API_BASE}/api/reports/pilot-readiness/export?${params.toString()}`;
}

export function setupReadinessExportUrl(): string {
  return `${API_BASE}/api/reports/setup-readiness/export`;
}

export function releaseReadinessExportUrl(): string {
  return `${API_BASE}/api/reports/release-readiness/export`;
}

export function postRunReviewExportUrl(timeframe = "24h", walletPublicKey = ""): string {
  const params = new URLSearchParams({ timeframe });
  if (walletPublicKey) params.set("wallet_public_key", walletPublicKey);
  return `${API_BASE}/api/reports/post-run-review/export?${params.toString()}`;
}

export async function fetchOutcomeExplanations(timeframe = "24h", limit = 80): Promise<OutcomeExplanationsReport> {
  const params = new URLSearchParams({ timeframe, limit: String(limit) });
  return request(`/api/reports/outcome-explanations?${params.toString()}`);
}

export function outcomeExplanationsExportUrl(timeframe = "24h", limit = 80): string {
  const params = new URLSearchParams({ timeframe, limit: String(limit) });
  return `${API_BASE}/api/reports/outcome-explanations/export?${params.toString()}`;
}

export function incidentExportUrl(auditId: string): string {
  return `${API_BASE}/api/live/audit/${encodeURIComponent(auditId)}/incident-export`;
}

export async function recordIncidentExportReview(
  auditId: string,
  payload: { exported?: boolean; reviewed?: boolean; note?: string } = {},
): Promise<IncidentExportReviewAttestation> {
  return request(`/api/live/audit/${encodeURIComponent(auditId)}/incident-export/review`, {
    method: "POST",
    body: JSON.stringify({
      exported: payload.exported ?? true,
      reviewed: payload.reviewed ?? true,
      note: payload.note ?? "",
    }),
  });
}

export function backupRestoreExportUrl(entryId = ""): string {
  const params = new URLSearchParams();
  if (entryId) params.set("entry_id", entryId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `${API_BASE}/api/data/backup-restore/export${suffix}`;
}

export async function downloadAuthenticatedExport(url: string, fallbackFilename = "cryptoarc-export.json"): Promise<void> {
  const response = await fetch(url, { headers: headers() });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || fallbackFilename;
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
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
