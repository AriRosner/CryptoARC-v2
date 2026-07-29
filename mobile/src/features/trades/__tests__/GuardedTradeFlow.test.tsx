import * as LocalAuthentication from "expo-local-authentication";
import React from "react";
import {
  act,
  fireEvent,
  render,
  waitFor,
} from "@testing-library/react-native";
import { AppState, type AppStateStatus } from "react-native";

import { HoldToConfirm } from "../../../components/actions/HoldToConfirm";
import { MobileApiError } from "../../../core/api/errors";
import { authenticatedRead } from "../../../core/api/authenticatedRead";
import { GuardedPositionActions } from "../../positions/GuardedPositionActions";
import type { PositionDetail } from "../../positions/types";
import { ActionStatus } from "../ActionStatus";
import { BoundedTradeForm } from "../BoundedTradeForm";
import { GuardedTradeApproval } from "../TradeDetailScreen";
import {
  pendingActionRoute,
  type PendingActionOwner,
  type PendingActionStore,
  type PendingMobileAction,
} from "../pendingAction";
import type { MobileActionReceipt, MobileTradeDetail, MobileTradeDraft } from "../types";

const routineTrade: MobileTradeDetail = {
  id: "intent-routine",
  version: 3,
  action: "buy",
  symbol: "ARC",
  mint: "MintRoutine",
  amount: "0.05",
  status: "simulated",
  reason: "Prepared by desktop review",
  source: "manual",
  updated_at: "2026-07-28T12:00:00Z",
  expires_at: "2026-07-28T12:02:00Z",
  quote: {
    status: "ready",
    slippage_pct: 1,
    expires_at: "2026-07-28T12:02:00Z",
    stale: false,
  },
  simulation: { status: "ok", ok: true, warning: "", error: "" },
  default_draft: {
    amount: "0.05",
    slippage_pct: "1",
    stop_pct: "20",
    target_pct: "40",
  },
  limits: {
    amount: { min: 0.05, max: 0.05, unit: "SOL" },
    slippage_pct: { min: 1, max: 1 },
    stop_pct: { min: 1, max: 100 },
    target_pct: { min: 1, max: 100 },
  },
  blockers: [],
  escalation_reasons: [],
  requires_escalation: false,
  allowed_actions: { approve: true, reject: true },
};

const validDraft: MobileTradeDraft = {
  amount: "0.05",
  slippage_pct: "1",
  stop_pct: "20",
  target_pct: "40",
};

const ownerA: PendingActionOwner = {
  apiBaseUrl: "https://node-a.test",
  deviceId: "device-a",
  sessionId: "session-a",
};

const ownerB: PendingActionOwner = {
  apiBaseUrl: "https://node-b.test",
  deviceId: "device-b",
  sessionId: "session-b",
};

function createPendingStore(initial: PendingMobileAction | null = null) {
  let current = initial;
  const store: PendingActionStore & {
    current(): PendingMobileAction | null;
    setCurrent(action: PendingMobileAction | null): void;
  } = {
    load: jest.fn(async () => current),
    save: jest.fn(async (action) => {
      current = action;
    }),
    clear: jest.fn(async (actionId) => {
      if (current?.actionId === actionId) current = null;
    }),
    current: () => current,
    setCurrent: (action) => {
      current = action;
    },
  };
  return store;
}

