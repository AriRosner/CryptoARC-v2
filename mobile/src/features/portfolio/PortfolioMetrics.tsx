import React from "react";
import { StyleSheet, View } from "react-native";

import { MetricTile } from "../../components/ui";
import { spacing } from "../../theme";
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
        value={sol(currentSnapshot.tracked_value_sol)}
        detail={`${sol(currentSnapshot.cost_basis_sol)} open basis`}
      />
      <MetricTile
        label="Period realized"
        value={sol(summary.selected_period_realized_pnl_sol)}
        tone={summary.selected_period_realized_pnl_sol >= 0 ? "success" : "danger"}
        detail={`${timeframe.toUpperCase()} paper closes`}
      />
      <MetricTile
        label="Win rate"
        value={`${summary.win_rate_pct}%`}
        tone={summary.win_rate_pct >= 50 ? "success" : "warning"}
        detail="decisive paper trades"
      />
      <MetricTile
        label="Health"
        value={summary.health_score}
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
});
