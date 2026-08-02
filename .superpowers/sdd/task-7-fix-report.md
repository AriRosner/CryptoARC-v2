# Task 7 Review-Fix Report

## Status

Implemented all five Important and four Minor Task 7 review corrections in the
isolated `mobile/operator-command-center` worktree. No shared runtime/database,
live sender, signer, wallet, RPC, Telegram delivery, full-repository verify, or
process-control script was used.

## Root Cause Of The Existing Acknowledgement Failure

The acknowledgement row was correctly owner-scoped and durable. The test saved
`evt_critical_123` before pairing two phones, while each pairing emitted a newer
actionable security event. `GET /api/mobile/alerts` therefore sorted those newer
events ahead of the target, and the test incorrectly asserted against
`alerts[0]`. The test now selects the row by `event_id`; the separate exact-alert
predicate regression proves that ordinary info events cannot be acknowledged.

Baseline reproduction:

```powershell
$env:PYTHONPATH='backend'
& '..\..\CryptoARC-v2\.venv\Scripts\python.exe' -m unittest tests.test_mobile_notifications.MobileNotificationTests.test_acknowledgement_is_owner_scoped_and_idempotent -v
```

Result: expected existing RED, 1 test run, 1 failure at the positional
`alerts[0]["acknowledged"]` assertion.

## Implementation

### Retryable, Attempt-Bound Delivery Claims

- Added additive existing-v11 schema compatibility for `attempt_id` and
  `lease_expires_at` on `mobile_notification_deliveries`.
- Claims use `BEGIN IMMEDIATE`, atomically insert or reclaim `failed` and expired
  `pending` rows, and return an attempt identity.
- Finish updates require the current attempt identity and `pending` state, so a
  stale finisher cannot overwrite a reclaimed attempt.
- Sender success is strict: only `True` or `{"status": "sent"}` counts as sent.
  `False`, unknown results, and exceptions become retryable failures.
- Tests cover exception retry, negative-result retry, stale claim recovery,
  concurrent claimers, and stale finishers.

### Authorization Lifecycle And Cleanup

- Delivery validates device existence, expiry, revocation, and `mobile:alerts`
  scope before claim and again immediately before decrypt/send. Invalid
  destinations are revoked without exposing token plaintext.
- The modern session provider best-effort unregisters the old push destination
  on explicit disconnect and backend/session replacement. Failure remains
  fail-safe and does not prevent local credential removal.
- Tests cover missing, expired, revoked, scope-reduced, and post-claim revoked
  devices plus disconnect/replacement cleanup.

### Rotation Ordering

- Native registration attempts now run through one serialized promise chain.
  A rotation observed while an older request is in flight queues the latest
  token behind it, preventing reverse completion from reactivating stale state.
- Tests defer the old/new registrations, verify no overlap, and assert both
  connectivity and native-token listener cleanup.

### Restore Fail-Closed

- Restore inspection now includes `mobile_push_registrations`,
  `mobile_alert_acknowledgements`, and `mobile_notification_deliveries`.
- Staged restore revokes every restored mobile credential and push registration
  before the database swap. A restored phone must re-pair and re-register.
- Acknowledgement and delivery ledgers remain available for review; tests prove
  table-delta visibility, restored ledger retention, and inactive destinations.

### Truthful Diagnostics

- Backend diagnostics no longer label unobserved tunnel/WebSocket/clock/snapshot
  state healthy or treat operator-event age as snapshot age. Unobserved checks
  are `unavailable` with `observed_at: null`; API and source timestamps carry
  their actual provenance.
- On-device enrichment uses the authenticated API request interval, current
  realtime state, and the verified local snapshot timestamp. Clock drift uses
  the server timestamp against the request midpoint only for round trips at or
  below 10 seconds; otherwise it stays unavailable.
- Displayed and exported diagnostics use the same client observations.

### Minor Contracts

- Push registration trims then accepts only bounded `ExponentPushToken[...]` or
  `ExpoPushToken[...]` values; blank/malformed input returns the same generic,
  non-reflecting 422 response.
- Trade/position notification routes are entity- and scope-validated after
  unlock. Current-generation 401 revokes only that generation; 403/404 are
  quarantined with a stable generic destination-unavailable reason.
- Diagnostic export writes `cryptoarc-mobile-diagnostics.json` and shares it as
  `application/json` through Expo FileSystem/Sharing.
- Alerts listing and acknowledgement share one exact predicate.

## TDD RED And GREEN Evidence

### Backend behavior group

RED command:

```powershell
$env:PYTHONPATH='backend'
& '..\..\CryptoARC-v2\.venv\Scripts\python.exe' -m unittest tests.test_mobile_notifications -v
```

Expected RED result: 16 tests ran with 10 assertion failures and 2 errors.
Failures demonstrated non-retryable delivery, missing attempt/lease API, four
unauthorized destinations still sending, false-green diagnostics, accepted
malformed tokens, omitted restore tables, and acknowledgement of a non-alert.
One unrelated test cleanup handle and one empty-string privacy assertion were
corrected before production work continued.

GREEN command/result: the same focused module passed 16/16 after the minimal
implementation. Final combined backend verification below passed 47/47 after
the post-claim revalidation regression was added.

