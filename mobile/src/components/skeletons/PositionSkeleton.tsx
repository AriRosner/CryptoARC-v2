import React from "react";
import { StyleSheet, View } from "react-native";
import { spacing } from "../../theme";
import { Skeleton } from "./Skeleton";
export function PositionSkeleton() { return <View accessibilityLabel="Loading position details" testID="position-initial-skeleton" style={styles.stack}><Skeleton width="48%" height={36} /><Skeleton height={128} /><Skeleton height={220} /></View>; }
const styles = StyleSheet.create({ stack: { gap: spacing.md } });
