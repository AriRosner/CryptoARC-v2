import React from "react";
import { 
  BarChart3, 
  Shield, 
  Target, 
  Sparkles, 
  Activity, 
  Gauge, 
  Clock,
  TrendingUp
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Card } from "../components/Card";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { PnlChart } from "../components/PnlChart";
import { Skeleton } from "../components/Skeleton";
import { cn } from "../components/utils";
import type { 
  TokenSignal, 
  TradeRecord, 
  PerformanceAnalytics, 
  TuningSuggestion, 
  PriceDiagnostics, 
  PumpFunReport, 
  SafetyStatus, 
  ReadinessStatus 
} from "../types";

interface AnalysisPageProps {
  tokens: TokenSignal[];
  trades: TradeRecord[];
  stats: any;
  analytics: PerformanceAnalytics | null;
  suggestions: TuningSuggestion[];
  priceDiagnostics: PriceDiagnostics | null;
  pumpfunReport: PumpFunReport | null;
  safetyStatus: SafetyStatus | null;
  readinessStatus: ReadinessStatus | null;
  pnlTimeframe: string;
  onTimeframeChange: (t: any) => void;
  onApplySuggestion: (suggestion: TuningSuggestion) => Promise<void>;
}

const AnalysisMetric: React.FC<{ label: string; value: string | number; color?: string; loading?: boolean }> = ({ label, value, color = "text-white", loading = false }) => (
  <div className="flex flex-col gap-1 rounded-xl border border-white/5 bg-white/[0.02] p-4 transition-colors hover:bg-white/[0.04]">
    <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">{label}</span>
    {loading ? <Skeleton className="h-7 w-24" /> : <span className={cn("text-xl font-black tracking-tight", color)}>{value}</span>}
  </div>
);

const BarMetric: React.FC<{ label: string; value: number; max: number; color?: string }> = ({ label, value, max, color = "bg-amber-500/50" }) => (
  <div className="space-y-1.5">
    <div className="flex items-center justify-between text-[11px]">
      <span className="font-bold text-zinc-400 uppercase tracking-tight">{label}</span>
      <span className="font-black text-white">{value}</span>
    </div>
    <div className="h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
      <div 
        className={cn("h-full rounded-full transition-all duration-1000", color)}
        style={{ width: `${Math.min(100, (value / (max || 1)) * 100)}%` }}
      />
    </div>
  </div>
);

function formatLatency(ms: number): string {
  if (!ms) return "0ms";
  if (ms >= 1000) return `${(ms / 1000).toFixed(ms >= 10000 ? 0 : 1)}s`;
  return `${ms}ms`;
}

