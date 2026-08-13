# CryptoARC v2

![Source lines](https://img.shields.io/badge/source%20lines-96.8k-blue)

CryptoARC v2 is a local-first FastAPI + React dashboard for Pump.fun and PumpPortal monitoring, research, backtesting, paper trading, and carefully gated localhost live execution.

This repository now uses a full documentation hub under [`docs/manual/INDEX.md`](docs/manual/INDEX.md).

## Start Here

- New operators: [`docs/manual/02-quickstart.md`](docs/manual/02-quickstart.md)
- Dashboard tour: [`docs/manual/03-dashboard-tour.md`](docs/manual/03-dashboard-tour.md)
- Live wallet and wallet manager: [`docs/manual/10-wallets-and-live-trading.md`](docs/manual/10-wallets-and-live-trading.md)
- Operations and recovery: [`docs/manual/11-operations-and-recovery.md`](docs/manual/11-operations-and-recovery.md)
- Developer architecture: [`docs/manual/12-developer-architecture.md`](docs/manual/12-developer-architecture.md)
- API and data reference: [`docs/manual/13-api-and-data-reference.md`](docs/manual/13-api-and-data-reference.md)
- Mobile cockpit: [`docs/MOBILE_COCKPIT.md`](docs/MOBILE_COCKPIT.md)

## Core Facts

- Paper mode is the default and recommended operating mode.
- Live execution is localhost-only and gated by environment, settings, caps, readiness, and audit controls.
- Browser wallet execution is assisted/manual unless the wallet environment explicitly supports unattended approval.
- Encrypted local hot-wallet support exists for localhost use only.
- Seed phrases remain out of scope.

## Local Setup

### Bootstrap

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
powershell -ExecutionPolicy Bypass -File scripts\restart-dev.ps1
powershell -ExecutionPolicy Bypass -File scripts\status-dev.ps1
```

By default, the local URLs are:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

If a default port is already busy, `scripts\restart-dev.ps1` picks the next free local port and records the active URLs in `data\logs\dev-ports.json`. Run `scripts\status-dev.ps1` to see the exact backend and frontend URLs for the current session.

If Python or npm are not on PATH, set `CRYPTOARC_PYTHON`, `CRYPTOARC_NPM`, or `CRYPTOARC_PNPM` to the executable path before running the scripts.

`scripts\doctor.ps1` diagnoses Python, `.venv`, backend imports including `solders`, Node/package-manager availability, frontend dependencies, `@solana/web3.js`, and `.env`. Use `-Json` for a report artifact or `-Strict` for CI-style failure on blockers.

### Backend

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r backend\requirements.txt
$env:PYTHONPATH = "backend"
py -m uvicorn app.main:app --reload --app-dir backend
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

## Verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1 -Strict
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Manual fallback:

```powershell
$env:PYTHONPATH = "backend"
python -m unittest discover -s tests -p "test_*.py" -q

cd frontend
npm run build

cd ..\mobile
npm run typecheck
npm test
```

## Existing Focused Docs

- Deployment: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- Live execution design: [`docs/LIVE_TRADING_DESIGN.md`](docs/LIVE_TRADING_DESIGN.md)
- Security notes: [`docs/SECURITY.md`](docs/SECURITY.md)
- Mobile cockpit: [`docs/MOBILE_COCKPIT.md`](docs/MOBILE_COCKPIT.md)
- Pump.fun research: [`docs/PUMPFUN_RESEARCH.md`](docs/PUMPFUN_RESEARCH.md)
- AI handoff: [`docs/AI_HANDOFF.md`](docs/AI_HANDOFF.md)
- Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md)

## Documentation Hub

Open [`docs/manual/INDEX.md`](docs/manual/INDEX.md) for the full operator and developer manual.
