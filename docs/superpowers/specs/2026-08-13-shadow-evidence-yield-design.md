# Shadow Evidence Yield and Funnel Monitoring Design

## Objective

Increase the number of genuine, version-matched economic shadow samples produced by the existing single paid PumpPortal subscription, without increasing wallet spend, subscription count, or live-execution authority. Detect future cases where processes remain healthy but the evidence pipeline is not producing useful results.

## Constraints

- Keep `LIVE_TRADING_ENABLED=false`, paper mode, and live execution unavailable.
- Do not add wallet, signer, simulation, submission, acknowledgement, arming, or live-session access.
- Keep `max_trade_subscriptions=1`; do not increase paid scope.
- Preserve the current strategy version and the strict economic-sample definition.
- Do not manufacture, backfill, or relabel evidence.
- Preserve restart-safe candidate and capture state.

## Candidate Admission

Shadow collection will admit at most one active candidate when the configured paid-subscription cap is one. The limit applies to the combined `awaiting_entry` and `tracking_shadow` states. While that slot is occupied, intent generation may continue to rank paper decisions for its normal response, but it must not persist additional `paper_promoted` shadow candidates.

When the active candidate completes or expires, the next generation cycle selects the highest-ranked eligible paper decision. This keeps the subscription assigned to a candidate that can actually use it and prevents queued candidates from consuming their deadlines before receiving service.

For configurations with more than one paid subscription, active candidate admission is bounded by the configured subscription cap. This preserves general behavior without making the one-slot campaign a special hard-coded mode.

## Observation Windows

An `awaiting_entry` candidate receives a five-minute deadline beginning at selection. This replaces the current use of the two-minute token-age setting as the candidate entry deadline. The candidate owns the paid slot for that full period unless it captures an entry sooner.

After a genuine, attributable, version-matched entry observation is bound, the candidate transitions to `tracking_shadow`. Its deadline remains the captured strategy's `max_hold_time_seconds` plus the existing 30-second evidence allowance. With the current settings, that is 10 minutes plus 30 seconds.

Entry and exit evidence rules remain unchanged: same mint, current strategy identity, positive price, ready access, clear conflict state, and non-fixture evidence.

## Funnel Diagnostics

The backend will expose a read-only candidate-funnel summary derived from durable candidate, capture, binding, observation, and comparison records. It will report:

- attempts, active candidates, completed candidates, missing-entry expirations, and missing-exit expirations;
- entry and completion conversion rates;
- candidates that expired without evidence after selection;
- active-candidate count, configured subscription cap, and excess/unserved queue depth;
- latest candidate selection, entry activation, and economic-completion timestamps;
- rolling windows for the latest 1, 4, and 12 hours;
- a bounded list of diagnostic conditions, not trading recommendations.

The summary must be a pure projection and must not refresh, normalize, quote, or mutate audits or candidates.

## Monitoring Policy

The recurring campaign automation will compare the current funnel with the prior run and judge evidence usefulness independently of uptime. It will investigate and notify on any of these conditions:

- active or queued candidates exceed the configured paid-subscription cap;
- a candidate expires without receiving meaningful paid-slot service;
- at least 20 terminal attempts in a rolling window produce a completion rate below 2%;
- entry conversion or completion conversion materially degrades relative to the previous comparable window;
- candidates advance but evaluated shadows or economic samples do not advance when the funnel shows qualifying entry-and-exit opportunities;
- any monotonic counter decreases or dashboard/backend values diverge beyond collection-timing tolerance;
- pending captures outlive their candidate deadline;
- repeated reconnects, queue backlog, timeouts, stale evidence, or internal failures make evidence incomplete even while health endpoints remain green.

The existing 12-hour stall checks remain as escalation rules, not the first line of detection. Missing entry evidence alone remains valid market evidence, but a high missing-entry rate becomes actionable when it shows candidates were unserved, admission exceeded capacity, or conversion is statistically poor.

## Automation State

The monitor will record its previous counters, latest advancement timestamps, funnel-window values, and material diagnostic conditions in the campaign status artifact. This makes comparisons restart-safe and auditable. A material funnel warning is cleared only after a later comparable window no longer meets the condition.

## Dashboard

The temporary dashboard will consume the authoritative funnel summary if it is available. Existing evaluated-shadow and economic-sample cards remain unchanged; diagnostics may appear in campaign warnings rather than adding a large new feature. This remains temporary and uncommitted.

## Tests

Backend tests will prove:

- one configured subscription persists at most one active candidate;
- a second candidate is admitted after the first completes or expires;
- the entry deadline is five minutes and the tracking deadline remains strategy-versioned;
- restart preserves the active owner and does not create another candidate;
- configurations above one retain cap-bounded behavior;
- funnel summaries are pure, windowed, and calculate rates and warnings correctly;
- live authority and execution boundaries remain unchanged.

Monitor tests will prove:

- poor conversion is detected before 12 hours once the minimum attempt count is reached;
- normal low-volume collection does not create a false alarm;
- unserved queue and deadline-overrun conditions are detected;
- monotonic progress and advancement timestamps survive subsequent runs;
- a recovered comparable window clears the material warning.

## Rollout and Verification

The change will be delivered through a focused pull request. Focused candidate, source lifecycle, economic shadow, monitor, and safety tests run first; repository verification and GitHub security/CI gates run before merge. Deployment uses the existing controlled exact-main paper-campaign restart. After deployment, verification will confirm one active candidate at most, a five-minute entry deadline, fresh trusted source data, unchanged paid-subscription count, and all live controls disabled.
