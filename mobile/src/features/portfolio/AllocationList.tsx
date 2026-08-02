import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { StatusBadge } from "../../components/ui";
import { colors, spacing } from "../../theme";
import type { PortfolioAllocation } from "./types";

export function AllocationList({ allocation }: { allocation: PortfolioAllocation[] }) {
  if (!allocation.length) {
    return <Text style={styles.empty}>No positive open tracked value is available.</Text>;
  }
  return (
    <View>
      {allocation.map((item) => (
        <View key={item.key} style={styles.row}>
          <View style={styles.labelBlock}>
            <Text style={styles.label}>{item.label}</Text>
            <StatusBadge label={item.mode} tone={item.mode === "live" ? "warning" : "neutral"} />
          </View>
          <View style={styles.valueBlock}>
            <Text style={styles.value}>{item.value_sol.toFixed(4)} SOL</Text>
            <Text style={styles.percentage}>{item.percentage.toFixed(1)}%</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: 54,
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    borderBottomColor: colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    paddingVertical: spacing.sm,
    gap: spacing.md,
  },
  labelBlock: {
    alignItems: "center",
    flex: 1,
    flexDirection: "row",
    gap: spacing.sm,
  },
  label: {
    color: colors.text,
    flexShrink: 1,
    fontSize: 13,
    fontWeight: "900",
  },
  valueBlock: {
    alignItems: "flex-end",
  },
  value: {
    color: colors.text,
    fontSize: 12,
    fontWeight: "800",
  },
  percentage: {
    color: colors.muted,
    fontSize: 10,
    marginTop: 3,
  },
  empty: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
});
