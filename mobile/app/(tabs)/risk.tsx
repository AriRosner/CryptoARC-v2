import { Activity, ShieldAlert, ShieldCheck, ShieldX } from "lucide-react-native";
import React, { useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ActionButton, DetailRow, EmptyState, ErrorBanner, MetricTile, PageHeader, ProgressBar, Section, StatusBadge } from "@/src/components/ui";
import { useMobileSession } from "@/src/MobileSession";
import { colors, spacing } from "@/src/theme";

export default function RiskScreen() {
  const { token, cockpit, locked, loading, error, unlockControls, setKillSwitch } = useMobileSession();
  const [reason, setReason] = useState("");
  const killEnabled = Boolean(cockpit?.live.kill_switch_enabled);
  const readinessScore = Number(cockpit?.readiness.score ?? 0);
  const sourceScore = Number(cockpit?.source.health_score ?? 0);
  const blockerCount = (cockpit?.live.blockers.length ?? 0) + (cockpit?.readiness.blockers.length ?? 0) + (cockpit?.open_risk.risk_blockers.length ?? 0);

  const confirmKillSwitch = (enabled: boolean) => {
    if (enabled && !reason.trim()) {
      Alert.alert("Reason required", "Enter a short reason before enabling the kill switch.");
      return;
    }
    Alert.alert(enabled ? "Enable kill switch?" : "Clear kill switch?", enabled ? "This blocks new live entries." : "Other live gates still apply.", [
      { text: "Cancel", style: "cancel" },
      { text: enabled ? "Enable" : "Clear", style: enabled ? "destructive" : "default", onPress: () => void setKillSwitch(enabled, reason) },
    ]);
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader
          eyebrow="Safety gates"
          title="Risk"
          subtitle="Open exposure, live blockers, and the guarded kill switch."
          right={cockpit ? <StatusBadge label={killEnabled ? "Kill on" : "Kill off"} tone={killEnabled ? "danger" : "success"} /> : null}
        />
        <ErrorBanner message={error} />
        {!token || !cockpit ? (
          <EmptyState title="No risk payload" body="Pair this device and refresh the cockpit to view risk state." />
        ) : (
          <>
            <Section title="Gate Overview" right={<StatusBadge label={`${blockerCount} blockers`} tone={blockerCount ? "danger" : "success"} />}>
              <View style={styles.scoreStack}>
                <View style={styles.scoreRow}>
                  <Text style={styles.scoreLabel}>Readiness</Text>
                  <Text style={styles.scoreValue}>{readinessScore}</Text>
                </View>
                <ProgressBar value={readinessScore} tone={readinessScore >= 75 ? "success" : readinessScore >= 50 ? "warning" : "danger"} />
                <View style={styles.scoreRow}>
                  <Text style={styles.scoreLabel}>Source health</Text>
                  <Text style={styles.scoreValue}>{sourceScore}</Text>
                </View>
                <ProgressBar value={sourceScore} tone={sourceScore >= 75 ? "success" : sourceScore >= 50 ? "warning" : "danger"} />
              </View>
              <DetailRow label="Entries" value={cockpit.readiness.entries_allowed ? "Allowed" : "Blocked"} tone={cockpit.readiness.entries_allowed ? "success" : "danger"} />
              <DetailRow label="Source" value={cockpit.source.status_message || cockpit.source.status || "Unknown"} tone={cockpit.source.live_entry_blocked ? "danger" : "info"} />
            </Section>

            <Section title="Open Risk">
              <View style={styles.metricGrid}>
                <MetricTile label="Paper open" value={cockpit.open_risk.paper_open_positions} />
                <MetricTile label="Live open" value={cockpit.open_risk.live_open_positions} />
                <MetricTile label="Audits" value={cockpit.open_risk.unresolved_live_audits} tone={cockpit.open_risk.unresolved_live_audits ? "danger" : "success"} />
                <MetricTile label="Intents" value={cockpit.open_risk.active_live_intents} />
              </View>
            </Section>

            <Section title="Kill Switch" right={locked ? <StatusBadge label="Locked" tone="warning" /> : <StatusBadge label="Guarded" tone="success" />}>
              <View style={[styles.killPanel, killEnabled && styles.killPanelActive]}>
                <View style={styles.killIcon}>
                  {killEnabled ? <ShieldX size={22} color={colors.rose} /> : <Activity size={22} color={colors.emerald} />}
                </View>
                <View style={styles.killCopy}>
                  <Text style={styles.killTitle}>{killEnabled ? "New live entries blocked" : "Kill switch is clear"}</Text>
                  <Text style={styles.killBody}>{killEnabled ? "The cockpit will continue monitoring while entry actions stay blocked." : "Use this only when the operator needs an immediate stop gate."}</Text>
                </View>
              </View>
              <TextInput
                value={reason}
                onChangeText={setReason}
                placeholder="Reason for kill switch"
                placeholderTextColor={colors.faint}
                style={styles.input}
              />
              {locked ? (
                <ActionButton label="Unlock Controls" tone="primary" onPress={() => void unlockControls()} icon={<ShieldCheck size={16} color={colors.text} />} />
              ) : null}
              <ActionButton
                label="Enable Kill Switch"
                tone="danger"
                onPress={() => confirmKillSwitch(true)}
                disabled={loading || locked}
                icon={<ShieldAlert size={16} color={colors.text} />}
              />
              <ActionButton label="Clear Kill Switch" onPress={() => confirmKillSwitch(false)} disabled={loading || locked} />
            </Section>

            <Section title="Live Blockers">
              {cockpit.live.blockers.length ? (
                cockpit.live.blockers.map((blocker) => (
                  <Text key={blocker} style={styles.blocker}>
                    {blocker}
                  </Text>
                ))
              ) : (
                <Text style={styles.muted}>No mobile-visible live blockers.</Text>
              )}
              {cockpit.open_risk.risk_blockers.map((blocker) => (
                <Text key={blocker} style={styles.blocker}>
                  {blocker}
                </Text>
              ))}
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
  metricGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  scoreStack: {
    gap: 8,
  },
  scoreRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  scoreLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  scoreValue: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "900",
  },
  killPanel: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: 8,
    backgroundColor: colors.deep,
    padding: spacing.md,
  },
  killPanelActive: {
    borderColor: colors.rose,
    backgroundColor: colors.roseSoft,
  },
  killIcon: {
    alignItems: "center",
    justifyContent: "center",
    height: 44,
    width: 44,
    borderRadius: 8,
    backgroundColor: colors.panelRaised,
  },
  killCopy: {
    flex: 1,
    gap: 4,
  },
  killTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "900",
  },
  killBody: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
  input: {
    minHeight: 46,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: 8,
    backgroundColor: colors.black,
    color: colors.text,
    fontSize: 13,
    paddingHorizontal: spacing.md,
  },
  blocker: {
    color: colors.rose,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 18,
  },
  muted: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
});
