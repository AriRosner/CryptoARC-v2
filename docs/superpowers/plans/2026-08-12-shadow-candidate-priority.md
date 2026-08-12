# Shadow Candidate Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the existing one-slot PumpPortal paid trade subscription to genuine strategy-qualified paper candidates long enough to collect attributable entry and exit evidence.

**Architecture:** Persist a restart-safe shadow candidate lifecycle in SQLite, defer automatic shadow quoting until a valid entry observation arrives, and let the PumpPortal source poll a narrow preferred-mint callback. The source may preempt ordinary launch tracking but never exceed `max_trade_subscriptions`; existing evidence binding, exit evaluation, and economic qualification remain authoritative.

**Tech Stack:** Python 3.12, FastAPI application state, asyncio/websockets, SQLite migrations, unittest/pytest, PowerShell verification.

## Global Constraints

- Keep `LIVE_TRADING_ENABLED=false`, bot mode `paper`, live execution unavailable, and model grading disabled.
- Never access wallets, signers, simulation, submission, acknowledgement, arming, or live-session endpoints.
- Keep `max_trade_subscriptions=1` for the running campaign; code must honor any configured nonnegative cap and never exceed it.
- Do not change strategy thresholds, the 100-sample gate, the seven-calendar-day gate, version matching, source attribution, or fixture/conflict/access rejection.
- Do not manufacture, infer, backfill, or reclassify entry or exit observations.
- Use the active settings-version snapshot for candidate identity and exit deadlines.
- Implement and benchmark against copied data before changing the running exact-main campaign.

## File Structure

- `backend/app/core/models.py`: define the serializable `ShadowTrackingCandidate` lifecycle record and add candidate-priority fields to `SourceStatus`.
- `backend/app/core/storage.py`: migration 026 and atomic candidate lifecycle queries/updates.
- `backend/app/core/state.py`: register qualified candidates, activate a quote only after accepted entry evidence, expire stale records, release completed records, and expose safe status.
- `backend/app/core/sources.py`: prefer the state-provided candidate mint over the ordinary launch queue while preserving the subscription cap.
- `backend/app/main.py`: wire the preferred-mint callback into the source and expose candidate tracking in health output.
- `tests/test_shadow_candidate_priority.py`: focused state/storage lifecycle tests.
- `tests/test_source_cancellation.py`: asynchronous subscription-preemption, reconnect, cap, and cancellation tests.
- `tests/test_core.py`: update existing automatic-shadow expectations to the entry-first contract.
- `scripts/analyze-shadow-candidate-coverage.py`: read-only before/after coverage and throughput analysis for copied campaign databases.
- `docs/manual/13-api-and-data-reference.md`: document candidate-priority status and deferred shadow creation.

---

### Task 1: Persist the candidate evidence lifecycle

**Files:**
- Modify: `backend/app/core/models.py:604`
- Modify: `backend/app/core/storage.py:73,295-322,1067-1087,1544-1726,4990-5130`
- Create: `tests/test_shadow_candidate_priority.py`

**Interfaces:**
- Produces: `ShadowTrackingCandidate` with states `awaiting_entry`, `tracking_shadow`, `complete`, and `expired`.
- Produces: `Storage.save_shadow_tracking_candidate(candidate)`, `load_shadow_tracking_candidates(active_only=False)`, `load_shadow_tracking_candidate(candidate_id)`, and `transition_shadow_tracking_candidate(...)`.

- [ ] **Step 1: Write failing migration and lifecycle tests**

