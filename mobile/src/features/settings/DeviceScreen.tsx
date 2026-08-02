import { router } from "expo-router";
import { Link2, LogOut, Stethoscope } from "lucide-react-native";
import React from "react";
import { Alert, ScrollView, StyleSheet, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { buildInfo } from "../../buildInfo";
import { ActionButton, DetailRow, EmptyState, ErrorBanner, PageHeader, Section, StatusBadge } from "../../components/ui";
import { useConnection } from "../../core/connectivity/ConnectionProvider";
import { useSession } from "../../core/session/SessionProvider";
import { colors, spacing } from "../../theme";

function formatTime(value?: string) {
  if (!value) return "Never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unknown" : date.toLocaleString();
}

export function DeviceScreen() {
  const session = useSession();
  const connection = useConnection();
  const confirmDisconnect = () => {
    Alert.alert(
      "Disconnect device?",
      "This removes the local mobile token. Revoke the device from desktop Settings as well.",
      [
        { text: "Cancel", style: "cancel" },
        { text: "Disconnect", style: "destructive", onPress: () => void session.clearSession() },
      ],
    );
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader
          eyebrow="Revocable mobile session"
          title="Device"
          subtitle={`${buildInfo.label} v${buildInfo.version} (${buildInfo.date})`}
          right={<StatusBadge label={connection.online ? "Online" : "Offline"} tone={connection.online ? "success" : "warning"} />}
        />
        <ErrorBanner message={session.error} />
        {!session.token ? (
          <>
            <EmptyState title="No mobile session" body="Pair this phone to create a scoped, revocable token." />
            <ActionButton label="Pair Device" tone="primary" onPress={() => router.push("/pairing")} icon={<Link2 color={colors.text} size={16} />} />
          </>
        ) : (
          <>
            <Section title="Paired device" right={<StatusBadge label={session.locked ? "Controls locked" : "Unlocked"} tone={session.locked ? "warning" : "success"} />}>
              <Text style={styles.name}>{session.device?.name || "Mobile device"}</Text>
              <DetailRow label="API URL" value={session.apiBaseUrl} tone="info" />
              <DetailRow label="Last seen" value={formatTime(session.device?.last_seen_at)} />
              <DetailRow label="Expires" value={formatTime(session.device?.expires_at)} />
              <DetailRow label="Scopes" value={(session.device?.scopes ?? []).join(", ") || "monitor"} />
              <DetailRow label="Build" value={`${buildInfo.version} / Android ${buildInfo.androidVersionCode}`} />
            </Section>
            <Section title="Session actions">
              <ActionButton label="Open Diagnostics" onPress={() => router.push("/diagnostics")} icon={<Stethoscope color={colors.text} size={16} />} />
              <ActionButton label="Disconnect" tone="danger" onPress={confirmDisconnect} icon={<LogOut color={colors.text} size={16} />} />
            </Section>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.background },
  content: { gap: spacing.md, padding: spacing.lg, paddingBottom: 96 },
  name: { color: colors.text, fontSize: 18, fontWeight: "900" },
});
