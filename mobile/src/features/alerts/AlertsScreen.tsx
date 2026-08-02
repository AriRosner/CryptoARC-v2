import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Check, RefreshCw } from "lucide-react-native";
import React, { useMemo, useState } from "react";
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
  ErrorBanner,
  PageHeader,
  StatusBadge,
} from "../../components/ui";
import { AlertsSkeleton } from "../../components/skeletons/AlertsSkeleton";
import { authenticatedRead } from "../../core/api/authenticatedRead";
import { useSession } from "../../core/session/SessionProvider";
import { colors, radius, spacing } from "../../theme";
import { acknowledgeAlert, fetchAlerts } from "./api";
import type { MobileAlert } from "./types";

interface AlertsScreenProps {
  alerts: MobileAlert[];
  loading: boolean;
  error: string;
  onRefresh(): void;
  onAcknowledge(eventId: string): void;
}

function alertTone(severity: MobileAlert["severity"]) {
  if (severity === "danger" || severity === "error") return "danger";
  if (severity === "warning") return "warning";
  return "info";
}

export function AlertsScreen({
  alerts,
  loading,
  error,
  onRefresh,
  onAcknowledge,
}: AlertsScreenProps) {
  const uniqueAlerts = useMemo(
    () =>
      Array.from(
        new Map(alerts.map((item) => [item.event_id, item])).values(),
      ),
    [alerts],
  );

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader
          eyebrow="Operator attention"
          title="Alerts"
          subtitle="Critical events and acknowledgements"
          right={
            <View style={styles.headerStatus}>
              <BellRing color={colors.amber} size={24} />
              {loading && uniqueAlerts.length > 0 ? (
                <Text accessibilityLabel="Syncing alerts" style={styles.syncing}>Syncing</Text>
              ) : null}
            </View>
          }
        />
        <ErrorBanner message={error} />
        {loading && uniqueAlerts.length === 0 ? (
          <AlertsSkeleton />
        ) : uniqueAlerts.length === 0 ? (
          <EmptyState
            title="No active alerts"
            body="New warning and critical events will appear here."
          />
        ) : (
          <View style={styles.stack}>
            {uniqueAlerts.map((item) => (
              <View key={item.event_id} style={styles.alert}>
                <View style={styles.alertHeader}>
                  <View style={styles.alertCopy}>
                    <Text style={styles.alertTitle}>{item.title}</Text>
                    <Text style={styles.subsystem}>{item.subsystem}</Text>
                  </View>
                  <StatusBadge
                    label={item.severity}
                    tone={alertTone(item.severity)}
                  />
                </View>
                <Text style={styles.summary}>{item.summary}</Text>
                <Text style={styles.timestamp}>
                  {new Date(item.created_at).toLocaleString()}
                </Text>
                {item.acknowledged ? (
                  <View accessibilityLabel={`${item.title} acknowledged`} style={styles.acknowledged}>
                    <Check color={colors.emerald} size={16} />
                    <Text style={styles.acknowledgedText}>Acknowledged</Text>
                  </View>
                ) : (
                  <Pressable
                    accessibilityLabel={`Acknowledge ${item.title.toLowerCase()}`}
                    accessibilityRole="button"
                    onPress={() => onAcknowledge(item.event_id)}
                    style={({ pressed }) => [
                      styles.ackButton,
                      pressed && styles.pressed,
                    ]}>
                    <Check color={colors.text} size={17} />
                    <Text style={styles.ackButtonText}>Acknowledge</Text>
                  </Pressable>
                )}
              </View>
            ))}
          </View>
        )}
        <ActionButton
          accessibilityLabel="Refresh alerts"
          icon={<RefreshCw color={colors.text} size={17} />}
          label="Refresh"
          onPress={onRefresh}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

export function AlertsFeatureScreen() {
  const session = useSession();
  const queryClient = useQueryClient();
  const [mutationError, setMutationError] = useState("");
  const query = useQuery({
    queryKey: ["mobile", "alerts", session.generation],
    enabled: Boolean(session.token && session.apiBaseUrl),
    queryFn: () =>
      authenticatedRead(session, () =>
        fetchAlerts({
          apiBaseUrl: session.apiBaseUrl,
          token: session.token,
        }),
      ),
  });

  const acknowledge = async (eventId: string) => {
    setMutationError("");
    try {
      await authenticatedRead(session, () =>
        acknowledgeAlert(eventId, {
          apiBaseUrl: session.apiBaseUrl,
          token: session.token,
        }),
      );
      await queryClient.invalidateQueries({ queryKey: ["mobile", "alerts"] });
    } catch {
      setMutationError("Alert acknowledgement failed.");
    }
  };

  return (
    <AlertsScreen
      alerts={query.data?.alerts ?? []}
      loading={query.isLoading}
      error={
        mutationError || (query.isError ? "Unable to load alerts." : "")
      }
      onRefresh={() => void query.refetch()}
      onAcknowledge={(eventId) => void acknowledge(eventId)}
    />
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
  headerStatus: {
    alignItems: "center",
    gap: spacing.xs,
  },
  syncing: {
    color: colors.amber,
    fontSize: 10,
    fontWeight: "800",
  },
  alert: {
    minHeight: 150,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: colors.panel,
    padding: spacing.md,
    gap: spacing.sm,
  },
  alertHeader: {
    alignItems: "flex-start",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  alertCopy: {
    flex: 1,
    gap: 4,
  },
  alertTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: "900",
  },
  subsystem: {
    color: colors.faint,
    fontSize: 10,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  summary: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
  timestamp: {
    color: colors.faint,
    fontSize: 10,
  },
  acknowledged: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.xs,
    minHeight: 44,
  },
  acknowledgedText: {
    color: colors.emerald,
    fontSize: 12,
    fontWeight: "800",
  },
  ackButton: {
    alignItems: "center",
    alignSelf: "flex-start",
    flexDirection: "row",
    gap: spacing.xs,
    minHeight: 44,
    borderRadius: radius.sm,
    backgroundColor: colors.panelRaised,
    paddingHorizontal: spacing.md,
  },
  ackButtonText: {
    color: colors.text,
    fontSize: 12,
    fontWeight: "900",
  },
  pressed: {
    opacity: 0.8,
  },
});
