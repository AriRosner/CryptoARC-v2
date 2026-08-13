# Shadow Evidence Yield Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align shadow-candidate admission with paid-stream capacity, give the active candidate a five-minute entry window, and make poor evidence conversion observable before a twelve-hour stall.

**Architecture:** `BotState.generate_live_intents` will calculate available candidate slots from durable active candidates and the configured trade-subscription cap, then persist only the best candidates that fit. Candidate entry deadlines will use a dedicated five-minute constant while tracking deadlines continue to use captured strategy settings. A pure storage-backed funnel projection will feed health/status responses and the local campaign monitor; the Codex heartbeat prompt will use those durable diagnostics for general evidence-usefulness checks.

**Tech Stack:** Python 3.11, FastAPI, SQLite, `unittest`, PowerShell scheduled task, Codex heartbeat automation.

## Global Constraints

- Keep `LIVE_TRADING_ENABLED=false`, paper mode, and live execution unavailable.
- Keep `max_trade_subscriptions=1` in the campaign; do not increase paid scope.
- Do not add wallet, signer, simulation, submission, acknowledgement, arming, or live-session access.
- Preserve strict genuine, non-fixture, version-matched economic evidence.
- Use test-first red-green cycles for every production behavior change.

---

### Task 1: Capacity-aligned candidate admission and deadlines

**Files:**
- Modify: `backend/app/core/state.py`
- Test: `tests/test_shadow_candidate_priority.py`

**Interfaces:**
- Consumes: `Storage.load_shadow_tracking_candidates(active_only=True)`, `BotSettings.max_trade_subscriptions`.
- Produces: `BotState.SHADOW_ENTRY_WINDOW_SECONDS = 300` and cap-bounded `paper_promoted` candidate persistence.

- [ ] **Step 1: Write failing tests**

