# 01 Overview

CryptoARC v2 is a single-user local workstation for Pump.fun and PumpPortal token-launch monitoring, research, replay, backtesting, paper trading, and tightly gated localhost live execution.

## Project Goals

- Detect and inspect new launches quickly.
- Evaluate launches using strategy, scoring, risk, and price-confidence logic.
- Train and validate behavior through replay and backtests.
- Operate paper trading as the default production mode.
- Expose live execution only through explicit operator-controlled gates.
- Preserve durable auditability, recovery, and local data ownership.

## Core Operating Model

- Backend: FastAPI app plus stateful bot runtime and SQLite persistence.
- Frontend: React/TypeScript/Vite dashboard rooted in `frontend/src/App.tsx`.
- Data store: SQLite with formal ordered migrations and restore support.
- Source layer: mock stream or PumpPortal realtime feed.
- Execution layers:
  paper trading
  assisted/manual browser-wallet live
  encrypted localhost hot wallet
  localhost signer-daemon contract path

## Safety Boundary

- Paper mode is the default and recommended operating mode.
- `LIVE_TRADING_ENABLED=false` is the normal default.
- Live execution is intended for localhost use only.
- Seed phrases are not supported.
- Browser-wallet execution is assisted/manual unless the environment explicitly supports unattended approval.
- Encrypted hot-wallet support is available for localhost use only.
- One live backend can be armed per session.
- All live paths remain behind readiness, cap, kill-switch, and audit controls.

## Major Capability Areas

### Monitoring

- Live token queue
- Watchlist
- Token detail forensics
- Queue and event stream scanning
- Wallet-scoped PnL display

### Research

- Analysis page diagnostics
- Pump.fun intelligence summaries
- Price diagnostics and confidence reporting
- Tuning suggestions

### Replay And Backtesting

- Replay backtests
- Raw source replay
- Strategy comparison
- A/B replay
- Backtesting v3
- Saved experiments

### Review

- Trade review detail
- PnL breakdown
- Timeline/replay context
- Labels and notes

### Data, Safety, And Ops

- Data integrity
- Watchdog status and recovery
- Safety status
- Operational monitoring
- Security status
- Backup/restore

### Wallets And Live Execution

- Active wallet selector including paper wallet
- Guided live wallet modal
- Assisted browser-wallet mode
- Encrypted hot-wallet mode
- Signer-daemon status contract
- Intent queue
- Quote/simulate/sign/send
- Audit, confirmation, reconciliation, and recovery

## Glossary

- Snapshot: the primary combined dashboard payload returned by `/api/snapshot`.
- Intent: a live trade candidate awaiting quote, review, or execution.
- Audit: the durable record of live quote/simulation/submission/reconciliation activity.
- Ledger: wallet-scoped live execution accounting and summary.
- Armed backend: the single live backend currently authorized for autonomous execution.
- Readiness: runtime health/safety evaluation used to allow or block behavior.
- Watchdog: stale-runtime detection and recovery helper.

## Screenshot Placeholder

Screenshot: `assets/screenshots/overview/project-shell.png`
Recommended capture: logged-in dashboard shell with sidebar and top-level pages visible.
