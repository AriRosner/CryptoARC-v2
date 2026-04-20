import React from "react";
import { X, ExternalLink, ShieldAlert, Zap, BarChart, Info } from "lucide-react";
import { Modal } from "./Modal";
import { Card } from "./Card";
import { Badge } from "./Badge";
import { Button } from "./Button";
import type { TokenSignal } from "../types";

interface TokenDetailProps {
  token: TokenSignal | null;
  isOpen: boolean;
  onClose: () => void;
}

const Metric: React.FC<{ label: string; value: string | number; icon?: any; color?: string }> = ({ 
  label, value, icon: Icon, color = "text-white" 
}) => (
  <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
    <div className="flex items-center gap-2 mb-1">
      {Icon && <Icon size={12} className="text-zinc-500" />}
      <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</span>
    </div>
    <div className={`text-lg font-black tracking-tight ${color}`}>{value}</div>
  </div>
);

const DetailRow: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="grid grid-cols-[140px_1fr] gap-3 border-b border-white/5 py-2 text-xs last:border-b-0">
    <span className="font-black uppercase tracking-widest text-zinc-600">{label}</span>
    <span className="min-w-0 break-words font-mono text-zinc-300">{value || "-"}</span>
  </div>
);

export const TokenDetail: React.FC<TokenDetailProps> = ({ token, isOpen, onClose }) => {
  if (!token) return null;

  const isProfit = (token.pnl_sol || 0) > 0;
  const isLoss = (token.pnl_sol || 0) < 0;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`${token.symbol} Analysis`}
      description={token.name}
      className="max-w-3xl"
    >
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Metric 
            label="Current P&L" 
            value={`${token.pnl_sol?.toFixed(4) ?? "0.0000"} SOL`} 
            color={isProfit ? "text-emerald-500" : isLoss ? "text-rose-500" : "text-white"}
          />
          <Metric label="Score" value={token.score} color="text-amber-500" />
          <Metric label="Success Est." value={`${token.success_rate_pct}%`} />
          <Metric label="Hold Time" value={`${token.hold_duration_seconds}s`} />
          <Metric label="Slippage" value={`${(token.slippage_paid_pct || 0).toFixed(2)}%`} />
          <Metric label="Fees" value={`${(token.fee_paid_sol || 0).toFixed(6)} SOL`} />
          <Metric label="Impact" value={`${(token.price_impact_pct || 0).toFixed(2)}%`} />
          <Metric label="Ticks Held" value={token.ticks_held} />
        </div>

        <section className="space-y-3">
          <h4 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
            <ShieldAlert size={14} />
            Risk Assessment
          </h4>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center justify-between rounded-xl bg-white/5 p-4">
              <span className="text-xs text-zinc-400">Honeypot Risk</span>
              <Badge variant={token.honeypot_risk ? "danger" : "success"}>
                {token.honeypot_risk ? "High" : "None"}
              </Badge>
            </div>
            <div className="flex items-center justify-between rounded-xl bg-white/5 p-4">
              <span className="text-xs text-zinc-400">Rug Risk</span>
              <Badge variant={token.rug_risk ? "danger" : "success"}>
                {token.rug_risk ? "High" : "None"}
              </Badge>
            </div>
            <div className="flex items-center justify-between rounded-xl bg-white/5 p-4 text-xs">
              <span className="text-zinc-400">Creator Hold</span>
              <span className="font-bold text-white">{(token.creator_hold_pct ?? 0).toFixed(1)}%</span>
            </div>
            <div className="flex items-center justify-between rounded-xl bg-white/5 p-4 text-xs">
              <span className="text-zinc-400">Metadata Score</span>
              <span className="font-bold text-white">{token.metadata_score.toFixed(2)}</span>
            </div>
          </div>
        </section>

        <section className="space-y-3">
          <h4 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
            <Info size={14} />
            Network Forensics
          </h4>
          <div className="rounded-xl border border-white/5 bg-black/40 p-4">
            <DetailRow label="Mint" value={token.mint} />
            <DetailRow label="Creator" value={token.creator} />
            <DetailRow label="Bonding Curve" value={token.bonding_curve || "-"} />
            <DetailRow label="Metadata URI" value={token.metadata_uri || "-"} />
            <DetailRow label="Buy Velocity" value={token.buy_velocity.toFixed(2)} />
            <DetailRow label="Sell Pressure" value={token.sell_pressure.toFixed(2)} />
            <DetailRow label="Initial Buy" value={`${(token.initial_buy_sol || 0).toFixed(4)} SOL`} />
            <DetailRow label="Market Cap" value={`${(token.market_cap_sol || 0).toFixed(2)} SOL`} />
            <DetailRow label="Observed Ticks" value={token.observed_price_updates || 0} />
            <DetailRow label="Price Source" value={`${token.price_source || "-"} / confidence ${(token.price_confidence || 0).toFixed(2)}`} />
            <DetailRow label="Last Trade Tick" value={token.last_observed_trade_at ? new Date(token.last_observed_trade_at).toLocaleString() : "no trade ticks"} />
            {token.price_reject_reason ? <DetailRow label="Price Reject" value={token.price_reject_reason} /> : null}
          </div>
        </section>

        <section className="space-y-3">
          <h4 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
            <Info size={14} />
            Decision Explorer
          </h4>
          <div className="grid gap-2">
            {[
              ["Source", token.mint ? "normalized launch event" : "missing source detail"],
              ["Intelligence", (token.intelligence_tags ?? []).join(", ") || "neutral"],
              ["Score", `${token.score} / ${token.success_rate_pct}% success estimate`],
              ["Risk", token.entry_risk_filters?.join(", ") || token.reason],
              ["Execution", token.fill_failed ? "fill failed" : `${token.status} / impact ${(token.price_impact_pct || 0).toFixed(2)}% / fees ${(token.fee_paid_sol || 0).toFixed(6)} SOL`],
              ["Exit", token.exit_reason || "open or skipped"]
            ].map(([label, value], index) => (
              <div key={label} className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
                <span className="text-[10px] font-black uppercase tracking-widest text-zinc-600">{index + 1}. {label}</span>
                <p className="mt-1 text-xs font-bold text-zinc-300">{value}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-3">
          <h4 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
            <Info size={14} />
            Decision Log
          </h4>
          <div className="rounded-xl border border-white/5 bg-black/40 p-4">
            {(token.decision_log ?? []).length ? (
              <ol className="space-y-2">
                {(token.decision_log ?? []).map((item, index) => (
                  <li key={`${item}-${index}`} className="text-xs text-zinc-400">{index + 1}. {item}</li>
                ))}
              </ol>
            ) : (
              <p className="text-xs text-zinc-500">No decision log recorded.</p>
            )}
          </div>
        </section>

        <section className="space-y-3">
          <h4 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
            <Zap size={14} />
            Decision Intelligence
          </h4>
          <Card className="p-4 bg-amber-500/[0.02] border-amber-500/10" hover={false}>
            <p className="text-sm leading-relaxed text-zinc-300 italic">
              &ldquo;{token.entry_reason || token.reason}&rdquo;
            </p>
            {token.exit_reason && (
              <div className="mt-4 border-t border-white/5 pt-4">
                <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Exit Execution</span>
                <p className="mt-1 text-sm text-zinc-400">{token.exit_reason}</p>
              </div>
            )}
          </Card>
        </section>

        <section className="space-y-3">
          <h4 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
            <BarChart size={14} />
            Score Breakdown
          </h4>
          <div className="rounded-xl border border-white/5 bg-black/40 p-4">
            <ul className="space-y-2">
              {token.score_breakdown.map((item, i) => (
                <li key={i} className="flex items-center gap-3 text-xs text-zinc-400">
                  <div className="h-1 w-1 rounded-full bg-amber-500" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <div className="sticky bottom-[-1.5rem] z-20 -mx-6 -mb-6 grid grid-cols-2 gap-4 border-t border-white/10 bg-[#10121c]/95 p-4 backdrop-blur-xl">
          <Button 
            variant="secondary" 
            className="w-full"
            onClick={() => window.open(`https://pump.fun/coin/${token.mint}`, "_blank")}
          >
            <ExternalLink size={14} className="mr-2" />
            View on Pump.fun
          </Button>
          <Button 
            variant="secondary" 
            className="w-full"
            onClick={() => window.open(`https://solscan.io/account/${token.creator}`, "_blank")}
          >
            <ExternalLink size={14} className="mr-2" />
            View Creator on Solscan
          </Button>
        </div>
      </div>
    </Modal>
  );
};
