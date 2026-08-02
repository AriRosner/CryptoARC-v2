import { router } from "expo-router";
import { RefreshCw } from "lucide-react-native";
import React, { useRef, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ActionButton,
  EmptyState,
  ErrorBanner,
  PageHeader,
  Section,
  SegmentedControl,
  StatusBadge,
} from "../../components/ui";
import { PortfolioSkeleton } from "../../components/skeletons/PortfolioSkeleton";
import { mobileReadErrorMessage } from "../../core/api/authenticatedRead";
import { MobileApiError } from "../../core/api/errors";
import { useOptionalSession } from "../../core/session/SessionProvider";
import { colors, radius, spacing } from "../../theme";
import { PositionList } from "../positions/PositionList";
import { PositionSheet } from "../positions/PositionSheet";
import { AllocationList } from "./AllocationList";
import { PerformanceChart } from "./PerformanceChart";
import { PortfolioMetrics } from "./PortfolioMetrics";
import { usePortfolioQuery } from "./queries";
import type { PortfolioTimeframe } from "./types";
import type { PortfolioPayload } from "./types";

const timeframes = [
  { label: "1D", value: "1d" },
  { label: "1W", value: "1w" },
  { label: "1M", value: "1m" },
  { label: "ALL", value: "all" },
];

export function PortfolioScreen() {
  const [timeframe, setTimeframe] = useState<PortfolioTimeframe>("1d");
  const [selectedPositionId, setSelectedPositionId] = useState<string | null>(null);
  const query = usePortfolioQuery(timeframe);
  const session = useOptionalSession();
  const canRead = session === null || Boolean(session.token);
  const needsPairing =
    session !== null && !session.loading && !session.token;
  const sessionKey =
    session === null
      ? "test"
      : `${session.generation}:${session.device?.id ?? "no-device"}`;
  const lastPayloadRef = useRef<
    { payload: PortfolioPayload; sessionKey: string } | undefined
  >(undefined);
  const accessDenied =
    query.error instanceof MobileApiError &&
    (query.error.status === 401 || query.error.status === 403);
  if (
    !canRead ||
    (lastPayloadRef.current &&
      lastPayloadRef.current.sessionKey !== sessionKey)
  ) {
    lastPayloadRef.current = undefined;
  }
  if (query.data && canRead && !accessDenied) {
    lastPayloadRef.current = { payload: query.data, sessionKey };
  }
  const payload = accessDenied
    ? undefined
    : query.data ?? lastPayloadRef.current?.payload;
  const displayedTimeframe = payload?.timeframe;
  const timeframeMismatch = Boolean(
    displayedTimeframe && displayedTimeframe !== timeframe,
  );

  const setSelectedTimeframe = (value: string) => {
    setTimeframe(value as PortfolioTimeframe);
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={query.isRefetching && !query.isLoading}
            tintColor={colors.amber}
            onRefresh={() => void query.refetch()}
          />
        }>
        <PageHeader
          eyebrow="Portfolio pulse"
          title="Portfolio"
          subtitle="Tracked positions and performance evidence. Account equity is not available in this view."
          right={
            query.isFetching && payload ? (
              <View accessibilityLabel="Syncing portfolio" style={styles.syncing}>
                <RefreshCw size={13} color={colors.amber} />
                <Text style={styles.syncingText}>Syncing</Text>
              </View>
            ) : null
          }
        />
        <SegmentedControl options={timeframes} value={timeframe} onChange={setSelectedTimeframe} />
        <ErrorBanner
          message={
            timeframeMismatch
              ? query.isError
                ? `Showing cached ${displayedTimeframe!.toUpperCase()} data; ${timeframe.toUpperCase()} is unavailable.`
                : `Showing ${displayedTimeframe!.toUpperCase()} data while ${timeframe.toUpperCase()} loads.`
              : query.isError
                ? mobileReadErrorMessage(query.error, "Portfolio")
                : ""
          }
        />
        {query.isError && !accessDenied && !needsPairing ? (
          <ActionButton
            label="Retry"
            onPress={() => void query.refetch()}
            icon={<RefreshCw size={16} color={colors.text} />}
          />
        ) : null}

        {session?.loading ? (
          <PortfolioSkeleton />
        ) : needsPairing ? (
          <View style={styles.pairing}>
            <EmptyState
              title="Pair this device"
              body="This mobile session is no longer available. Pair again before loading financial data."
            />
            <ActionButton
              label="Go to Pairing"
              tone="primary"
              onPress={() => router.push("/pairing")}
            />
          </View>
        ) : query.isLoading && !payload ? (
          <PortfolioSkeleton />
        ) : payload ? (
          <>
            <PortfolioMetrics
              currentSnapshot={payload.current_snapshot}
              summary={payload.summary}
              timeframe={payload.timeframe}
            />
            <Section
              title={`${payload.timeframe.toUpperCase()} realized performance`}
              right={
                <StatusBadge
                  label="Period exact"
                  tone="success"
                />
              }>
              <PerformanceChart
                currentSnapshot={payload.current_snapshot}
                series={payload.series}
              />
            </Section>
            <Section title="Positions" right={<StatusBadge label={`${payload.summary.open_positions} open`} />}>
              <PositionList positions={payload.positions} onPress={setSelectedPositionId} />
            </Section>
            <Section title="Allocation">
              <AllocationList allocation={payload.allocation} />
            </Section>
          </>
        ) : null}
      </ScrollView>
      <PositionSheet
        positionId={selectedPositionId}
        onDismiss={() => setSelectedPositionId(null)}
        onOpenDetails={(positionId) => {
          setSelectedPositionId(null);
          router.push(`/position/${encodeURIComponent(positionId)}`);
        }}
        onAdjustExit={(positionId) => {
          setSelectedPositionId(null);
          router.push(
            `/position/${encodeURIComponent(positionId)}?action=adjust`,
          );
        }}
        onClose={(positionId) => {
          setSelectedPositionId(null);
          router.push(
            `/position/${encodeURIComponent(positionId)}?action=close`,
          );
        }}
      />
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
    paddingBottom: 96,
    gap: spacing.md,
  },
  syncing: {
    minHeight: 36,
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.xs,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    borderWidth: 1,
    backgroundColor: colors.panelRaised,
    paddingHorizontal: spacing.sm,
  },
  syncingText: {
    color: colors.amber,
    fontSize: 10,
    fontWeight: "800",
  },
  pairing: {
    gap: spacing.md,
  },
});
