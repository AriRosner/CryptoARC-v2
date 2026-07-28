export interface PositionSummary {
  id: string;
  mode: "paper" | "live";
  symbol: string;
  mint: string;
  status: string;
  opened_at: string | null;
  updated_at: string;
  cost_basis_sol: number;
  value_sol: number;
  realized_pnl_sol: number;
  unrealized_pnl_sol: number;
  pnl_pct: number;
  pnl_approximate: boolean;
  mark_fresh: boolean;
  mark_age_seconds: number | null;
  mark_source: string;
}

export interface PositionDetail extends PositionSummary {
  wallet_label: string;
  token_balance: number;
  mark: {
    price_sol: number;
    source: string;
    confidence: number;
    observed_at: string | null;
    age_seconds: number | null;
    fresh: boolean;
  };
  pnl: {
    realized_sol: number;
    unrealized_sol: number;
    total_sol: number;
    percentage: number;
    approximate: boolean;
    confidence: string;
    notes: string[];
  };
  reconciliation_status: string;
  allowed_actions: {
    adjust_exit: boolean;
    close: boolean;
    reason: string;
  };
}

export interface PositionsPayload {
  artifact_type: "cryptoarc_mobile_positions";
  format_version: 1;
  generated_at: string;
  freshness: import("../portfolio/types").MobileFreshness;
  positions: PositionSummary[];
}
