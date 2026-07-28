import { useNetInfo } from "@react-native-community/netinfo";
import * as LocalAuthentication from "expo-local-authentication";
import { router } from "expo-router";
import { ArrowLeft } from "lucide-react-native";
import React, { useEffect, useRef, useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { HoldToConfirm } from "../../components/actions/HoldToConfirm";
import {
  ActionButton,
  DetailRow,
  EmptyState,
  PageHeader,
  Section,
  StatusBadge,
} from "../../components/ui";
import { MobileApiError } from "../../core/api/errors";
import { useOptionalSession } from "../../core/session/SessionProvider";
import { colors, radius, spacing } from "../../theme";
import {
  approveTrade,
  createMobileIdempotencyKey,
  fetchAction,
} from "./api";
import { ActionStatus } from "./ActionStatus";
import { BoundedTradeForm } from "./BoundedTradeForm";
import { useTradeQuery } from "./queries";
import { RiskEscalation } from "./RiskEscalation";
import type {
  GuardedApprovalInput,
  MobileActionReceipt,
  MobileTradeDetail,
  MobileTradeDraft,
} from "./types";

export interface GuardedTradeApprovalProps {
  trade: MobileTradeDetail;
  initialDraft: MobileTradeDraft;
  online: boolean;
  submitApproval(input: GuardedApprovalInput): Promise<MobileActionReceipt>;
  reconcileAction?(actionId: string): Promise<MobileActionReceipt>;
  createIdempotencyKey?(): string;
}

function ambiguousReceipt(actionId: string): MobileActionReceipt {
  const now = new Date().toISOString();
  return {
    action_id: actionId,
    status: "verifying",
    submitted_at: now,
    updated_at: now,
    operator_message: "Verifying outcome",
    reconcile_after_ms: 250,
  };
}

export function GuardedTradeApproval({
  trade,
  initialDraft,
  online,
  submitApproval,
  reconcileAction,
  createIdempotencyKey = createMobileIdempotencyKey,
}: GuardedTradeApprovalProps) {
  const [draft, setDraft] = useState(initialDraft);
  const [receipt, setReceipt] = useState<MobileActionReceipt | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const idempotencyKey = useRef("");

  useEffect(() => {
    setDraft(initialDraft);
    setReceipt(null);
    setError("");
    inFlight.current = false;
    idempotencyKey.current = "";
  }, [initialDraft, trade.id, trade.version]);

  useEffect(() => {
    if (
      !receipt?.action_id ||
      !["pending", "verifying"].includes(receipt.status) ||
      !reconcileAction
    ) {
      return;
    }
    let active = true;
    const timer = setTimeout(() => {
      void reconcileAction(receipt.action_id).then(
        (next) => {
          if (active) setReceipt(next);
        },
        () => {
          // The existing receipt remains authoritative until reconciliation succeeds.
        },
      );
    }, Math.max(250, Math.min(30000, receipt.reconcile_after_ms)));
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [receipt, reconcileAction]);

  const disabled =
    !online ||
    !trade.allowed_actions.approve ||
    trade.blockers.length > 0 ||
    busy ||
    Boolean(receipt && ["pending", "verifying"].includes(receipt.status));

  const authorize = async (escalationAcknowledged: boolean) => {
    if (disabled || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const biometric = await LocalAuthentication.authenticateAsync({
        promptMessage: "Approve prepared CryptoARC trade",
        cancelLabel: "Cancel",
        disableDeviceFallback: true,
      });
      if (!biometric.success) {
        idempotencyKey.current = "";
        return;
      }
      if (!idempotencyKey.current) {
        idempotencyKey.current = createIdempotencyKey();
      }
      const next = await submitApproval({
        expectedVersion: trade.version,
        draft,
        escalationAcknowledged,
        idempotencyKey: idempotencyKey.current,
      });
      setReceipt(next);
    } catch (caught) {
      if (
        caught instanceof MobileApiError &&
        caught.category === "ambiguous_outcome"
      ) {
        setReceipt(ambiguousReceipt(idempotencyKey.current));
      } else {
        idempotencyKey.current = "";
        setError(
          caught instanceof Error ? caught.message : "Trade approval failed",
        );
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <View style={styles.approval}>
      <BoundedTradeForm
        draft={draft}
        limits={trade.limits}
        disabled={disabled}
        onChange={setDraft}
      />
      <RiskEscalation reasons={trade.escalation_reasons} />
      {!online ? (
        <Text style={styles.blocker}>Offline actions are disabled.</Text>
      ) : null}
      {trade.blockers.map((blocker) => (
        <Text key={blocker} style={styles.blocker}>
          {blocker}
        </Text>
      ))}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {trade.requires_escalation ? (
        <HoldToConfirm
          label="Hold to approve trade"
          durationMs={1400}
          disabled={disabled}
          onConfirm={() => authorize(true)}
          accessibilityHint="Hold continuously to approve this elevated-risk prepared trade"
        />
      ) : (
        <ActionButton
          accessibilityLabel="Approve trade"
          accessibilityRole="button"
          label="Approve trade"
          tone="danger"
          disabled={disabled}
          loading={busy}
          onPress={() => void authorize(false)}
        />
      )}
      {receipt ? <ActionStatus receipt={receipt} /> : null}
    </View>
  );
}

export function TradeDetailScreen({
  intentId,
  onBack,
}: {
  intentId: string;
  onBack(): void;
}) {
  const session = useOptionalSession();
  const netInfo = useNetInfo();
  const query = useTradeQuery(intentId);
  const trade = query.data;
  const initialDraft: MobileTradeDraft | null = trade
    ? {
        amount: trade.amount,
        slippage_pct: String(trade.quote.slippage_pct),
        stop_pct: String(trade.limits.stop_pct.min),
        target_pct: String(trade.limits.target_pct.min),
      }
    : null;
  const connectionOptions = session
    ? { apiBaseUrl: session.apiBaseUrl, token: session.token }
    : {};

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Pressable
          accessibilityLabel="Back to trades"
          accessibilityRole="button"
          onPress={onBack}
          style={styles.back}>
          <ArrowLeft color={colors.text} size={20} />
        </Pressable>
        {query.isLoading ? (
          <View accessibilityLabel="Loading trade review" style={styles.loading}>
            <View style={[styles.skeleton, { width: "52%", height: 32 }]} />
            <View style={[styles.skeleton, { height: 180 }]} />
          </View>
        ) : !trade || !initialDraft ? (
          <>
            <EmptyState
              title="Trade unavailable"
              body="This prepared intent could not be loaded."
            />
            <ActionButton label="Retry" onPress={() => void query.refetch()} />
          </>
        ) : (
          <>
            <PageHeader
              eyebrow="Prepared trade"
              title={`${trade.action.toUpperCase()} ${trade.symbol || "token"}`}
              subtitle={trade.mint}
              right={
                <StatusBadge
                  label={trade.status}
                  tone={trade.status === "simulated" ? "success" : "warning"}
                />
              }
            />
            <Section title="Prepared evidence">
              <DetailRow
                label="Amount"
                value={`${trade.amount} ${trade.limits.amount.unit}`}
              />
              <DetailRow
                label="Quote"
                value={trade.quote.stale ? "Stale" : trade.quote.status}
                tone={trade.quote.stale ? "danger" : "success"}
              />
              <DetailRow
                label="Simulation"
                value={trade.simulation.ok ? "Passed" : "Blocked"}
                tone={trade.simulation.ok ? "success" : "danger"}
              />
              <DetailRow label="Reason" value={trade.reason} />
            </Section>
            <Section title="Authorization">
              <GuardedTradeApproval
                trade={trade}
                initialDraft={initialDraft}
                online={Boolean(
                  netInfo.isConnected &&
                    netInfo.isInternetReachable !== false,
                )}
                submitApproval={(input) =>
                  approveTrade(trade.id, input, connectionOptions)
                }
                reconcileAction={(actionId) =>
                  fetchAction(actionId, connectionOptions)
                }
              />
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
    paddingBottom: spacing.xl,
    gap: spacing.md,
  },
  approval: {
    gap: spacing.md,
  },
  back: {
    alignItems: "center",
    justifyContent: "center",
    width: 44,
    height: 44,
    backgroundColor: colors.panel,
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  blocker: {
    color: colors.amber,
    fontSize: 11,
    lineHeight: 16,
  },
  error: {
    color: colors.rose,
    fontSize: 11,
    lineHeight: 16,
  },
  loading: {
    gap: spacing.md,
  },
  skeleton: {
    backgroundColor: colors.panelRaised,
    borderRadius: radius.sm,
  },
});
