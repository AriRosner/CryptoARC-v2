import { CartesianChart, Line } from "victory-native";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, spacing } from "../../theme";
import { useSettingsStore } from "../../core/settings/settingsStore";
import type { PortfolioPoint } from "./types";

export function PerformanceChart({ series }: { series: PortfolioPoint[] }) {
  const motion = useSettingsStore((state) => state.motion);
  const data = series.map((point, index) => ({
    index,
    value: point.net_pnl_sol,
  }));

  if (data.length < 2) {
    return <Text style={styles.empty}>Performance history will appear after observed closes.</Text>;
  }

  return (
    <View>
      <View style={styles.chart} accessibilityLabel="Net performance chart">
        <CartesianChart
          data={data}
          xKey="index"
          yKeys={["value"]}
          domainPadding={{ top: 12, bottom: 12, left: 8, right: 8 }}>
          {({ points }) => (
            <Line
              points={points.value}
              color={data[data.length - 1].value >= 0 ? colors.emerald : colors.rose}
              strokeWidth={3}
              curveType="linear"
              animate={
                motion === "expressive" || motion === "balanced"
                  ? { type: "timing", duration: motion === "expressive" ? 220 : 160 }
                  : undefined
              }
            />
          )}
        </CartesianChart>
      </View>
      <Text style={styles.caption}>
        Historical points are realized paper performance. The latest point adds the approximate current snapshot.
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
  empty: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
    paddingVertical: spacing.lg,
    textAlign: "center",
  },
});
