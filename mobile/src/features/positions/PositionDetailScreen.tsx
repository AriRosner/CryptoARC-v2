import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ShieldAlert } from "lucide-react-native";
import React from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ActionButton, DetailRow, EmptyState, PageHeader, Section, StatusBadge } from "../../components/ui";
import { MobileApiError } from "../../core/api/errors";
import { useOptionalSession } from "../../core/session/SessionProvider";
import { colors, radius, spacing } from "../../theme";
import { fetchPositionDetail } from "./api";

export function PositionDetailScreen({
  positionId,
  onBack,
}: {
  positionId: string;
  onBack(): void;
}) {
  const session = useOptionalSession();
  const query = useQuery({
    queryKey: ["mobile", "position", positionId, session?.generation ?? "test"],
    queryFn: () =>
      session
        ? fetchPositionDetail(positionId, {
            apiBaseUrl: session.apiBaseUrl,
            token: session.token,
          })
        : fetchPositionDetail(positionId),
    enabled: Boolean(positionId) && (session === null || Boolean(session.token)),
  });
  const position = query.data;
  const notFound = query.error instanceof MobileApiError && query.error.status === 404;

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Pressable accessibilityLabel="Back to portfolio" onPress={onBack} style={styles.back}>
          <ArrowLeft size={20} color={colors.text} />
        </Pressable>
        {query.isLoading ? (
          <View accessibilityLabel="Loading position details" style={styles.skeletonStack}>
            <View style={[styles.skeleton, { height: 36, width: "48%" }]} />
            <View style={[styles.skeleton, { height: 128 }]} />
            <View style={[styles.skeleton, { height: 220 }]} />
          </View>
        ) : !position ? (
          <>
            <EmptyState
              title={notFound ? "Position not found" : "Position unavailable"}
              body={
                notFound
                  ? "This stable position ID is no longer present in the local ledger."
                  : "The private tunnel or mobile API is unavailable."
              }
            />
            {!notFound ? <ActionButton label="Retry" onPress={() => void query.refetch()} /> : null}
          </>
        ) : (
          <>
            <PageHeader
              eyebrow={`${position.mode} position`}
              title={position.symbol}
              subtitle={position.mint}
              right={<StatusBadge label={position.status} tone={position.status === "open" ? "success" : "neutral"} />}
            />
            {query.isError ? (
              <View style={styles.retryBand}>
                <Text style={styles.retryText}>The latest refresh failed. Showing the cached detail.</Text>
                <ActionButton label="Retry" onPress={() => void query.refetch()} />
              </View>
            ) : null}
            <Section title="Performance" right={<StatusBadge label={position.pnl.approximate ? "Approximate" : "Reconciled"} tone={position.pnl.approximate ? "warning" : "success"} />}>
              <DetailRow label="Tracked value" value={`${position.value_sol.toFixed(6)} SOL`} />
              <DetailRow label="Open cost basis" value={`${position.cost_basis_sol.toFixed(6)} SOL`} />
              <DetailRow label="Realized PnL" value={`${position.pnl.realized_sol.toFixed(6)} SOL`} tone={position.pnl.realized_sol >= 0 ? "success" : "danger"} />
              <DetailRow label="Unrealized PnL" value={`${position.pnl.unrealized_sol.toFixed(6)} SOL`} tone={position.pnl.unrealized_sol >= 0 ? "success" : "danger"} />
              <DetailRow label="PnL confidence" value={position.pnl.confidence} />
            </Section>
            <Section title="Mark evidence">
              <DetailRow label="Price" value={`${position.mark.price_sol.toFixed(10)} SOL`} />
              <DetailRow label="Source" value={position.mark.source || "Unavailable"} />
              <DetailRow label="Age" value={position.mark.age_seconds === null ? "Unavailable" : `${position.mark.age_seconds}s`} tone={position.mark.fresh ? "success" : "warning"} />
              <DetailRow label="Confidence" value={`${Math.round(position.mark.confidence * 100)}%`} />
              <DetailRow label="Reconciliation" value={position.reconciliation_status} />
            </Section>
            <View style={styles.guard}>
              <ShieldAlert size={18} color={colors.amber} />
              <Text style={styles.guardText}>{position.allowed_actions.reason}</Text>
            </View>
          </>
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
    gap: spacing.md,
  },
  back: {
    alignItems: "center",
    justifyContent: "center",
    height: 44,
    width: 44,
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
    backgroundColor: colors.panel,
  },
  guard: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    borderColor: colors.amber,
    borderRadius: radius.md,
    borderWidth: 1,
    backgroundColor: colors.amberSoft,
    padding: spacing.md,
  },
  guardText: {
    color: colors.text,
    flex: 1,
    fontSize: 11,
    lineHeight: 17,
  },
  skeletonStack: {
    gap: spacing.md,
  },
  skeleton: {
    backgroundColor: colors.panelRaised,
    borderRadius: radius.sm,
  },
  retryBand: {
    borderColor: colors.rose,
    borderRadius: radius.md,
    borderWidth: 1,
    backgroundColor: colors.roseSoft,
    padding: spacing.sm,
    gap: spacing.sm,
  },
  retryText: {
    color: colors.rose,
    fontSize: 11,
    lineHeight: 16,
  },
});