### Mobile lifecycle, routing, and rotation group

RED command:

```powershell
& $npm test -- --runTestsByPath src/features/alerts/__tests__/Notifications.test.tsx src/core/__tests__/providerLifecycle.test.tsx
```

Expected RED result: 2 suites failed, 4 tests failed and 18 passed. The failures
showed navigation before destination validation, no 401/403/404 handling,
overlapping reverse-order token registrations, and no cleanup unregister.

GREEN result: 2/2 suites and 22/22 tests passed.

### Diagnostic artifact and provenance group

RED command:

```powershell
& $npm test -- --runTestsByPath src/features/diagnostics/__tests__/Diagnostics.test.tsx
```

Expected RED result: suite failed because the typed artifact and client
observation modules did not exist.

GREEN result: 1/1 suite and 7/7 tests passed, covering the stable filename/MIME,
real snapshot freshness, connected states, bounded clock drift, and stale or
disconnected non-green states.

### Type contract iteration

`npm run typecheck` first found two narrow inferred-literal errors in the new
freshness value. After explicitly typing it as the diagnostics freshness
contract, TypeScript passed. No runtime behavior was changed by that correction.

## Dependency Compatibility

Used only Node 24 npm and the local Expo CLI. No pnpm command was run.

```powershell
& $npm ci
& $node node_modules\expo\bin\cli install expo-sharing expo-file-system --npm
& $node node_modules\expo\bin\cli install --fix --npm
& $node node_modules\expo\bin\cli install 'expo-constants@~57.0.8' 'jest-expo@~57.0.3' --npm
& $npm install --package-lock-only
```

Final compatible versions: Expo `57.0.9`, Expo Constants `57.0.8`, Expo
Notifications `57.0.8`, Expo Router `57.0.9`, React Native `0.86.2`, Reanimated
`4.5.1`, Worklets `0.10.1`, Jest Expo `57.0.3`, Expo FileSystem `57.0.1`, and
Expo Sharing `57.0.8`. React remains `19.2.3`. Expo's generated `app.json`
sharing plugin was removed because outbound `shareAsync` does not require it.

## Final Verification

Focused backend:

```powershell
$env:PYTHONPATH='backend'
& '..\..\CryptoARC-v2\.venv\Scripts\python.exe' -m unittest tests.test_mobile_notifications tests.test_mobile_command_center -v
```

Result: 47/47 passed.

Focused mobile plus session/deep-link lifecycle:

```powershell
& $npm run typecheck
& $npm test -- --runTestsByPath src/features/alerts/__tests__/Notifications.test.tsx src/features/diagnostics/__tests__/Diagnostics.test.tsx src/core/__tests__/providerLifecycle.test.tsx
```

Result: TypeScript passed; 3/3 suites and 29/29 tests passed.

Full isolated gate:

```powershell
$env:CRYPTOARC_NPM=$npm
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-mobile.ps1
```

Result: TypeScript passed; 21/21 suites and 169/169 tests passed; production
audit found 0 vulnerabilities; Expo Doctor passed 20/20; Android Metro export
completed with 4,555 modules and wrote `dist-android`; script exited 0.

```powershell
git diff --check
```

Result: exit 0. Git emitted only the repository's existing LF-to-CRLF working
copy notices.

## Files

- Backend: `backend/app/core/storage.py`, `backend/app/core/state.py`,
  `backend/app/mobile/contracts.py`, `backend/app/mobile/router.py`,
  `backend/app/mobile/service.py`, `tests/test_mobile_notifications.py`.
- Mobile lifecycle/alerts: `mobile/src/core/session/SessionProvider.tsx`,
  `mobile/src/core/notifications/notifications.ts`,
  `mobile/src/core/__tests__/providerLifecycle.test.tsx`,
  `mobile/src/features/alerts/api.ts`, and alert tests.
- Diagnostics: screen/API/types/tests plus new `artifact.ts` and
  `observations.ts`.
- Packaging: `mobile/package.json` and `mobile/package-lock.json`.

## Self-Review

- Rechecked all nine review findings against implementation and focused tests.
- Confirmed the push payload remains exactly `event_id`, `severity`,
  `subsystem`, and `route`; no new payload or plaintext token surfaces exist.
- Confirmed attempt finish is identity-bound and device validation occurs on
  both sides of claim reservation.
- Confirmed restore revocation occurs on the staged database before swap.
- Confirmed `handoff.md`, shared scripts/runtime/database, and unrelated files
  were not edited or staged.

## Residual Concerns / Deferred Evidence

- Live Expo sender integration, provider receipts, event-to-delivery wiring,
  cold-start Android notification handling, and real token rotation remain
  unconnected/unverified.
- Private tunnel, WebSocket transitions, clock behavior, file sharing UX, and
  snapshot provenance were unit-tested but not exercised on a physical phone.
- Metro export is not proof of SQLCipher in a signed EAS/internal artifact.
- Physical accessibility, process-kill, two-process SQLite contention, and real
  signer/wallet/RPC verification remain Task 10 evidence. No such evidence is
  claimed here.
