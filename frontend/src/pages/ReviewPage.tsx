import React from "react";
import { 
  Target, 
  History, 
  Search, 
  Filter, 
  ArrowRight,
  ChevronRight,
  TrendingUp,
  Zap,
  Info
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Card } from "../components/Card";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { cn } from "../components/utils";
import type { TradeRecord, SettingsVersion, PerformanceAnalytics, TuningSuggestion, TradeLabel } from "../types";

interface ReviewPageProps {
  trades: TradeRecord[];
  versions: SettingsVersion[];
  analytics: PerformanceAnalytics | null;
  suggestions: TuningSuggestion[];
  selectedTradeId: string | null;
  timeline: any[];
  detail: any;
  labels: TradeLabel[];
  onLabelTrade: (tokenId: string, label: string) => Promise<void>;
  onSelectTrade: (tokenId: string) => void;
}

export const ReviewPage: React.FC<ReviewPageProps> = ({
  trades,
  versions,
  analytics,
  suggestions,
  selectedTradeId,
  timeline,
  detail,
  labels,
  onLabelTrade,
  onSelectTrade
}) => {
  const getLabel = (tokenId: string) => labels.find(l => l.token_id === tokenId)?.label;

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Trade Review" 
        description="Audit every paper execution and fine-tune your strategy."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Trade List */}
        <div className="lg:col-span-1 space-y-6">
          <Card className="flex flex-col h-[600px]" hover={false}>
            <div className="border-b border-white/5 p-4 flex items-center justify-between">
              <h3 className="text-xs font-black uppercase tracking-widest text-zinc-500">History</h3>
              <Badge variant="info">{trades.length}</Badge>
            </div>
            <div className="flex-1 overflow-auto scrollbar-thin scrollbar-thumb-white/10">
              <div className="divide-y divide-white/5">
                {trades.map((trade) => (
                  <button
                    key={trade.id}
                    onClick={() => onSelectTrade(trade.token_id)}
                    className={cn(
                      "w-full p-4 text-left transition-all hover:bg-white/[0.02]",
                      selectedTradeId === trade.token_id && "bg-amber-500/[0.05]"
                    )}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-black text-white">{trade.token_id.slice(0, 8)}...</span>
                      <span className={cn(
                        "text-[10px] font-black uppercase",
                        (trade.pnl_sol || 0) >= 0 ? "text-emerald-500" : "text-rose-500"
                      )}>
                        {(trade.pnl_sol || 0).toFixed(4)} SOL
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-zinc-500 font-bold uppercase">{trade.strategy_profile}</span>
                      <span className="text-zinc-600">{new Date(trade.opened_at || "").toLocaleTimeString()}</span>
                    </div>
                    {getLabel(trade.token_id) && (
                      <Badge variant="info" className="mt-2">{getLabel(trade.token_id)}</Badge>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </Card>
        </div>

        {/* Trade Detail / Timeline */}
        <div className="lg:col-span-2 space-y-6">
          {selectedTradeId ? (
            <>
              <Card className="p-6" hover={false}>
                 <div className="mb-6 flex items-center justify-between">
                  <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                    <Target size={16} />
                    Execution Audit
                  </h3>
                  <div className="flex gap-2">
                    {["good", "bad", "scam", "manual"].map(label => (
                      <button
                        key={label}
                        onClick={() => onLabelTrade(selectedTradeId, label)}
                        className={cn(
                          "rounded-lg px-2 py-1 text-[9px] font-black uppercase border transition-all",
                          getLabel(selectedTradeId) === label
                            ? "border-amber-500 bg-amber-500 text-[#160f08]"
                            : "border-white/10 text-zinc-500 hover:text-white"
                        )}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    <div className="rounded-xl bg-white/[0.02] p-3 border border-white/5">
                      <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">Entry</span>
                      <div className="text-xs font-black text-white">{detail?.entry_price?.toFixed(9) || "-"}</div>
                    </div>
                    <div className="rounded-xl bg-white/[0.02] p-3 border border-white/5">
                      <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">Exit</span>
                      <div className="text-xs font-black text-white">{detail?.exit_price?.toFixed(9) || "-"}</div>
                    </div>
                    <div className="rounded-xl bg-white/[0.02] p-3 border border-white/5">
                      <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">Size</span>
                      <div className="text-xs font-black text-white">{detail?.amount_sol?.toFixed(3) || "-"} SOL</div>
                    </div>
                    <div className="rounded-xl bg-white/[0.02] p-3 border border-white/5">
                      <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">Hold</span>
                      <div className="text-xs font-black text-white">{detail?.hold_duration_seconds || 0}s</div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-amber-500/10 bg-amber-500/[0.02] p-4">
                    <span className="text-[10px] font-black text-amber-500 uppercase tracking-widest">Strategy Verdict</span>
                    <p className="mt-1 text-xs text-zinc-300 italic leading-relaxed">
                      &ldquo;{detail?.exit_reason || detail?.entry_reason || "Decision details loading..."}&rdquo;
                    </p>
                  </div>
                </div>
              </Card>

              <Card className="flex flex-col h-[400px]" hover={false}>
                <div className="border-b border-white/5 p-4">
                  <h3 className="text-xs font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                    <History size={14} />
                    Signal Timeline
                  </h3>
                </div>
                <div className="flex-1 overflow-auto p-4 scrollbar-thin scrollbar-thumb-white/10">
                  <div className="relative space-y-6 before:absolute before:left-2 before:top-2 before:h-[calc(100%-16px)] before:w-px before:bg-white/5">
                    {timeline.map((event, i) => (
                      <div key={i} className="relative pl-8">
                        <div className="absolute left-0 top-1.5 h-4 w-4 rounded-full border border-white/10 bg-[#08090f] flex items-center justify-center">
                          <div className={cn(
                            "h-1.5 w-1.5 rounded-full",
                            event.type === "buy" ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" :
                            event.type === "sell" ? "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]" : "bg-zinc-500"
                          )} />
                        </div>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[10px] font-black text-white uppercase tracking-tight">{event.type}</span>
                          <span className="text-[9px] text-zinc-600 font-mono">{new Date(event.at).toLocaleString()}</span>
                        </div>
                        <p className="text-[11px] text-zinc-400 leading-relaxed">{event.message || event.reason}</p>
                        {event.price && (
                          <div className="mt-1 text-[9px] font-mono text-zinc-500">Price: {event.price.toFixed(9)}</div>
                        )}
                      </div>
                    ))}
                    {!timeline.length && (
                      <p className="text-center text-xs text-zinc-600 py-10">No timeline data for this trade.</p>
                    )}
                  </div>
                </div>
              </Card>
            </>
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-center p-12">
              <div className="mb-4 rounded-full bg-white/5 p-6 text-zinc-700">
                <Target size={48} />
              </div>
              <h3 className="text-lg font-bold text-zinc-500">Select a trade to audit</h3>
              <p className="text-sm text-zinc-600 max-w-xs mt-2">
                Detailed execution logs and strategy decisions will appear here for the selected position.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
