# 13 API And Data Reference

This is a practical reference to the main API and data concepts used by the dashboard.

## Core Snapshot And Control

- `GET /api/snapshot`
  Main dashboard snapshot.
- `POST /api/start`
  Starts the bot runtime.
- `POST /api/stop`
  Stops the bot runtime.
- `PATCH /api/settings`
  Applies settings patch values.

## Analytics And Backtests

- `GET /api/analytics/performance`
- `GET /api/analytics/suggestions`
- `POST /api/analytics/suggestions/apply`
- `POST /api/backtest/replay`
- `POST /api/backtest/raw-replay`
- `POST /api/backtest/compare`
- `POST /api/backtest/ab-replay`
- `POST /api/backtest/v3`

Replay and raw-replay backtest responses include `determinism_fingerprint`, a stable short SHA-256 fingerprint derived from replay inputs, selected settings, headline metrics, PnL curve, and trade decisions. It excludes run id and timestamp so repeated runs over the same evidence can be compared directly. Raw replay fingerprints also avoid temporary replay-token ids.

`GET /api/analytics/performance` keeps paper trade analytics separate from live ledger analytics. It includes paper strategy/exit/score groups, `wallets` and `wallet_summary` derived from wallet-scoped live ledger positions, and `mode_comparison` rows for paper, replay, shadow, and live evidence.

## Data Quality And Safety

- `GET /api/data/integrity`
- `GET /api/price/diagnostics`
- `GET /api/pumpfun/intelligence`
- `GET /api/source-health`
- `GET /api/source-events`
- `GET /api/source-adapters`
- `GET /api/safety/status`
- `GET /api/readiness/status`
- `GET /api/watchdog/status`
- `POST /api/watchdog/recover`
- `GET /api/monitoring/ops`
- `GET /api/security/status`

## Solana Status

- `GET /api/solana/status`

Supports read-only RPC visibility and watched-wallet state.

## Live Status And Wallet Surfaces

- `GET /api/live/status`
- `GET /api/live/wallet/status`
- `POST /api/live/session/acknowledge`
- `POST /api/live/session/start`
- `POST /api/live/backend/arm`
- `POST /api/live/backend/disarm`

## Hot Wallet

- `GET /api/live/hot-wallet/status`
- `POST /api/live/hot-wallet/import`
- `POST /api/live/hot-wallet/unlock`
- `POST /api/live/hot-wallet/lock`
- `POST /api/live/hot-wallet/clear`

## Intents And Execution

- `GET /api/live/intents`
- `POST /api/live/intents`
- `POST /api/live/intents/generate`
- `POST /api/live/intents/{id}/cancel`
- `POST /api/live/intents/{id}/quote`
- `POST /api/live/intents/{id}/reconcile`
- `POST /api/live/quote`
- `POST /api/live/simulate`
- `POST /api/live/submit`
- `POST /api/live/confirm`

## Live Audit, Ledger, And Positions

- `GET /api/live/audit`
- `POST /api/live/audit/recover-unresolved`
- `POST /api/live/audit/{id}/recover`
- `GET /api/live/ledger`
- `GET /api/live/positions`

## Manual Live Requests

- `GET /api/live/requests`
- `POST /api/live/manual-request`
- `POST /api/live/requests/{id}/review`

## Review And Timeline

- `GET /api/trade-review/{token_id}`
- `GET /api/trade-review/queue`
- `GET /api/replay/timeline/{token_id}`

## Other Important Collections

- `/api/trades`
- `/api/trade-sessions`
- `/api/settings/versions`
- `/api/experiments`
- `/api/trade-labels`
- `/api/strategy-presets`

## Operational Monitoring

`GET /api/monitoring/ops` includes `observability`, a structured local-operations view derived from durable event records. It reports event counts by level and subsystem, high-severity events, readiness-related events, source metrics, signer metrics, recovery metrics, and a recommended operator action.

