import React from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from "recharts";

interface PnlChartProps {
  data: number[];
  height?: number;
}

export const PnlChart: React.FC<PnlChartProps> = ({ data, height = 100 }) => {
  const chartData = data.map((value, index) => ({ index, value }));
  const isPositive = (data[data.length - 1] || 0) >= (data[0] || 0);

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
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
            fill="url(#pnlGradient)"
            isAnimationActive={true}
            animationDuration={1000}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                return (
                  <div className="rounded-lg border border-white/10 bg-[#090b13] p-2 text-xs shadow-xl">
                    <p className="font-bold text-white">
                      {payload[0].value?.toLocaleString(undefined, { minimumFractionDigits: 4 })} SOL
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
};
