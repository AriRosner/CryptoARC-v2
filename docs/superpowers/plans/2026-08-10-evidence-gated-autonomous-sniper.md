# Evidence-Gated Autonomous Sniper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Do not use or spawn subagents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finalize one deterministic, evidence-gated new-token sniper that can be validated without live authority, then admit separately authorized manual-live and attended autonomous evidence only after every machine-verifiable gate is fresh.

**Architecture:** Keep `BotState` and the existing intent-to-reconciliation flow authoritative. Add focused deterministic domain modules, versioned SQLite records, authenticated read/report APIs, and a separate bounded low-priority review worker; the sentinel, grader, model classifier, dashboard, and candidate pipeline never gain live authority. Treat genuine source observations and later physical rehearsals as external evidence campaigns, not test fixtures or software-completion claims.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, SQLite WAL and schema migrations, `unittest`, React 19, TypeScript 5.7, Vite 8, PowerShell operational scripts.

## Global Constraints

- Repository: `C:\Users\Ari Rosner\Projects\CryptoARC\CryptoARC-v2`; execute this plan in a fresh isolated implementation worktree created from the approved design branch, not in a dirty shared checkout.
- Keep `LIVE_TRADING_ENABLED=false` through Tasks 1-10 and every automated test.
- Do not create or fund wallets; the $100 pilot wallet plus $100 external reserve is a design limit only.
- Do not unlock or invoke signers, arm or acknowledge a backend, approve or submit a transaction, or traverse a live-network transaction path during implementation or automated verification.
- Do not purchase, configure, or invent funded source credentials. Genuine observations, shadows, readiness, profitability, and production evidence must come from attributable external evidence windows.
- Do not start shared runtimes or databases. Every test uses temporary directories, local fixtures, and mocked read-only clients.
- Do not run `scripts/verify.ps1`, mobile gates, shared runtime probes, or physical/live drills without a separately coordinated window.
- Sentinel verdicts are deterministic, expiring, stale-rejecting, read-only, and zero-authority.
- Grading is asynchronous and outside ingestion, decision, execution, protective-exit, confirmation, reconciliation, audit, ledger, and kill-switch paths.
- Strategy candidates are immutable, cannot self-promote, and cannot replace an active-session version.
- Dashboard, sentinel, reporting, grading, and model workloads shed before ingestion, execution, protective exits, reconciliation, ledger/audit integrity, or kill-switch handling degrades.
- No output may claim guaranteed profit or blend replay, paper, shadow, manual-live, and autonomous-live PnL.
- Do not merge, rebase, push, open a PR, or begin Tasks 11-12 without separate authorization.

---

## Planned File Structure

- `backend/app/core/evidence_inventory.py`: immutable exact-main and evidence-state inventory assembly.
- `backend/app/core/strategy_contract.py`: canonical strategy schema, hashing, validation, and deterministic decision input.
- `backend/app/core/shadow_evaluation.py`: all-cost shadow ledger, walk-forward/cost-stress metrics, and economic gate.
- `backend/app/core/sentinel.py`: deterministic expiring market-session verdict from bounded read models.
- `backend/app/core/trade_grading.py`: deterministic ex-ante/ex-post grading, append-only corrections, and redaction.
- `backend/app/core/model_classifier.py`: disabled-by-default bounded batch classifier contract.
- `backend/app/core/strategy_candidates.py`: immutable candidate creation, comparison, rejection, and explicit promotion checks.
- `backend/app/core/workload_governor.py`: pressure measurements, priority tiers, bounded queues, and load shedding.
- `backend/app/core/pilot_risk.py`: session-start USD-to-SOL conversion and immutable pilot caps.
- `backend/app/core/models.py`: persisted record dataclasses/enums shared by the new modules.
- `backend/app/core/storage.py`: migrations and narrow save/load/claim/finalize methods; no generic unbounded scans.
- `backend/app/core/state.py`: compose new modules into existing source, readiness, intent, audit, ledger, backup, and reporting contracts.
- `backend/app/main.py`: authenticated read/report endpoints plus explicitly guarded candidate promotion; no sentinel/grader authority endpoint.
- `backend/app/grading_worker.py`: separate low-priority worker entrypoint with bounded concurrency and cancellation.
- `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/pages/AnalysisPage.tsx`, `frontend/src/pages/ReviewPage.tsx`, `frontend/src/pages/DataPage.tsx`: bounded cached projections and visible degraded/stale state.
- `frontend/scripts/check-critical-projections.mjs`: static UI contract check for bounded polling and authenticated exports.
- `scripts/capture-evidence-inventory.ps1`, `scripts/run-critical-path-load-test.ps1`, `scripts/rehearse-production-gates.ps1`: fail-closed local evidence capture; live steps remain disabled unless separately authorized.
- `docs/manual/16-evidence-campaign.md`, `17-manual-live-proof.md`, `18-attended-autonomous-pilot.md`, `19-post-pilot-decision.md`: operator runbooks with explicit authorization boundaries.
- `tests/test_evidence_inventory.py`, `test_strategy_contract.py`, `test_shadow_evaluation.py`, `test_sentinel.py`, `test_trade_grading.py`, `test_model_classifier.py`, `test_strategy_candidates.py`, `test_workload_isolation.py`, `test_pilot_risk.py`, `test_production_gate_rehearsal.py`, `test_manual_live_proof.py`, `test_autonomous_pilot.py`, `test_post_pilot_review.py`: focused TDD suites.
- `tests/fixtures/evidence_gated/*.json`: synthetic/local contract fixtures marked `fixture_only=true`; never eligible for genuine readiness.

## Interface Conventions

All new persisted records include `record_id`, `created_at`, `schema_version`, `strategy_id`, `strategy_version`, and `evidence_mode`. Timestamps are timezone-aware UTC ISO-8601 strings; future, naive, stale, conflicting, or version-mismatched evidence fails closed. Every collection API takes a bounded `limit`; every publication uses compare-and-set input/version identity so stale worker results cannot overwrite newer state.

---

### Task 1: Exact-Main Readiness and Evidence Inventory

