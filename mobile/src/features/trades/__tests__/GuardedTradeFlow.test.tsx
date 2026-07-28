import * as LocalAuthentication from "expo-local-authentication";
import React from "react";
import {
  fireEvent,
  render,
  waitFor,
} from "@testing-library/react-native";

import { HoldToConfirm } from "../../../components/actions/HoldToConfirm";
import { MobileApiError } from "../../../core/api/errors";
import { ActionStatus } from "../ActionStatus";
import { BoundedTradeForm } from "../BoundedTradeForm";
import { GuardedTradeApproval } from "../TradeDetailScreen";
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

    await fireEvent(hold, "longPress");

    await waitFor(() => expect(authenticate).toHaveBeenCalledTimes(1));
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        escalationAcknowledged: true,
        idempotencyKey: "elevated-key",
      }),
    );
    expect(await screen.findByText("No automatic resubmission")).toBeTruthy();
  });

  it("resets an interrupted hold without submitting", async () => {
    const confirm = jest.fn();
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

    expect(confirm).not.toHaveBeenCalled();
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
