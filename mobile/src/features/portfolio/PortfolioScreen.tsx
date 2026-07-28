import { router } from "expo-router";
import { RefreshCw } from "lucide-react-native";
import React, { useEffect, useRef, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ActionButton, ErrorBanner, PageHeader, Section, SegmentedControl, StatusBadge } from "../../components/ui";
import { mobileReadErrorMessage } from "../../core/api/authenticatedRead";
import { MobileApiError } from "../../core/api/errors";
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
  const lastPayloadRef = useRef<PortfolioPayload | undefined>(undefined);
  useEffect(() => {
    if (query.data) lastPayloadRef.current = query.data;
  }, [query.data]);
  const accessDenied =
    query.error instanceof MobileApiError &&
    (query.error.status === 401 || query.error.status === 403);
  const payload = accessDenied ? undefined : query.data ?? lastPayloadRef.current;
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
              <View style={styles.syncing}>
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
        {query.isError ? (
          <ActionButton
            label="Retry"
            onPress={() => void query.refetch()}
            icon={<RefreshCw size={16} color={colors.text} />}
          />
        ) : null}

        {query.isLoading && !payload ? (
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
        onAdjustExit={() => undefined}
        onClose={() => undefined}
      />
    </SafeAreaView>
  );
}

function PortfolioSkeleton() {
  return (
    <View accessibilityLabel="Loading portfolio" style={styles.skeletonStack}>
      <View style={styles.skeletonMetrics}>
        {Array.from({ length: 4 }, (_, index) => (
          <View
            key={index}
            testID="portfolio-metric-skeleton"
            style={[styles.skeleton, styles.skeletonMetric]}
          />
        ))}
      </View>
      <View style={[styles.skeleton, styles.skeletonChart]} />
      <View style={[styles.skeleton, styles.skeletonRow]} />
      <View style={[styles.skeleton, styles.skeletonRow]} />
    </View>
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
  skeletonStack: {
    gap: spacing.md,
  },
  skeletonMetrics: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  skeleton: {
    backgroundColor: colors.panelRaised,
    borderRadius: radius.md,
  },
  skeletonMetric: {
    flexBasis: "47%",
    flexGrow: 1,
    height: 92,
  },
  skeletonChart: {
    height: 220,
  },
  skeletonRow: {
    height: 64,
  },
});
