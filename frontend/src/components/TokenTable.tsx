import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Search, Filter, Eye, Pin } from "lucide-react";
import { Card } from "./Card";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { Skeleton } from "./Skeleton";
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
  hideSkipped: boolean;
  setHideSkipped: (value: boolean) => void;
  loading?: boolean;
}

const statusVariant = (status: TokenSignal["status"]): "success" | "danger" | "warning" | "info" | "neutral" => {
  if (status.includes("bought") || status === "buying") return "success";
  if (status === "paper_sold" || status === "selling") return "warning";
  if (status === "skipped") return "neutral";
  if (status === "detected" || status === "analyzing") return "info";
  return "neutral";
};

const tokenGridColumns = "minmax(220px,1.8fr) 96px 126px 116px 132px 118px 76px";
const TOKEN_ROW_HEIGHT = 62;
const TOKEN_OVERSCAN = 8;

function formatTokenAge(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.floor(seconds))}s`;
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const remain = Math.floor(seconds % 60);
    return remain ? `${minutes}m ${remain}s` : `${minutes}m`;
  }
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
  }
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return hours ? `${days}d ${hours}h` : `${days}d`;
}

interface TokenRowProps {
  token: TokenSignal;
  selected: boolean;
  watched: boolean;
  onSelectToken: (id: string) => void;
  onToggleWatch: (token: TokenSignal) => void;
  animateIn: boolean;
}

const TokenRow = React.memo(function TokenRow({
  token,
  selected,
  watched,
  onSelectToken,
  onToggleWatch,
  animateIn
}: TokenRowProps) {
  const pnl = token.pnl_sol || 0;
  const ageLabel = formatTokenAge(token.age_seconds || 0);

  return (
    <motion.div
      key={token.id}
      initial={animateIn ? { opacity: 0, y: 6 } : false}
      animate={{ opacity: 1, y: 0 }}
      exit={undefined}
      transition={{ duration: 0.16 }}
      onClick={() => onSelectToken(token.id)}
      style={{ gridTemplateColumns: tokenGridColumns }}
      className={cn(
        "group grid h-[62px] cursor-pointer items-center border-b border-white/5 transition-colors hover:bg-white/[0.03]",
        selected && "bg-amber-500/[0.06] hover:bg-amber-500/[0.09]"
      )}
    >
      <div className="min-w-0 px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-zinc-800 to-zinc-950 font-black text-amber-400 shadow-inner">
            {token.symbol.slice(0, 1)}
          </div>
          <div className="min-w-0">
            <div className="truncate font-bold text-white transition-colors group-hover:text-amber-400">{token.symbol}</div>
            <div className="truncate text-[10px] font-medium text-zinc-500">{token.name}</div>
          </div>
        </div>
      </div>
      <div className="px-3 py-2.5">
        <Button
          variant={watched ? "outline" : "ghost"}
          size="sm"
          className={cn(
            "h-7 w-[76px] gap-1 px-2 text-[10px]",
            watched && "border-amber-500/40 bg-amber-500/10 text-amber-400"
          )}
          onClick={(event) => {
            event.stopPropagation();
            onToggleWatch(token);
          }}
        >
          <Pin size={12} />
          {watched ? "Pinned" : "Pin"}
        </Button>
      </div>
      <div className="px-3 py-2.5">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-14 overflow-hidden rounded-full bg-white/5">
            <div
              style={{ width: `${Math.max(0, Math.min(100, token.score))}%` }}
              className={cn(
                "h-full rounded-full transition-[width] duration-300",
                token.score > 70 ? "bg-emerald-500" : token.score > 40 ? "bg-amber-500" : "bg-rose-500"
              )}
            />
          </div>
          <span className="w-7 text-xs font-bold text-zinc-300">{token.score}</span>
        </div>
      </div>
      <div className="px-3 py-2.5">
        <Badge variant={statusVariant(token.status)}>
          {token.status.replace("_", " ")}
        </Badge>
      </div>
      <div className="px-3 py-2.5">
        <span className="whitespace-nowrap text-xs font-bold text-zinc-400">{ageLabel}</span>
      </div>
      <div className="px-3 py-2.5">
        <span className={cn(
          "whitespace-nowrap text-xs font-black tracking-tight",
          pnl > 0 ? "text-emerald-500" : pnl < 0 ? "text-rose-500" : "text-zinc-500"
        )}>
          {pnl ? `${pnl > 0 ? "+" : ""}${pnl.toFixed(4)}` : "0.0000"}
        </span>
      </div>
      <div className="px-4 py-2.5 text-right">
        <Button variant="ghost" size="icon" className="h-8 w-8 opacity-70 transition-opacity group-hover:opacity-100">
          <Eye size={14} />
        </Button>
      </div>
    </motion.div>
  );
}, (prev, next) => (
  prev.selected === next.selected &&
  prev.watched === next.watched &&
  prev.token.id === next.token.id &&
  prev.token.mint === next.token.mint &&
  prev.token.symbol === next.token.symbol &&
  prev.token.name === next.token.name &&
  prev.token.score === next.token.score &&
  prev.token.status === next.token.status &&
  prev.token.age_seconds === next.token.age_seconds &&
  prev.token.pnl_sol === next.token.pnl_sol
));

export const TokenTable: React.FC<TokenTableProps> = React.memo(({
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
  loading = false
}) => {
  const scrollRef = React.useRef<HTMLDivElement | null>(null);
  const seenRowIdsRef = React.useRef<Set<string>>(new Set());
  const [scrollTop, setScrollTop] = React.useState(0);
  const [viewportHeight, setViewportHeight] = React.useState(520);
  const visibleRows = React.useMemo(() => tokens, [tokens]);
  const totalHeight = visibleRows.length * TOKEN_ROW_HEIGHT;
  const startIndex = Math.max(0, Math.floor(scrollTop / TOKEN_ROW_HEIGHT) - TOKEN_OVERSCAN);
  const visibleCount = Math.ceil(viewportHeight / TOKEN_ROW_HEIGHT) + TOKEN_OVERSCAN * 2;
  const endIndex = Math.min(visibleRows.length, startIndex + visibleCount);
  const virtualRows = React.useMemo(() => visibleRows.slice(startIndex, endIndex), [visibleRows, startIndex, endIndex]);
  const topSpacerHeight = startIndex * TOKEN_ROW_HEIGHT;
  const bottomSpacerHeight = Math.max(0, totalHeight - topSpacerHeight - virtualRows.length * TOKEN_ROW_HEIGHT);

  React.useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;

    const updateViewport = () => setViewportHeight(node.clientHeight);
    const handleScroll = () => setScrollTop(node.scrollTop);

    updateViewport();
    handleScroll();

    node.addEventListener("scroll", handleScroll, { passive: true });
    const resizeObserver = new ResizeObserver(updateViewport);
    resizeObserver.observe(node);

    return () => {
      node.removeEventListener("scroll", handleScroll);
      resizeObserver.disconnect();
    };
  }, []);

  return (
    <Card className="flex h-[clamp(520px,calc(100vh-270px),760px)] min-h-[520px] flex-col" hover={false}>
      <div className="grid min-h-12 grid-cols-[max-content_minmax(200px,1fr)_8.5rem_9rem_8rem] items-center gap-2 border-b border-white/5 px-3 py-2">
        <h3 className="flex shrink-0 items-center gap-2 text-xs font-black uppercase tracking-[0.2em] text-white">
          <Activity size={14} className="text-amber-400" />
          Token Monitor
          <Badge variant="info">{tokens.length}</Badge>
        </h3>

        <div className="relative min-w-0">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="Search tokens..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="dashboard-search-input h-9 w-full rounded-lg border border-white/10 bg-black/40 pr-3 text-xs font-semibold text-white placeholder-zinc-600 transition-all focus:border-amber-500/50 focus:outline-none focus:ring-4 focus:ring-amber-500/10"
          />
        </div>
          
        <select
          aria-label="Filter token status"
          value={filter}
          onChange={(e) => setFilter(e.target.value as any)}
          className="dashboard-select h-9 w-full rounded-lg border border-white/10 bg-black/40 pl-2.5 text-xs font-bold text-white focus:outline-none focus:ring-4 focus:ring-amber-500/10"
        >
          <option value="all">All Status</option>
          <option value="open">Open Positions</option>
          <option value="profitable">Profitable</option>
          <option value="losses">Losses</option>
        </select>

        <select
          aria-label="Sort token monitor"
          value={sort}
          onChange={(e) => setSort(e.target.value as any)}
          className="dashboard-select h-9 w-full rounded-lg border border-white/10 bg-black/40 pl-2.5 text-xs font-bold text-white focus:outline-none focus:ring-4 focus:ring-amber-500/10"
        >
          <option value="newest">Newest First</option>
          <option value="score">Highest Score</option>
          <option value="pnl">Highest P&L</option>
        </select>

        <label
          style={{ display: "flex", margin: 0, gap: "0.5rem" }}
          className="m-0 h-9 cursor-pointer items-center justify-center gap-2 rounded-lg border border-white/10 bg-black/40 px-2.5 text-[10px] font-black uppercase tracking-widest text-zinc-400 transition hover:border-amber-500/30 hover:text-white"
        >
          <input
            type="checkbox"
            checked={hideSkipped}
            onChange={(event) => setHideSkipped(event.target.checked)}
            className="h-4 w-4"
          />
          <span className="whitespace-nowrap leading-none">Hide Skips</span>
        </label>
      </div>

      <div ref={scrollRef} className="crypto-scrollbar flex-1 overflow-auto">
        <div className="min-w-[780px]">
          <div
            style={{ gridTemplateColumns: tokenGridColumns }}
            className="sticky top-0 z-20 grid h-9 items-center border-b border-white/5 bg-[#10121c]/95 text-[10px] font-black uppercase tracking-widest text-zinc-500 backdrop-blur-md"
          >
            <div className="px-4">Token / Symbol</div>
            <div className="px-3">Watch</div>
            <div className="px-3">Score</div>
            <div className="px-3">Status</div>
            <div className="px-3">Age</div>
            <div className="px-3">P&L (SOL)</div>
            <div className="px-4 text-right">Action</div>
          </div>
          <div>
            {loading ? (
              <div className="space-y-0">
                {Array.from({ length: 8 }).map((_, index) => (
                  <div
                    key={index}
                    style={{ gridTemplateColumns: tokenGridColumns }}
                    className="grid h-[62px] items-center border-b border-white/5 px-0"
                  >
                    <div className="px-4 py-2.5">
                      <div className="flex items-center gap-3">
                        <Skeleton className="h-8 w-8 rounded-lg" />
                        <div className="min-w-0 flex-1 space-y-2">
                          <Skeleton className="h-3.5 w-24 rounded-full" />
                          <Skeleton className="h-2.5 w-32 rounded-full" />
                        </div>
                      </div>
                    </div>
                    <div className="px-3 py-2.5"><Skeleton className="h-7 w-[76px] rounded-lg" /></div>
                    <div className="px-3 py-2.5"><Skeleton className="h-3.5 w-20 rounded-full" /></div>
                    <div className="px-3 py-2.5"><Skeleton className="h-6 w-20 rounded-full" /></div>
                    <div className="px-3 py-2.5"><Skeleton className="h-3.5 w-14 rounded-full" /></div>
                    <div className="px-3 py-2.5"><Skeleton className="h-3.5 w-16 rounded-full" /></div>
                    <div className="px-4 py-2.5 text-right"><Skeleton className="ml-auto h-8 w-8 rounded-lg" /></div>
                  </div>
                ))}
              </div>
            ) : (
              <>
                <div style={{ height: topSpacerHeight }} />
                <AnimatePresence initial={false}>
                  {virtualRows.map((token) => {
                    const animateIn = !seenRowIdsRef.current.has(token.id);
                    seenRowIdsRef.current.add(token.id);
                    return (
                      <TokenRow
                        key={token.id}
                        token={token}
                        selected={selectedTokenId === token.id}
                        watched={watchlist.has(token.mint)}
                        onSelectToken={onSelectToken}
                        onToggleWatch={onToggleWatch}
                        animateIn={animateIn}
                      />
                    );
                  })}
                </AnimatePresence>
                <div style={{ height: bottomSpacerHeight }} />
              </>
            )}
          </div>
        </div>
        
        {!loading && tokens.length === 0 && (
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
});

TokenTable.displayName = "TokenTable";
