import { CartesianChart, Line } from "victory-native";
import { Circle } from "@shopify/react-native-skia";
import React, { useEffect, useMemo, useState } from "react";
import { AccessibilityInfo, StyleSheet, Text, View } from "react-native";

import {
  type MotionPreference,
  useSettingsStore,
} from "../../core/settings/settingsStore";
import { colors, spacing } from "../../theme";
import type {
  CurrentPortfolioSnapshot,
  PortfolioPoint,
} from "./types";

export interface PerformanceChartDatum extends Record<string, unknown> {
  currentSnapshot: boolean;
  timestamp: number;
  value: number;
}

export function buildPerformanceChartData(
  series: PortfolioPoint[],
  currentSnapshot?: CurrentPortfolioSnapshot,
): PerformanceChartDatum[] {
  const periodPoints = series.filter((point) => !point.current_snapshot);
  const legacySnapshot = series.find((point) => point.current_snapshot);
  const snapshotPoint: PortfolioPoint | undefined = currentSnapshot
    ? {
        at: currentSnapshot.generated_at,
        net_pnl_sol: currentSnapshot.net_pnl_sol,
        paper_pnl_sol: currentSnapshot.paper_pnl_sol,
        live_pnl_sol: currentSnapshot.live_pnl_sol,
        current_snapshot: true,
        approximate: currentSnapshot.approximate,
      }
    : legacySnapshot;
  return [...periodPoints, ...(snapshotPoint ? [snapshotPoint] : [])]
    .map((point) => ({
      currentSnapshot: point.current_snapshot,
      timestamp: Date.parse(point.at),
      value: point.net_pnl_sol,
    }))
    .filter((point) => Number.isFinite(point.timestamp));
}

export function performanceChartAnimation(
  motion: MotionPreference,
  systemReducedMotion: boolean,
) {
  if (motion === "minimal" || (motion === "system" && systemReducedMotion)) {
    return undefined;
  }
  return {
    type: "timing" as const,
    duration: motion === "expressive" ? 220 : 160,
  };
}

export function PerformanceChart({
  currentSnapshot,
  series,
}: {
  currentSnapshot?: CurrentPortfolioSnapshot;
  series: PortfolioPoint[];
}) {
  const motion = useSettingsStore((state) => state.motion);
  const [systemReducedMotion, setSystemReducedMotion] = useState(true);
  useEffect(() => {
    if (motion !== "system") return;
    let active = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((enabled) => {
      if (active) setSystemReducedMotion(enabled);
    });
    const subscription = AccessibilityInfo.addEventListener(
      "reduceMotionChanged",
      setSystemReducedMotion,
    );
    return () => {
      active = false;
      subscription.remove();
    };
  }, [motion]);

  const data = useMemo(
    () => buildPerformanceChartData(series, currentSnapshot),
    [currentSnapshot, series],
  );
  const animation = performanceChartAnimation(motion, systemReducedMotion);
  const legacySnapshot = series.find((point) => point.current_snapshot);
  const snapshot = currentSnapshot
    ? {
        approximate: currentSnapshot.approximate,
        value: currentSnapshot.net_pnl_sol,
      }
    : legacySnapshot
      ? {
          approximate: legacySnapshot.approximate,
          value: legacySnapshot.net_pnl_sol,
        }
      : null;
  const latestPeriodValue = [...data]
    .reverse()
    .find((point) => !point.currentSnapshot)?.value ?? 0;

  if (data.length < 2) {
    return (
      <View>
        <Text style={styles.empty}>Performance history will appear after observed closes.</Text>
        {snapshot ? <SnapshotLabel approximate={snapshot.approximate} value={snapshot.value} /> : null}
      </View>
    );
  }

  return (
    <View>
      <View style={styles.chart} accessibilityLabel="Net performance chart">
        <CartesianChart
          data={data}
          xKey="timestamp"
          yKeys={["value"]}
          domainPadding={{ top: 12, bottom: 12, left: 8, right: 8 }}>
          {({ points }) => (
            <>
              <Line
                points={points.value.slice(
                  0,
                  data[data.length - 1].currentSnapshot ? -1 : undefined,
                )}
                color={latestPeriodValue >= 0 ? colors.emerald : colors.rose}
                strokeWidth={3}
                curveType="linear"
                animate={animation}
              />
              {(() => {
                const point = points.value[points.value.length - 1];
                return data[data.length - 1].currentSnapshot &&
                  typeof point?.x === "number" &&
                  typeof point.y === "number" ? (
                  <Circle
                    cx={point.x}
                    cy={point.y}
                    r={5}
                    color={colors.amber}
                  />
                ) : null;
              })()}
            </>
          )}
        </CartesianChart>
      </View>
      <Text style={styles.caption}>The line is selected-period realized paper performance plotted by observation time.</Text>
      {snapshot ? <SnapshotLabel approximate={snapshot.approximate} value={snapshot.value} /> : null}
    </View>
  );
}

function SnapshotLabel({ approximate, value }: { approximate: boolean; value: number }) {
  return (
    <View style={styles.snapshot}>
      <View style={styles.snapshotDot} />
      <Text style={styles.snapshotText}>
        {approximate ? "Approximate" : "Reconciled"} current snapshot: {value >= 0 ? "+" : ""}
        {value.toFixed(4)} SOL
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chart: {
    height: 176,
  },
  caption: {
    color: colors.faint,
    fontSize: 10,
    lineHeight: 15,
    marginTop: spacing.xs,
  },
  snapshot: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.xs,
    marginTop: spacing.sm,
  },
  snapshotDot: {
    backgroundColor: colors.amber,
    borderRadius: 5,
    height: 10,
    width: 10,
  },
  snapshotText: {
    color: colors.muted,
    flex: 1,
    fontSize: 10,
    lineHeight: 15,
  },
  empty: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
    paddingVertical: spacing.lg,
    textAlign: "center",
  },
});
