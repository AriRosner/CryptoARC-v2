# 15 Troubleshooting

Use this section as a symptom-driven checklist.

## The bot will not start

Check:

- backend is running
- auth/session is valid
- settings are not malformed
- source configuration is present
- backend logs for startup exceptions

## The monitor is empty

Check:

- source health
- launch source selection
- `detect_new_tokens`
- source event age
- watchdog status

## PnL looks wrong

Check:

- price diagnostics
- rejected observations
- selected price confidence
- paper model settings
- review detail and settings version

## Watchdog reports stale state

1. Open Data & Safety.
2. Inspect watchdog and source quality.
3. Use Recover Bot.
4. Restart backend if stale state persists.

## Live wallet shows blockers

Check:

- `LIVE_TRADING_ENABLED`
- live settings and caps
- session acknowledgement
- signer mode
- wallet connection / unlock state
- kill switch
- readiness

## Hot wallet will not unlock

Check:

- correct password
- imported vault exists
- no corruption in local vault file
- backend error messages for vault status

## Signer daemon is unavailable

Check:

- endpoint is localhost-only
- daemon process is actually running
- health endpoint responds
- auth/capability is configured correctly

## Restore completed but system looks wrong

Check:

- migration/runtime schema state
- source health
- safety/readiness status
- live audit and ledger state
- active wallet selection

## Frontend build or UI issues

Run:

```powershell
cd frontend
npm run build
```

Then inspect:

- recent UI changes in `frontend/src/App.tsx`
- page components
- `Sidebar.tsx`
- `SettingsModal.tsx`

## Backend test failures

Run:

```powershell
$env:PYTHONPATH='backend'
python -m unittest discover -s tests -p "test_*.py" -q
```

Then inspect:

- `backend/app/main.py`
- `backend/app/core/state.py`
- `backend/app/core/storage.py`
- `tests/test_core.py`
