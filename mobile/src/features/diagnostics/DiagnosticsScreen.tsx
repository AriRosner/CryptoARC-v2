import { useQuery } from "@tanstack/react-query";
import { Download, RefreshCw, Stethoscope } from "lucide-react-native";
import React, { useState } from "react";
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ActionButton,
  DetailRow,
  EmptyState,
  ErrorBanner,
  PageHeader,
  Section,
  StatusBadge,
  type Tone,
} from "../../components/ui";
import { DiagnosticsSkeleton } from "../../components/skeletons/DiagnosticsSkeleton";
import { authenticatedRead } from "../../core/api/authenticatedRead";
import { useConnection } from "../../core/connectivity/ConnectionProvider";
import { useSession } from "../../core/session/SessionProvider";
import { loadVerifiedSnapshot } from "../../core/storage/snapshot";
import { colors, radius, spacing } from "../../theme";
import { exportDiagnostics, fetchDiagnostics } from "./api";
import { redactDiagnosticPayload } from "./redaction";
import { shareDiagnosticArtifact } from "./artifact";
import { applyClientDiagnosticObservations } from "./observations";
import type {
  MobileDiagnosticsPayload,
  MobileDiagnosticStatus,
} from "./types";

interface DiagnosticsScreenProps {
  diagnostics: MobileDiagnosticsPayload | null;
  loading: boolean;
  error: string;
  exporting: boolean;
  onRefresh(): void;
  onExport(): void;
}

function statusTone(status: MobileDiagnosticStatus): Tone {
  if (status === "healthy") return "success";
  if (status === "warning") return "warning";
  if (status === "blocked") return "danger";
  return "neutral";
}

export function DiagnosticsScreen({
  diagnostics,
  loading,
  error,
  exporting,
  onRefresh,
  onExport,
}: DiagnosticsScreenProps) {
  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader
          eyebrow="Read-only recovery"
          title="Diagnostics"
          subtitle="Freshness-aware operator checks"
          right={
            <View style={styles.headerStatus}>
              <Stethoscope color={colors.amber} size={24} />
              {loading && diagnostics ? (
                <Text accessibilityLabel="Syncing diagnostics" style={styles.syncing}>Syncing</Text>
              ) : null}
            </View>
          }
        />
        <ErrorBanner message={error} />
        {loading && !diagnostics ? (
          <DiagnosticsSkeleton />
        ) : diagnostics ? (
          <>
            <Section
              title="System checks"
              right={
                <StatusBadge
                  label={diagnostics.freshness.status}
                  tone={
                    diagnostics.freshness.status === "fresh"
                      ? "success"
                      : diagnostics.freshness.status === "stale"
                        ? "warning"
                        : "neutral"
                  }
                />
              }>
              {diagnostics.checks.map((check) => (
                <View key={check.id} style={styles.check}>
                  <View style={styles.checkHeader}>
                    <Text style={styles.checkLabel}>{check.label}</Text>
                    <StatusBadge
                      label={check.status}
                      tone={statusTone(check.status)}
                    />
                  </View>
                  <Text style={styles.detail}>{check.detail}</Text>
                </View>
              ))}
            </Section>
            <Section title="Recovery center">
              {diagnostics.recovery_actions.map((action) => (
                <DetailRow
                  key={action.id}
                  label={action.label}
                  value={action.detail}
                  tone={action.enabled ? "info" : "neutral"}
                />
              ))}
            </Section>
          </>
        ) : (
          <EmptyState
            title="Diagnostics unavailable"
            body="Reconnect to the trusted backend and refresh."
          />
        )}
        <View style={styles.actions}>
          <ActionButton
            accessibilityLabel="Refresh diagnostics"
            icon={<RefreshCw color={colors.text} size={17} />}
            label="Refresh"
            onPress={onRefresh}
          />
          <ActionButton
            accessibilityLabel="Export redacted diagnostics"
            disabled={!diagnostics || exporting}
            icon={<Download color={colors.text} size={17} />}
            label={exporting ? "Exporting" : "Export redacted diagnostics"}
            loading={exporting}
            onPress={onExport}
            tone="primary"
          />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

export function DiagnosticsFeatureScreen() {
  const session = useSession();
  const connection = useConnection();
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const query = useQuery({
    queryKey: ["mobile", "diagnostics", session.generation],
    enabled: Boolean(session.token && session.apiBaseUrl),
    queryFn: async () => {
      const apiStartedAt = new Date().toISOString();
      const payload = await authenticatedRead(session, () =>
        fetchDiagnostics({
          apiBaseUrl: session.apiBaseUrl,
          token: session.token,
        }),
      );
      const apiReceivedAt = new Date().toISOString();
      let verifiedSnapshot = null;
      try {
        verifiedSnapshot = await loadVerifiedSnapshot();
      } catch {
        verifiedSnapshot = null;
      }
      return applyClientDiagnosticObservations(payload, {
        apiBaseUrl: session.apiBaseUrl,
        apiStartedAt,
        apiReceivedAt,
        now: apiReceivedAt,
        online: connection.online,
        realtime: connection.realtime,
        verifiedSnapshot,
      });
    },
  });

  const exportReport = async () => {
    setExporting(true);
    setExportError("");
    try {
      const apiStartedAt = new Date().toISOString();
      const payload = await authenticatedRead(session, () =>
        exportDiagnostics({
          apiBaseUrl: session.apiBaseUrl,
          token: session.token,
        }),
      );
      const apiReceivedAt = new Date().toISOString();
      let verifiedSnapshot = null;
      try {
        verifiedSnapshot = await loadVerifiedSnapshot();
      } catch {
        verifiedSnapshot = null;
      }
      const observed = applyClientDiagnosticObservations(payload, {
        apiBaseUrl: session.apiBaseUrl,
        apiStartedAt,
        apiReceivedAt,
        now: apiReceivedAt,
        online: connection.online,
        realtime: connection.realtime,
        verifiedSnapshot,
      });
      const redacted = redactDiagnosticPayload({
        ...observed,
        exported_at: payload.exported_at,
      });
      await shareDiagnosticArtifact(redacted);
    } catch {
      setExportError("Redacted diagnostic export failed.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <DiagnosticsScreen
      diagnostics={query.data ?? null}
      loading={query.isLoading}
      error={
        exportError ||
        (query.isError ? "Diagnostics unavailable" : "")
      }
      exporting={exporting}
      onRefresh={() => void query.refetch()}
      onExport={() => void exportReport()}
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
  check: {
    minHeight: 68,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    paddingVertical: spacing.xs,
    gap: 5,
  },
  checkHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  checkLabel: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "900",
  },
  detail: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 16,
  },
  actions: {
    gap: spacing.sm,
  },
});