export const AnalysisPage: React.FC<AnalysisPageProps> = ({
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
  onTimeframeChange,
  onApplySuggestion
}) => {
  const loadingAnalytics = !analytics || !priceDiagnostics || !pumpfunReport || !safetyStatus || !readinessStatus;
  const closed = trades.filter(t => t.lifecycle_status === "closed" && t.pnl_sol !== null);
  const timeframePnl = closed.reduce((total, t) => total + (t.pnl_sol || 0), 0);
  const scratchThreshold = stats.scratch_threshold_sol ?? 0.001;
  const wins = closed.filter(t => (t.pnl_sol || 0) > scratchThreshold).length;
  const losses = closed.filter(t => (t.pnl_sol || 0) < -scratchThreshold).length;
  
  const avgHold = closed.length
    ? closed.reduce((total, t) => total + (t.hold_duration_seconds || 0), 0) / closed.length
    : 0;
  const promotion = readinessStatus?.strategy_promotion;
  const promotionTone = promotion?.can_promote ? "success" : promotion?.status === "not_enough_data" ? "warning" : "danger";
  const execution = readinessStatus?.execution_readiness;
  const executionTone = execution?.can_shadow ? "success" : execution?.status === "not_enough_quote_data" ? "warning" : "danger";
  const quoteEvidenceWindowLabel = execution ? `${execution.quote_evidence_window_hours}h` : "24h";

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Intelligence Analysis" 
        description="Deep-dive into paper P&L, decision quality, and engine diagnostics."
      >
        <div className="flex items-center gap-1 rounded-xl bg-white/5 p-1">
          {["5m", "15m", "1h", "all"].map((t) => (
            <button
              key={t}
              onClick={() => onTimeframeChange(t)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-[10px] font-black uppercase tracking-widest transition-all",
                pnlTimeframe === t 
                  ? "bg-amber-500 text-[#160f08] shadow-lg shadow-amber-500/20" 
                  : "text-zinc-500 hover:text-white"
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </PageHeader>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
        <AnalysisMetric label="Range P&L" value={`${timeframePnl.toFixed(4)} SOL`} color={timeframePnl >= 0 ? "text-emerald-500" : "text-rose-500"} />
        <AnalysisMetric label="W / L" value={`${wins} / ${losses}`} />
        <AnalysisMetric label="Avg Hold" value={`${Math.round(avgHold)}s`} />
        <AnalysisMetric label="Readiness" value={`${readinessStatus?.score ?? 0}%`} color="text-amber-500" loading={!readinessStatus} />
        <AnalysisMetric label="Safety" value={safetyStatus?.entries_allowed ? "OK" : "GUARD"} color={safetyStatus?.entries_allowed ? "text-emerald-500" : "text-rose-500"} loading={!safetyStatus} />
        <AnalysisMetric label="Open" value={stats.open_positions} />
        <AnalysisMetric label="Best" value={`${stats.best_trade_sol.toFixed(3)}`} color="text-emerald-500" />
        <AnalysisMetric label="Win Rate" value={`${stats.win_rate_pct}%`} color="text-amber-500" />
      </div>

      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-2">
        <div className="space-y-6">
          <Card className="p-6" hover={false}>
            <div className="mb-6 flex items-center justify-between">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <BarChart3 size={16} />
                P&L Accumulation Curve
              </h3>
              <Badge variant="success">+{timeframePnl.toFixed(4)} SOL</Badge>
            </div>
            <PnlChart data={trades.map(t => t.pnl_sol || 0)} height={300} />
          </Card>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <Card className="p-6" hover={false}>
              <h3 className="mb-6 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Gauge size={16} />
                Price Engine v3
              </h3>
              {!priceDiagnostics ? (
                <div className="space-y-4">
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-8 w-full" />
                </div>
              ) : (
                <div className="space-y-5">
                  <BarMetric label="Acceptance Rate" value={Math.round((priceDiagnostics?.acceptance_rate ?? 0) * 100)} max={100} color="bg-emerald-500/50" />
                  <BarMetric label="Jump Warnings" value={priceDiagnostics?.impossible_jump_warnings ?? 0} max={20} color="bg-rose-500/50" />
                  <BarMetric label="Observation Density" value={priceDiagnostics?.observations ?? 0} max={1000} color="bg-blue-500/50" />
                </div>
              )}
            </Card>

            <Card className="p-6" hover={false}>
              <h3 className="mb-6 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Activity size={16} />
                Decision Mix
              </h3>
              <div className="space-y-5">
                <BarMetric label="Bought" value={tokens.filter(t => t.status.includes("bought")).length} max={tokens.length} color="bg-emerald-500/50" />
                <BarMetric label="Skipped" value={tokens.filter(t => t.status === "skipped").length} max={tokens.length} color="bg-zinc-500/50" />
                <BarMetric label="Analyzing" value={tokens.filter(t => t.status === "analyzing").length} max={tokens.length} color="bg-amber-500/50" />
              </div>
            </Card>

            <Card className="p-6" hover={false}>
              <h3 className="mb-6 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <TrendingUp size={16} />
                Creator Reputation
              </h3>
              {!pumpfunReport ? (
                <div className="space-y-3">
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                </div>
              ) : (
                <div className="space-y-3">
                  {pumpfunReport.creator_performance.slice(0, 4).map((creator) => (
                    <div key={creator.creator} className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px]">
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate font-bold text-zinc-300">{creator.creator}</span>
                        <Badge variant={creator.reputation === "positive" ? "success" : creator.reputation === "negative" || creator.reputation === "exclude_or_review" ? "danger" : "warning"}>
                          {creator.reputation.replace(/_/g, " ")}
                        </Badge>
                      </div>
                      <div className="mt-2 flex items-center justify-between gap-3 text-[10px] text-zinc-500">
                        <span>{creator.launches} launches / {creator.closed_trades} closed</span>
                        <span className={cn("font-black", creator.pnl_sol >= 0 ? "text-emerald-400" : "text-rose-400")}>{creator.pnl_sol.toFixed(4)} SOL</span>
                      </div>
                      <BarMetric label="Creator win rate" value={creator.win_rate_pct} max={100} color={creator.win_rate_pct >= 50 ? "bg-emerald-500/40" : "bg-rose-500/40"} />
                    </div>
                  ))}
                  {!pumpfunReport.creator_performance.length ? <p className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-xs text-zinc-500">No creator performance evidence yet.</p> : null}
                </div>
              )}
            </Card>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2 2xl:grid-cols-1">
          <Card className="p-6" hover={false}>
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Shield size={16} />
                Promotion Gates
              </h3>
              <Badge variant={promotionTone}>{promotion?.status?.replace(/_/g, " ") ?? "unknown"}</Badge>
            </div>
            {!promotion ? (
              <div className="space-y-3">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : (
              <div className="space-y-3">
                <p className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px] font-bold text-zinc-300">{promotion.summary}</p>
                {promotion.out_of_sample ? (
                  <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px] text-zinc-300">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <span className="font-black uppercase tracking-widest text-zinc-500">Out-of-sample</span>
                      <span className={cn("font-black", promotion.out_of_sample.collapse_warning ? "text-rose-400" : "text-emerald-400")}>
                        {promotion.out_of_sample.collapse_warning ? "collapse" : "stable"}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="rounded-lg bg-black/20 p-2">
                        <span className="block text-[9px] font-black uppercase tracking-widest text-zinc-600">Train</span>
                        <span className="font-black text-white">{promotion.out_of_sample.train.estimated_pnl_sol.toFixed(4)} SOL</span>
                        <span className="mt-0.5 block text-[10px] text-zinc-500">PF {promotion.out_of_sample.train.profit_factor.toFixed(2)} / {promotion.out_of_sample.split.train_tokens} tokens</span>
                      </div>
                      <div className="rounded-lg bg-black/20 p-2">
                        <span className="block text-[9px] font-black uppercase tracking-widest text-zinc-600">Validate</span>
                        <span className={cn("font-black", promotion.out_of_sample.validate.estimated_pnl_sol >= 0 ? "text-emerald-400" : "text-rose-400")}>{promotion.out_of_sample.validate.estimated_pnl_sol.toFixed(4)} SOL</span>
                        <span className="mt-0.5 block text-[10px] text-zinc-500">PF {promotion.out_of_sample.validate.profit_factor.toFixed(2)} / {promotion.out_of_sample.split.validate_tokens} tokens</span>
                      </div>
                    </div>
                  </div>
                ) : null}
                {promotion.gates.slice(0, 6).map((gate) => (
                  <div key={gate.id} className="rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-bold text-zinc-400">{gate.label}</span>
                      <span className={cn("font-black", gate.status === "pass" ? "text-emerald-500" : "text-rose-400")}>{String(gate.value)}</span>
                    </div>
                    <div className="mt-1 flex items-center justify-between gap-3 text-[10px] text-zinc-600">
                      <span>{gate.reason}</span>
                      <span>{String(gate.target)}</span>
                    </div>
                  </div>
                ))}
                {promotion.blockers.length ? (
                  <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-[11px] text-amber-100">
                    {promotion.blockers.slice(0, 3).map((blocker) => <div key={blocker}>{blocker}</div>)}
                  </div>
                ) : null}
              </div>
            )}
          </Card>

          <Card className="p-6" hover={false}>
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Clock size={16} />
                Execution Readiness
              </h3>
              <Badge variant={executionTone}>{execution?.status?.replace(/_/g, " ") ?? "unknown"}</Badge>
            </div>
            {!execution ? (
              <div className="space-y-3">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-2">
                  <div className="rounded-xl bg-white/[0.02] p-3">
                    <div className="text-[9px] font-black uppercase tracking-widest text-zinc-600">Quotes ({quoteEvidenceWindowLabel})</div>
                    <div className="mt-1 text-lg font-black text-white">{execution.metrics.current_quote_attempts}</div>
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3">
                    <div className="text-[9px] font-black uppercase tracking-widest text-zinc-600">Stale ({quoteEvidenceWindowLabel})</div>
                    <div className="mt-1 text-lg font-black text-amber-400">{Math.round(execution.metrics.current_stale_quote_rate * 100)}%</div>
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3">
                    <div className="text-[9px] font-black uppercase tracking-widest text-zinc-600">Unhealthy ({quoteEvidenceWindowLabel})</div>
                    <div className="mt-1 text-lg font-black text-rose-400">{Math.round(execution.metrics.current_unhealthy_quote_rate * 100)}%</div>
                    <div className="mt-1 text-[9px] font-bold text-zinc-600">
                      {execution.metrics.current_failed_quotes} failed / {execution.metrics.current_blocked_quotes} blocked
                    </div>
                  </div>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[10px] text-zinc-500">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-black uppercase tracking-widest text-zinc-600">Loaded history</span>
                    <span className="font-bold text-zinc-400">
                      {execution.metrics.loaded_history_quote_attempts ?? execution.metrics.quote_attempts} quotes
                    </span>
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-3">
                    <span>
                      {Math.round((execution.metrics.loaded_history_stale_quote_rate ?? execution.metrics.stale_quote_rate) * 100)}% stale /{" "}
                      {Math.round((execution.metrics.loaded_history_blocked_quote_rate ?? execution.metrics.blocked_quote_rate) * 100)}% blocked
                    </span>
                    {execution.audit_history_truncated ? (
                      <span className="font-bold text-amber-400">
                        latest {execution.audit_history_limit} records
                      </span>
                    ) : (
                      <span>{execution.audit_history_complete ? "complete" : "partial"}</span>
                    )}
                  </div>
                </div>
                {execution.current_quote_issues?.total_issues ? (
                  <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px] text-zinc-300">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <span className="font-black uppercase tracking-widest text-zinc-500">Quote Issues ({quoteEvidenceWindowLabel})</span>
                      <span className="font-black text-white">{execution.current_quote_issues.total_issues}</span>
                    </div>
                    {execution.current_quote_issues.categories.slice(0, 4).map((issue) => (
                      <div key={issue.category} className="mt-2 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-bold text-zinc-400">{issue.category.replace(/_/g, " ")}</div>
                          <div className="truncate text-[10px] text-zinc-600">{issue.reasons[0] ?? "No reason recorded"}</div>
                        </div>
                        <span className="shrink-0 font-black text-white">{issue.count}</span>
                      </div>
                    ))}
                    {execution.current_quote_issues.recent.slice(0, 2).map((issue) => (
                      <div key={issue.audit_id} className="mt-2 flex items-center justify-between gap-3 border-t border-white/5 pt-2 text-[10px] text-zinc-600">
                        <span className="truncate">{issue.mint}</span>
                        <span className="shrink-0 font-bold text-zinc-400">{issue.status.replace(/_/g, " ")}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
                {execution.current_failure_stages?.total_failures ? (
                  <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px] text-zinc-300">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <span className="font-black uppercase tracking-widest text-zinc-500">Failure Stages ({quoteEvidenceWindowLabel})</span>
                      <span className="font-black text-white">{execution.current_failure_stages.total_failures}</span>
                    </div>
                    {execution.current_failure_stages.stages.filter((stage) => stage.count > 0).slice(0, 5).map((stage) => (
                      <div key={stage.stage} className="mt-2 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-bold text-zinc-400">{stage.stage.replace(/_/g, " ")}</div>
                          <div className="truncate text-[10px] text-zinc-600">{stage.categories[0]?.category.replace(/_/g, " ") ?? stage.reasons[0] ?? "No category recorded"}</div>
                        </div>
                        <span className="shrink-0 font-black text-white">{stage.count}</span>
                      </div>
                    ))}
                    <p className="mt-2 border-t border-white/5 pt-2 text-[10px] text-zinc-500">{execution.current_failure_stages.operator_action}</p>
                  </div>
                ) : null}
                <div className="grid grid-cols-3 gap-2">
                  <div className="rounded-xl bg-white/[0.02] p-3">
                    <div className="text-[9px] font-black uppercase tracking-widest text-zinc-600">Loaded history shadow</div>
                    <div className="mt-1 text-lg font-black text-white">{execution.metrics.shadow_evaluated}/{execution.metrics.shadow_samples}</div>
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3">
                    <div className="text-[9px] font-black uppercase tracking-widest text-zinc-600">Win</div>
                    <div className="mt-1 text-lg font-black text-emerald-400">{execution.metrics.shadow_win_rate_pct}%</div>
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3">
                    <div className="text-[9px] font-black uppercase tracking-widest text-zinc-600">Est P&L</div>
                    <div className={cn("mt-1 text-lg font-black", execution.metrics.shadow_estimated_pnl_sol >= 0 ? "text-emerald-400" : "text-rose-400")}>{execution.metrics.shadow_estimated_pnl_sol.toFixed(4)}</div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="rounded-xl bg-white/[0.02] p-3">
                    <div className="text-[9px] font-black uppercase tracking-widest text-zinc-600">Delay</div>
                    <div className="mt-1 text-lg font-black text-white">{execution.metrics.shadow_landing_evaluated}/{execution.metrics.shadow_landing_windows}</div>
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3">
                    <div className="text-[9px] font-black uppercase tracking-widest text-zinc-600">D-Win</div>
                    <div className="mt-1 text-lg font-black text-emerald-400">{execution.metrics.shadow_landing_win_rate_pct}%</div>
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3">
                    <div className="text-[9px] font-black uppercase tracking-widest text-zinc-600">Range</div>
                    <div className="mt-1 text-xs font-black text-zinc-300">{execution.metrics.shadow_landing_worst_pnl_sol.toFixed(4)} / {execution.metrics.shadow_landing_best_pnl_sol.toFixed(4)}</div>
                  </div>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px] text-zinc-300">
                  <div className="mb-3 flex items-center justify-between gap-3 border-b border-white/5 pb-2">
                    <span className="font-black uppercase tracking-widest text-zinc-500">Latency</span>
                    <Badge variant={execution.latency_summary.status === "fast" ? "success" : execution.latency_summary.status === "slow" ? "danger" : "warning"}>
                      {execution.latency_summary.status.replace(/_/g, " ")}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <div className="text-[9px] font-black uppercase tracking-widest text-zinc-600">Signal &gt; Quote</div>
                      <div className="mt-1 font-black text-white">{formatLatency(execution.latency_summary.signal_to_quote_p50_ms)} / {formatLatency(execution.latency_summary.signal_to_quote_p90_ms)}</div>
                    </div>
                    <div>
                      <div className="text-[9px] font-black uppercase tracking-widest text-zinc-600">Quote &gt; Submit</div>
                      <div className="mt-1 font-black text-white">{formatLatency(execution.latency_summary.quote_to_submit_p50_ms)} / {formatLatency(execution.latency_summary.quote_to_submit_p90_ms)}</div>
                    </div>
                  </div>
                  {execution.latency_summary.issues.slice(0, 2).map((issue) => (
                    <div key={issue} className="mt-2 text-[10px] font-bold text-amber-300">{issue}</div>
                  ))}
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px] text-zinc-300">
                  <div className="mb-3 flex items-center justify-between gap-3 border-b border-white/5 pb-2">
                    <span className="font-black uppercase tracking-widest text-zinc-500">Execution Policy</span>
                    <Badge variant={execution.policy.recommendation?.status === "stable" ? "success" : execution.policy.recommendation?.status === "blocked" ? "danger" : "warning"}>
                      {(execution.policy.recommendation?.status ?? "policy").replace(/_/g, " ")}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-bold text-zinc-500">Slippage suggestion</span>
                    <span className="font-black text-white">{execution.policy.suggested_slippage_pct}%</span>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <span className="font-bold text-zinc-500">Priority fee suggestion</span>
                    <span className="font-black text-white">{execution.policy.suggested_priority_fee_sol} SOL</span>
                  </div>
                  {execution.policy.recommendation ? (
                    <>
                      <div className="mt-2 flex items-center justify-between gap-3">
                        <span className="font-bold text-zinc-500">Cap room</span>
                        <span className="font-black text-zinc-300">{execution.policy.recommendation.cap_room.slippage_pct}% / {execution.policy.recommendation.cap_room.priority_fee_sol} SOL</span>
                      </div>
                      <div className="mt-2 flex items-center justify-between gap-3">
                        <span className="font-bold text-zinc-500">Missed landing</span>
                        <span className="font-black text-zinc-300">{Math.round(execution.policy.recommendation.inputs.missed_landing_rate * 100)}%</span>
                      </div>
                      {execution.policy.recommendation.reasons.slice(0, 2).map((reason) => (
                        <div key={reason} className="mt-2 rounded-lg border border-white/5 bg-black/20 p-2 text-[10px] leading-4 text-zinc-400">{reason}</div>
                      ))}
                    </>
                  ) : null}
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <span className="font-bold text-zinc-500">Landing calibration</span>
                    <span className="font-black text-white">{execution.landing_calibration.source} / {execution.landing_calibration.samples}</span>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <span className="font-bold text-zinc-500">Quote submit p50/p90/p99</span>
                    <span className="font-black text-white">{execution.landing_calibration.quote_to_submit_p50_ms} / {execution.landing_calibration.quote_to_submit_p90_ms} / {execution.landing_calibration.quote_to_submit_p99_ms} ms</span>
                  </div>
                  {Object.entries(execution.landing_calibration.by_signer_mode).slice(0, 2).map(([mode, timing]) => (
                    <div key={mode} className="mt-2 flex items-center justify-between gap-3">
                      <span className="font-bold text-zinc-500">{mode.replace(/_/g, " ")}</span>
                      <span className="font-black text-white">{timing.samples} / {timing.quote_to_submit_p90_ms}ms</span>
                    </div>
                  ))}
                  {Object.entries(execution.landing_calibration.by_pool).slice(0, 1).map(([pool, timing]) => (
                    <div key={pool} className="mt-2 flex items-center justify-between gap-3">
                      <span className="font-bold text-zinc-500">Pool {pool}</span>
                      <span className="font-black text-white">{timing.samples} / {timing.quote_to_submit_p90_ms}ms</span>
                    </div>
                  ))}
                  {Object.entries(execution.landing_calibration.by_quote_source).slice(0, 1).map(([source, timing]) => (
                    <div key={source} className="mt-2 flex items-center justify-between gap-3">
                      <span className="font-bold text-zinc-500">{source.replace(/_/g, " ")}</span>
                      <span className="font-black text-white">{timing.samples} / {timing.quote_to_submit_p90_ms}ms</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px] text-zinc-300">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <span className="font-black uppercase tracking-widest text-zinc-500">Pipeline Latency</span>
                    <span className="font-black text-white">{execution.pipeline_latency.samples} samples</span>
                  </div>
                  {[
                    ["Signal -> Quote", "signal_to_quote_ms"],
                    ["Source -> Token", "source_to_token_ms"],
                    ["Token -> Decision", "token_to_decision_ms"],
                    ["Decision -> Intent", "decision_to_intent_ms"],
                    ["Intent -> Quote", "intent_to_quote_ms"],
                    ["Quote -> Submit", "quote_to_submit_ms"]
                  ].map(([label, key]) => {
                    const stage = execution.pipeline_latency.totals[key];
                    return (
                      <div key={key} className="mt-2 flex items-center justify-between gap-3">
                        <span className="font-bold text-zinc-500">{label}</span>
                        <span className="font-black text-white">{formatLatency(stage?.p50_ms ?? 0)} / {formatLatency(stage?.p90_ms ?? 0)}</span>
                      </div>
                    );
                  })}
                  <div className="mt-2 flex items-center justify-between gap-3 border-t border-white/5 pt-2">
                    <span className="font-bold text-zinc-500">Evidence gaps</span>
                    <span className="font-black text-zinc-300">
                      S {execution.pipeline_latency.missing_evidence.source_events} / D {execution.pipeline_latency.missing_evidence.decisions} / I {execution.pipeline_latency.missing_evidence.intents}
                    </span>
                  </div>
                </div>
                {execution.gates.slice(0, 4).map((gate) => (
                  <div key={gate.id} className="rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-bold text-zinc-400">{gate.label}</span>
                      <span className={cn("font-black", gate.status === "pass" ? "text-emerald-500" : "text-rose-400")}>{String(gate.value)}</span>
                    </div>
                    <div className="mt-1 text-[10px] text-zinc-600">{gate.reason}</div>
                  </div>
                ))}
                {execution.shadow_comparisons.length ? (
                  <div className="space-y-2">
                    {execution.shadow_comparisons.slice(0, 3).map((shadow) => (
                      <div key={shadow.audit_id} className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px]">
                        <div className="flex items-center justify-between gap-3">
                          <span className="truncate font-bold text-zinc-300">{shadow.mint}</span>
                          <span className={cn("font-black", shadow.estimated_pnl_sol >= 0 ? "text-emerald-400" : "text-rose-400")}>{shadow.estimated_pnl_sol.toFixed(4)} SOL</span>
                        </div>
                        <div className="mt-1 flex items-center justify-between gap-3 text-[10px] text-zinc-600">
                          <span>{shadow.exit_reason || shadow.status.replace(/_/g, " ")}</span>
                          <span>{shadow.move_pct === null ? "pending" : `${shadow.move_pct.toFixed(1)}%`}</span>
                        </div>
                        {shadow.landing_windows?.length ? (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {shadow.landing_windows.slice(0, 3).map((window) => (
                              <span key={`${shadow.audit_id}-${window.delay_ms}`} className="rounded border border-white/5 bg-black/20 px-1.5 py-0.5 text-[9px] font-bold text-zinc-500">
                                {window.delay_ms}ms {window.outcome}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
                {execution.blockers.length ? (
                  <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-[11px] text-rose-100">
                    {execution.blockers.slice(0, 3).map((blocker) => <div key={blocker}>{blocker}</div>)}
                  </div>
                ) : (
                  <p className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-[11px] font-bold text-emerald-100">
                    Shadow execution comparison can run without submitting transactions.
                  </p>
                )}
              </div>
            )}
          </Card>

          <Card className="p-6" hover={false}>
             <h3 className="mb-6 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Sparkles size={16} />
              Auto-Tuning Engine
            </h3>
            <div className="space-y-4">
              {!suggestions.length && loadingAnalytics ? (
                <>
                  <Skeleton className="h-28 w-full" />
                  <Skeleton className="h-28 w-full" />
                </>
              ) : suggestions.slice(0, 4).map((item, i) => (
                <div key={i} className="rounded-xl border border-white/5 bg-white/[0.02] p-4 transition-all hover:bg-white/[0.04]">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] font-black text-white uppercase tracking-tight">{item.title}</span>
                    <Badge variant="info">{Math.round(item.confidence * 100)}%</Badge>
                  </div>
                  <p className="text-[10px] text-zinc-500 leading-relaxed italic">&ldquo;{item.reason}&rdquo;</p>
                  {item.expected_benefit ? <p className="mt-2 text-[10px] leading-relaxed text-zinc-400">{item.expected_benefit}</p> : null}
                  <div className="mt-3 grid grid-cols-3 gap-2 text-[9px] font-bold uppercase tracking-widest text-zinc-500">
                    <span className="rounded-lg bg-black/20 p-2">Samples <b className="block pt-1 text-xs text-white">{item.supporting_sample_size ?? 0}</b></span>
                    <span className="rounded-lg bg-black/20 p-2">PnL <b className="block pt-1 text-xs text-white">{(item.supporting_pnl_sol ?? 0).toFixed(4)}</b></span>
                    <span className="rounded-lg bg-black/20 p-2">Risk <b className="block pt-1 text-xs text-white">{item.overfit_risk ?? "review"}</b></span>
                  </div>
                  <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase">Suggested</span>
                    <span className="text-[10px] font-black text-amber-500 uppercase">{String(item.suggested_value)}</span>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="mt-3 w-full"
                    onClick={() => onApplySuggestion(item)}
                    disabled={item.suggested_value === undefined}
                  >
                    Implement
                  </Button>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Activity size={16} />
              Wallet Performance
            </h3>
            <div className="space-y-4">
              {!analytics ? (
                <>
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                </>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-2 text-[10px]">
                    {Object.entries(analytics.mode_comparison ?? {}).map(([mode, row]) => (
                      <div key={mode} className="rounded-lg bg-black/20 p-2">
                        <span className="block uppercase tracking-wider text-zinc-500">{row.mode}</span>
                        <span className={cn("mt-1 block font-black", row.pnl_sol >= 0 ? "text-emerald-400" : "text-rose-400")}>{row.pnl_sol.toFixed(4)} SOL</span>
                        <span className="mt-1 block truncate text-zinc-600">{row.samples} samples / {row.confidence}</span>
                      </div>
                    ))}
                  </div>
                  {(analytics.wallets ?? []).slice(0, 3).map((wallet) => (
                    <div key={wallet.wallet_public_key} className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate text-[10px] font-black uppercase tracking-tight text-white">{wallet.wallet_public_key}</span>
                        <Badge variant={wallet.pnl_confidence === "needs_review" ? "danger" : wallet.pnl_confidence === "audited" ? "success" : "warning"}>{wallet.pnl_confidence}</Badge>
                      </div>
                      <div className="mt-2 grid grid-cols-3 gap-2 text-[10px]">
                        <span className="text-zinc-500">Pos <b className="text-white">{wallet.positions}</b></span>
                        <span className="text-zinc-500">Open <b className="text-white">{wallet.open_positions}</b></span>
                        <span className={wallet.total_pnl_sol >= 0 ? "text-emerald-400" : "text-rose-400"}>{wallet.total_pnl_sol.toFixed(4)} SOL</span>
                      </div>
                    </div>
                  ))}
                  {!(analytics.wallets ?? []).length ? <p className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-xs text-zinc-500">No live wallet ledger performance yet.</p> : null}
                </>
              )}
            </div>
          </Card>

          <Card className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Target size={16} />
              Strategy Performance
            </h3>
            <div className="space-y-4">
              {!analytics ? (
                <>
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                </>
              ) : analytics.by_strategy.slice(0, 3).map((item, i) => (
                <div key={i} className="space-y-1.5">
                  <div className="flex justify-between text-[10px] font-bold uppercase tracking-tight">
                    <span className="text-zinc-400">{item.label}</span>
                    <span className={item.pnl_sol >= 0 ? "text-emerald-500" : "text-rose-500"}>
                      {item.pnl_sol.toFixed(3)} SOL
                    </span>
                  </div>
                  <BarMetric label="Win Rate" value={item.win_rate_pct} max={100} color={item.win_rate_pct > 50 ? "bg-emerald-500/40" : "bg-rose-500/40"} />
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
