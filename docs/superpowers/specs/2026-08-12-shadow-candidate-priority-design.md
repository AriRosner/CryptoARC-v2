# Shadow Candidate Priority Design

## Goal

Increase the rate of genuine, version-matched economic shadow samples while keeping the campaign in paper mode and keeping PumpPortal paid trade subscriptions capped at one.

The change must improve how the existing paid slot is allocated. It must not lower the 100-sample or seven-calendar-day gates, change strategy thresholds, manufacture observations, access a signer or wallet, or enable simulation, submission, acknowledgement, arming, or live execution.

## Confirmed problem

The campaign has one paid token-trade subscription. The source currently assigns that slot to new launches in arrival order and, when the cap is one, holds each assignment for at least ten minutes. Shadow candidates are selected later by the strategy pipeline, so the paid slot usually follows a different mint by the time a candidate is quoted.

On the current strategy version, six of eight shadow candidates had no accepted entry observation. Five of those candidates also received no accepted follow-up observation. The economic validator correctly rejected them. This is an allocation problem, not an evidence-validation problem.

## Selected approach

Use a candidate-priority subscription coordinator between strategy selection and the PumpPortal trade stream.

The coordinator has two priority classes:

1. A strategy-qualified paper candidate awaiting an accepted entry observation or carrying a pending shadow audit.
2. An ordinary newly launched token.

With a one-slot cap, a qualified candidate owns the slot until its evidence lifecycle is complete or its bounded tracking deadline expires. Ordinary launch rotation resumes only when there is no eligible candidate. Increasing the cap remains an operator-controlled setting and is outside this change.

This is preferable to increasing paid scope because it does not increase the configured number of subscriptions. It is preferable to rotating faster through every launch because that would spend messages on more unrelated tokens without ensuring entry and exit coverage for qualified candidates.

## Components

### Candidate tracking registry

Persist a small, restart-safe record when the existing strategy pipeline selects a paper-promoted buy candidate. The record contains the mint, strategy identity and version, selection time, state, deadline, and optional audit ID. It contains no credential, wallet secret, transaction, or trading instruction.

States are:

- `awaiting_entry`: selected by the unchanged strategy rules but no accepted, attributable entry observation is available.
- `tracking_shadow`: a versioned shadow-only audit exists and needs later accepted observations.
- `complete`: an economic comparison was persisted.
- `expired`: the bounded evidence window ended without sufficient observations.

Only `awaiting_entry` and `tracking_shadow` records are eligible to control the paid slot. Terminal records do not resume automatically.

### Subscription coordinator

The source runtime receives a coordinator through a narrow interface rather than reaching into strategy state. It chooses one desired mint deterministically:

- continue the oldest `tracking_shadow` item first;
- otherwise choose the oldest `awaiting_entry` item;
- otherwise use the existing ordinary-launch queue.

A new qualifying candidate may replace an ordinary launch immediately. Candidate-to-candidate replacement is deterministic and happens only when the current candidate completes or expires. This prevents high-frequency churn and keeps the active subscription count at or below the configured cap.

On reconnect, the source replays only the coordinator's current desired subscription. The source status continues to report active and dropped subscription counts and additionally reports whether the slot is serving candidate evidence or ordinary discovery.

### Entry-first shadow creation

Candidate selection remains unchanged, but automatic shadow quote creation becomes evidence-aware:

1. If a matching, accepted, non-fixture, conflict-clear observation exists for the candidate and current strategy version, create the shadow-only quote using that attributable observation as entry evidence.
2. Otherwise persist `awaiting_entry`, prioritize its mint, and defer the quote.
3. When an accepted observation for that record arrives, atomically bind it as the entry, create the shadow-only audit, and transition the record to `tracking_shadow`.

The deferred path must be idempotent. Repeated campaign monitor calls or reconnects cannot create duplicate intents, quotes, audits, or entry bindings.

### Exit tracking and release

