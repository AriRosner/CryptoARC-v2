import React from "react";
import { StyleSheet, View } from "react-native";

import { spacing } from "../../theme";
import { Skeleton } from "./Skeleton";

export function TradeDetailSkeleton() {
  return (
    <View
      accessibilityLabel="Loading trade review"
      testID="trade-detail-initial-skeleton"
      style={styles.stack}>
      <View testID="trade-detail-header-skeleton" style={styles.header}>
        <Skeleton height={48} />
      </View>
      <View testID="trade-detail-evidence-skeleton" style={styles.evidence}>
        <Skeleton height={180} />
      </View>
      <View testID="trade-detail-form-skeleton" style={styles.form}>
        <Skeleton height={260} />
      </View>
      <View testID="trade-detail-auth-skeleton" style={styles.auth}>
        <Skeleton height={64} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: spacing.md },
  header: { height: 48 },
  evidence: { height: 180 },
  form: { height: 260 },
  auth: { height: 64 },
});