function makeGuardedPosition(): PositionDetail {
  return {
    id: "live-position-guarded",
    mode: "live",
    symbol: "ARC",
    mint: "MintRoutine",
    status: "open",
    opened_at: "2026-07-28T12:00:00Z",
    updated_at: "2026-07-28T12:00:00Z",
    wallet_label: "Wallet",
    token_balance: 100,
    cost_basis_sol: 0.05,
    value_sol: 0.06,
    realized_pnl_sol: 0,
    unrealized_pnl_sol: 0.01,
    pnl_pct: 20,
    pnl_approximate: false,
    mark_fresh: true,
    mark_age_seconds: 1,
    mark_source: "test",
    mark: {
      price_sol: 0.001,
      source: "test",
      confidence: 1,
      observed_at: "2026-07-28T12:00:00Z",
      age_seconds: 1,
      fresh: true,
    },
    pnl: {
      realized_sol: 0,
      unrealized_sol: 0.01,
      total_sol: 0.01,
      percentage: 20,
      approximate: false,
      confidence: "audited",
      notes: [],
    },
    reconciliation_status: "matched",
    version: 7,
    stop_pct: 20,
    target_pct: 40,
    prepared_close: {
      intent_id: "intent-close",
      intent_version: 5,
      position_version: 7,
      amount: "100%",
      slippage_pct: 1,
      expires_at: "2026-07-28T12:02:00Z",
    },
    allowed_actions: { adjust_exit: true, close: true, reason: "Ready" },
  };
}

function verifyingReceipt(): MobileActionReceipt {
  return {
    action_id: "maction-test",
    status: "verifying",
    submitted_at: "2026-07-28T12:00:01Z",
    updated_at: "2026-07-28T12:00:01Z",
    operator_message: "Verifying outcome",
    reconcile_after_ms: 1000,
  };
}

