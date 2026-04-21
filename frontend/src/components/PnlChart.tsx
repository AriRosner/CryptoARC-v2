import React from "react";
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip } from "recharts";
import { Skeleton } from "./Skeleton";

interface PnlChartProps {
  data: number[];
  height?: number;
  unit?: "SOL" | "USD";
  animationKey?: string;
  loading?: boolean;
}

export const PnlChart: React.FC<PnlChartProps> = React.memo(({ data, height = 100, unit = "SOL", animationKey = "default", loading = false }) => {
  const id = React.useId();
  const gradientId = `pnlGradient-${id.replace(/:/g, "")}`;
  const lastAnimationKeyRef = React.useRef<string | null>(null);
  const hasData = data.length > 0;
  const chartData = React.useMemo(() => {
    if (data.length === 0) return [{ index: 0, value: 0 }, { index: 1, value: 0 }];
    if (data.length === 1) return [{ index: 0, value: data[0] }, { index: 1, value: data[0] }];
    return data.map((value, index) => ({ index, value }));
  }, [data]);
  const isPositive = (data[data.length - 1] || 0) >= (data[0] || 0);
  const shouldAnimate = hasData && data.length > 1 && data.length <= 180 && lastAnimationKeyRef.current !== animationKey;

  React.useEffect(() => {
    lastAnimationKeyRef.current = animationKey;
  }, [animationKey]);

  return (
    <div className="relative overflow-hidden rounded-lg" style={{ width: "100%", height }}>
      {loading ? (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#090b13]/78 backdrop-blur-sm">
          <div className="w-[min(86%,320px)] space-y-3 rounded-xl border border-white/10 bg-[#0d1018]/88 px-4 py-4 shadow-[0_18px_50px_rgba(0,0,0,0.35)]">
            <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.24em] text-[#00ffbd]">
              <span className="h-2 w-2 animate-pulse rounded-full bg-[#00ffbd] shadow-[0_0_12px_rgba(0,255,189,0.75)]" />
              Loading P&amp;L Stream
            </div>
            <Skeleton className="h-3 w-24 rounded-full" />
            <Skeleton className="h-16 w-full rounded-xl" />
            <div className="grid grid-cols-3 gap-2">
              <Skeleton className="h-2.5 rounded-full" />
              <Skeleton className="h-2.5 rounded-full" />
              <Skeleton className="h-2.5 rounded-full" />
            </div>
          </div>
        </div>
      ) : !hasData ? (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#090b13]/70 backdrop-blur-sm">
          <div className="flex items-center gap-3 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[10px] font-black uppercase tracking-widest text-amber-300">
            <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400 shadow-[0_0_12px_rgba(232,154,74,0.8)]" />
            Awaiting P&amp;L Data
          </div>
        </div>
      ) : null}
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="5%"
                stopColor={isPositive ? "#10b981" : "#f43f5e"}
                stopOpacity={0.3}
              />
              <stop
                offset="95%"
                stopColor={isPositive ? "#10b981" : "#f43f5e"}
                stopOpacity={0}
              />
            </linearGradient>
          </defs>
          <ReferenceLine y={0} stroke="#3f3f46" strokeDasharray="3 3" />
          <Area
            type="monotone"
            dataKey="value"
            stroke={isPositive ? "#10b981" : "#f43f5e"}
            strokeWidth={2}
            fillOpacity={1}
            fill={`url(#${gradientId})`}
            isAnimationActive={shouldAnimate}
            animationDuration={450}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                return (
                  <div className="rounded-lg border border-white/10 bg-[#090b13] p-2 text-xs shadow-xl">
                    <p className="font-bold text-white">
                      {unit === "USD" ? "$" : ""}{payload[0].value?.toLocaleString(undefined, { minimumFractionDigits: unit === "USD" ? 2 : 4, maximumFractionDigits: unit === "USD" ? 2 : 4 })} {unit === "USD" ? "" : "SOL"}
                    </p>
                  </div>
                );
              }
              return null;
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
});

PnlChart.displayName = "PnlChart";
