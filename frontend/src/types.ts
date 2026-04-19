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
  minimum_hold_time_seconds: number;
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
  kill_switch_enabled: boolean;
  max_consecutive_losses_enabled: boolean;
  max_consecutive_losses: number;
  halt_on_low_replay_confidence: boolean;
  min_replay_confidence: number;
  halt_on_low_readiness: boolean;
  min_readiness_score: number;
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
  use_observed_prices: boolean;
  max_trade_subscriptions: number;
  min_price_confidence: number;
  max_first_observed_move_pct: number;
  prefer_market_cap_price: boolean;
  trailing_stop_enabled: boolean;
  trailing_stop_pct: number;
  partial_take_profit_enabled: boolean;
  partial_take_profit_pct: number;
  partial_take_profit_fraction: number;
  cooldown_after_loss_enabled: boolean;
  cooldown_after_loss_seconds: number;
  max_trades_per_hour_enabled: boolean;
  max_trades_per_hour: number;
  velocity_slippage_enabled: boolean;
  max_same_creator_buys_enabled: boolean;
  max_same_creator_buys: number;
  stop_on_source_degraded: boolean;
  max_rejected_price_streak_enabled: boolean;
  max_rejected_price_streak: number;
  strategy_weight_metadata: number;
  strategy_weight_momentum: number;
  strategy_weight_pressure: number;
  strategy_weight_creator: number;
  break_even_stop_enabled: boolean;
  break_even_after_profit_pct: number;
  stalled_trade_exit_enabled: boolean;
  stalled_trade_seconds: number;
  stalled_trade_min_move_pct: number;
  sell_pressure_exit_enabled: boolean;
  sell_pressure_exit_threshold: number;
  solana_rpc_url: string;
  watch_wallet_address: string;
  manual_live_enabled: boolean;
  manual_live_max_sol: number;
  autonomous_live_enabled: boolean;
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
  partial_take_profit_taken: boolean;
  realized_pnl_sol: number;
  remaining_fraction: number;
  rejected_price_streak: number;
  market_cap_sol: number;
  initial_buy_sol: number;
  bonding_curve: string;
  metadata_uri: string;
  price_source: string;
  price_confidence: number;
  price_reject_reason: string;
  observed_price_updates: number;
  last_observed_trade_at: string | null;
  settings_version_id: string;
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
  losing_trades: number;
  scratch_trades: number;
  skipped_tokens: number;
  open_positions: number;
  closed_trades: number;
  win_rate_pct: number;
  gross_win_rate_pct: number;
  scratch_rate_pct: number;
  scratch_threshold_sol: number;
  total_pnl_sol: number;
  best_trade_sol: number;
  worst_trade_sol: number;
  average_win_sol: number;
  average_loss_sol: number;
  profit_factor: number;
  max_drawdown_sol: number;
  avg_hold_seconds: number;
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
  launch_events_seen: number;
  trade_events_seen: number;
  status_events_seen: number;
  active_trade_subscriptions: number;
  dropped_trade_subscriptions: number;
}

export interface BacktestResult {
  id: string;
  created_at: string;
  tokens_replayed: number;
  paper_buys: number;
  skips: number;
  wins: number;
  losses: number;
  scratches: number;
  win_rate_pct: number;
  gross_win_rate_pct: number;
  scratch_rate_pct: number;
  estimated_pnl_sol: number;
  max_drawdown_sol: number;
  profit_factor: number;
  avg_hold_seconds: number;
  best_trade_sol: number;
  worst_trade_sol: number;
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
  price_observations: number;
  strategy_decisions: number;
  trade_sessions: number;
  settings_versions: number;
  experiments: number;
  trade_labels: number;
  strategy_presets: number;
  live_execution_requests: number;
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
  lifecycle_status: string;
  entry_fee_sol: number;
  exit_fee_sol: number;
  price_impact_pct: number;
  slippage_paid_pct: number;
  source_price_confidence: number;
  decision_log: string[];
  settings_version_id: string;
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
  trade_events: number;
  launch_events: number;
  status_events: number;
  active_trade_subscriptions: number;
  dropped_trade_subscriptions: number;
  price_observations: number;
  strategy_decisions: number;
  trade_sessions: number;
  reliability_note: string;
}

