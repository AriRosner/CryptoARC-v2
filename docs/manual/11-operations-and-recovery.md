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

## Local Autonomous Pilot Checklist

### Launch

1. Run `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`.
2. Confirm source health, paper/replay evidence, recent shadow evidence, and manual-live wallet proof.
3. Create a fresh local backup artifact.
4. Enable live env only for the intentional local pilot, acknowledge the session, confirm tiny caps, and arm the selected local backend.

### Run

1. Confirm `full_sniper_gate.ready` in live status.
2. Run only under tiny hard caps.
3. Watch source, audit, ledger, cap, and wallet evidence.

### Stop

1. Enable the kill switch to stop new entries.
2. Disarm the backend.
3. Stop the bot on stale source, wallet mismatch, cap breach, unresolved audit, or ledger confidence blocker.

### Recover

1. Recover or inspect unresolved live audits.
2. Resolve stale or `needs_review` ledger evidence.
3. Use backup/restore preview and restore smoke test before trusting restored local state.

### Review

1. Open the post-run review report.
2. Export incident bundles for failed, stale, blocked, or needs-review audits.
3. Confirm every live action has audit, transaction, ledger, cap, kill-switch, and PnL evidence before the next pilot.

## Backup Workflow

Use local backup artifacts before:

- upgrades
- risky config or schema work
- restore tests
- major operating sessions

Use Restore Smoke Test in the Data workspace before any real-money phase. It creates a fresh backup artifact, runs the restore preview validator against it, records a backup/restore audit event, and reports SQLite integrity, schema version, risk, payload size, warnings, and recommended actions without returning the embedded database payload.

## Restore Workflow

1. Open restore preview.
2. Validate artifact details.
3. Confirm restore intentionally.
4. Re-check schema status, health, and readiness.
5. Re-check local hot-wallet status; backup artifacts do not include the encrypted sidecar, and startup or restore reload persists a disarm of stale `local_hot_wallet` backend authorization until the local wallet is re-imported or unlocked and armed again.
6. Review live audit/recovery state if relevant.

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

## Production Gate Rehearsal

Run the safe default without starting services or touching a wallet/signer:

```powershell
$env:CRYPTOARC_PYTHON='C:\absolute\path\to\python.exe'
& .\scripts\rehearse-production-gates.ps1 -FixtureOnly
```

The fixture report is always ineligible for production and labels every physical step `DEFERRED`. A later physical window requires a fresh JSON authorization record with `scope=production-rehearsal`, `authorization_id`, and an unexpired timezone-aware `expires_at`. Even with that record, the harness only validates local tests and enumerates the physical checklist; it does not import, unlock, rotate, clear, or invoke a signer and it refuses to proceed if `LIVE_TRADING_ENABLED=true`.

Production evidence must cover password and TOTP persistence across restart, bearer-only APIs, exact wallet/signer identity, signer rotation and loss invalidation, source-loss entry blocking plus guarded protective-exit preparation, kill switch, fresh backup, restore preview/smoke/schema match, restart recovery, zero audit/ledger debt, tailnet-only exposure, notification limitations, and a fresh explicit acceptance of the transitive `image-size` build risk. No credential or secret belongs in a rehearsal report.

## Screenshot Placeholders

- `assets/screenshots/ops/watchdog-recovery.png`
- `assets/screenshots/ops/backup-restore-flow.png`