```python
def test_shadow_candidate_lifecycle_is_restart_safe(self) -> None:
    with TemporaryDirectory() as directory:
        path = str(Path(directory) / "candidate.db")
        storage = Storage(path)
        candidate = ShadowTrackingCandidate(
            candidate_id="shadow_candidate_intent_1",
            intent_id="intent_1",
            mint="MintCandidate111",
            strategy_id="balanced",
            strategy_version="set_current",
            selected_at=NOW,
            deadline_at=NOW + timedelta(seconds=120),
        )
        storage.save_shadow_tracking_candidate(candidate)

        restarted = Storage(path)
        loaded = restarted.load_shadow_tracking_candidate(candidate.candidate_id)

        self.assertEqual(restarted.schema_status()["current_version"], 26)
        self.assertEqual(loaded.state, "awaiting_entry")
        self.assertEqual(loaded.mint, candidate.mint)


def test_candidate_transition_is_compare_and_set(self) -> None:
    storage.save_shadow_tracking_candidate(candidate)

    first = storage.transition_shadow_tracking_candidate(
        candidate.candidate_id,
        expected_state="awaiting_entry",
        state="tracking_shadow",
        audit_id="audit_1",
        deadline_at=NOW + timedelta(seconds=630),
        reason="entry evidence accepted",
    )
    duplicate = storage.transition_shadow_tracking_candidate(
        candidate.candidate_id,
        expected_state="awaiting_entry",
        state="tracking_shadow",
        audit_id="audit_2",
        deadline_at=NOW + timedelta(seconds=630),
        reason="duplicate",
    )

    self.assertTrue(first)
    self.assertFalse(duplicate)
    self.assertEqual(storage.load_shadow_tracking_candidate(candidate.candidate_id).audit_id, "audit_1")
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/test_shadow_candidate_priority.py -v`

Expected: FAIL because `ShadowTrackingCandidate`, schema 26, and lifecycle storage methods do not exist.

- [ ] **Step 3: Add the model and migration**

```python
@dataclass(slots=True)
class ShadowTrackingCandidate:
    candidate_id: str
    intent_id: str
    mint: str
    strategy_id: str
    strategy_version: str
    selected_at: datetime
    deadline_at: datetime
    state: str = "awaiting_entry"
    audit_id: str = ""
    reason: str = "waiting for accepted entry evidence"
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["selected_at"] = self.selected_at.isoformat()
        payload["deadline_at"] = self.deadline_at.isoformat()
        payload["updated_at"] = (self.updated_at or self.selected_at).isoformat()
        return payload
```

Set `Storage.SCHEMA_VERSION = 26`, register migration `026_shadow_tracking_candidates`, and create:

```sql
CREATE TABLE IF NOT EXISTS shadow_tracking_candidates (
    candidate_id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL UNIQUE,
    mint TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    state TEXT NOT NULL,
    selected_at TEXT NOT NULL,
    deadline_at TEXT NOT NULL,
    audit_id TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_tracking_candidate_priority
ON shadow_tracking_candidates(state, selected_at, deadline_at);
```

Implement serialization and a transactionally guarded transition using:

```sql
UPDATE shadow_tracking_candidates
SET state = ?, audit_id = ?, deadline_at = ?, reason = ?, updated_at = ?, payload = ?
WHERE candidate_id = ? AND state = ?;
```

- [ ] **Step 4: Run lifecycle and schema tests and verify GREEN**

Run: `python -m pytest tests/test_shadow_candidate_priority.py tests/test_data_summary_counts.py -v`

Expected: PASS with schema version 26 and compare-and-set behavior.

- [ ] **Step 5: Commit the persistence milestone**

```powershell
git add backend/app/core/models.py backend/app/core/storage.py tests/test_shadow_candidate_priority.py tests/test_data_summary_counts.py
git commit -m "Persist shadow candidate evidence lifecycle"
git push
```

### Task 2: Defer shadow creation until genuine entry evidence

**Files:**
- Modify: `backend/app/core/state.py:2362-2418,6045-6058,8559-8688`
- Modify: `tests/test_shadow_candidate_priority.py`
- Modify: `tests/test_core.py:2557-2767`

**Interfaces:**
- Consumes: candidate storage APIs from Task 1.
- Produces: `BotState.preferred_shadow_trade_mints(now=None) -> list[str]`.
- Produces: `BotState.shadow_candidate_priority_status(now=None) -> dict[str, object]`.
- Produces: private idempotent activation method `_activate_waiting_shadow_candidate(observation)`.

- [ ] **Step 1: Write failing entry-first tests**

