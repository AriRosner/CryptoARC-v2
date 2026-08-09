import React from "react";
import { StyleSheet, View } from "react-native";

import { MetricTile } from "../../components/ui";
import { AnimatedNumber } from "../../components/motion/AnimatedNumber";
import { colors, spacing } from "../../theme";
import type { CurrentPortfolioSnapshot, PortfolioSummary, PortfolioTimeframe } from "./types";

function sol(value: number): string {
  return `${value >= 0 ? "" : "-"}${Math.abs(value).toFixed(4)} SOL`;
}

export function PortfolioMetrics({
  currentSnapshot,
  summary,
  timeframe,
}: {
  currentSnapshot: CurrentPortfolioSnapshot;
  summary: PortfolioSummary;
  timeframe: PortfolioTimeframe;
}) {
  return (
    <View style={styles.grid}>
      <MetricTile
        label="Current tracked value"
        value={
          <AnimatedNumber
            accessibilityLabel={`Current tracked value: ${sol(currentSnapshot.tracked_value_sol)}`}
            format={sol}
            value={currentSnapshot.tracked_value_sol}
            style={styles.value}
          />
        }
        detail={`${sol(currentSnapshot.cost_basis_sol)} open basis`}
      />
      <MetricTile
        label="Period realized"
        value={
          <AnimatedNumber
            accessibilityLabel={`Period realized: ${sol(summary.selected_period_realized_pnl_sol)}`}
            format={sol}
            value={summary.selected_period_realized_pnl_sol}
            style={summary.selected_period_realized_pnl_sol >= 0 ? styles.success : styles.danger}
          />
        }
        tone={summary.selected_period_realized_pnl_sol >= 0 ? "success" : "danger"}
        detail={`${timeframe.toUpperCase()} paper closes`}
      />
      <MetricTile
        label="Win rate"
        value={
          <AnimatedNumber
            accessibilityLabel={`Win rate: ${summary.win_rate_pct}%`}
            format={(value) => `${Math.round(value)}%`}
            value={summary.win_rate_pct}
            style={summary.win_rate_pct >= 50 ? styles.success : styles.warning}
          />
        }
        tone={summary.win_rate_pct >= 50 ? "success" : "warning"}
        detail="decisive paper trades"
      />
      <MetricTile
        label="Health"
        value={
          <AnimatedNumber
            accessibilityLabel={`Health: ${summary.health_score}`}
            format={(value) => String(Math.round(value))}
            value={summary.health_score}
            style={summary.health_score >= 75 ? styles.success : summary.health_score >= 50 ? styles.warning : styles.danger}
          />
        }
        tone={summary.health_score >= 75 ? "success" : summary.health_score >= 50 ? "warning" : "danger"}
        detail="source score"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  value: { color: colors.text, fontSize: 18, fontWeight: "900" },
  success: { color: colors.emerald, fontSize: 18, fontWeight: "900" },
  warning: { color: colors.amber, fontSize: 18, fontWeight: "900" },
  danger: { color: colors.rose, fontSize: 18, fontWeight: "900" },
});
