# 02 Quickstart

This guide gets a new user from clone to safe first use.

## Prerequisites

- Windows PowerShell environment
- Python installed, or `CRYPTOARC_PYTHON` set to a `python.exe` path
- Node.js and npm installed, or `CRYPTOARC_NPM` / `CRYPTOARC_PNPM` set to a package-manager path
- Local browser
- PumpPortal access only if using the live source

## Local Setup

### One-command bootstrap

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

This creates `.venv`, installs backend dependencies, installs frontend dependencies, and creates `.env` from `.env.example` when `.env` is missing.

### Verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

This is the canonical local health check. It runs setup diagnostics, a backend import smoke test, backend unit tests, frontend build, and local Markdown link check.

### Frontend dependency audit

```powershell
powershell -ExecutionPolicy Bypass -File scripts\audit-frontend.ps1
```

This wraps `npm audit --json` with the project release policy. High, critical, and unacknowledged moderate advisories block release work. The current moderate `@solana/web3.js -> jayson -> uuid` advisory is treated as an acknowledged review item because npm's available fix downgrades `@solana/web3.js` to `0.0.3`.

### Setup diagnostics

```powershell
powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1
```

Use this before or after bootstrap when the workstation feels misconfigured. It checks the repository root, Python availability, `.venv`, backend imports including `solders`, Node/npm or pnpm, `frontend\node_modules`, `@solana/web3.js`, and `.env`. Add `-Json` for a machine-readable report or `-Strict` to return a failing exit code when required setup is missing.

### Start or restart the local app

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restart-dev.ps1
```

Default backend: `http://127.0.0.1:8000`

Default frontend: `http://127.0.0.1:5173`

If a default port is busy, the script automatically uses the next free local port and prints the active URLs. To check the current session later:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\status-dev.ps1
```

The active backend and frontend URLs are also stored in `data\logs\dev-ports.json`.

### Manual backend fallback

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r backend\requirements.txt
$env:PYTHONPATH = "backend"
py -m uvicorn app.main:app --reload --app-dir backend
```

### Manual frontend fallback

```powershell
cd frontend
npm install
npm run dev
```

## First Login

1. Open the frontend URL.
2. If dashboard auth is enabled, sign in with the configured password.
3. If TOTP is enabled, provide the authenticator code.
4. Wait for the dashboard shell to load.

Screenshot: `assets/screenshots/quickstart/login-screen.png`

## First Safe Configuration

Before starting the bot:

1. Open Settings.
2. Confirm `launch_source`.
3. Confirm the strategy profile and paper trade size.
4. Leave `LIVE_TRADING_ENABLED` effectively disabled for first use.
5. Confirm risk caps and filters.
6. Save settings.

## First Run Checklist

1. Stay in paper mode.
2. Confirm source health is connected or expected.
3. Confirm safety state shows no unexpected blockers.
4. Start the bot.
5. Watch the Monitor page for new tokens and event flow.
6. Confirm data is populating in Analysis, Review, and Data & Safety.

## First Verification Checks

- Bot status changes correctly when started and stopped.
- Source status receives events.
- Tokens appear in the monitor queue.
- Event toasts and status surfaces update.
- No critical watchdog or safety warnings appear.

## First Live-Wallet Rule

Do not begin with live execution. Learn the monitor, review, and recovery surfaces first. If you later use live mode, read [`10-wallets-and-live-trading.md`](10-wallets-and-live-trading.md) completely before arming any backend.

## Related Guides

- Dashboard tour: [`03-dashboard-tour.md`](03-dashboard-tour.md)
- Settings reference: [`09-settings-reference.md`](09-settings-reference.md)
- Operations and recovery: [`11-operations-and-recovery.md`](11-operations-and-recovery.md)
