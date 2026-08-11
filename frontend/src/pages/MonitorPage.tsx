import React from "react";
import { Activity, RefreshCw, TrendingUp } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { StatsGrid } from "../components/StatsGrid";
import { Card } from "../components/Card";
import { PnlChart } from "../components/PnlChart";
import { TokenTable } from "../components/TokenTable";
import { Badge } from "../components/Badge";
import { Skeleton } from "../components/Skeleton";
import { cn } from "../components/utils";
import { fetchAutonomousPilotStatus } from "../api";
import type { AutonomousPilotStatus, LiveLedger } from "../types";

interface MonitorPageProps {
  stats: any;
  pnlHistory: number[];
  pnlValue: number;
  pnlCurrency: "SOL" | "USD";
  pnlCurrencyLabel: string;
  solUsdPrice: number;
  onTogglePnlCurrency: () => void;
  pnlCaption: string;
  liveLedger: LiveLedger | null;
  walletOptions: Array<{ value: string; label: string }>;
  timeframe: string;
  setTimeframe: (t: any) => void;
  pnlWallet: string;
  setPnlWallet: (w: any) => void;
  tokens: any[];
  onSelectToken: (id: string) => void;
  selectedTokenId: string | null;
  watchlist: Set<string>;
  onToggleWatch: (token: any) => void;
  search: string;
  setSearch: (s: string) => void;
  filter: string;
  setFilter: (f: any) => void;
  sort: string;
  setSort: (s: any) => void;
  hideSkipped: boolean;
  setHideSkipped: (value: boolean) => void;
  apiState: string;
  loading?: boolean;
  pnlLoading?: boolean;
  tokenLoading?: boolean;
}

