import React from "react";
import { StyleSheet, View } from "react-native";
import { spacing } from "../../theme";
import { Skeleton } from "./Skeleton";
export function WalletSkeleton() { return <View accessibilityLabel="Loading wallet" testID="wallet-initial-skeleton" style={styles.stack}><Skeleton height={180} /><Skeleton height={120} /><Skeleton height={220} /></View>; }
const styles = StyleSheet.create({ stack: { gap: spacing.md } });