```python
def test_promoted_candidate_waits_for_genuine_entry_before_shadow_quote(self) -> None:
    state, token = self.make_promoted_candidate_state()
    calls: list[dict[str, object]] = []
    state._pumpportal_local_transaction = lambda **kwargs: (calls.append(kwargs) or ({"ok": True}, "dHgi", ""))

    intents = state.generate_live_intents("WalletShadow")
    intent = next(item for item in intents if item["mint"] == token.mint)

    self.assertEqual(intent["status"], "open")
    self.assertEqual(intent["audit_id"], "")
    self.assertEqual(calls, [])
    self.assertEqual(state.preferred_shadow_trade_mints(), [token.mint])


def test_first_accepted_entry_creates_exactly_one_shadow_audit(self) -> None:
    state, token, intent = self.make_waiting_candidate()
    observation = self.accepted_observation(state, token.mint)

    state._activate_waiting_shadow_candidate(observation)
    state._activate_waiting_shadow_candidate(observation)

    stored_intent = state.storage.load_live_intent(intent.id)
    candidate = state.storage.load_shadow_tracking_candidate(f"shadow_candidate_{intent.id}")
    bindings = state.storage.load_shadow_market_evidence_bindings(stored_intent.audit_id)
    self.assertEqual(candidate.state, "tracking_shadow")
    self.assertEqual(len([row for row in bindings if row["role"] == "entry"]), 1)
    self.assertEqual(len([a for a in state.storage.load_live_execution_audits(20) if a.mint == token.mint]), 1)
```

Also add rejection cases for wrong mint, wrong strategy version, fixture-only, conflicted, access-blocked, and nonpositive observations.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_shadow_candidate_priority.py tests/test_core.py -k "promoted or candidate or shadow_quote" -v`

Expected: FAIL because candidates still quote immediately and no preferred-mint API exists.

- [ ] **Step 3: Register candidates instead of quoting immediately**

In `generate_live_intents`, preserve existing selection and intent creation, but replace the immediate `quote_live_intent(...)` call with:

```python
self.storage.save_shadow_tracking_candidate(
    ShadowTrackingCandidate(
        candidate_id=f"shadow_candidate_{intent.id}",
        intent_id=intent.id,
        mint=intent.mint,
        strategy_id=self.settings.strategy_profile,
        strategy_version=self.current_settings_version_id,
        selected_at=now,
        deadline_at=now + timedelta(seconds=max(1, int(self.settings.max_token_age_seconds))),
    )
)
entry = self._latest_eligible_candidate_entry(intent.mint, now)
if entry is not None:
    self._activate_waiting_shadow_candidate(entry)
```

`_latest_eligible_candidate_entry` must query accepted observations by exact strategy ID/version and return only ready, non-fixture, conflict-clear, positive observations for the exact mint.

- [ ] **Step 4: Activate idempotently after accepted observation persistence**

After `save_accepted_market_observation(item)` succeeds and existing pending-shadow binding runs, call `_activate_waiting_shadow_candidate(item)`. The method must:

```python
for candidate in self.storage.load_shadow_tracking_candidates(active_only=True):
    if candidate.state != "awaiting_entry" or not self._observation_matches_candidate(observation, candidate):
        continue
    intent = self.storage.load_live_intent(candidate.intent_id)
    if intent is None:
        self.storage.transition_shadow_tracking_candidate(..., state="expired", reason="intent missing")
        continue
    if intent.audit_id:
        audit = self.storage.load_live_execution_audit(intent.audit_id)
    else:
        self.quote_live_intent(
            False,
            intent.id,
            self.settings.live_max_slippage_pct,
            self.settings.live_priority_fee_cap_sol,
            "pump",
            shadow_only=True,
        )
        intent = self.storage.load_live_intent(intent.id)
        audit = self.storage.load_live_execution_audit(intent.audit_id)
    self.storage.transition_shadow_tracking_candidate(
        candidate.candidate_id,
        expected_state="awaiting_entry",
        state="tracking_shadow",
        audit_id=audit.id,
        deadline_at=audit.created_at + timedelta(seconds=self._candidate_tracking_window_seconds(candidate.strategy_version)),
        reason="accepted entry evidence bound",
    )
