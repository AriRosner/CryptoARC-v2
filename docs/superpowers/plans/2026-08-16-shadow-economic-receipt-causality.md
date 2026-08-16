# Shadow Economic Receipt Causality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure only market evidence genuinely received after a shadow quote can trigger and qualify an economic exit.

**Architecture:** Preserve processing time for diagnostics, but use durable `AcceptedMarketObservation.received_at` as the causal clock for entry/exit selection and rule timing. Persist quote, entry-receipt, and exit-receipt timestamps into every economic comparison so the pure final validator and external monitor can independently reject non-causal evidence.

**Tech Stack:** Python 3.11, dataclasses, SQLite, `unittest`, FastAPI state/storage, repository evidence exporter.

## Global Constraints

- Keep `LIVE_TRADING_ENABLED=false`, paper mode, and the kill switch unchanged.
- Never mutate or reuse the frozen r2 database.
- Use the captured settings version for rule evaluation.
- Treat event receipt time—not asynchronous processing time—as the forward-evidence boundary.
- Start no replacement formal campaign until full verification and disposable real-source proof pass.

---

### Task 1: Causal shadow evidence selection

**Files:**
- Modify: `backend/app/core/state.py`
- Test: `tests/test_shadow_evaluation.py`

**Interfaces:**
- Consumes: `AcceptedMarketObservation.received_at`, quote `created_at`.
- Produces: shadow rule observations ordered and timed by receipt; pre-quote backlog cannot become an exit.

- [x] Add a regression where an observation has `received_at <= quoted_at` but `observed_at > quoted_at`; assert the shadow remains `waiting_for_price` and no economic row persists.
- [x] Run `python -m unittest tests.test_shadow_evaluation.ShadowEvaluationTests.test_received_before_quote_observation_cannot_trigger_exit -v`; verify it fails because the sample is currently evaluated.
- [x] Filter entry evidence with `received_at <= quoted_at`, exit evidence with `received_at > quoted_at`, and construct rule observations using `received_at` as their causal timestamp.
- [x] Re-run the regression and full `tests.test_shadow_evaluation`; verify green.

### Task 2: Independent final-validator defense

**Files:**
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/core/shadow_evaluation.py`
- Test: `tests/test_shadow_evaluation.py`

**Interfaces:**
- Produces: optional `quoted_at`, `entry_received_at`, and `exit_received_at` fields on `ShadowComparison`, serialized as ISO-8601.
- Enforces: `entry_received_at <= quoted_at < exit_received_at` and `completed_at == exit_received_at` for qualification.

- [x] Add validator tests for missing timing proof and pre-quote exit receipt; verify both fail under the current validator.
- [x] Add timestamp fields and storage serialization/deserialization.
- [x] Populate fields only from the bound accepted observations used by the strict persistence path.
- [x] Add `source_evidence_timing_invalid` as a deduplicated blocker when timing proof is missing or non-causal.
- [x] Run the focused evaluator/storage tests and verify green.

### Task 3: Operational detection and frozen-evidence audit

**Files:**
- Modify: `evidence/2026-08-11/shadow-campaign-monitor.py`
- Modify: `evidence/2026-08-11/test-shadow-campaign-monitor.py`
- Modify: `scripts/export-shadow-campaign-evidence.py`
- Test: `tests/test_shadow_evaluation.py`

**Interfaces:**
- Produces: a nonzero `received_before_quote_economic_samples` reachability count and immediate pipeline/anomaly warning.

- [x] Add a monitor regression using a persisted economic record whose exit evidence was received before its quote; verify red.
- [x] Join economic evidence IDs to accepted observations and audits, count causal violations, and emit `received_before_quote_economic_evidence` immediately; the exporter already promotes pipeline warnings to anomalies.
- [ ] Verify the frozen r2 archive triggers the warning and the corrected disposable database does not. (Frozen r2 detection is complete; corrected disposable proof remains.)

### Task 4: Verification and replacement campaign

**Files:**
- Update durable evidence under `evidence/2026-08-11/` only after commands pass.

- [x] Run focused shadow, monitor, storage, source, and candidate tests.
- [x] Run `scripts/verify.ps1` and require a clean exit.
- [ ] Run security diff review and CI on the exact commit.
- [ ] Run a disposable live-source preflight proving pre-quote backlog is rejected and genuinely later receipt can evaluate.
- [ ] Merge, create a clean detached runtime/database, establish an exact zero boundary, retarget paused automation, then start r3 and repeat integrity, safety, exporter, dashboard, and exact-stop audits.
