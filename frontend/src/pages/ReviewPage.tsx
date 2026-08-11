import React from "react";
import {
  Activity,
  Clock,
  Search,
  Shield,
  Sparkles,
  Target,
  TrendingUp
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Card } from "../components/Card";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Skeleton } from "../components/Skeleton";
import { cn } from "../components/utils";
import { fetchTradeGrades } from "../api";
import type { PerformanceAnalytics, SettingsVersion, TokenSignal, TradeGrade, TradeLabel, TradeRecord, TradeReviewDetail, TradeReviewQueue, TuningSuggestion } from "../types";

interface ReviewPageProps {
  trades: TradeRecord[];
  versions: SettingsVersion[];
  tokens: TokenSignal[];
  analytics: PerformanceAnalytics | null;
  suggestions: TuningSuggestion[];
  selectedTradeId: string | null;
  timeline: Array<{ at: string; type: string; title: string; detail: string }>;
  detail: TradeReviewDetail | null;
  labels: TradeLabel[];
  reviewQueue: TradeReviewQueue | null;
  loading: boolean;
  onLabelTrade: (tokenId: string, label: string) => Promise<void>;
  onSelectTrade: (tokenId: string) => void;
  onApplySuggestion: (suggestion: TuningSuggestion) => Promise<void>;
}

const reviewLabels = [
  "good_entry",
  "bad_entry",
  "bad_exit",
  "bad_price_data",
  "rug_behavior",
  "exited_too_early",
  "held_too_long",
  "ignore_from_tuning"
] as const;

const ReviewMetric: React.FC<{ label: string; value: string; tone?: "neutral" | "good" | "bad" | "warn" }> = ({ label, value, tone = "neutral" }) => (
  <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
    <div className="text-[9px] font-black uppercase tracking-widest text-zinc-500">{label}</div>
    <div
      className={cn(
        "mt-1 text-sm font-black",
        tone === "good" && "text-emerald-400",
        tone === "bad" && "text-rose-400",
        tone === "warn" && "text-amber-300",
        tone === "neutral" && "text-white"
      )}
    >
      {value}
    </div>
  </div>
);

const ReviewQueueSkeleton: React.FC = () => (
  <Card className="p-4" hover={false}>
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div className="space-y-2">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-3 w-80 max-w-full" />
      </div>
      <Skeleton className="h-7 w-24 rounded-lg" />
    </div>
    <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-6">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="rounded-xl border border-white/5 bg-white/[0.015] p-3">
          <div className="flex items-center justify-between gap-2">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-4 w-8" />
          </div>
          <Skeleton className="mt-3 h-8 w-full" />
        </div>
      ))}
    </div>
  </Card>
);

const ReviewTradeListSkeleton: React.FC = () => (
  <div className="divide-y divide-white/5">
    {Array.from({ length: 9 }).map((_, index) => (
      <div key={index} className="px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-3 w-44" />
          </div>
          <Skeleton className="h-4 w-20" />
        </div>
        <div className="mt-3 flex items-center justify-between gap-3">
          <Skeleton className="h-3 w-36" />
          <Skeleton className="h-3 w-12" />
        </div>
      </div>
    ))}
  </div>
);

const ReviewDetailSkeleton: React.FC = () => (
  <div className="space-y-6">
    <Card className="p-6" hover={false}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-3">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-7 w-56" />
          <Skeleton className="h-3 w-72 max-w-full" />
        </div>
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} className="h-7 w-24 rounded-lg" />)}
        </div>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-5">
        {Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} className="h-16 rounded-xl" />)}
      </div>
      <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Skeleton className="h-40 rounded-xl" />
        <Skeleton className="h-40 rounded-xl" />
      </div>
      <Skeleton className="mt-5 h-24 rounded-xl" />
    </Card>
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.35fr)_360px]">
      <Skeleton className="h-[640px] rounded-xl" />
      <div className="space-y-6">
        <Skeleton className="h-56 rounded-xl" />
        <Skeleton className="h-56 rounded-xl" />
        <Skeleton className="h-56 rounded-xl" />
      </div>
    </div>
  </div>
);

function formatNumber(value: number | null | undefined, digits = 4): string {
  return typeof value === "number" ? value.toFixed(digits) : "-";
}

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return "0s";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remain = seconds % 60;
  return remain ? `${minutes}m ${remain}s` : `${minutes}m`;
}