`GET /api/reports/operator-logs` returns a structured local operator-log artifact. It supports `timeframe`, `level`, `subsystem`, and `limit` query parameters, then reports summary counts, level counts, subsystem counts, session counts, recovery/source/live related event counts, recent matching events, action items, and a privacy note. `GET /api/reports/operator-logs/export` downloads the same artifact for incident review or handoff.

Operator events include `session_id` and `context` when a live session or backend is active. `observability.session_metrics` reports the active session id, number of session-tagged events, sessions seen, and top recent sessions by event count.

The app-shell notification center is backed by the durable `events` array from `GET /api/snapshot`. It keeps local read/unread state in the browser and surfaces level, subsystem, event time, operator action, and live-session tags without storing secrets.

## Data Concepts

### Snapshot

Aggregated dashboard state for the main app shell.

### Tuning suggestions

`GET /api/tuning/suggestions` returns local evidence-backed setting suggestions. Each suggestion includes the target setting, suggested value, confidence, expected benefit, supporting sample size, supporting closed-trade count, supporting PnL, overfit risk, `requires_operator_review`, and a review note. Applying a suggestion still requires operator confirmation and records a settings version; it does not place trades or change live safety gates by itself.

### Settings version

Immutable captured settings state used for historical context.

### Intent

Live execution candidate record.

### Audit

Live execution record spanning quote, simulation, submission, and reconciliation.

### Ledger

Wallet-scoped live accounting summary.

Live ledger positions include cost basis, realized/unrealized PnL, reconciliation status, token-balance verification time/age, mark price, mark source, mark confidence, mark age, and realized/unrealized PnL confidence labels. They also include `cost_basis_method`, `cost_basis_breakdown`, and `realized_pnl_events`; sells record the sale fraction, consumed basis, estimated proceeds, priority-fee impact, realized PnL delta, and provenance note. The ledger summary includes `pnl_confidence`, confidence counts, stale mark counts, stale balance counts, needs-review counts, and a note that live PnL remains approximate until balances, fills, and marks are reconciled. Open positions with stale or unknown balance verification block unattended autonomy until reconciliation refreshes the evidence.

### Position

Wallet/mint execution state with balance and PnL context.

### Trade review queue

`GET /api/trade-review/queue` summarizes closed paper trades into operator queues: unlabeled, losses, bad price evidence, long holds, missing decisions, and ignored-from-tuning. Each queue includes counts, sample trade/token ids, and a reason so review can start from the highest-value evidence gap.

### Creator reputation

`GET /api/pumpfun/intelligence` includes `creator_performance`, which joins token creators with closed paper trades and latest trade labels. It reports launches, closed trades, wins/losses, PnL, win rate, label counts, and a reputation state such as `positive`, `negative`, `mixed`, `exclude_or_review`, or `unproven`.

### Restore artifact

Local backup package used for preview and confirmed restore.

Restore preview includes current-versus-artifact table deltas, changed tables, `risk_level`, SQLite `integrity_check`, warnings, and recommended operator actions. Restore confirmation still creates a safety copy before replacing local SQLite state.

`GET /api/data/backup-restore/export` downloads a backup/restore evidence artifact. It includes restore history, an optional selected history entry, schema status, data summary, source/readiness state, unresolved live recovery debt, related operator events, and a privacy note.

`POST /api/data/restore/smoke-test` creates a fresh local backup artifact, immediately previews it through the restore validator, records an audit event, refreshes the snapshot, and returns a safe restore smoke-test report with integrity, schema, risk, warnings, and recommended actions. The response does not include the embedded `database_base64` payload.

### Source health

Source reliability payload with status, health score, normalized ratios, reconnects, subscription counts, and source-trust fields.

Trust states:

- `trusted`
- `degraded`
- `stale`
- `conflicting`
- `unknown`

The payload includes `trust_blockers`, `trust_warnings`, `live_entry_blocked`, `paper_collection_allowed`, `operator_action`, and `raw_event_inspection`.

