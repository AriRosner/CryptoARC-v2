# 09 Settings Reference

This reference groups important settings by subsystem and explains their runtime effect.

For the authoritative type shape, see `BotSettings` in `frontend/src/types.ts`.

## Source

- `launch_source`
  Selects `mock` or `pumpportal`.
- `detect_new_tokens`
  Controls whether the bot adds new launches automatically.
- `auto_refresh`
  Enables dashboard auto-refresh behavior.
- `source_stale_seconds`
  Defines when the source is treated as stale.
- `source_max_reconnects`
  Limits source reconnect attempts.
- `max_trade_subscriptions`
  Controls how many trade subscriptions the source layer can keep active.

## Strategy Core

- `strategy_profile`
  High-level preset such as conservative, balanced, aggressive, scalper, custom.
- `trade_size_sol`
  Default paper-trade size.
- `trading_speed`
  Strategy cadence and aggressiveness helper.
- `score_threshold`
  Minimum score needed for entry.
- `max_open_positions`
  Limits concurrent positions.
- `launch_interval_seconds`
  Affects launch pacing in controlled/runtime behavior.

## Strategy Weights

- `strategy_weight_metadata`
- `strategy_weight_momentum`
- `strategy_weight_pressure`
- `strategy_weight_creator`

These weights tune how the strategy scoring model values each signal family.

## Risk And Filters

- `risk_tolerance`
- `daily_loss_cap_sol`
- `wallet_balance_cap_sol`
- `max_creator_hold_pct`
- `filter_honeypots`
- `filter_rug_risk`
- `duplicate_symbol_penalty`
- `strict_metadata_checks`
- `min_buy_velocity`
- `max_sell_pressure`
- `min_metadata_score`
- `max_token_age_seconds`

These settings shape which launches remain eligible and how far the bot can push risk.

## Exit Behavior

- `take_profit_pct`
- `stop_loss_pct`
- `max_hold_time_seconds`
- `minimum_hold_time_seconds`
- `max_position_ticks`
- `trailing_stop_enabled`
- `trailing_stop_pct`
- `partial_take_profit_enabled`
- `partial_take_profit_pct`
- `partial_take_profit_fraction`
- `break_even_stop_enabled`
- `break_even_after_profit_pct`
- `stalled_trade_exit_enabled`
- `stalled_trade_seconds`
- `stalled_trade_min_move_pct`
- `sell_pressure_exit_enabled`
- `sell_pressure_exit_threshold`

These collectively define how positions are reduced or exited.

## Simulation / Paper Model

- `paper_fill_delay_ticks`
- `paper_fee_bps`
- `paper_price_impact_pct`
- `paper_failed_fill_pct`
- `paper_price_volatility_pct`

These affect how realistic or strict the paper model feels.

## Safety Controls

- `kill_switch_enabled`
- `max_consecutive_losses_enabled`
- `max_consecutive_losses`
- `halt_on_low_replay_confidence`
- `min_replay_confidence`
- `halt_on_low_readiness`
- `min_readiness_score`
- `stop_on_source_degraded`
- `max_rejected_price_streak_enabled`
- `max_rejected_price_streak`

These are the main runtime brake systems.

## Price And Confidence

- `use_observed_prices`
- `min_price_confidence`
- `max_first_observed_move_pct`
- `prefer_market_cap_price`

These settings influence price selection and rejection behavior.

## Solana And External Inputs

- `solana_rpc_url`
- `watch_wallet_address`

These support read-only RPC and wallet balance visibility.

## Live Settings

- `manual_live_enabled`
- `manual_live_max_sol`
- `autonomous_live_enabled`
- `live_trading_enabled`
- `live_max_trade_sol`
- `live_daily_loss_cap_sol`
- `live_wallet_exposure_cap_sol`
- `live_max_open_positions`
- `live_max_slippage_pct`
- `live_priority_fee_cap_sol`
- `live_session_acknowledged`
- `live_signer_mode`
- `live_active_backend_armed`
- `live_active_wallet_public_key`
- `live_hot_wallet_enabled`
- `live_hot_wallet_public_key`
- `live_hot_wallet_label`

These govern whether live flows are allowed, what backend is active, and what caps apply.

## Direct Solana Paper Collection

- `direct_solana_paper_enabled`
- `direct_solana_min_confidence`

These allow decoded Solana `logsSubscribe` create evidence to enter paper monitoring only. The default is off. Even when enabled, this path does not grant live-source authority or bypass source-soak, readiness, signer, cap, backup, or recovery gates.

## UX And Dashboard

- `enable_trade_toasts`
- `compact_table_mode`
- `mode`
- `require_live_confirmation`

These settings change operator-facing behavior and display surfaces.

## Security

Dashboard password and TOTP configuration are managed through the security surfaces and backend auth endpoints rather than ordinary trading controls.

## Operator Alerts

Telegram alerts are configured with local environment variables, not stored dashboard settings:

- `TELEGRAM_ALERTS_ENABLED`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_ALERT_MIN_INTERVAL_SECONDS`

The dashboard can show route status and send a test alert, but it never returns the bot token. Critical alerts are deduplicated by category and rate-limited by the configured interval.

## Screenshot Placeholder

Screenshot: `assets/screenshots/settings/settings-modal-sections.png`
