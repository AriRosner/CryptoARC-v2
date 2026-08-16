# Expo Push Delivery Implementation Plan

> **For implementation:** Execute this plan in the current isolated release worktree using test-driven development. Do not start shared services, use the formal-soak database, or make any live-trading, signing, wallet, or money-movement action.

**Goal:** Deliver minimal, security-scoped CryptoARC mobile alerts through the Expo Push Service, durably reconcile provider receipts, and validate a signed Android build on the connected device.

**Architecture:** Keep `MobileCommandCenterService` as the sole owner of push-token decryption, registration lifecycle checks, payload minimization, and durable delivery claims. Add a small Expo HTTP adapter that returns normalized ticket results without logging tokens or provider bodies. Persist the Expo ticket ID on the existing delivery ledger; periodically reconcile receipt results and revoke the corresponding registration only when Expo reports `DeviceNotRegistered`. `BotState` emits an in-process event callback, while `main.py` schedules bounded background delivery only for warning/danger/error events, so core event persistence never waits on a network call.

**Tech Stack:** Python 3.12, FastAPI, SQLite, `urllib.request`, unittest, Expo Push Service.

---

### Task 1: Add a fail-closed Expo provider boundary

**Files:**
- Create: `backend/app/mobile/expo_push.py`
- Modify: `backend/app/config.py`
- Test: `tests/test_mobile_notifications.py`

**Step 1: Write the failing tests.** Cover an enabled adapter POSTing only the token plus the already-minimal payload to the configured Expo endpoint, accepting exactly one `status=ok` ticket with a non-empty ticket ID, rejecting malformed/error/multi-ticket responses generically, and never including a token or provider response text in raised errors.

**Step 2: Run the focused test file and confirm RED.**

Run: `$env:PYTHONPATH='backend'; & 'C:\Users\Ari Rosner\Projects\CryptoARC\CryptoARC-v2\.venv\Scripts\python.exe' -m unittest tests.test_mobile_notifications -v`

**Step 3: Implement the smallest adapter.** Add explicit `MOBILE_EXPO_PUSH_ENABLED` and bounded timeout settings while pinning delivery to Expo's official HTTPS endpoint. When disabled or misconfigured, `main.py` must inject no sender. Use JSON `POST` to Expo; normalize a successful ticket to `{"status": "sent", "ticket_id": "..."}`. Do not log request bodies, tokens, ticket bodies, or HTTP exception content.

**Step 4: Run the focused tests and confirm GREEN.**

### Task 2: Make the delivery ledger receipt-aware

**Files:**
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/mobile/service.py`
- Test: `tests/test_mobile_notifications.py`

**Step 1: Write failing storage/service tests.** Cover storing a ticket ID only when the active attempt completes as sent; stale attempt updates cannot overwrite a newer attempt; pending receipt tickets can be loaded in bounded batches; and a receipt result cannot expose a raw push token.

**Step 2: Run the focused tests and confirm RED.**

**Step 3: Implement the smallest migration and methods.** Extend `mobile_notification_deliveries` compatibly with provider ticket and receipt status/timestamps. Keep the existing `(event_id, device_id, channel)` deduplication and lease semantics. Persist no token plaintext and no provider body/error text.

**Step 4: Update service handling.** A normalized provider ticket is required for `sent`; persist it atomically with the active attempt. Existing mock senders returning only `{"status": "sent"}` remain supported for unit-level delivery behavior but produce no receipt work.

**Step 5: Run focused tests and confirm GREEN.**

### Task 3: Reconcile Expo receipts and revoke invalid registrations

**Files:**
- Modify: `backend/app/mobile/expo_push.py`
- Modify: `backend/app/mobile/service.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_mobile_notifications.py`

**Step 1: Write failing tests.** Cover a receipt request containing at most the bounded ticket batch; receipt `ok` marking delivery confirmed; a missing receipt remaining pending without a token leak; terminal provider errors ending receipt polling; and `DeviceNotRegistered` revoking only the registration linked to that ticket while recording the invalidated outcome.

**Step 2: Run the focused tests and confirm RED.**

**Step 3: Implement the adapter and periodic task.** Expo receipt polling uses its documented receipt endpoint. `main.py` runs it on a conservative periodic background task only when Expo delivery is enabled, tracks/cancels it with the existing app lifespan tasks, and contains failures so it cannot stop the bot. No automatic re-send based solely on receipt state.

**Step 4: Run focused tests and confirm GREEN.**

### Task 4: Bridge persisted alerts to push without blocking core state

**Files:**
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_mobile_notifications.py`
- Test: `tests/test_mobile_command_center.py`

