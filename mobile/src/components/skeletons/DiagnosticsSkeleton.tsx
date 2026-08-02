import React from "react";
import { StyleSheet, View } from "react-native";
import { spacing } from "../../theme";
import { Skeleton } from "./Skeleton";
export function DiagnosticsSkeleton() { return <View accessibilityLabel="Loading diagnostics" testID="diagnostics-initial-skeleton" style={styles.stack}><Skeleton height={220} /><Skeleton height={220} /></View>; }
const styles = StyleSheet.create({ stack: { gap: spacing.sm } });
