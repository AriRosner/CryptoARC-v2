# CryptoARC v2

CryptoARC v2 is a local-first Pump.fun launch monitoring, research, backtesting, and paper-trading dashboard. It is built to help study token-launch strategies without custody, private keys, or live transaction execution.

> Status: active paper-trading research platform. Live trading is intentionally blocked by default.

## Highlights

- Real-time token queue with Pump.fun/PumpPortal source support.
- Paper-only position engine with fees, slippage, price impact, partial take profit, trailing stop, and optional advanced exits.
- Strategy Engine v3 with rule-level decision logs, configurable profile weights, and risk guardrails.
- Price Engine v3 with direct, market-cap, virtual-reserve, selected-price, confidence, and rejection diagnostics.
- Backtesting v3 with deterministic replay fingerprints, strategy comparison, and walk-forward validation.
- Trade Review page with PnL breakdown, decision records, source/price timeline, and settings-version context.
- Data Integrity reports for replay confidence, missing records, rejected prices, and malformed source events.
- Pump.fun intelligence summaries for creator behavior, metadata coverage, bonding curve fields, and launch quality.
- Operational monitoring for backend state, source health, storage counts, warnings, and safety guard state.
- Stability watchdog with loop recovery status for production paper deployments.
- Solana read-only RPC health and watched-wallet balance checks.
- Manual browser-wallet live intent workbench with caps, quote previews, simulation warnings, audit records, confirmation recovery, and reconciliation.
- Wallet-scoped PnL views with paper/live wallet switching and SOL/USD display toggle.
- Faster start/stop feedback with immediate runtime shutdown of source streaming and queued launch processing.
- Dashboard auth with optional authenticator-app 2FA.
- Docker-ready deployment structure with a paper/live safety boundary.

## Feature Map

### Bot Core

- Live launch monitoring from mock streams or PumpPortal.
- Paper-only buy, monitor, and sell lifecycle.
- Fee, slippage, price-impact, fill-delay, and failed-fill modeling.
- Configurable take profit, stop loss, max hold, max ticks, trailing stop, partial TP, break-even stop, stalled-trade exit, and sell-pressure exit.

### Research And Intelligence

- Pump.fun intelligence for creator reuse, metadata coverage, bonding curve fields, market-cap presence, initial buys, and creator concentration.
- Price Engine v4 foundations with selected-price diagnostics, confidence floors, direct/market-cap/virtual reserve candidates, rejected-observation review, and minute-level price candles.
- Source Adapter Layer V2 with adapter capability, confidence, and status contracts.

### Strategy And Risk

- Strategy Engine v3 module snapshots for scoring, risk guards, position sizing, exits, and source quality.
- Strategy Builder presets from the dashboard and persistent server-side preset storage.
- Risk Controller V2 with manual kill switch, source-degraded halt, daily loss cap, max open positions, consecutive-loss halt, and replay-confidence halt.

### Backtesting And Experiments

- Token replay, raw source replay, strategy comparison, and A/B replay.
- Backtesting v3 with deterministic fingerprints and walk-forward train/validate checks.
- Saved experiment runs with settings version, profile, replay source, notes, and fingerprint.
- Auto-tuning suggestions that can ignore manually labeled trades.

### Trade Review

- Persistent trade records with settings version context.
- Per-trade PnL breakdown including fees, slippage, impact, and net-before-fees estimate.
- Source, price, decision, and execution timeline.
- Manual labels such as good entry, bad entry, bad exit, bad price data, held too long, exited too early, rug-like behavior, and ignore from tuning.

### Operations And Deployment

- Data integrity and replay-confidence reports.
- SQLite schema metadata and runtime migration status.
- Local database backup endpoint.
- Operational monitoring for backend state, source health, storage counts, warnings, and errors.
- Watchdog status for stale bot ticks, source events, launch ingestion age, and recover action.
- Solana read-only status for RPC health and public wallet balance checks.
- Dashboard password auth, session expiry, login lockout, and optional authenticator-app 2FA.
- GitHub Actions CI for backend tests and frontend builds.

## Safety Boundary

CryptoARC v2 is paper-first. Live-money support is limited to a local manual browser-wallet flow that requires explicit environment enablement, user-set caps, and wallet approval for every transaction. The backend does not store signer material and does not autonomously sign, send, or resubmit transactions.

Default safety assumptions:

- No private-key storage.
- No automatic wallet signing or unattended live execution.
- `LIVE_TRADING_ENABLED=false` in normal use.
- Dashboard password should be set before any network deployment.
- Optional TOTP 2FA is available.
- Paper-only mode remains the default and recommended mode.
- Browser-wallet live actions are manual and audited; legacy manual live requests remain audit records only.
- Autonomous live mode remains blocked until a reviewed executor, signer flow, and risk controller exist.

## Architecture

