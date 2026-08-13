# Soak Final Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore continuous shadow-candidate collection and make the temporary soak dashboard's rates and trends reconcile with authoritative campaign counters.

**Architecture:** Candidate generation will perform its existing intent-expiry maintenance synchronously before computing the ten-item active cap, preserving event-loop serialization and all execution boundaries. The temporary dashboard will continue using lightweight endpoints, but compact snapshots will handle process-counter resets and source evaluated-shadow history from the campaign status artifact.

**Tech Stack:** Python 3.11, FastAPI application state, SQLite, unittest/pytest, Node.js, Vitest, React/Vite.

## Global Constraints

- Keep `LIVE_TRADING_ENABLED=false`, paper mode, and live execution unavailable.
- Do not call wallet, signer, simulation, submission, acknowledgement, arming, or live-session endpoints.
- Do not weaken source-soak, economic-validation, or sentinel gates.
- Do not commit the temporary dashboard.
- Preserve the exact campaign database and untracked `backend/cryptoarc.db`.

---

### Task 1: Recover candidate generation from expired open intents

**Files:**
- Modify: `backend/app/core/state.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: `BotState._mark_stale_live_intents(now)` and `BotState.generate_live_intents(...)`.
- Produces: generator behavior in which expired active intents are persisted as stale before the active-cap calculation.

- [ ] **Step 1: Write the failing regression**

Create ten expired open paper-promoted intents plus one eligible recent paper token, call `generate_live_intents`, and assert the old intents become stale and the eligible token receives a new intent/candidate.

- [ ] **Step 2: Verify the regression fails**

Run: `.venv\Scripts\python.exe -m unittest tests.test_core.CoreLogicTests.test_generate_live_intents_expires_stale_rows_before_capacity_check -v`

Expected: FAIL because the ten expired rows still fill the active-intent cap.

- [ ] **Step 3: Implement minimal serialized maintenance**

Call `_mark_stale_live_intents(now)` before loading and filtering intents in `generate_live_intents`. Do not move the generator or maintenance to a worker thread and do not change execution authority.

- [ ] **Step 4: Verify focused and neighboring candidate tests**

Run the new test plus `tests.test_shadow_candidate_priority` and the existing live-intent generation tests.

- [ ] **Step 5: Commit**

Commit only the backend and test changes with message `fix: expire intents before shadow generation`.

### Task 2: Reconcile temporary dashboard rates and shadow trends

**Files:**
- Modify locally: `evidence/2026-08-11/soak-dashboard/server-lib.mjs`
- Modify locally: `evidence/2026-08-11/soak-dashboard/server-lib.test.mjs`
- Modify locally only if required: `evidence/2026-08-11/soak-dashboard/src/data/normalize.ts`

**Interfaces:**
- Consumes: monotonic database counts, process-local paid-message counters, campaign `evaluated_shadow_quotes`.
- Produces: non-negative rates only across compatible counters and persisted evaluated-shadow history.

- [ ] **Step 1: Add failing Vitest cases**

Cover process-local paid-counter reset, monotonic source-event deltas, and campaign-status fallback for evaluated shadows.

- [ ] **Step 2: Verify the tests fail for the missing fallback/reset semantics**

Run: `npm test -- server-lib.test.mjs`.

- [ ] **Step 3: Implement minimal snapshot corrections**

Use `status.evaluated_shadow_quotes` before optional report fields. Return `null`, not zero, for a paid-counter interval that crossed a backend restart. Keep authoritative one-minute source-health and observed database-throughput metrics distinct.

- [ ] **Step 4: Run all dashboard tests and build**

Run: `npm test`; expected all tests pass. Run: `npm run build`; expected exit 0.

- [ ] **Step 5: Keep changes local**

Do not stage or commit any temporary dashboard files.

### Task 3: Integrate, deploy, and prove live collection

**Files:**
- No additional product files expected.
- Runtime-only monitor/dashboard files remain outside the repository.

**Interfaces:**
- Consumes: merged `origin/main`, scheduled monitor, backend port 8010, dashboard port 4174.
- Produces: exact-main campaign running one backend/monitor chain with candidate generation no longer cap-blocked.

- [ ] **Step 1: Run repository verification**

Run focused tests, full backend tests, `scripts/verify.ps1`, and `git diff --check` in the isolated worktree.

- [ ] **Step 2: Publish and review**

Push the branch, open a PR, require CI/CodeQL, and obtain independent correctness/safety review before merge.

- [ ] **Step 3: Deploy exact main safely**

Pause the scheduled task, stop only verified campaign backend descendants, fast-forward the exact-main worktree, clear only a verified stale monitor lock, and restart one hidden scheduled instance.

- [ ] **Step 4: Observe multiple natural cycles**

Verify dashboard timestamps advance, task results remain zero, source trust stays trusted, the generator no longer reports zero solely due to expired open intents, and accepted prices/candidates resume when eligible market events arrive.

- [ ] **Step 5: Reconcile all displayed statistics**

Confirm source events, paid rate, accepted prices, evaluated shadows, economic samples, source-soak gates, sentinel state, and safety flags agree across API, database, status artifact, and dashboard. Report remaining evidence gates honestly.
