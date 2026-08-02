import { router } from "expo-router";
import { ArrowRight, ShieldCheck } from "lucide-react-native";
import React from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ActionButton,
  EmptyState,
  PageHeader,
  StatusBadge,
} from "../../components/ui";
import { TradeSkeleton } from "../../components/skeletons/TradeSkeleton";
import { colors, radius, spacing } from "../../theme";
import { useTradesQuery } from "./queries";

export function TradesScreen() {
  const query = useTradesQuery();
  const trades = query.data?.trades ?? [];

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader
          eyebrow="Guarded execution"
          title="Trade review"
          subtitle="Prepared intents only"
          right={<ShieldCheck color={colors.emerald} size={24} />}
        />
        {query.isLoading ? (
          <TradeSkeleton />
        ) : trades.length === 0 ? (
          <>
            <EmptyState
              title="No prepared intents"
              body="Prepare, quote, and simulate a trade on the trusted backend before reviewing it here."
            />
            {query.isError ? (
              <ActionButton label="Retry" onPress={() => void query.refetch()} />
            ) : null}
          </>
        ) : (
          <View style={styles.stack}>
            {trades.map((trade) => (
              <Pressable
                key={trade.id}
                accessibilityLabel={`Review ${trade.action} ${trade.symbol || trade.mint}`}
                accessibilityRole="button"
                onPress={() =>
                  router.push(`/trade/${encodeURIComponent(trade.id)}`)
                }
                style={({ pressed }) => [
                  styles.row,
                  pressed && styles.pressed,
                ]}>
                <View style={styles.rowCopy}>
                  <View style={styles.rowHeader}>
                    <Text style={styles.symbol}>
                      {trade.symbol || trade.mint.slice(0, 8)}
                    </Text>
                    <StatusBadge
                      label={trade.action}
                      tone={trade.action === "sell" ? "warning" : "info"}
                    />
                  </View>
                  <Text style={styles.amount}>
                    {trade.amount} {trade.limits.amount.unit}
                  </Text>
                  <Text style={styles.reason} numberOfLines={2}>
                    {trade.blockers[0] || trade.reason}
                  </Text>
                </View>
                <View style={styles.rowState}>
                  <StatusBadge
                    label={trade.status}
                    tone={
                      trade.allowed_actions.approve ? "success" : "warning"
                    }
                  />
                  <ArrowRight color={colors.muted} size={18} />
                </View>
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    padding: spacing.lg,
    paddingBottom: spacing.xl,
    gap: spacing.lg,
  },
  stack: {
    gap: spacing.sm,
  },
  row: {
    alignItems: "center",
    flexDirection: "row",
    minHeight: 112,
    padding: spacing.md,
    gap: spacing.md,
    backgroundColor: colors.panel,
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  pressed: {
    backgroundColor: colors.panelRaised,
  },
  rowCopy: {
    flex: 1,
    gap: 5,
  },
  rowHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  symbol: {
    color: colors.text,
    fontSize: 17,
    fontWeight: "900",
  },
  amount: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
  },
  reason: {
    color: colors.faint,
    fontSize: 10,
    lineHeight: 15,
  },
  rowState: {
    alignItems: "flex-end",
    gap: spacing.md,
  },
});
