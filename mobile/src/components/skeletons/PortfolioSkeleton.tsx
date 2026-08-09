import React from "react";
import { StyleSheet, View } from "react-native";
import { spacing } from "../../theme";
import { Skeleton } from "./Skeleton";

export function PortfolioSkeleton() {
  return <View accessibilityLabel="Loading portfolio" testID="portfolio-initial-skeleton" style={styles.stack}>
    <View style={styles.metrics}>{[0, 1, 2, 3].map((key) => <View key={key} testID="portfolio-metric-skeleton" style={styles.metric}><Skeleton height={92} /></View>)}</View>
    <Skeleton height={220} />
    <Skeleton height={64} />
    <Skeleton height={64} />
  </View>;
}
const styles = StyleSheet.create({ stack: { gap: spacing.md }, metrics: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", gap: spacing.sm }, metric: { width: "48%" } });
