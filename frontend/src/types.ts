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
  paper_priority_fee_sol: number;
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
  entry_confirmation_enabled: boolean;
  entry_confirmation_min_buy_velocity: number;
  entry_confirmation_max_sell_pressure: number;
  entry_confirmation_min_metadata_score: number;
  entry_confirmation_min_initial_buy_sol: number;
  entry_confirmation_min_price_confidence: number;
  entry_confirmation_min_observed_trades: number;
  max_trades_per_hour_enabled: boolean;
  max_trades_per_hour: number;
  velocity_slippage_enabled: boolean;
  max_same_creator_buys_enabled: boolean;
  max_same_creator_buys: number;
  stop_on_source_degraded: boolean;
  direct_solana_paper_enabled: boolean;
  direct_solana_min_confidence: number;
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
  live_max_trade_sol: number;
  live_daily_loss_cap_sol: number;
  live_wallet_exposure_cap_sol: number;
  live_max_open_positions: number;
  live_max_slippage_pct: number;
  live_priority_fee_cap_sol: number;
  live_session_acknowledged: boolean;
  live_signer_mode: "browser_wallet" | "local_hot_wallet" | "local_signer_daemon";
  live_active_backend_armed: boolean;
  live_active_wallet_public_key: string;
  live_hot_wallet_enabled: boolean;
  live_hot_wallet_public_key: string;
  live_hot_wallet_label: string;
  profit_sweep_enabled: boolean;
  profit_sweep_mode: "fixed_sol" | "percentage";
  profit_sweep_threshold_sol: number;
  profit_sweep_amount_sol: number;
  profit_sweep_percentage: number;
  profit_sweep_min_profit_sol: number;
  profit_sweep_destination_wallet: string;
  profit_sweep_min_reserve_sol: number;
  profit_sweep_cooldown_seconds: number;
  profit_sweep_max_per_day: number;
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
  exit_fee_sol: number;
  total_fees_sol: number;
  entry_provider_fee_sol: number;
  exit_provider_fee_sol: number;
  entry_network_fee_sol: number;
  exit_network_fee_sol: number;
  entry_priority_fee_sol: number;
  exit_priority_fee_sol: number;
  entry_slippage_cost_sol: number;
  entry_price_impact_cost_sol: number;
  price_impact_pct: number;
  quote_shadow_fee_sol: number;
  quote_shadow_priority_fee_sol: number;
  quote_shadow_impact_sol: number;
  quote_shadow_total_cost_sol: number;
  quote_shadow_slippage_pct: number;
  quote_shadow_status: string;
  wallet_public_key: string;
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
  subsystem?: string;
  operator_action?: string;
  session_id?: string;
  context?: Record<string, unknown>;
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
  entry_fees_sol: number;
  exit_fees_sol: number;
  total_fees_sol: number;
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
  connection_requested_at: string | null;
  connected_at: string | null;
  first_event_at: string | null;
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

export interface SourceConnectionStatus {
  state: string;
  requested_at: string | null;
  connected_at: string | null;
  first_event_at: string | null;
  startup_ms: number | null;
  first_event_ms: number | null;
  message: string;
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
  determinism_fingerprint: string;
}

export interface SourceEvent {
  id: string;
  source: string;
  received_at: string;
  raw_payload: Record<string, unknown>;
  normalized_token_id: string | null;
  status: string;
  message: string;
  event_kind?: string;
  parser_result?: string;
}

export interface SourceParserReplayReport {
  artifact_type: "cryptoarc_source_parser_replay" | string;
  format_version: number;
  generated_at: string;
  limit: number;
  profile: string;
  date_from: string;
  date_to: string;
  summary: {
    raw_events: number;
    launch_candidates: number;
    normalized: number;
    normalization_failures: number;
    trade_events: number;
    normalization_rate: number;
    parser_counts: Record<string, number>;
    event_kind_counts: Record<string, number>;
  };
  dry_backtest: {
    tokens_replayed: number;
    paper_buys: number;
    skips: number;
    estimated_pnl_sol: number;
    win_rate_pct: number;
    profit_factor: number;
    replay_source: string;
  };
  failures: Array<{
    event_id: string;
    received_at: string;
    source: string;
    status: string;
    event_kind: string;
    parser_result: string;
    mint: string;
    normalized_token_id: string | null;
    symbol: string;
    failure_reason: string;
    replay_action: string;
    message: string;
  }>;
  events: Array<Record<string, unknown>>;
  operator_action: string;
  privacy_note: string;
}

export interface SolanaLogsVerificationReport {
  artifact_type: "cryptoarc_solana_logs_verification" | string;
  format_version: number;
  generated_at: string;
  limit: number;
  status: "not_configured" | "configured_no_events" | "matching" | "partial" | "review" | "no_matches" | "unknown" | string;
  configured: boolean;
  wss_configured: boolean;
  mentions_address_configured: boolean;
  summary: {
    direct_events: number;
    pumpportal_events: number;
    direct_create_hints: number;
    decoded_create_events: number;
    matches: number;
    unmatched_direct: number;
    unmatched_pumpportal: number;
    conflicts: number;
  };
  matches: Array<Record<string, unknown>>;
  unmatched_direct: Array<Record<string, unknown>>;
  unmatched_pumpportal: Array<Record<string, unknown>>;
  conflicts: Array<Record<string, unknown>>;
  direct_events: Array<Record<string, unknown>>;
  source_soak: SourceSoakSummary;
  operator_action: string;
  action_items: string[];
  docs: Record<string, string>;
  privacy_note: string;
}

export interface SourceSoakSummary {
  direct_events: number;
  pumpportal_events: number;
  direct_create_hints: number;
  decoded_create_events: number;
  matches: number;
  match_rate: number;
  decoded_create_rate: number;
  unmatched_direct: number;
  unmatched_pumpportal: number;
  conflicts: number;
  target: Record<string, string | number>;
}

export interface SourceSoakAcceptanceReport {
  artifact_type: "cryptoarc_source_soak_acceptance" | string;
  format_version: number;
  generated_at: string;
  status: "ready" | "blocked" | "not_configured" | string;
  ready: boolean;
  hard_required: boolean;
  gates: Array<{
    id: string;
    label: string;
    status: "pass" | "fail" | string;
    value: string | number | boolean | Record<string, unknown>;
    target: string | number | boolean;
    reason: string;
  }>;
  blockers: string[];
  summary: SourceSoakSummary;
  verification_status: string;
  history?: SourceSoakAcceptanceReport[];
  history_summary?: {
    snapshots: number;
    ready_snapshots: number;
    blocked_snapshots: number;
    latest_status: string;
    latest_ready: boolean;
    latest_created_at: string | null;
    average_match_rate: number;
    average_decoded_create_rate: number;
    direct_events_recorded: number;
    operator_action: string;
  };
  operator_action: string;
  privacy_note: string;
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
  live_sessions: number;
  live_intents: number;
  live_ledger_positions: number;
  live_execution_audits: number;
  backup_restore_history?: number;
  source_soak_history?: number;
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
  entry_provider_fee_sol: number;
  exit_provider_fee_sol: number;
  entry_network_fee_sol: number;
  exit_network_fee_sol: number;
  entry_priority_fee_sol: number;
  exit_priority_fee_sol: number;
  entry_slippage_cost_sol: number;
  entry_price_impact_cost_sol: number;
  price_impact_pct: number;
  slippage_paid_pct: number;
  paper_model_cost_sol: number;
  shadow_quote_cost_sol: number;
  quote_adjustment_sol: number;
  quote_adjusted_pnl_sol: number | null;
  simulation_accuracy_status: string;
  source_price_confidence: number;
  decision_log: string[];
  settings_version_id: string;
}

