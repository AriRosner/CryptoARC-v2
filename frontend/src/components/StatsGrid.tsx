import React from "react";
import { Activity, RefreshCw, TrendingUp, TrendingDown, Target, Zap } from "lucide-react";
import { Card } from "./Card";
import { AnimatedNumber } from "./AnimatedNumber";
import { Skeleton } from "./Skeleton";
import { cn } from "./utils";

interface StatsGridProps {
  stats: {
    total_trades: number;
    win_rate_pct: number;
    total_pnl_sol: number;
    open_positions: number;
  };
  pnlCurrency?: "SOL" | "USD";
  solUsdPrice?: number;
  onTogglePnlCurrency?: () => void;
  loading?: boolean;
}

export const StatsGrid: React.FC<StatsGridProps> = React.memo(({ stats, pnlCurrency = "SOL", solUsdPrice = 0, onTogglePnlCurrency, loading = false }) => {
  const showUsd = pnlCurrency === "USD" && solUsdPrice > 0;
  const items = React.useMemo(() => [
    {
      label: "Total P&L",
      value: showUsd ? stats.total_pnl_sol * solUsdPrice : stats.total_pnl_sol,
      precision: showUsd ? 2 : 4,
      prefix: showUsd ? "$" : "",
      suffix: showUsd ? "" : " SOL",
      icon: stats.total_pnl_sol >= 0 ? TrendingUp : TrendingDown,
      color: stats.total_pnl_sol >= 0 ? "text-emerald-500" : "text-rose-500",
      bg: stats.total_pnl_sol >= 0 ? "bg-emerald-500/10" : "bg-rose-500/10",
      canToggle: true
    },
    {
      label: "Win Rate",
      value: stats.win_rate_pct,
      precision: 1,
      prefix: "",
      suffix: "%",
      icon: Target,
      color: "text-amber-500",
      bg: "bg-amber-500/10",
      canToggle: false
    },
    {
      label: "Total Trades",
      value: stats.total_trades,
      precision: 0,
      prefix: "",
      suffix: "",
      icon: Activity,
      color: "text-blue-500",
      bg: "bg-blue-500/10",
      canToggle: false
    },
    {
      label: "Open Positions",
      value: stats.open_positions,
      precision: 0,
      prefix: "",
      suffix: "",
      icon: Zap,
      color: "text-purple-500",
      bg: "bg-purple-500/10",
      canToggle: false
    }
  ], [showUsd, stats.total_pnl_sol, solUsdPrice, stats.win_rate_pct, stats.total_trades, stats.open_positions]);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item, index) => (
        <Card key={item.label} className="p-6" hover={true} transition={{ delay: index * 0.1 }}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{item.label}</p>
              {loading ? (
                <div className="mt-2 space-y-2">
                  <Skeleton className="h-8 w-28 rounded-lg" />
                  <Skeleton className="h-3 w-20 rounded-full" />
                </div>
              ) : (
                <>
                  <div className="mt-2 flex items-baseline gap-1">
                    <AnimatedNumber
                      value={item.value}
                      precision={item.precision}
                      prefix={item.prefix}
                      suffix={item.suffix}
                      className={cn("text-2xl font-black tracking-tight", item.color)}
                    />
                  </div>
                  {item.canToggle ? <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-zinc-600">{showUsd ? "USD display" : "SOL display"}</p> : null}
                </>
              )}
            </div>
            {loading ? (
              <Skeleton className="h-12 w-12 rounded-2xl" />
            ) : item.canToggle && onTogglePnlCurrency ? (
              <button
                className={cn("flex h-12 w-12 items-center justify-center rounded-2xl transition hover:scale-105", item.bg)}
                onClick={onTogglePnlCurrency}
                title="Switch P&L currency"
                aria-label="Switch P&L currency"
              >
                <RefreshCw size={22} className={item.color} />
              </button>
            ) : (
              <div className={cn("flex h-12 w-12 items-center justify-center rounded-2xl", item.bg)}>
                <item.icon size={24} className={item.color} />
              </div>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
});
