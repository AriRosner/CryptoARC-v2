import {
  mobileAction,
  mobileGet,
  type MobileActionOptions,
  type MobileGetOptions,
} from "../../core/api/client";
import type {
  MobileDestinationsPayload,
  MobileTreasuryPreview,
  MobileWalletPayload,
  MobileWalletTransactionsPayload,
  TreasuryAction,
  TreasuryExecuteInput,
  TreasuryPreviewInput,
  TreasuryReceipt,
} from "./types";

type ConnectionOptions = Pick<
  MobileActionOptions<unknown>,
  "apiBaseUrl" | "token" | "timeoutMs" | "signal" | "headers"
>;

const actionPaths: Record<TreasuryAction, string> = {
  withdrawal: "withdrawals",
  profit_sweep: "profit-sweeps",
  rent_recovery: "rent-recovery",
};

function treasuryBody(input: TreasuryPreviewInput, previewId = "") {
  return {
    authorization_id: input.authorizationId,
    preview_id: previewId,
    address: input.address,
    asset: input.asset,
    amount: input.amount,
    token_accounts: input.tokenAccounts ?? [],
  };
}

export function fetchWallet(
  options?: MobileGetOptions,
): Promise<MobileWalletPayload> {
  return mobileGet<MobileWalletPayload>("/api/mobile/wallet", options);
}

export function fetchWalletTransactions(
  options?: MobileGetOptions,
): Promise<MobileWalletTransactionsPayload> {
  return mobileGet<MobileWalletTransactionsPayload>(
    "/api/mobile/wallet/transactions",
    options,
  );
}

export function fetchDestinations(
  options?: MobileGetOptions,
): Promise<MobileDestinationsPayload> {
  return mobileGet<MobileDestinationsPayload>(
    "/api/mobile/wallet/destinations",
    options,
  );
}

export function previewTreasuryAction(
  action: TreasuryAction,
  input: TreasuryPreviewInput,
  options: ConnectionOptions = {},
): Promise<MobileTreasuryPreview> {
  return mobileAction<
    MobileTreasuryPreview,
    ReturnType<typeof treasuryBody>
  >(`/api/mobile/wallet/${actionPaths[action]}/preview`, {
    ...options,
    body: treasuryBody(input),
    idempotencyKey: `preview-${input.authorizationId}`,
  });
}

export function executeTreasuryAction(
  action: TreasuryAction,
  input: TreasuryExecuteInput,
  options: ConnectionOptions = {},
): Promise<TreasuryReceipt> {
  return mobileAction<TreasuryReceipt, ReturnType<typeof treasuryBody>>(
    `/api/mobile/wallet/${actionPaths[action]}`,
    {
      ...options,
      body: treasuryBody(input, input.previewId),
      idempotencyKey: input.idempotencyKey,
    },
  );
}

export function fetchTreasuryAction(
  actionId: string,
  options?: MobileGetOptions,
): Promise<TreasuryReceipt> {
  return mobileGet<TreasuryReceipt>(
    `/api/mobile/wallet/actions/${encodeURIComponent(actionId)}`,
    options,
  );
}