export const MonitorPage: React.FC<MonitorPageProps> = React.memo(({
  stats,
  pnlHistory,
  pnlValue,
  pnlCurrency,
  pnlCurrencyLabel,
  solUsdPrice,
  onTogglePnlCurrency,
  pnlCaption,
  liveLedger,
  walletOptions,
  timeframe,
  setTimeframe,
  pnlWallet,
  setPnlWallet,
  tokens,
  onSelectToken,
  selectedTokenId,
  watchlist,
  onToggleWatch,
  search,
  setSearch,
  filter,
  setFilter,
  sort,
  setSort,
  hideSkipped,
  setHideSkipped,
  apiState,
  loading = false,
  pnlLoading = false,
  tokenLoading = false
}) => {
  const [pilotStatus, setPilotStatus] = React.useState<AutonomousPilotStatus | null>(null);
  const [pilotStatusError, setPilotStatusError] = React.useState("");

  React.useEffect(() => {
    let active = true;
    void fetchAutonomousPilotStatus()
      .then((status) => {
        if (active) setPilotStatus(status);
      })
      .catch((error: unknown) => {
        if (active) setPilotStatusError(error instanceof Error ? error.message : "Pilot status unavailable");
      });
    return () => { active = false; };
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Live Monitor"
        description="Real-time surveillance of PumpPortal token launches and paper trading performance."
      >
        <div className="flex items-center gap-2 rounded-xl bg-white/5 p-1">
          {["5m", "15m", "1h", "24h", "all"].map((t) => (
            <button
              key={t}
              onClick={() => setTimeframe(t)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-[10px] font-black uppercase tracking-widest transition-all",
                timeframe === t
                  ? "bg-amber-500 text-[#160f08] shadow-lg shadow-amber-500/20"
                  : "text-zinc-500 hover:text-white"
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </PageHeader>

      <StatsGrid stats={stats} pnlCurrency={pnlCurrency} solUsdPrice={solUsdPrice} onTogglePnlCurrency={onTogglePnlCurrency} loading={loading} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <TokenTable
            tokens={tokens}
            onSelectToken={onSelectToken}
            selectedTokenId={selectedTokenId}
            watchlist={watchlist}
            onToggleWatch={onToggleWatch}
            search={search}
            setSearch={setSearch}
            filter={filter}
            setFilter={setFilter}
            sort={sort}
            setSort={setSort}
            hideSkipped={hideSkipped}
            setHideSkipped={setHideSkipped}
            loading={tokenLoading}
          />
        </div>

        <div className="space-y-6">
          <Card className="p-6" hover={false}>
            <div className="flex items-center justify-between gap-3">
              <h4 className="text-sm font-black uppercase tracking-widest text-zinc-500">Attended Pilot Window</h4>
              <Badge variant={pilotStatus?.opened ? "success" : "warning"}>{pilotStatus?.status ?? "loading"}</Badge>
            </div>
            <p className="mt-3 text-xs text-zinc-400">{pilotStatus?.operator_action ?? "Reading the zero-authority pilot gate."}</p>
            <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/10 p-2 text-[11px] text-amber-100">
              {pilotStatus?.opened ? "Attended window open; monitor every stop condition." : "No autonomous entry authority is open. Guarded exits remain separately controlled."}
            </div>
            {pilotStatusError ? <p className="mt-2 text-xs text-rose-300">{pilotStatusError}</p> : null}
          </Card>

          <Card className="p-6" hover={false}>
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h4 className="text-sm font-black uppercase tracking-widest text-zinc-500">P&L Performance</h4>
                {pnlLoading ? (
                  <div className="mt-2 space-y-2">
                    <Skeleton className="h-8 w-36 rounded-lg" />
                    <Skeleton className="h-3 w-28 rounded-full" />
                  </div>
                ) : (
                  <>
                    <div className="mt-1 flex items-baseline gap-2">
                      <span className={cn(
                        "text-2xl font-black tracking-tight",
                        pnlValue >= 0 ? "text-emerald-500" : "text-rose-500"
                      )}>
                        {pnlValue >= 0 ? "+" : ""}{pnlCurrency === "USD" ? `$${pnlValue.toFixed(2)}` : `${pnlValue.toFixed(4)} SOL`}
                      </span>
                      <button
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-zinc-400 transition hover:border-amber-500/40 hover:text-amber-300"
                        onClick={onTogglePnlCurrency}
                        title="Switch P&L currency"
                        aria-label="Switch P&L currency"
                      >
                        <RefreshCw size={14} />
                      </button>
                    </div>
                    <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-zinc-600">{pnlCurrencyLabel}</p>
                  </>
                )}
              </div>
              {pnlLoading ? (
                <Skeleton className="h-10 w-10 rounded-xl" />
              ) : (
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10">
                  <TrendingUp size={20} className="text-emerald-500" />
                </div>
              )}
            </div>

            <PnlChart data={pnlHistory} height={160} unit={pnlCurrency} animationKey={`${timeframe}:${pnlWallet}:${pnlCurrency}`} loading={pnlLoading} />

            <div className="mt-6 flex items-center justify-between border-t border-white/5 pt-6">
              <label className="flex flex-col gap-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                Active Wallet
                {pnlLoading ? (
                  <Skeleton className="h-8 min-w-44 rounded-lg" />
                ) : (
                  <select
                    value={pnlWallet}
                    onChange={(event) => setPnlWallet(event.target.value)}
                    className="dashboard-select min-w-44 rounded-lg border border-white/10 bg-black/50 px-2 py-1 text-xs font-bold normal-case tracking-normal text-white"
                  >
                    {walletOptions.map((wallet) => (
                      <option key={wallet.value} value={wallet.value}>{wallet.label}</option>
                    ))}
                  </select>
                )}
              </label>
            </div>
            {pnlLoading ? (
              <div className="mt-3 border-t border-white/5 pt-3">
                <Skeleton className="h-3 w-52 rounded-full" />
              </div>
            ) : (
              <p className="mt-3 border-t border-white/5 pt-3 text-[10px] font-medium text-zinc-500">{pnlCaption}</p>
            )}
          </Card>

          {pnlWallet !== "paper" ? (
            <Card className="p-6" hover={false}>
              <h4 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500">Live Fill Audit</h4>
              <div className="max-h-72 space-y-2 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                {(liveLedger?.recent_fills ?? []).slice(0, 6).map((fill) => {
                  const solDelta = Number(fill.wallet_sol_delta_sol ?? 0);
                  const pnlDelta = Number(fill.realized_pnl_delta_sol ?? 0);
                  const feeSol = Number(fill.fee_sol ?? 0);
                  return (
                    <article key={`${fill.id}:${fill.signature}`} className="rounded-xl border border-white/5 bg-black/25 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <strong className="block truncate text-xs font-black uppercase tracking-[0.18em] text-white">{fill.action} / {fill.symbol || fill.mint.slice(0, 8)}</strong>
                          <span className="mt-1 block truncate text-[11px] text-zinc-500">{fill.signature || fill.reconciliation_status}</span>
                        </div>
                        <span className={cn("shrink-0 text-xs font-black", solDelta >= 0 ? "text-emerald-400" : "text-rose-400")}>{solDelta >= 0 ? "+" : ""}{solDelta.toFixed(6)} SOL</span>
                      </div>
                      <div className="mt-3 grid grid-cols-3 gap-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                        <span>Fee <strong className="block pt-1 text-xs normal-case tracking-normal text-orange-300">{feeSol.toFixed(6)}</strong></span>
                        <span>Priority <strong className="block pt-1 text-xs normal-case tracking-normal text-zinc-300">{Number(fill.priority_fee_sol ?? 0).toFixed(6)}</strong></span>
                        <span>Net PnL <strong className={cn("block pt-1 text-xs normal-case tracking-normal", pnlDelta >= 0 ? "text-emerald-400" : "text-rose-400")}>{pnlDelta >= 0 ? "+" : ""}{pnlDelta.toFixed(6)}</strong></span>
                      </div>
                      <p className="mt-2 text-[11px] text-zinc-500">Tokens {Number(fill.token_delta ?? 0).toFixed(4)} / {fill.provenance || "estimated"}</p>
                    </article>
                  );
                })}
                {!(liveLedger?.recent_fills ?? []).length ? <p className="rounded-xl border border-white/5 bg-black/25 p-3 text-xs text-zinc-500">No reconciled live fills for this wallet yet.</p> : null}
              </div>
            </Card>
          ) : null}

          <Card className="p-6" hover={false}>
            <h4 className="mb-4 flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
              <Activity size={16} className="text-amber-400" />
              Market Signal
            </h4>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-400">Network Readiness</span>
                {loading ? <Skeleton className="h-6 w-20 rounded-full" /> : (
                  <Badge variant={apiState === "connected" ? "success" : "danger"}>
                    {apiState === "connected" ? "Optimal" : "Degraded"}
                  </Badge>
                )}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-400">Launch Velocity</span>
                {loading ? <Skeleton className="h-3.5 w-16 rounded-full" /> : <span className="text-xs font-bold text-white">Normal</span>}
              </div>
              <div className="flex items-center justify-between border-t border-white/5 pt-4">
                <span className="text-xs text-zinc-400">Active Signals</span>
                {loading ? <Skeleton className="h-3.5 w-10 rounded-full" /> : <span className="text-xs font-bold text-amber-500">{tokens.length}</span>}
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
});

function shortAddress(value: string): string {
  return value ? `${value.slice(0, 6)}...${value.slice(-4)}` : "not connected";
}