export interface SimulationAccuracyReport {
  artifact_type: string;
  format_version: number;
  generated_at: string;
  wallet_public_key: string;
  paper: {
    samples: number;
    pnl_sol: number;
    quote_adjusted_samples: number;
    quote_adjusted_pnl_sol: number;
    quote_adjustment_sol: number;
    shadow_quote_cost_sol: number;
  };
  shadow: {
    samples: number;
    attempts: number;
    failures: number;
    failure_rate_pct: number;
    estimated_pnl_sol: number;
    avg_quote_latency_ms: number;
  };
  live: {
    samples: number;
    pnl_sol: number;
    total_fees_sol: number;
    pnl_confidence: string;
  };
  error: {
    paper_minus_shadow_sol: number | null;
    shadow_minus_live_sol: number | null;
    paper_minus_live_sol: number | null;
  };
  operator_action: string;
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
  connection: SourceConnectionStatus;
  price_observations: number;
  strategy_decisions: number;
  trade_sessions: number;
  reliability_note: string;
  trust_state: "trusted" | "degraded" | "stale" | "conflicting" | "unknown" | string;
  trust_blockers: string[];
  trust_warnings: string[];
  pumpportal_funding_blocked: boolean;
  pumpportal_funding_message: string;
  pumpportal_funding_blocked_at: string | null;
  shadow_price_observations_blocked: boolean;
  live_entry_blocked: boolean;
  paper_collection_allowed: boolean;
  operator_action: string;
  raw_event_inspection: {
    recent_events: number;
    status_counts: Record<string, number>;
    source_counts: Record<string, number>;
    unique_mints: number;
    duplicate_mints: string[];
    malformed_events: number;
    filterable_fields: string[];
  };
  quality_history: Array<{
    bucket_start: string;
    bucket_end: string;
    events: number;
    normalized: number;
    raw: number;
    trade: number;
    malformed: number;
    unique_mints: number;
    normalized_ratio: number;
    trust_state: "trusted" | "degraded" | "conflicting" | "empty" | string;
  }>;
}

