# Must-Have Safety Gates

## Principle

Keep only the gates that prevent catastrophic loss, unsafe signing, bad source input, or unrecoverable state. Everything else belongs in the post-launch backlog.

## Launch-Blocking Gates

### 1. Explicit Live Enablement

Live trading must require intentional enablement through configuration and operator acknowledgement. Paper mode remains the default posture.

Block launch if live execution can happen accidentally.

### 2. Local-Only Signing Boundary

The launch path must keep signing local to the workstation.

Required:

- no seed phrases stored in CryptoARC
- no remote signer exposure
- backend armed intentionally
- selected wallet matches the expected live wallet
- live actions auditable by wallet and run

### 3. Hard Risk Caps

Autonomous mode must be constrained by hard caps before real money is allowed.

Required caps:

- max trade size
- daily loss
- wallet exposure
- max open positions
- slippage
- priority fee

Block launch if caps can be bypassed, ignored, or changed without visible operator intent.

### 4. Kill Switch

The operator must have a clear kill switch that stops new live execution immediately.

Block launch if the kill switch is hidden, unreliable, or only cosmetic.

### 5. Source Sanity

PumpPortal is acceptable as the launch data source, but the app must reject obviously unsafe source conditions.

Required:

- source is connected and not stale
- source health is recent
- raw events are archived for review
- conflicting or missing source state blocks autonomous operation

Direct Solana `logsSubscribe` verification is valuable, but it is not a launch blocker unless the configured verifier reports a hard conflict.

### 6. Basic Evidence

Strategy promotion must pass the existing evidence thresholds. Full scientific certainty is not required for the first usable product.

Required:

- recent paper or replay evidence
- at least 5 recent shadow comparisons in the last 24 hours
- recent shadow PnL is non-negative
- selected strategy/run can be traced in review screens

### 7. Manual-Live Wallet Proof

Before unattended real-money autonomy, the selected wallet must have a recent tiny manual live proof.

Required:

- confirmed live transaction in the last 24 hours
- reconciled ledger entry
- wallet identity matches selected execution wallet
- no unresolved audit tied to the proof

### 8. Recovery And Accounting Confidence

The system must be able to recover and explain live state.

Required:

- fresh pre-run backup
- no unresolved audits
- ledger confidence is not stale or `needs_review`
- open positions are visible
- post-run review can export incidents and evidence

### 9. Post-Run Review

After every pilot run, the operator must be able to see what happened.

Required:

- live audit evidence
- trades and positions
- cap decisions
- kill-switch state
- incidents and export status
- ledger/PnL confidence

## Deferred Gates

These improve the product but should not block the first usable local autonomous launch:

- perfect direct Solana authority
- multi-provider source quorum
- advanced creator reputation modeling
- deep walk-forward optimization
- sophisticated latency and priority-fee automation
- hosted deployment
- multi-user permissions
- premium UI polish
- exhaustive analytics