**Step 1: Write failing tests.** Verify `BotState.add_event` invokes an optional callback after durable event persistence; only warning/danger/error events schedule mobile delivery; a failing delivery task does not alter event persistence or create recursive push events; and disabled Expo configuration leaves the path unavailable.

**Step 2: Run focused tests and confirm RED.**

**Step 3: Implement the smallest bridge.** Add an optional event callback to state (default `None`). Register an async-safe scheduler in `main.py` after mobile service construction; it dispatches `deliver_push_event` with `asyncio.to_thread`, bounds concurrent tasks, and only records sanitized operational logging. Do not change the paper-only or live-execution safety boundary.

**Step 4: Run focused tests and confirm GREEN.**

### Task 5: Update diagnostics and operator documentation

**Files:**
- Modify: `backend/app/mobile/service.py`
- Modify: `docs/MOBILE_COCKPIT.md`
- Modify: `docs/manual/15-mobile-operator-command-center.md`
- Test: `tests/test_mobile_notifications.py`

**Step 1: Write failing diagnostics tests.** Assert that an active token is not reported healthy while provider delivery is unavailable, and that diagnostics distinguishes configured delivery from receipt-confirmed delivery without exposing token/ticket identifiers.

**Step 2: Implement minimal status data and documentation.** Document required backend environment configuration, Expo/EAS credential ownership, Android notification permission/channel behavior, receipt timing, invalid-token handling, and the signed-device acceptance steps. Keep secrets out of examples and logs.

**Step 3: Run focused suites.**

Run: `$env:PYTHONPATH='backend'; & 'C:\Users\Ari Rosner\Projects\CryptoARC\CryptoARC-v2\.venv\Scripts\python.exe' -m unittest tests.test_mobile_notifications tests.test_mobile_command_center tests.test_mobile_api tests.test_mobile_release_contract -v`

### Task 6: Verify, package, and test the connected phone

**Files:**
- Modify if needed: `mobile/` build metadata only after the backend path is proven
- Evidence: release handoff/documentation

**Step 1: Run repository-local mobile verification.**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-mobile.ps1`

**Step 2: Build a signed internal Android APK through the already-authorized project credentials.** Confirm the active EAS account and signing provenance without printing credentials. Do not use Expo Go, which cannot prove the release notification configuration.

**Step 3: Install only the newly-built signed artifact over the existing app and test the full paired-device path using an isolated, paper-only backend database.** Verify permission grant, registration, a warning/danger test alert, device receipt, foreground/background behavior, safe deep link, acknowledgement, and unregister/revoke behavior. Do not connect to the formal-soak runtime or use any wallet/signer/live-execution endpoint.

**Step 4: Run the full repository verifier only after the formal-soak owner confirms its runtime/database are stopped and audited.**

### Task 7: Commit and hand off

**Files:**
- Commit all implementation, tests, docs, and release evidence together after all authorized gates pass.

**Step 1: Inspect `git diff --check`, status, and test results.**

**Step 2: Commit with an intentional message, push the release branch, and prepare the PR/release handoff.** Do not include generated artifacts, secrets, `.artifacts/`, `.publish/`, or `.runtime-tools/`.
