import React from "react";
import { 
  Database, 
  Download, 
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
import { cn } from "../components/utils";
import { exportUrl, backupDatabase } from "../api";
import type { 
  DataSummary, 
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

const DataMetric: React.FC<{ label: string; value: string | number; color?: string }> = ({ label, value, color = "text-white" }) => (
  <div className="flex flex-col gap-1 rounded-xl border border-white/5 bg-white/[0.02] p-3 transition-colors hover:bg-white/[0.04]">
    <span className="text-[9px] font-black uppercase tracking-widest text-zinc-500">{label}</span>
    <span className={cn("text-sm font-black tracking-tight", color)}>{value}</span>
  </div>
);

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
        </div>
      </PageHeader>

      {/* High-Density Metrics Grid */}
      <Card className="p-4" hover={false}>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
          <DataMetric label="Tokens" value={summary?.tokens ?? 0} />
          <DataMetric label="Audit" value={summary?.events ?? 0} />
          <DataMetric label="Signals" value={summary?.source_events ?? 0} />
          <DataMetric label="Trades" value={summary?.trades ?? 0} />
          <DataMetric label="Decisions" value={summary?.strategy_decisions ?? 0} />
          <DataMetric label="Prices" value={summary?.price_observations ?? 0} />
          <DataMetric label="Readiness" value={`${readinessStatus?.score ?? 0}%`} color="text-amber-500" />
          <DataMetric label="Integrity" value={`${dataIntegrity?.score ?? 0}%`} color="text-emerald-500" />
          <DataMetric label="Health" value={`${sourceHealth?.health_score ?? 0}%`} color="text-blue-500" />
          <DataMetric label="RPC" value={solanaStatus?.health ?? "unknown"} color={solanaStatus?.health === "ok" ? "text-emerald-500" : "text-rose-500"} />
          <DataMetric label="Watchdog" value={watchdogStatus?.status ?? "unknown"} />
          <DataMetric label="Live Reqs" value={liveRequests.length} color="text-rose-500" />
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
              <table className="w-full border-collapse text-left text-[11px]">
                <thead className="sticky top-0 z-10 bg-[#10121c] after:absolute after:bottom-0 after:left-0 after:h-px after:w-full after:bg-white/5">
                  <tr>
                    <th className="px-4 py-2 font-black text-zinc-600">Timestamp</th>
                    <th className="px-4 py-2 font-black text-zinc-600">Level</th>
                    <th className="px-4 py-2 font-black text-zinc-600">Message</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono">
                  {auditEvents.map((event) => (
                    <tr key={event.id} className="hover:bg-white/[0.02]">
                      <td className="whitespace-nowrap px-4 py-2 text-zinc-500">
                        {new Date(event.created_at).toLocaleTimeString()}
                      </td>
                      <td className="px-4 py-2">
                        <span className={cn(
                          "font-bold uppercase",
                          event.level === "error" ? "text-rose-500" : event.level === "warn" ? "text-amber-500" : "text-emerald-500"
                        )}>
                          {event.level}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-zinc-300">{event.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
              <table className="w-full border-collapse text-left text-[11px]">
                <thead className="sticky top-0 z-10 bg-[#10121c]">
                  <tr>
                    <th className="px-4 py-2 font-black text-zinc-600">Created</th>
                    <th className="px-4 py-2 font-black text-zinc-600">Action</th>
                    <th className="px-4 py-2 font-black text-zinc-600">Amount</th>
                    <th className="px-4 py-2 font-black text-zinc-600">Status</th>
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
              <table className="w-full border-collapse text-left text-[11px]">
                <thead className="sticky top-0 z-10 bg-[#10121c]">
                  <tr>
                    <th className="px-4 py-2 font-black text-zinc-600">Created</th>
                    <th className="px-4 py-2 font-black text-zinc-600">Action</th>
                    <th className="px-4 py-2 font-black text-zinc-600">Mint</th>
                    <th className="px-4 py-2 font-black text-zinc-600">Status</th>
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
              <div className="grid grid-cols-2 gap-2">
                {clearTargets.map((target) => (
                  <Button 
                    key={target} 
                    variant="ghost" 
                    size="sm" 
                    className="justify-start text-[10px] h-8 border border-white/5 bg-white/[0.02] hover:bg-rose-500/10 hover:text-rose-500 hover:border-rose-500/20"
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
                <Shield size={16} />
                Readiness
              </h3>
              <Badge variant={readinessStatus?.entries_allowed ? "success" : "danger"}>
                {readinessStatus?.entries_allowed ? "Ready" : "Halted"}
              </Badge>
            </div>
            <div className="space-y-4">
              {readinessStatus?.gates.map((gate) => (
                <div key={gate.id} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-bold text-zinc-400">{gate.label}</span>
                    <span className={cn("font-black", gate.status === "pass" ? "text-emerald-500" : "text-rose-500")}>
                      {String(gate.value)} / {gate.target}
                    </span>
                  </div>
                  <div className="h-1 w-full rounded-full bg-white/5">
                    <div 
                      className={cn("h-full rounded-full", gate.status === "pass" ? "bg-emerald-500" : "bg-rose-500")}
                      style={{ width: `${Math.min(100, (Number(gate.value) / Number(gate.target)) * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Activity size={16} />
              Operations
            </h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3 text-[11px]">
                <span className="text-zinc-500">Watchdog</span>
                <span className="font-black text-white">{watchdogStatus?.status} ({watchdogStatus?.tick_age_seconds}s)</span>
              </div>
              <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3 text-[11px]">
                <span className="text-zinc-500">Source Health</span>
                <span className="font-black text-emerald-500">{sourceHealth?.health_score}%</span>
              </div>
              <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3 text-[11px]">
                <span className="text-zinc-500">RPC Health</span>
                <span className="font-black text-emerald-500">{solanaStatus?.health}</span>
              </div>
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
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