export const ReviewPage: React.FC<ReviewPageProps> = ({
  trades,
  versions,
  tokens,
  analytics,
  suggestions,
  selectedTradeId,
  timeline,
  detail,
  labels,
  reviewQueue,
  loading,
  onLabelTrade,
  onSelectTrade,
  onApplySuggestion
}) => {
  const [search, setSearch] = React.useState("");
  const [activeQueueId, setActiveQueueId] = React.useState("unlabeled");
  const [selectedGrade, setSelectedGrade] = React.useState<TradeGrade | null>(null);
  const tokenById = React.useMemo(() => new Map(tokens.map((token) => [token.id, token])), [tokens]);
  const labelByTokenId = React.useMemo(() => new Map(labels.map((label) => [label.token_id, label.label])), [labels]);
  const selectedTrade = detail?.trade ?? trades.find((trade) => trade.token_id === selectedTradeId) ?? null;
  const selectedToken = detail?.token ?? null;
  const selectedTimeline = detail?.timeline?.length ? detail.timeline : timeline;
  const selectedDecision = detail?.decisions?.[0] ?? null;
  const selectedSettingsVersion = versions.find((version) => version.id === selectedTrade?.settings_version_id);
  const workflow = detail?.review_workflow;
  const selectedLabel = workflow?.selected_label || (selectedTradeId ? labelByTokenId.get(selectedTradeId) : undefined);
  const query = search.trim().toLowerCase();
  const tradeMatchesQueue = React.useCallback((trade: TradeRecord) => {
    const label = labelByTokenId.get(trade.token_id);
    if (activeQueueId === "unlabeled") return !label;
    if (activeQueueId === "losses") return (trade.pnl_sol ?? 0) < 0;
    if (activeQueueId === "long_holds") return (trade.hold_duration_seconds ?? 0) >= 180;
    if (activeQueueId === "missing_decision") return false;
    if (activeQueueId === "bad_price_data") return label === "bad_price_data";
    if (activeQueueId === "ignored_from_tuning") return label === "ignore_from_tuning";
    return true;
  }, [activeQueueId, labelByTokenId]);
  const filteredTrades = trades.filter((trade) => {
    const token = tokenById.get(trade.token_id);
    if (!tradeMatchesQueue(trade)) return false;
    if (!query) return true;
    const haystack = [
      trade.token_id,
      token?.symbol,
      token?.name,
      token?.mint,
      trade.strategy_profile,
      trade.entry_reason,
      trade.exit_reason,
      trade.lifecycle_status
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
  const acceptedObservations = detail?.observations?.filter((observation) => observation.accepted) ?? [];
  const rejectedObservations = detail?.observations?.filter((observation) => !observation.accepted) ?? [];
  const activeQueue = reviewQueue?.queues.find((queue) => queue.id === activeQueueId);

  React.useEffect(() => {
    let active = true;
    setSelectedGrade(null);
    if (selectedTrade?.id) {
      fetchTradeGrades(selectedTrade.id)
        .then((grades) => { if (active) setSelectedGrade(grades[0] ?? null); })
        .catch(() => { if (active) setSelectedGrade(null); });
    }
    return () => { active = false; };
  }, [selectedTrade?.id]);

  React.useEffect(() => {
    if (!reviewQueue?.queues.some((queue) => queue.id === activeQueueId)) {
      setActiveQueueId(reviewQueue?.next_queue_id || "unlabeled");
    }
  }, [activeQueueId, reviewQueue]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Trade Review"
        description="Inspect paper executions, decision evidence, and tuning opportunities trade by trade."
      />

      {loading && !reviewQueue ? (
        <ReviewQueueSkeleton />
      ) : reviewQueue ? (
        <Card className="p-4" hover={false}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-xs font-black uppercase tracking-widest text-zinc-500">Review Queues</h3>
              <p className="mt-1 text-xs text-zinc-500">{reviewQueue.operator_action}</p>
            </div>
            <Badge variant={reviewQueue.unlabeled ? "warning" : "success"}>
              {reviewQueue.labeled}/{reviewQueue.total_closed} labeled
            </Badge>
            {reviewQueue.next_token_id ? (
              <Button variant="secondary" size="sm" onClick={() => onSelectTrade(reviewQueue.next_token_id)}>
                Next Review
              </Button>
            ) : null}
          </div>
          <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-6">
            {reviewQueue.queues.map((queue) => (
              <button
                key={queue.id}
                className={cn(
                  "rounded-xl border p-3 text-left transition hover:bg-white/[0.04]",
                  queue.count ? "border-white/10 bg-white/[0.03]" : "border-white/5 bg-white/[0.015] opacity-70",
                  activeQueueId === queue.id && "border-amber-400/40 bg-amber-500/10"
                )}
                onClick={() => {
                  setActiveQueueId(queue.id);
                  if (queue.sample_token_ids[0]) onSelectTrade(queue.sample_token_ids[0]);
                }}
                disabled={!queue.count}
                title={queue.reason}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[10px] font-black uppercase tracking-widest text-zinc-500">{queue.label}</span>
                  <span className={cn("text-sm font-black", queue.count ? "text-white" : "text-zinc-600")}>{queue.count}</span>
                </div>
                <p className="mt-2 line-clamp-2 min-h-8 text-[10px] leading-4 text-zinc-500">{queue.reason}</p>
              </button>
            ))}
          </div>
        </Card>
      ) : null}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <div className="space-y-6">
          <Card className="flex h-[760px] flex-col" hover={false}>
            <div className="border-b border-white/5 p-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-xs font-black uppercase tracking-widest text-zinc-500">{activeQueue?.label ?? "Closed Trades"}</h3>
                <Badge variant="info">{filteredTrades.length}</Badge>
              </div>
              {activeQueue ? <p className="mt-1 line-clamp-2 text-[11px] text-zinc-500">{activeQueue.reason}</p> : null}
              <div className="relative mt-3">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex w-11 items-center justify-center text-zinc-600">
                  <Search className="h-4 w-4" />
                </div>
                <input
                  aria-label="Search closed trades"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search token, profile, reason…"
                  className="text-xs text-white placeholder:text-zinc-600"
                  style={{
                    height: "40px",
                    paddingLeft: "44px",
                    paddingRight: "12px",
                    lineHeight: "40px"
                  }}
                />
              </div>
            </div>
            <div className="crypto-scrollbar flex-1 overflow-auto">
              {loading && !trades.length ? (
                <ReviewTradeListSkeleton />
              ) : (
              <div className="divide-y divide-white/5">
                {filteredTrades.map((trade) => {
                  const token = tokenById.get(trade.token_id);
                  const tradeLabel = labels.find((item) => item.token_id === trade.token_id)?.label;
                  const pnl = trade.pnl_sol ?? 0;
                  return (
                    <button
                      key={trade.id}
                      onClick={() => onSelectTrade(trade.token_id)}
                      className={cn(
                        "w-full px-4 py-3 text-left transition-colors hover:bg-white/[0.03]",
                        selectedTradeId === trade.token_id && "bg-amber-500/[0.08]"
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-black text-white">
                            {token?.symbol || token?.name || trade.token_id}
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                            <span className="normal-case tracking-normal text-zinc-400">{token?.mint ? `${token.mint.slice(0, 6)}...${token.mint.slice(-4)}` : trade.token_id}</span>
                            <span>{trade.strategy_profile}</span>
                            <span>{trade.lifecycle_status}</span>
                            {tradeLabel ? <Badge variant="info">{tradeLabel.replace(/_/g, " ")}</Badge> : null}
                          </div>
                        </div>
                        <div className={cn("shrink-0 text-xs font-black", pnl >= 0 ? "text-emerald-400" : "text-rose-400")}>
                          {pnl >= 0 ? "+" : ""}
                          {pnl.toFixed(4)} SOL
                        </div>
                      </div>
                      <div className="mt-2 flex items-center justify-between text-[10px] text-zinc-600">
                        <span>{trade.opened_at ? new Date(trade.opened_at).toLocaleString() : "No entry time"}</span>
                        <span>{formatDuration(trade.hold_duration_seconds)}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
              )}
              {!loading && !filteredTrades.length ? <div className="p-6 text-center text-xs text-zinc-500">No trades match that filter.</div> : null}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          {loading && !selectedTrade ? (
            <ReviewDetailSkeleton />
          ) : selectedTrade ? (
            <>
              <Card className="p-6" hover={false}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500">Execution Audit</h3>
                      <Badge variant={(selectedTrade.pnl_sol ?? 0) >= 0 ? "success" : "danger"}>
                        {(selectedTrade.pnl_sol ?? 0) >= 0 ? "Winner" : "Loser"}
                      </Badge>
                    </div>
                    <div className="mt-2 text-xl font-black text-white">
                      {selectedToken?.symbol || selectedTrade.token_id}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                      <span>{selectedTrade.strategy_profile}</span>
                      <span>{selectedTrade.lifecycle_status}</span>
                      {selectedSettingsVersion ? <span>{selectedSettingsVersion.label || selectedSettingsVersion.id}</span> : null}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {workflow?.previous_token_id ? (
                      <Button variant="secondary" size="sm" onClick={() => onSelectTrade(workflow.previous_token_id)}>
                        Previous
                      </Button>
                    ) : null}
                    {workflow?.next_token_id ? (
                      <Button variant="secondary" size="sm" onClick={() => onSelectTrade(workflow.next_token_id)}>
                        Next
                      </Button>
                    ) : null}
                    {reviewLabels.map((label) => (
                      <button
                        key={label}
                        onClick={() => selectedTradeId && onLabelTrade(selectedTradeId, label)}
                        className={cn(
                          "rounded-lg border px-2.5 py-1 text-[10px] font-black uppercase tracking-wider transition-colors",
                          selectedLabel === label
                            ? "border-amber-400 bg-amber-400 text-[#160f08]"
                            : "border-white/10 bg-white/[0.03] text-zinc-400 hover:border-white/20 hover:text-white"
                        )}
                      >
                        {label.replace(/_/g, " ")}
                      </button>
                    ))}
                  </div>
                </div>
                {workflow ? (
                  <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px] text-zinc-400">
                    <span className="font-black uppercase tracking-widest text-zinc-500">
                      Review {workflow.current_index >= 0 ? workflow.current_index + 1 : "-"} / {workflow.total_closed}
                    </span>
                    {workflow.suggested_labels.map((label) => (
                      <button
                        key={label}
                        onClick={() => selectedTradeId && onLabelTrade(selectedTradeId, label)}
                        className="rounded-md border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-wider text-amber-200 hover:bg-amber-500/20"
                      >
                        {label.replace(/_/g, " ")}
                      </button>
                    ))}
                    <span className="min-w-0 flex-1 text-right text-zinc-500">{workflow.operator_action}</span>
                  </div>
                ) : null}

                <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-5">
                  <ReviewMetric label="P&L" value={`${selectedTrade.pnl_sol?.toFixed(4) ?? "0.0000"} SOL`} tone={(selectedTrade.pnl_sol ?? 0) >= 0 ? "good" : "bad"} />
                  <ReviewMetric label="Entry" value={formatNumber(selectedTrade.entry_price, 9)} />
                  <ReviewMetric label="Exit" value={formatNumber(selectedTrade.exit_price, 9)} />
                  <ReviewMetric label="Size" value={`${formatNumber(selectedTrade.amount_sol, 3)} SOL`} />
                  <ReviewMetric label="Hold" value={formatDuration(selectedTrade.hold_duration_seconds)} tone="warn" />
                </div>

                <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
                  <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                    <div className="mb-3 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-zinc-500">
                      <Shield size={14} />
                      PnL Breakdown
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-[11px]">
                      <ReviewMetric label="Net" value={`${formatNumber(detail?.pnl_breakdown?.final_pnl_sol, 4)} SOL`} tone={(detail?.pnl_breakdown?.final_pnl_sol ?? 0) >= 0 ? "good" : "bad"} />
                      <ReviewMetric label="Before Fees" value={`${formatNumber(detail?.pnl_breakdown?.net_before_fees_estimate, 4)} SOL`} />
                      <ReviewMetric label="Fees" value={`${formatNumber(detail?.pnl_breakdown?.fees_sol, 4)} SOL`} tone="warn" />
                      <ReviewMetric label="Slippage" value={`${formatNumber(detail?.pnl_breakdown?.slippage_pct, 2)}%`} tone="warn" />
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                    <div className="mb-3 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-zinc-500">
                      <Activity size={14} />
                      Evidence Summary
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-[11px]">
                      <ReviewMetric label="Decisions" value={String(detail?.decisions?.length ?? 0)} />
                      <ReviewMetric label="Accepted Prices" value={String(acceptedObservations.length)} tone="good" />
                      <ReviewMetric label="Rejected Prices" value={String(rejectedObservations.length)} tone={rejectedObservations.length ? "bad" : "neutral"} />
                      <ReviewMetric label="Confidence" value={`${Math.round((selectedTrade.source_price_confidence ?? 0) * 100)}%`} tone="warn" />
                    </div>
                  </div>
                </div>

                <div className="mt-5 rounded-xl border border-white/5 bg-white/[0.02] p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-zinc-500">
                      <Target size={14} /> Deterministic Grade
                    </div>
                    <Badge variant={selectedGrade ? "info" : "warning"}>{selectedGrade ? `${Math.round(selectedGrade.confidence * 100)}% confidence` : "queued"}</Badge>
                  </div>
                  {selectedGrade ? (
                    <>
                      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
                        {Object.entries(selectedGrade.classifications).map(([name, value]) => (
                          <div key={name} className="rounded-lg bg-black/20 p-2">
                            <span className="block text-[9px] font-black uppercase tracking-widest text-zinc-600">{name}</span>
                            <span className={cn("font-black", value === "good" ? "text-emerald-400" : value === "poor" ? "text-rose-400" : "text-amber-300")}>{value}</span>
                          </div>
                        ))}
                      </div>
                      <div className="mt-3 text-[10px] text-zinc-600">{selectedGrade.mode.replace(/_/g, " ")} · {selectedGrade.grader_version} · {selectedGrade.evidence_ids.length} evidence IDs</div>
                    </>
                  ) : (
                    <p className="text-[11px] text-zinc-500">The low-priority worker has not published a grade for this immutable revision yet. Trade persistence is unaffected.</p>
                  )}
                </div>

                <div className="mt-5 rounded-xl border border-amber-500/10 bg-amber-500/[0.03] p-4">
                  <div className="text-[10px] font-black uppercase tracking-widest text-amber-300">Decision Verdict</div>
                  <div className="mt-2 text-sm leading-relaxed text-zinc-200">
                    {selectedTrade.exit_reason || selectedTrade.entry_reason || selectedDecision?.reason || "No detailed rationale was recorded for this trade."}
                  </div>
                  {selectedDecision?.decision_log?.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {selectedDecision.decision_log.slice(0, 6).map((line) => (
                        <span key={line} className="rounded-md border border-white/10 bg-black/30 px-2 py-1 text-[10px] text-zinc-300">
                          {line}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </Card>

              <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.35fr)_360px]">
                <Card className="flex h-[640px] min-h-[640px] flex-col" hover={false}>
                  <div className="border-b border-white/5 p-4">
                    <h3 className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-zinc-500">
                      <Target size={14} />
                      Timeline
                    </h3>
                  </div>
                  <div className="crypto-scrollbar flex-1 overflow-auto p-4">
                    <div className="relative space-y-5 before:absolute before:left-[7px] before:top-1 before:h-[calc(100%-8px)] before:w-px before:bg-white/8">
                      {selectedTimeline.map((event) => (
                        <div key={`${event.at}-${event.title}`} className="relative pl-8">
                          <div className="absolute left-0 top-1.5 h-4 w-4 rounded-full border border-white/10 bg-[#0b0d15]">
                            <div
                              className={cn(
                                "mx-auto mt-[4px] h-1.5 w-1.5 rounded-full",
                                event.type.includes("price") && "bg-blue-400",
                                event.type.includes("decision") && "bg-amber-300",
                                event.type.includes("trade") && "bg-emerald-400",
                                event.type.includes("source") && "bg-fuchsia-400",
                                !event.type.includes("price") && !event.type.includes("decision") && !event.type.includes("trade") && !event.type.includes("source") && "bg-zinc-500"
                              )}
                            />
                          </div>
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="text-xs font-black uppercase tracking-wide text-white">{event.title}</div>
                            <div className="text-[10px] font-mono text-zinc-600">{new Date(event.at).toLocaleString()}</div>
                          </div>
                          <div className="mt-1 text-[11px] leading-relaxed text-zinc-400">{event.detail}</div>
                          <div className="mt-1 text-[10px] uppercase tracking-wider text-zinc-600">{event.type}</div>
                        </div>
                      ))}
                      {!selectedTimeline.length ? <div className="py-10 text-center text-xs text-zinc-500">No replay timeline was recorded for this trade.</div> : null}
                    </div>
                  </div>
                </Card>

                <div className="space-y-6">
                  <Card className="p-4" hover={false}>
                    <h3 className="mb-4 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-zinc-500">
                      <TrendingUp size={14} />
                      Decision Stack
                    </h3>
                    <div className="space-y-3">
                      {detail?.decisions?.slice(0, 6).map((decision) => (
                        <div key={decision.id} className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-black uppercase text-white">{decision.action}</span>
                            <Badge variant={decision.allowed ? "success" : "warning"}>{decision.score}</Badge>
                          </div>
                          <div className="mt-2 text-[11px] text-zinc-400">{decision.reason}</div>
                          {decision.score_breakdown?.length ? (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {decision.score_breakdown.slice(0, 4).map((line) => (
                                <span key={line} className="rounded-md border border-white/10 px-2 py-1 text-[10px] text-zinc-500">
                                  {line}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ))}
                      {!detail?.decisions?.length ? <div className="text-xs text-zinc-500">No strategy decision records are attached to this trade.</div> : null}
                    </div>
                  </Card>

                  <Card className="p-4" hover={false}>
                    <h3 className="mb-4 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-zinc-500">
                      <Sparkles size={14} />
                      Auto-Tuning Suggestions
                    </h3>
                    <div className="space-y-3">
                      {suggestions.slice(0, 3).map((item) => (
                        <div key={`${item.setting}-${item.title}`} className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-black uppercase text-white">{item.title}</span>
                            <Badge variant="info">{Math.round(item.confidence * 100)}%</Badge>
                          </div>
                          <div className="mt-2 text-[11px] leading-relaxed text-zinc-400">{item.reason}</div>
                          <div className="mt-2 text-[10px] uppercase tracking-wider text-amber-300">
                            Suggested: {item.suggested_value === undefined ? "Review only" : String(item.suggested_value)}
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

                  <Card className="p-4" hover={false}>
                    <h3 className="mb-4 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-zinc-500">
                      <Clock size={14} />
                      Evidence Checklist
                    </h3>
                    <div className="space-y-2">
                      {(workflow?.checklist ?? []).map((item) => (
                        <div key={item.id} className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-[11px] font-black uppercase tracking-wider text-white">{item.label}</span>
                            <Badge variant={item.status === "pass" ? "success" : item.status === "warn" ? "warning" : "danger"}>{item.count}</Badge>
                          </div>
                          <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">{item.operator_action}</p>
                          {item.ids.length ? <p className="mt-2 truncate font-mono text-[10px] text-zinc-600">{item.ids.join(", ")}</p> : null}
                        </div>
                      ))}
                      {!workflow?.checklist?.length ? <div className="text-xs text-zinc-500">No review checklist is available for this trade.</div> : null}
                    </div>
                  </Card>

                  <Card className="p-4" hover={false}>
                    <h3 className="mb-4 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-zinc-500">
                      <Clock size={14} />
                      Review Context
                    </h3>
                    <div className="space-y-2 text-[11px] text-zinc-400">
                      <div className="flex justify-between gap-3">
                        <span>Selected settings</span>
                        <span className="text-right text-white">{selectedSettingsVersion?.label || selectedTrade.settings_version_id || "Legacy"}</span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span>Strategy median P&L</span>
                        <span className="text-right text-white">
                          {analytics?.by_strategy.find((item) => item.label === selectedTrade.strategy_profile)?.avg_pnl_sol?.toFixed(4) ?? "0.0000"} SOL
                        </span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span>Token mint</span>
                        <span className="text-right text-white">{selectedToken?.mint || "-"}</span>
                      </div>
                    </div>
                  </Card>
                </div>
              </div>
            </>
          ) : (
            <Card className="flex min-h-[520px] flex-col items-center justify-center p-12 text-center" hover={false}>
              <div className="mb-4 rounded-full border border-white/10 bg-white/[0.03] p-5 text-zinc-600">
                <Target size={40} />
              </div>
              <h3 className="text-lg font-black text-white">Select a trade to review</h3>
              <p className="mt-2 max-w-md text-sm text-zinc-500">
                Pick a closed trade from the left to inspect its decision trail, observed price evidence, PnL breakdown, and tuning context.
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};
