import React from "react";
import { StyleSheet, View } from "react-native";

import { MetricTile } from "../../components/ui";
import { spacing } from "../../theme";
import type { PortfolioSummary } from "./types";

function sol(value: number): string {
  return `${value >= 0 ? "" : "-"}${Math.abs(value).toFixed(4)} SOL`;
}

export function PortfolioMetrics({ summary }: { summary: PortfolioSummary }) {
  return (
    <View style={styles.grid}>
      <MetricTile
        label="Tracked value"
        value={sol(summary.tracked_value_sol)}
        detail={`${sol(summary.cost_basis_sol)} open basis`}
      />
      <MetricTile
        label="Net performance"
        value={sol(summary.net_pnl_sol)}
        tone={summary.net_pnl_sol >= 0 ? "success" : "danger"}
        detail={`${summary.closed_trades} closed`}
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
