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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
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
          </div>
        </div>

        <div className="space-y-6">
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
