# CryptoARC v2 Autonomous Launch Roadmap

This roadmap replaces the broad finished-product roadmap with a two-week, crucial-only path to a usable local full autonomous sniper bot.

## Finish Line

CryptoARC is launch-ready when Ari can run it locally, intentionally enable live mode, arm the local backend, let the bot execute autonomous buy and sell flow under hard caps, stop it instantly, and recover or review every live action without code edits.

## Product Principle

Ship usable first. Perfect later.

Do not add new launch gates unless they prevent catastrophic loss, unsafe signing, bad source input, or unrecoverable accounting.

## Two-Week Shape

- Week 1: make the autonomous loop boring and operable.
- Week 2: run proof sessions, fix blockers, document the exact launch procedure, and tag the first usable local launch.

## Roadmap Files

- [Launch Critical Path](01-launch-critical-path.md)
- [Must-Have Safety Gates](02-must-have-safety-gates.md)
- [Post-Launch Backlog](03-post-launch-backlog.md)

## Locked Launch Scope

In scope before launch:

- local setup, doctor, verification, and release attestation
- PumpPortal source health and raw event capture
- recent paper, replay, and shadow evidence using existing thresholds
- recent manual live proof for the selected wallet
- autonomous buy/sell loop under tiny caps
- explicit live enablement, local-only signer/backend arming, and hard risk caps
- kill switch
- ledger reconciliation, backup, unresolved-audit checks, and post-run review
- exact operator run, stop, and recover checklist

Out of scope before launch:

- deeper strategy science
- richer Solana verifier authority
- multi-provider quorum
- hosted deployment
- paid infrastructure
- big UI redesign
- multi-user auth
- extra analytics