export interface SecurityStatus {
  auth_enabled: boolean;
  totp_enabled: boolean;
  live_trading_env_enabled: boolean;
  live_trading_requested: boolean;
  effective_live_trading_enabled: boolean;
  allowed_origins: string[];
  paper_only_boundary: boolean;
  runtime_password_configurable: boolean;
  failed_attempts: number;
  locked: boolean;
  session_ttl_seconds: number;
}

export interface PriceObservation {
  id: string;
  source: string;
  mint: string;
  observed_at: string;
  price: number | null;
  price_source: string;
  confidence: number;
  accepted: boolean;
  reason: string;
  market_cap_sol: number | null;
  sol_amount: number | null;
  trade_side: string | null;
  token_id: string | null;
  direct_price: number | null;
  market_cap_price: number | null;
  virtual_reserve_price: number | null;
  selected_price: number | null;
}

export interface StrategyDecisionRecord {
  id: string;
  token_id: string;
  mint: string;
  created_at: string;
  engine_version: string;
  profile: string;
  score: number;
  allowed: boolean;
  action: string;
  reason: string;
  risk_reason: string;
  snapshot: Record<string, unknown>;
  score_breakdown: string[];
  decision_log: string[];
  settings_version_id: string;
}

export interface TradeSession {
  id: string;
  token_id: string;
  mint: string;
  symbol: string;
  strategy_profile: string;
  status: string;
  opened_at: string | null;
  closed_at: string | null;
  amount_sol: number | null;
  entry_price: number | null;
  exit_price: number | null;
  pnl_sol: number | null;
  realized_pnl_sol: number;
  remaining_fraction: number;
  exit_reason: string | null;
  lifecycle: Array<Record<string, unknown>>;
  settings_version_id: string;
}

export interface SettingsVersion {
  id: string;
  created_at: string;
  settings: Record<string, unknown>;
  label: string;
  changed_keys: string[];
}

export interface PerformanceGroup {
  label: string;
  count: number;
  wins: number;
  losses: number;
  scratches: number;
  win_rate_pct: number;
  pnl_sol: number;
  avg_pnl_sol: number;
  profit_factor: number;
  avg_hold_seconds: number;
}

export interface PerformanceAnalytics {
  summary: PerformanceGroup;
  by_exit_reason: PerformanceGroup[];
  by_strategy: PerformanceGroup[];
  by_settings_version: PerformanceGroup[];
  by_score_bucket: PerformanceGroup[];
  by_price_confidence: PerformanceGroup[];
  recent_curve: Array<{ at: string; pnl_sol: number; trade_id: string }>;
}

export interface TuningSuggestion {
  title: string;
  reason: string;
  setting: string;
  suggested_value?: string | number | boolean;
  confidence: number;
}

export interface ReplayTimelineEvent {
  at: string;
  type: string;
  title: string;
  detail: string;
}

export interface DataIntegrityReport {
  score: number;
  tokens: number;
  trades: number;
  source_events: number;
  price_observations: number;
  strategy_decisions: number;
  issues: Array<{ severity: string; category: string; message: string; count: number }>;
  replay_confidence: {
    score: number;
    accepted_price_ratio: number;
    normalized_event_ratio: number;
    closed_trade_price_coverage: number;
    sample_size: Record<string, number>;
  };
  determinism_fingerprint: string;
}

export interface PriceDiagnostics {
  engine_version: string;
  observations: number;
  accepted: number;
  rejected: number;
  acceptance_rate: number;
  impossible_jump_warnings: number;
  sources: Array<{ source: string; count: number; accepted: number; acceptance_rate: number; avg_confidence: number }>;
  recommended_min_confidence: number;
}

