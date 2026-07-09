# CryptoARC-v2 Memory

## Project
- Local-first Solana/Pump.fun autonomous sniper bot, currently optimized for paper/shadow evidence and safety-gated manual/live operation.
- Root: `C:\Users\Ari Rosner\Projects\CryptoARC\CryptoARC-v2`.
- Goal bias: make the local autonomous bot usable with must-have launch safety gates; defer polish to `docs/roadmap/03-post-launch-backlog.md`.

## Stack
- Backend: Python FastAPI/Uvicorn, SQLite storage, `websockets`, `solders`, local hot-wallet/signing helpers, PumpPortal + optional Solana logs verifier.
- Frontend: React 19 + TypeScript + Vite + Tailwind CSS, lucide icons, framer-motion, Recharts, `@solana/web3.js`.
- Mobile: companion app/API work exists under `mobile/` plus mobile cockpit docs.
- Dev scripts: `scripts/start-dev.ps1`, `scripts/stop-dev.ps1`, `scripts/status-dev.ps1`, `scripts/reset-runtime-state.ps1`.

## Recent Architecture
- PumpPortal launch stream now uses the public websocket URL with API key stripped; keyed trade subscriptions run on a separate websocket after real mints appear.
- Source health ignores trade rows for normalization ratio, treats startup/reconnect as warning, and reports stopped/idle as healthy.
- Websocket/start/stop snapshots are compact: no full token list, recent events only; token monitor refreshes separately via `/api/tokens`.
- Added source connection telemetry: `connection_requested_at`, `connected_at`, `first_event_at`, `startup_ms`, `first_event_ms`.
- Added cached `/api/latency/status`: backend loop latency, PumpPortal public probe, source startup state, dashboard RTT in frontend.
- Dashboard status supports `connecting`, `reconnecting`, `disconnected`; reconnect/disconnected still use Stop because bot runtime is active.
- Polling storm fixed: stable refresh callbacks, in-flight guards, `npm run check:polling`; latency failures now preserve last good payload and show stale/error instead of clearing to dashes.
- Dev process cleanup hardened with manifest/port-owner stop/start scripts to avoid stale/orphan processes.

## Safety/Trading Features Added
- PumpPortal API wallet funding detection/notification when trade-stream evidence silently stops.
- Profit Vault Sweep added with fixed-SOL and percentage modes, minimum profit, reserve, cooldown, max/day, destination wallet, and sweep history UI.
- Live/manual safety gates include hard caps, kill switch, local signing/hot wallet flows, backup/recovery, live audit/reconciliation surfaces.
- Trade review and tuning surfaces improved: labels, queues, skeleton loaders, performance/tuning suggestions, ignored-trade handling.

## Current State
- Dev stack should be started with `scripts/start-dev.ps1`; bot remains stopped until started manually from dashboard.
- Dashboard URL: `http://127.0.0.1:5173`; backend URL: `http://127.0.0.1:8000`.
- After the latest restart, bot was stopped; latency endpoint returned PumpPortal connected while source was idle.
- Worktree is very dirty with many related roadmap/backend/frontend/docs/mobile changes; do not revert unrelated edits.

## Verification Habits
- Frontend: `cd frontend; npm run check:polling; npm run build`.
- Backend focused tests: `$env:PYTHONPATH='backend'; .\.venv\Scripts\python.exe -m unittest ...`.
- Backend compile: `python -m py_compile backend/app/main.py backend/app/core/state.py backend/app/core/sources.py`.
- Runtime sanity: `scripts/status-dev.ps1`, `/api/latency/status`, `/api/source-health`, `/health/deep`.

## Coding Conventions
- Use `apply_patch` for manual edits; avoid destructive git commands.
- Prefer existing patterns and focused patches; no unrelated refactors.
- PowerShell on Windows; quote paths with spaces and prefer repo scripts over ad hoc process killing.
- Frontend controls should be dense, operational, and consistent with existing dashboard UI; use lucide icons where appropriate.
- Keep API/websocket payloads compact and avoid render-triggered polling loops; add in-flight guards for repeated dashboard refreshes.