**Files:**
- Create: `backend/app/core/evidence_inventory.py`
- Create: `tests/test_evidence_inventory.py`
- Create: `scripts/capture-evidence-inventory.ps1`
- Create: `docs/manual/16-evidence-campaign.md`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`

**Existing APIs and patterns to reuse:** `BotState.readiness_status`, `live_status`, `evidence_mode_separation_report`, `pilot_readiness_report`, `post_run_review_report`, `source_adapters`; authenticated report/export handlers in `backend/app/main.py`; read-only PowerShell diagnostics in `scripts/doctor.ps1`.

**Interfaces:**
- Produces: `EvidenceInventory.build(repo_head: str, origin_main: str, reports: Mapping[str, object]) -> dict[str, object]` and `GET /api/reports/evidence-inventory`.
- Consumes: current Git IDs supplied by the capture script and existing report payloads; it does not query Git or start services from request handling.

- [ ] **Step 1: Write the failing tests.** Add tests that require exact `head`, `origin_main`, `merge_base`, `dirty=false`, active strategy identity, source-access state, genuine/shadow sample counts, readiness blockers, backup age, signer mode, and explicit `deferred_physical_evidence`. Include a fixture with `fixture_only=true` and assert it cannot increment genuine counts.

```python
def test_inventory_keeps_fixture_rows_out_of_genuine_evidence(self) -> None:
    report = EvidenceInventory.build(
        repo_head="abc", origin_main="base",
        reports={"source": {"observations": [{"fixture_only": True}]}, "pilot": {"ready": False}},
    )
    self.assertEqual(report["evidence"]["genuine_source_observations"], 0)
    self.assertIn("genuine source soak", report["deferred_physical_evidence"])
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_evidence_inventory -v`

Expected: `ModuleNotFoundError: No module named 'app.core.evidence_inventory'`.

- [ ] **Step 3: Implement the immutable builder, endpoint, capture script, and runbook.** The script accepts `-BaseRef origin/main` and `-OutputPath`, refuses a dirty worktree, records `git rev-parse HEAD`, `origin/main`, and `merge-base`, and writes a JSON inventory without starting a runtime. The runbook labels source, shadow, rehearsal, manual-live, and autonomous-live evidence `DEFERRED` until captured from their authoritative paths.
- [ ] **Step 4: Run GREEN.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_evidence_inventory tests.test_scripts -v`

Expected: all inventory and script-contract tests pass; no runtime, DB, or network is opened.

**Acceptance criteria:** One report separates code state, machine-verifiable blockers, genuine evidence, fixture-only evidence, and deferred physical evidence. It never converts absence into readiness.

**Safety/performance invariants:** Read-only; bounded report inputs; no secrets; no authority mutations; no runtime launch.

**Rollback point:** Revert the endpoint, builder, script, runbook, and tests; existing readiness reports remain authoritative.

**Dependencies / independent mergeability:** No prior task. Independently mergeable because it only composes existing read reports.

**Commit:** `git commit -m "feat: add fail-closed evidence inventory"`

---

### Task 2: Genuine Market-Data Access and Source-Soak Evidence

**Files:**
- Modify: `backend/app/core/sources.py`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Create: `tests/test_genuine_source_evidence.py`
- Create: `tests/fixtures/evidence_gated/source_conflicts.json`
- Modify: `docs/manual/16-evidence-campaign.md`

**Existing APIs and patterns to reuse:** `PumpPortalLaunchSource._run_trade_stream`, `normalize_pumpportal_trade`, `PricePipeline.observe`, `BotState.solana_logs_verification_report`, `source_soak_acceptance_report`, `record_source_soak_snapshot`, and storage migration 008/source-soak history.

**Interfaces:**
- Produces: `AcceptedMarketObservation` with source/event IDs, observed/received times, price, confidence, acceptance reason, conflict state, access state, and `fixture_only`; `SourceEvidenceGate.evaluate(...) -> SourceEvidenceResult`.
- Consumes: normalized launch/trade events and direct Solana comparison; never fabricates missing prices.

- [ ] **Step 1: Write failing tests** for missing/future/naive/stale prices, funded-access denial, primary/direct conflict, duplicate event identity, archival round trip, exact-strategy attribution, and fixtures excluded from promotion.

```python
def test_funded_access_failure_blocks_shadow_promotion(self) -> None:
    result = SourceEvidenceGate.evaluate(observations=[], access_state="funding_required", now=UTC_NOW)
    self.assertFalse(result.shadow_eligible)
    self.assertEqual(result.blockers, ("funded_trade_price_access_unavailable",))
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_genuine_source_evidence -v`

Expected: import/type failures for `AcceptedMarketObservation` and `SourceEvidenceGate`.

- [ ] **Step 3: Implement minimal accepted-observation persistence and fail-closed gate.** Add migration 012 with unique `(source, source_event_id, observed_at)` identity and bounded indexes. Preserve raw source-event archival; store access failures as evidence, not observations. Extend source-soak snapshots with accepted price count, conflicts, staleness, access state, and direct-comparison sample IDs.
- [ ] **Step 4: Run GREEN plus existing focused source tests.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_genuine_source_evidence tests.test_source_event_batch tests.test_source_cancellation -v`

Expected: all pass with no external connection.

**Acceptance criteria:** Only attributable accepted trade-price observations can advance source evidence; access failures and insufficient samples block without retry storms. The physical seven-day source soak remains deferred.

**Safety/performance invariants:** Queue operations bounded; parsing deterministic; raw credentials never persisted; source conflicts block new entries; fixture rows cannot satisfy gates.

**Rollback point:** Migration 012 is additive; revert consumers while leaving the table inert.

**Dependencies / independent mergeability:** Depends only on Task 1 vocabulary. Independently mergeable before strategy work.

**Commit:** `git commit -m "feat: persist genuine source evidence"`

---

### Task 3: Versioned Deterministic Sniper Strategy

**Files:**
- Create: `backend/app/core/strategy_contract.py`
- Create: `tests/test_strategy_contract.py`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/strategy.py`
- Modify: `backend/app/core/risk.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`

**Existing APIs and patterns to reuse:** `DecisionPipeline.evaluate/strategy_snapshot`, `RiskEngine.evaluate/entry_confirmation_reason`, `StrategyDecisionRecord`, `SettingsVersion`, deterministic backtest fingerprints, `live_intent_generate` (intent creation only).

**Interfaces:**
- Produces: `SniperStrategyVersion.from_dict(payload)`, `.canonical_json()`, `.fingerprint()`, and `SniperDecision.evaluate(strategy, evidence, session_state) -> StrategyDecision`.
- Consumes: Task 2 accepted observations and immutable session risk state; produces an intent recommendation, never a signer call.

