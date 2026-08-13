# Reconnect Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve successful disconnect/recovery evidence for the current paper campaign and present it accurately in the temporary soak dashboard.

**Architecture:** Extend the in-memory `SourceStatus` projection with cumulative per-process reconnect event counts and last disconnect/recovery timestamps. Both PumpPortal websocket loops update the shared telemetry, while the existing `reconnect_attempts` remains the current consecutive primary-stream retry count. The temporary dashboard derives a warning state from those fields without adding controls or trading authority.

**Tech Stack:** Python 3.11, asyncio, websockets, unittest, React 19, TypeScript, Vitest, Astryx, StyleX.

## Global Constraints

- Keep `LIVE_TRADING_ENABLED=false`, paper mode, and live execution unavailable.
- Do not access wallets, signers, simulation, submission, acknowledgement, arming, or live session endpoints.
- Backend telemetry is process-lifetime operational evidence; the temporary dashboard remains uncommitted.
- A recovered incident remains visually highlighted for 10 minutes.

---

### Task 1: Backend reconnect lifecycle telemetry

**Files:**
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/sources.py`
- Modify: `backend/app/core/state.py`
- Test: `tests/test_source_cancellation.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Produces: `SourceStatus.reconnect_events`, `trade_reconnect_events`, `last_disconnect_at`, `last_recovered_at`, and `last_disconnect_stream`.
- Produces: the same fields in `/health/deep` and `/api/source-health` projections.

- [ ] Write source-loop tests proving disconnect increments the appropriate cumulative count, records the stream and time, successful reconnect records recovery, current primary attempts reset to zero, and trade subscriptions are replayed.
- [ ] Run the focused tests and confirm they fail because the new fields do not exist.
- [ ] Add the minimal model fields, serialization, loop updates, and source-health projection.
- [ ] Run focused source and source-health tests and confirm they pass.

### Task 2: Temporary dashboard recovery warning

**Files:**
- Create: `C:/Users/Ari Rosner/Projects/CryptoARC/evidence/2026-08-11/soak-dashboard/src/data/reconnect.ts`
- Create: `C:/Users/Ari Rosner/Projects/CryptoARC/evidence/2026-08-11/soak-dashboard/src/data/reconnect.test.ts`
- Modify: `C:/Users/Ari Rosner/Projects/CryptoARC/evidence/2026-08-11/soak-dashboard/src/App.tsx`

**Interfaces:**
- Consumes: backend reconnect fields from `sourceHealth`, falling back to `health.source`.
- Produces: a plain-language current/recent incident assessment with cumulative launch/trade counts.

- [ ] Write failing tests for active reconnect, recovery within 10 minutes, and quiet healthy state.
- [ ] Run the focused Vitest file and confirm failure because the assessment helper is absent.
- [ ] Implement the helper and render an amber banner plus accurate Campaign State labels.
- [ ] Run dashboard tests, lint, and build.

### Task 3: Rate semantics and campaign verification

**Files:**
- Inspect: `soak-dashboard/server-lib.mjs`
- Inspect: `soak-dashboard/src/data/health.ts`
- Inspect: live `/dashboard-data`, `/health/deep`, `/api/source-health`, and the authoritative status file.

**Interfaces:**
- Verifies: paid rate is the positive delta in paid trade messages over the trailing 30 minutes.
- Verifies: stored events/min is the authoritative database source-event delta per elapsed minute.

- [ ] Recompute both rates from persisted dashboard samples.
- [ ] Explain counter resets and the post-filter source-event rate reduction with raw values.
- [ ] Verify paper-only authority, fresh source activity, Direct Match, evaluated shadows, and economic samples.
- [ ] Commit and push only the backend telemetry changes, open a PR, wait for required checks, merge if clean, and deploy exact `main` safely.
