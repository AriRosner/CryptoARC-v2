export type BotStatus = "stopped" | "running";
export type TokenStatus = "detected" | "analyzing" | "buying" | "paper_bought" | "monitoring" | "selling" | "paper_sold" | "skipped";

export interface BotSettings {
  mode: "preview" | "paper" | "live_locked";
  launch_source: "mock" | "pumpportal";
  strategy_profile: "conservative" | "balanced" | "aggressive" | "scalper" | "custom";
  trade_size_sol: number;
  slippage_tolerance_pct: number;
  take_profit_pct: number;
  stop_loss_pct: number;
  daily_loss_cap_sol: number;
  wallet_balance_cap_sol: number;
  max_creator_hold_pct: number;
  trading_speed: "slow" | "normal" | "fast" | "turbo";
  max_hold_time_seconds: number;
  risk_tolerance: "low" | "medium" | "high" | "degen";
  score_threshold: number;
  max_open_positions: number;
  launch_interval_seconds: number;
  paper_price_volatility_pct: number;
  max_position_ticks: number;
  require_live_confirmation: boolean;
  detect_new_tokens: boolean;
  auto_refresh: boolean;
  filter_honeypots: boolean;
  filter_rug_risk: boolean;
  live_trading_enabled: boolean;
  min_buy_velocity: number;
  max_sell_pressure: number;
  min_metadata_score: number;
  max_token_age_seconds: number;
  source_stale_seconds: number;
  source_max_reconnects: number;
  backtest_replay_limit: number;
  raw_replay_limit: number;
  enable_trade_toasts: boolean;
  compact_table_mode: boolean;
  paper_fill_delay_ticks: number;
  paper_fee_bps: number;
  paper_price_impact_pct: number;
  paper_failed_fill_pct: number;
  duplicate_symbol_penalty: boolean;
  strict_metadata_checks: boolean;
}

export interface TokenSignal {
  id: string;
  symbol: string;
  name: string;
  mint: string;
  creator: string;
  detected_at: string;
  status: TokenStatus;
  score: number;
  reason: string;
  amount_sol: number | null;
  pnl_sol: number | null;
  success_rate_pct: number;
  age_seconds: number;
  buy_velocity: number;
  sell_pressure: number;
  metadata_score: number;
  score_breakdown: string[];
  entry_price: number | null;
  current_price: number | null;
  exit_price: number | null;
  opened_at: string | null;
  closed_at: string | null;
  ticks_held: number;
  peak_price: number | null;
  trough_price: number | null;
  unrealized_pct: number;
  creator_hold_pct: number;
  creator_launch_count: number;
  intelligence_tags: string[];
  exit_reason: string | null;
  honeypot_risk: boolean;
  rug_risk: boolean;
  decision_log: string[];
  entry_reason: string | null;
  entry_strategy_profile: string | null;
  entry_risk_filters: string[];
  slippage_paid_pct: number;
  highest_unrealized_pct: number;
  lowest_unrealized_pct: number;
  hold_duration_seconds: number;
  fill_delay_ticks_remaining: number;
  fee_paid_sol: number;
  price_impact_pct: number;
  fill_failed: boolean;
}

export interface TradeEvent {
  id: string;
  created_at: string;
  level: "info" | "warning" | "success" | "danger" | string;
  message: string;
  token_id: string | null;
}

export interface BotStats {
  total_trades: number;
  successful_trades: number;
  skipped_tokens: number;
  open_positions: number;
  closed_trades: number;
  win_rate_pct: number;
  total_pnl_sol: number;
  best_trade_sol: number;
  worst_trade_sol: number;
  average_win_sol: number;
  average_loss_sol: number;
  profit_factor: number;
  max_drawdown_sol: number;
}

export interface SourceStatus {
  source: "mock" | "pumpportal" | string;
  status: "offline" | "connecting" | "connected" | "reconnecting" | string;
  message: string;
  events_received: number;
  last_event_at: string | null;
  reconnect_attempts: number;
  raw_events_seen: number;
  normalized_events: number;
  normalization_failures: number;
  events_per_minute: number;
  last_event_age_seconds: number | null;
  health_score: number;
}

export interface BacktestResult {
  id: string;
  created_at: string;
  tokens_replayed: number;
  paper_buys: number;
  skips: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  estimated_pnl_sol: number;
  max_drawdown_sol: number;
  profit_factor: number;
  profile: string;
  risk_tolerance: string;
  pnl_curve: number[];
  trades: Array<Record<string, string | number>>;
  comparison: Array<Record<string, string | number>>;
  replay_source: string;
}

export interface SourceEvent {
  id: string;
  source: string;
  received_at: string;
  raw_payload: Record<string, unknown>;
  normalized_token_id: string | null;
  status: string;
  message: string;
}

export interface DataSummary {
  tokens: number;
  events: number;
  source_events: number;
  backtests: number;
  trades: number;
}

export interface TradeRecord {
  id: string;
  token_id: string;
  mode: string;
  strategy_profile: string;
  entry_price: number | null;
  exit_price: number | null;
  amount_sol: number | null;
  pnl_sol: number | null;
  entry_reason: string | null;
  exit_reason: string | null;
  opened_at: string | null;
  closed_at: string | null;
  hold_duration_seconds: number;
  decision_log: string[];
}

export interface SourceHealth {
  status: string;
  events_per_minute: number;
  normalized_ratio: number;
  normalization_failures: number;
  last_event_age_seconds: number | null;
  reconnect_attempts: number;
  health_score: number;
  recent_normalized_ratio: number;
  status_message: string;
  last_valid_token_id: string | null;
  last_source_message: string;
}

export interface SecurityStatus {
  auth_enabled: boolean;
  totp_enabled: boolean;
  live_trading_env_enabled: boolean;
  live_trading_requested: boolean;
  effective_live_trading_enabled: boolean;
  allowed_origins: string[];
  paper_only_boundary: boolean;
}

export interface BotSnapshot {
  status: BotStatus;
  settings: BotSettings;
  tokens: TokenSignal[];
  events: TradeEvent[];
  stats: BotStats;
  source_status: SourceStatus;
}
