import { RefreshCw } from "lucide-react-native";
import React, { useEffect, useMemo, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { FeedList, filterFeedEvents, summarizeFeed } from "@/src/components/FeedList";
import { ActionButton, EmptyState, ErrorBanner, MetricTile, PageHeader, SegmentedControl, StatusBadge } from "@/src/components/ui";
import { useMobileSession } from "@/src/MobileSession";
import { colors, spacing } from "@/src/theme";

const levels = [
  { label: "all", value: "", tone: "warning" as const },
  { label: "danger", value: "danger", tone: "danger" as const },
  { label: "warning", value: "warning", tone: "warning" as const },
  { label: "info", value: "info", tone: "info" as const },
];

export default function FeedScreen() {
  const { token, feed, cockpit, loading, error, loadFeed } = useMobileSession();
  const [level, setLevel] = useState("");

  useEffect(() => {
    if (token) void loadFeed();
  }, [loadFeed, token]);

  const sourceEvents = feed?.events ?? cockpit?.alerts.latest ?? [];
  const events = useMemo(() => filterFeedEvents(sourceEvents, level, ""), [sourceEvents, level]);
  const summary = useMemo(() => summarizeFeed(sourceEvents), [sourceEvents]);

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader eyebrow="Operator events" title="Feed" subtitle="Warnings, recoverable items, and mobile-visible audit trail." right={<StatusBadge label={`${events.length} shown`} tone="neutral" />} />
        <ErrorBanner message={error} />
        {!token ? (
          <EmptyState title="No paired device" body="Pair this Android device before loading the event feed." />
        ) : (
          <>
            <View style={styles.metricGrid}>
              <MetricTile label="Danger" value={summary.danger} tone={summary.danger ? "danger" : "neutral"} />
              <MetricTile label="Warning" value={summary.warning} tone={summary.warning ? "warning" : "neutral"} />
              <MetricTile label="Info" value={summary.info} />
            </View>
            <SegmentedControl options={levels} value={level} onChange={setLevel} />
            <ActionButton label="Refresh Feed" onPress={() => void loadFeed(level)} loading={loading} icon={<RefreshCw size={16} color={colors.text} />} />
            <FeedList events={events} />
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
  metricGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
});
