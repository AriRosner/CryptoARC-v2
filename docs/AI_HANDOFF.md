# CryptoARC v2 AI Handoff

Use this as the first context block when handing the project to another AI agent.

## Project Summary

CryptoARC v2 is a local-first FastAPI + React/TypeScript/Vite dashboard for Pump.fun/PumpPortal monitoring, research, replay, backtesting, paper trading, and carefully gated manual live-money workflows.

The codebase is not a toy. Preserve existing bot logic, state management, settings semantics, and safety controls unless explicitly asked to change them.

## Current Safety Boundary

- Paper trading remains the default operating mode.
- Browser-wallet live trading is manual only and requires user wallet approval.
- CryptoARC does not store private keys, seed phrases, raw signer material, or custodial trading API keys.
- Local signer daemon support is design-only and disabled.
- Browser wallets cannot unattended-sign, so auto-sell and autonomous live execution remain unavailable.
- `LIVE_TRADING_ENABLED=false` blocks live quote/sign/submit paths by default.
- Recovery and reconciliation are read-only checks against recorded signatures and RPC balances; they never sign, send, resubmit, or create transactions.

## Important Paths

- Backend app: `backend/app/main.py`
- Backend state: `backend/app/core/state.py`
- Backend models: `backend/app/core/models.py`
- SQLite storage: `backend/app/core/storage.py`
- PumpPortal/mock sources: `backend/app/core/sources.py`
- Paper trader: `backend/app/core/paper_trader.py`
- Strategy/risk: `backend/app/core/strategy.py`, `backend/app/core/risk.py`
- Solana read-only client: `backend/app/core/solana_readonly.py`
- Frontend dashboard: `frontend/src/main.tsx`
- Frontend API/types: `frontend/src/api.ts`, `frontend/src/types.ts`
- Core tests: `tests/test_core.py`

## Current Major Features

- PumpPortal and mock launch source support.
- Token monitor, watchlist, token detail forensics, and animated cyber-terminal dashboard.
- Persistent events, prices, trades, sessions, strategy decisions, settings versions, experiments, labels, presets, live intents, audits, and live ledger positions.
- Paper trader with fees, slippage, price impact, fill delay, failed fills, trailing stop, partial TP, cooldowns, max trades/hour, max position ticks, break-even/stalled/sell-pressure exits.
- Readiness scorecard for paper edge validation.
- Live Wallet modal with browser-wallet manual flow, caps, blockers, quote preview, simulation warning, sign/send, positions, audit records, and recovery/review.
- Manual Live Trust Layer: backend-assisted confirmation polling, manual recovery endpoints, and best-effort ledger reconciliation.
- Auth with password, session tokens, login lockout, and optional authenticator-app 2FA.

## Verification Commands

```powershell
$env:PYTHONPATH='backend'
python -m unittest discover -s tests -p "test_*.py" -q

cd frontend
npm run build
```

## Agent Rules

- Do not use other projects on the PC as context.
- Inspect `git status` first and preserve user changes.
- Do not remove settings, inputs, buttons, dashboard pages, wallet flows, token detail fields, or audit surfaces during redesign work.
- Use existing code patterns and keep changes narrowly scoped.
- Never introduce private-key storage, seed phrase fields, custodial trading API keys, or unattended signing without a separate reviewed plan.
- Do not turn strategy decisions into direct live transaction submission. Strategy may create intents; execution remains a separate manual layer.

## Good Starting Prompt For Another AI

You are continuing CryptoARC v2 in `C:\Users\hrpho\Downloads\SniperBotPOC_v3`, GitHub repo `https://github.com/AriRosner/CryptoARC-v2`, branch `main`. Start by checking `git status --short --branch`, then read this file, `README.md`, `docs/LIVE_TRADING_DESIGN.md`, `backend/app/core/state.py`, `backend/app/main.py`, `frontend/src/main.tsx`, `frontend/src/api.ts`, and `frontend/src/types.ts`.

Preserve the paper-first safety boundary. Browser-wallet live trading is manual only. Do not add private-key storage, seed phrases, custodial API keys, local signer daemon execution, auto-sell, auto-buy, or autonomous transaction submission unless explicitly requested through a new safety plan. Run backend tests and frontend build before committing.
