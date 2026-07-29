import * as LocalAuthentication from "expo-local-authentication";
import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import {
  TEST_PENDING_ACTION_OWNER,
  type PendingActionStore,
  type PendingMobileAction,
} from "../../trades/pendingAction";
import { ProfitSweepSheet } from "../ProfitSweepSheet";
import { RentRecoverySheet } from "../RentRecoverySheet";
import { WalletScreen } from "../WalletScreen";
import {
  TreasuryPendingRecovery,
  WithdrawalScreen,
} from "../WithdrawalScreen";
import type {
  MobileTreasuryPreview,
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
  };
}

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
    const view = await render(
      <WalletScreen
        wallet={wallet}
        transactions={transactions}
        loading={false}
        onRefresh={jest.fn()}
        onWithdraw={jest.fn()}
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
});
