import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Filter, Eye, Pin } from "lucide-react";
import { Card } from "./Card";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { cn } from "./utils";
import type { TokenSignal } from "../types";

interface TokenTableProps {
  tokens: TokenSignal[];
  onSelectToken: (id: string) => void;
  selectedTokenId: string | null;
  watchlist: Set<string>;
  onToggleWatch: (token: TokenSignal) => void;
  search: string;
  setSearch: (s: string) => void;
  filter: string;
  setFilter: (f: any) => void;
  sort: string;
  setSort: (s: any) => void;
}

const statusVariant = (status: TokenSignal["status"]): "success" | "danger" | "warning" | "info" | "neutral" => {
  if (status.includes("bought") || status === "buying") return "success";
  if (status === "paper_sold" || status === "selling") return "warning";
  if (status === "skipped") return "neutral";
  if (status === "detected" || status === "analyzing") return "info";
  return "neutral";
};

export const TokenTable: React.FC<TokenTableProps> = ({
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
  setSort
}) => {
  return (
    <Card className="flex h-full flex-col" hover={false}>
      <div className="border-b border-white/5 p-4 lg:flex lg:items-center lg:justify-between lg:gap-4">
        <h3 className="text-lg font-bold text-white mb-4 lg:mb-0 flex items-center gap-2">
          Token Monitor
          <Badge variant="info" className="ml-2">{tokens.length}</Badge>
        </h3>
        
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              placeholder="Search tokens..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-10 w-full rounded-xl border border-white/10 bg-black/40 pl-10 pr-4 text-sm text-white placeholder-zinc-500 transition-all focus:border-amber-500/50 focus:outline-none focus:ring-4 focus:ring-amber-500/10"
            />
          </div>
          
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as any)}
            className="h-10 rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-white focus:outline-none focus:ring-4 focus:ring-amber-500/10"
          >
            <option value="all">All Status</option>
            <option value="open">Open Positions</option>
            <option value="profitable">Profitable</option>
            <option value="losses">Losses</option>
          </select>

          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as any)}
            className="h-10 rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-white focus:outline-none focus:ring-4 focus:ring-amber-500/10"
          >
            <option value="newest">Newest First</option>
            <option value="score">Highest Score</option>
            <option value="pnl">Highest P&L</option>
          </select>
        </div>
      </div>

      <div className="flex-1 overflow-auto scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
        <table className="w-full border-collapse text-left">
          <thead className="sticky top-0 z-10 bg-[#10121c] after:absolute after:bottom-0 after:left-0 after:h-px after:w-full after:bg-white/5">
            <tr>
              <th className="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-zinc-500">Token / Symbol</th>
              <th className="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-zinc-500">Watch</th>
              <th className="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-zinc-500">Score</th>
              <th className="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-zinc-500">Status</th>
              <th className="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-zinc-500">P&L (SOL)</th>
              <th className="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-zinc-500 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            <AnimatePresence mode="popLayout">
              {tokens.map((token, index) => (
                <motion.tr
                  key={token.id}
                  layout
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.2, delay: Math.min(index * 0.05, 0.5) }}
                  onClick={() => onSelectToken(token.id)}
                  className={cn(
                    "group cursor-pointer transition-colors hover:bg-white/[0.02]",
                    selectedTokenId === token.id && "bg-amber-500/[0.05] hover:bg-amber-500/[0.08]"
                  )}
                >
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-zinc-800 to-zinc-900 font-black text-amber-500 shadow-inner">
                        {token.symbol.slice(0, 1)}
                      </div>
                      <div>
                        <div className="font-bold text-white group-hover:text-amber-500 transition-colors">{token.symbol}</div>
                        <div className="text-[10px] font-medium text-zinc-500">{token.name}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <Button
                      variant={watchlist.has(token.mint) ? "outline" : "ghost"}
                      size="sm"
                      className={cn(
                        "h-8 gap-1 text-[10px]",
                        watchlist.has(token.mint) && "border-amber-500/40 bg-amber-500/10 text-amber-500"
                      )}
                      onClick={(event) => {
                        event.stopPropagation();
                        onToggleWatch(token);
                      }}
                    >
                      <Pin size={12} />
                      {watchlist.has(token.mint) ? "Pinned" : "Pin"}
                    </Button>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-12 rounded-full bg-white/5 overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${token.score}%` }}
                          className={cn(
                            "h-full rounded-full",
                            token.score > 70 ? "bg-emerald-500" : token.score > 40 ? "bg-amber-500" : "bg-rose-500"
                          )}
                        />
                      </div>
                      <span className="text-xs font-bold text-zinc-300">{token.score}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <Badge variant={statusVariant(token.status)}>
                      {token.status.replace("_", " ")}
                    </Badge>
                  </td>
                  <td className="px-6 py-4">
                    <span className={cn(
                      "text-xs font-black tracking-tight",
                      (token.pnl_sol || 0) > 0 ? "text-emerald-500" : (token.pnl_sol || 0) < 0 ? "text-rose-500" : "text-zinc-500"
                    )}>
                      {token.pnl_sol ? (token.pnl_sol > 0 ? "+" : "") + token.pnl_sol.toFixed(4) : "0.0000"}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <Button variant="ghost" size="icon" className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Eye size={14} />
                    </Button>
                  </td>
                </motion.tr>
              ))}
            </AnimatePresence>
          </tbody>
        </table>
        
        {tokens.length === 0 && (
          <div className="flex h-64 flex-col items-center justify-center text-center">
            <div className="mb-4 rounded-full bg-white/5 p-4 text-zinc-600">
              <Filter size={32} />
            </div>
            <h4 className="text-sm font-bold text-zinc-400">No tokens found</h4>
            <p className="text-xs text-zinc-600 mt-1">Try adjusting your search or filters</p>
          </div>
        )}
      </div>
    </Card>
  );
};