- [ ] **Step 1: Write failing contract tests** covering every Section 5 field, canonical ordering/hash stability, unknown/missing-field rejection, source freshness, token age, liquidity, authority/concentration policies, all exits, quote/cost caps, exposure/stops, explicit rejection reasons, abstention, and changed-version restart.

```python
def test_missing_required_evidence_abstains_with_stable_reason(self) -> None:
    decision = SniperDecision.evaluate(STRATEGY_V1, evidence={"liquidity_sol": None}, session_state=EMPTY_SESSION)
    self.assertEqual(decision.action, "abstain")
    self.assertEqual(decision.reasons, ("required_liquidity_missing",))
    self.assertEqual(decision.strategy_version, "sniper-v1")
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_strategy_contract -v`

Expected: missing `strategy_contract` module.

- [ ] **Step 3: Implement the frozen contract and integrate it behind the current strategy pipeline.** Add migration 013 for immutable strategy versions and decision-to-version foreign identity. Save the complete canonical configuration and fingerprint with every decision. Reject duplicate version IDs with different content.
- [ ] **Step 4: Run GREEN and regression tests.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_strategy_contract tests.test_strategy_promotion_cohort tests.test_core.CoreTests.test_backtest_runs_have_deterministic_fingerprints -v`

Expected: all pass.

**Acceptance criteria:** Identical inputs produce identical action, score, reasons, exits, and fingerprint; any required missing/stale evidence abstains; strategy produces intents only.

**Safety/performance invariants:** Pure evaluation, no I/O, no wall-clock reads inside evaluator, no mutation of prior versions, no live authority.

**Rollback point:** Disable the versioned strategy selector and return to the existing decision pipeline; retain additive records.

**Dependencies / independent mergeability:** Depends on Task 2 evidence type. Mergeable independently of UI, grading, and live work.

**Commit:** `git commit -m "feat: add immutable sniper strategy contract"`

---

### Task 4: All-Cost Shadow Evaluation and Economic Validation

**Files:**
- Create: `backend/app/core/shadow_evaluation.py`
- Create: `tests/test_shadow_evaluation.py`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`

**Existing APIs and patterns to reuse:** shadow-only quote audits, `shadow_comparison`, landing windows, `simulation_accuracy_report`, `evidence_mode_separation_report`, `BacktestRun`, peak-to-trough drawdown tests.

**Interfaces:**
- Produces: `ShadowCostBreakdown`, `ShadowComparison`, and `EconomicValidator.evaluate(strategy_version, comparisons, now) -> EconomicGateReport`; `GET /api/reports/economic-validation`.
- Consumes: accepted prices, quote snapshots, observed landing windows, and explicit cost schedule.

- [ ] **Step 1: Write failing tests** for entry/exit slippage, base/priority/tip/rent/setup/failed-attempt costs, TP/SL/min/max hold, stale landing, 2x variable-cost stress, profit factor, peak-to-trough drawdown, seven-day/multi-regime span, 100 completed comparisons, walk-forward split, evidence-mode contamination, and future/version mismatch.

```python
def test_cost_stress_doubles_only_variable_execution_costs(self) -> None:
    report = EconomicValidator.evaluate("sniper-v1", [comparison(gross=1.0, base=.1, variable=.2)], NOW)
    self.assertAlmostEqual(report.cost_stress.net_pnl, 1.0 - .1 - .4)
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_shadow_evaluation -v`

Expected: missing module/types.

- [ ] **Step 3: Implement deterministic accounting and additive migration 014.** Persist every cost component and evidence ID; compute `sample_count>=100`, `calendar_days>=7`, `profit_factor>=1.20`, `max_drawdown<=10%` of modeled $100, positive held-out result, and non-catastrophic stress as distinct blockers. Never synthesize later prices or treat quote readiness as a completed shadow.
- [ ] **Step 4: Run GREEN and existing quote/shadow tests.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_shadow_evaluation tests.test_execution_readiness_quote_freshness -v`

Expected: all pass.

**Acceptance criteria:** The report explains every cent/SOL of modeled cost and cannot be ready without genuine, recent, version-matched evidence. Actual 100-comparison/seven-day campaign is deferred.

**Safety/performance invariants:** Read-only evaluation; bounded rows; mode separation; no live PnL claim; no network.

**Rollback point:** Remove the new report from readiness; retain raw shadow/audit rows.

**Dependencies / independent mergeability:** Depends on Tasks 2-3. Independently mergeable before sentinel/grading.

**Commit:** `git commit -m "feat: validate all-cost shadow economics"`

---

### Task 5: Deterministic Read-Only Market Session Sentinel

**Files:**
- Create: `backend/app/core/sentinel.py`
- Create: `tests/test_sentinel.py`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/pages/AnalysisPage.tsx`

**Existing APIs and patterns to reuse:** `_source_trust_snapshot`, cached readiness snapshots, source/quote/latency/economic/backup/auth/signer/reconciliation reports, bounded authenticated export helpers.

**Interfaces:**
- Produces: `Sentinel.evaluate(inputs: SentinelInputs, thresholds: SentinelThresholds, now: datetime) -> SentinelVerdict`; `GET /api/sentinel/current`; `GET /api/sentinel/history?limit<=100`.
- Consumes: bounded immutable read models only. No POST authority route is created.

- [ ] **Step 1: Write failing tests** for the four exact verdicts, missing/conflicting/future/expired inputs, creation/expiration, strategy/input supersession, sample size, thresholds/confidence/reasons, stale publication rejection, deterministic replay, and zero-authority static scan.

```python
def test_pilot_eligible_verdict_cannot_mutate_authority(self) -> None:
    verdict = Sentinel.evaluate(PILOT_ELIGIBLE_INPUTS, THRESHOLDS, NOW)
    self.assertEqual(verdict.status, "pilot_eligible")
    self.assertFalse(hasattr(verdict, "arm"))
    self.assertNotIn("live_enabled", verdict.to_dict())
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_sentinel -v`

Expected: missing sentinel module.

