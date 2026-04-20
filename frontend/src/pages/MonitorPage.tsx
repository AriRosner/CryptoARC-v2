import React from "react";
import { motion } from "framer-motion";
import { LayoutDashboard, TrendingUp } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { StatsGrid } from "../components/StatsGrid";
import { Card } from "../components/Card";
import { PnlChart } from "../components/PnlChart";
import { TokenTable } from "../components/TokenTable";
import { Badge } from "../components/Badge";

interface MonitorPageProps {
  stats: any;
  pnlHistory: number[];
  pnlValue: number;
  pnlCaption: string;
  liveWallets: string[];
  walletPublicKey: string;
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
  apiState: string;
}

export const MonitorPage: React.FC<MonitorPageProps> = ({
  stats,
  pnlHistory,
  pnlValue,
  pnlCaption,
  liveWallets,
  walletPublicKey,
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
  apiState
}) => {
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

      <StatsGrid stats={stats} />

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
          />
        </div>

        <div className="space-y-6">
          <Card className="p-6" hover={false}>
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h4 className="text-sm font-black uppercase tracking-widest text-zinc-500">P&L Performance</h4>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className={cn(
                    "text-2xl font-black tracking-tight",
                    pnlValue >= 0 ? "text-emerald-500" : "text-rose-500"
                  )}>
                    {pnlValue >= 0 ? "+" : ""}{pnlValue.toFixed(4)} SOL
                  </span>
                </div>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10">
                <TrendingUp size={20} className="text-emerald-500" />
              </div>
            </div>
            
            <PnlChart data={pnlHistory} height={160} />
            
            <div className="mt-6 flex items-center justify-between border-t border-white/5 pt-6">
              <label className="flex flex-col gap-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                Wallet Scope
                <select
                  value={pnlWallet}
                  onChange={(event) => setPnlWallet(event.target.value)}
                  className="min-w-44 rounded-lg border border-white/10 bg-black/50 px-2 py-1 text-xs font-bold normal-case tracking-normal text-white"
                >
                  <option value="paper">Paper wallet</option>
                  {liveWallets.map((wallet) => (
                    <option key={wallet} value={wallet}>Live {shortAddress(wallet)}</option>
                  ))}
                  {walletPublicKey && !liveWallets.includes(walletPublicKey) ? (
                    <option value={walletPublicKey}>Live {shortAddress(walletPublicKey)}</option>
                  ) : null}
                </select>
              </label>
            </div>
            <p className="mt-3 border-t border-white/5 pt-3 text-[10px] font-medium text-zinc-500">{pnlCaption}</p>
          </Card>

          <Card className="p-6" hover={false}>
            <h4 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500">Market Signal</h4>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-400">Network Readiness</span>
                <Badge variant={apiState === "connected" ? "success" : "danger"}>
                  {apiState === "connected" ? "Optimal" : "Degraded"}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-400">Launch Velocity</span>
                <span className="text-xs font-bold text-white">Normal</span>
              </div>
              <div className="flex items-center justify-between border-t border-white/5 pt-4">
                <span className="text-xs text-zinc-400">Active Signals</span>
                <span className="text-xs font-bold text-amber-500">{tokens.length}</span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};

import { cn } from "../components/utils";

function shortAddress(value: string): string {
  return value ? `${value.slice(0, 6)}...${value.slice(-4)}` : "not connected";
}
