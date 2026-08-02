import * as LocalAuthentication from "expo-local-authentication";
import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import {
  TEST_PENDING_ACTION_OWNER,
  pendingActionRoute,
  type PendingActionStore,
  type PendingMobileAction,
} from "../../trades/pendingAction";
import { ProfitSweepSheet } from "../ProfitSweepSheet";
import { RentRecoverySheet } from "../RentRecoverySheet";
import { WalletScreen } from "../WalletScreen";
import {
  TreasuryPreviewError,
  TreasuryPendingRecovery,
  WithdrawalScreen,
} from "../WithdrawalScreen";
import type {
  MobileTreasuryPreview,
  MobileDestinationAuthorization,
  MobileWalletPayload,
  MobileWalletTransaction,
} from "../types";

const authenticate = LocalAuthentication.authenticateAsync as jest.Mock;

const wallet: MobileWalletPayload = {
  artifact_type: "cryptoarc_mobile_wallet",
  format_version: 1,
  generated_at: "2026-07-29T14:00:00Z",
  wallet_public_key: "WalletTreasurySource1111111111111111111111111",
  total_value_sol: 1.25,
  freshness: {
    status: "fresh",
    generated_at: "2026-07-29T14:00:00Z",
    age_seconds: 2,
    stale_after_seconds: 30,
    approximate: true,
  },
  balances: [
    {
      asset: "SOL",
      total: 1.25,
      committed: 0.4,
      available: 0.7,
      reserved: 0.15,
      approximate: true,
    },
  ],
  allocation: [{ asset: "SOL", value_sol: 1.25, percentage: 100 }],
  pnl: { realized_sol: 0.2, unrealized_sol: 0.1, approximate: true },
  fees: {
    network_sol: 0.001,
    priority_sol: 0.0002,
    total_sol: 0.0012,
    approximate: false,
  },
  rent: {
    recoverable_sol: 0.004,
    eligible_accounts: 2,
    eligible_token_accounts: [
      "RentTokenAccount11111111111111111111111111111",
      "RentTokenAccount22222222222222222222222222222",
    ],
    status: "ready",
    approximate: false,
  },
  reconciliation: {
    status: "matched",
    last_reconciled_at: "2026-07-29T13:59:55Z",
    approximate: false,
  },
  health: {
    rpc: "healthy",
    signer: "healthy",
    backend: "armed",
    readiness: "ready",
    kill_switch: "clear",
  },
};

const transactions: MobileWalletTransaction[] = [
  {
    id: "tx-public-1",
    action: "withdrawal",
    asset: "SOL",
    amount: "0.2",
    destination: "DestinationTreasury111111111111111111111111",
    status: "confirmed",
    created_at: "2026-07-29T13:58:00Z",
    transaction_signature: "PublicSignature111",
  },
];

function preview(
  action: MobileTreasuryPreview["action"] = "withdrawal",
): MobileTreasuryPreview {
  return {
    preview_id: `${action}-preview`,
    action,
    destination: "DestinationTreasury111111111111111111111111",
    asset: "SOL",
    amount: "0.2",
    expected_fee_sol: "0.000005",
    remaining_balance_sol: "1.049995",
    authorization_id: `${action}-authorization`,
    expires_at: "2026-07-29T14:05:00Z",
    warnings: ["Treasury movement requires elevated confirmation."],
    token_accounts: [],
    source_wallet_public_key:
      "WalletTreasurySource1111111111111111111111111",
    purpose: `${action} operator authorization`,
  };
}

const destinations: MobileDestinationAuthorization[] = [
  {
    id: "withdrawal-authorization",
    device_id: "test-device",
    action: "withdrawal",
    address: "DestinationTreasury111111111111111111111111",
    asset: "SOL",
    max_amount: "0.2",
    purpose: "manual withdrawal",
    created_at: "2026-07-29T14:00:00Z",
    expires_at: "2026-07-29T14:05:00Z",
    used_at: null,
    status: "active",
  },
  {
    id: "profit-authorization",
    device_id: "test-device",
    action: "profit_sweep",
    address: "ProfitDestination111111111111111111111111111",
    asset: "SOL",
    max_amount: "0.025",
    purpose: "configured profit sweep",
    created_at: "2026-07-29T14:00:00Z",
    expires_at: "2026-07-29T14:05:00Z",
    used_at: null,
    status: "active",
  },
  {
    id: "rent-authorization",
    device_id: "test-device",
    action: "rent_recovery",
    address: wallet.wallet_public_key,
    asset: "SOL",
    max_amount: "0.004",
    purpose: "eligible rent recovery",
    created_at: "2026-07-29T14:00:00Z",
    expires_at: "2026-07-29T14:05:00Z",
    used_at: null,
    status: "active",
  },
];