- [ ] **Step 3: Implement pure evaluation, migration 015, compare-and-set publication, bounded history, and stale UI.** The UI says “conditions assessment—not authorization,” shows age/expiry/blockers, and never renders an arm/start action beside the verdict.
- [ ] **Step 4: Run GREEN plus frontend contract/build.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_sentinel -v`

Run: `Push-Location frontend; npm run build; Pop-Location`

Expected: tests and build pass.

**Acceptance criteria:** Exactly one expiring verdict is published for an exact input/version identity; stale or replaced evidence yields/discards to `insufficient_evidence`; verdict never changes authority.

**Safety/performance invariants:** Deterministic, read-only, bounded queries, short reads, cached UI, zero signer/live imports.

**Rollback point:** Stop scheduling sentinel refresh and remove read endpoints/UI card; no trading behavior changes.

**Dependencies / independent mergeability:** Depends on Tasks 2-4 read models. Independently mergeable and safe to disable.

**Commit:** `git commit -m "feat: add zero-authority market sentinel"`

---

### Task 6: Asynchronous Deterministic-First Trade Grading

**Files:**
- Create: `backend/app/core/trade_grading.py`
- Create: `backend/app/grading_worker.py`
- Create: `tests/test_trade_grading.py`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/pages/ReviewPage.tsx`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`

**Existing APIs and patterns to reuse:** `trade_review_queue`, `trade_review_detail`, `TradeLabel`, audit/ledger persistence, mobile delivery claim/finish identity as the leasing model, and append-only event records.

**Interfaces:**
- Produces: `DeterministicTradeGrader.grade(TradeRevision) -> TradeGrade`, `enqueue_trade_review`, `claim_trade_review(lease_owner, lease_until)`, `finish_trade_review(job_id, claim_id, expected_revision, result)`.
- Consumes: completed paper/shadow/manual-live/autonomous-live revisions after their authoritative persistence commits.

- [ ] **Step 1: Write failing tests** for non-blocking enqueue, reclaimable leases, retry/dead-letter, entry/signal/risk/source/execution/exit classifications, ex-ante cutoff, separately stored ex-post result, mode separation, versions/evidence IDs/confidence, append-only corrections, stale-result rejection, and worker crash recovery.

```python
def test_future_information_cannot_change_ex_ante_grade(self) -> None:
    grade = DeterministicTradeGrader.grade(revision_with(post_exit_peak=99.0))
    self.assertNotIn("post_exit_peak", grade.ex_ante_facts)
    self.assertEqual(grade.ex_post_facts["post_exit_peak"], 99.0)
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_trade_grading -v`

Expected: missing module/queue methods.

- [ ] **Step 3: Implement migration 016, deterministic grader, durable low-priority queue, separate worker process, bounded claims, and append-only correction API.** Enqueue after completed evidence persistence and catch queue errors without rolling back the trade. Reject finish-by-claim when revision/version changed.
- [ ] **Step 4: Run GREEN.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_trade_grading -v`

Expected: all pass, including crash/reclaim cases.

**Acceptance criteria:** Every completed eligible revision can eventually obtain a versioned grade without delaying its persistence; corrections preserve originals; modes remain distinct.

**Safety/performance invariants:** Separate process, concurrency 1 by default, bounded batch/lease/retries, no live imports, no blocking enqueue, no private material.

**Rollback point:** Stop the worker and leave queued jobs durable; trading continues unchanged.

**Dependencies / independent mergeability:** Depends on Task 3 identities and Task 4 evidence modes. Mergeable independently of model/candidates.

**Commit:** `git commit -m "feat: add durable deterministic trade grading"`

---

### Task 7: Optional Bounded and Redacted Model Classification

**Files:**
- Create: `backend/app/core/model_classifier.py`
- Create: `tests/test_model_classifier.py`
- Modify: `backend/app/grading_worker.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/core/storage.py`
- Modify: `docs/manual/16-evidence-campaign.md`

**Existing APIs and patterns to reuse:** environment-backed config, secret-redaction behavior, grading claims/version checks, and deterministic grade facts from Task 6.

**Interfaces:**
- Produces: `ModelBatchPolicy(enabled=False, daily_token_budget, daily_cost_budget, max_items, timeout_seconds, retry_limit)` and `RedactedClassifier.classify(batch, policy, client) -> list[ModelClassification]`.
- Consumes: allowlisted deterministic-grade fields only; outputs ambiguous narrative categories/explanations only.

- [ ] **Step 1: Write failing tests** for disabled default, allowlist, seeds/keys/auth/raw-transaction/operator-data redaction, batch/item/token/cost/time/retry limits, cancellation, budget exhaustion leaving rule grade intact, stale revision rejection, and client failure isolation.

```python
def test_budget_exhaustion_never_blocks_or_replaces_rule_grade(self) -> None:
    result = RedactedClassifier.classify([RULE_GRADED_ITEM], policy(budget=0), client=FailIfCalled())
    self.assertEqual(result, [])
    self.assertEqual(RULE_GRADED_ITEM.status, "rule_graded")
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_model_classifier -v`

Expected: missing classifier module.

- [ ] **Step 3: Implement the disabled adapter and budget ledger.** Do not add a provider dependency; define a protocol injected only into the worker. Reject output unless job ID, trade revision, strategy/rules/input/schema versions still match.
- [ ] **Step 4: Run GREEN plus static secret scan.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_model_classifier tests.test_trade_grading -v`

Run: `rg -n "private_key|seed|authorization|signed_transaction" backend/app/core/model_classifier.py`

Expected: tests pass; matches occur only in the explicit denylist/test assertions.

**Acceptance criteria:** With default config no model call is possible. Enabling later affects explanations only, respects budgets, and cannot block or authorize anything.

**Safety/performance invariants:** Redacted allowlist, bounded batch/time/cost/retries, cancellable, separate worker, deterministic grade remains authoritative.

**Rollback point:** Set classifier disabled and remove injected client; queued work remains rule-graded.

**Dependencies / independent mergeability:** Depends on Task 6 only. Optional and independently mergeable/revertible.

**Commit:** `git commit -m "feat: add bounded redacted grade classification"`

---

### Task 8: Immutable Strategy Candidates and Gated Promotion

**Files:**
- Create: `backend/app/core/strategy_candidates.py`
- Create: `tests/test_strategy_candidates.py`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/pages/ReviewPage.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`

**Existing APIs and patterns to reuse:** immutable strategy presets/versions, backtest fingerprints, promotion cohort and drawdown logic, explicit authenticated review endpoints, session state, Tasks 4 and 6 reports.

**Interfaces:**
- Produces: `CandidateFactory.propose(base_version, patch, evidence_ids)`, `CandidateValidator.compare(incumbent, candidate, replay, walk_forward, shadow)`, and `PromotionGate.promote(candidate_id, operator_intent_id, now)`.
- Consumes: append-only grades/corrections and genuine version-matched evaluation. Promotion writes a new active-version selection only when no session is active.

