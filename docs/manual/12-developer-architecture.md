# 12 Developer Architecture

This guide documents the actual current architecture of CryptoARC v2.

## High-Level Shape

- `backend/app/main.py`
  FastAPI entrypoint, auth integration, websocket/API routes
- `backend/app/core/state.py`
  Main runtime state, orchestration, analytics, safety, live control plane
- `backend/app/core/storage.py`
  SQLite persistence, migrations, backup/restore behaviors
- `backend/app/core/models.py`
  shared dataclasses and payload models
- `backend/app/core/hot_wallet.py`
  encrypted local hot-wallet vault

## Backend Module Responsibilities

### `main.py`

- exposes snapshot/start/stop/settings
- exposes analytics, backtests, safety, watchdog, solana, live, auth, and restore routes
- adapts HTTP requests into state operations

### `state.py`

- owns runtime bot state
- manages tokens, trades, events, sessions, analytics, and live execution state
- centralizes readiness, safety, and autonomy gating logic
- coordinates live intents, audits, positions, ledger, and reconciliation

### `storage.py`

- persists core entities in SQLite
- manages migrations and schema metadata
- supports backup/restore artifacts and restore preview/confirm flows

### `models.py`

- defines settings, payload, and reporting structures

### `hot_wallet.py`

- stores encrypted private-key material locally
- supports import, unlock, lock, clear
- can sign and submit transactions through the configured RPC path

### Supporting modules

- `paper_trader.py`
  paper position lifecycle and exit logic
- `strategy.py`
  strategy evaluation and decision logic
- `risk.py`
  risk guardrails
- `price_pipeline.py`
  price candidate selection and confidence logic
- `sources.py`
  source ingestion and normalization
- `integrity.py`
  data quality and replay confidence reporting
- `solana_readonly.py`
  read-only RPC access and confirmation checks
- `pumpfun_intelligence.py`
  launch/creator intelligence summaries

## Frontend Architecture

### `frontend/src/App.tsx`

- primary application shell and state container
- page selection
- modal ownership
- live-wallet guided flow and workspace
- refresh coordination and cross-surface data wiring

### Page components

- `MonitorPage.tsx`
- `AnalysisPage.tsx`
- `BacktestsPage.tsx`
- `ReviewPage.tsx`
- `DataPage.tsx`

### Common components

- `AppLayout.tsx`
- `Sidebar.tsx`
- `SettingsModal.tsx`
- `TokenTable.tsx`
- `TokenDetail.tsx`
- `PnlChart.tsx`

### API layer

- `frontend/src/api.ts`
  request wrapper and endpoint helpers
- `frontend/src/types.ts`
  frontend-visible state and API shapes

## Runtime Data Flow

1. Source events are ingested by the backend.
2. Runtime state evaluates and normalizes launch information.
3. Strategy/risk/price logic updates tokens and trade state.
4. Snapshot and specialized endpoints feed the frontend.
5. Frontend renders pages, modals, and operator controls.
6. Live actions flow back through API routes into the backend control plane.

## Live Control Plane

The live system is intentionally centralized:

- wallet selection
- signer status
- intent generation
- quote creation
- simulation
- submission
- confirmation
- reconciliation
- recovery

This prevents strategy logic from bypassing the audit and gating model.

## Storage Concepts

Persistent entities include:

- tokens
- events / source events
- trades / trade sessions
- settings versions
- presets
- experiments
- labels
- live intents
- live execution requests
- live audits
- live ledger positions
- backup/restore history