export interface LatencyStatus {
  artifact_type: string;
  format_version: number;
  updated_at: number | null;
  server_time: number;
  dashboard_rtt_ms?: number | null;
  latency_error?: string;
  latency_stale?: boolean;
  api_loop_ms: number | null;
  pumpportal_public_ms: number | null;
  pumpportal_state: string;
  pumpportal_error: string;
  source_connection: SourceConnectionStatus;
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

export interface MobileDevice {
  id: string;
  name: string;
  platform: string;
  scopes: string[];
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  revoked_at: string;
  paired_from_pairing_id?: string;
}

export interface MobilePairingStartResponse {
  id: string;
  code: string;
  manual_code: string;
  api_base_url: string;
  expires_at: string;
  scopes: string[];
  qr_payload: Record<string, unknown>;
  dashboard_auth_enabled: boolean;
  dashboard_totp_enabled: boolean;
  pairing_security_note: string;
}

export interface MobileDevicesResponse {
  devices: MobileDevice[];
  pairing_ttl_seconds: number;
  token_ttl_days: number;
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

export interface WalletPerformanceRow {
  wallet_public_key: string;
  label: string;
  positions: number;
  open_positions: number;
  closed_positions: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  cost_basis_sol: number;
  realized_pnl_sol: number;
  unrealized_pnl_sol: number;
  total_pnl_sol: number;
  fees_sol: number;
  priority_fees_sol: number;
  needs_review_positions: number;
  stale_balance_positions: number;
  pnl_confidence: string;
  confidence_counts: Record<string, number>;
  operator_action: string;
}

export interface PerformanceAnalytics {
  summary: PerformanceGroup;
  by_exit_reason: PerformanceGroup[];
  by_strategy: PerformanceGroup[];
  by_settings_version: PerformanceGroup[];
  by_score_bucket: PerformanceGroup[];
  by_price_confidence: PerformanceGroup[];
  recent_curve: Array<{ at: string; pnl_sol: number; trade_id: string }>;
  wallets?: WalletPerformanceRow[];
  wallet_summary?: {
    wallets: number;
    positions: number;
    open_positions: number;
    closed_positions: number;
    realized_pnl_sol: number;
    unrealized_pnl_sol: number;
    total_pnl_sol: number;
    needs_review_positions: number;
    stale_balance_positions: number;
    pnl_confidence: string;
  };
  mode_comparison?: Record<string, {
    mode: string;
    pnl_sol: number;
    samples: number;
    confidence: string;
    source: string;
  }>;
}

export interface MonitorPnlSummary {
  timeframe: "5m" | "15m" | "1h" | "24h" | "all" | string;
  closed_trade_count: number;
  pnl_sol: number;
  entry_fees_sol: number;
  exit_fees_sol: number;
  total_fees_sol: number;
  history: number[];
}

export interface TuningSuggestion {
  title: string;
  reason: string;
  setting: string;
  suggested_value?: string | number | boolean;
  confidence: number;
  expected_benefit?: string;
  supporting_sample_size?: number;
  supporting_closed_trades?: number;
  supporting_pnl_sol?: number;
  overfit_risk?: "low" | "medium" | "high" | string;
  requires_operator_review?: boolean;
  review_note?: string;
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
  creator_performance: Array<{
    creator: string;
    launches: number;
    closed_trades: number;
    wins: number;
    losses: number;
    pnl_sol: number;
    avg_pnl_sol: number;
    win_rate_pct: number;
    labels: Record<string, number>;
    reputation: "positive" | "negative" | "mixed" | "exclude_or_review" | "unproven" | string;
  }>;
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

export interface AlertStatus {
  telegram_enabled: boolean;
  telegram_configured: boolean;
  min_interval_seconds: number;
  last_result: {
    status: string;
    reason: string;
    key?: string;
    at?: number;
  };
  routes: string[];
  critical_events: string[];
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

export interface StrategyPromotionStatus {
  can_promote: boolean;
  status: "eligible" | "blocked" | "not_enough_data" | string;
  mode: "paper_to_shadow" | string;
  gates: Array<{
    id: string;
    label: string;
    status: "pass" | "fail" | string;
    value: string | number | boolean;
    target: string | number | boolean;
    reason: string;
  }>;
  blockers: string[];
  summary: string;
  requires_operator_review: boolean;
  out_of_sample?: {
    engine_version: string;
    profile: string;
    sample_size: number;
    split: { train_tokens: number; validate_tokens: number };
    train: BacktestResult & { profit_factor: number };
    validate: BacktestResult & { profit_factor: number };
    collapse_warning: boolean;
    determinism_fingerprint: string;
  };
  generated_at: string;
}

export interface ExecutionReadinessStatus {
  status: "shadow_ready" | "not_enough_quote_data" | "blocked" | string;
  can_shadow: boolean;
  can_live_submit: boolean;
  live_submit_quote_evidence_ready: boolean;
  mode: "dry_run_to_shadow" | string;
  quote_ttl_seconds: number;
  quote_evidence_window_hours: number;
  audit_history_limit: number;
  audit_history_truncated: boolean;
  audit_history_complete: boolean;
  latest_quote_age_seconds: number | null;
  current_latest_quote_age_seconds: number | null;
  metrics: {
    quote_attempts: number;
    ready_quotes: number;
    blocked_quotes: number;
    stale_quotes: number;
    submitted_audits: number;
    unresolved_audits: number;
    stale_quote_rate: number;
    blocked_quote_rate: number;
    shadow_samples: number;
    shadow_evaluated: number;
    shadow_win_rate_pct: number;
    shadow_estimated_pnl_sol: number;
    shadow_landing_windows: number;
    shadow_landing_evaluated: number;
    shadow_landing_win_rate_pct: number;
    shadow_landing_best_pnl_sol: number;
    shadow_landing_worst_pnl_sol: number;
    live_landing_samples: number;
    live_quote_to_submit_p50_ms: number;
    live_quote_to_submit_p90_ms: number;
    live_quote_to_submit_p99_ms: number;
    live_submit_to_confirm_p50_ms: number;
    live_submit_to_confirm_p90_ms: number;
    live_submit_to_confirm_p99_ms: number;
    pipeline_samples: number;
    signal_to_quote_p50_ms: number;
    signal_to_quote_p90_ms: number;
    intent_to_quote_p50_ms: number;
    intent_to_quote_p90_ms: number;
    current_quote_attempts: number;
    recent_submittable_quote_attempts: number;
    current_quote_health_sample: number;
    current_quote_health_sample_kind: "current_quote_audits";
    current_ready_quotes: number;
    current_blocked_quotes: number;
    current_failed_quotes: number;
    current_unhealthy_quotes: number;
    current_stale_quotes: number;
    current_submitted_audits: number;
    current_stale_quote_rate: number;
    current_blocked_quote_rate: number;
    current_unhealthy_quote_rate: number;
    current_live_submit_quote_evidence_ready: boolean;
    current_shadow_samples: number;
    current_submittable_quote_health_sample: number;
    current_submittable_ready_quotes: number;
    current_submittable_stale_quotes: number;
    current_submittable_unhealthy_quotes: number;
    current_submittable_stale_quote_rate: number;
    current_submittable_unhealthy_quote_rate: number;
    excluded_ambiguous_timestamp_quote_audits: number;
    excluded_future_timestamp_quote_audits: number;
    current_live_landing_samples: number;
    current_live_quote_to_submit_p50_ms: number;
    current_live_quote_to_submit_p90_ms: number;
    current_live_quote_to_submit_p99_ms: number;
    current_live_submit_to_confirm_p50_ms: number;
    current_live_submit_to_confirm_p90_ms: number;
    current_live_submit_to_confirm_p99_ms: number;
    current_pipeline_samples: number;
    current_signal_to_quote_p50_ms: number;
    current_signal_to_quote_p90_ms: number;
    current_intent_to_quote_p50_ms: number;
    current_intent_to_quote_p90_ms: number;
    loaded_history_quote_attempts: number;
    loaded_history_submittable_quote_attempts: number;
    loaded_history_ready_quotes: number;
    loaded_history_blocked_quotes: number;
    loaded_history_stale_quotes: number;
    loaded_history_submitted_audits: number;
    loaded_history_stale_quote_rate: number;
    loaded_history_blocked_quote_rate: number;
    loaded_history_shadow_samples: number;
    loaded_history_shadow_evaluated: number;
    loaded_history_shadow_win_rate_pct: number;
    loaded_history_shadow_estimated_pnl_sol: number;
    loaded_history_shadow_landing_windows: number;
    loaded_history_shadow_landing_evaluated: number;
    loaded_history_shadow_landing_win_rate_pct: number;
    loaded_history_shadow_landing_best_pnl_sol: number;
    loaded_history_shadow_landing_worst_pnl_sol: number;
  };
  policy: {
    max_trade_sol: number;
    max_slippage_pct: number;
    priority_fee_cap_sol: number;
    daily_loss_cap_sol: number;
    wallet_exposure_cap_sol: number;
    max_open_positions: number;
    suggested_slippage_pct: number;
    suggested_priority_fee_sol: number;
    recommendation?: {
      status: string;
      suggested_slippage_pct: number;
      suggested_priority_fee_sol: number;
      cap_room: {
        slippage_pct: number;
        priority_fee_sol: number;
      };
      inputs: {
        stale_quote_rate: number;
        blocked_quote_rate: number;
        missed_landing_rate: number;
        landing_windows: number;
        evaluated_landing_windows: number;
        quote_to_submit_p90_ms: number;
        issue_categories: string[];
      };
      reasons: string[];
      operator_action: string;
    };
    blockers: string[];
  };
  latency_summary: {
    status: "fast" | "watch" | "slow" | "needs_samples" | string;
    samples: number;
    signal_to_quote_p50_ms: number;
    signal_to_quote_p90_ms: number;
    intent_to_quote_p50_ms: number;
    intent_to_quote_p90_ms: number;
    quote_to_submit_p50_ms: number;
    quote_to_submit_p90_ms: number;
    quote_to_submit_samples: number;
    issues: string[];
    operator_action: string;
  };
  landing_calibration: {
    samples: number;
    quote_to_submit_p50_ms: number;
    quote_to_submit_p90_ms: number;
    quote_to_submit_p99_ms: number;
    submit_to_confirm_p50_ms: number;
    submit_to_confirm_p90_ms: number;
    submit_to_confirm_p99_ms: number;
    quote_to_confirm_p50_ms: number;
    quote_to_confirm_p90_ms: number;
    quote_to_confirm_p99_ms: number;
    by_signer_mode: Record<string, {
      samples: number;
      quote_to_submit_p50_ms: number;
      quote_to_submit_p90_ms: number;
      quote_to_submit_p99_ms: number;
      submit_to_confirm_p50_ms: number;
      submit_to_confirm_p90_ms: number;
      submit_to_confirm_p99_ms: number;
      quote_to_confirm_p50_ms: number;
      quote_to_confirm_p90_ms: number;
      quote_to_confirm_p99_ms: number;
    }>;
    by_pool: Record<string, {
      samples: number;
      quote_to_submit_p50_ms: number;
      quote_to_submit_p90_ms: number;
      quote_to_submit_p99_ms: number;
      submit_to_confirm_p50_ms: number;
      submit_to_confirm_p90_ms: number;
      submit_to_confirm_p99_ms: number;
      quote_to_confirm_p50_ms: number;
      quote_to_confirm_p90_ms: number;
      quote_to_confirm_p99_ms: number;
    }>;
    by_quote_source: Record<string, {
      samples: number;
      quote_to_submit_p50_ms: number;
      quote_to_submit_p90_ms: number;
      quote_to_submit_p99_ms: number;
      submit_to_confirm_p50_ms: number;
      submit_to_confirm_p90_ms: number;
      submit_to_confirm_p99_ms: number;
      quote_to_confirm_p50_ms: number;
      quote_to_confirm_p90_ms: number;
      quote_to_confirm_p99_ms: number;
    }>;
    suggested_delay_windows_ms: number[];
    source: string;
  };
  pipeline_latency: {
    samples: number;
    totals: Record<string, {
      samples: number;
      p50_ms: number;
      p90_ms: number;
      p99_ms: number;
      max_ms: number;
    }>;
    recent_samples: Array<{
      audit_id: string;
      mint: string;
      action: string;
      status: string;
      quoted_at: string;
      source_event_id: string;
      token_id: string;
      decision_id: string;
      intent_id: string;
      stages: Record<string, number | null>;
    }>;
    missing_evidence: Record<string, number>;
  };
  quote_issues: {
    total_issues: number;
    stale_count: number;
    blocked_count: number;
    failed_count: number;
    categories: Array<{
      category: string;
      count: number;
      latest_at: string;
      reasons: string[];
      audit_ids: string[];
    }>;
    recent: Array<{
      audit_id: string;
      mint: string;
      status: string;
      category: string;
      reason: string;
      created_at: string;
    }>;
    operator_action: string;
  };
  failure_stages: {
    total_failures: number;
    stages: Array<{
      stage: "quote" | "simulation" | "submit" | "confirmation" | "reconciliation" | string;
      count: number;
      latest_at: string;
      categories: Array<{ category: string; count: number }>;
      audit_ids: string[];
      reasons: string[];
    }>;
    recent: Array<{
      audit_id: string;
      mint: string;
      action: string;
      stage: string;
      category: string;
      reason: string;
      status: string;
      created_at: string;
    }>;
    operator_action: string;
  };
  current_latency_summary: ExecutionReadinessStatus["latency_summary"];
  current_pipeline_latency: ExecutionReadinessStatus["pipeline_latency"];
  current_quote_issues: ExecutionReadinessStatus["quote_issues"];
  current_failure_stages: ExecutionReadinessStatus["failure_stages"];
  current_landing_calibration: ExecutionReadinessStatus["landing_calibration"];
  gates: Array<{
    id: string;
    label: string;
    status: "pass" | "fail" | string;
    value: string | number | boolean;
    target: string | number | boolean;
    reason: string;
  }>;
  shadow_comparisons: Array<{
    mode: string;
    status: string;
    evaluation_model: string;
    audit_id: string;
    intent_id: string;
    mint: string;
    quoted_at: string;
    would_submit_at: string;
    amount_sol: number;
    entry_price: number | null;
    entry_price_source: string;
    entry_observed_at: string | null;
    latest_price: number | null;
    latest_price_source: string;
    latest_observed_at: string | null;
    exit_price: number | null;
    exit_price_source: string;
    exit_observed_at: string | null;
    exit_reason: string;
    hold_duration_seconds: number;
    landing_windows: Array<{
      delay_ms: number;
      landing_at: string;
      status: string;
      entry_price: number | null;
      entry_price_source: string;
      entry_observed_at: string | null;
      exit_price: number | null;
      exit_price_source: string;
      exit_observed_at: string | null;
      exit_reason: string;
      hold_duration_seconds: number;
      move_pct: number | null;
      estimated_pnl_sol: number;
      outcome: string;
      fill_status: string;
      reason: string;
    }>;
    move_pct: number | null;
    estimated_pnl_sol: number;
    outcome: string;
    latency_ms: number;
    rules: Record<string, unknown>;
    reason: string;
  }>;
  current_shadow_comparisons: ExecutionReadinessStatus["shadow_comparisons"];
  blockers: string[];
  operator_action: string;
  generated_at: string;
}

export interface ReadinessStatus {
  engine_version: "readiness-v1";
  score: number;
  status: "not_enough_data" | "blocked" | "warning" | "ready";
  entries_allowed: boolean;
  gates: ReadinessGate[];
  recommended_actions: string[];
  strategy_promotion: StrategyPromotionStatus;
  execution_readiness: ExecutionReadinessStatus;
  source_soak: SourceSoakAcceptanceReport;
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

export interface PilotRiskPolicy {
  policy_id: string;
  policy_version: string;
  created_at: string;
  observed_at: string;
  reference_observation_id: string;
  settings_version: string;
  operator_intent_id: string;
  reference_usd_per_sol: string;
  wallet_equity_sol: string;
  max_trade_sol: string;
  max_open_positions: number;
  session_loss_stop_sol: string;
  daily_loss_stop_sol: string;
  cumulative_loss_freeze_sol: string;
  consecutive_loss_stop: number;
  initial_slippage_pct: string;
  max_reviewable_slippage_pct: string;
}

export interface PilotRiskStatus {
  status: "not_configured" | "configured";
  policy?: PilotRiskPolicy;
  ledger?: { cumulative_loss_sol: string; consecutive_losses: number; entries: unknown[] };
  authority_changed: false;
  operator_action: string;
}

export interface ManualLiveProofReport {
  proof_id?: string;
  created_at?: string;
  status: "QUALIFIED" | "DEFERRED" | "INVALID";
  qualified: boolean;
  blockers: string[];
  authorization_id?: string;
  wallet_public_key?: string;
  signer_mode?: string;
  signer_identity_id?: string;
  audit_ids: string[];
  transaction_signatures: string[];
  authority_changed: false;
  operator_action: string;
}

export type SentinelVerdictStatus = "insufficient_evidence" | "unfavorable" | "observe_only" | "pilot_eligible";

export interface SentinelVerdict {
  verdict_id: string;
  status: SentinelVerdictStatus;
  created_at: string;
  expires_at: string;
  strategy_id: string;
  strategy_version: string;
  input_version: string;
  inputs: Record<string, unknown>;
  thresholds: Record<string, number>;
  sample_size: number;
  confidence: number;
  blockers: string[];
  warnings: string[];
  reasons: string[];
  stale: boolean;
  authority: "none";
}

export interface OperationalMonitoring {
  backend: Record<string, string | number | boolean>;
  source: SourceHealth;
  storage: DataSummary;
  schema: MigrationStatus;
  backup_restore?: BackupRestoreStatus;
  signer_daemon?: SignerStatus;
  live_recovery?: {
    last_poll_at: string | null;
    summary: Record<string, unknown>;
    unresolved_audits: number;
  };
  recent_errors: TradeEvent[];
  recent_warnings: TradeEvent[];
  events_by_subsystem?: Record<string, TradeEvent[]>;
  observability?: {
    generated_at: string;
    event_count: number;
    level_counts: Record<string, number>;
    session_metrics?: {
      active_session_id: string;
      session_event_count: number;
      sessions_seen: number;
      top_sessions: Array<{ session_id: string; events: number }>;
    };
    subsystems: Array<{
      subsystem: string;
      events: number;
      warnings: number;
      errors: number;
      latest_at: string;
      latest_message: string;
    }>;
    high_severity: TradeEvent[];
    readiness_changes: TradeEvent[];
    source_metrics: Record<string, unknown>;
    signer_metrics: Record<string, unknown>;
    recovery_metrics: Record<string, unknown>;
    operator_action: string;
  };
}

export interface OperatorLogsReport {
  artifact_type: "cryptoarc_operator_logs" | string;
  format_version: number;
  generated_at: string;
  timeframe: string;
  filters: {
    level: string;
    subsystem: string;
    limit: number;
  };
  summary: {
    total_events: number;
    returned_events: number;
    warnings: number;
    errors: number;
    subsystems: number;
    sessions: number;
    recovery_related_events: number;
    source_related_events: number;
    live_related_events: number;
  };
  level_counts: Record<string, number>;
  subsystem_counts: Array<{ subsystem: string; events: number }>;
  session_counts: Array<{ session_id: string; events: number }>;
  events: TradeEvent[];
  action_items: string[];
  operator_action: string;
  privacy_note: string;
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
  review_workflow?: {
    current_index: number;
    total_closed: number;
    previous_token_id: string;
    next_token_id: string;
    selected_label: string;
    suggested_labels: string[];
    checklist: Array<{
      id: string;
      label: string;
      status: "pass" | "warn" | "missing" | string;
      count: number;
      ids: string[];
      operator_action: string;
    }>;
    operator_action: string;
  };
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

export interface WorkloadPressure {
  artifact_type: "cryptoarc_workload_pressure";
  format_version: 1;
  status: "healthy" | "degraded_observability";
  disabled_tiers: Array<"model" | "grading" | "sentinel" | "dashboard_analytics">;
  failure_windows: number;
  recovery_windows: number;
  snapshot_version: number;
  reasons: string[];
  worker_failures: string[];
  metrics: Record<string, unknown>;
  queue: Record<string, number>;
  core_tiers_shed: false;
  operator_action: string;
}

export interface TradeGrade {
  grade_id: string;
  trade_id: string;
  revision_id: string;
  mode: "paper" | "shadow" | "manual_live" | "autonomous_live";
  created_at: string;
  grader_version: string;
  rules_version: string;
  strategy_version: string;
  data_schema_version: number;
  classifications: Record<"entry" | "signal" | "risk" | "source" | "execution" | "exit" | "outcome", "good" | "warning" | "poor" | "unknown">;
  ex_ante_facts: Record<string, unknown>;
  ex_post_facts: Record<string, unknown>;
  evidence_ids: string[];
  confidence: number;
  reasons: string[];
}

export interface TradeGradeCorrection {
  correction_id: string;
  grade_id: string;
  trade_id: string;
  created_at: string;
  operator_intent_id: string;
  patch: Record<string, unknown>;
  note: string;
}

export interface StrategyCandidateValidation {
  validation_id: string;
  candidate_id: string;
  created_at: string;
  accepted: boolean;
  blockers: string[];
  metrics: Record<string, unknown>;
}

export interface StrategyCandidate {
  candidate_id: string;
  base_strategy_version: string;
  proposed_strategy_version: string;
  created_at: string;
  patch: Record<string, unknown>;
  evidence_ids: string[];
  fingerprint: string;
  validation: StrategyCandidateValidation | null;
  active: boolean;
}

export interface StrategyCandidatePromotionResult {
  candidate_id: string;
  promoted: boolean;
  blocker: string;
  idempotent: boolean;
  promotion_id: string;
}

export interface TradeReviewQueue {
  total_closed: number;
  labeled: number;
  unlabeled: number;
  label_counts: Record<string, number>;
  queues: Array<{
    id: string;
    label: string;
    count: number;
    sample_token_ids: string[];
    sample_trade_ids: string[];
    reason: string;
  }>;
  next_queue_id: string;
  next_token_id: string;
  operator_action: string;
  generated_at: string;
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
  details?: Record<string, string | number | boolean>;
}

export interface WatchdogStatus {
  status: string;
  bot_running: boolean;
  last_tick_at: string | null;
  last_tick_tokens_seen: number;
  last_tick_active_tokens: number;
  last_tick_closed: number;
  last_tick_completed_at: string | null;
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

export interface SignerStatus {
  mode: "browser_wallet" | "local_hot_wallet" | "local_signer_daemon";
  connected: boolean;
  wallet_public_key: string;
  healthy: boolean;
  can_sign: boolean;
  can_unattended_sign: boolean;
  supports_auto_sell: boolean;
  supports_auto_buy: boolean;
  disabled_reason: string;
  message: string;
  endpoint: string;
  transport: string;
  version: string;
  last_heartbeat_at: string;
  auth_configured: boolean;
}

export interface HotWalletStatus {
  imported: boolean;
  unlocked: boolean;
  wallet_public_key: string;
  label: string;
  imported_at: string;
  last_unlock_at: string;
  version: number;
  storage_scope: string;
  recovery_note: string;
}

export interface MigrationStatus {
  current_version: number;
  expected_version: number;
  ok: boolean;
  status: string;
  startup_error: string;
  startup_completed_at: string | null;
  migrations: Array<{
    migration_id: string;
    version: number;
    description: string;
    applied_at: string;
  }>;
}

export interface BackupRestoreHistoryEntry {
  id?: string;
  created_at?: string;
  action?: string;
  status?: string;
  path?: string;
  backup_path?: string;
  operator_action?: string;
  [key: string]: unknown;
}

export interface BackupRestoreStatus {
  history: BackupRestoreHistoryEntry[];
  latest_backup: BackupRestoreHistoryEntry | null;
  latest_restore: BackupRestoreHistoryEntry | null;
  latest_failed_restore?: BackupRestoreHistoryEntry | null;
  database_exists?: boolean;
  database_path?: string;
  database_size_bytes?: number;
  history_count?: number;
  recommended_action?: string;
}

export interface RestoreArtifactPreview {
  compatible: boolean;
  artifact_type: string;
  format_version: number;
  created_at: string | null;
  database_name: string | null;
  schema_version: number;
  current_schema_version: number;
  summary: Record<string, number>;
  current_summary?: Record<string, number>;
  table_deltas?: Record<string, { current: number; artifact: number; delta: number }>;
  changed_tables?: string[];
  risk_level?: "low" | "review" | "blocked" | string;
  recommended_actions?: string[];
  warnings: string[];
  payload_bytes: number;
  integrity_check?: string;
  detected_tables?: string[];
  status?: string;
  backup_path?: string;
}

export interface RestoreSmokeTestReport {
  artifact_type: string;
  format_version: number;
  generated_at: string;
  status: "pass" | "review" | string;
  passed: boolean;
  backup_artifact_created_at?: string | null;
  schema_version?: number;
  current_schema_version?: number;
  database_name?: string | null;
  payload_bytes?: number;
  integrity_check?: string;
  risk_level?: "low" | "review" | "blocked" | string;
  changed_tables?: string[];
  table_deltas?: Record<string, { current: number; artifact: number; delta: number }>;
  summary?: Record<string, number>;
  current_summary?: Record<string, number>;
  warnings?: string[];
  recommended_actions?: string[];
  operator_action?: string;
  privacy_note?: string;
}

export interface PreRunBackupStatus {
  required: boolean;
  state: "fresh" | "missing" | "stale" | "superseded_by_restore" | string;
  fresh: boolean;
  max_age_hours: number;
  age_seconds: number | null;
  latest_backup: BackupRestoreHistoryEntry | null;
  latest_restore: BackupRestoreHistoryEntry | null;
  backup_after_restore: boolean;
  blocks_live_entries: boolean;
  blocker: string;
  operator_action: string;
}

export interface LiveCapOperatorIntent {
  visible: boolean;
  settings_version_id: string;
  recorded_at: string | null;
  changed_keys: string[];
  blocker: string;
  operator_action: string;
}

export interface LiveCapsSnapshot {
  max_trade_sol: number;
  daily_loss_cap_sol: number;
  wallet_exposure_cap_sol: number;
  max_open_positions: number;
  max_slippage_pct: number;
  priority_fee_cap_sol: number;
  operator_intent: LiveCapOperatorIntent;
}

export interface LiveStatus {
  mode: string;
  paper_default: boolean;
  live_execution_available: boolean;
  env_live_enabled: boolean;
  effective_live_enabled: boolean;
  blockers: string[];
  signer: SignerStatus;
  caps: LiveCapsSnapshot;
  session_acknowledged: boolean;
  readiness: ReadinessStatus;
  execution_readiness: ExecutionReadinessStatus;
  local_desktop_only: boolean;
  autonomous_live_available: boolean;
  auto_sell_available: boolean;
  auto_buy_available: boolean;
  autonomy_blockers: string[];
  autonomy: {
    entry: LiveAutonomyGate;
    exit: LiveAutonomyGate;
    active_backend_matches: boolean;
    recovery_debt: {
      unresolved_audits: number;
      recoverable_audits: number;
      blocks_new_entries: boolean;
    };
    override: {
      available: boolean;
      local_auth_enabled: boolean;
      local_only: boolean;
      bypass_enabled: boolean;
      supported_targets: string[];
      operator_action: string;
      disabled_reason: string;
    };
  };
  mode_visibility: Array<{
    id: "paper" | "shadow" | "manual_live" | "autonomous_live" | string;
    label: string;
    state: "active" | "available" | "ready" | "blocked" | string;
    tone: "emerald" | "sky" | "amber" | "rose" | string;
    summary: string;
    blockers: string[];
  }>;
  source_degraded_mode: {
    mode: "normal" | "paper_only" | "exit_only" | string;
    state: "ready" | "review" | "degraded" | string;
    trust_state: string;
    live_entries_allowed: boolean;
    paper_collection_allowed: boolean;
    protective_exits_available: boolean;
    entry_blockers: string[];
    exit_blockers: string[];
    operator_action: string;
  };
  runtime_connectivity: {
    source_connected: boolean;
    rpc_available: boolean;
    rpc_balance_checked: boolean;
    signer_available: boolean;
    recovery_debt_clear: boolean;
    safe_for_new_entry: boolean;
    blockers: string[];
    operator_action: string;
  };
  full_sniper_gate: {
    mode: "full_sniper" | string;
    ready: boolean;
    state: "ready" | "blocked" | string;
    entry_ready: boolean;
    exit_ready: boolean;
    active_backend_matches: boolean;
    source_mode: string;
    pre_run_backup_fresh: boolean;
    manual_live_verified: boolean;
    manual_live_audit_id: string;
    manual_live_verified_at: string | null;
    manual_live_window_hours: number | null;
    audited_override_active: boolean;
    override_effect: string;
    blockers: string[];
    operator_action: string;
  };
  manual_live_verification: {
    verified: boolean;
    audit_id: string;
    verified_at: string | null;
    window_hours: number;
    wallet_public_key: string;
    signer_mode: string;
    blocker: string;
    operator_action: string;
  };
  pre_run_backup: PreRunBackupStatus;
  active_intent_count: number;
  stale_quote_count: number;
  unresolved_audit_count: number;
  recoverable_audit_count: number;
  last_live_poll_at: string | null;
  poller_status: string;
  recovery_summary: {
    checked: number;
    updated: number;
    skipped: boolean;
    reason?: string;
    errors?: string[];
  };
  latest_reconciliation_status: string;
  wallet_adapter: WalletAdapterStatus;
  execution_backend: {
    mode: string;
    submit_path: string;
    implemented: boolean;
    local_only: boolean;
    manual_approval_required: boolean;
    unattended_submit_available: boolean;
    can_submit_now: boolean;
    blockers: string[];
    operator_action: string;
  };
  live_pnl: {
    realized_pnl_sol: number;
    unrealized_pnl_sol: number;
    cost_basis_sol: number;
    open_positions?: number;
    approximate: boolean;
  };
  readiness_warnings: string[];
  hot_wallet: HotWalletStatus;
  active_backend: {
    armed: boolean;
    mode: string;
    wallet_public_key: string;
  };
  backend_capabilities: Record<string, SignerStatus>;
  entry_autonomy_available: boolean;
  exit_autonomy_available: boolean;
}

export interface LiveAutonomyGate {
  action: "buy" | "sell" | string;
  label: string;
  stage: string;
  available: boolean;
  blockers: string[];
  active_backend_matches: boolean;
  recovery_debt_blocks_entries: boolean;
  operator_action: string;
}

export interface PilotReadinessReport {
  artifact_type: "cryptoarc_tiny_pilot_readiness" | string;
  format_version: number;
  generated_at: string;
  wallet_public_key: string;
  signer_mode: string;
  status: "ready" | "blocked" | string;
  ready: boolean;
  stage: string;
  gates: Array<{
    id: string;
    label: string;
    status: "pass" | "fail" | string;
    value: string | number | boolean;
    target: string | number | boolean;
    reason: string;
  }>;
  runbook_checklist: Array<{
    id: "launch" | "run" | "stop" | "recover" | "review" | string;
    label: string;
    status: "ready" | "blocked" | string;
    blockers: string[];
    actions: Array<{
      label: string;
      command?: string;
    }>;
    operator_action: string;
  }>;
  blockers: string[];
  operator_action: string;
  evidence: {
    source?: SourceHealth;
    source_soak?: SourceSoakAcceptanceReport;
    readiness?: Record<string, unknown>;
    live_status?: LiveStatus;
    live_ledger?: LiveLedger;
    backup_restore?: BackupRestoreStatus;
    pre_run_backup?: Record<string, unknown>;
    caps?: LiveCapsSnapshot;
    [key: string]: unknown;
  };
  privacy_note: string;
}

export interface PostRunReviewReport {
  artifact_type: "cryptoarc_post_run_review" | string;
  format_version: number;
  generated_at: string;
  timeframe: string;
  wallet_public_key: string;
  status: "clear" | "review_required" | string;
  ready: boolean;
  summary: {
    audits: number;
    confirmed_or_reconciled: number;
    unresolved: number;
    needs_review: number;
    incident_export_candidates: number;
    pending_incident_exports: number;
  };
  checklist: Array<{
    id: string;
    label: string;
    status: "pass" | "fail" | "review" | "empty" | string;
    value: string | number | boolean;
    target: string | number | boolean;
    reason: string;
  }>;
  run_controls: {
    kill_switch_enabled: boolean;
    kill_switch_events: TradeEvent[];
    caps: LiveCapsSnapshot;
    audits_missing_caps_snapshot: number;
    audit_caps_snapshots: Array<{
      audit_id: string;
      mint: string;
      action: string;
      caps_snapshot: LiveCapsSnapshot | Record<string, unknown>;
    }>;
  };
  incident_exports: Array<{
    reviewed: boolean;
    exported?: boolean;
    review_event_id?: string;
    reviewed_at?: string | null;
    review_note?: string;
    audit_id: string;
    mint: string;
    action: string;
    status: string;
    final_status: string;
    wallet_public_key: string;
    reason: string;
    export_path: string;
  }>;
  recent_live_audits: LiveExecutionAudit[];
  action_items: string[];
  operator_action: string;
  privacy_note: string;
}

export interface OpenRiskReport {
  status: "clear" | "warning" | "blocked" | string;
  wallet_public_key: string;
  open_positions: number;
  active_intents: number;
  unresolved_audits: number;
  cost_basis_sol: number;
  unrealized_pnl_sol: number;
  realized_pnl_sol: number;
  total_live_pnl_sol: number;
  wallet_exposure_cap_sol: number;
  exposure_ratio: number | null;
  daily_loss_cap_sol: number;
  daily_loss_used_ratio: number | null;
  stale_balance_positions: number;
  needs_review_positions: number;
  pnl_confidence: string;
  blockers: string[];
  warnings: string[];
  action_items: string[];
  operator_action: string;
}

export interface OperatorSessionReport {
  artifact_type: "cryptoarc_operator_session_report" | string;
  format_version: number;
  generated_at: string;
  timeframe: string;
  wallet_public_key: string;
  bot: Record<string, unknown>;
  paper_pnl: MonitorPnlSummary;
  mode_comparison: PerformanceAnalytics["mode_comparison"];
  live_ledger: LiveLedger;
  open_risk: OpenRiskReport;
  source: SourceHealth;
  source_quality: {
    status: string;
    trust_state: string;
    health_score: number;
    events: number;
    normalized: number;
    trade_events: number;
    malformed: number;
    normalized_ratio: number;
    degraded_buckets: number;
    bucket_count: number;
    warnings: string[];
    operator_action: string;
  };
  readiness: Record<string, unknown>;
  live_recovery: {
    last_poll_at: string | null;
    summary: Record<string, unknown>;
    unresolved_audits: LiveExecutionAudit[];
  };
  alerts: AlertStatus;
  backup_restore: BackupRestoreStatus;
  recent_events: TradeEvent[];
  action_items: string[];
}

export interface EvidenceModeSeparationReport {
  artifact_type: "cryptoarc_evidence_mode_separation" | string;
  format_version: number;
  generated_at: string;
  status: "clear" | "review" | string;
  ready: boolean;
  modes: Array<{
    mode: "paper" | "replay" | "shadow" | "manual_live" | "autonomous_live" | string;
    label: string;
    samples: number;
    pnl_sol: number;
    source: string;
    boundary: string;
    status: "clear" | "review" | "missing" | string;
    latest_at: string | null;
    operator_action: string;
    evaluated?: number;
    pending?: number;
    submitted?: number;
    fingerprinted?: number;
    sources?: string[];
  }>;
  contamination_warnings: string[];
  operator_action: string;
  privacy_note: string;
}

export interface OutcomeExplanation {
  id: string;
  at: string;
  outcome_type: "buy" | "skip" | "sell" | "block" | "override" | "recovery" | string;
  status: string;
  subject: string;
  mint: string;
  token_id: string;
  reason: string;
  recommended_action: string;
  evidence: Record<string, unknown>;
}

export interface OutcomeExplanationsReport {
  artifact_type: "cryptoarc_outcome_explanations" | string;
  format_version: number;
  generated_at: string;
  timeframe: string;
  limit: number;
  summary: {
    total: number;
    by_type: Record<string, number>;
    by_status: Record<string, number>;
  };
  outcomes: OutcomeExplanation[];
  action_items: string[];
  operator_action: string;
  privacy_note: string;
}

export interface SetupReadinessReport {
  artifact_type: "cryptoarc_setup_readiness" | string;
  format_version: number;
  generated_at: string;
  status: "ready" | "review" | "blocked" | string;
  ready_for_paper: boolean;
  gates: Array<{
    id: string;
    label: string;
    status: "pass" | "warn" | "fail" | string;
    value: string | number | boolean;
    target: string | number | boolean;
    reason: string;
  }>;
  blockers: string[];
  warnings: string[];
  operator_action: string;
  next_steps: string[];
  evidence: Record<string, unknown>;
  privacy_note: string;
}

export interface ReleaseReadinessReport {
  artifact_type: "cryptoarc_release_readiness" | string;
  format_version: number;
  generated_at: string;
  app_version: string;
  frontend_version: string;
  status: "ready" | "review" | "blocked" | string;
  ready: boolean;
  gates: Array<{
    id: string;
    label: string;
    status: "pass" | "warn" | "fail" | string;
    value: string | number | boolean;
    target: string | number | boolean;
    reason: string;
  }>;
  blockers: string[];
  warnings: string[];
  next_steps: string[];
  operator_action: string;
  evidence: Record<string, unknown>;
  privacy_note: string;
}

export interface ReleaseVerificationAttestation {
  artifact_type: "cryptoarc_release_verification" | string;
  app_version: string;
  verify_passed: boolean;
  diff_reviewed: boolean;
  docs_reviewed: boolean;
  verified: boolean;
  event_id: string;
  recorded_at: string;
  status: "verified" | "incomplete" | string;
  note?: string;
  privacy_note: string;
}

export interface IncidentExportReviewAttestation {
  artifact_type: "cryptoarc_incident_export_review" | string;
  audit_id: string;
  mint: string;
  wallet_public_key: string;
  exported: boolean;
  reviewed: boolean;
  complete: boolean;
  event_id: string;
  recorded_at: string;
  status: "reviewed" | "incomplete" | string;
  note?: string;
  privacy_note: string;
}

export type LiveIntentSource = "manual" | "watchlist" | "paper_promoted" | "live_position_rules" | string;

export interface WalletAdapterStatus {
  mode: string;
  manual_approval_required: boolean;
  can_sign: boolean;
  can_unattended_sign: boolean;
  supports_auto_sell: boolean;
  supports_auto_buy: boolean;
  disabled_reason: string;
}

export interface LiveQuotePreview {
  id: string;
  created_at: string;
  intent_id: string;
  provider: string;
  action: "buy" | "sell";
  mint: string;
  amount: string;
  denominated_in_sol: boolean;
  slippage_pct: number;
  priority_fee_sol: number;
  pool: string;
  status: string;
  unsigned_transaction_base64: string;
  error: string;
  expires_at: string | null;
  stale: boolean;
}

export interface LiveSimulationResult {
  id: string;
  created_at: string;
  quote_id: string;
  status: string;
  ok: boolean;
  warning: string;
  error: string;
  result: Record<string, unknown>;
}

export interface LiveIntent {
  id: string;
  created_at: string;
  updated_at: string;
  action: "buy" | "sell";
  mint: string;
  amount: string;
  denominated_in_sol: boolean;
  signer_mode: string;
  wallet_public_key: string;
  status: string;
  reason: string;
  source: LiveIntentSource;
  symbol: string;
  score: number;
  priority: number;
  quote_id: string;
  audit_id: string;
  expires_at: string | null;
  stale: boolean;
  warnings: string[];
  autonomy_blocked: boolean;
  autonomy_blockers: string[];
  operator_recommendation: string;
  priority_reason: string;
  generated_from_position: boolean;
}

export interface LiveExecutionAudit {
  id: string;
  created_at: string;
  updated_at: string;
  action: "buy" | "sell" | "profit_sweep" | string;
  mint: string;
  amount: string;
  status: string;
  signer_mode: string;
  wallet_public_key: string;
  quote: Record<string, unknown>;
  simulation: Record<string, unknown>;
  request: Record<string, unknown>;
  preflight_checks: Array<{
    id: string;
    label: string;
    status: "pass" | "warn" | "fail" | string;
    value: unknown;
    target: unknown;
    reason: string;
  }>;
  caps_snapshot: Record<string, unknown>;
  balance_snapshot: Record<string, unknown>;
  transaction_signature: string;
  confirmation_status: string;
  errors: string[];
  warnings: string[];
  final_status: string;
  intent_id: string;
  reconciliation_status: LiveReconciliationStatus;
  reconciliation: Record<string, unknown>;
  confirmation: Record<string, unknown>;
  confirmation_checked_at: string | null;
  recovery_attempts: number;
  last_recovery_error: string;
  recommended_action: string;
}

export type LiveReconciliationStatus = "pending" | "matched" | "needs_review" | string;

export interface LiveFill {
  id: string;
  created_at: string;
  audit_id: string;
  intent_id: string;
  action: "buy" | "sell";
  mint: string;
  amount: string;
  amount_sol: number;
  token_amount: number;
  price_sol: number;
  fee_sol: number;
  priority_fee_sol: number;
  signature: string;
  accounting?: Record<string, unknown>;
}

export interface LiveRecentFill {
  id: string;
  created_at: string;
  position_id: string;
  wallet_public_key: string;
  mint: string;
  symbol: string;
  action: string;
  amount: string;
  signature: string;
  fee_sol: number;
  priority_fee_sol: number;
  wallet_sol_delta_sol: number;
  wallet_sol_received_sol: number;
  wallet_sol_spent_sol: number;
  token_delta: number;
  realized_pnl_delta_sol: number;
  provenance: string;
  reconciliation_status: string;
}

export interface LiveCostBasis {
  cost_basis_sol: number;
  realized_pnl_sol: number;
  unrealized_pnl_sol: number;
  average_entry_price_sol: number;
}

export interface LiveLedgerPosition extends LiveCostBasis {
  id: string;
  created_at: string;
  updated_at: string;
  mint: string;
  wallet_public_key: string;
  symbol: string;
  status: string;
  token_balance: number;
  total_fees_sol: number;
  total_priority_fees_sol: number;
  fills: LiveFill[];
  cost_basis_method: string;
  cost_basis_breakdown: Record<string, unknown>;
  realized_pnl_events: Array<Record<string, unknown>>;
  reconciliation_status: LiveReconciliationStatus;
  reconciliation: Record<string, unknown>;
  review_notes: string;
  mark_price_sol: number;
  mark_price_source: string;
  mark_price_confidence: number;
  mark_price_at: string | null;
  mark_price_age_seconds: number | null;
  balance_verified_at: string | null;
  balance_age_seconds: number | null;
  realized_pnl_confidence: string;
  unrealized_pnl_confidence: string;
  pnl_confidence_notes: string[];
}

export interface LiveLedger {
  positions: LiveLedgerPosition[];
  recent_fills: LiveRecentFill[];
  summary: {
    realized_pnl_sol: number;
    unrealized_pnl_sol: number;
    net_pnl_sol: number;
    total_pnl_sol: number;
    cost_basis_sol: number;
    total_fees_sol: number;
    total_priority_fees_sol: number;
    open_positions: number;
    approximate: boolean;
    pnl_confidence?: string;
    confidence_counts?: Record<string, number>;
    stale_mark_positions?: number;
    stale_balance_positions?: number;
    needs_review_positions?: number;
    pnl_note?: string;
    wallet_public_key?: string;
  };
}

export interface RentRecoveryAccount {
  token_account: string;
  mint: string;
  owner: string;
  program_id: string;
  token_amount: number;
  token_amount_raw: string;
  decimals: number;
  lamports: number;
  rent_sol: number;
  eligible: boolean;
  reason: string;
}

export interface RentRecoveryScan {
  wallet_public_key: string;
  eligible_accounts: RentRecoveryAccount[];
  ineligible_accounts: RentRecoveryAccount[];
  eligible_count: number;
  ineligible_count: number;
  recoverable_rent_sol: number;
  manual_approval_required: boolean;
  operator_action: string;
}

export interface RentRecoveryPreview {
  audit_id: string;
  wallet_public_key: string;
  selected_accounts: RentRecoveryAccount[];
  selected_count: number;
  recoverable_rent_sol: number;
  unsigned_transaction_base64: string;
  manual_approval_required: boolean;
  status: string;
  warnings: string[];
}

export interface LivePosition {
  mint: string;
  symbol: string;
  token_balance: number;
  estimated_value_sol: number;
  source: string;
  warning: string;
}

export interface BotSnapshot {
  status: BotStatus;
  settings: BotSettings;
  tokens: TokenSignal[];
  events: TradeEvent[];
  stats: BotStats;
  source_status: SourceStatus;
}