```

Before quoting, expire candidates whose deadline passed or whose strategy version no longer matches. Redact caught provider exceptions using the existing shadow failure path; leave the candidate awaiting entry until deadline so a transient quote-provider failure does not fabricate success.

- [ ] **Step 5: Release completed candidates and expose preference/status**

When `_persist_economic_shadow_comparison(audit)` returns true, transition its candidate from `tracking_shadow` to `complete`. Implement deterministic preference:

```python
def preferred_shadow_trade_mints(self, now: datetime | None = None) -> list[str]:
    self._expire_shadow_tracking_candidates(now or utc_now())
    active = self.storage.load_shadow_tracking_candidates(active_only=True)
    active.sort(key=lambda item: (0 if item.state == "tracking_shadow" else 1, item.selected_at, item.candidate_id))
    return [active[0].mint] if active else []
```

Status must expose mint prefix only, state, age, queue depth, deadline, completed count, and expiry counts; it must not expose wallet fields, credentials, provider payloads, or full raw transactions.

- [ ] **Step 6: Run state tests and verify GREEN**

Run: `python -m pytest tests/test_shadow_candidate_priority.py tests/test_core.py -k "promoted or candidate or shadow_quote or shadow_comparison" -v`

Expected: PASS; updated old tests assert `open` before entry evidence and `quoted` only after accepted evidence.

- [ ] **Step 7: Commit the entry-first milestone**

```powershell
git add backend/app/core/state.py tests/test_shadow_candidate_priority.py tests/test_core.py
git commit -m "Prioritize genuine shadow entry evidence"
git push
```

### Task 3: Give qualified candidates the existing paid subscription slot

**Files:**
- Modify: `backend/app/core/sources.py:172-364,449-452`
- Modify: `backend/app/main.py:749-802`
- Modify: `backend/app/core/models.py:1012-1045`
- Modify: `tests/test_source_cancellation.py:171-230,481-680`

**Interfaces:**
- Consumes: `preferred_trade_mints: Callable[[], list[str]]` supplied by `BotState.preferred_shadow_trade_mints`.
- Produces: candidate-aware `PumpPortalLaunchSource` that still reports `active_trade_subscriptions <= max_trade_subscriptions`.

- [ ] **Step 1: Write failing asynchronous preemption and cap tests**

```python
async def test_candidate_preempts_ordinary_launch_without_second_subscription(self) -> None:
    preferred: list[str] = []
    source = PumpPortalLaunchSource(
        ws_url="wss://example.invalid",
        max_trade_subscriptions=1,
        preferred_trade_mints=lambda: list(preferred),
        preference_poll_seconds=0.01,
    )
    # Fake websocket captures subscribe/unsubscribe messages and blocks on recv.
    subscription_queue.put_nowait("OrdinaryMint")
    task = asyncio.create_task(source._run_trade_stream(event_queue, status, subscription_queue))
    await subscribed("OrdinaryMint")
    preferred[:] = ["CandidateMint"]
    await subscribed("CandidateMint")

    self.assertIn({"method": "unsubscribeTokenTrade", "keys": ["OrdinaryMint"]}, sent)
    self.assertLessEqual(status.active_trade_subscriptions, 1)
    self.assertEqual(status.trade_subscription_priority, "shadow_candidate")