function pendingStore(initial: PendingMobileAction | null = null) {
  let pending = initial;
  const store: PendingActionStore = {
    load: jest.fn(async () => pending),
    save: jest.fn(async (action) => {
      pending = action;
    }),
    clear: jest.fn(async (actionId) => {
      if (pending?.actionId === actionId) pending = null;
    }),
  };
  return { store, current: () => pending };
}

describe("wallet analytics and guarded treasury", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    authenticate.mockResolvedValue({ success: true });
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.clearAllMocks();
  });

  it("renders balance groups, allocation, fees, rent, reconciliation, health, and transactions", async () => {
    const onWithdraw = jest.fn();
    const onProfitSweep = jest.fn();
    const onRentRecovery = jest.fn();
    const view = await render(
      <WalletScreen
        wallet={wallet}
        transactions={transactions}
        destinations={destinations}
        loading={false}
        onRefresh={jest.fn()}
        onWithdraw={onWithdraw}
        onProfitSweep={onProfitSweep}
        onRentRecovery={onRentRecovery}
      />,
    );

    expect(view.getByText("Committed")).toBeTruthy();
    expect(view.getByText("0.400000 SOL")).toBeTruthy();
    expect(view.getByText("Available")).toBeTruthy();
    expect(view.getByText("0.700000 SOL")).toBeTruthy();
    expect(view.getByText("Reserved")).toBeTruthy();
    expect(view.getByText("0.150000 SOL")).toBeTruthy();
    expect(view.getByText("Approximate")).toBeTruthy();
    expect(view.getByText("100.0%")).toBeTruthy();
    expect(view.getByText("0.001200 SOL")).toBeTruthy();
    expect(view.getByText("0.004000 SOL")).toBeTruthy();
    expect(view.getByText("matched")).toBeTruthy();
    expect(view.getByText("RPC healthy")).toBeTruthy();
    expect(view.getByText("Signer healthy")).toBeTruthy();
    expect(view.getByText("Withdrawal")).toBeTruthy();
    expect(view.getByText("0.2 SOL")).toBeTruthy();
    await fireEvent.press(view.getByText("Review withdrawal"));
    await fireEvent.press(view.getByText("Review profit sweep"));
    await fireEvent.press(view.getByText("Review rent recovery"));
    expect(onWithdraw).toHaveBeenCalledTimes(1);
    expect(onProfitSweep).toHaveBeenCalledTimes(1);
    expect(onRentRecovery).toHaveBeenCalledTimes(1);
  });

  it("preserves wallet content during a background refresh", async () => {
    const view = await render(
      <WalletScreen
        wallet={wallet}
        transactions={transactions}
        destinations={destinations}
        loading
        onRefresh={jest.fn()}
      />,
    );

    expect(view.getByText("0.400000 SOL")).toBeTruthy();
    expect(view.getByLabelText("Syncing wallet")).toBeTruthy();
    expect(view.queryByTestId("wallet-initial-skeleton")).toBeNull();
  });

  it("keeps every treasury execute disabled offline", async () => {
    const execute = jest.fn();
    const props = {
      online: false,
      execute,
      reconcileAction: jest.fn(),
      createIdempotencyKey: () => "offline-action",
      pendingActionStore: pendingStore().store,
      pendingOwner: TEST_PENDING_ACTION_OWNER,
    };

    const view = await render(
      <>
        <WithdrawalScreen preview={preview()} {...props} />
        <ProfitSweepSheet preview={preview("profit_sweep")} {...props} />
        <RentRecoverySheet preview={preview("rent_recovery")} {...props} />
      </>,
    );

    expect(view.getAllByText("Unavailable offline")).toHaveLength(3);
    expect(view.queryAllByTestId("hold-to-confirm-1400")).toHaveLength(0);
    expect(execute).not.toHaveBeenCalled();
    expect(authenticate).not.toHaveBeenCalled();
  });

  it.each([
    ["withdrawal", WithdrawalScreen, preview("withdrawal")],
    ["profit sweep", ProfitSweepSheet, preview("profit_sweep")],
    ["rent recovery", RentRecoverySheet, preview("rent_recovery")],
  ] as const)(
    "requires fresh biometric plus a 1400ms hold for %s",
    async (_, Component, actionPreview) => {
      const execute = jest.fn(async () => ({
        action_id: `${actionPreview.action}-action`,
        status: "pending" as const,
        submitted_at: "2026-07-29T14:00:00Z",
        updated_at: "2026-07-29T14:00:00Z",
        operator_message: "Treasury request submitted",
        reconcile_after_ms: 1000,
      }));
      const pending = pendingStore();
      const view = await render(
        <Component
          preview={actionPreview}
          online
          execute={execute}
          reconcileAction={jest.fn()}
          createIdempotencyKey={() => `${actionPreview.action}-action`}
          pendingActionStore={pending.store}
          pendingOwner={TEST_PENDING_ACTION_OWNER}
        />,
      );

      await fireEvent.press(view.getByText("Authenticate treasury action"));
      expect(authenticate).toHaveBeenCalledTimes(1);
      expect(execute).not.toHaveBeenCalled();
      const hold = await view.findByTestId("hold-to-confirm-1400");
      await fireEvent(hold, "pressIn");
      await act(async () => {
        jest.advanceTimersByTime(1399);
      });
      expect(execute).not.toHaveBeenCalled();
      await act(async () => {
        jest.advanceTimersByTime(1);
      });
      await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
      expect(execute).toHaveBeenCalledWith(
        expect.objectContaining({
          idempotencyKey: `${actionPreview.action}-action`,
          previewId: actionPreview.preview_id,
          authorizationId: actionPreview.authorization_id,
        }),
      );
      expect(pending.store.save).toHaveBeenCalledWith(
        expect.objectContaining({
          actionId: `${actionPreview.action}-action`,
          actionType: actionPreview.action,
          owner: TEST_PENDING_ACTION_OWNER,
        }),
      );
    },
  );

  it("persists an ambiguous request and reconciles after restart without resubmitting", async () => {
    const actionId = "restart-withdrawal";
    const pending = pendingStore({
      actionId,
      entityId: preview().authorization_id,
      actionType: "withdrawal",
      owner: TEST_PENDING_ACTION_OWNER,
      state: "pending",
    });
    const execute = jest.fn();
    const reconcile = jest.fn(async () => ({
      action_id: actionId,
      status: "confirmed" as const,
      submitted_at: "2026-07-29T14:00:00Z",
      updated_at: "2026-07-29T14:01:00Z",
      operator_message: "Treasury transaction confirmed",
      reconcile_after_ms: 1000,
    }));

    const view = await render(
      <WithdrawalScreen
        preview={preview()}
        online
        execute={execute}
        reconcileAction={reconcile}
        pendingActionStore={pending.store}
        pendingOwner={TEST_PENDING_ACTION_OWNER}
      />,
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(view.getAllByText("Verifying outcome")).toHaveLength(2);
    await act(async () => {
      jest.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(reconcile).toHaveBeenCalledWith(actionId));
    expect(execute).not.toHaveBeenCalled();
    expect(await view.findByText("Treasury transaction confirmed")).toBeTruthy();
    expect(pending.store.clear).toHaveBeenCalledWith(actionId);
  });

  it("returns the exact rent token accounts from preview to execute", async () => {
    const rentPreview = {
      ...preview("rent_recovery"),
      token_accounts: [
        "RentTokenAccount11111111111111111111111111111",
        "RentTokenAccount22222222222222222222222222222",
      ],
    } as MobileTreasuryPreview;
    const execute = jest.fn(async () => ({
      action_id: "rent-bound-action",
      status: "pending" as const,
      submitted_at: "2026-07-29T14:00:00Z",
      updated_at: "2026-07-29T14:00:00Z",
      operator_message: "Rent recovery submitted",
      reconcile_after_ms: 1000,
    }));
    const view = await render(
      <RentRecoverySheet
        preview={rentPreview}
        online
        execute={execute}
        reconcileAction={jest.fn()}
        createIdempotencyKey={() => "rent-bound-action"}
        pendingActionStore={pendingStore().store}
        pendingOwner={TEST_PENDING_ACTION_OWNER}
      />,
    );

    await fireEvent.press(view.getByText("Authenticate treasury action"));
    const hold = await view.findByTestId("hold-to-confirm-1400");
    await fireEvent(hold, "pressIn");
    await act(async () => {
      jest.advanceTimersByTime(1400);
    });
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    expect(execute).toHaveBeenCalledWith(
      expect.objectContaining({
        tokenAccounts: rentPreview.token_accounts,
      }),
    );
  });

  it("never confirms from one accessibility activation and supports cancellation", async () => {
    const execute = jest.fn(async () => ({
      action_id: "accessible-action",
      status: "pending" as const,
      submitted_at: "2026-07-29T14:00:00Z",
      updated_at: "2026-07-29T14:00:00Z",
      operator_message: "Treasury request submitted",
      reconcile_after_ms: 1000,
    }));
    const view = await render(
      <WithdrawalScreen
        preview={preview()}
        online
        execute={execute}
        reconcileAction={jest.fn()}
        createIdempotencyKey={() => "accessible-action"}
        pendingActionStore={pendingStore().store}
        pendingOwner={TEST_PENDING_ACTION_OWNER}
      />,
    );
    await fireEvent.press(view.getByText("Authenticate treasury action"));
    const hold = await view.findByTestId("hold-to-confirm-1400");

    await fireEvent(hold, "accessibilityAction", {
      nativeEvent: { actionName: "activate" },
    });
    await act(async () => {
      jest.advanceTimersByTime(1400);
    });
    expect(execute).not.toHaveBeenCalled();
    expect(
      view.getByText(
        "Accessibility confirmation armed. Activate again after the safety delay.",
      ),
    ).toBeTruthy();

    await fireEvent(hold, "accessibilityAction", {
      nativeEvent: { actionName: "escape" },
    });
    await fireEvent(hold, "accessibilityAction", {
      nativeEvent: { actionName: "activate" },
    });
    await act(async () => {
      jest.advanceTimersByTime(1399);
    });
    await fireEvent(hold, "accessibilityAction", {
      nativeEvent: { actionName: "activate" },
    });
    expect(execute).not.toHaveBeenCalled();
    await act(async () => {
      jest.advanceTimersByTime(1);
    });
    await fireEvent(hold, "accessibilityAction", {
      nativeEvent: { actionName: "activate" },
    });
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
  });

  it("retains review-required recovery until deliberate resolution", async () => {
    const actionId = "review-required-action";
    const pending = pendingStore({
      actionId,
      entityId: preview().authorization_id,
      actionType: "withdrawal",
      owner: TEST_PENDING_ACTION_OWNER,
      state: "pending",
    });
    const reconcile = jest.fn(async () => ({
      action_id: actionId,
      status: "review_required" as const,
      submitted_at: "2026-07-29T14:00:00Z",
      updated_at: "2026-07-29T14:01:00Z",
      operator_message: "Signature unavailable; review locally",
      reconcile_after_ms: 1000,
    }));
    const view = await render(
      <WithdrawalScreen
        preview={preview()}
        online
        execute={jest.fn()}
        reconcileAction={reconcile}
        pendingActionStore={pending.store}
        pendingOwner={TEST_PENDING_ACTION_OWNER}
      />,
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      jest.advanceTimersByTime(1000);
    });
    expect(
      await view.findByText("Signature unavailable; review locally"),
    ).toBeTruthy();
    expect(pending.store.clear).not.toHaveBeenCalled();
    expect(pending.current()).toEqual(
      expect.objectContaining({
        actionId,
        state: "review_required",
      }),
    );
  });

  it("opens a same-owner cross-entity pending action without allowing abandon", async () => {
    const crossEntity = {
      actionId: "profit-elsewhere",
      entityId: "profit-authorization",
      actionType: "profit_sweep",
      owner: TEST_PENDING_ACTION_OWNER,
      state: "pending" as const,
    };
    const pending = pendingStore(crossEntity);
    const openPending = jest.fn();
    const view = await render(
      <WithdrawalScreen
        preview={preview()}
        online
        execute={jest.fn()}
        reconcileAction={jest.fn()}
        pendingActionStore={pending.store}
        pendingOwner={TEST_PENDING_ACTION_OWNER}
        onOpenPendingAction={openPending}
      />,
    );

    await fireEvent.press(await view.findByText("Open pending action"));
    expect(openPending).toHaveBeenCalledWith(crossEntity);
    expect(view.queryByText("Abandon pending action")).toBeNull();
    expect(pending.store.clear).not.toHaveBeenCalled();
  });

  it("routes every treasury pending action to a reachable recovery screen", () => {
    expect(
      pendingActionRoute({
        actionId: "profit",
        entityId: "profit-auth",
        actionType: "profit_sweep",
        owner: TEST_PENDING_ACTION_OWNER,
        state: "pending",
      }),
    ).toBe("/wallet/treasury?action=profit_sweep");
    expect(
      pendingActionRoute({
        actionId: "rent",
        entityId: "rent-auth",
        actionType: "rent_recovery",
        owner: TEST_PENDING_ACTION_OWNER,
        state: "pending",
      }),
    ).toBe("/wallet/treasury?action=rent_recovery");
  });

  it("does not reconcile or replace a pending action owned by another pairing", async () => {
    const pending = pendingStore({
      actionId: "old-pairing-action",
      entityId: preview().authorization_id,
      actionType: "withdrawal",
      owner: {
        apiBaseUrl: "https://old.example",
        deviceId: "old-device",
        sessionId: "old-session",
      },
      state: "pending",
    });
    const execute = jest.fn();
    const reconcile = jest.fn();

    const view = await render(
      <WithdrawalScreen
        preview={preview()}
        online
        execute={execute}
        reconcileAction={reconcile}
        pendingActionStore={pending.store}
        pendingOwner={TEST_PENDING_ACTION_OWNER}
      />,
    );

    expect(
      await view.findByText(
        "Pending action belongs to a different pairing. Review it before abandoning.",
      ),
    ).toBeTruthy();
    expect(reconcile).not.toHaveBeenCalled();
    expect(execute).not.toHaveBeenCalled();
  });

  it("reconciles from the owner-bound registry when the original preview is gone", async () => {
    const actionId = "preview-gone-action";
    const pending = pendingStore({
      actionId,
      entityId: "authorization-after-restart",
      actionType: "withdrawal",
      owner: TEST_PENDING_ACTION_OWNER,
      state: "pending",
    });
    const reconcile = jest.fn(async () => ({
      action_id: actionId,
      status: "confirmed" as const,
      submitted_at: "2026-07-29T14:00:00Z",
      updated_at: "2026-07-29T14:01:00Z",
      operator_message: "Treasury transaction confirmed",
      reconcile_after_ms: 1000,
    }));

    const view = await render(
      <TreasuryPendingRecovery
        reconcileAction={reconcile}
        pendingActionStore={pending.store}
        pendingOwner={TEST_PENDING_ACTION_OWNER}
      />,
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(view.getAllByText("Verifying outcome")).toHaveLength(2);
    await act(async () => {
      jest.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(reconcile).toHaveBeenCalledWith(actionId));
    expect(await view.findByText("Treasury transaction confirmed")).toBeTruthy();
    expect(pending.store.clear).toHaveBeenCalledWith(actionId);
  });

  it("requires warned two-step abandonment for restart-only review state", async () => {
    const actionId = "restart-review-required";
    const pending = pendingStore({
      actionId,
      entityId: "consumed-authorization",
      actionType: "profit_sweep",
      owner: TEST_PENDING_ACTION_OWNER,
      state: "review_required",
      reviewMessage: "Signature missing; verify the chain manually.",
    });
    const reconcile = jest.fn();
    const view = await render(
      <TreasuryPendingRecovery
        reconcileAction={reconcile}
        pendingActionStore={pending.store}
        pendingOwner={TEST_PENDING_ACTION_OWNER}
      />,
    );

    expect(
      await view.findByText("Signature missing; verify the chain manually."),
    ).toBeTruthy();
    expect(reconcile).not.toHaveBeenCalled();
    await fireEvent.press(view.getByText("Abandon pending action"));
    expect(
      view.getByText(
        "Abandoning removes only local recovery state. Verify the desktop and chain outcome first.",
      ),
    ).toBeTruthy();
    expect(pending.store.clear).not.toHaveBeenCalled();
    await fireEvent.press(
      view.getByText("Confirm abandon pending action"),
    );
    expect(pending.store.clear).toHaveBeenCalledWith(actionId);
    expect(pending.current()).toBeNull();
    expect(reconcile).not.toHaveBeenCalled();
  });

  it("keeps restart recovery from another pairing review-only", async () => {
    const pending = pendingStore({
      actionId: "foreign-restart-review",
      entityId: "foreign-authorization",
      actionType: "rent_recovery",
      owner: {
        apiBaseUrl: "https://old.example",
        deviceId: "old-device",
        sessionId: "old-session",
      },
      state: "review_required",
      reviewMessage:
        "Pending action belongs to a different pairing. Review it before abandoning.",
    });
    const reconcile = jest.fn();
    const view = await render(
      <TreasuryPendingRecovery
        reconcileAction={reconcile}
        pendingActionStore={pending.store}
        pendingOwner={TEST_PENDING_ACTION_OWNER}
      />,
    );

    expect(
      await view.findByText(
        "Pending action belongs to a different pairing. Review it before abandoning.",
      ),
    ).toBeTruthy();
    expect(view.queryByText("Abandon pending action")).toBeNull();
    expect(pending.store.clear).not.toHaveBeenCalled();
    expect(reconcile).not.toHaveBeenCalled();
  });

  it("renders connected treasury preview failures as visible alerts", async () => {
    const view = await render(
      <TreasuryPreviewError message="Daily sweep cap reached" />,
    );

    const alert = view.getByText("Daily sweep cap reached");
    expect(alert).toBeTruthy();
    expect(alert.props.accessibilityRole).toBe("alert");
  });
});
