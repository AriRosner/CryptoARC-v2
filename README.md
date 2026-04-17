# CryptoARC v2

CryptoARC v2 is a local-first Pump.fun token monitoring and paper-trading dashboard. The first build is intentionally non-custodial and paper-only: it simulates trades, records decisions, and exposes the dashboard shape before any live wallet execution is added.

## Current Scope

- Local development first, deployable web architecture later.
- Python backend with FastAPI.
- React frontend with Vite and TypeScript.
- Pump.fun-focused token launch monitoring, mocked in the MVP.
- Paper trading only.
- Manual wallet signing first when live trading is eventually added.

## Safety Defaults

- Live trading is disabled in the MVP.
- The backend exposes a paper-only safety boundary at `/api/security/status`.
- Set `DASHBOARD_PASSWORD` before deploying the dashboard beyond localhost.
- Optional authenticator-app 2FA can be enabled with `DASHBOARD_TOTP_SECRET`.
- Default paper trade size: `0.1 SOL`.
- Default take profit: `50%`.
- Default stop loss: `30%`.
- Future live daily loss cap: `1 SOL`.
- Future live mode requires an explicit risk confirmation every app start.
- Future live mode should refuse wallets above a configurable balance cap.

## Project Layout

```text
backend/
  app/
    core/          Pure trading, scoring, and risk logic
    main.py        FastAPI app and WebSocket API
frontend/
  src/             React dashboard
docs/
  ROADMAP.md       Build roadmap and milestones
tests/
  test_core.py     Dependency-light Python core tests
```

## Backend Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r backend\requirements.txt
py -m uvicorn app.main:app --reload --app-dir backend
```

Backend URL: `http://127.0.0.1:8000`

## Frontend Setup

Node.js is required for the dashboard dev server.

```powershell
cd frontend
npm install
npm run dev
```

Frontend URL: `http://127.0.0.1:5173`

## Test Core Logic

```powershell
$env:PYTHONPATH = "backend"
py -m unittest discover -s tests
```

## Deployment Checklist

- Copy `.env.example` to `.env` and set a strong `DASHBOARD_PASSWORD`.
- Set `ALLOWED_ORIGINS` to the deployed frontend origin only.
- Keep `LIVE_TRADING_ENABLED=false`; this project currently has no live transaction executor.
- Put the app behind HTTPS if it is reachable outside your machine.
- Use the Data & Safety page to confirm auth, 2FA, source health, and the paper-only boundary.

## Docker Compose

```powershell
copy .env.example .env
docker compose up --build
```

The compose setup keeps backend data in the `cryptoarc-data` volume and exposes:

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`

Run `.\scripts\healthcheck.ps1` after startup to verify the frontend, backend, and source state.

## MVP Behavior

The backend generates mock Pump.fun-style token launches. The scoring engine analyzes each launch, the risk engine decides whether a paper trade is allowed, and the paper trader simulates buy/monitor/sell behavior. The dashboard receives live updates over WebSocket.