### Source events

Raw and normalized source evidence. `GET /api/source-events` supports optional query filters:

- `limit`
- `status`
- `mint`
- `source`
- `event_kind`
- `parser_result`

Each source event includes derived `event_kind` and `parser_result` fields for inspection and filtering. The Data & Intelligence page includes a source-event inspector with status/source/kind/parser/mint filters and exports a local JSON evidence bundle containing the current source-health payload and matched source events.

`GET /api/source-events/parser-replay` replays recent stored source events through the parser and returns normalization counts, failure samples, event-kind/parser counts, and a dry backtest summary that is not saved to backtest history. `GET /api/source-events/parser-replay/export` downloads the same evidence. The Data & Intelligence page shows this report as parser replay evidence before the raw source-event table.

`GET /api/source-health` also includes `quality_history`, a recent bucketed source-soak view with event counts, normalized/raw/trade counts, malformed counts, unique mints, normalized ratio, and per-bucket trust state. `GET /api/source-health/export` downloads a source-health history artifact with current trust, bucket summary, source event counts, recent source rows, source-related operator events, and a privacy note. The Data & Intelligence page renders the history as a compact strip with an export action.

### Source adapters

`GET /api/source-adapters` reports the configured launch-data adapters. PumpPortal is the fast path. `solana_logs` is the direct-chain verification adapter; it is enabled only when both `SOLANA_WSS_ENDPOINT` and `SOLANA_LOGS_MENTIONS_ADDRESS` are set. It advertises `logsSubscribe`, `single_address_mentions_filter`, `raw_event_archive`, `direct_chain_verification`, and `paper_create_normalization` capabilities. While the bot is running, the companion verifier archives Solana log notifications as `solana_logs` source events. By default these remain evidence-only; when `direct_solana_paper_enabled` is true, rich create evidence at or above `direct_solana_min_confidence` can enter paper monitoring only.

`GET /api/source-events/solana-logs-verification` returns stored direct-chain verification evidence. `GET /api/source-events/solana-logs-verification/export` downloads the same artifact. The report parses archived `solana_logs` source events using Solana `logsSubscribe` notification shape, extracts signature, slot, error, log, create-hint, candidate mint evidence, and rich create evidence from direct log text or decoded `Program data` when available. Rich create evidence includes mint, name, symbol, metadata URI, creator, bonding curve, field coverage, confidence, missing fields, and decoded Program-data snippets. The report compares direct events with PumpPortal events by signature or mint. This is source-soak evidence only; it does not permit live execution by itself.

`GET /api/source-events/source-soak` returns the hybrid source-soak acceptance gate plus durable snapshot history. `POST /api/source-events/source-soak/snapshot` saves the current gate result as an auditable local snapshot, and `GET /api/source-events/source-soak/export` downloads the current artifact with history. The gate checks raw source event volume, primary source trust, direct-verifier configuration, direct log sample count, direct/PumpPortal match count and match rate, decoded create coverage, and direct conflicts. Readiness and strategy promotion include this evidence as `source_soak`; it becomes a hard blocker once the direct verifier is configured or direct events are present.

### Readiness, strategy promotion, and execution readiness

`GET /api/readiness/status` includes core readiness gates plus `strategy_promotion` and `execution_readiness`.

The promotion payload summarizes whether the current paper strategy is eligible for `paper_to_shadow` promotion. It includes:

- `can_promote`
- `status`
- `mode`
- promotion `gates`
- `blockers`
- `summary`
- `requires_operator_review`
- `out_of_sample`

Promotion gates cover closed paper trades, source-event sample size, replay confidence, source trust, hybrid source-soak when applicable, price acceptance, paper profitability, drawdown, out-of-sample validation replay, strategy drift, and the paper-first safety boundary. `out_of_sample` contains walk-forward train/validation replay evidence for the active strategy profile, including validation PnL, validation profit factor, validation token count, and train/validate collapse detection.

