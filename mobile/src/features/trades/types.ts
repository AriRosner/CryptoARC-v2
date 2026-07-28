export type MobileActionStatusValue =
  | "pending"
  | "verifying"
  | "confirmed"
  | "failed"
  | "cancelled"
  | "expired"
  | "review_required";

export interface MobileTradeDraft {
  amount: string;
  slippage_pct: string;
  stop_pct: string | null;
  target_pct: string | null;
}

export interface NumericLimit {
  min: number;
  max: number;
}

export interface MobileTradeLimits {
  amount: NumericLimit & { unit: string };
  slippage_pct: NumericLimit;
  stop_pct: NumericLimit;
  target_pct: NumericLimit;
}

export interface MobileTradeSummary {
  id: string;
  version: number;
  action: "buy" | "sell";
  symbol: string;
  mint: string;
  amount: string;
  status: string;
  reason: string;
  source: string;
  updated_at: string;
  expires_at: string | null;
  quote: {
    status: string;
    slippage_pct: number;
    expires_at: string | null;
    stale: boolean;
  };
  simulation: {
    status: string;
    ok: boolean;
    warning: string;
    error: string;
  };
  limits: MobileTradeLimits;
  blockers: string[];
  escalation_reasons: string[];
  requires_escalation: boolean;
  allowed_actions: {
    approve: boolean;
    reject: boolean;
  };
}

export type MobileTradeDetail = MobileTradeSummary;

export interface MobileTradesPayload {
  artifact_type: "cryptoarc_mobile_trades";
  format_version: 1;
  generated_at: string;
  trades: MobileTradeSummary[];
}

export interface MobileTradeValidation {
  intent_id: string;
  expected_version: number;
  valid: boolean;
  limits: MobileTradeLimits;
  blockers: string[];
  escalation_reasons: string[];
  requires_escalation: boolean;
  escalation_acknowledged: boolean;
}

export interface MobileActionReceipt {
  action_id: string;
  status: MobileActionStatusValue;
  submitted_at: string;
  updated_at: string;
  operator_message: string;
  reconcile_after_ms: number;
}

export interface GuardedApprovalInput {
  expectedVersion: number;
  draft: MobileTradeDraft;
  escalationAcknowledged: boolean;
  idempotencyKey: string;
}
