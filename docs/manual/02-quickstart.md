# 02 Quickstart

This guide gets a new user from clone to safe first use.

## Prerequisites

- Windows PowerShell environment
- Python installed
- Node.js and npm installed
- Local browser
- PumpPortal access only if using the live source

## Local Setup

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

### One-command local restart

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restart-dev.ps1
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