The execution-readiness payload summarizes whether the current live quote/audit path is ready for dry-run shadow comparison. It includes:

- `can_shadow`
- `can_live_submit`
- quote health metrics such as `quote_attempts`, `ready_quotes`, `blocked_quotes`, `stale_quotes`, `stale_quote_rate`, and `blocked_quote_rate`
- shadow evidence metrics such as `shadow_samples`, `shadow_evaluated`, `recent_shadow_evaluated`, `recent_shadow_window_hours`, `shadow_win_rate_pct`, `shadow_estimated_pnl_sol`, and recent-shadow PnL/win-rate fields
- landing-window metrics such as `shadow_landing_windows`, `shadow_landing_evaluated`, `shadow_landing_win_rate_pct`, `shadow_landing_best_pnl_sol`, and `shadow_landing_worst_pnl_sol`
- live calibration metrics such as `live_landing_samples`, quote-to-submit p50/p90/p99, and submit-to-confirm p50/p90/p99
- policy caps, cap `operator_intent` settings-version evidence, suggested `slippage_pct` / `priority_fee_sol`, and a bounded policy `recommendation` with cap room, inputs, reasons, and operator action
- `latency_summary`, an operator-facing verdict with signal-to-quote and quote-to-submit p50/p90 timing, sample counts, and latency issues
- `quote_issues`, a queryable taxonomy of stale, blocked, and failed quote/audit issues grouped by category with recent affected audits and reasons
- `failure_stages`, a queryable per-stage taxonomy for quote, simulation, submit, confirmation, and reconciliation failures
- `landing_calibration`, including suggested delay windows and whether the source is fixed defaults or live audits
- execution `gates`
- recent `shadow_comparisons`
- blocking reasons and an operator action

Execution-readiness gates cover the dry-run quote path, quote sample size, stale quote pressure, failed/blocked quote pressure, live policy caps, source trust, PumpPortal shadow price-observation availability, strategy shadow promotion, signer boundary, and unresolved audit recovery. Unsigned stale quotes count as quote pressure but not live recovery debt; submitted, failed, needs-review, or signed unreconciled audits remain recovery debt. Tiny-pilot readiness uses the recent-shadow metrics and requires at least five evaluated shadow comparisons from the last 24 hours with non-negative recent shadow PnL.

`GET /api/live/status` also includes `mode_visibility`, a four-tile operator summary for `paper`, `shadow`, `manual_live`, and `autonomous_live`. Each tile has a state, tone, summary, and top blockers so the live workspace can keep simulated, shadow, assisted live, and unattended live modes visually distinct.

`GET /api/live/status` includes `execution_backend`, which identifies the selected submit path, whether it is implemented, whether it stays local-only, whether manual approval is required, whether unattended submit is currently available, current executor blockers, and the recommended operator action. Implemented paths are browser-wallet manual signature submission, encrypted local-hot-wallet submission, and guarded localhost signer-daemon submission when the daemon health endpoint advertises signing capability. The signer-daemon status and execute paths both reject non-localhost endpoints before any network signer request is sent.

`GET /api/live/status` includes `source_degraded_mode`, which reports `normal`, `paper_only`, or `exit_only` operation from current source trust. It records whether live entries are allowed, paper collection is allowed, protective exits are available, source entry blockers, exit blockers, and the recommended operator action. Live buy/new-entry blockers also include `low replay confidence halt active` when `halt_on_low_replay_confidence` is enabled and replay confidence is below `min_replay_confidence`; protective sells remain preparable if other sell prerequisites pass.

`GET /api/live/status` includes `manual_live_verification`, which reports whether the selected wallet has a clean confirmed and reconciled manual live audit from the last 24 hours for the selected signer path. Audits with recorded errors or pending review do not qualify as proof. `full_sniper_gate`, the final unattended buy-and-sell readiness state, requires that selected signer-path manual-live proof plus entry autonomy, exit autonomy, active backend match, normal source mode, and fresh pre-run backup before reporting ready. Expert override evidence remains audit-only and does not bypass this gate.

