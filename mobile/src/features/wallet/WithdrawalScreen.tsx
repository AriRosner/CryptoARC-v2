import React, { useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { HoldToConfirm } from "../../components/actions/HoldToConfirm";
import { ActionButton, DetailRow, StatusBadge } from "../../components/ui";
import { MobileApiError } from "../../core/api/errors";
import {
  useOptionalAppLock,
  type ControlAuthorizationBinding,
  type ControlAuthorizationProof,
} from "../../components/system/AppLock";
import { colors, spacing } from "../../theme";
import { createMobileIdempotencyKey } from "../trades/api";
import { ActionStatus } from "../trades/ActionStatus";
import {
  pendingActionForOwner,
  pendingActionForReview,
  pendingActionRoute,
  pendingActionStore as durablePendingActionStore,
  samePendingActionOwner,
  TEST_PENDING_ACTION_OWNER,
  type PendingActionOwner,
  type PendingActionStore,
  type PendingMobileAction,
} from "../trades/pendingAction";
import type { MobileActionReceipt } from "../trades/types";
import type {
  MobileTreasuryPreview,
  TreasuryExecuteInput,
} from "./types";

export interface GuardedTreasuryActionProps {
  preview: MobileTreasuryPreview;
  online: boolean;
  execute(input: TreasuryExecuteInput): Promise<MobileActionReceipt>;
  reconcileAction(actionId: string): Promise<MobileActionReceipt>;
  createIdempotencyKey?(): string;
  pendingActionStore?: PendingActionStore;
  pendingOwner?: PendingActionOwner;
  onOpenPendingAction?(action: PendingMobileAction): void;
}

export interface TreasuryPendingRecoveryProps {
  reconcileAction(actionId: string): Promise<MobileActionReceipt>;
  pendingActionStore?: PendingActionStore;
  pendingOwner?: PendingActionOwner;
}

function verifyingReceipt(actionId: string): MobileActionReceipt {
  const now = new Date().toISOString();
  return {
    action_id: actionId,
    status: "verifying",
    submitted_at: now,
    updated_at: now,
    operator_message: "Verifying outcome",
    reconcile_after_ms: 1000,
  };
}

function reviewReceipt(
  actionId: string,
  message: string,
): MobileActionReceipt {
  const now = new Date().toISOString();
  return {
    action_id: actionId,
    status: "review_required",
    submitted_at: now,
    updated_at: now,
    operator_message: message,
    reconcile_after_ms: 1000,
  };
}

function definitiveFailure(error: unknown) {
  return (
    error instanceof MobileApiError &&
    error.status !== null &&
    [400, 401, 403, 404, 409, 410, 412, 422, 426].includes(error.status)
  );
}

export function GuardedTreasuryAction({
  preview,
  online,
  execute,
  reconcileAction,
  createIdempotencyKey = createMobileIdempotencyKey,
  pendingActionStore = durablePendingActionStore,
  pendingOwner = TEST_PENDING_ACTION_OWNER,
  onOpenPendingAction,
}: GuardedTreasuryActionProps) {
  const controlAuthorization = useOptionalAppLock();
  const [authorized, setAuthorized] = useState(false);
  const [receipt, setReceipt] = useState<MobileActionReceipt | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingElsewhere, setPendingElsewhere] = useState(false);
  const [abandonArmed, setAbandonArmed] = useState(false);
  const inFlight = useRef(false);
  const pendingAction = useRef<PendingMobileAction | null>(null);
  const actionId = useRef("");
  const authorizationProof = useRef<ControlAuthorizationProof | null>(null);
  const active = useRef(true);
  const currentPreview = useRef(preview);
  currentPreview.current = preview;

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  useEffect(() => {
    authorizationProof.current = null;
    setAuthorized(false);
    setReceipt(null);
    setError("");
    setAbandonArmed(false);
    setPendingElsewhere(false);
    inFlight.current = false;
    actionId.current = "";
  }, [preview.preview_id]);

  useEffect(() => {
    let active = true;
    void pendingActionStore.load().then((pending) => {
      if (!active || !pending) return;
      const belongsHere =
        pending.entityId === preview.authorization_id &&
        pending.actionType === preview.action;
      const ownerMatches = samePendingActionOwner(pending, pendingOwner);
      if (!ownerMatches || pending.state === "review_required") {
        const message =
          pending.reviewMessage ||
          "Pending action belongs to a different pairing. Review it before abandoning.";
        const reviewed = pendingActionForReview(pending, message);
        pendingAction.current = reviewed;
        actionId.current = pending.actionId;
        setPendingElsewhere(false);
        void pendingActionStore.save(reviewed);
        setReceipt(reviewReceipt(pending.actionId, message));
      } else if (belongsHere) {
        pendingAction.current = pending;
        actionId.current = pending.actionId;
        setPendingElsewhere(false);
        setReceipt(verifyingReceipt(pending.actionId));
      } else {
        const message =
          "Another financial action is pending. Open its owning screen to reconcile it.";
        pendingAction.current = pending;
        setPendingElsewhere(true);
        setReceipt(reviewReceipt(pending.actionId, message));
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
    preview.action,
    preview.authorization_id,
  ]);

  useEffect(() => {
    if (
      !receipt?.action_id ||
      !["pending", "verifying"].includes(receipt.status)
    ) {
      return;
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = () => {
      timer = setTimeout(() => {
        void reconcileAction(receipt.action_id).then(
          (next) => {
            if (!active) return;
            setReceipt(next);
            if (["pending", "verifying"].includes(next.status)) {
              poll();
            } else if (next.status === "review_required") {
              const current = pendingAction.current;
              if (current) {
                const reviewed = pendingActionForReview(
                  current,
                  next.operator_message,
                );
                pendingAction.current = reviewed;
                void pendingActionStore.save(reviewed);
              }
            } else {
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
                  "This pairing cannot reconcile the treasury action. Review before abandoning it.";
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
      }, Math.max(250, Math.min(30000, receipt.reconcile_after_ms)));
    };
    poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [pendingActionStore, receipt, reconcileAction]);

  const authenticate = async () => {
    if (!online || busy || receipt) return;
    setError("");
    const binding = treasuryBinding(currentPreview.current);
    const proof = await controlAuthorization?.authorizeControl(binding);
    if (
      !active.current ||
      !proof ||
      !controlAuthorization?.isControlAuthorizationCurrent(
        proof,
        treasuryBinding(currentPreview.current),
      )
    ) return;
    authorizationProof.current = proof;
    setAuthorized(true);
  };

  const treasuryBinding = (
    value: MobileTreasuryPreview,
  ): ControlAuthorizationBinding => ({
    actionType: value.action,
    entityId: value.authorization_id,
    reviewKey: JSON.stringify({
      address: value.destination,
      amount: value.amount,
      asset: value.asset,
      previewId: value.preview_id,
      sourceWallet: value.source_wallet_public_key,
      tokenAccounts: value.token_accounts,
    }),
  });

  const proofIsCurrent = (): boolean =>
    Boolean(
      active.current &&
      authorizationProof.current &&
      controlAuthorization?.isControlAuthorizationCurrent(
        authorizationProof.current,
        treasuryBinding(currentPreview.current),
      ),
    );

  const submit = async () => {
    if (
      !online ||
      busy ||
      inFlight.current ||
      !authorized ||
      !proofIsCurrent()
    ) {
      authorizationProof.current = null;
      setAuthorized(false);
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setError("");
    if (!actionId.current) {
      actionId.current = createIdempotencyKey();
    }
    try {
      const existing = await pendingActionStore.load();
      if (!proofIsCurrent()) return;
      if (existing && existing.actionId !== actionId.current) {
        actionId.current = "";
        setError(
          "Reconcile the pending financial action before starting another.",
        );
        return;
      }
      const durable = pendingActionForOwner(
        actionId.current,
        preview.authorization_id,
        preview.action,
        pendingOwner,
      );
      pendingAction.current = durable;
      await pendingActionStore.save(durable);
      if (!proofIsCurrent()) {
        await pendingActionStore.clear(durable.actionId);
        pendingAction.current = null;
        actionId.current = "";
        return;
      }
      const next = await execute({
        authorizationId: preview.authorization_id,
        previewId: preview.preview_id,
        address: preview.destination,
        asset: preview.asset,
        amount: preview.amount,
        tokenAccounts: preview.token_accounts,
        idempotencyKey: actionId.current,
      });
      setReceipt(next);
      if (next.status === "review_required") {
        const reviewed = pendingActionForReview(
          durable,
          next.operator_message,
        );
        pendingAction.current = reviewed;
        await pendingActionStore.save(reviewed);
      } else if (!["pending", "verifying"].includes(next.status)) {
        await pendingActionStore.clear(next.action_id);
        pendingAction.current = null;
      }
    } catch (caught) {
      if (definitiveFailure(caught)) {
        await pendingActionStore.clear(actionId.current);
        pendingAction.current = null;
        actionId.current = "";
        setReceipt(null);
        setError(
          caught instanceof Error
            ? caught.message
            : "Treasury authorization failed",
        );
      } else {
        setReceipt(verifyingReceipt(actionId.current));
        setError(
          "Treasury outcome is unknown. Reconciliation will continue without resubmission.",
        );
      }
    } finally {
      authorizationProof.current = null;
      if (active.current) {
        setAuthorized(false);
        setBusy(false);
      }
      inFlight.current = false;
    }
  };

  const confirmAbandon = async () => {
    const current = pendingAction.current;
    if (!current || pendingElsewhere) return;
    await pendingActionStore.clear(current.actionId);
    pendingAction.current = null;
    actionId.current = "";
    setReceipt(null);
    setAbandonArmed(false);
  };

  const openPendingAction = () => {
    const current = pendingAction.current;
    if (!current || !pendingActionRoute(current)) return;
    onOpenPendingAction?.(current);
  };

  const blocked =
    !online ||
    busy ||
    Boolean(
      receipt &&
        ["pending", "verifying", "review_required"].includes(receipt.status),
    );

  return (
    <View style={styles.stack}>
      <View style={styles.previewHeader}>
        <Text style={styles.action}>
          {preview.action.replace("_", " ")}
        </Text>
        <StatusBadge label="Preview bound" tone="warning" />
      </View>
      <DetailRow label="Destination" value={preview.destination} />
      <DetailRow
        label="Amount"
        value={`${preview.amount} ${preview.asset}`}
      />
      <DetailRow
        label="Expected fee"
        value={`${preview.expected_fee_sol} SOL`}
      />
      <DetailRow
        label="Remaining balance"
        value={`${preview.remaining_balance_sol} SOL`}
      />
      <DetailRow label="Authorization" value={preview.authorization_id} />
      <DetailRow label="Purpose" value={preview.purpose} />
      <DetailRow
        label="Source wallet"
        value={preview.source_wallet_public_key}
      />
      <DetailRow
        label="Expires"
        value={new Date(preview.expires_at).toLocaleString()}
      />
      {preview.warnings.map((warning) => (
        <Text key={warning} style={styles.warning}>
          {warning}
        </Text>
      ))}
      {!online ? (
        <Text style={styles.offline}>Unavailable offline</Text>
      ) : !authorized ? (
        <ActionButton
          label="Authenticate treasury action"
          tone="danger"
          disabled={blocked}
          loading={busy}
          onPress={() => void authenticate()}
        />
      ) : (
        <HoldToConfirm
          label="Hold to execute treasury action"
          durationMs={1400}
          disabled={blocked}
          onConfirm={submit}
          accessibilityHint="Requires a deliberate hold after fresh biometric authentication"
        />
      )}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {receipt ? <ActionStatus receipt={receipt} /> : null}
      {receipt?.status === "review_required" ? (
        pendingElsewhere ? (
          pendingAction.current &&
          pendingActionRoute(pendingAction.current) &&
          onOpenPendingAction ? (
            <ActionButton
              label="Open pending action"
              onPress={openPendingAction}
            />
          ) : (
            <Text style={styles.warning}>
              Open the owning treasury screen to reconcile this action.
            </Text>
          )
        ) : abandonArmed ? (
          <>
            <Text style={styles.warning}>
              Abandoning removes only local recovery state. Verify the desktop
              and chain outcome first.
            </Text>
            <ActionButton
              label="Confirm abandon pending action"
              onPress={() => void confirmAbandon()}
            />
          </>
        ) : (
          <ActionButton
            label="Abandon pending action"
            onPress={() => setAbandonArmed(true)}
          />
        )
      ) : null}
    </View>
  );
}

export function TreasuryPendingRecovery({
  reconcileAction,
  pendingActionStore = durablePendingActionStore,
  pendingOwner = TEST_PENDING_ACTION_OWNER,
}: TreasuryPendingRecoveryProps) {
  const [receipt, setReceipt] = useState<MobileActionReceipt | null>(null);
  const [message, setMessage] = useState("");
  const [abandonArmed, setAbandonArmed] = useState(false);
  const [canAbandon, setCanAbandon] = useState(false);
  const pendingAction = useRef<PendingMobileAction | null>(null);

  useEffect(() => {
    let active = true;
    void pendingActionStore.load().then((pending) => {
      if (!active || !pending) {
        if (active) setMessage("No pending treasury action was found.");
        return;
      }
      if (
        !["withdrawal", "profit_sweep", "rent_recovery"].includes(
          pending.actionType,
        )
      ) {
        setMessage("The pending financial action belongs to another screen.");
        return;
      }
      pendingAction.current = pending;
      const sameOwner = samePendingActionOwner(pending, pendingOwner);
      setCanAbandon(sameOwner);
      if (
        !sameOwner ||
        pending.state === "review_required"
      ) {
        const reviewMessage =
          pending.reviewMessage ||
          "Pending action belongs to a different pairing. Review it before abandoning.";
        const reviewed =
          pending.state === "review_required" && pending.reviewMessage
            ? pending
            : pendingActionForReview(pending, reviewMessage);
        pendingAction.current = reviewed;
        if (reviewed !== pending) {
          void pendingActionStore.save(reviewed);
        }
        setReceipt(reviewReceipt(pending.actionId, reviewMessage));
        return;
      }
      setReceipt(verifyingReceipt(pending.actionId));
    });
    return () => {
      active = false;
    };
  }, [
    pendingActionStore,
    pendingOwner.apiBaseUrl,
    pendingOwner.deviceId,
    pendingOwner.sessionId,
  ]);

  useEffect(() => {
    if (
      !receipt?.action_id ||
      !["pending", "verifying"].includes(receipt.status)
    ) {
      return;
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = () => {
      timer = setTimeout(() => {
        void reconcileAction(receipt.action_id).then(
          (next) => {
            if (!active) return;
            setReceipt(next);
            if (["pending", "verifying"].includes(next.status)) {
              poll();
            } else if (next.status === "review_required") {
              const current = pendingAction.current;
              if (current) {
                const reviewed = pendingActionForReview(
                  current,
                  next.operator_message,
                );
                pendingAction.current = reviewed;
                void pendingActionStore.save(reviewed);
              }
            } else {
              pendingAction.current = null;
              void pendingActionStore.clear(next.action_id);
            }
          },
          () => {
            if (active) poll();
          },
        );
      }, Math.max(250, Math.min(30000, receipt.reconcile_after_ms)));
    };
    poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [pendingActionStore, receipt, reconcileAction]);

  const confirmAbandon = async () => {
    const current = pendingAction.current;
    if (!current) return;
    await pendingActionStore.clear(current.actionId);
    pendingAction.current = null;
    setReceipt(null);
    setAbandonArmed(false);
    setMessage("No pending treasury action was found.");
  };

  if (receipt) {
    return (
      <View style={styles.stack}>
        <ActionStatus receipt={receipt} />
        {receipt.status === "review_required" && canAbandon ? (
          abandonArmed ? (
            <>
              <Text style={styles.warning}>
                Abandoning removes only local recovery state. Verify the desktop
                and chain outcome first.
              </Text>
              <ActionButton
                label="Confirm abandon pending action"
                onPress={() => void confirmAbandon()}
              />
            </>
          ) : (
            <ActionButton
              label="Abandon pending action"
              onPress={() => setAbandonArmed(true)}
            />
          )
        ) : null}
      </View>
    );
  }
  return <Text style={styles.warning}>{message}</Text>;
}

export function TreasuryPreviewError({ message }: { message: string }) {
  if (!message) return null;
  return (
    <Text
      accessibilityLiveRegion="assertive"
      accessibilityRole="alert"
      style={styles.error}
    >
      {message}
    </Text>
  );
}

export function WithdrawalScreen(props: GuardedTreasuryActionProps) {
  return <GuardedTreasuryAction {...props} />;
}

const styles = StyleSheet.create({
  stack: {
    gap: spacing.md,
  },
  previewHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md,
  },
  action: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "900",
    textTransform: "capitalize",
  },
  warning: {
    color: colors.amber,
    fontSize: 11,
    lineHeight: 17,
  },
  offline: {
    color: colors.rose,
    fontSize: 12,
    fontWeight: "900",
  },
  error: {
    color: colors.rose,
    fontSize: 11,
    lineHeight: 17,
  },
});
