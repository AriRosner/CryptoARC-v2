import { router, useLocalSearchParams } from "expo-router";
import { Activity, BellRing, Link2, ServerCog, Settings, Smartphone, Stethoscope } from "lucide-react-native";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { fetchMobileCockpit, setMobileKillSwitch } from "../../api";
import { useAppLock } from "../../components/system/AppLock";
import { ActionButton, DetailRow, EmptyState, ErrorBanner, MetricTile, PageHeader, Section, StatusBadge } from "../../components/ui";
import { useConnection } from "../../core/connectivity/ConnectionProvider";
import { useSession } from "../../core/session/SessionProvider";
import { sanitizeReason } from "../../security";
import { colors, spacing } from "../../theme";
import type { MobileCockpitPayload } from "../../types";
import { DeviceScreen } from "./DeviceScreen";
import { SettingsScreen } from "./SettingsScreen";

const EMERGENCY_ENABLE_REASON = "Emergency mobile kill-switch enable";

function MoreMenu() {
  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader eyebrow="Operator tools" title="More" subtitle="System safety, device, privacy, and recovery." />
        <Section title="Operations">
          <ActionButton label="System" onPress={() => router.push("/(tabs)/more?section=system")} icon={<ServerCog color={colors.text} size={16} />} />
          <ActionButton label="Device" onPress={() => router.push("/(tabs)/more?section=device")} icon={<Smartphone color={colors.text} size={16} />} />
          <ActionButton label="Settings" onPress={() => router.push("/(tabs)/more?section=settings")} icon={<Settings color={colors.text} size={16} />} />
        </Section>
        <Section title="Access and recovery">
          <ActionButton label="Pair Device" onPress={() => router.push("/pairing")} icon={<Link2 color={colors.text} size={16} />} />
          <ActionButton label="Diagnostics" onPress={() => router.push("/diagnostics")} icon={<Stethoscope color={colors.text} size={16} />} />
          <ActionButton label="Alerts" onPress={() => router.push("/(tabs)/alerts")} icon={<BellRing color={colors.text} size={16} />} />
        </Section>
      </ScrollView>
    </SafeAreaView>
  );
}