`GET /api/live/status` includes `pre_run_backup`, which blocks live buy entries when the latest backup artifact is missing, older than 24 hours, or older than the latest restore. `GET /api/reports/pilot-readiness` includes the same evidence and requires a `fresh` pre-run backup gate before tiny real-money pilot mode.

Live execution audits include `preflight_checks`, an ordered list of quote-readiness checks with `id`, `label`, `status`, `value`, `target`, and `reason` fields. The checks cover environment state, mint, wallet, signer, amount, slippage, priority fee, pool, caps, and aggregate blockers so blocked and ready quotes can be reviewed with the same evidence contract. Submit/autonomy paths reject audits that contain failed preflight rows.

Ready dry-run buy quotes add `shadow_comparison` to their live audit. The comparison records the would-submit timestamp, entry price, later accepted price, simulated exit price, exit reason, hold duration, move percentage, estimated PnL, and outcome. The evaluator applies configured exit rules such as minimum hold, take profit, stop loss, trailing stop, break-even, stalled trade, max hold, and max ticks.

Each comparison also includes `landing_windows` for immediate, 250ms, 500ms, 1000ms, and 2000ms delayed fills. These windows estimate whether a delayed submit would have filled, missed, or gone stale before quote expiry. They are evidence only; they do not submit, sign, or confirm a transaction.

Submitted and confirmed live audits include `execution_timing` when timing is available. New submit/confirm flows record quote-to-submit, submit-to-confirm, and quote-to-confirm milliseconds. Execution readiness uses those samples to add calibrated delay windows alongside the fixed defaults, and reports p50/p90/p99 globally plus `by_signer_mode`, `by_pool`, and `by_quote_source` timing groups.

Execution readiness also includes `pipeline_latency`, a derived view of source-to-token, token-to-decision, decision-to-intent, intent-to-quote, quote-to-submit, submit-to-confirm, confirm-to-reconcile, signal-to-quote, and signal-to-confirm timing when the stored evidence can be linked. It reports p50/p90/p99/max per stage plus recent sample evidence and missing-link counts.

### Operator reports and incident exports

`GET /api/reports/setup-readiness` returns the first-run setup checklist for paper monitoring. `GET /api/reports/setup-readiness/export` downloads the same artifact. It separates hard blockers from warnings across mode, source selection, source detection, local schema, paper settings, source health, local auth, backup status, and live-disabled safety. The Data & Intelligence page turns this evidence into a staged first-run setup wizard with environment, source, paper, security, backup, and live-guard steps.

`GET /api/reports/session` returns an operator session report. `GET /api/reports/session/export` downloads the same report as JSON. The report includes paper PnL, paper/replay/shadow/live `mode_comparison`, live ledger summary, open risk, source quality/trust, readiness, alert status, backup/restore state, unresolved live audits, recent events, and action items. `open_risk` summarizes active intents, open positions, wallet exposure versus cap, live PnL versus daily-loss cap, stale balance evidence, needs-review ledger positions, unresolved audits, blockers, warnings, and recommended actions. `source_quality` summarizes recent source-quality buckets, normalized ratio, malformed counts, degraded buckets, and operator action.

`GET /api/reports/evidence-mode-separation` returns a dedicated evidence-boundary report. `GET /api/reports/evidence-mode-separation/export` downloads the same artifact. It separates paper trades, replay/backtest runs, dry-run shadow quote comparisons, manual live audits, and autonomous live audits by source, sample count, PnL, latest evidence time, and operator action. The report adds contamination warnings when rows appear to cross boundaries, such as submitted shadow evidence or live audits without wallet public keys.

