import type { MobileActionReceipt } from "../trades/types";

export type TreasuryAction =
  | "withdrawal"
  | "profit_sweep"
  | "rent_recovery";

export interface WalletFreshness {
  status: "fresh" | "stale" | "unavailable";
  generated_at: string;
  age_seconds: number;
  stale_after_seconds: number;
  approximate: boolean;
}

export interface WalletBalanceGroup {
  asset: string;
  total: number;
  committed: number;
  available: number;
  reserved: number;
  approximate: boolean;
}

export interface MobileWalletPayload {
  artifact_type: "cryptoarc_mobile_wallet";
  format_version: 1;
  generated_at: string;
  wallet_public_key: string;
  total_value_sol: number;
  freshness: WalletFreshness;
  balances: WalletBalanceGroup[];
  allocation: Array<{
    asset: string;
    value_sol: number;
    percentage: number;
  }>;
  pnl: {
    realized_sol: number;
    unrealized_sol: number;
    approximate: boolean;
  };
  fees: {
    network_sol: number;
    priority_sol: number;
    total_sol: number;
    approximate: boolean;
  };
  rent: {
    recoverable_sol: number;
    eligible_accounts: number;
    eligible_token_accounts: string[];
    status: string;
    approximate: boolean;
  };
  reconciliation: {
    status: string;
    last_reconciled_at: string | null;
    approximate: boolean;
  };
  health: {
    rpc: string;
    signer: string;
    backend: string;
    readiness: string;
    kill_switch: string;
  };
}

export interface MobileWalletTransaction {
  id: string;
  action: TreasuryAction;
  asset: string;
  amount: string;
  destination: string;
  status: string;
  created_at: string;
  transaction_signature: string;
}

export interface MobileWalletTransactionsPayload {
  artifact_type: "cryptoarc_mobile_wallet_transactions";
  format_version: 1;
  generated_at: string;
  transactions: MobileWalletTransaction[];
}

export interface MobileDestinationAuthorization {
  id: string;
  device_id: string;
  action: TreasuryAction;
  address: string;
  asset: string;
  max_amount: string;
  purpose: string;
  created_at: string;
  expires_at: string;
  used_at: string | null;
  status: "active" | "used" | "expired";
}

export interface MobileDestinationsPayload {
  artifact_type: "cryptoarc_mobile_destinations";
  format_version: 1;
  generated_at: string;
  destinations: MobileDestinationAuthorization[];
}

export interface MobileTreasuryPreview {
  preview_id: string;
  action: TreasuryAction;
  destination: string;
  asset: string;
  amount: string;
  expected_fee_sol: string;
  remaining_balance_sol: string;
  authorization_id: string;
  expires_at: string;
  warnings: string[];
  token_accounts: string[];
  source_wallet_public_key: string;
  purpose: string;
}

export interface TreasuryPreviewInput {
  authorizationId: string;
  address: string;
  asset: string;
  amount: string;
  tokenAccounts?: string[];
}

export interface TreasuryExecuteInput extends TreasuryPreviewInput {
  previewId: string;
  idempotencyKey: string;
}

export type TreasuryReceipt = MobileActionReceipt;
