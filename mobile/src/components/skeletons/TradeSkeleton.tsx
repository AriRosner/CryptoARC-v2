import React from "react";
import { StyleSheet, View } from "react-native";
import { spacing } from "../../theme";
import { Skeleton } from "./Skeleton";
export function TradeSkeleton() { return <View accessibilityLabel="Loading prepared trades" testID="trade-initial-skeleton" style={styles.stack}><Skeleton height={112} /><Skeleton height={112} /></View>; }
const styles = StyleSheet.create({ stack: { gap: spacing.sm } });
