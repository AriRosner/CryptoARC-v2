import { Lock, LogOut, RefreshCw, Server, ShieldCheck, Unlock, Wifi } from "lucide-react-native";
import React from "react";
import { Alert, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ActionButton, DetailRow, EmptyState, ErrorBanner, LiveIndicator, MetricTile, PageHeader, Section, StatusBadge } from "@/src/components/ui";
import { buildInfo } from "@/src/buildInfo";
import { useMobileSession } from "@/src/MobileSession";
import { colors, spacing } from "@/src/theme";

function formatTime(value?: string) {
  if (!value) return "Never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unknown" : date.toLocaleString();
}

export default function DeviceScreen() {
  const { token, device, apiBaseUrl, cockpit, connected, locked, loading, error, unlockControls, refreshCockpit, clearSession } = useMobileSession();
  const telegram = cockpit?.alerts.telegram ?? {};

  const confirmDisconnect = () => {
    Alert.alert("Disconnect device?", "This removes the local mobile token. Revoke the device from desktop Settings as well.", [
      { text: "Cancel", style: "cancel" },
      { text: "Disconnect", style: "destructive", onPress: () => void clearSession() },
    ]);
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader
          eyebrow="Secure session"
          title="Device"
          subtitle={`${buildInfo.label} v${buildInfo.version} (${buildInfo.date})`}
          right={<LiveIndicator connected={connected} label={connected ? "Live" : "Offline"} />}
        />
        <ErrorBanner message={error} />
        {!token ? (
          <EmptyState title="No mobile session" body="Pair this device from the Pair tab to create a revocable token." />
        ) : (
          <>
            <Section title="Paired Device" right={<StatusBadge label={locked ? "Locked" : "Unlocked"} tone={locked ? "warning" : "success"} />}>
              <Text style={styles.name}>{device?.name || "Mobile device"}</Text>
              <View style={styles.metricGrid}>
                <MetricTile label="Tunnel" value={connected ? "Online" : "Offline"} tone={connected ? "success" : "warning"} detail={cockpit?.connection.api || "API"} />
                <MetricTile label="Socket" value={cockpit?.connection.websocket || "Unknown"} tone={connected ? "success" : "warning"} detail="realtime" />
                <MetricTile label="Scopes" value={(device?.scopes ?? []).length || 0} detail="mobile token" />
              </View>
              <DetailRow label="API URL" value={apiBaseUrl || "Not set"} tone="info" />
              <DetailRow label="App build" value={`${buildInfo.label} v${buildInfo.version} / Android ${buildInfo.androidVersionCode}`} tone="success" />
              <DetailRow label="Last seen" value={formatTime(device?.last_seen_at)} />
              <DetailRow label="Expires" value={formatTime(device?.expires_at)} />
              <DetailRow label="Scopes" value={(device?.scopes ?? []).join(", ") || "monitor"} />
            </Section>

            <Section title="Controls" right={<ShieldCheck size={16} color={locked ? colors.amber : colors.emerald} />}>
              <ActionButton
                label={locked ? "Unlock Controls" : "Controls Unlocked"}
                tone={locked ? "primary" : "secondary"}
                onPress={() => void unlockControls()}
                disabled={!locked}
                icon={locked ? <Lock size={16} color={colors.text} /> : <Unlock size={16} color={colors.text} />}
              />
              <ActionButton label="Refresh Cockpit" onPress={() => void refreshCockpit()} loading={loading} icon={<RefreshCw size={16} color={colors.text} />} />
              <ActionButton label="Disconnect" tone="danger" onPress={confirmDisconnect} icon={<LogOut size={16} color={colors.text} />} />
            </Section>

            <Section title="Diagnostics">
              <View style={styles.diagnosticRow}>
                <View style={styles.diagnosticIcon}>
                  <Server size={18} color={colors.blue} />
                </View>
                <View style={styles.diagnosticCopy}>
                  <Text style={styles.body}>Backend {cockpit?.connection.state || "unknown"}</Text>
                  <Text style={styles.subtle}>Private tunnel required: {cockpit?.connection.private_tunnel_required ? "yes" : "unknown"}</Text>
                </View>
              </View>
              <View style={styles.diagnosticRow}>
                <View style={styles.diagnosticIcon}>
                  <Wifi size={18} color={telegram.telegram_configured ? colors.emerald : colors.amber} />
                </View>
                <View style={styles.diagnosticCopy}>
                  <Text style={styles.body}>Telegram {telegram.telegram_configured ? "configured" : "not configured"}</Text>
                  <Text style={styles.subtle}>Critical out-of-app alerts remain routed through Telegram.</Text>
                </View>
              </View>
            </Section>
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
  name: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "900",
  },
  metricGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  body: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 19,
  },
  subtle: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
  diagnosticRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.md,
  },
  diagnosticIcon: {
    alignItems: "center",
    justifyContent: "center",
    height: 40,
    width: 40,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.panelRaised,
  },
  diagnosticCopy: {
    flex: 1,
    gap: 2,
  },
});
