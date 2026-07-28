import { router } from "expo-router";
import React from "react";
import { Alert, RefreshControl, ScrollView, StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { buildInfo } from "@/src/buildInfo";
import { CockpitSummary } from "@/src/components/CockpitSummary";
import {
  ActionButton,
  EmptyState,
  ErrorBanner,
  LiveIndicator,
  PageHeader,
} from "@/src/components/ui";
import { useMobileSession } from "@/src/MobileSession";
import { colors, spacing } from "@/src/theme";

export default function CockpitScreen() {
  const {
    cockpit,
    connected,
    error,
    loading,
    locked,
    refreshCockpit,
    startBot,
    stopBot,
    token,
    unlockControls,
  } = useMobileSession();

  const confirmStart = () => {
    Alert.alert("Start bot?", "Start the paper/source loop from this mobile device.", [
      { text: "Cancel", style: "cancel" },
      { text: "Start", onPress: () => void startBot() },
    ]);
  };

  const confirmStop = () => {
    Alert.alert("Stop bot?", "Stop the paper/source loop and runtime source tasks.", [
      { text: "Cancel", style: "cancel" },
      { text: "Stop", style: "destructive", onPress: () => void stopBot() },
    ]);
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            tintColor={colors.amber}
            onRefresh={() => void refreshCockpit()}
          />
        }>
        <PageHeader
          eyebrow={connected ? "Realtime connected" : "Polling fallback"}
          title="Cockpit"
          subtitle={
            cockpit?.server_time
              ? `${buildInfo.label} v${buildInfo.version} | Updated ${new Date(cockpit.server_time).toLocaleTimeString()}`
              : `${buildInfo.label} v${buildInfo.version} | Waiting for mobile cockpit payload`
          }
          right={<LiveIndicator connected={connected} label={connected ? "Live" : "Poll"} />}
        />
        <ErrorBanner message={error} />
        {!token ? (
          <EmptyState
            title="Pair this device"
            body="Open Settings on desktop, start a mobile pairing code, then scan it from the Pair tab."
          />
        ) : (
          <CockpitSummary
            cockpit={cockpit}
            locked={locked}
            loading={loading}
            onRefresh={() => void refreshCockpit()}
            onUnlock={() => void unlockControls()}
            onStart={confirmStart}
            onStop={confirmStop}
          />
        )}
        {!token ? (
          <ActionButton
            label="Go to Pairing"
            tone="primary"
            onPress={() => router.push("/pairing")}
          />
        ) : null}
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
});