- [ ] **Step 1: Write failing tests** for content-addressed immutability, leakage/train-collapse/sample/tail-loss/drawdown/exit/cost rejection, incumbent comparison, fixture exclusion, explicit operator intent, inactive-session requirement, double-promotion idempotency, and grader/sentinel inability to promote.

```python
def test_candidate_cannot_promote_during_active_session(self) -> None:
    result = PromotionGate(STORE).promote(CANDIDATE_ID, OPERATOR_INTENT_ID, now=NOW, active_session_id="live-1")
    self.assertFalse(result.promoted)
    self.assertEqual(result.blocker, "active_session")
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_strategy_candidates -v`

Expected: missing candidate module.

- [ ] **Step 3: Implement migration 017 and explicit promotion service.** Candidate payloads are frozen/content-addressed; validation phases append results; only `POST /api/strategy-candidates/{id}/promote` with auth, recorded operator intent, clear gates, and no active session can change selection. Promotion invalidates old sentinel results and starts a new validation campaign.
- [ ] **Step 4: Run GREEN and promotion regressions.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_strategy_candidates tests.test_strategy_promotion_cohort -v`

Expected: all pass.

**Acceptance criteria:** Candidates can be proposed and rejected without touching active strategy; promotion is explicit, audited, inactive-session-only, and resets validation readiness.

**Safety/performance invariants:** No self-promotion, no active-session changes, no live authority, immutable evidence chain.

**Rollback point:** Disable candidate endpoints; current active strategy remains unchanged.

**Dependencies / independent mergeability:** Depends on Tasks 3-6; optional classifier not required. Mergeable before any live work.

**Commit:** `git commit -m "feat: gate immutable strategy candidates"`

---

### Task 9: Critical-Path Isolation and Load Shedding

**Files:**
- Create: `backend/app/core/workload_governor.py`
- Create: `tests/test_workload_isolation.py`
- Create: `scripts/run-critical-path-load-test.ps1`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/core/storage.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/ReviewPage.tsx`
- Modify: `frontend/src/pages/AnalysisPage.tsx`
- Modify: `frontend/src/pages/DataPage.tsx`
- Create: `frontend/scripts/check-critical-projections.mjs`
- Modify: `frontend/package.json`

**Existing APIs and patterns to reuse:** background task ownership/cancellation, tick telemetry, readiness cache, short `_connect` context, bounded websocket snapshots, frontend polling guards, `check:polling`.

**Interfaces:**
- Produces: `WorkloadGovernor.observe(CriticalMetrics) -> PressureState`, `allowed(tier)`, `record_result(job_identity)`, and bounded `/api/monitoring/workload-pressure`.
- Consumes: queue depth, DB lock wait, source loss, p99 source-to-decision and intent-to-quote latency, memory/connections, focus/connectivity state.

- [ ] **Step 1: Write failing tests** for priority order, bounded queues, retry/dead-letter, short dashboard reads, websocket coalescing, stale-result rejection, three-window shedding, healthy recovery window, worker crash isolation, unfocused/disconnected backoff, and fixture load comparisons.

```python
def test_pressure_sheds_noncritical_work_in_required_order(self) -> None:
    governor = WorkloadGovernor(consecutive_failures=3, recovery_windows=3)
    state = drive_pressure(governor, windows=3)
    self.assertEqual(state.disabled_tiers, ("model", "grading", "sentinel", "dashboard_analytics"))
    self.assertTrue(state.allowed("kill_switch"))
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_workload_isolation -v`

Expected: missing governor module.

- [ ] **Step 3: Implement governor and local fixture load harness.** Configure SQLite bounded busy timeout and WAL read pattern without long dashboard write transactions. Coalesce websocket projections. The harness runs workers-off, normal, and review-stress against temporary DB/local mocks and emits a comparison JSON.
- [ ] **Step 4: Run GREEN and performance acceptance.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_workload_isolation tests.test_source_cancellation -v`

Run: `& .\scripts\run-critical-path-load-test.ps1 -FixtureOnly -OutputPath .\data\test-artifacts\critical-path-load.json`

Expected: zero accepted-observation loss, zero missed kill/protective events, bounded resources, <=5% p99 regression, DB lock p99 <=50 ms, and readable health/kill/positions/alerts under shedding.

**Acceptance criteria:** Reproducible local evidence proves measured non-interference; pressure publishes `degraded_observability` and sheds in the approved order.

**Safety/performance invariants:** Core tiers never shed; no live sender/signers; bounded memory/connections/locks; worker failure cannot terminate trading process.

**Rollback point:** Disable non-critical worker scheduling and cached analytics; core engine remains available.

**Dependencies / independent mergeability:** Depends on Tasks 5-7 workloads but governor tests use protocols. Mergeable before those consumers and activated incrementally.

**Commit:** `git commit -m "feat: isolate and shed noncritical workloads"`

---

### Task 10: Micro-Pilot Risk Enforcement

**Files:**
- Create: `backend/app/core/pilot_risk.py`
- Create: `tests/test_pilot_risk.py`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/components/SettingsModal.tsx`
- Modify: `frontend/src/types.ts`

**Existing APIs and patterns to reuse:** `BotSettings`, settings-version/operator-intent evidence, live quote preflight, submit-time cap recheck, session loss/kill-switch, one-position ledger, protective-sell exceptions.

**Interfaces:**
- Produces: `PilotRiskPolicy.create(reference_usd_per_sol, wallet_equity_sol, observed_at)`, `.evaluate_entry(request, state)`, and `.evaluate_exit(request, state)`.
- Consumes: independently observed session-start SOL/USD price and wallet equity; values become immutable for the session.

- [ ] **Step 1: Write failing tests** for decimal round-down, $5-or-5% requested trade, one position, $10 session/daily realized+unrealized stop, $25 cumulative freeze, three losses, 3% initial slippage, >5% configuration rejection, $0.25-or-5% total cost, no auto increase/restart/replenishment, and separate emergency-exit decision.

```python
def test_trade_cap_is_lower_of_five_dollars_or_five_percent_equity_and_rounds_down(self) -> None:
    policy = PilotRiskPolicy.create(reference_usd_per_sol=Decimal("200"), wallet_equity_sol=Decimal("0.4"), observed_at=NOW)
    self.assertEqual(policy.max_trade_sol, Decimal("0.0001") * 100)  # $2 at $200/SOL
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_pilot_risk -v`

