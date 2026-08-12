# Soak Operations Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the seven-day paper/shadow campaign observable, recoverable, and exportable without changing trading authority or evidence semantics.

**Architecture:** Reuse already-computed readiness dependencies inside composite reports instead of rebuilding the same large evidence graphs. Add read-only command-line evidence tooling around a deterministic Python core, then validate the active database through SQLite's online backup API and an independent read-only connection.

**Tech Stack:** Python 3.11, SQLite, unittest/pytest, PowerShell, GitHub Actions/CLI.

## Global Constraints

- Keep `LIVE_TRADING_ENABLED=false`, persisted paper mode, kill switch enabled, and live execution unavailable.
- Never invoke wallet, signer, simulation, submission, acknowledgement, arming, or live-session endpoints.
- Do not alter strategy settings, readiness thresholds, or evidence eligibility semantics.
- Profile and restore-test only database copies; use SQLite online backup for the live snapshot.
- Preserve all unrelated dirty worktrees and files.

---

### Task 1: Composite report performance

**Files:**
- Modify: `backend/app/core/state.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: existing `source_health()`, `source_soak_acceptance_report()`, `readiness_status()`, and `live_status()` results.
- Produces: optional internal snapshot parameters that preserve public API output while eliminating duplicate report construction.

- [ ] Write a failing test asserting one source-soak and one readiness build per pilot report.
- [ ] Run the focused test and confirm duplicate calls make it fail.
- [ ] Add optional precomputed snapshots to the internal report methods and pass them from `pilot_readiness_report`.
- [ ] Run focused report-contract tests and benchmark a copied campaign database.
- [ ] Commit the verified performance milestone.

### Task 2: Deterministic campaign evidence and anomaly tooling

**Files:**
- Create: `backend/app/core/soak_evidence.py`
- Create: `scripts/export-shadow-campaign-evidence.py`
- Create: `tests/test_soak_evidence.py`
- Modify: `docs/manual/16-evidence-campaign.md`

**Interfaces:**
- Consumes: monitor status JSON, a read-only SQLite database, exact code head, and optional prior status JSON.
- Produces: schema-versioned redacted JSON and Markdown summaries plus explicit anomaly findings.

- [ ] Write failing tests for deterministic output, counter regression, code drift, stale monitor state, database/status divergence, seven-day/sample gates, and secret redaction.
- [ ] Run tests and confirm the module/CLI are absent.
- [ ] Implement pure snapshot/anomaly functions and a read-only CLI wrapper.
- [ ] Run focused tests and generate an artifact from a database copy.
- [ ] Commit the evidence-tooling milestone.

### Task 3: Backup and resume validation

**Files:**
- Create: `scripts/test-shadow-campaign-backup.py`
- Create: `tests/test_shadow_campaign_backup.py`
- Modify: `docs/manual/16-evidence-campaign.md`
- Update outside Git: `evidence/2026-08-11/FRIDAY-PAUSE-RESUME.md`

**Interfaces:**
- Consumes: active SQLite path and output directory.
- Produces: online backup database plus JSON validation containing integrity, schema, safety state, and source-count parity.

- [ ] Write failing tests for online-backup validation and refusal to overwrite an existing artifact.
- [ ] Implement the minimal backup validator using `sqlite3.Connection.backup` and independent `mode=ro` checks.
- [ ] Run focused tests, create a fresh active-campaign backup, and verify it independently.
- [ ] Perform a bounded scheduled-task pause/resume drill only while the task is idle; prove code head, safety invariants, and event growth afterward.
- [ ] Commit the resilience milestone.

### Task 4: Release verification and publication

**Files:**
- Review all files above.

**Interfaces:**
- Consumes: focused tests, canonical verifier, GitHub checks, CodeQL, secret scanning, Dependabot, and campaign monitor state.
- Produces: reviewed commits, pushed branch, pull request, green merge, and exact-main campaign continuation.

- [ ] Run focused backend/script tests and syntax checks.
- [ ] Run `scripts/verify.ps1` and inspect the complete exit result.
- [ ] Review diff for secrets, authority changes, threshold changes, and unrelated files.
- [ ] Push the branch, open the PR, wait for required checks, resolve only safe failures, and merge.
- [ ] Advance the campaign worktree to exact main, verify the scheduled task remains hidden/healthy, and re-check all security/dependency surfaces.

## Self-Review

- Spec coverage: performance, backup/restore, pause/resume, deterministic export, anomalies, and security watch are each assigned to a testable task.
- Placeholder scan: no deferred implementation placeholders are present.
- Type consistency: snapshot inputs remain dictionaries; evidence outputs are schema-versioned dictionaries serialized by thin CLI wrappers.