function SystemScreen() {
  const session = useSession();
  const connection = useConnection();
  const appLock = useAppLock();
  const [cockpit, setCockpit] = useState<MobileCockpitPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const activeRef = useRef(true);
  const reviewRef = useRef({ enabled: false, reason: "" });

  useEffect(() => () => {
    activeRef.current = false;
  }, []);

  const refresh = useCallback(async () => {
    if (!session.token || !session.apiBaseUrl || !connection.online) return;
    const generation = session.generation;
    setLoading(true);
    try {
      const payload = await fetchMobileCockpit(session.apiBaseUrl, session.token);
      if (!session.isCurrentGeneration(generation)) return;
      setCockpit(payload);
      setError("");
    } catch {
      if (session.isCurrentGeneration(generation)) setError("Unable to refresh system state.");
    } finally {
      if (session.isCurrentGeneration(generation)) setLoading(false);
    }
  }, [connection.online, session]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const killEnabled = Boolean(cockpit?.live.kill_switch_enabled);
  const sanitizedReason = sanitizeReason(reason);
  reviewRef.current = { enabled: killEnabled, reason: sanitizedReason };

  const changeKillSwitch = async (enabled: boolean) => {
    if (!session.token || !session.apiBaseUrl || !connection.online || loading) return;
    const auditReason = enabled
      ? sanitizedReason || EMERGENCY_ENABLE_REASON
      : sanitizedReason;
    if (!enabled && !auditReason) {
      Alert.alert("Reason required", "Enter a short reason before clearing the kill switch.");
      return;
    }
    const generation = session.generation;
    const binding = {
      actionType: enabled ? "kill_switch.enable" : "kill_switch.clear",
      entityId: "system-kill-switch",
      reviewKey: JSON.stringify([killEnabled, auditReason]),
    };
    const proof = await appLock.authorizeControl(binding);
    const currentReason = enabled
      ? reviewRef.current.reason || EMERGENCY_ENABLE_REASON
      : reviewRef.current.reason;
    if (
      !proof ||
      !activeRef.current ||
      !session.isCurrentGeneration(generation) ||
      reviewRef.current.enabled !== killEnabled ||
      currentReason !== auditReason ||
      !appLock.isControlAuthorizationCurrent(proof, binding)
    ) return;
    setLoading(true);
    try {
      if (
        !activeRef.current ||
        !session.isCurrentGeneration(generation) ||
        !appLock.isControlAuthorizationCurrent(proof, binding)
      ) return;
      const payload = await setMobileKillSwitch(
        session.apiBaseUrl,
        session.token,
        enabled,
        auditReason,
      );
      if (!activeRef.current || !session.isCurrentGeneration(generation)) return;
      setCockpit(payload);
      setError("");
    } catch {
      if (activeRef.current && session.isCurrentGeneration(generation)) setError("Kill-switch update failed.");
    } finally {
      if (activeRef.current && session.isCurrentGeneration(generation)) setLoading(false);
    }
  };
  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader eyebrow="Safety gates" title="System" subtitle="Readiness, exposure, and fresh-auth kill-switch controls." right={<StatusBadge label={killEnabled ? "Kill on" : "Kill off"} tone={killEnabled ? "danger" : "success"} />} />
        <ErrorBanner message={error} />
        {!session.token ? (
          <EmptyState title="Pair this device" body="A revocable mobile session is required for system status." />
        ) : !cockpit ? (
          <EmptyState title={connection.online ? "Loading system state" : "Offline"} body={connection.online ? "Waiting for current readiness data." : "Controls are unavailable offline and no action will be queued."} />
        ) : (
          <>
            <Section title="Gate overview">
              <View style={styles.metricGrid}>
                <MetricTile label="Readiness" value={cockpit.readiness.score ?? 0} />
                <MetricTile label="Source" value={cockpit.source.health_score ?? 0} />
                <MetricTile label="Live open" value={cockpit.open_risk.live_open_positions} />
              </View>
              <DetailRow label="Entries" value={cockpit.readiness.entries_allowed ? "Allowed" : "Blocked"} tone={cockpit.readiness.entries_allowed ? "success" : "danger"} />
            </Section>
            <Section title="Kill switch" right={<Activity color={killEnabled ? colors.rose : colors.emerald} size={18} />}>
              <Text style={styles.body}>Every change requires a fresh local unlock. Offline changes are never queued.</Text>
              <TextInput value={reason} onChangeText={setReason} placeholder="Reason for kill switch" placeholderTextColor={colors.faint} style={styles.input} />
              <ActionButton label="Enable Kill Switch" tone="danger" disabled={!connection.online || loading || killEnabled} onPress={() => void changeKillSwitch(true)} />
              <ActionButton label="Clear Kill Switch" disabled={!connection.online || loading || !killEnabled} onPress={() => void changeKillSwitch(false)} />
            </Section>
          </>
        )}
        <ActionButton label="Refresh System" disabled={!connection.online || loading} loading={loading} onPress={() => void refresh()} />
      </ScrollView>
    </SafeAreaView>
  );
}

export function MoreScreen() {
  const params = useLocalSearchParams<{ section?: string }>();
  if (params.section === "system") return <SystemScreen />;
  if (params.section === "device") return <DeviceScreen />;
  if (params.section === "settings") return <SettingsScreen />;
  return <MoreMenu />;
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.background },
  content: { gap: spacing.md, padding: spacing.lg, paddingBottom: 96 },
  metricGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  body: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  input: {
    minHeight: 46,
    borderColor: colors.borderStrong,
    borderRadius: 8,
    borderWidth: 1,
    backgroundColor: colors.black,
    color: colors.text,
    paddingHorizontal: spacing.md,
  },
});