`GET /api/reports/pilot-readiness` returns the tiny real-money pilot gate report. `GET /api/reports/pilot-readiness/export` downloads the same artifact. It combines source trust, hybrid source-soak evidence, durable source-soak snapshot history, strategy promotion, shadow execution evidence, live caps, manual-live wallet proof, signer/autonomy status, recovery debt, ledger confidence, kill switch, backup status, and blockers. The `source_trust` gate requires the PumpPortal source to be connected, recent, trusted, and backed by archived PumpPortal source events in the local evidence store. The report also includes `runbook_checklist`, a concise launch/run/stop/recover/review checklist derived from the same gate evidence. The `source_soak` gate blocks a real-money pilot when direct verification is configured or direct events exist but matched PumpPortal/direct evidence is incomplete. The `source_soak_history` gate also requires at least one saved ready source-soak snapshot from the last 24 hours when direct source-soak is required.

`GET /api/reports/post-run-review` includes `run_controls`, which summarizes current kill-switch state, recent kill-switch events, current cap settings, and per-audit cap snapshots. The `cap_and_stop_evidence` checklist row fails when recent live audits are missing cap snapshots, because post-run review must explain cap decisions and stop-control state before the next pilot.

`GET /api/reports/post-run-review` returns the post-run live/pilot review report. `GET /api/reports/post-run-review/export` downloads the same artifact. It classifies recent non-shadow-only live audits, unresolved recovery, needs-review states, ledger confidence, incident-export candidates, and pending incident exports so a real-money pilot can be reviewed before the next run. Shadow-only evidence audits stay in shadow/evidence readiness and do not satisfy or pollute post-run live audit inventory. If the selected timeframe has no live audit evidence, the report status is `missing_evidence` and `ready` is false. `POST /api/live/audit/{audit_id}/incident-export/review` records that an incident bundle was exported and reviewed; this clears the post-run incident-export checklist for blocked/failed audit evidence that does not still carry unresolved recovery debt.

`GET /api/reports/release-readiness` returns the local release gate report. `GET /api/reports/release-readiness/export` downloads the same artifact. It checks changelog and release-checklist presence, bootstrap/doctor/verify/frontend-audit script presence, dependency-audit policy, schema status, frontend/API version alignment, backup state, source trust, live-disabled state, unresolved live audits, local auth, and the required manual verifier step before tagging, live testing, or handoff. `POST /api/reports/release-readiness/verification` records the local verifier attestation after `scripts/verify.ps1` passes, git diff is reviewed, and release docs are reviewed; the `manual_verification` gate passes only when that attestation is for the current app version and was recorded in the last 24 hours. The dependency-audit evidence records the acknowledged moderate `@solana/web3.js -> jayson -> uuid` advisory chain while keeping high, critical, and unacknowledged moderate advisories as release blockers.

`GET /api/reports/outcome-explanations` returns a unified explanation report for recent buys, skips, sells, blocks, audited overrides, and recovery outcomes. `GET /api/reports/outcome-explanations/export` downloads the same artifact. Each outcome includes type, status, subject, mint/token references, reason, recommended action, and evidence ids such as decision, audit, request, or event ids.

The Data & Intelligence page shows setup readiness, release readiness, evidence mode separation, the pilot gate, post-run review, and outcome explanations as in-app panels with pass/block counts, warning counts where relevant, failed gate actions, direct links to the relevant evidence panels or incident exports, and direct export links.

`GET /api/trade-review/queue` returns queue counts plus `next_token_id` for the next actionable closed trade. `GET /api/trade-review/{token_id}` returns `review_workflow` with previous/next trade ids, selected label, suggested labels, and a source/decision/price/PnL checklist so the Review workspace can move through labels quickly without losing evidence context.

`GET /api/live/audit/{audit_id}/incident-export` downloads a single live-audit incident bundle. It includes the audit, intent, quote, simulation, stored signature/confirmation status, balance snapshot, matching ledger position, token/source evidence, operator events, and recovery state. Recovery/export endpoints are evidence-only and do not submit or replay transactions.
