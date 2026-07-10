# Live Trading Design

CryptoARC v2 now includes a localhost live-execution control plane in addition to its paper-trading workflow. This document describes what exists today, what is still constrained, and which safety boundaries must remain intact.

## Current Runtime Model

Implemented today:

- `LIVE_TRADING_ENABLED=false` remains the default environment posture.
- Live execution is wallet-scoped and local-first.
- One active live backend can be armed per session.
- Browser-wallet execution is assisted/manual unless the wallet environment exposes unattended approval.
- Encrypted local hot-wallet execution is available for localhost use after explicit private-key import and password unlock.
- Local signer-daemon support is localhost-only and the repo ships a minimal guarded daemon for local operator use.
- Every live path runs through intent, quote, simulation, submission, audit, confirmation, and reconciliation state.

## Backend Paths

### Browser Wallet

Current behavior:

- Best for assisted/manual live review.
- Browser approval is still expected in normal environments.
- Useful for quote preview, simulation review, manual signing, reconciliation, and audit visibility.

### Local Hot Wallet

Current behavior:

- Private-key import only. Seed phrases remain out of scope.
- Key material is encrypted at rest in the local vault.
- Unlock is required each app start.
- Can support localhost unattended execution once the operator explicitly enables autonomy, configures caps, acknowledges risk, and arms the backend.

### Local Signer Daemon

Current behavior:

- Must stay localhost-only.
- CryptoARC can probe daemon health/capability state and route through the daemon contract.
- `scripts\start-signer-daemon.ps1` starts the local daemon and `scripts\check-signer-daemon.ps1` performs a no-trade health check.
- Submission is disabled by default. The daemon signs/submits only when started with explicit submit mode, a local private key in the operator environment, and a policy that allows the request.
- This path should still be treated as infrastructure-dependent until the daemon health check, selected wallet, caps, backup, source health, and manual-live proof are current.

## Execution Flow

Live execution is intentionally explicit:

```text
strategy decision / operator action
  -> live intent
  -> quote creation
  -> simulation
  -> signing backend
  -> submission
  -> confirmation polling
  -> reconciliation
  -> audit + ledger update
```

The strategy layer should continue to create intents, not bypass the live control plane.

## Autonomy Gates

Autonomous live is possible only when all of these are true:

- `LIVE_TRADING_ENABLED=true`
- dashboard live settings enable the required live mode
- a single backend is armed
- the requested wallet matches the armed live wallet
- readiness, caps, and kill-switch checks pass
- the selected backend reports the required signing capability

Protective exits may still proceed when entry autonomy is halted, as long as the active backend can still execute them.

## Non-Negotiable Safety Boundaries

- Paper mode remains the default and recommended mode.
- Live execution should remain localhost-only.
- Seed phrases must not be added.
- Remote signer exposure must not be added.
- Signer-daemon work must preserve localhost-only endpoint enforcement.
- Live actions must continue to produce durable audit and reconciliation records.
- Browser-wallet execution should continue to degrade gracefully to assisted/manual behavior when unattended approval is unavailable.
