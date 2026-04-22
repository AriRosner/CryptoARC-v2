# CryptoARC v2

CryptoARC v2 is a local-first FastAPI + React dashboard for Pump.fun and PumpPortal monitoring, research, backtesting, paper trading, and carefully gated localhost live execution.

This repository now uses a full documentation hub under [`docs/manual/INDEX.md`](docs/manual/INDEX.md).

## Start Here

- New operators: [`docs/manual/02-quickstart.md`](docs/manual/02-quickstart.md)
- Dashboard tour: [`docs/manual/03-dashboard-tour.md`](docs/manual/03-dashboard-tour.md)
- Live wallet and wallet manager: [`docs/manual/10-wallets-and-live-trading.md`](docs/manual/10-wallets-and-live-trading.md)
- Operations and recovery: [`docs/manual/11-operations-and-recovery.md`](docs/manual/11-operations-and-recovery.md)
- Developer architecture: [`docs/manual/12-developer-architecture.md`](docs/manual/12-developer-architecture.md)
- API and data reference: [`docs/manual/13-api-and-data-reference.md`](docs/manual/13-api-and-data-reference.md)

## Core Facts

- Paper mode is the default and recommended operating mode.
- Live execution is localhost-only and gated by environment, settings, caps, readiness, and audit controls.
- Browser wallet execution is assisted/manual unless the wallet environment explicitly supports unattended approval.
- Encrypted local hot-wallet support exists for localhost use only.
- Seed phrases remain out of scope.

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

## Verification

```powershell
$env:PYTHONPATH = "backend"
python -m unittest discover -s tests -p "test_*.py" -q

cd frontend
npm run build
```

## Existing Focused Docs

- Deployment: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- Live execution design: [`docs/LIVE_TRADING_DESIGN.md`](docs/LIVE_TRADING_DESIGN.md)
- Security notes: [`docs/SECURITY.md`](docs/SECURITY.md)
- Pump.fun research: [`docs/PUMPFUN_RESEARCH.md`](docs/PUMPFUN_RESEARCH.md)
- AI handoff: [`docs/AI_HANDOFF.md`](docs/AI_HANDOFF.md)
- Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md)

## Documentation Hub

Open [`docs/manual/INDEX.md`](docs/manual/INDEX.md) for the full operator and developer manual.
