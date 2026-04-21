import React from "react";
import { 
  Database, 
  Download, 
  Upload,
  Trash2, 
  RotateCcw, 
  Shield, 
  Activity, 
  Gauge, 
  Clock, 
  Target, 
  Bell,
  Save,
  ChevronRight
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { Badge } from "../components/Badge";
import { Skeleton } from "../components/Skeleton";
import { cn } from "../components/utils";
import { exportUrl, backupDatabase, confirmRestoreArtifact, createBackupArtifact, previewRestoreArtifact } from "../api";
import type { 
  BackupRestoreHistoryEntry,
  DataSummary, 
  RestoreArtifactPreview,
  SourceEvent, 
  SourceHealth, 
  SecurityStatus, 
  TradeRecord, 
  PriceObservation, 
  StrategyDecisionRecord, 
  TradeSession, 
  SettingsVersion, 
  DataIntegrityReport, 
  PriceDiagnostics, 
  PumpFunReport, 
  SafetyStatus, 
  ReadinessStatus, 
  OperationalMonitoring, 
  SourceAdapterStatus, 
  WatchdogStatus, 
  SolanaStatus, 
  LiveExecutionRequest, 
  LiveExecutionAudit, 
  TradeEvent 
} from "../types";

export type DataClearTarget =
  | "tokens" | "events" | "source_events" | "backtests" | "trades"
  | "price_observations" | "strategy_decisions" | "trade_sessions"
  | "settings_versions" | "experiments" | "trade_labels" | "strategy_presets"
  | "live_execution_requests" | "live_sessions" | "live_execution_audits"
  | "live_intents" | "live_ledger_positions" | "all";

interface DataPageProps {
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
  onClear: (target: DataClearTarget) => Promise<void>;
}

const DataMetric: React.FC<{ label: string; value: string | number; color?: string; loading?: boolean }> = ({ label, value, color = "text-white", loading = false }) => (
  <div className="flex flex-col gap-1 rounded-xl border border-white/5 bg-white/[0.02] p-3 transition-colors hover:bg-white/[0.04]">
    <span className="text-[9px] font-black uppercase tracking-widest text-zinc-500">{label}</span>
    {loading ? <Skeleton className="h-5 w-20" /> : <span className={cn("text-sm font-black tracking-tight", color)}>{value}</span>}
  </div>
);

function auditLevelTone(level: string): string {
  const normalized = level.toLowerCase();
  if (normalized === "error" || normalized === "danger") return "border-rose-500/20 bg-rose-500/10 text-rose-300";
  if (normalized === "warn" || normalized === "warning") return "border-amber-500/20 bg-amber-500/10 text-amber-300";
  if (normalized === "success") return "border-emerald-500/20 bg-emerald-500/10 text-emerald-300";
  return "border-blue-500/20 bg-blue-500/10 text-blue-300";
}

export const DataPage: React.FC<DataPageProps> = ({
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
}) => {
  const loadingCore = !summary || !dataIntegrity || !readinessStatus || !sourceHealth || !solanaStatus || !watchdogStatus;
  const clearTargets: DataClearTarget[] = [
    "tokens", "events", "source_events", "backtests", "trades", 
    "price_observations", "strategy_decisions", "trade_sessions", 
    "settings_versions", "experiments", "trade_labels", "strategy_presets", 
    "live_execution_requests", "live_sessions", "live_execution_audits", 
    "live_intents", "live_ledger_positions"
  ];

  const exportTargets: Exclude<DataClearTarget, "events">[] = [
    "tokens", "source_events", "backtests", "trades", "price_observations", 
    "strategy_decisions", "trade_sessions", "settings_versions", 
    "experiments", "trade_labels", "strategy_presets", 
    "live_execution_requests", "live_sessions", "live_execution_audits", 
    "live_intents", "live_ledger_positions", "all"
  ];
  const readinessTone =
    readinessStatus?.status === "ready"
      ? "success"
      : readinessStatus?.status === "warning" || readinessStatus?.status === "not_enough_data"
        ? "warning"
        : "danger";
  const sourceHealthTone =
    (sourceHealth?.health_score ?? 0) >= 70
      ? "text-emerald-500"
      : (sourceHealth?.health_score ?? 0) >= 50
        ? "text-amber-400"
        : "text-rose-400";
  const [restorePreview, setRestorePreview] = React.useState<RestoreArtifactPreview | null>(null);
  const [restoreArtifact, setRestoreArtifact] = React.useState<Record<string, unknown> | null>(null);
  const [restoreFileName, setRestoreFileName] = React.useState("");
  const [restoreBusy, setRestoreBusy] = React.useState(false);
  const [restoreMessage, setRestoreMessage] = React.useState("");
  const restoreInputRef = React.useRef<HTMLInputElement | null>(null);
  const backupRestoreHistory = opsMonitoring?.backup_restore?.history ?? [];
  const signerDaemon = opsMonitoring?.signer_daemon;

  async function downloadBackupArtifact() {
    setRestoreMessage("");
    const result = await createBackupArtifact();
    const blob = new Blob([JSON.stringify(result.artifact, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = result.filename;
    anchor.click();
    URL.revokeObjectURL(url);
    setRestoreMessage(`Backup artifact downloaded as ${result.filename}.`);
    await onRefresh();
  }

  async function handleRestoreFile(file: File | null) {
    if (!file) return;
    setRestoreBusy(true);
    setRestoreMessage("");
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as Record<string, unknown>;
      const preview = await previewRestoreArtifact(parsed);
      setRestoreArtifact(parsed);
      setRestorePreview(preview);
      setRestoreFileName(file.name);
    } catch (error) {
      setRestorePreview(null);
      setRestoreArtifact(null);
      setRestoreMessage(error instanceof Error ? error.message : "Restore preview failed");
    } finally {
      setRestoreBusy(false);
      if (restoreInputRef.current) restoreInputRef.current.value = "";
    }
  }

  async function confirmRestore() {
    if (!restoreArtifact) return;
    setRestoreBusy(true);
    setRestoreMessage("");
    try {
      const result = await confirmRestoreArtifact(restoreArtifact);
      setRestorePreview(result);
      setRestoreMessage("Restore completed. Review migration/runtime status before trading.");
      await onRefresh();
    } catch (error) {
      setRestoreMessage(error instanceof Error ? error.message : "Restore failed");
    } finally {
      setRestoreBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Data & Intelligence" 
        description="Core signal storage, audit logs, and system maintenance."
        className="mb-6 p-6"
      >
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={onRefresh}>
            <RotateCcw size={14} className="mr-2" />
            Refresh
          </Button>
          <Button variant="primary" size="sm" onClick={() => backupDatabase()}>
            <Save size={14} className="mr-2" />
            Backup Database
          </Button>
          <Button variant="secondary" size="sm" onClick={downloadBackupArtifact}>
            <Download size={14} className="mr-2" />
            Backup Artifact
          </Button>
        </div>
      </PageHeader>

      {/* High-Density Metrics Grid */}
      <Card className="p-4" hover={false}>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
          <DataMetric label="Tokens" value={summary?.tokens ?? 0} loading={!summary} />
          <DataMetric label="Audit" value={summary?.events ?? 0} loading={!summary} />
          <DataMetric label="Signals" value={summary?.source_events ?? 0} loading={!summary} />
          <DataMetric label="Trades" value={summary?.trades ?? 0} loading={!summary} />
          <DataMetric label="Decisions" value={summary?.strategy_decisions ?? 0} loading={!summary} />
          <DataMetric label="Prices" value={summary?.price_observations ?? 0} loading={!summary} />
          <DataMetric label="Readiness" value={`${readinessStatus?.score ?? 0}%`} color="text-amber-500" loading={!readinessStatus} />
          <DataMetric label="Integrity" value={`${dataIntegrity?.score ?? 0}%`} color="text-emerald-500" loading={!dataIntegrity} />
          <DataMetric label="Health" value={`${sourceHealth?.health_score ?? 0}% ${sourceHealth?.status_message ? `| ${sourceHealth.status_message}` : ""}`} color={sourceHealthTone} loading={!sourceHealth} />
          <DataMetric label="RPC" value={solanaStatus?.health ?? "unknown"} color={solanaStatus?.health === "ok" ? "text-emerald-500" : "text-rose-500"} loading={!solanaStatus} />
          <DataMetric label="Watchdog" value={watchdogStatus?.status ?? "unknown"} loading={!watchdogStatus} />
          <DataMetric label="Live Reqs" value={liveRequests.length} color="text-rose-500" loading={!summary && !liveRequests.length} />
          <DataMetric label="Migrations" value={`${opsMonitoring?.schema?.current_version ?? 0}/${opsMonitoring?.schema?.expected_version ?? 0}`} loading={!opsMonitoring?.schema} />
          <DataMetric label="Restore Log" value={summary?.backup_restore_history ?? 0} loading={!summary} />
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left Column: Logs & Events */}
        <div className="space-y-6 lg:col-span-2">
          <Card className="flex flex-col h-[500px]" hover={false}>
            <div className="flex items-center justify-between border-b border-white/5 p-4">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Bell size={14} />
                System Audit Log
              </h3>
              <Badge variant="info">{auditEvents.length} Events</Badge>
            </div>
            <div className="flex-1 overflow-auto p-0 scrollbar-thin scrollbar-thumb-white/10">
              <div className="min-w-[560px] text-[11px]">
                <div className="sticky top-0 z-10 grid h-10 grid-cols-[140px_88px_minmax(0,1fr)] border-b border-white/5 bg-[#10121c]">
                  <div className="flex items-center px-4 font-black text-zinc-600">Timestamp</div>
                  <div className="flex items-center px-4 font-black text-zinc-600">Level</div>
                  <div className="flex items-center px-4 font-black text-zinc-600">Message</div>
                </div>
                <div className="divide-y divide-white/5 font-mono">
                  {auditEvents.map((event) => (
                    <div key={event.id} className="grid min-h-10 grid-cols-[140px_88px_minmax(0,1fr)] hover:bg-white/[0.02]">
                      <div className="flex items-center whitespace-nowrap px-4 text-zinc-500">
                        {new Date(event.created_at).toLocaleTimeString()}
                      </div>
                      <div className="flex items-center px-4">
                        <span className={cn("inline-flex items-center rounded-md border px-2 py-1 text-[10px] font-black uppercase tracking-wider", auditLevelTone(event.level))}>
                          {event.level}
                        </span>
                      </div>
                      <div className="flex items-center px-4 py-2 text-zinc-300">{event.message}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          <Card className="flex flex-col" hover={false}>
            <div className="flex items-center justify-between border-b border-white/5 p-4">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Target size={14} />
                Manual Live Requests
              </h3>
              <Badge variant="warning">{liveRequests.length} Requests</Badge>
            </div>
            <div className="max-h-[320px] overflow-auto p-0 scrollbar-thin scrollbar-thumb-white/10">
              <table className="min-w-full table-fixed border-collapse text-left text-[11px]">
                <colgroup>
                  <col className="w-28" />
                  <col className="w-20" />
                  <col className="w-24" />
                  <col className="w-24" />
                  <col />
                </colgroup>
                <thead className="sticky top-0 z-10 bg-[#10121c]">
                  <tr className="border-b border-white/5">
                    <th className="w-28 px-4 py-2 font-black text-zinc-600">Created</th>
                    <th className="w-20 px-4 py-2 font-black text-zinc-600">Action</th>
                    <th className="w-24 px-4 py-2 font-black text-zinc-600">Amount</th>
                    <th className="w-24 px-4 py-2 font-black text-zinc-600">Status</th>
                    <th className="px-4 py-2 font-black text-zinc-600 text-right">Review</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono">
                  {liveRequests.slice(0, 30).map((request) => (
                    <tr key={request.id} className="hover:bg-white/[0.02]">
                      <td className="px-4 py-2 text-zinc-500">{new Date(request.created_at).toLocaleTimeString()}</td>
                      <td className="px-4 py-2 text-zinc-300">{request.action}</td>
                      <td className="px-4 py-2 text-zinc-300">{request.amount_sol} SOL</td>
                      <td className="px-4 py-2"><Badge variant={request.status === "pending" ? "warning" : request.status === "rejected" ? "danger" : "success"}>{request.status}</Badge></td>
                      <td className="px-4 py-2 text-right">
                        {request.status === "pending" ? (
                          <div className="flex justify-end gap-2">
                            <Button variant="secondary" size="sm" onClick={() => onReviewLiveRequest(request.id, "reviewed")}>Review</Button>
                            <Button variant="danger" size="sm" onClick={() => onReviewLiveRequest(request.id, "rejected")}>Reject</Button>
                          </div>
                        ) : <span className="text-zinc-600">closed</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!liveRequests.length ? <p className="p-4 text-xs text-zinc-500">No manual live requests recorded.</p> : null}
            </div>
          </Card>

          <Card className="flex flex-col" hover={false}>
            <div className="flex items-center justify-between border-b border-white/5 p-4">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Shield size={14} />
                Live Execution Audit
              </h3>
              <Badge variant="info">{liveAudit.length} Rows</Badge>
            </div>
            <div className="max-h-[360px] overflow-auto p-0 scrollbar-thin scrollbar-thumb-white/10">
              <table className="min-w-full table-fixed border-collapse text-left text-[11px]">
                <colgroup>
                  <col className="w-28" />
                  <col className="w-20" />
                  <col className="w-52" />
                  <col className="w-24" />
                  <col />
                </colgroup>
                <thead className="sticky top-0 z-10 bg-[#10121c]">
                  <tr className="border-b border-white/5">
                    <th className="w-28 px-4 py-2 font-black text-zinc-600">Created</th>
                    <th className="w-20 px-4 py-2 font-black text-zinc-600">Action</th>
                    <th className="w-52 px-4 py-2 font-black text-zinc-600">Mint</th>
                    <th className="w-24 px-4 py-2 font-black text-zinc-600">Status</th>
                    <th className="px-4 py-2 font-black text-zinc-600">Signature</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono">
                  {liveAudit.slice(0, 40).map((audit) => (
                    <tr key={audit.id} className="hover:bg-white/[0.02]">
                      <td className="px-4 py-2 text-zinc-500">{new Date(audit.created_at).toLocaleTimeString()}</td>
                      <td className="px-4 py-2 text-zinc-300">{audit.action}</td>
                      <td className="max-w-[180px] truncate px-4 py-2 text-zinc-500" title={audit.mint}>{audit.mint}</td>
                      <td className="px-4 py-2"><Badge variant={audit.final_status === "confirmed" ? "success" : audit.final_status === "failed" ? "danger" : "warning"}>{audit.final_status || audit.status}</Badge></td>
                      <td className="max-w-[220px] truncate px-4 py-2 text-zinc-500">
                        {audit.transaction_signature ? (
                          <a className="text-blue-400 hover:text-blue-300" href={`https://solscan.io/tx/${audit.transaction_signature}`} target="_blank" rel="noreferrer">{audit.transaction_signature}</a>
                        ) : "not submitted"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!liveAudit.length ? <p className="p-4 text-xs text-zinc-500">No live execution audit rows recorded.</p> : null}
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
             <Card className="p-4" hover={false}>
              <h3 className="mb-4 text-xs font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Trash2 size={14} className="text-rose-500" />
                Data Purge
              </h3>
              <div className="grid grid-cols-2 gap-1.5">
                {clearTargets.map((target) => (
                  <Button 
                    key={target} 
                    variant="ghost" 
                    size="sm" 
                    className="h-8 justify-start border border-white/5 bg-white/[0.02] px-3 py-1.5 text-[10px] font-bold tracking-normal text-zinc-400 hover:border-rose-500/20 hover:bg-rose-500/10 hover:text-rose-500"
                    onClick={() => onClear(target)}
                  >
                    {target.replace(/_/g, " ")}
                  </Button>
                ))}
              </div>
            </Card>

            <Card className="p-4" hover={false}>
              <h3 className="mb-4 text-xs font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Download size={14} className="text-blue-500" />
                Export Portal
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {exportTargets.map((target) => (
                  <a 
                    key={target}
                    href={exportUrl(target as any)}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center rounded-lg border border-white/5 bg-white/[0.02] px-3 py-1.5 text-[10px] font-bold text-zinc-400 transition-all hover:bg-blue-500/10 hover:text-blue-500 hover:border-blue-500/20"
                  >
                    {target.replace(/_/g, " ")}
                  </a>
                ))}
              </div>
            </Card>
          </div>
        </div>

        {/* Right Column: Status & Health */}
        <div className="space-y-6">
          <Card className="p-6" hover={false}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Database size={16} />
                Migration Status
              </h3>
              <Badge variant={opsMonitoring?.schema?.ok ? "success" : "warning"}>{opsMonitoring?.schema?.status ?? "pending"}</Badge>
            </div>
            {!opsMonitoring?.schema ? (
              <div className="space-y-3">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : (
              <div className="space-y-3 text-[11px]">
                <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3">
                  <span className="text-zinc-500">Schema Version</span>
                  <span className="font-black text-white">{opsMonitoring.schema.current_version} / {opsMonitoring.schema.expected_version}</span>
                </div>
                {opsMonitoring.schema.startup_error ? (
                  <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-rose-200">{opsMonitoring.schema.startup_error}</div>
                ) : null}
                <div className="space-y-2">
                  {opsMonitoring.schema.migrations.slice(0, 5).map((migration) => (
                    <div key={migration.migration_id} className="rounded-xl bg-white/[0.02] p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-black text-white">{migration.migration_id}</span>
                        <span className="text-zinc-500">{new Date(migration.applied_at).toLocaleDateString()}</span>
                      </div>
                      <p className="mt-1 text-zinc-400">{migration.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          <Card className="p-6" hover={false}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Upload size={16} />
                Import / Restore
              </h3>
              <input
                ref={restoreInputRef}
                type="file"
                accept="application/json"
                className="hidden"
                onChange={(event) => void handleRestoreFile(event.target.files?.[0] ?? null)}
              />
              <Button variant="secondary" size="sm" onClick={() => restoreInputRef.current?.click()} disabled={restoreBusy}>
                Select Artifact
              </Button>
            </div>
            <div className="space-y-3 text-[11px]">
              <p className="text-zinc-400">Preview a local backup artifact before replacing the SQLite state. Restore always creates a safety copy first.</p>
              {restoreFileName ? <div className="rounded-xl bg-white/[0.02] p-3 text-zinc-300">{restoreFileName}</div> : null}
              {restorePreview ? (
                <div className="space-y-3 rounded-xl border border-white/5 bg-white/[0.02] p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-zinc-500">Schema</span>
                    <span className="font-black text-white">{restorePreview.schema_version} {"->"} {restorePreview.current_schema_version}</span>
                  </div>
                  <div className="space-y-2">
                    {restorePreview.warnings.map((warning) => (
                      <div key={warning} className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-amber-100">{warning}</div>
                    ))}
                  </div>
                  <Button variant="danger" size="sm" onClick={confirmRestore} disabled={!restorePreview.compatible || restoreBusy}>
                    Confirm Restore
                  </Button>
                </div>
              ) : null}
              {restoreMessage ? <div className="rounded-xl bg-white/[0.02] p-3 text-zinc-300">{restoreMessage}</div> : null}
            </div>
          </Card>

          <Card className="p-6" hover={false}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Shield size={16} />
                Signer Daemon
              </h3>
              <Badge variant={signerDaemon?.healthy ? "success" : "warning"}>{signerDaemon?.healthy ? "healthy" : "blocked"}</Badge>
            </div>
            <div className="space-y-3 text-[11px]">
              <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3">
                <span className="text-zinc-500">Transport</span>
                <span className="font-black text-white">{signerDaemon?.transport ?? "localhost_http"}</span>
              </div>
              <div className="rounded-xl bg-white/[0.02] p-3 text-zinc-300 break-all">{signerDaemon?.endpoint || "http://127.0.0.1:8799"}</div>
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-amber-100">
                {signerDaemon?.disabled_reason || "Browser wallet remains the only active signer path in this phase."}
              </div>
            </div>
          </Card>

          <Card className="p-6" hover={false}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Shield size={16} />
                Readiness
              </h3>
              <Badge variant={readinessTone}>
                {readinessStatus?.status?.replace(/_/g, " ") || "unknown"}
              </Badge>
            </div>
            <div className="space-y-4">
              {!readinessStatus ? (
                <div className="space-y-3">
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                </div>
              ) : readinessStatus.gates.map((gate) => (
                <div key={gate.id} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-bold text-zinc-400">{gate.label}</span>
                    <span className={cn("font-black", gate.status === "pass" ? "text-emerald-500" : gate.status === "warn" ? "text-amber-400" : "text-rose-500")}>
                      {String(gate.value)} / {gate.target}
                    </span>
                  </div>
                  <div className="h-1 w-full rounded-full bg-white/5">
                    <div 
                      className={cn("h-full rounded-full", gate.status === "pass" ? "bg-emerald-500" : gate.status === "warn" ? "bg-amber-400" : "bg-rose-500")}
                      style={{ width: `${gate.status === "pass" ? 100 : gate.status === "warn" ? 60 : 28}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-zinc-600">{gate.reason}</span>
                </div>
              ))}
              {readinessStatus?.recommended_actions?.length ? (
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px] text-zinc-400">
                  {readinessStatus.recommended_actions.slice(0, 3).map((action) => (
                    <div key={action} className="flex gap-2 py-1">
                      <ChevronRight size={12} className="mt-0.5 shrink-0 text-amber-300" />
                      <span>{action}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </Card>

          <Card className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Activity size={16} />
              Operations
            </h3>
            <div className="space-y-3">
              {loadingCore ? (
                <>
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </>
              ) : (
                <>
                  <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <span className="text-zinc-500">Watchdog</span>
                    <span className="font-black text-white">{watchdogStatus?.status} ({watchdogStatus?.tick_age_seconds}s)</span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <span className="text-zinc-500">Source Health</span>
                    <span className={cn("font-black", sourceHealthTone)}>{sourceHealth?.health_score}%</span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <span className="text-zinc-500">RPC Health</span>
                    <span className="font-black text-emerald-500">{solanaStatus?.health}</span>
                  </div>
                </>
              )}
              <Button variant="secondary" size="sm" className="w-full mt-2" onClick={onRecover}>
                <RotateCcw size={14} className="mr-2" />
                Recover System
              </Button>
            </div>
          </Card>

          <Card className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Gauge size={16} />
              Security Boundary
            </h3>
            <div className="space-y-2 text-[11px]">
              {!securityStatus ? (
                <>
                  <Skeleton className="h-6 w-full" />
                  <Skeleton className="h-6 w-full" />
                  <Skeleton className="h-6 w-full" />
                  <Skeleton className="h-6 w-full" />
                </>
              ) : (
                <>
                  <div className="flex justify-between border-b border-white/5 pb-2">
                    <span className="text-zinc-500 font-bold uppercase tracking-tighter">Auth</span>
                    <span className={cn("font-black", securityStatus?.auth_enabled ? "text-emerald-500" : "text-amber-500")}>{securityStatus?.auth_enabled ? "Enabled" : "Disabled"}</span>
                  </div>
                  <div className="flex justify-between border-b border-white/5 py-2">
                    <span className="text-zinc-500 font-bold uppercase tracking-tighter">2FA</span>
                    <span className={cn("font-black", securityStatus?.totp_enabled ? "text-emerald-500" : "text-zinc-400")}>{securityStatus?.totp_enabled ? "Active" : "Off"}</span>
                  </div>
                  <div className="flex justify-between border-b border-white/5 py-2">
                    <span className="text-zinc-500 font-bold uppercase tracking-tighter">Live Env</span>
                    <span className="text-rose-500 font-black">Blocked by default</span>
                  </div>
                  <div className="flex justify-between pt-2">
                    <span className="text-zinc-500 font-bold uppercase tracking-tighter">Boundary</span>
                    <span className="text-zinc-300 font-black italic">Paper Only</span>
                  </div>
                </>
              )}
            </div>
          </Card>

          <Card className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Clock size={16} />
              Backup / Restore History
            </h3>
            <div className="space-y-2 text-[11px]">
              {backupRestoreHistory.slice(0, 6).map((item: BackupRestoreHistoryEntry, index) => (
                <div key={`${item.created_at ?? "entry"}-${index}`} className="rounded-xl bg-white/[0.02] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-black uppercase tracking-widest text-white">{String(item.action ?? "event")}</span>
                    <Badge variant={item.status === "restored" ? "warning" : "info"}>{String(item.status ?? "recorded")}</Badge>
                  </div>
                  <p className="mt-1 text-zinc-400">{String(item.operator_action ?? "Operator history entry")}</p>
                </div>
              ))}
              {!backupRestoreHistory.length ? <p className="text-zinc-500">No backup or restore history yet.</p> : null}
            </div>
          </Card>

          <Card className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Bell size={16} />
              By Subsystem
            </h3>
            <div className="space-y-2 text-[11px]">
              {Object.entries(opsMonitoring?.events_by_subsystem ?? {}).slice(0, 8).map(([subsystem, events]) => (
                <div key={subsystem} className="rounded-xl bg-white/[0.02] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-black uppercase tracking-widest text-white">{subsystem}</span>
                    <Badge variant="info">{events.length}</Badge>
                  </div>
                  <p className="mt-1 text-zinc-400">{events[0]?.message ?? "No recent events"}</p>
                </div>
              ))}
              {!Object.keys(opsMonitoring?.events_by_subsystem ?? {}).length ? <p className="text-zinc-500">No subsystem groups available yet.</p> : null}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
