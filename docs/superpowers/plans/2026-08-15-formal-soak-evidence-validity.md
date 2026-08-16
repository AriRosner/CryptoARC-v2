# Formal Soak Evidence Validity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a clean seven-date formal soak capable of producing internally consistent, source-fresh, multi-regime, independently auditable qualification evidence.

**Architecture:** Classify the market session at quote time from the preceding 60 seconds of direct Solana create notifications, using fixed pre-entry thresholds and persisting the supporting count/window in the audit comparison. Evaluate source eligibility only on the recent valid window while retaining stale-history diagnostics. Build strict shadow audits and economics from the same accepted entry observation, and make deterministic checkpoint exports surface monitor and metric contradictions.

**Tech Stack:** Python 3.11, `unittest`, SQLite, FastAPI state/storage models, PowerShell verification, GitHub Actions.

## Global Constraints

- Paper-only: `LIVE_TRADING_ENABLED=false`; no wallet, signer, simulation, submission, acknowledgement, arming, or live-session calls.
- Regime evidence is deterministic, pre-entry, immutable, and outcome-independent.
- Regime labels are `quiet` for 0-4, `normal` for 5-19, and `surge` for 20+ direct create notifications in the 60 seconds ending at quote time.
- `unknown` or arbitrary regime labels cannot satisfy economic qualification.
- Historical stale observations remain visible but cannot invalidate independent fresh observations.
- Never mutate, relabel, backfill, or reuse `formal-2026-08-15-r1`.

---

### Task 1: Deterministic pre-entry market regimes

**Files:**
- Modify: `backend/app/core/shadow_evaluation.py`
- Modify: `backend/app/core/state.py`
- Test: `tests/test_shadow_evaluation.py`

**Interfaces:**
- Produces: `MarketRegimeClassifier.classify(direct_create_count: int) -> str`
- Persists: `shadow_comparison.regime` and `shadow_comparison.regime_evidence`

- [ ] **Step 1: Write failing tests** proving threshold boundaries, rejection of unsupported labels, and quote-time persistence from only source events received in `[quoted_at-60s, quoted_at]`.
- [ ] **Step 2: Run** `python -m unittest tests.test_shadow_evaluation -v` and confirm failures are caused by the missing classifier/production assignment.
- [ ] **Step 3: Implement** a classifier with fixed boundaries and set the audit comparison fields before any later price/outcome exists:

```python
class MarketRegimeClassifier:
    VALID_REGIMES = frozenset({"quiet", "normal", "surge"})

    @classmethod
    def classify(cls, direct_create_count: int) -> str:
        if direct_create_count < 5:
            return "quiet"
        if direct_create_count < 20:
            return "normal"
        return "surge"
```

- [ ] **Step 4: Make `EconomicValidator` reject any regime outside `VALID_REGIMES`; run the module tests green.**
- [ ] **Step 5: Commit** `fix: persist deterministic pre-entry market regimes`.

### Task 2: Recent-window source eligibility

**Files:**
- Modify: `backend/app/core/state.py`
- Test: `tests/test_core.py`

**Interfaces:**
- `genuine_source_evidence_report(now, limit)` evaluates only timezone-valid observations satisfying `0 <= now-observed_at <= 300s`.
- Historical totals and `stale_or_invalid_time_count` remain reported separately.

- [ ] **Step 1: Write a failing test** with one fresh genuine observation plus one stale genuine observation; require `shadow_eligible=True`, recent count `1`, historical count `2`, and stale count `1`.
- [ ] **Step 2: Run the single test and confirm the current all-row evaluation fails it.**
- [ ] **Step 3: Filter the evaluation input to the recent valid window, preserve historical diagnostics, and keep conflicts/fixtures inside the recent gate.**
- [ ] **Step 4: Run source/core tests green.**
- [ ] **Step 5: Commit** `fix: isolate fresh source evidence from stale history`.

### Task 3: Align audit and economic entry evidence

**Files:**
- Modify: `backend/app/core/state.py`
- Test: `tests/test_shadow_evaluation.py`

**Interfaces:**
- Strict `exit_rules_v2_strict` audit comparisons use the latest accepted, ready, clear, non-fixture, version-matched observation at or before quote time.
- If no accepted entry exists, the comparison remains `missing_entry_price`; `token_current_price` cannot produce an evaluated strict audit.

- [ ] **Step 1: Write a failing regression** reproducing an audit whose token price implies stop loss but accepted entry/path prices remain subthreshold; require the audit to stay pending and no economic record.
- [ ] **Step 2: Run the test red against the current token-price fallback.**
- [ ] **Step 3: Add a shared accepted-entry lookup and use it in both comparison construction and binding.**
- [ ] **Step 4: Run shadow lifecycle tests green.**
- [ ] **Step 5: Commit** `fix: align shadow audit and economic entry evidence`.

### Task 4: Checkpoint anomaly coverage

**Files:**
- Modify: `backend/app/core/soak_evidence.py`
- Test: `tests/test_soak_evidence.py`
- Modify: `docs/manual/16-evidence-campaign.md`

**Interfaces:**
- `build_campaign_evidence(...)` emits deterministic findings for pipeline warnings, source gate/count contradictions, unsupported or single-regime evidence, and economic counter divergence.

- [ ] **Step 1: Write failing tests** for each anomaly using complete monitor-status fixtures.
- [ ] **Step 2: Run tests red.**
- [ ] **Step 3: Implement stable finding IDs and severity ordering without changing the exporter CLI.**
- [ ] **Step 4: Document the new checks and run exporter tests green.**
- [ ] **Step 5: Commit** `fix: surface formal soak evidence contradictions`.

### Task 5: Full verification, independent audit, and reviewed restart

**Files:**
- Create after verification: outer evidence audit and new campaign startup checkpoint; do not add runtime databases to Git.

- [ ] **Step 1: Run focused red/green suites, then `scripts/verify.ps1`; require complete exit `0`.**
- [ ] **Step 2: Run `git diff --check`, security-relevant tests, CodeQL/CI through a pull request, and verify no open review blockers.**
- [ ] **Step 3: Merge only the reviewed commit, fetch exact `origin/main`, and create a new zero-evidence database with a fresh campaign ID and valuation.**
- [ ] **Step 4: Run production-path integration tests proving every regime is reachable from pre-entry counts, then a short live preflight proving a non-unknown regime is persisted, fresh+stale source rows keep the gate ready, strict evaluated records materialize or remain pending after grace, and the exporter reports no unexplained anomalies.**
- [ ] **Step 5: Start the seven-date campaign only after zero-baseline dashboard and natural scheduled-task result `0`; otherwise remain paused.**
- [ ] **Step 6: Perform a second full operational/data-quality audit and record exact commands, counts, rates, identities, safety state, archive plan, and stop date.**
