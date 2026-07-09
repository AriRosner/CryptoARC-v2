# Launch Critical Path

## Goal

Reach a usable local full autonomous sniper bot in two weeks. The launch target is not perfection; it is a product Ari can operate locally with real money under tiny caps, clear stop controls, and enough evidence to avoid reckless execution.

## Current State

CryptoARC already has the bones needed for a launch push:

- local FastAPI and React workstation app
- setup, doctor, docs-link, and verification scripts
- PumpPortal ingestion, source health, and raw event capture
- replay, paper, shadow, backtest, and promotion workflows
- live quote/submit plumbing, browser-wallet/manual live paths, and local hot-wallet support
- hard caps, live acknowledgement, backend arming, kill switch, ledger, backups, recovery, and post-run review
- release attestation and incident-export review surfaces

The remaining work is to prove and tighten the shortest real-money autonomous path, not expand the product surface.

## Week 1: Make The Loop Operable

1. Stabilize setup and verification.
   - Run bootstrap, doctor, release verifier, and full verification.
   - Fix only blockers that prevent a clean local launch workflow.

2. Collect fresh paper and shadow evidence.
   - Use PumpPortal as the launch source.
   - Accept existing promotion and shadow thresholds unless they are clearly broken.
   - Do not pause launch for deeper model science.

3. Prove the selected wallet manually.
   - Run a tiny browser-wallet or manual live trade flow.
   - Confirm and reconcile it in the ledger.
   - Treat wallet mismatch, failed reconciliation, or stale proof as launch blockers.

4. Dry-run the autonomous path.
   - Arm the local backend.
   - Enable live mode intentionally, then keep trade sizes at dust-level caps.
   - Exercise quote, preflight, buy, position tracking, sell/exit, ledger update, and kill switch behavior.

5. Fix only launch blockers.
   - Prioritize execution correctness, stuck positions, ledger confidence, kill-switch reliability, and recovery.
   - Move polish and strategy improvements to the backlog.

## Week 2: Prove Tiny Real-Money Autonomy

1. Run a capped autonomous pilot.
   - Use the smallest useful caps.
   - Keep the run local.
   - Stop immediately on unresolved audit, source staleness, wallet mismatch, cap breach, or kill-switch failure.

2. Review the run.
   - Check live audit evidence, ledger confidence, PnL, open positions, incidents, and exported reports.
   - Confirm every live action is explainable after the run.

3. Patch only pilot blockers.
   - Fix failures that directly prevent a safe usable launch.
   - Do not chase nice-to-have UI or analytics during this phase.

4. Write the exact operator checklist.
   - Start app.
   - Verify environment.
   - Connect source.
   - Select strategy.
   - Confirm evidence.
   - Arm live mode.
   - Run.
   - Stop.
   - Recover.
   - Review.

5. Tag usable autonomous local launch.
   - Tag only after the checklist works end to end and the must-have safety gates pass.

## Definition Of Done

The launch roadmap is complete when:

- `scripts/verify.ps1` passes on the launch machine
- docs links pass
- the app can run locally without code edits
- PumpPortal source health is visible and acceptable
- selected strategy has fresh paper/shadow evidence
- selected wallet has a recent confirmed and reconciled manual live proof
- local backend can be armed and disarmed intentionally
- autonomous live mode runs under tiny caps
- kill switch stops new execution immediately
- ledger and post-run review explain every live action
- unresolved audits and stale ledger confidence block unattended operation
- Ari has one concise launch/run/stop/recover checklist

