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
import { authenticatedRead } from "../../core/api/authenticatedRead";
import { MobileApiError } from "../../core/api/errors";
import { useOptionalSession } from "../../core/session/SessionProvider";
import { colors, radius, spacing } from "../../theme";
import {
  approveTrade,
  createMobileIdempotencyKey,
  fetchAction,
  rejectTrade,
  validateTrade,
} from "./api";
import { ActionStatus } from "./ActionStatus";
import { BoundedTradeForm } from "./BoundedTradeForm";
import { useTradeQuery } from "./queries";
import { RiskEscalation } from "./RiskEscalation";
import {
  pendingActionForOwner,
  pendingActionForReview,
  pendingActionStore as durablePendingActionStore,
  samePendingActionOwner,
  TEST_PENDING_ACTION_OWNER,
  type PendingActionOwner,
  type PendingActionStore,
  type PendingMobileAction,
} from "./pendingAction";
import type {
  GuardedApprovalInput,
  GuardedRejectionInput,
  MobileActionReceipt,
  MobileTradeDetail,
  MobileTradeDraft,
  MobileTradeValidation,
} from "./types";

export interface GuardedTradeApprovalProps {
  trade: MobileTradeDetail;
  initialDraft: MobileTradeDraft;
  online: boolean;
  submitApproval(input: GuardedApprovalInput): Promise<MobileActionReceipt>;
  submitRejection?(
    input: GuardedRejectionInput,
  ): Promise<MobileActionReceipt>;
  validateDraft?(
    draft: MobileTradeDraft,
  ): Promise<MobileTradeValidation>;
  reconcileAction?(actionId: string): Promise<MobileActionReceipt>;
  createIdempotencyKey?(): string;
  pendingActionStore?: PendingActionStore;
  pendingOwner?: PendingActionOwner;
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

function reviewReceipt(
  actionId: string,
  operatorMessage: string,
): MobileActionReceipt {
  const now = new Date().toISOString();
  return {
    action_id: actionId,
    status: "review_required",
    submitted_at: now,
    updated_at: now,
    operator_message: operatorMessage,
    reconcile_after_ms: 1000,
  };
}

function isDefinitivePreReceiptFailure(caught: unknown): boolean {
  return (
    caught instanceof MobileApiError &&
    !caught.actionId &&
    caught.status !== null &&
    [400, 401, 403, 404, 409, 410, 412, 422, 426].includes(caught.status)
  );
}

export function GuardedTradeApproval({
  trade,
  initialDraft,
  online,
  submitApproval,
  submitRejection,
  validateDraft,
  reconcileAction,
  createIdempotencyKey = createMobileIdempotencyKey,
  pendingActionStore = durablePendingActionStore,
  pendingOwner = TEST_PENDING_ACTION_OWNER,
}: GuardedTradeApprovalProps) {
  const [draft, setDraft] = useState(initialDraft);
  const [receipt, setReceipt] = useState<MobileActionReceipt | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [liveValidation, setLiveValidation] =
    useState<MobileTradeValidation | null>(null);
  const inFlight = useRef(false);
  const idempotencyKey = useRef("");
  const pendingAction = useRef<PendingMobileAction | null>(null);

  useEffect(() => {
    setDraft(initialDraft);
    setReceipt(null);
    setError("");
    setLiveValidation(null);
    inFlight.current = false;
    idempotencyKey.current = "";
  }, [initialDraft, trade.id, trade.version]);

  useEffect(() => {
    let active = true;
    void pendingActionStore.load().then((pending) => {
      if (!active || !pending) return;
      const belongsToTrade =
        pending.entityId === trade.id &&
        ["trade_approve", "trade_reject"].includes(pending.actionType);
      const ownerMatches = samePendingActionOwner(pending, pendingOwner);
      if (!ownerMatches || pending.state === "review_required") {
        const message =
          pending.reviewMessage ||
          "Pending action belongs to a different pairing. Review it before abandoning.";
        const reviewed = pendingActionForReview(pending, message);
        pendingAction.current = reviewed;
        idempotencyKey.current = pending.actionId;
        void pendingActionStore.save(reviewed);
        setReceipt(reviewReceipt(pending.actionId, message));
      } else if (belongsToTrade) {
        pendingAction.current = pending;
        idempotencyKey.current = pending.actionId;
        setReceipt(ambiguousReceipt(pending.actionId));
      }
    });
    return () => {
      active = false;
    };
  }, [
    pendingActionStore,
    pendingOwner.apiBaseUrl,
    pendingOwner.deviceId,
    pendingOwner.sessionId,
    trade.id,
  ]);

  useEffect(() => {
    if (!validateDraft) return;
    let active = true;
    const timer = setTimeout(() => {
      void validateDraft(draft).then(
        (validation) => {
          if (active) setLiveValidation(validation);
        },
        () => {
          if (active) setLiveValidation(null);
        },
      );
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [draft, validateDraft]);

  useEffect(() => {
    if (
      !receipt?.action_id ||
      !["pending", "verifying"].includes(receipt.status) ||
      !reconcileAction
    ) {
      return;
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const delay = Math.max(
      250,
      Math.min(30000, receipt.reconcile_after_ms),
    );
    const poll = () => {
      timer = setTimeout(() => {
        void reconcileAction(receipt.action_id).then(
          (next) => {
            if (!active) return;
            setReceipt(next);
            if (["pending", "verifying"].includes(next.status)) poll();
            else {
              pendingAction.current = null;
              void pendingActionStore.clear(next.action_id);
            }
          },
          (caught) => {
            if (!active) return;
            if (
              caught instanceof MobileApiError &&
              caught.status !== null &&
              [401, 403, 404, 409, 410, 412, 422].includes(caught.status)
            ) {
              const current = pendingAction.current;
              if (current) {
                const message =
                  caught.status === 404
                    ? "The pending action is not visible to this pairing. Review before abandoning it."
                    : "This pairing cannot reconcile the pending action. Review before abandoning it.";
                const reviewed = pendingActionForReview(current, message);
                pendingAction.current = reviewed;
                void pendingActionStore.save(reviewed);
                setReceipt(reviewReceipt(current.actionId, message));
              }
              return;
            }
            poll();
          },
        );
      }, delay);
    };
    poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [pendingActionStore, receipt, reconcileAction]);

  const blockers = liveValidation?.blockers ?? trade.blockers;
  const escalationReasons =
    liveValidation?.escalation_reasons ?? trade.escalation_reasons;
  const requiresEscalation =
    liveValidation?.requires_escalation ?? trade.requires_escalation;

  const disabled =
    !online ||
    !trade.allowed_actions.approve ||
    blockers.length > 0 ||
    busy ||
    Boolean(
      receipt &&
        ["pending", "verifying", "review_required"].includes(receipt.status),
    );

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
      const pending = await pendingActionStore.load();
      if (
        pending &&
        pending.actionId !== idempotencyKey.current
      ) {
        idempotencyKey.current = "";
        setError(
          "Reconcile the pending financial action before starting another.",
        );
        return;
      }
      const durableAction = pendingActionForOwner(
        idempotencyKey.current,
        trade.id,
        "trade_approve",
        pendingOwner,
      );
      pendingAction.current = durableAction;
      await pendingActionStore.save(durableAction);
      const next = await submitApproval({
        expectedVersion: trade.version,
        draft,
        escalationAcknowledged,
        idempotencyKey: idempotencyKey.current,
      });
      setReceipt(next);
      if (!["pending", "verifying"].includes(next.status)) {
        await pendingActionStore.clear(next.action_id);
        pendingAction.current = null;
      }
    } catch (caught) {
      if (
        caught instanceof MobileApiError &&
        caught.category === "ambiguous_outcome"
      ) {
        setReceipt(ambiguousReceipt(idempotencyKey.current));
      } else if (isDefinitivePreReceiptFailure(caught)) {
        await pendingActionStore.clear(idempotencyKey.current);
        pendingAction.current = null;
        setReceipt(null);
        idempotencyKey.current = "";
        if (caught instanceof MobileApiError && caught.status === 403) {
          setError(
            "This device does not have trade execution access.",
          );
        } else {
          setError(
            caught instanceof Error ? caught.message : "Trade approval failed",
          );
        }
      } else {
        setReceipt(ambiguousReceipt(idempotencyKey.current));
        setError("Approval outcome is unknown. Reconciliation will continue.");
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const reject = async () => {
    if (
      !submitRejection ||
      !online ||
      !trade.allowed_actions.reject ||
      busy ||
      inFlight.current
    ) {
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setError("");
    const actionId = createIdempotencyKey();
    try {
      const pending = await pendingActionStore.load();
      if (pending && pending.actionId !== actionId) {
        setError(
          "Reconcile the pending financial action before starting another.",
        );
        return;
      }
      const durableAction = pendingActionForOwner(
        actionId,
        trade.id,
        "trade_reject",
        pendingOwner,
      );
      pendingAction.current = durableAction;
      await pendingActionStore.save(durableAction);
      const next = await submitRejection({
        expectedVersion: trade.version,
        reason: "Rejected from mobile review",
        idempotencyKey: actionId,
      });
      setReceipt(next);
      if (!["pending", "verifying"].includes(next.status)) {
        await pendingActionStore.clear(next.action_id);
        pendingAction.current = null;
      }
    } catch (caught) {
      if (
        caught instanceof MobileApiError &&
        caught.category === "ambiguous_outcome"
      ) {
        setReceipt(ambiguousReceipt(actionId));
      } else if (isDefinitivePreReceiptFailure(caught)) {
        await pendingActionStore.clear(actionId);
        pendingAction.current = null;
        setReceipt(null);
        if (caught instanceof MobileApiError && caught.status === 403) {
          setError("This device does not have trade review access.");
        } else {
          setError(
            caught instanceof Error ? caught.message : "Trade rejection failed",
          );
        }
      } else {
        setReceipt(ambiguousReceipt(actionId));
        setError("Rejection outcome is unknown. Reconciliation will continue.");
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const abandonPendingAction = async () => {
    const actionId =
      pendingAction.current?.actionId || receipt?.action_id || "";
    if (!actionId) return;
    await pendingActionStore.clear(actionId);
    pendingAction.current = null;
    idempotencyKey.current = "";
    setReceipt(null);
    setError("");
  };

  return (
    <View style={styles.approval}>
      <BoundedTradeForm
        draft={draft}
        limits={trade.limits}
        disabled={disabled}
        onChange={setDraft}
      />
      <RiskEscalation reasons={escalationReasons} />
      {!online ? (
        <Text style={styles.blocker}>Offline actions are disabled.</Text>
      ) : null}
      {blockers.map((blocker) => (
        <Text key={blocker} style={styles.blocker}>
          {blocker}
        </Text>
      ))}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {requiresEscalation ? (
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
      {submitRejection ? (
        <ActionButton
          label="Reject trade"
          disabled={
            !online ||
            !trade.allowed_actions.reject ||
            busy ||
            Boolean(
                receipt &&
                ["pending", "verifying", "review_required"].includes(
                  receipt.status,
                ),
            )
          }
          onPress={() => void reject()}
        />
      ) : null}
      {receipt ? <ActionStatus receipt={receipt} /> : null}
      {receipt?.status === "review_required" ? (
        <ActionButton
          label="Abandon pending action"
          onPress={() => void abandonPendingAction()}
        />
      ) : null}
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
    ? trade.default_draft
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
                  authenticatedRead(session, () =>
                    approveTrade(trade.id, input, connectionOptions),
                  )
                }
                submitRejection={(input) =>
                  authenticatedRead(session, () =>
                    rejectTrade(trade.id, input, connectionOptions),
                  )
                }
                validateDraft={(draft) =>
                  authenticatedRead(session, () =>
                    validateTrade(
                      trade.id,
                      {
                        expectedVersion: trade.version,
                        draft,
                        escalationAcknowledged: false,
                      },
                      connectionOptions,
                    ),
                  )
                }
                reconcileAction={(actionId) =>
                  authenticatedRead(session, () =>
                    fetchAction(actionId, connectionOptions),
                  )
                }
                pendingOwner={
                  session
                    ? {
                        apiBaseUrl: session.apiBaseUrl,
                        deviceId: session.device?.id || "unpaired-device",
                        sessionId:
                          session.record?.savedAt ||
                          `session-${session.generation}`,
                      }
                    : TEST_PENDING_ACTION_OWNER
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
