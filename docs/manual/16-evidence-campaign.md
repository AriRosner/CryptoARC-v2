# Evidence Campaign

This runbook separates software verification from genuine source, shadow, deployment, and live evidence. Missing evidence stays missing. Tests, fixtures, replay rows, prose, or manually entered prices cannot satisfy a genuine-evidence gate.

## Current evidence state

- Genuine source soak: DEFERRED
- Shadow campaign: DEFERRED
- Production rehearsal: DEFERRED
- Manual-live proof: DEFERRED
- Autonomous-live pilot: DEFERRED

These labels remain until the corresponding authoritative campaign is separately authorized and captured. They are blockers, not estimates.

## Genuine source evidence contract

Accepted market observations are additive records keyed by source, source event ID, and observed timestamp. Each record carries observed/received time, price, confidence, access state, conflict state, strategy identity, evidence mode, and an explicit `fixture_only` marker. Fixture rows, missing/future/naive/stale timestamps, duplicate identities, unavailable funded access, source conflicts, and strategy mismatches remain ineligible for shadow promotion.

Access failures are recorded separately from accepted observations so an unavailable paid stream cannot manufacture a zero-price sample. Direct Solana comparison sample IDs remain attributable. The seven-day source soak and funded or replacement trade-price access are still `DEFERRED` and require separate operator coordination; no credential is requested or configured by the software implementation.

## Capture exact Git state

Use a clean isolated worktree. This capture is Git-only: it does not start the backend, open the application database, connect to a source, inspect a wallet, or call a signer.

```powershell
& .\scripts\capture-evidence-inventory.ps1 `
  -BaseRef origin/main `
  -OutputPath 'C:\absolute\operator-selected\cryptoarc-evidence-inventory.json'
```

Prefer an output path outside the repository so the capture itself does not dirty the worktree. The script refuses to run when `git status --porcelain` is non-empty. It records HEAD, the selected base ref, their merge-base, branch, and clean status. It deliberately reports runtime readiness, source access, genuine observations, and shadows as unavailable or zero rather than manufacturing them.

## Read the authenticated inventory

`GET /api/reports/evidence-inventory` composes existing readiness, live-status, evidence-mode, pilot-readiness, post-run, and source-adapter reports. It is read-only and does not query Git. Unless an exact Git capture is explicitly supplied to the domain method by a trusted local caller, `code_state.exact_main_state_captured` is false and the inventory remains blocked.

Review these sections independently:

- `code_state`: exact Git identifiers and ancestry, when supplied.
- `active_strategy`: current profile/fingerprint; unversioned or unknown stays visible.
- `source_access`: configured access state and available adapters.
- `evidence`: genuine, fixture, rejected, shadow, and evaluated-shadow counts.
- `operations`: backup age/state, signer mode/status, and post-run status.
- `machine_verifiable_readiness`: deduplicated blockers from existing reports.
- `deferred_physical_evidence`: work that software and fixtures cannot complete.
- `authority`: must remain read-only with `authority_changed=false`.

## Campaign boundaries

Keep `LIVE_TRADING_ENABLED=false` during implementation and non-live evidence collection. Do not purchase or configure funded source access, create or fund wallets, unlock or invoke signers, acknowledge or arm a backend, submit or approve transactions, start shared runtimes or databases, or run full/mobile gates without separate authorization.

The future sequence remains:

1. Capture exact Git and machine-verifiable readiness.
2. Obtain separately authorized genuine trade-price source access.
3. Record attributable source-soak evidence and direct-chain comparisons.
4. Complete version-matched all-cost shadows over the approved sample and calendar window.
5. Rehearse production authentication, backup, restore, signer-loss, source-loss, shutdown, restart, reconciliation, and kill-switch behavior in a coordinated window.
6. Request separate authorization for manual-live proof.
7. Request separate authorization for an attended autonomous pilot.
8. Reconcile the run and record an explicit scale, hold, revise, or stop decision.

No step guarantees profit. Changed or stale market conditions return the strategy to source-connected paper and shadow validation.