Add tests proving one-slot generation persists only one active candidate, the selected deadline is approximately 300 seconds, a later generation while active adds none, and generation after forced expiry admits the next candidate. Add a cap-two test proving at most two candidates are admitted.

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:PYTHONPATH='backend'; .\.venv\Scripts\python.exe -m unittest tests.test_shadow_candidate_priority -v`

Expected: the new admission and five-minute deadline assertions fail against current behavior.

- [ ] **Step 3: Implement minimal admission logic**

Expire candidates before candidate selection, calculate `available_shadow_slots = max(0, max_trade_subscriptions - active_candidate_count)`, stop creating `paper_promoted` candidates when those slots are filled, and use `SHADOW_ENTRY_WINDOW_SECONDS` for their deadlines. Do not change watchlist or live-position intent behavior.

- [ ] **Step 4: Run tests and verify GREEN**

Run the focused command from Step 2 and require zero failures.

- [ ] **Step 5: Commit**

Commit `backend/app/core/state.py` and `tests/test_shadow_candidate_priority.py` with message `fix: align shadow candidates with paid capacity`.

### Task 2: Pure evidence-funnel diagnostics

**Files:**
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_shadow_candidate_priority.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Produces: `Storage.shadow_candidate_funnel(now: datetime, window_hours: int) -> dict[str, object]` and `BotState.shadow_evidence_funnel_status(now: datetime | None = None) -> dict[str, object]`.
- Exposes: `candidate_funnel` in `/health/deep` without mutation or sensitive identifiers.

- [ ] **Step 1: Write failing funnel tests**

Construct durable completed, missing-entry, missing-exit, active, and overdue-capture fixtures. Assert exact attempts, terminal attempts, entry/completion conversion, excess queue, latest timestamps, and diagnostic conditions. Patch mutation helpers to raise and prove the projection does not call them.

- [ ] **Step 2: Run tests and verify RED**

Run the focused candidate and health tests; expect missing-method or missing-field failures.

- [ ] **Step 3: Implement the pure projection**

Use indexed candidate columns and bounded aggregate queries. Return no mint, wallet, API key, audit payload, or execution data. Calculate one-, four-, and twelve-hour windows and conditions for cap excess, overdue captures, at least 20 terminal attempts below 2% completion, and latest advancement timestamps.

- [ ] **Step 4: Expose projection in deep health**

Add the redacted `candidate_funnel` object alongside `candidate_priority`. Do not add a mutating endpoint.

- [ ] **Step 5: Run tests and verify GREEN**

Run candidate-priority and focused health tests and require zero failures.

- [ ] **Step 6: Commit**

Commit the backend and tests with message `feat: expose shadow evidence funnel health`.

### Task 3: Restart-safe local monitor state and early warnings

**Files:**
- Modify outside repository: `C:\Users\Ari Rosner\Projects\CryptoARC\evidence\2026-08-11\shadow-campaign-monitor.py`
- Modify outside repository: `C:\Users\Ari Rosner\Projects\CryptoARC\evidence\2026-08-11\test-shadow-campaign-monitor.py`

**Interfaces:**
- Consumes: `/health/deep.candidate_funnel`, previous `shadow-campaign-status.json`.
- Produces: `candidate_funnel`, `progress_timestamps`, `evidence_pipeline_warnings`, and previous-run deltas in the status artifact.

- [ ] **Step 1: Write failing pure-function tests**

Add tests for poor conversion after 20 terminal attempts, no warning below the minimum population, cap excess/unserved queue, monotonic counter decrease, advancement timestamps, and warning recovery.

- [ ] **Step 2: Run tests and verify RED**

Run: `& '<campaign worktree>\.venv\Scripts\python.exe' 'C:\Users\Ari Rosner\Projects\CryptoARC\evidence\2026-08-11\test-shadow-campaign-monitor.py' -v`

Expected: missing diagnostic helper failures.

- [ ] **Step 3: Implement pure comparison helpers and status persistence**

Load the previous status before collection, compare monotonic counters and funnel windows, preserve latest advancement timestamps, emit bounded warning identifiers/details, and write them into the next atomic status artifact. Do not mutate campaign evidence.

- [ ] **Step 4: Run tests and verify GREEN**

Run the monitor tests and require zero failures.

- [ ] **Step 5: Dry-run against current authoritative endpoints**

Import the monitor module and call its pure diagnostics with the current status and health payload. Confirm the existing low-yield campaign produces the expected early warning without starting, stopping, quoting, or trading.

### Task 4: Update the recurring Codex monitor policy

**Files:**
- Update via Codex automation API: `monitor-cryptoarc-shadow-campaign`

**Interfaces:**
- Consumes: durable `candidate_funnel` and monitor status warnings.
- Produces: hourly general evidence-usefulness checks.

- [ ] **Step 1: Preserve existing automation fields and expand the prompt**

Add explicit rules to inspect funnel windows, cap excess, unserved candidates, poor conversion, deadlines, paid-slot ownership, counter deltas, dashboard divergence, reconnect/backlog effects, and repeated failures. State that green process health does not override evidence-pipeline warnings.

- [ ] **Step 2: Verify the automation**

Read it back through the automation API and confirm its id, hourly schedule, active status, target thread, safety prohibitions, and new funnel rules.

### Task 5: Integration, review, merge, and exact-main deployment

**Files:**
- Repository changes from Tasks 1-2
- Local monitor changes from Task 3

**Interfaces:**
- Produces: reviewed PR, merged exact-main commit, controlled paper deployment, and live funnel evidence.

- [ ] **Step 1: Run focused and full verification**

Run candidate, economic, source lifecycle, core health, and monitor tests; compile affected Python; run `scripts/verify.ps1` because this is campaign-critical behavior.

- [ ] **Step 2: Push and open a focused PR**

Push `fix/shadow-yield-funnel`, open a PR explaining the one-slot budget boundary, five-minute entry window, funnel diagnostics, and unchanged live authority.

- [ ] **Step 3: Address review and security findings**

Inspect connector feedback, CI, CodeQL, dependency review, secret scanning, and Dependabot. Fix only actionable regressions, test first, and resolve threads only after verification.

- [ ] **Step 4: Merge only when all required gates pass**

Use squash merge and record the merge commit.

- [ ] **Step 5: Deploy safely**

Disable the scheduled collector, verify the exact campaign processes, stop only the campaign backend/monitor, switch the detached campaign worktree to the merged main commit, remove only a verified stale zero-byte lock if necessary, then re-enable the task.

- [ ] **Step 6: Verify live paper behavior**

Confirm paper mode, all live flags false, source connected/trusted/fresh, one paid subscription, at most one active candidate, a five-minute awaiting-entry deadline, no overdue capture, fresh dashboard, task result zero, and funnel diagnostics consistent with raw durable records.

## Plan Self-Review

- Every approved design requirement maps to a task.
- The repository and temporary local monitor write sets are separated.
- Tests precede every behavior change.
- No paid-scope or live-authority expansion is permitted.
- No placeholders or unspecified implementation steps remain.
