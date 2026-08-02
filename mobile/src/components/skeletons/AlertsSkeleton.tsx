import React from "react";
import { StyleSheet, View } from "react-native";
import { spacing } from "../../theme";
import { Skeleton } from "./Skeleton";
export function AlertsSkeleton() { return <View accessibilityLabel="Loading alerts" testID="alerts-initial-skeleton" style={styles.stack}><Skeleton height={150} /><Skeleton height={150} /></View>; }
const styles = StyleSheet.create({ stack: { gap: spacing.sm } });
