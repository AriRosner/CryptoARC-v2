# 11 Operations And Recovery

This guide is the day-to-day playbook for operating CryptoARC safely and recovering from common issues.

## Daily Startup

1. Start backend and frontend.
2. Log in.
3. Confirm bot status, API state, and source state.
4. Review Data & Safety for watchdog or safety warnings.
5. Confirm active wallet and PnL scope.
6. Start the bot only after source and safety look sane.

## Daily Shutdown

1. Stop the bot.
2. Confirm source/event activity settles.
3. Review unresolved audits or live recovery state if live features were used.
4. Create a backup if the session included important changes or trades.

## Backup Workflow

Use local backup artifacts before:

- upgrades
- risky config or schema work
- restore tests
- major operating sessions

## Restore Workflow

1. Open restore preview.
2. Validate artifact details.
3. Confirm restore intentionally.
4. Re-check schema status, health, and readiness.
5. Review live audit/recovery state if relevant.

## Common Operational Scenarios

### Bot looks stale

- Check watchdog
- Check source health
- Use Recover Bot once
- Restart backend if stale state persists

### Source degraded

- Review source status and reconnect attempts
- Check event age and normalized ratio
- Do not trust live decisions until source health recovers

### Strange PnL behavior

- Check price diagnostics
- Check price confidence and rejected observations
- Use Trade Review and Analysis together

### Live wallet looks blocked

- Open live workspace
- Review blockers
- Review caps, kill switch, and readiness
- Confirm active wallet and signer mode

## Verification Routine

Recommended recurring verification:

```powershell
$env:PYTHONPATH='backend'
python -m unittest discover -s tests -p "test_*.py" -q

cd frontend
npm run build
```

## Screenshot Placeholders

- `assets/screenshots/ops/watchdog-recovery.png`
- `assets/screenshots/ops/backup-restore-flow.png`