export interface PumpFunReport {
  tokens_analyzed: number;
  unique_creators: number;
  repeat_creators: number;
  high_creator_hold: number;
  large_initial_buys: number;
  migration_markers: number;
  field_coverage: Record<string, number>;
  top_creators: Array<{ creator: string; launches: number }>;
  research_notes: string[];
}

export interface SafetyStatus {
  paper_only: boolean;
  entries_allowed: boolean;
  stop_reasons: string[];
  consecutive_losses: number;
  open_positions: number;
  daily_loss_cap_sol: number;
  total_pnl_sol: number;
  kill_switch_available: boolean;
  kill_switch_enabled: boolean;
  replay_confidence: number;
  manual_live_ready: boolean;
  autonomous_live_ready: boolean;
  live_blockers: string[];
}

export interface ReadinessGate {
  id: string;
  label: string;
  status: "pass" | "warn" | "fail";
  value: string | number | boolean;
  target: string | number | boolean;
  weight: number;
  reason: string;
}

export interface ReadinessStatus {
  engine_version: "readiness-v1";
  score: number;
  status: "not_enough_data" | "blocked" | "warning" | "ready";
  entries_allowed: boolean;
  gates: ReadinessGate[];
  recommended_actions: string[];
  sample_size: {
    closed_trades: number;
    source_events: number;
    price_observations: number;
    strategy_decisions: number;
  };
  paper_only: boolean;
  halt_on_low_readiness: boolean;
  min_readiness_score: number;
}

export interface OperationalMonitoring {
  backend: Record<string, string | number | boolean>;
  source: SourceHealth;
  storage: DataSummary;
  recent_errors: TradeEvent[];
  recent_warnings: TradeEvent[];
}

export interface BacktestV3Result {
  engine_version: string;
  tokens_replayed: number;
  determinism_fingerprint: string;
  best_profile: string | null;
  runs: Array<{ profile: string; full: BacktestResult; train: BacktestResult; validate: BacktestResult; overfit_warning: boolean }>;
}

export interface TradeReviewDetail {
  token: TokenSignal | null;
  trade: TradeRecord | null;
  decisions: StrategyDecisionRecord[];
  observations: PriceObservation[];
  timeline: ReplayTimelineEvent[];
  pnl_breakdown: Record<string, number>;
}

export interface ExperimentRun {
  id: string;
  name: string;
  created_at: string;
  settings_version_id: string;
  profile: string;
  replay_source: string;
  result: BacktestV3Result;
  fingerprint: string;
  notes: string;
}

export interface TradeLabel {
  id: string;
  token_id: string;
  trade_id: string;
  label: string;
  created_at: string;
  note: string;
}

export interface StrategyPreset {
  id: string;
  name: string;
  created_at: string;
  settings: Record<string, unknown>;
  description: string;
}

export interface SourceAdapterStatus {
  name: string;
  enabled: boolean;
  status: string;
  capabilities: string[];
  confidence: number;
}

export interface WatchdogStatus {
  status: string;
  bot_running: boolean;
  last_tick_at: string | null;
  tick_age_seconds: number | null;
  last_ingested_launch_at: string | null;
  launch_ingestion_age_seconds: number | null;
  source_event_age_seconds: number | null;
  tick_stale: boolean;
  source_stale: boolean;
  launch_stale: boolean;
  loop_iterations: number;
  last_error: string;
  recommended_action: string;
}

export interface SolanaStatus {
  configured: boolean;
  rpc_url: string;
  wallet_configured: boolean;
  wallet_address: string;
  health: string;
  balance_sol: number | null;
  read_only: boolean;
  error: string;
}

export interface LiveExecutionRequest {
  id: string;
  created_at: string;
  action: string;
  mint: string;
  amount_sol: number;
  status: string;
  reason: string;
  mode: string;
  payload: Record<string, unknown>;
  reviewed_at: string | null;
}

export interface BotSnapshot {
  status: BotStatus;
  settings: BotSettings;
  tokens: TokenSignal[];
  events: TradeEvent[];
  stats: BotStats;
  source_status: SourceStatus;
}
