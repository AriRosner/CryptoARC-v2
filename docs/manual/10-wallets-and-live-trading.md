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
- Uses the repo-shipped guarded daemon contract when started locally
- Status and capability are surfaced in the app
- Submission is disabled by default unless the operator explicitly starts the daemon in submit mode

## Live Wallet Workspace

After setup, the workspace exposes:

- backend access
- blocker and cap review
- execution-readiness status for dry-run and shadow comparison
- autonomy control plane
- intent queue
- quote preview
- recovery and review
- positions
- latest audit

Screenshot: `assets/screenshots/live/live-wallet-workspace-overview.png`

Execution readiness summarizes quote attempts, stale quote pressure, blocked quote pressure, unresolved audits, live policy caps, bounded slippage/priority-fee recommendations, and shadow comparison results. Policy recommendations include cap room, quote issue categories, missed landing rate, timing evidence, and reasons so the operator can see why a suggestion exists. Every live quote audit records structured `preflight_checks` for the environment, mint, wallet, signer, amount, slippage, priority fee, pool, caps, and aggregate blockers before the quote can proceed. Live submission and autonomous execution refuse audits with failed preflight rows, so a quote cannot move to signing after cap, signer, pool, wallet, or aggregate blocker evidence fails. Ready dry-run buy quotes record a `shadow_comparison` on the live audit so later accepted prices, configured exit rules, and landing-delay windows can estimate whether a fast live entry would have won, lost, scratched, missed, or gone stale. When submitted/confirmed live audits exist, the landing windows are calibrated from recorded quote-to-submit and submit-to-confirm timing. A shadow-ready state means the quote/audit path is healthy enough for comparison work; it does not bypass signing, simulation, caps, or audit recovery.

Live cap readiness also requires settings-version evidence that the current cap values were saved through the operator settings flow. Direct database or in-memory cap changes are treated as missing operator intent and block the pilot cap gate.

Unsigned stale quotes remain quote-quality evidence and can block shadow readiness through stale quote pressure. They do not create live recovery debt because no transaction was submitted. Submitted, failed, needs-review, or signed unreconciled audits remain recovery debt until recovered or reviewed.

Post-run live review excludes shadow-only evidence audits. A pilot review is not satisfied by shadow-only quotes; it requires actual live audit evidence from the selected wallet/run.

The live status payload also exposes an `autonomy` object with separate `entry` and `exit` gate states. It reports whether the selected backend matches the armed backend, whether unresolved recovery debt blocks new entries, and whether expert override recording is available. Override recording is audit-only; it records target gate, action, reason, timestamp, blockers, active backend, kill-switch state, and caps, but it does not bypass live blockers.

`execution_backend` shows the selected submit path. Browser wallet reports `browser_wallet_manual_signature` and always requires operator approval. Local hot wallet reports `encrypted_local_hot_wallet`; it can submit unattended only when the encrypted wallet is unlocked, live env is enabled, and the matching backend is armed. Local signer daemon reports `localhost_signer_daemon` and remains blocked unless a localhost-only daemon is connected and healthy. Both daemon health and execute calls reject non-localhost endpoints before any signer request is sent.

## Local Signer Daemon Quick Start

Use this path for unattended automation only after manual-live proof is complete for the same wallet. Do not paste private keys or seed phrases into chat, issue trackers, docs, or logs.

The daemon accepts a private key only from the local operator environment:

```powershell
$env:CRYPTOARC_SIGNER_PRIVATE_KEY = "<base58-secret-key-or-json-byte-array>"
$env:CRYPTOARC_SIGNER_AUTH_TOKEN = "<local-random-token>"
scripts\start-signer-daemon.ps1 -AuthToken $env:CRYPTOARC_SIGNER_AUTH_TOKEN -MaxTradeSol 0.001
scripts\check-signer-daemon.ps1 -AuthToken $env:CRYPTOARC_SIGNER_AUTH_TOKEN
```

That startup keeps submit mode off. The health check is a no-trade check and never calls `/execute`.

For the later autonomous pilot, start the daemon only after caps, backup, source health, kill-switch state, and manual-live proof are reviewed:

```powershell
scripts\start-signer-daemon.ps1 -AuthToken $env:CRYPTOARC_SIGNER_AUTH_TOKEN -MaxTradeSol 0.001 -AllowSubmit
```