While `tracking_shadow` is active, accepted observations continue to bind through the existing pending-shadow mechanism. Completion uses the strategy-version snapshot and existing take-profit, stop-loss, maximum-hold, and maximum-tick rules.

The coordinator releases the slot when the existing economic comparison persistence succeeds. If evidence never arrives, it releases the slot at a deadline derived from the captured strategy's maximum hold window plus a small transport grace period. Expiration records the reason and preserves the incomplete audit; it never treats missing data as a flat price or a completed sample.

## Data flow

1. PumpPortal's public launch stream continues collecting launch events.
2. Existing normalization, scoring, paper decisions, and promotion thresholds identify a candidate.
3. The candidate registry either finds valid entry evidence or requests the one paid slot.
4. A genuine paid trade event passes through the existing price acceptance pipeline.
5. The first valid observation creates and binds the shadow entry; later valid observations bind as path evidence.
6. Existing exit rules evaluate the shadow and the economic validator persists it only when every current gate passes.
7. Completion or bounded expiration releases the slot to the next candidate or ordinary launch.

## Failure handling

- Paid access unavailable: preserve the candidate as awaiting evidence, mark source access blocked as today, and create no sample.
- Process restart: rebuild the desired subscription from nonterminal persisted records and avoid duplicate quotes.
- Stale strategy version: expire the record as version-mismatched; do not migrate it to the new version.
- Malformed, fixture, conflicted, nonpositive, late, or wrong-mint observation: reject it through existing acceptance and binding rules.
- Source reconnect or queue pressure: replay the current candidate rather than silently falling back to the newest launch.
- Deadline reached without entry or exit: record an explicit incomplete/expired result and move to the next candidate.

## Observability and budget proof

Expose enough status to answer, without credentials:

- selected mint prefix and priority reason;
- tracking state and age;
- candidate queue depth;
- active subscription count and configured cap;
- accepted observations and completed economic samples attributable to candidate-priority tracking;
- expirations grouped by missing entry versus missing exit.

The campaign check must assert that the active paid-subscription count never exceeds `max_trade_subscriptions`. A before/after benchmark on copied evidence data will compare candidate entry coverage, follow-up coverage, and projected samples per day. Message rate is observed as a guardrail, not declared improved merely because coverage rises.

## Testing

Tests are written before production changes and cover:

- a qualifying candidate preempts an ordinary launch without opening a second subscription;
- a second candidate cannot churn the active candidate slot;
- no shadow quote is created before genuine accepted entry evidence exists;
- the first valid observation creates exactly one versioned shadow audit and entry binding;
- later observations bind to the same pending audit and completion releases the slot;
- restart and reconnect restore the same desired candidate without duplication;
- expiry releases the slot without manufacturing an observation or economic sample;
- wrong-mint, wrong-version, fixture, conflicted, and blocked-access observations remain ineligible;
- paper mode and all live execution prohibitions remain enforced.

Focused source, storage, shadow-evaluation, and API tests run first. Because this touches launch-critical evidence collection, the full repository verification suite is required before a pull request can merge.

## Rollout

Implementation and benchmarking occur in an isolated worktree and against copied campaign data. After tests, full verification, pull-request review, and green GitHub security/CI checks, the change may merge to `main`.

Advancing the running campaign is a separate controlled step: stop only the hidden paper campaign process, back up its database and status artifacts, move its detached exact-main worktree to the verified merge commit, and restart it hidden with the existing `.env` and database. Confirm paper mode, `LIVE_TRADING_ENABLED=false`, live execution unavailable, model grading disabled, source trust healthy, subscription cap one, and candidate-priority status visible. No prior sample is reclassified or backfilled.

## Success criteria

- The paid subscription cap remains one and observed cost does not exceed the existing budget scope.
- Strategy selection and economic qualification gates are unchanged.
- Every new economic sample has genuine, attributable, version-matched entry and exit observations.
- Candidate entry and follow-up coverage materially improve in the copied benchmark and then in live paper monitoring.
- The system remains fail-closed whenever evidence, access, version identity, or source trust is missing.
