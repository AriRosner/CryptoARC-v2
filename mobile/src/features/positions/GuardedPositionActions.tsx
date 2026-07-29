import * as LocalAuthentication from "expo-local-authentication";
import React, { useEffect, useRef, useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { HoldToConfirm } from "../../components/actions/HoldToConfirm";
import { ActionButton } from "../../components/ui";
import { MobileApiError } from "../../core/api/errors";
import { colors, radius, spacing } from "../../theme";
import { ActionStatus } from "../trades/ActionStatus";
import {
  createMobileIdempotencyKey,
} from "../trades/api";
import {
  pendingActionStore as durablePendingActionStore,
  type PendingActionStore,
} from "../trades/pendingAction";
import type {
  GuardedApprovalInput,
  MobileActionReceipt,
} from "../trades/types";
import type { PositionDetail } from "./types";

interface AdjustmentInput {
  expectedVersion: number;
  stopPct: string;
  targetPct: string;
  escalationAcknowledged: boolean;
  idempotencyKey: string;
}

interface CloseInput extends GuardedApprovalInput {
  intentId: string;
  positionVersion: number;
}

export interface GuardedPositionActionsProps {
  position: PositionDetail;
  online: boolean;
  submitAdjustment(input: AdjustmentInput): Promise<MobileActionReceipt>;
  submitClose(input: CloseInput): Promise<MobileActionReceipt>;
  reconcileAction?(actionId: string): Promise<MobileActionReceipt>;
  createIdempotencyKey?(): string;
  pendingActionStore?: PendingActionStore;
  onCompleted?(): Promise<unknown> | void;
}

function pendingReceipt(actionId: string): MobileActionReceipt {
  const now = new Date().toISOString();
  return {
    action_id: actionId,
    status: "verifying",
    submitted_at: now,
    updated_at: now,
    operator_message: "Verifying outcome",
    reconcile_after_ms: 500,
  };
}

export function GuardedPositionActions({
  position,
  online,
  submitAdjustment,
  submitClose,
  reconcileAction,
  createIdempotencyKey = createMobileIdempotencyKey,
  pendingActionStore = durablePendingActionStore,
  onCompleted,
}: GuardedPositionActionsProps) {
  const [stopPct, setStopPct] = useState(String(position.stop_pct));
  const [targetPct, setTargetPct] = useState(String(position.target_pct));
  const [receipt, setReceipt] = useState<MobileActionReceipt | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  useEffect(() => {
    setStopPct(String(position.stop_pct));
    setTargetPct(String(position.target_pct));
  }, [position.stop_pct, position.target_pct, position.version]);

  useEffect(() => {
    let active = true;
    void pendingActionStore.load().then((pending) => {
      if (
        active &&
        pending?.entityId === position.id &&
        ["position_adjust_exit", "position_close"].includes(
          pending.actionType,
        )
      ) {
        setReceipt(pendingReceipt(pending.actionId));
      }
    });
    return () => {
      active = false;
    };
  }, [pendingActionStore, position.id]);

  useEffect(() => {
    if (
      !receipt ||
      !reconcileAction ||
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
            if (["pending", "verifying"].includes(next.status)) poll();
            else void pendingActionStore.clear(next.action_id);
          },
          (caught) => {
            if (!active) return;
            if (caught instanceof MobileApiError && caught.status === 403) {
              setError(
                "This device does not have trade execution access.",
              );
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

  const authenticate = async (promptMessage: string) => {
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage,
      cancelLabel: "Cancel",
      disableDeviceFallback: true,
    });
    return result.success;
  };

  const run = async (
    actionType: "position_adjust_exit" | "position_close",
    operation: (actionId: string) => Promise<MobileActionReceipt>,
  ) => {
    if (!online || busy || inFlight.current) return;
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
      await pendingActionStore.save({
        actionId,
        entityId: position.id,
        actionType,
      });
      const next = await operation(actionId);
      setReceipt(next);
      if (!["pending", "verifying"].includes(next.status)) {
        await pendingActionStore.clear(next.action_id);
        await onCompleted?.();
      }
    } catch (caught) {
      if (
        caught instanceof MobileApiError &&
        caught.category === "ambiguous_outcome"
      ) {
        setReceipt(pendingReceipt(actionId));
      } else if (
        caught instanceof MobileApiError &&
        caught.status === 403
      ) {
        setError("This device does not have trade execution access.");
      } else {
        setError(
          caught instanceof Error ? caught.message : "Position action failed",
        );
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const adjust = async () => {
    if (!position.allowed_actions.adjust_exit) return;
    if (!(await authenticate("Update CryptoARC exit controls"))) return;
    await run("position_adjust_exit", (actionId) =>
      submitAdjustment({
        expectedVersion: position.version,
        stopPct,
        targetPct,
        escalationAcknowledged: true,
        idempotencyKey: actionId,
      }),
    );
  };

  const close = async () => {
    const prepared = position.prepared_close;
    if (!position.allowed_actions.close || !prepared) return;
    if (!(await authenticate("Close the full CryptoARC position"))) return;
    await run("position_close", (actionId) =>
      submitClose({
        expectedVersion: prepared.intent_version,
        positionVersion: prepared.position_version,
        intentId: prepared.intent_id,
        draft: {
          amount: "100%",
          slippage_pct: String(prepared.slippage_pct),
          stop_pct: String(position.stop_pct),
          target_pct: String(position.target_pct),
        },
        escalationAcknowledged: true,
        idempotencyKey: actionId,
      }),
    );
  };

  const disabled =
    !online ||
    busy ||
    Boolean(
      receipt && ["pending", "verifying"].includes(receipt.status),
    );

  return (
    <View style={styles.container}>
      <View style={styles.fields}>
        <View style={styles.field}>
          <Text style={styles.label}>Stop %</Text>
          <TextInput
            accessibilityLabel="Position stop percentage"
            keyboardType="decimal-pad"
            value={stopPct}
            onChangeText={setStopPct}
            editable={!disabled}
            style={styles.input}
          />
        </View>
        <View style={styles.field}>
          <Text style={styles.label}>Target %</Text>
          <TextInput
            accessibilityLabel="Position target percentage"
            keyboardType="decimal-pad"
            value={targetPct}
            onChangeText={setTargetPct}
            editable={!disabled}
            style={styles.input}
          />
        </View>
      </View>
      <ActionButton
        label="Apply exit controls"
        disabled={disabled || !position.allowed_actions.adjust_exit}
        loading={busy}
        onPress={() => void adjust()}
      />
      {position.prepared_close ? (
        <HoldToConfirm
          label="Hold to close full position"
          durationMs={1400}
          disabled={disabled || !position.allowed_actions.close}
          onConfirm={() => close()}
          accessibilityHint="Hold continuously to submit the exact prepared full-position close"
        />
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {receipt ? <ActionStatus receipt={receipt} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.md,
  },
  fields: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  field: {
    flex: 1,
    gap: 6,
  },
  label: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
  },
  input: {
    minHeight: 44,
    borderColor: colors.borderStrong,
    borderRadius: radius.sm,
    borderWidth: 1,
    backgroundColor: colors.deep,
    color: colors.text,
    paddingHorizontal: spacing.sm,
  },
  error: {
    color: colors.rose,
    fontSize: 11,
    lineHeight: 16,
  },
});
