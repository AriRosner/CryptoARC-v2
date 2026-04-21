import React from "react";
import { History, Play, Target, TrendingUp } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { Badge } from "../components/Badge";
import { cn } from "../components/utils";
import type { BacktestResult, BacktestV3Result, ExperimentRun } from "../types";

interface BacktestsPageProps {
  runs: BacktestResult[];
  latest: BacktestResult | null;
  limit: number;
  profile: string;
  dateFrom: string;
  dateTo: string;
  speed: string;
  onLimitChange: (n: number) => void;
  onProfileChange: (p: string) => void;
  onDateFromChange: (d: string) => void;
  onDateToChange: (d: string) => void;
  onSpeedChange: (s: string) => void;
  onRun: () => void;
  onRawReplay: () => void;
  onCompare: () => void;
  onABReplay: () => void;
  onRunV3: () => void;
  onSaveExperiment: () => void;
  v3Result: BacktestV3Result | null;
  experiments: ExperimentRun[];
}

export const BacktestsPage: React.FC<BacktestsPageProps> = ({
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
  onSaveExperiment
}) => {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Replay Lab"
        description="Backtest strategies against historical PumpPortal launch data."
      >
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={onRawReplay}>
            Raw Replay
          </Button>
          <Button variant="secondary" size="sm" onClick={onRunV3}>
            Suite V3
          </Button>
          <Button variant="primary" size="sm" onClick={onRun}>
            <Play size={14} className="mr-2" />
            Run Backtest
          </Button>
        </div>
      </PageHeader>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        <div className="space-y-6 lg:col-span-1">
          <Card className="p-6" hover={false}>
            <h3 className="mb-6 flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
              <Target size={16} className="text-amber-400" />
              Configuration
            </h3>
            <div className="space-y-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-[10px] font-bold uppercase tracking-tight text-zinc-500">Strategy Profile</span>
                <select value={profile} onChange={(event) => onProfileChange(event.target.value)} className="dashboard-select rounded-lg border border-white/10 bg-black px-3 py-2 text-xs text-white">
                  <option value="conservative">Conservative</option>
                  <option value="balanced">Balanced</option>
                  <option value="aggressive">Aggressive</option>
                  <option value="custom">Custom</option>
                </select>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-[10px] font-bold uppercase tracking-tight text-zinc-500">Launch Limit</span>
                <input type="number" value={limit} onChange={(event) => onLimitChange(parseInt(event.target.value, 10) || 0)} className="rounded-lg border border-white/10 bg-black px-3 py-2 text-xs text-white" />
              </label>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-1">
                <label className="flex flex-col gap-1.5">
                  <span className="text-[10px] font-bold uppercase tracking-tight text-zinc-500">From Date</span>
                  <input type="date" value={dateFrom} onChange={(event) => onDateFromChange(event.target.value)} className="rounded-lg border border-white/10 bg-black px-3 py-2 text-xs text-white" />
                </label>
                <label className="flex flex-col gap-1.5">
                  <span className="text-[10px] font-bold uppercase tracking-tight text-zinc-500">To Date</span>
                  <input type="date" value={dateTo} onChange={(event) => onDateToChange(event.target.value)} className="rounded-lg border border-white/10 bg-black px-3 py-2 text-xs text-white" />
                </label>
              </div>

              <label className="flex flex-col gap-1.5">
                <span className="text-[10px] font-bold uppercase tracking-tight text-zinc-500">Simulation Speed</span>
                <select value={speed} onChange={(event) => onSpeedChange(event.target.value)} className="dashboard-select rounded-lg border border-white/10 bg-black px-3 py-2 text-xs text-white">
                  <option value="instant">Instant</option>
                  <option value="fast">Fast (10x)</option>
                  <option value="realtime">Real-time</option>
                </select>
              </label>

              <div className="grid grid-cols-2 gap-2 pt-2">
                <Button variant="outline" size="sm" onClick={onCompare}>Compare</Button>
                <Button variant="outline" size="sm" onClick={onABReplay}>A/B Test</Button>
              </div>
            </div>
          </Card>
        </div>

        <div className="space-y-6 lg:col-span-3">
          {latest ? (
            <Card className="border-amber-500/20 bg-amber-500/[0.02] p-6" hover={false}>
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-amber-500">
                    <TrendingUp size={16} />
                    Latest Run Results
                  </h3>
                  <p className="mt-1 text-[10px] text-zinc-500">Profile: {latest.profile} | {new Date(latest.created_at).toLocaleTimeString()}</p>
                </div>
                <Button variant="primary" size="sm" onClick={onSaveExperiment}>Save Experiment</Button>
              </div>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div className="rounded-xl border border-white/5 bg-black/40 p-4">
                  <span className="text-[9px] font-bold uppercase tracking-widest text-zinc-500">Est. P&amp;L</span>
                  <div className={cn("text-xl font-black", latest.estimated_pnl_sol >= 0 ? "text-emerald-500" : "text-rose-500")}>
                    {latest.estimated_pnl_sol >= 0 ? "+" : ""}
                    {latest.estimated_pnl_sol.toFixed(4)} SOL
                  </div>
                </div>
                <div className="rounded-xl border border-white/5 bg-black/40 p-4">
                  <span className="text-[9px] font-bold uppercase tracking-widest text-zinc-500">Win Rate</span>
                  <div className="text-xl font-black text-amber-500">{latest.win_rate_pct}%</div>
                </div>
                <div className="rounded-xl border border-white/5 bg-black/40 p-4">
                  <span className="text-[9px] font-bold uppercase tracking-widest text-zinc-500">Total Buys</span>
                  <div className="text-xl font-black text-white">{latest.paper_buys}</div>
                </div>
                <div className="rounded-xl border border-white/5 bg-black/40 p-4">
                  <span className="text-[9px] font-bold uppercase tracking-widest text-zinc-500">Skips</span>
                  <div className="text-xl font-black text-zinc-400">{latest.skips}</div>
                </div>
              </div>
            </Card>
          ) : null}

          <Card className="flex h-[400px] flex-col" hover={false}>
            <div className="flex items-center justify-between border-b border-white/5 p-4">
              <h3 className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-zinc-500">
                <History size={14} className="text-amber-400" />
                History
              </h3>
              <Badge variant="info">{runs.length} Runs</Badge>
            </div>
            <div className="flex-1 overflow-auto scrollbar-thin scrollbar-thumb-white/10">
              <div className="min-w-[590px] text-[11px]">
                <div className="sticky top-0 z-10 grid h-11 grid-cols-[180px_120px_90px_110px_90px] border-b border-white/5 bg-[#10121c]">
                  <div className="flex items-center px-6 font-black text-zinc-600">Timestamp</div>
                  <div className="flex items-center px-6 font-black text-zinc-600">Profile</div>
                  <div className="flex items-center px-6 font-black text-zinc-600">Limit</div>
                  <div className="flex items-center justify-end px-6 font-black text-zinc-600">P&amp;L</div>
                  <div className="flex items-center justify-end px-6 font-black text-zinc-600">Win %</div>
                </div>
                <div className="divide-y divide-white/5 font-mono">
                  {runs.map((run) => (
                    <div key={run.id} className="grid h-11 grid-cols-[180px_120px_90px_110px_90px] hover:bg-white/[0.02]">
                      <div className="flex items-center whitespace-nowrap px-6 text-zinc-500">{new Date(run.created_at).toLocaleString()}</div>
                      <div className="flex items-center truncate px-6 font-bold text-white">{run.profile}</div>
                      <div className="flex items-center px-6 text-zinc-400">{run.tokens_replayed}</div>
                      <div className={cn("flex items-center justify-end px-6 font-black", run.estimated_pnl_sol >= 0 ? "text-emerald-500" : "text-rose-500")}>
                        {run.estimated_pnl_sol.toFixed(4)}
                      </div>
                      <div className="flex items-center justify-end px-6 font-bold text-amber-500">{run.win_rate_pct}%</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
