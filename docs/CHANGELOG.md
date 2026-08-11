# CryptoARC v2 Changelog

All notable local release changes should be recorded here before tagging, live testing, or handing the project to another agent.

## Unreleased

- Added roadmap hub docs for finishing CryptoARC v2 as a polished local workstation bot first, then an evidence-backed real-money sniper bot.
- Added local bootstrap, verification, Markdown link checking, and CI release-discipline paths.
- Added frontend dependency audit policy reporting for the acknowledged Solana advisory chain without applying npm's breaking downgrade.
- Added release-verifier attestation evidence and a Data workspace control so `/api/reports/release-readiness` can pass the manual verification gate after a recent local `scripts/verify.ps1` run, git diff review, and docs review are recorded.
- Added setup diagnostics for Python, virtualenv, backend imports, Node/package manager, frontend dependencies, Solana frontend package, and `.env` readiness.
- Added source reliability evidence including raw-event filters, parser replay, source-adapter status, and source-quality session summaries.
- Added exportable source-health history evidence with trust summary, quality buckets, recent source rows, and source-related operator events.
- Added stored Solana `logsSubscribe` verification evidence that compares direct-chain log events with PumpPortal events by signature or mint.
- Added optional live Solana `logsSubscribe` raw archival behind `SOLANA_WSS_ENDPOINT` and `SOLANA_LOGS_MENTIONS_ADDRESS`.
- Added richer direct Solana create-event evidence extraction from log text and decoded `Program data`.
- Added bounded Borsh decoding for the official Pump `CreateEvent` layout and limited source-soak sample/match rates to genuine Pump create notifications.
- Added opt-in paper-only direct Solana create normalization behind confidence gates.
- Added hybrid source-soak acceptance gates for matched PumpPortal/direct evidence before source promotion.
- Added durable source-soak snapshots with local history, export, data-summary counts, and dashboard capture controls.
- Added a tiny-pilot `source_soak_history` gate requiring a saved ready source-soak snapshot from the last 24 hours when direct verification is required.
- Added hybrid source-soak evidence to the tiny real-money pilot readiness gate.
- Added strategy evidence reports for promotion gates, replay confidence, creator reputation, and outcome explanations.
- Added deterministic fingerprints to saved replay/raw-replay backtest runs and surfaced them in Replay Lab history.
- Added evidence mode separation reporting and dashboard visibility for paper, replay, shadow, manual live, and autonomous live evidence boundaries.
- Added evidence-backed tuning suggestion fields for expected benefit, sample size, PnL, overfit risk, and operator review.
- Added faster trade-review workflow with next-trade navigation, suggested labels, and checklist-backed evidence review.
- Added execution readiness evidence for quote health, bounded slippage/priority-fee recommendations, shadow/live comparison, latency summaries, and landing-delay tracking.
- Added recent shadow-evidence metrics and tightened tiny-pilot readiness so stale shadow comparisons cannot satisfy the pilot sample or PnL gates.
- Added structured live-quote preflight evidence for environment, wallet, signer, cap, slippage, priority-fee, pool, and blocker checks.
- Added submit/autonomy enforcement so failed live-quote preflight evidence blocks signing or backend execution.
- Added stage-level execution failure taxonomy for quote, simulation, submit, confirmation, and reconciliation review.
- Added live autonomy safety reports for staged pilot gates, local signer boundaries, caps, kill switch state, and audited override evidence.
- Added live execution-backend status for browser-wallet manual submit, encrypted local-hot-wallet submit, and localhost signer-daemon capability blockers.
- Added a full-sniper manual-live verification gate requiring a recent browser-wallet live success before unattended buy-and-sell readiness can report ready.
- Added explicit source-degraded operating mode reporting so live status can show normal, paper-only, or exit-only behavior.
- Added live-entry enforcement for the low replay-confidence halt while preserving protective sell preparation.
- Added explicit full-sniper gate reporting for unattended buy-and-sell readiness.
- Added operator UI panels for setup readiness, session summaries, pilot readiness, post-run review, alerts, parser replay, restore smoke tests, and outcome explanations.
- Added ledger/recovery/observability artifacts including PnL confidence, unresolved audit recovery, incident export bundles, backup/restore evidence, and restore smoke tests.
- Tightened post-run review so an empty timeframe reports missing evidence instead of passing as clear.
- Added incident-export review attestations and Data workspace controls so post-run review can distinguish pending incident bundles from blocked/failed audits that were exported and reviewed.
- Added structured operator-log reports with local filters, summary counts, action items, dashboard visibility, and JSON export.

## 0.1.0-roadmap - 2026-06-29

- Established the finished-product roadmap and acceptance gates for the local-first CryptoARC v2 build.
- Preserved safety defaults: paper mode first, no seed phrases in exported artifacts, no remote signer exposure, and localhost-first live execution.