```

Add tests proving a second candidate does not churn the current preference, reconnect resubscribes only the preferred mint, clearing preference resumes the ordinary queue, and cancellation reaps receive/preference tasks.

- [ ] **Step 2: Run source tests and verify RED**

Run: `python -m pytest tests/test_source_cancellation.py -k "candidate or subscription or reconnect" -v`

Expected: FAIL because the source has no preferred-mint callback or status fields.

- [ ] **Step 3: Add the narrow preferred-mint source contract**

Add these constructor fields:

```python
preferred_trade_mints: Callable[[], list[str]] | None = None
preference_poll_seconds: float = 1.0
```

Add safe status fields:

```python
trade_subscription_priority: str = "ordinary_launch"
preferred_trade_mint_prefix: str = ""
```

Factor subscription replacement into one helper that always unsubscribes before subscribing when the cap is one and updates status only after sends succeed. Preference polling must never call network, state mutation, wallets, or execution code; it only reads the callback result.

- [ ] **Step 4: Integrate preference into the receive loop**

Each loop waits on websocket receive, ordinary queue input when no preferred mint is active, and a bounded preference poll. When the callback returns a mint different from the ordinary active mint, preempt immediately. When it returns the same candidate, do nothing. When it returns no mint, retain the candidate only until state has marked it terminal, then resume the newest queued ordinary launch.

Maintain these invariants after every branch:

```python
assert len(subscribed_lookup) <= max(0, self.max_trade_subscriptions)
status.active_trade_subscriptions = len(subscribed_lookup)
status.preferred_trade_mint_prefix = active_preferred[:8] if active_preferred else ""
status.trade_subscription_priority = "shadow_candidate" if active_preferred else "ordinary_launch"
```

Use normal control flow rather than leaving runtime `assert` as the only cap defense.

- [ ] **Step 5: Wire the callback in main without changing source restart identity**

Extend `make_source(...)` with `preferred_trade_mints=None` and pass:

```python
source = make_source(
    name=state.settings.launch_source,
    launch_interval_seconds=state.settings.launch_interval_seconds,
    pumpportal_ws_url=config.pumpportal_ws_url,
    max_trade_subscriptions=state.settings.max_trade_subscriptions,
    preferred_trade_mints=state.preferred_shadow_trade_mints,
)
```

Do not place callback identity in `source_key`; settings changes remain the only reason to restart the source task.

- [ ] **Step 6: Run source and cancellation tests and verify GREEN**

Run: `python -m pytest tests/test_source_cancellation.py tests/test_core.py -k "source or candidate or cancellation" -v`

Expected: PASS with no leaked asyncio tasks, subscription count never above cap, and candidate preemption observed.

- [ ] **Step 7: Commit the subscription-routing milestone**

```powershell
git add backend/app/core/sources.py backend/app/core/models.py backend/app/main.py tests/test_source_cancellation.py
git commit -m "Route paid trade slot to shadow candidates"
git push
```

### Task 4: Complete lifecycle observability and read-only coverage analysis

**Files:**
- Modify: `backend/app/main.py:1000-1040`
- Modify: `backend/app/core/state.py`
- Create: `scripts/analyze-shadow-candidate-coverage.py`
- Modify: `tests/test_shadow_candidate_priority.py`
- Modify: `docs/manual/13-api-and-data-reference.md:257-263`

**Interfaces:**
- Consumes: candidate lifecycle and source status from Tasks 1-3.
- Produces: `candidate_priority` health block and a read-only JSON coverage analyzer.

- [ ] **Step 1: Write failing status and analyzer tests**

```python
def test_candidate_priority_status_is_redacted_and_counts_terminal_reasons(self) -> None:
    status = state.shadow_candidate_priority_status(now=NOW)
    self.assertEqual(status["configured_subscription_cap"], 1)
    self.assertEqual(status["active_mint_prefix"], "MintCand")
    self.assertNotIn("wallet", json.dumps(status).lower())
    self.assertNotIn("api-key", json.dumps(status).lower())


