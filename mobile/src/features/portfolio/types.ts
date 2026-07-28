import type { PositionSummary } from "../positions/types";

export type PortfolioTimeframe = "1d" | "1w" | "1m" | "all";

export interface MobileFreshness {
  status: "fresh" | "stale" | "unavailable";
  generated_at: string;
  age_seconds: number;
  stale_after_seconds: number;
  approximate_pnl: boolean;
}

export interface PortfolioSummary {
  equity_sol: number | null;
  tracked_value_sol: number;
  cost_basis_sol: number;
  net_pnl_sol: number;
  realized_pnl_sol: number;
  unrealized_pnl_sol: number;
  win_rate_pct: number;
  health_score: number;
  open_positions: number;
  closed_trades: number;
}

export interface PortfolioPoint {
  at: string;
  net_pnl_sol: number;
  paper_pnl_sol: number;
  live_pnl_sol: number;
  current_snapshot: boolean;
  approximate: boolean;
}

export interface PortfolioAllocation {
  key: string;
  label: string;
  value_sol: number;
  percentage: number;
  mode: "paper" | "live";
}

export interface PortfolioPayload {
  artifact_type: "cryptoarc_mobile_portfolio";
  format_version: 1;
  generated_at: string;
  timeframe: PortfolioTimeframe;
  freshness: MobileFreshness;
  summary: PortfolioSummary;
  series: PortfolioPoint[];
  allocation: PortfolioAllocation[];
  positions: PositionSummary[];
}
