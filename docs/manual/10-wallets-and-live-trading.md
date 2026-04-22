# 10 Wallets And Live Trading

This guide documents the current wallet-management and live-execution system exactly as implemented, with localhost-only and paper-first warnings kept explicit.

## Important Safety Rules

- Live execution is intended for localhost use only.
- Paper mode remains the default and recommended mode.
- Browser-wallet execution is usually assisted/manual.
- Seed phrases are not supported.
- Network deployment should keep live execution disabled.

## Wallet Manager

The dashboard includes an active wallet selector with:

- paper wallet
- tracked live wallets
- add wallet
- manage wallet
- remove selected wallet

The wallet manager controls which wallet-scoped views and live ledgers the dashboard is showing.

Screenshot: `assets/screenshots/live/wallet-manager-sidebar.png`

## Live Wallet Guided Flow

The live wallet modal is a guided setup flow with named stages:

- Choose Path
- Connect / Import / Unlock
- Review
- Confirm
- Ready

Screenshot: `assets/screenshots/live/live-wallet-stepper.png`

## Backend Paths

### Browser wallet

- Best for assisted/manual operation
- Usually requires wallet approval in the browser
- Useful for quote preview, simulation, manual signing, audit, and reconciliation

### Local hot wallet

- Private-key import only
- Encrypted at rest locally
- Requires password unlock each app start
- Can be used for localhost unattended execution when gates are satisfied

### Local signer daemon

- Must stay localhost-only
- Depends on an external daemon implementing the expected contract
- Status and capability are surfaced in the app

## Live Wallet Workspace

After setup, the workspace exposes:

- backend access
- blocker and cap review
- autonomy control plane
- intent queue
- quote preview
- recovery and review
- positions
- latest audit

Screenshot: `assets/screenshots/live/live-wallet-workspace-overview.png`

## Active Backend And Arming

Only one backend can be armed at a time.

Arming means:

- the selected backend is the current authorized autonomous backend
- the selected wallet becomes the armed live wallet
- autonomous entries/exits remain subject to other gates

Disarming stops new autonomous execution through that backend.

## Blockers And Caps

Common live blockers include:

- environment disabled
- missing caps
- missing session acknowledgement
- no connected signer or wallet
- kill switch enabled
- readiness failures

The workspace exposes blocker fix flows and confirmation steps for supported fixes.

Screenshot: `assets/screenshots/live/live-blocker-fix-flow.png`

## Intent Lifecycle

1. Strategy or operator creates an intent.
2. Intent can be quoted.
3. Quote can be simulated.
4. Transaction can be signed/submitted by the selected backend.
5. Audit records track the full flow.
6. Confirmation and reconciliation update the result.

## Autonomy Gates

Autonomous live depends on:

- `LIVE_TRADING_ENABLED=true`
- dashboard settings enabling the required live mode
- one armed backend
- matching wallet
- passing readiness, caps, and kill-switch checks
- backend capability support

If backend health degrades, entry autonomy can halt while protective exits remain allowed if the active backend can still execute them.

## Audit, Confirmation, And Recovery

Live execution is always centered on:

- intents
- quotes
- simulation
- submission/audit record
- confirmation polling
- reconciliation
- recovery endpoints

The recovery/review surfaces are meant to help reconcile recorded activity. They should not be treated as silent resubmission machinery.

Screenshot: `assets/screenshots/live/live-recovery-review.png`

## Recommended Operator Workflow

1. Select the active wallet.
2. Open Manage wallet / Live wallet.
3. Choose the backend path.
4. Resolve blockers and confirm caps.
5. Acknowledge the session and arm the backend if appropriate.
6. Create/generate intents.
7. Quote, simulate, review, and submit carefully.
8. Monitor audit, confirmation, and reconciliation state.
