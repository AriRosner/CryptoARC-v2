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
- Dashboard auth with optional authenticator-app 2FA.
- Docker-ready deployment structure with a paper/live safety boundary.

## Safety Boundary

CryptoARC v2 does not execute live trades. The backend exposes a paper-only safety boundary and refuses live execution unless a future executor is explicitly added and enabled through environment-level controls.

Default safety assumptions:

- No private-key storage.
- No automatic wallet signing.
- `LIVE_TRADING_ENABLED=false` in normal use.
- Dashboard password should be set before any network deployment.
- Optional TOTP 2FA is available.
- Paper-only mode remains the default and recommended mode.

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
- `DASHBOARD_PASSWORD`
- `DASHBOARD_TOTP_SECRET`
- `ALLOWED_ORIGINS`
- `LIVE_TRADING_ENABLED`

For any deployment beyond localhost, set a strong dashboard password, restrict CORS origins, use HTTPS, and keep live trading disabled.

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
- `GET /api/monitoring/ops`
- `GET /api/trade-review/{token_id}`
- `GET /api/replay/timeline/{token_id}`
- `GET /api/security/status`

## Dashboard Pages

- **Monitor**: live token queue, sidebar PnL, event stream, queue filters, watchlist.
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
- Keep live execution out of scope until the paper engine, replay data, auth, and audit systems are mature.

## Disclaimer

CryptoARC v2 is research software. It is not financial advice, does not guarantee profitable trading, and currently does not provide live execution. Token launches can be risky, volatile, manipulated, or illiquid. Use paper mode for research and validation.
