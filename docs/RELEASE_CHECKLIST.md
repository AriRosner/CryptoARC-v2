# CryptoARC v2 Release Checklist

Use this checklist before tagging a local release, starting a live-testing session, or handing the project to another agent.

## Required Local Checks

- Confirm git status and review all local changes.
- Run `powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1` on fresh or changed environments.
- Run `powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1 -Strict`.
- Run `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`.
- Confirm `scripts\audit-mobile.ps1 -Strict` is `ready` or reports only the
  unexpired exception documented in
  `docs/security/mobile-image-size-risk-acceptance.md`.
- Run `powershell -ExecutionPolicy Bypass -File scripts\audit-frontend.ps1 -Strict`.
- Record `/api/reports/release-readiness/verification` after verification, git diff review, and release-doc review so the release-readiness manual gate has local evidence.
- Confirm GitHub Actions CI is green for backend tests, frontend build, frontend dependency audit policy, and docs links.
- Confirm backend tests pass.
- Confirm frontend build passes.
- Confirm local Markdown links pass.
- Confirm `.env` exists and live trading is intentionally configured.

## Data And Storage

- Confirm schema status is OK from the Data & Safety or ops surface.
- Create a backup before any live-testing session.
- Confirm restore preview can read the backup artifact.
- Keep local database files out of git.

## Paper And Source Smoke Test

- Start the local app with `scripts\restart-dev.ps1`.
- Run `scripts\status-dev.ps1` and use the printed active backend/frontend URLs.
- Confirm backend health at the active backend `/health` endpoint.
- Confirm the active frontend URL loads.
- Confirm the bot starts and stops in paper mode.
- Confirm source health is expected for the selected source.
- Confirm no unexpected watchdog or safety warnings appear.

## Live Safety Gate

- Keep `LIVE_TRADING_ENABLED=false` unless this is an intentional local live test.
- Confirm paper mode remains the default.
- Confirm active wallet and signer mode are explicit.
- Confirm max trade size, daily loss cap, wallet exposure cap, slippage cap, and priority-fee cap are configured.
- Confirm kill switch behavior before any real-money session.
- Confirm unresolved audits and recovery debt are zero before new entries.

## Autonomous Launch / Run / Stop / Recover Checklist

Use this concise checklist for the first local full autonomous sniper pilot.

### Launch

- Run `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`.
- Confirm PumpPortal source health is acceptable and raw source events are archived.
- Confirm recent paper or replay evidence, at least five evaluated shadow comparisons from the last 24 hours, and non-negative recent shadow PnL.
- Confirm the selected wallet has a confirmed and reconciled tiny manual-live proof from the last 24 hours.
- Confirm live cap values show operator-intent settings-version evidence in the pilot readiness report.
- Create a fresh local backup artifact.
- Confirm live env, session acknowledgement, tiny caps, selected wallet, signer mode, and local backend arming are intentional.

### Run

- Arm only the selected local backend.
- Confirm `full_sniper_gate.ready` is true in `/api/live/status`.
- Run only under tiny max trade, daily loss, exposure, max open position, slippage, and priority-fee caps.
- Watch live audit, ledger, source, cap, and kill-switch evidence while the pilot is active.

### Stop

- Enable the live kill switch to stop new entries immediately.
- Disarm the backend after the run or on any source, wallet, cap, audit, or ledger blocker.
- Stop the bot if source health becomes stale/conflicting, wallet identity changes, caps are breached, or unresolved audits appear.

### Recover

- Recover or inspect unresolved live audits before any new entry.
- Resolve stale balance evidence and `needs_review` ledger confidence.
- Use backup/restore preview and restore smoke test before trusting restored local state.

### Review

- Open `/api/reports/post-run-review` after every pilot.
- Export incident bundles for failed, stale, blocked, or needs-review audits.
- Confirm every live action has audit, transaction, ledger, cap, kill-switch, and PnL evidence.
- Do not start the next pilot until post-run review is clear.

## Handoff Notes

- Update `docs/roadmap/01-launch-critical-path.md` if setup, verification, source health, or live-safety assumptions changed.
- Update `docs/AI_HANDOFF.md` when new major subsystems, commands, or safety boundaries are added.
- Confirm `scripts\audit-frontend.ps1` reports `ready` with no acknowledged exception when the audit is clear. If the recognized `@solana/web3.js -> jayson -> uuid` advisory signature reappears with npm's breaking `@solana/web3.js@0.0.3` fix, keep it as an explicit review item until a compatible remediation is verified.
- Preserve the no-seed-phrase and localhost-only live-execution boundaries.