describe("guarded mobile trade flow", () => {
  const authenticate = jest.mocked(LocalAuthentication.authenticateAsync);

  beforeEach(() => {
    jest.clearAllMocks();
    authenticate.mockResolvedValue({ success: true });
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it("requires biometric confirmation before a routine approval", async () => {
    const submit = jest.fn(async () => verifyingReceipt());
    const screen = await render(
      <GuardedTradeApproval
        trade={routineTrade}
        initialDraft={validDraft}
        online
        submitApproval={submit}
        createIdempotencyKey={() => "routine-key"}
      />,
    );

    await fireEvent.press(
      screen.getByRole("button", { name: "Approve trade" }),
    );

    await waitFor(() => expect(authenticate).toHaveBeenCalledTimes(1));
    expect(submit).toHaveBeenCalledTimes(1);
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({ idempotencyKey: "routine-key" }),
    );
    expect(await screen.findByText("No automatic resubmission")).toBeTruthy();
  });

  it("requires biometric plus a 1400ms hold for elevated risk", async () => {
    jest.useFakeTimers();
    const submit = jest.fn(async () => verifyingReceipt());
    const elevated = {
      ...routineTrade,
      requires_escalation: true,
      escalation_reasons: ["Wide stop", "High target"],
    };
    const screen = await render(
      <GuardedTradeApproval
        trade={elevated}
        initialDraft={validDraft}
        online
        submitApproval={submit}
        createIdempotencyKey={() => "elevated-key"}
      />,
    );
    const hold = screen.getByTestId("hold-to-confirm-1400");

    await fireEvent(hold, "pressIn");
    await act(async () => {
      jest.advanceTimersByTime(1399);
    });
    expect(authenticate).not.toHaveBeenCalled();
    await act(async () => {
      jest.advanceTimersByTime(1);
      await Promise.resolve();
    });

    expect(authenticate).toHaveBeenCalledTimes(1);
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        escalationAcknowledged: true,
        idempotencyKey: "elevated-key",
      }),
    );
    expect(await screen.findByText("No automatic resubmission")).toBeTruthy();
  });

  it("resets interrupted, backgrounded, and screen-reader holds safely", async () => {
    jest.useFakeTimers();
    const confirm = jest.fn();
    let appStateListener: ((state: AppStateStatus) => void) | undefined;
    jest.spyOn(AppState, "addEventListener").mockImplementation(
      (_event, listener) => {
        appStateListener = listener;
        return { remove: jest.fn() };
      },
    );
    const screen = await render(
      <HoldToConfirm
        label="Hold to approve trade"
        durationMs={1400}
        disabled={false}
        onConfirm={confirm}
        accessibilityHint="Hold continuously to confirm this elevated-risk approval"
      />,
    );
    const hold = screen.getByTestId("hold-to-confirm-1400");

    await fireEvent(hold, "pressIn");
    await fireEvent(hold, "pressOut");
    await act(async () => {
      jest.advanceTimersByTime(1400);
    });
    expect(confirm).not.toHaveBeenCalled();

    await fireEvent(hold, "pressIn");
    await act(async () => {
      appStateListener?.("background");
      jest.advanceTimersByTime(1400);
    });
    expect(confirm).not.toHaveBeenCalled();

    await fireEvent(hold, "accessibilityAction", {
      nativeEvent: { actionName: "activate" },
    });
    await act(async () => {
      jest.advanceTimersByTime(1399);
    });
    expect(confirm).not.toHaveBeenCalled();
    await act(async () => {
      jest.advanceTimersByTime(1);
    });
    expect(confirm).toHaveBeenCalledTimes(1);
  });

  it("does not submit when the device is offline or the backend disables approval", async () => {
    const submit = jest.fn(async () => verifyingReceipt());
    const offline = await render(
      <GuardedTradeApproval
        trade={routineTrade}
        initialDraft={validDraft}
        online={false}
        submitApproval={submit}
      />,
    );
    await fireEvent.press(offline.getByText("Approve trade"));

    const disabled = await render(
      <GuardedTradeApproval
        trade={{
          ...routineTrade,
          blockers: ["Readiness blocked"],
          allowed_actions: { approve: false, reject: true },
        }}
        initialDraft={validDraft}
        online
        submitApproval={submit}
      />,
    );
    await fireEvent.press(disabled.getByText("Approve trade"));

    expect(submit).not.toHaveBeenCalled();
    expect(authenticate).not.toHaveBeenCalled();
  });

  it("creates one idempotency key and one request for repeated taps in flight", async () => {
    let resolveRequest: ((value: MobileActionReceipt) => void) | undefined;
    const submit = jest.fn(
      () =>
        new Promise<MobileActionReceipt>((resolve) => {
          resolveRequest = resolve;
        }),
    );
    const createKey = jest.fn(() => "one-tap-key");
    const screen = await render(
      <GuardedTradeApproval
        trade={routineTrade}
        initialDraft={validDraft}
        online
        submitApproval={submit}
        createIdempotencyKey={createKey}
      />,
    );
    const approve = screen.getByText("Approve trade");

    await fireEvent.press(approve);
    await fireEvent.press(approve);

    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(createKey).toHaveBeenCalledTimes(1);
    resolveRequest?.(verifyingReceipt());
    expect(await screen.findByText("No automatic resubmission")).toBeTruthy();
  });

  it("reconciles a lost response by known action id without a second submit", async () => {
    const actionId = "mobile-00000000-0000-4000-8000-000000000001";
    const submit = jest.fn(async () => {
      throw new MobileApiError(
        "Financial action outcome is unknown",
        "ambiguous_outcome",
        null,
        false,
      );
    });
    const reconcile = jest.fn(async () => ({
      ...verifyingReceipt(),
      action_id: actionId,
      status: "confirmed" as const,
      operator_message: "Trade confirmed",
    }));
    const screen = await render(
      <GuardedTradeApproval
        trade={routineTrade}
        initialDraft={validDraft}
        online
        submitApproval={submit}
        reconcileAction={reconcile}
        createIdempotencyKey={() => actionId}
      />,
    );

    await fireEvent.press(
      screen.getByRole("button", { name: "Approve trade" }),
    );

    expect(await screen.findByText("No automatic resubmission")).toBeTruthy();
    await waitFor(() => expect(reconcile).toHaveBeenCalledWith(actionId));
    expect(await screen.findByText("Confirmed")).toBeTruthy();
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it("persists a known action before dispatch and resumes retrying after remount", async () => {
    const actionId = "mobile-00000000-0000-4000-8000-000000000009";
    const pendingStore = createPendingStore();
    const submit = jest.fn(async () => {
      throw new MobileApiError(
        "Financial action outcome is unknown",
        "ambiguous_outcome",
        null,
        false,
      );
    });
    const first = await render(
      <GuardedTradeApproval
        trade={routineTrade}
        initialDraft={validDraft}
        online
        submitApproval={submit}
        reconcileAction={jest.fn()}
        createIdempotencyKey={() => actionId}
        pendingActionStore={pendingStore}
        pendingOwner={ownerA}
      />,
    );

    await fireEvent.press(first.getByText("Approve trade"));
    await waitFor(() =>
      expect(pendingStore.save).toHaveBeenCalledWith({
        actionId,
        entityId: routineTrade.id,
        actionType: "trade_approve",
        owner: ownerA,
        state: "pending",
      }),
    );
    await first.unmount();

    pendingStore.setCurrent({
      actionId,
      entityId: routineTrade.id,
      actionType: "trade_approve",
      owner: ownerA,
      state: "pending",
    });
    const reconcile = jest
      .fn()
      .mockRejectedValueOnce(new Error("transient tunnel drop"))
      .mockResolvedValueOnce({
        ...verifyingReceipt(),
        action_id: actionId,
        status: "confirmed",
        operator_message: "Trade confirmed",
      });
    const resumed = await render(
      <GuardedTradeApproval
        trade={routineTrade}
        initialDraft={validDraft}
        online
        submitApproval={submit}
        reconcileAction={reconcile}
        pendingActionStore={pendingStore}
        pendingOwner={ownerA}
      />,
    );

    await waitFor(() => expect(pendingStore.load).toHaveBeenCalled());
    await waitFor(() => expect(reconcile).toHaveBeenCalledTimes(2), {
      timeout: 2000,
    });
    expect(await resumed.findByText("Confirmed")).toBeTruthy();
    expect(submit).toHaveBeenCalledTimes(1);
    expect(pendingStore.clear).toHaveBeenCalledWith(actionId);
  });

  it("exposes rejection and renders a stable execute-scope denial", async () => {
    const reject = jest.fn(async () => ({
      ...verifyingReceipt(),
      status: "cancelled" as const,
      operator_message: "Trade intent rejected",
    }));
    const denied = jest.fn(async () => {
      throw new MobileApiError(
        "mobile:trade:execute required",
        "authorization",
        403,
        false,
      );
    });
    const screen = await render(
      <GuardedTradeApproval
        trade={routineTrade}
        initialDraft={validDraft}
        online
        submitApproval={denied}
        submitRejection={reject}
      />,
    );

    await fireEvent.press(screen.getByText("Reject trade"));
    await waitFor(() => expect(reject).toHaveBeenCalledTimes(1));
    await fireEvent.press(screen.getByText("Approve trade"));
    expect(
      await screen.findByText(
        "This device does not have trade execution access.",
      ),
    ).toBeTruthy();
  });

  it("revalidates edited risk controls before choosing the approval gesture", async () => {
    const validate = jest.fn(async () => ({
      intent_id: routineTrade.id,
      expected_version: routineTrade.version,
      valid: false,
      limits: routineTrade.limits,
      blockers: [],
      escalation_reasons: ["Stop is wider than the configured strategy stop"],
      requires_escalation: true,
      escalation_acknowledged: false,
    }));
    const screen = await render(
      <GuardedTradeApproval
        trade={routineTrade}
        initialDraft={validDraft}
        online
        submitApproval={jest.fn(async () => verifyingReceipt())}
        validateDraft={validate}
      />,
    );

    await fireEvent.changeText(
      screen.getByTestId("trade-field-stop_pct"),
      "35",
    );
    expect(
      await screen.findByText("Hold to approve trade", {}, { timeout: 1500 }),
    ).toBeTruthy();
    expect(validate).toHaveBeenCalledWith(
      expect.objectContaining({ stop_pct: "35" }),
    );
  });

  it("passes the captured session generation when an action 401 quarantines credentials", async () => {
    const revokeSession = jest.fn(async () => true);
    await expect(
      authenticatedRead(
        {
          generation: 12,
          token: "revoked-token",
          revokeSession,
        },
        async () => {
          throw new MobileApiError(
            "session revoked",
            "authentication",
            401,
            false,
          );
        },
      ),
    ).rejects.toMatchObject({ status: 401 });
    expect(revokeSession).toHaveBeenCalledWith(12);
  });

  it("submits functional version-bound position adjust and full-close actions", async () => {
    jest.useFakeTimers();
    const position = makeGuardedPosition();
    const adjust = jest.fn(async () => ({
      ...verifyingReceipt(),
      status: "confirmed" as const,
    }));
    const close = jest.fn(async () => verifyingReceipt());
    const screen = await render(
      <GuardedPositionActions
        position={position}
        online
        submitAdjustment={adjust}
        submitClose={close}
        createIdempotencyKey={() => "position-action-key"}
      />,
    );

    await fireEvent.press(screen.getByText("Apply exit controls"));
    await waitFor(() =>
      expect(adjust).toHaveBeenCalledWith(
        expect.objectContaining({
          expectedVersion: 7,
          stopPct: "20",
          targetPct: "40",
        }),
      ),
    );
    await fireEvent(screen.getByTestId("hold-to-confirm-1400"), "pressIn");
    await act(async () => {
      jest.advanceTimersByTime(1400);
      await Promise.resolve();
    });
    await waitFor(() =>
      expect(close).toHaveBeenCalledWith(
        expect.objectContaining({
          expectedVersion: 5,
          positionVersion: 7,
          intentId: "intent-close",
          draft: expect.objectContaining({ amount: "100%" }),
        }),
      ),
    );
  });

  it.each([401, 403, 409, 422])(
    "clears a definitive pre-receipt trade approval failure (%s)",
    async (status) => {
      const actionId = `trade-definitive-${status}`;
      const pendingStore = createPendingStore();
      const submit = jest.fn(async () => {
        throw new MobileApiError(
          "definitive rejection",
          status === 401
            ? "authentication"
            : status === 403
              ? "authorization"
              : status === 409
                ? "conflict"
                : "validation",
          status,
          false,
        );
      });
      const screen = await render(
        <GuardedTradeApproval
          trade={routineTrade}
          initialDraft={validDraft}
          online
          submitApproval={submit}
          createIdempotencyKey={() => actionId}
          pendingActionStore={pendingStore}
          pendingOwner={ownerA}
        />,
      );

      await fireEvent.press(screen.getByText("Approve trade"));
      await waitFor(() =>
        expect(pendingStore.clear).toHaveBeenCalledWith(actionId),
      );
      expect(pendingStore.current()).toBeNull();
      await screen.unmount();
    },
  );

  it("clears a definitive pre-receipt trade rejection failure", async () => {
    const actionId = "trade-reject-definitive";
    const pendingStore = createPendingStore();
    const reject = jest.fn(async () => {
      throw new MobileApiError(
        "stale intent",
        "validation",
        422,
        false,
      );
    });
    const screen = await render(
      <GuardedTradeApproval
        trade={routineTrade}
        initialDraft={validDraft}
        online
        submitApproval={jest.fn(async () => verifyingReceipt())}
        submitRejection={reject}
        createIdempotencyKey={() => actionId}
        pendingActionStore={pendingStore}
        pendingOwner={ownerA}
      />,
    );

    await fireEvent.press(screen.getByText("Reject trade"));
    await waitFor(() =>
      expect(pendingStore.clear).toHaveBeenCalledWith(actionId),
    );
    expect(pendingStore.current()).toBeNull();
  });

  it.each([401, 403, 409, 422])(
    "clears a definitive pre-receipt position failure (%s)",
    async (status) => {
      const actionId = `position-definitive-${status}`;
      const pendingStore = createPendingStore();
      const submitAdjustment = jest.fn(async () => {
        throw new MobileApiError(
          "definitive position rejection",
          status === 401
            ? "authentication"
            : status === 403
              ? "authorization"
              : status === 409
                ? "conflict"
                : "validation",
          status,
          false,
        );
      });
      const screen = await render(
        <GuardedPositionActions
          position={makeGuardedPosition()}
          online
          submitAdjustment={submitAdjustment}
          submitClose={jest.fn(async () => verifyingReceipt())}
          createIdempotencyKey={() => actionId}
          pendingActionStore={pendingStore}
          pendingOwner={ownerA}
        />,
      );

      await fireEvent.press(screen.getByText("Apply exit controls"));
      await waitFor(() =>
        expect(pendingStore.clear).toHaveBeenCalledWith(actionId),
      );
      expect(pendingStore.current()).toBeNull();
      await screen.unmount();
    },
  );

  it.each([
    ["trade", "trade_approve", routineTrade.id],
    ["position", "position_adjust_exit", "live-position-guarded"],
  ] as const)(
    "turns a permanent 404 %s reconciliation into an abandonable review",
    async (kind, actionType, entityId) => {
      const actionId = `${kind}-missing-receipt`;
      const pendingStore = createPendingStore({
        actionId,
        entityId,
        actionType,
        owner: ownerA,
        state: "pending",
      });
      const reconcile = jest.fn(async () => {
        throw new MobileApiError(
          "Mobile action receipt not found",
          "validation",
          404,
          false,
        );
      });
      const screen =
        kind === "trade"
          ? await render(
              <GuardedTradeApproval
                trade={routineTrade}
                initialDraft={validDraft}
                online
                submitApproval={jest.fn(async () => verifyingReceipt())}
                reconcileAction={reconcile}
                pendingActionStore={pendingStore}
                pendingOwner={ownerA}
              />,
            )
          : await render(
              <GuardedPositionActions
                position={makeGuardedPosition()}
                online
                submitAdjustment={jest.fn(async () => verifyingReceipt())}
                submitClose={jest.fn(async () => verifyingReceipt())}
                reconcileAction={reconcile}
                pendingActionStore={pendingStore}
                pendingOwner={ownerA}
              />,
            );

      expect(
        await screen.findByText("Review required", {}, { timeout: 2000 }),
      ).toBeTruthy();
      expect(reconcile).toHaveBeenCalledTimes(1);
      expect(pendingStore.current()).toEqual(
        expect.objectContaining({ state: "review_required" }),
      );
      await fireEvent.press(screen.getByText("Abandon pending action"));
      expect(pendingStore.current()).not.toBeNull();
      expect(
        screen.getByText(
          "Abandoning removes only local recovery state. Verify the backend outcome first.",
        ),
      ).toBeTruthy();
      await fireEvent.press(screen.getByText("Confirm abandon pending action"));
      await waitFor(() => expect(pendingStore.current()).toBeNull());
      await screen.unmount();
    },
  );

  it.each([
    [
      "trade",
      {
        actionId: "position-pending-elsewhere",
        entityId: "position-other",
        actionType: "position_close",
        owner: ownerA,
        state: "pending" as const,
      },
      "/position/position-other",
    ],
    [
      "position",
      {
        actionId: "trade-pending-elsewhere",
        entityId: "intent-other",
        actionType: "trade_reject",
        owner: ownerA,
        state: "pending" as const,
      },
      "/trade/intent-other",
    ],
  ] as const)(
    "surfaces a same-owner pending action globally from the %s screen",
    async (kind, pending, expectedRoute) => {
      const pendingStore = createPendingStore(pending);
      const openPending = jest.fn();
      const reconcile = jest.fn(async () => verifyingReceipt());
      const submitTrade = jest.fn(async () => verifyingReceipt());
      const submitPosition = jest.fn(async () => verifyingReceipt());
      const screen =
        kind === "trade"
          ? await render(
              <GuardedTradeApproval
                trade={routineTrade}
                initialDraft={validDraft}
                online
                submitApproval={submitTrade}
                reconcileAction={reconcile}
                pendingActionStore={pendingStore}
                pendingOwner={ownerA}
                onOpenPendingAction={(action) =>
                  openPending(pendingActionRoute(action))
                }
              />,
            )
          : await render(
              <GuardedPositionActions
                position={makeGuardedPosition()}
                online
                submitAdjustment={submitPosition}
                submitClose={submitPosition}
                reconcileAction={reconcile}
                pendingActionStore={pendingStore}
                pendingOwner={ownerA}
                onOpenPendingAction={(action) =>
                  openPending(pendingActionRoute(action))
                }
              />,
            );

      expect(await screen.findByText("Review required")).toBeTruthy();
      expect(
        screen.getByText(
          "Another financial action is pending. Open its owning screen to reconcile it.",
        ),
      ).toBeTruthy();
      expect(reconcile).not.toHaveBeenCalled();
      expect(submitTrade).not.toHaveBeenCalled();
      expect(submitPosition).not.toHaveBeenCalled();
      expect(pendingStore.current()).toEqual(pending);

      await fireEvent.press(screen.getByText("Open pending action"));
      expect(openPending).toHaveBeenCalledWith(expectedRoute);
      expect(pendingStore.current()).toEqual(pending);

      await fireEvent.press(screen.getByText("Abandon pending action"));
      expect(pendingStore.current()).toEqual(pending);
      await fireEvent.press(screen.getByText("Confirm abandon pending action"));
      await waitFor(() => expect(pendingStore.current()).toBeNull());
      expect(submitTrade).not.toHaveBeenCalled();
      expect(submitPosition).not.toHaveBeenCalled();
      await screen.unmount();
    },
  );

  it("requires review then abandon when a pending action belongs to an old pairing", async () => {
    const oldActionId = "old-pairing-action";
    const newActionId = "new-pairing-action";
    const pendingStore = createPendingStore({
      actionId: oldActionId,
      entityId: routineTrade.id,
      actionType: "trade_approve",
      owner: ownerA,
      state: "pending",
    });
    const reconcile = jest.fn(async () => verifyingReceipt());
    const submit = jest.fn(async () => verifyingReceipt());
    const screen = await render(
      <GuardedTradeApproval
        trade={routineTrade}
        initialDraft={validDraft}
        online
        submitApproval={submit}
        reconcileAction={reconcile}
        createIdempotencyKey={() => newActionId}
        pendingActionStore={pendingStore}
        pendingOwner={ownerB}
      />,
    );

    expect(await screen.findByText("Review required")).toBeTruthy();
    expect(reconcile).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByText("Abandon pending action"));
    expect(pendingStore.current()).not.toBeNull();
    await fireEvent.press(screen.getByText("Confirm abandon pending action"));
    await waitFor(() => expect(pendingStore.current()).toBeNull());
    await fireEvent.press(screen.getByText("Approve trade"));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(pendingStore.current()).toEqual(
      expect.objectContaining({
        actionId: newActionId,
        owner: ownerB,
        state: "pending",
      }),
    );
  });

  it("clamps bounded fields to backend-provided limits", async () => {
    const onChange = jest.fn();
    const screen = await render(
      <BoundedTradeForm
        draft={validDraft}
        limits={routineTrade.limits}
        disabled={false}
        onChange={onChange}
      />,
    );

    await fireEvent.changeText(screen.getByTestId("trade-field-amount"), "999");
    await fireEvent.changeText(
      screen.getByTestId("trade-field-slippage_pct"),
      "99",
    );
    await fireEvent.changeText(screen.getByTestId("trade-field-stop_pct"), "250");
    await fireEvent.changeText(screen.getByTestId("trade-field-target_pct"), "250");

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ amount: "0.05" }),
    );
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ slippage_pct: "1" }),
    );
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ stop_pct: "100" }),
    );
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ target_pct: "100" }),
    );
  });

  it("renders review-required reconciliation as a manual stop state", async () => {
    const screen = await render(
      <ActionStatus
        receipt={{
          ...verifyingReceipt(),
          status: "review_required",
          operator_message: "Review the signature manually.",
        }}
      />,
    );

    expect(screen.getByText("Review required")).toBeTruthy();
    expect(screen.getByText("Review the signature manually.")).toBeTruthy();
  });
});