Expected: missing policy module.

- [ ] **Step 3: Implement Decimal-based immutable policy and migration 018.** Persist reference observation ID, settings version, operator intent, rounded-down SOL caps, and cumulative-pilot ledger. Recheck at quote, preflight, and submit boundaries. Protective exits may return `requires_explicit_recovery_decision`; never silently widen.
- [ ] **Step 4: Run GREEN and existing cap/kill tests.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_pilot_risk tests.test_core.CoreTests.test_live_submit_rechecks_hard_caps_before_accepting_buy_signature tests.test_core.CoreTests.test_live_kill_switch_blocks_ready_buy_submit -v`

Expected: all pass without signer/network calls.

**Acceptance criteria:** All USD limits convert once, round down, stay immutable, and stop entries at exact boundaries. UI shows reference and policy version but cannot raise caps during a session.

**Safety/performance invariants:** Decimal arithmetic, fail closed, no auto restart/replenishment/cap increase, protective exit remains guarded.

**Rollback point:** Disable pilot-session creation; existing stricter live caps continue to block entries.

**Dependencies / independent mergeability:** Depends on Task 3 strategy identity; independent of grading/UI workload.

**Commit:** `git commit -m "feat: enforce immutable micro-pilot risk caps"`

---

### Task 11: Authentication, TOTP, Backup, Restore, Signer, and Recovery Rehearsal

**Files:**
- Create: `tests/test_production_gate_rehearsal.py`
- Create: `scripts/rehearse-production-gates.ps1`
- Modify: `backend/app/auth.py`
- Modify: `backend/app/core/hot_wallet.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`
- Modify: `docs/manual/11-operations-and-recovery.md`
- Modify: `docs/manual/16-evidence-campaign.md`

**Existing APIs and patterns to reuse:** bearer-only REST auth, `AuthManager` TOTP, `HotWalletVault` fail-closed lifecycle, local signer-daemon status contract, atomic restore tests, backup/restore history, startup disarm, source-loss/kill-switch/reconciliation/readiness reports.

**Interfaces:**
- Produces: `ProductionGateRehearsal.evaluate(evidence) -> RehearsalReport` and a PowerShell harness with `-FixtureOnly` default and a separate unavailable-by-default `-PhysicalWindowAuthorized` switch.
- Consumes: actual evidence IDs only when later supplied; automated tests use explicitly ineligible fixture evidence.

- [ ] **Step 1: Write failing tests** for persistent password/TOTP restart, bearer-only auth, wallet/signer match, signer rotation/loss invalidation, source-loss entry block/protective preparation, kill switch, fresh backup, restore preview/smoke/schema match, restart recovery, unresolved audit/ledger debt, tailnet/public exposure flags, notification disclosure, and `image-size` risk-acceptance expiry.

```python
def test_fixture_rehearsal_cannot_qualify_production_gate(self) -> None:
    report = ProductionGateRehearsal.evaluate({"fixture_only": True, "totp": "pass", "restore": "pass"})
    self.assertFalse(report.ready)
    self.assertIn("physical_rehearsal_required", report.blockers)
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_production_gate_rehearsal tests.test_restore_atomic tests.test_hot_wallet tests.test_signer_daemon -v`

Expected: rehearsal contract missing while existing suites remain green.

- [ ] **Step 3: Implement fail-closed rehearsal aggregation and script.** Default script runs local/temp-DB checks only and prints physical steps as `DEFERRED`; it must refuse physical mode unless the operator supplies a fresh authorization record and `LIVE_TRADING_ENABLED` remains false for non-live drills. Do not import, unlock, clear, or invoke a wallet/signer in automated mode.
- [ ] **Step 4: Run GREEN.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_production_gate_rehearsal tests.test_restore_atomic tests.test_hot_wallet tests.test_signer_daemon -v`

Expected: all pass; physical deployment rehearsal remains deferred.

**Acceptance criteria:** Machine checks enumerate every production gate and distinguish fixture/local proof from actual deployment evidence. Notification limitations and build-time risk acceptance are explicit.

**Safety/performance invariants:** Tailnet-only requirement; no secret export; restore is atomic; signer loss disarms/blocks; no shared DB/runtime; no physical action without separate authorization.

**Rollback point:** Remove the aggregate rehearsal report/script; existing auth/backup/signer gates remain intact.

**Dependencies / independent mergeability:** Depends on Tasks 1, 9, and 10 reports. Code portion independently mergeable; physical evidence is not.

**Commit:** `git commit -m "feat: aggregate production recovery rehearsal gates"`

---

### Task 12: Separately Authorized Manual-Live Proof

**Files:**
- Create: `tests/test_manual_live_proof.py`
- Create: `docs/manual/17-manual-live-proof.md`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/pages/DataPage.tsx`

**Existing APIs and patterns to reuse:** live request/review audit-only boundary, fresh quote, simulation/preflight, local signer selection, confirm/reconcile, ledger, manual-live proof qualification and invalidation, incident export.

**Interfaces:**
- Produces: `ManualLiveProof.qualify(audits, ledger, signer_identity, authorization) -> ProofReport` and authenticated read/export endpoints. No endpoint auto-executes the proof.
- Consumes: one separately authorized $2-$5 round trip recorded through existing live paths.

- [ ] **Step 1: Write failing tests** for exact wallet/signer identity, one buy plus actual sell/protective-exit, $2-$5 bounds, fresh authorization, confirmed signatures, complete reconciliation/fees/PnL, export, and invalidation on errors, mismatch, unknown/unconfirmed transaction, manual DB repair, or review debt.

```python
def test_manual_proof_is_invalidated_by_manual_database_repair(self) -> None:
    report = ManualLiveProof.qualify(AUDITS, ledger(with_manual_repair=True), SIGNER, AUTH)
    self.assertFalse(report.qualified)
    self.assertIn("manual_database_repair", report.blockers)
```

- [ ] **Step 2: Run RED without a runtime or signer.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_manual_live_proof -v`

Expected: missing proof type.