The backend must also be configured with the same token through `LIVE_SIGNER_DAEMON_AUTH_TOKEN` and the local URL through `LIVE_SIGNER_DAEMON_URL`. Keep the URL on `127.0.0.1` or `localhost`; remote signer URLs are rejected before any signer request is sent.

## Rent Recovery

The live wallet workspace includes a manual Rent Recovery tool for reclaiming SOL locked in unused token-account rent. It scans the selected wallet through RPC, lists only zero-balance token accounts as eligible, and excludes token accounts tied to open live positions.

Closing a token account is permanent. If the wallet later trades that mint again, the token account may need to be recreated and rent paid again. Use the preview step first, then sign the close transaction manually from the browser wallet. Rent recovery never runs automatically during trading and never closes accounts with nonzero token balances.

Hot-wallet status and launch-readiness reports expose only public wallet metadata, lock state, and the `local_encrypted_sidecar` storage scope. They do not expose the vault filesystem path, seed phrases, private keys, or encrypted payload fields. Database backup artifacts restore ledger and app state, but they intentionally do not embed the hot-wallet sidecar; after a restore, re-check the hot-wallet status and re-import or unlock the local wallet before arming `local_hot_wallet`. If the restored database still has old hot-wallet metadata but the sidecar is missing, startup, restore reload, and status checks clear the stale public key and label from live settings, persist that cleanup, and disarm any stale `local_hot_wallet` backend authorization.

`full_sniper_gate` is the final unattended buy-and-sell gate. It is ready only when entry autonomy, exit autonomy, active backend match, normal source mode, fresh pre-run backup, and a recent clean confirmed/reconciled manual-live proof for the selected wallet and selected signer path all pass. A proof audit with recorded errors, pending reconciliation, or review debt does not qualify. Override records remain audit-only and do not mark this gate ready.

Live status also includes `pre_run_backup`. New live buy entries require a fresh local backup artifact, currently within 24 hours and newer than the latest restore. Missing, stale, or restore-superseded backup evidence blocks entries until the operator creates a new backup artifact from the Data workspace.

## Active Backend And Arming

Only one backend can be armed at a time.

Arming means:

- the selected backend is the current authorized autonomous backend
- the selected wallet becomes the armed live wallet
- autonomous entries/exits remain subject to other gates

Disarming stops new autonomous execution through that backend.

Live-session acknowledgement records the current caps, active backend, kill-switch state, and timestamp in the event log. This is an operator acknowledgement, not a bypass.

The live workspace exposes explicit kill-switch controls. Enabling the kill switch records the reason and risk state, immediately blocks new entries, and leaves protective exits available when the selected backend can still sign. Buy submission re-checks the kill switch at the signing boundary, so a ready quote cannot be submitted after the operator stops entries. Clearing the kill switch is also audited and only allows entries again when all other gates pass.

Buy submission also re-checks entry policy before accepting a browser-wallet signature or invoking a local backend signer. If source trust, wallet exposure, daily loss, max open positions, signer health, or unresolved live-audit recovery debt changes after quote creation, the ready quote must be discarded and re-quoted after the blocker is resolved.

## Blockers And Caps

Common live blockers include:

- environment disabled
- missing caps
- missing session acknowledgement
- missing, stale, or restore-superseded pre-run backup
- no connected signer or wallet
- kill switch enabled
- readiness failures
- low replay confidence when the replay halt setting is enabled
- unresolved live-audit recovery debt

Protective exits can remain preparable when source trust or replay confidence blocks new entries, but only when signer, wallet, session, and cap requirements still pass. The workspace exposes blocker fix flows and confirmation steps for supported fixes.

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
- no unresolved live-audit recovery debt for new entries

If backend health degrades, entry autonomy can halt while protective exits remain allowed if the active backend can still execute them.

`GET /api/live/status` exposes `source_degraded_mode` so the Live workspace can show the current source-driven operating mode. `normal` means source trust is not forcing a downgrade. `paper_only` means live entries are blocked and the operator should keep collecting evidence. `exit_only` means source trust blocks new live entries while protective exit preparation remains available through the selected backend.

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

Recovery has a bounded retry policy. If RPC repeatedly cannot find a submitted signature, the audit escalates to `needs_review` after the retry cap, keeps the recovery-attempt count and last recovery error, and requires operator inspection instead of silent resubmission. Batch recovery summaries report checked, updated, needs-review, error, and max-attempt counts.

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
