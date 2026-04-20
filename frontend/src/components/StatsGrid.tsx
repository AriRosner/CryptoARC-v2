import React from "react";
import { TrendingUp, TrendingDown, Target, Zap } from "lucide-react";
import { Card } from "./Card";
import { AnimatedNumber } from "./AnimatedNumber";
import { cn } from "./utils";

interface StatsGridProps {
  stats: {
    total_trades: number;
    win_rate_pct: number;
    total_pnl_sol: number;
    open_positions: number;
  };
}

export const StatsGrid: React.FC<StatsGridProps> = ({ stats }) => {
  const items = [
    {
      label: "Total P&L",
      value: stats.total_pnl_sol,
      precision: 4,
      suffix: " SOL",
      icon: stats.total_pnl_sol >= 0 ? TrendingUp : TrendingDown,
      color: stats.total_pnl_sol >= 0 ? "text-emerald-500" : "text-rose-500",
      bg: stats.total_pnl_sol >= 0 ? "bg-emerald-500/10" : "bg-rose-500/10"
    },
    {
      label: "Win Rate",
      value: stats.win_rate_pct,
      precision: 1,
      suffix: "%",
      icon: Target,
      color: "text-amber-500",
      bg: "bg-amber-500/10"
    },
    {
      label: "Total Trades",
      value: stats.total_trades,
      precision: 0,
      icon: Activity,
      color: "text-blue-500",
      bg: "bg-blue-500/10"
    },
    {
      label: "Open Positions",
      value: stats.open_positions,
      precision: 0,
      icon: Zap,
      color: "text-purple-500",
      bg: "bg-purple-500/10"
    }
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item, index) => (
        <Card key={item.label} className="p-6" hover={true} transition={{ delay: index * 0.1 }}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{item.label}</p>
              <div className="mt-2 flex items-baseline gap-1">
                <AnimatedNumber
                  value={item.value}
                  precision={item.precision}
                  suffix={item.suffix}
                  className={cn("text-2xl font-black tracking-tight", item.color)}
                />
              </div>
            </div>
            <div className={cn("flex h-12 w-12 items-center justify-center rounded-2xl", item.bg)}>
              <item.icon size={24} className={item.color} />
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
};

import { Activity } from "lucide-react";