```text
backend/
  app/
    auth.py                 Dashboard auth and TOTP helpers
    config.py               Environment loading
    main.py                 FastAPI, WebSocket, and API routes
    core/
      models.py             Dataclasses and API payload shapes
      state.py              Bot state, replay, analytics, safety, monitoring
      storage.py            SQLite persistence
      strategy.py           Strategy Engine v3
      risk.py               Entry risk guardrails
      paper_trader.py       Paper position lifecycle and exits
      price_pipeline.py     Price Engine v3
      sources.py            Mock and PumpPortal sources
      integrity.py          Data quality and replay-confidence checks
      pumpfun_intelligence.py Pump.fun field research
frontend/
  src/
    main.tsx                Dashboard, settings, review, analysis, data pages
    api.ts                  API client
    types.ts                Shared frontend types
tests/
  test_core.py              Dependency-light backend core tests
scripts/
  restart-dev.ps1           Local dev process restart
  healthcheck.ps1           Local service health checks
```

## Local Setup

### Backend

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r backend\requirements.txt
$env:PYTHONPATH = "backend"
py -m uvicorn app.main:app --reload --app-dir backend
```

Backend: `http://127.0.0.1:8000`

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend: `http://127.0.0.1:5173`

### One-Command Local Restart

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restart-dev.ps1
```

## Testing

```powershell
$env:PYTHONPATH = "backend"
python -m unittest discover -s tests -p "test_*.py" -q

cd frontend
npm run build
```

## Docker

```powershell
copy .env.example .env
docker compose up --build
```

Exposed services:

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`

Run a health check after startup:

```powershell
.\scripts\healthcheck.ps1
```

## Environment

Start from `.env.example`:

- `DATABASE_PATH`
- `PUMPFUN_SOURCE`
- `PUMPPORTAL_WS_URL`
- `SOLANA_RPC_URL`
- `WATCH_WALLET_ADDRESS`
- `DASHBOARD_PASSWORD`
- `DASHBOARD_TOTP_SECRET`
- `ALLOWED_ORIGINS`
- `LIVE_TRADING_ENABLED`

For any deployment beyond localhost, set a strong dashboard password, restrict CORS origins, use HTTPS, and keep live trading disabled. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and [docs/LIVE_TRADING_DESIGN.md](docs/LIVE_TRADING_DESIGN.md).

## Key API Surfaces

- `GET /api/snapshot`
- `PATCH /api/settings`
- `POST /api/backtest/replay`
- `POST /api/backtest/raw-replay`
- `POST /api/backtest/compare`
- `POST /api/backtest/ab-replay`
- `POST /api/backtest/v3`
- `GET /api/analytics/performance`
- `GET /api/analytics/suggestions`
- `GET /api/data/integrity`
- `GET /api/price/diagnostics`
- `GET /api/pumpfun/intelligence`
- `GET /api/safety/status`
- `GET /api/watchdog/status`
- `POST /api/watchdog/recover`
- `GET /api/solana/status`
- `GET /api/live/status`
- `GET /api/live/intents`
- `POST /api/live/intents`
- `POST /api/live/intents/{id}/quote`
- `POST /api/live/intents/{id}/submit`
- `POST /api/live/intents/{id}/confirm`
- `POST /api/live/intents/{id}/reconcile`
- `GET /api/live/ledger`
- `GET /api/live/positions`
- `GET /api/live/audit`
- `POST /api/live/audit/recover-unresolved`
- `POST /api/live/audit/{id}/recover`
- `GET /api/live/requests`
- `POST /api/live/manual-request`
- `GET /api/monitoring/ops`
- `GET /api/trade-review/{token_id}`
- `GET /api/replay/timeline/{token_id}`
- `GET /api/security/status`

## Dashboard Pages

- **Monitor**: live token queue, sidebar PnL, event stream, queue filters, watchlist.
- **Monitor** also includes wallet-scoped PnL charting, hide-skips filtering, and compact token-monitor controls.
- **Analysis**: persistent PnL analytics, strategy performance, price diagnostics, Pump.fun intelligence, tuning suggestions.
- **Backtests**: replay, raw replay, strategy comparison, A/B replay, Backtesting v3 suite.
- **Trade Review**: closed-trade review, PnL breakdown, decision records, replay timeline.
- **Data & Safety**: integrity checks, source quality, monitoring, security state, exports, maintenance tools.

## Roadmap

Near-term priorities:

- Add formal database migrations.
- Add import/export restore flows for full local backups.
- Improve Pump.fun intelligence with additional trusted source adapters.
- Add richer replay filters and saved experiment runs.
- Add strategy-builder UX for cloning and comparing custom rule sets.
- Continue hardening the manual browser-wallet flow with stronger reconciliation, operator recovery, and richer live ledger accounting.
- Keep unattended signing and autonomous execution out of scope until a reviewed signer/executor architecture exists.

## AI Handoff

If another AI agent takes over this repo, start with [docs/AI_HANDOFF.md](docs/AI_HANDOFF.md). It summarizes the architecture, current safety boundary, verification commands, and the rules for preserving the paper-first/manual-only live trading model.

## Disclaimer

CryptoARC v2 is research software. It is not financial advice, does not guarantee profitable trading, and currently does not provide live execution. Token launches can be risky, volatile, manipulated, or illiquid. Use paper mode for research and validation.