- [ ] **Step 3: Implement qualification/reporting only and write the runbook.** The runbook begins with a hard stop requiring fresh operator authorization, actual deployment gates, selected wallet/signer, and `LIVE_TRADING_ENABLED=true` only inside that later window. It records commands to capture quote/simulation/buy/confirm/reconcile/sell/confirm/reconcile/export, but implementation execution stops before them.
- [ ] **Step 4: Run GREEN on fixtures only.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_manual_live_proof -v`

Expected: all qualification/invalidation tests pass; report remains `DEFERRED` without physical evidence.

**Acceptance criteria:** Software can qualify or invalidate authoritative evidence but cannot manufacture it or start the proof. Actual manual-live proof requires a new user authorization and coordination window.

**Safety/performance invariants:** No wallet creation/funding, signer unlock, arm, acknowledgement, or transaction in this task; exact wallet/signer match; fail closed on any debt.

**Rollback point:** Remove qualification report/runbook; full sniper gate remains blocked by missing proof.

**Dependencies / independent mergeability:** Depends on Tasks 10-11. Qualification code mergeable; physical evidence explicitly not mergeable as code.

**Commit:** `git commit -m "feat: qualify separately authorized manual live proof"`

---

### Task 13: Separately Authorized Attended Autonomous Pilot

**Files:**
- Create: `tests/test_autonomous_pilot.py`
- Create: `docs/manual/18-attended-autonomous-pilot.md`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/pages/MonitorPage.tsx`

**Existing APIs and patterns to reuse:** `full_sniper_gate`, pilot-readiness, `run_live_autonomy`, guarded intents/exits, kill switch/disarm, unresolved-audit recovery, session reports, Task 10 policy and Task 12 proof.

**Interfaces:**
- Produces: `AutonomousPilotGate.open_window(authorization, readiness_snapshot, policy, manual_proof) -> PilotWindow`; `PilotStopEvaluator.evaluate(event, state) -> StopDecision`.
- Consumes: fresh exact-wallet/signer readiness and a separately authorized attended window.

- [ ] **Step 1: Write failing tests** for fresh full/pilot gates, exact wallet/signer/manual proof, window expiry, attended marker, source/signer/identity/quote/simulation/preflight/cap/loss/drawdown/consecutive-loss/audit/ledger/backup/kill stops, guarded protective exit, no auto restart, and mandatory end kill/disarm/reconciliation.

```python
def test_source_conflict_stops_new_entries_without_bypassing_guarded_exit(self) -> None:
    decision = PilotStopEvaluator.evaluate(source_conflict_event(), OPEN_PILOT)
    self.assertTrue(decision.stop_new_entries)
    self.assertEqual(decision.exit_mode, "existing_guarded_exit_only")
```

- [ ] **Step 2: Run RED without live configuration.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_autonomous_pilot -v`

Expected: missing pilot gate/evaluator.

- [ ] **Step 3: Implement gate/stop state machine and runbook; do not open a window.** Opening requires a fresh external authorization ID and actual reports. Any stop closes new-entry authority; end-of-window requires kill switch, backend disarm, accounted open state, and post-run review before another window.
- [ ] **Step 4: Run GREEN on local fixtures.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_autonomous_pilot tests.test_pilot_risk -v`

Expected: all pass; attended autonomous pilot remains `DEFERRED`.

**Acceptance criteria:** The state machine admits only a fresh separately authorized window and stops on every approved condition. No automated test can open a real window.

**Safety/performance invariants:** Attended, bounded, one position, existing guarded exit only, no auto restart/scale/replenishment, kill/disarm at closure.

**Rollback point:** Disable pilot-window creation; manual proof/evidence remain intact and live autonomy remains blocked.

**Dependencies / independent mergeability:** Depends on Tasks 1-12 and is not independently deployable to live use. Code can merge behind a disabled gate.

**Commit:** `git commit -m "feat: gate attended autonomous pilot windows"`

---

### Task 14: Post-Run Review and Scale/Hold/Stop Decision

**Files:**
- Create: `tests/test_post_pilot_review.py`
- Create: `docs/manual/19-post-pilot-decision.md`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/pages/DataPage.tsx`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`

**Existing APIs and patterns to reuse:** `post_run_review_report`, operator/session reports, ledger/audit reconciliation, outcome explanations, evidence-mode separation, authenticated export.

**Interfaces:**
- Produces: `PilotReview.close(window, audits, ledger, grades, performance) -> PostPilotReview` and `record_operator_decision(review_id, decision in {scale, hold, revise, stop}, rationale, authorization_id)`.
- Consumes: one closed pilot window and complete attributable evidence; it cannot alter caps or strategy automatically.

- [ ] **Step 1: Write failing tests** for explained transactions/balances/fees/PnL, drawdown/fills/latency/exits/caps/audits/reconciliation, unresolved-position/debt blockers, $25 freeze, cap-bypass/unexplained-transaction stop, append-only decision, and no automatic scaling.

```python
def test_unexplained_transaction_forces_stop_or_revise_and_blocks_next_pilot(self) -> None:
    review = PilotReview.close(WINDOW, audits=[unexplained_audit()], ledger=LEDGER, grades=[], performance={})
    self.assertFalse(review.clear)
    self.assertIn("unexplained_transaction", review.blockers)
    self.assertTrue(review.next_pilot_blocked)
```

