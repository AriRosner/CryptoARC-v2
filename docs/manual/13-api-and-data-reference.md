# 13 API And Data Reference

This is a practical reference to the main API and data concepts used by the dashboard.

## Core Snapshot And Control

- `GET /api/snapshot`
  Main dashboard snapshot.
- `POST /api/start`
  Starts the bot runtime.
- `POST /api/stop`
  Stops the bot runtime.
- `PATCH /api/settings`
  Applies settings patch values.

## Analytics And Backtests

- `GET /api/analytics/performance`
- `GET /api/analytics/suggestions`
- `POST /api/analytics/suggestions/apply`
- `POST /api/backtest/replay`
- `POST /api/backtest/raw-replay`
- `POST /api/backtest/compare`
- `POST /api/backtest/ab-replay`
- `POST /api/backtest/v3`

## Data Quality And Safety

- `GET /api/data/integrity`
- `GET /api/price/diagnostics`
- `GET /api/pumpfun/intelligence`
- `GET /api/safety/status`
- `GET /api/readiness/status`
- `GET /api/watchdog/status`
- `POST /api/watchdog/recover`
- `GET /api/monitoring/ops`
- `GET /api/security/status`

## Solana Status

- `GET /api/solana/status`

Supports read-only RPC visibility and watched-wallet state.

## Live Status And Wallet Surfaces

- `GET /api/live/status`
- `GET /api/live/wallet/status`
- `POST /api/live/session/acknowledge`
- `POST /api/live/session/start`
- `POST /api/live/backend/arm`
- `POST /api/live/backend/disarm`

## Hot Wallet

- `GET /api/live/hot-wallet/status`
- `POST /api/live/hot-wallet/import`
- `POST /api/live/hot-wallet/unlock`
- `POST /api/live/hot-wallet/lock`
- `POST /api/live/hot-wallet/clear`

## Intents And Execution

- `GET /api/live/intents`
- `POST /api/live/intents`
- `POST /api/live/intents/generate`
- `POST /api/live/intents/{id}/cancel`
- `POST /api/live/intents/{id}/quote`
- `POST /api/live/intents/{id}/reconcile`
- `POST /api/live/quote`
- `POST /api/live/simulate`
- `POST /api/live/submit`
- `POST /api/live/confirm`

## Live Audit, Ledger, And Positions

- `GET /api/live/audit`
- `POST /api/live/audit/recover-unresolved`
- `POST /api/live/audit/{id}/recover`
- `GET /api/live/ledger`
- `GET /api/live/positions`

## Manual Live Requests

- `GET /api/live/requests`
- `POST /api/live/manual-request`
- `POST /api/live/requests/{id}/review`

## Review And Timeline

- `GET /api/trade-review/{token_id}`
- `GET /api/replay/timeline/{token_id}`

## Other Important Collections

- `/api/trades`
- `/api/trade-sessions`
- `/api/settings/versions`
- `/api/experiments`
- `/api/trade-labels`
- `/api/strategy-presets`

## Data Concepts

### Snapshot

Aggregated dashboard state for the main app shell.

### Settings version

Immutable captured settings state used for historical context.

### Intent

Live execution candidate record.

### Audit

Live execution record spanning quote, simulation, submission, and reconciliation.

### Ledger

Wallet-scoped live accounting summary.

### Position

Wallet/mint execution state with balance and PnL context.

### Restore artifact

Local backup package used for preview and confirmed restore.