def test_coverage_analyzer_counts_entry_followup_and_projection(self) -> None:
    report = analyze_database(database_path, strategy_version="set_current", now=NOW)
    self.assertEqual(report["candidates"], 3)
    self.assertEqual(report["entry_covered"], 2)
    self.assertEqual(report["followup_covered"], 1)
    self.assertEqual(report["economic_samples"], 1)
    self.assertGreaterEqual(report["projected_samples_per_day"], 0)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_shadow_candidate_priority.py -k "status or analyzer" -v`

Expected: FAIL because the health block and analyzer do not exist.

- [ ] **Step 3: Add redacted health output**

Add this sibling to the existing `/health/deep` source block:

```python
"candidate_priority": state.shadow_candidate_priority_status(),
```

The status implementation returns:

```python
{
    "state": active.state if active else "idle",
    "active_mint_prefix": active.mint[:8] if active else "",
    "active_age_seconds": max(0, int((now - active.selected_at).total_seconds())) if active else 0,
    "deadline_at": active.deadline_at.isoformat() if active else None,
    "queue_depth": len(nonterminal),
    "awaiting_entry": count("awaiting_entry"),
    "tracking_shadow": count("tracking_shadow"),
    "completed": count("complete"),
    "expired_missing_entry": count_expired("entry"),
    "expired_missing_exit": count_expired("exit"),
    "active_subscriptions": self.source_status.active_trade_subscriptions,
    "configured_subscription_cap": self.settings.max_trade_subscriptions,
    "cap_respected": self.source_status.active_trade_subscriptions <= self.settings.max_trade_subscriptions,
}
```

- [ ] **Step 4: Implement the read-only analyzer**

The script accepts `--database`, optional `--strategy-version`, and `--json`. It opens SQLite in read-only URI mode, never runs migrations, and reports:

- candidate/audit count and observation span;
- attributable entry coverage;
- attributable follow-up coverage;
- completed economic sample count;
- samples per elapsed day and seven-day projection;
- candidate lifecycle counts when schema 26 exists;
- active subscription cap from settings.

If schema 26 is absent, candidate lifecycle counts are `null`; audit/binding coverage still works for the pre-change baseline.

- [ ] **Step 5: Document semantics and safety**

Update the API manual to state that candidate priority reallocates paid scope, does not increase it, and that `awaiting_entry`/`tracking_shadow` are not completed samples. Document that only accepted, attributable, version-matched entry and exit observations qualify.

- [ ] **Step 6: Run tests and verify GREEN**

Run: `python -m pytest tests/test_shadow_candidate_priority.py tests/test_data_summary_counts.py -v`

Expected: PASS; status contains no sensitive fields and analyzer works on pre- and post-migration copies.

- [ ] **Step 7: Commit the observability milestone**

```powershell
git add backend/app/main.py backend/app/core/state.py scripts/analyze-shadow-candidate-coverage.py tests/test_shadow_candidate_priority.py docs/manual/13-api-and-data-reference.md
git commit -m "Report shadow candidate collection coverage"
git push
```

### Task 5: Benchmark copied campaign data and verify the repository

**Files:**
- Modify only if tests identify a defect in Task 1-4 files.
- Create outside Git: `C:\Users\Ari Rosner\Projects\CryptoARC\evidence\2026-08-11\candidate-priority-benchmark\`

**Interfaces:**
- Consumes: read-only analyzer and completed implementation.
- Produces: baseline and post-change benchmark JSON artifacts; no database artifact is committed.

- [ ] **Step 1: Capture a read-only baseline from the running campaign database**

```powershell
$campaignDb = 'C:\Users\Ari Rosner\Projects\CryptoARC\.worktrees\launch-evidence-main-2026-08-11\data\shadow-campaign-2026-08-11.db'
$out = 'C:\Users\Ari Rosner\Projects\CryptoARC\evidence\2026-08-11\candidate-priority-benchmark'
New-Item -ItemType Directory -Force -Path $out | Out-Null
python scripts/analyze-shadow-candidate-coverage.py --database $campaignDb --json | Set-Content -Encoding utf8 (Join-Path $out 'baseline.json')
```

Expected: baseline reports current entry/follow-up/economic conversion without modifying the database.

- [ ] **Step 2: Copy the database and run migration/startup tests only on the copy**

```powershell
$copy = Join-Path $out 'shadow-campaign-copy.db'
Copy-Item -LiteralPath $campaignDb -Destination $copy
$env:CRYPTOARC_DATABASE_PATH = $copy
python -m pytest tests/test_shadow_candidate_priority.py tests/test_source_cancellation.py tests/test_shadow_evaluation.py -v
Remove-Item Env:\CRYPTOARC_DATABASE_PATH
```

Expected: focused suites PASS; the running database remains unchanged.

- [ ] **Step 3: Run the complete backend test suite**

Run: `python -m pytest tests -q`

Expected: all backend tests PASS with zero failures.

- [ ] **Step 4: Run full cross-project verification**

Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

Expected: backend, frontend, and mobile verification phases all PASS. Wait for the final exit code and complete phase output.

- [ ] **Step 5: Review the final diff and safety invariants**

```powershell
git diff origin/main...HEAD --check
git status --short --branch
rg -n "LIVE_TRADING_ENABLED|live_submit|simulate|acknowledge|arm|wallet|signer" backend/app/core/sources.py scripts/analyze-shadow-candidate-coverage.py
```

Expected: clean diff; only explicitly safe references in state validation remain; no new execution call path exists.

- [ ] **Step 6: Commit any test-driven corrections and push**

```powershell
$corrected = git diff --name-only -- backend/app/core/models.py backend/app/core/storage.py backend/app/core/state.py backend/app/core/sources.py backend/app/main.py tests scripts/analyze-shadow-candidate-coverage.py docs/manual/13-api-and-data-reference.md
git add -- $corrected
git commit -m "Harden shadow candidate priority verification"
git push
```

Skip the commit when verification required no corrections.

### Task 6: Pull request, checks, merge, and controlled exact-main rollout

**Files:**
- No planned source edits.
- Update external campaign evidence/status artifacts through existing scripts only.

**Interfaces:**
- Consumes: green branch, copied benchmark, and current hidden campaign.
- Produces: merged main commit and verified hidden paper campaign on that exact commit.

- [ ] **Step 1: Open the pull request with evidence and explicit non-goals**

```powershell
gh pr create --base main --head agent/shadow-candidate-priority --title "Prioritize paid shadow evidence collection" --body-file .git\candidate-priority-pr.md
```

The PR body records root cause, one-slot invariant, test counts, full verification, baseline metrics, and the unchanged economic gates. It states that no wallet, signer, simulation, submission, acknowledgement, arming, or live endpoint was used.

- [ ] **Step 2: Wait for and inspect all GitHub checks**

Run: `$prNumber = gh pr view --json number --jq '.number'; gh pr checks $prNumber --watch --interval 20`

Expected: CI and CodeQL PASS. Then inspect unresolved reviews, secret scanning, and Dependabot state. Fix only regressions caused by this branch, with a failing local reproduction first.

- [ ] **Step 3: Merge only after the branch is green and reviewable**

Run: `gh pr merge $prNumber --squash --delete-branch`

Expected: PR merged to `main`; record the exact merge SHA with `$mergeSha = gh pr view $prNumber --json mergeCommit --jq '.mergeCommit.oid'`.

- [ ] **Step 4: Reconfirm campaign safety before stopping anything**

Verify scheduled task name, hidden execution, database path, backend deep health, current detached SHA, paper mode, `LIVE_TRADING_ENABLED=false`, execution unavailable, model grading disabled, and no active live session. If any identity differs from the known campaign, stop and investigate rather than guessing.

- [ ] **Step 5: Back up campaign evidence and advance exact main**

Use the existing campaign backup/snapshot script against the exact database and status paths. Stop only the hidden scheduled campaign process, verify its PID and worktree path, fetch main, and move the detached campaign worktree forward only when it is clean:

```powershell
git -C 'C:\Users\Ari Rosner\Projects\CryptoARC\.worktrees\launch-evidence-main-2026-08-11' fetch origin
git -C 'C:\Users\Ari Rosner\Projects\CryptoARC\.worktrees\launch-evidence-main-2026-08-11' switch --detach $mergeSha
```

Do not reset, clean, or overwrite a dirty campaign worktree.

- [ ] **Step 6: Restart hidden and verify the new collection path**

Start the existing scheduled task with its hidden configuration. Verify within two monitor cycles:

- exact merge SHA;
- task result 0 and backend deep health ready;
- paper mode and all live prohibitions unchanged;
- source trusted/connected;
- active subscriptions `<= 1`;
- candidate-priority block present and redacted;
- a qualifying candidate enters `awaiting_entry` or `tracking_shadow` when naturally observed;
- no old audit or sample was reclassified.

- [ ] **Step 7: Measure post-change conversion without claiming premature readiness**

After enough natural candidates have occurred to make the comparison meaningful, write `post-change.json` with the analyzer and compare entry coverage, follow-up coverage, economic samples/day, and observed paid message rate against `baseline.json`. Report improvement or regression honestly. Keep the seven-day and 100-sample gates blocked until both are genuinely satisfied.

## Plan Self-Review

- Spec coverage: persistence, deterministic priority, entry-first quoting, exit release, expiry, reconnect, cap enforcement, redacted observability, copied benchmark, full verification, PR, and controlled rollout are each assigned to a task.
- Completeness scan: every implementation and error-handling step is concrete. Runtime PR and merge identifiers are captured by exact commands before use.
- Type consistency: `ShadowTrackingCandidate`, lifecycle states, storage APIs, callback signature, state preference/status APIs, and source status field names are consistent across tasks.
- Scope: the plan changes allocation and evidence timing only. It does not change strategy selection, economic gates, paid subscription count, or live authority.