- [ ] **Step 2: Run RED.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_post_pilot_review -v`

Expected: missing review/decision types.

- [ ] **Step 3: Implement additive review closure and explicit decision record.** Scaling requires a later reviewed design and new immutable policy; `scale` here records intent only and cannot change wallet/caps. Any unexplained transaction, cap bypass, unreconciled position, or $25 cumulative loss blocks the next pilot and routes to non-live investigation.
- [ ] **Step 4: Run GREEN and report regressions.**

Run: `& .\.venv\Scripts\python.exe -m unittest tests.test_post_pilot_review tests.test_manual_live_proof tests.test_autonomous_pilot -v`

Expected: all pass.

**Acceptance criteria:** Every live action and balance must be explained before a clear review; the operator records exactly one append-only scale/hold/revise/stop decision; no scaling occurs automatically.

**Safety/performance invariants:** Read/report path only; mode separation; no authority mutation; bounded exports; scale requires a new design review.

**Rollback point:** Keep next pilot blocked and export raw audit/ledger evidence for manual review.

**Dependencies / independent mergeability:** Depends on Tasks 6 and 12-13. Not independently useful before a pilot; safe to merge behind read-only endpoints.

**Commit:** `git commit -m "feat: close pilots with explicit operator decisions"`

---

## Final Verification Matrix

| Gate | Automated evidence | Physical/genuine evidence | Authority required |
|---|---|---|---|
| Exact-main/inventory | `tests.test_evidence_inventory`; clean Git ancestry capture | Current origin fetch/ancestry at execution | No |
| Source acceptance | parser/freshness/conflict/access/storage tests | Funded or replacement accepted trade-price feed; direct Solana comparison; seven-day soak | Credential purchase/configuration separately authorized |
| Strategy | deterministic contract/rejection/fingerprint tests | Operator-reviewed immutable version | No live authority |
| Economics | all-cost, 2x stress, OOS/walk-forward tests | >=100 genuine completed shadows over >=7 days and multiple regimes | Source window separately coordinated |
| Sentinel | verdict/expiry/stale/version/zero-authority tests | Fresh version-matched input snapshots | No |
| Grading/model | queue/revision/redaction/budget/recovery tests | Operator corrections as applicable | Model use separately enabled; disabled by default |
| Candidates | immutability/comparison/promotion/session tests | Genuine candidate shadow campaign and operator review | Explicit promotion outside active session |
| Isolation | unit tests + fixture load harness | Deployment-equivalent load rehearsal later | Shared runtime window separately coordinated |
| Pilot risk | Decimal conversion and every cap/stop boundary | Independently observed session-start SOL/USD and equity | No funding authority implied |
| Production operations | auth/TOTP/backup/restore/signer/source-loss/kill/restart fixture tests | Actual tailnet deployment and recovery rehearsals | Physical window separately authorized |
| Manual-live | qualification/invalidation tests | One clean $2-$5 buy/exit round trip | Fresh explicit manual-live authorization |
| Autonomous pilot | window/stop/closure tests | One attended bounded autonomous session | Fresh explicit autonomous authorization |
| Post-run | reconciliation/decision tests | Clear actual audit/ledger/post-run evidence | Explicit operator scale/hold/revise/stop decision |

### Focused package gate

Run after each task only the commands listed in that task. Before integration—but only in a separately authorized verifier window—run:

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -q
Push-Location frontend
npm run check:polling
npm run check:execution-readiness
npm run check:critical-projections
npm run build
Pop-Location
& .\scripts\check-doc-links.ps1
```

Expected: all backend tests and frontend checks/build pass; docs links pass; no live sender, wallet, signer, shared DB, or source credential is used.

### Canonical release gate (deferred)

`& .\scripts\verify.ps1` remains the canonical cross-cutting gate, but it includes mobile work and must not be run until a separately authorized, coordinated full-verifier window. Passing it does not satisfy genuine source, shadow, production rehearsal, manual-live, autonomous-live, or profitability evidence.

## Proposed Commit and Integration Sequence

1. `feat: add fail-closed evidence inventory`
2. `feat: persist genuine source evidence`
3. `feat: add immutable sniper strategy contract`
4. `feat: validate all-cost shadow economics`
5. `feat: add zero-authority market sentinel`
6. `feat: add durable deterministic trade grading`
7. `feat: add bounded redacted grade classification` (optional; may be omitted from first release)
8. `feat: gate immutable strategy candidates`
9. `feat: isolate and shed noncritical workloads`
10. `feat: enforce immutable micro-pilot risk caps`
11. `feat: aggregate production recovery rehearsal gates`
12. `feat: qualify separately authorized manual live proof`
13. `feat: gate attended autonomous pilot windows`
14. `feat: close pilots with explicit operator decisions`

Integrate Tasks 1-4 first as the evidence spine; Tasks 5-8 as read-only/async intelligence; Task 9 before enabling any background consumer; Tasks 10-11 as launch safety; Tasks 12-14 behind disabled gates. A normal PR per coherent package is preferred; stack only genuine dependencies (2→3→4, 6→8, 10→11→12→13→14). Never rebase, merge, push, or open PRs without separate authorization.

## Explicitly Deferred Live and Physical Evidence

- Purchase/configuration of funded PumpPortal or replacement source access.
- Genuine accepted trade-price observations, direct-chain comparisons, and seven-day source soak.
- One hundred completed version-matched shadow comparisons across multiple regimes and their positive all-cost/OOS/stress result.
- Deployment-equivalent shared-runtime performance rehearsal.
- Tailnet/auth/TOTP, selected wallet/signer, signer loss/rotation, backup/restore/restart/source-loss/kill-switch/reconciliation physical drills.
- Wallet creation or funding; signer import/unlock/invocation; live enablement, acknowledgement, arming, submission, or approval.
- Manual-live $2-$5 round trip.
- Attended autonomous pilot.
- Real post-run scale/hold/revise/stop decision.

These remain blockers until authoritative evidence is captured. Fixtures, tests, replays, simulated prices, or prose cannot satisfy them.

## Plan Self-Review

- Spec coverage: all 14 requested phases, approved thresholds, live boundaries, sentinel/grader/candidate authority separation, load-shedding order, final verification, integration sequence, deferred evidence, and execution prompt are mapped above.
- Placeholder scan: no deferred implementation markers or unspecified error-handling/test steps remain.
- Type consistency: strategy identity flows from `SniperStrategyVersion` through accepted observations, shadows, sentinel inputs, grades, candidates, pilot policy, proof, pilot window, and post-run review; evidence modes remain distinct throughout.
- Scope check: each task ends in an independently testable deliverable and rollback point. Tasks 12-14 add qualification/state-machine/reporting code only; their physical evidence is deliberately outside implementation authority.

## Next Execution Prompt

```text
Execute C:\Users\Ari Rosner\Projects\CryptoARC\.worktrees\evidence-gated-autonomous-sniper-design\docs\superpowers\plans\2026-08-10-evidence-gated-autonomous-sniper.md task-by-task using the executing-plans, test-driven-development, and verification-before-completion skills. Do all work directly: do not use or spawn subagents. Start with read-only Git/worktree/status and origin/main ancestry checks, create a fresh isolated implementation worktree, preserve unrelated changes, and stop if write ownership is ambiguous. Keep LIVE_TRADING_ENABLED=false. Do not create/fund wallets, configure funded source credentials, unlock/invoke signers, start shared runtimes/databases, traverse live-network transaction paths, run full/mobile gates, merge/rebase/push/open a PR, or fabricate evidence without separate authorization. Run only each task's focused RED/GREEN checks, commit each accepted task separately, and stop for review after Task 1.
```
