# Task 3 Report: Resilient Mobile Client, Atomic Session, And Offline Snapshot

## Status

Complete and committed on `mobile/operator-command-center`.

- Commit: `26f5452` (`Harden mobile session and realtime state`)
- Focused Task 3 plus unchanged legacy recovery tests: 40/40 passed.
- Full mobile verifier: 50/50 tests passed, production audit found 0 vulnerabilities, Expo Doctor passed 20/20, and Android export succeeded.
- Final staged and unstaged diff checks passed.
- No backend, shared runtime, `tests/test_scripts.py`, or out-of-scope source was changed.

## Exact Files

Modified:

- `mobile/app/_layout.tsx`
- `mobile/package.json`
- `mobile/package-lock.json`
- `mobile/src/api.ts`
- `mobile/src/MobileSession.tsx`

Created:

- `mobile/src/core/__tests__/client.test.ts`
- `mobile/src/core/__tests__/sessionStorage.test.ts`
- `mobile/src/core/__tests__/realtime.test.ts`
- `mobile/src/core/__tests__/snapshot.test.ts`
- `mobile/src/core/api/client.ts`
- `mobile/src/core/api/errors.ts`
- `mobile/src/core/api/queryClient.ts`
- `mobile/src/core/connectivity/ConnectionProvider.tsx`
- `mobile/src/core/connectivity/realtime.ts`
- `mobile/src/core/connectivity/types.ts`
- `mobile/src/core/session/SessionProvider.tsx`
- `mobile/src/core/session/storage.ts`
- `mobile/src/core/session/types.ts`
- `mobile/src/core/settings/settingsStore.ts`
- `mobile/src/core/storage/snapshot.ts`

Report:

- `.superpowers/sdd/task-3-report.md`

No `pnpm-lock.yaml` was introduced.

## RED Evidence

All four required focused suites were written before production implementation.

The first literal `npm test -- --runTestsByPath ...` attempt could not start because `npm` was absent from `PATH`. A fallback `pnpm` attempt was not accepted as RED evidence because it tried to convert the npm-managed install and was blocked from the registry. The npm-managed dependencies were restored with the approved exact npm shim using `npm ci`; `package-lock.json` remained consistent.

The valid RED run used the resolved Node runtime to invoke the repository's installed Jest:

```powershell
& 'C:\Users\Ari Rosner\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' 'node_modules\jest\bin\jest.js' --runInBand --runTestsByPath src/core/__tests__/client.test.ts src/core/__tests__/sessionStorage.test.ts src/core/__tests__/realtime.test.ts src/core/__tests__/snapshot.test.ts
```

Result: 4/4 suites failed for the expected missing production modules:

- `../api/errors`
- `../session/storage`
- `../connectivity/realtime`
- `../storage/snapshot`

Three additional focused RED/GREEN cycles were recorded during the security audit:

- A later realtime delta incorrectly cleared `requiresSnapshot`; the new regression failed with `requiresSnapshot: false`, then passed after making snapshot-required state terminal until a full snapshot reset.
- An HTTP 500 financial action error was incorrectly `retryable: true`; the new regression failed, then passed after forcing every dispatched action error to non-retryable.
- A legitimate crypto read model field named `token` was incorrectly rejected as a credential; the regression failed, then passed after narrowing prohibited snapshot fields to credential-specific names such as `access_token`, `session_token`, seed, key, password, and signature fields.

## Implementation And Compatibility Decisions

- `MobileApiError` provides typed categories and status/action-receipt metadata.
- `mobileGet()` performs one transport attempt and returns retryable connection/server metadata for TanStack Query to govern safe read retries.
- `mobileAction()` requires a non-empty idempotency key, sends `Idempotency-Key`, performs exactly one request, never queues, marks lost responses `ambiguous_outcome`, and exposes every action failure as `retryable: false`.
- TanStack Query mutations have `retry: false`; read retries are bounded to retryable typed errors.
- The v2 session is one `cryptoarc.mobile.session.v2` SecureStore record. Migration writes and re-reads the v2 record before deleting any legacy key. Failed verification restores the previous v2 record or removes the unverified new write. Partial legacy cleanup leaves the verified v2 record recoverable and retries cleanup on remount.
- `SessionProvider` owns the app session, lock lifecycle, and atomic replacement/clear behavior.
- `MobileSession.tsx` remains the Task 8 compatibility boundary. The app path maps the new session into the existing cockpit/feed/action contract; rendering the exported provider without the new outer provider retains the legacy recovery implementation used by unchanged tests.
- `expo-crypto@~57.0.1` was added with Expo-compatible npm installation semantics.
- The SQLCipher key is generated once from 32 `expo-crypto` random bytes, stored only in SecureStore as validated hex, and never derived from a token or device identifier.
- `PRAGMA key` is the first database command immediately after `openDatabaseAsync`, before table/schema or data access.
- Snapshot persistence accepts only schema-versioned, server-verified, JSON-safe read models and rejects credential/seed/key/signature-bearing fields. It contains no action queue.
- The realtime reducer fails closed on sequence gaps, schema mismatch, revocation, invalid envelopes, and clock drift over 30 seconds.
- Reconnect uses capped full jitter at 1s, 2s, 4s, 8s, 16s, and 30s. The client owns one socket, cancels pending reconnects on cleanup, does not reconnect policy-closed/revoked sessions, and invalidates specific or all mobile queries as appropriate.
- `ConnectionProvider` wires NetInfo, AppState, polling invalidation fallback, and realtime state. UI changes were limited to provider composition.

## Exact Verification Commands And Results

Dependency addition:

```powershell
& 'C:\Users\Ari Rosner\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.18.0-win-x64\npx.cmd' expo install 'expo-crypto@~57.0.1' --npm
```

Result: installed `expo-crypto` 57.0.1 and updated only `mobile/package.json` and `mobile/package-lock.json`.

Final focused typecheck:

```powershell
& 'C:\Users\Ari Rosner\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' 'node_modules\typescript\bin\tsc' --noEmit
```

Result: exit 0.

Final focused tests:

```powershell
& 'C:\Users\Ari Rosner\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' 'node_modules\jest\bin\jest.js' --runInBand --runTestsByPath src/core/__tests__/client.test.ts src/core/__tests__/sessionStorage.test.ts src/core/__tests__/realtime.test.ts src/core/__tests__/snapshot.test.ts src/__tests__/MobileSession.test.tsx
```

Result: 5 suites passed, 40 tests passed, 0 failed.

Full mobile verifier:

```powershell
$env:CRYPTOARC_NPM='C:\Users\Ari Rosner\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.18.0-win-x64\npm.cmd'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-mobile.ps1
```

Result:

- TypeScript passed.
- 10 suites passed, 50 tests passed, 0 failed.
- `npm audit --omit=dev --audit-level=high`: 0 vulnerabilities.
- Expo Doctor: 20/20 checks passed.
- Android Metro export: succeeded, 3,511 modules bundled.

Diff and scope checks:

```powershell
git diff --check
git status --short
git diff --name-only
git ls-files --others --exclude-standard
git diff --cached --check
git diff --cached --name-status
```

Result: no whitespace errors; only the 20 committed Task 3/dependency files were staged; no out-of-scope files or pnpm lock were present.

Commit:

```powershell
git commit -m "Harden mobile session and realtime state"
```

Result: `26f5452`.

## Concerns And Remaining Verification

- The current backend `/ws/mobile` still emits the legacy cockpit payload rather than the new sequence-aware envelope. The new client intentionally reports compatibility/freshness failure and invalidates queries, while the compatibility adapter keeps REST polling operational. Backend envelope delivery remains a later coordinated backend task; no backend file was changed here.
- Metro Android export proves JavaScript bundling, not native SQLCipher operation. The configured SQLCipher plugin and immediate-key ordering still need confirmation in the final EAS/internal Android artifact.
- No shared runtime/database or full repository verifier was invoked, by Task 3 constraint. The required full mobile verifier passed.

---

# Task 3 Fix Report: Review Rejection Repair

## Status

All Important and Minor review findings were repaired with regression-first tests.
The approved backend change is limited to the mobile WebSocket-ticket endpoint,
mobile service ticket store, `/ws/mobile` consumer, and focused mobile API test.

## RED Evidence

The first focused mobile RED run failed 13 tests for the expected missing behavior:

- no durable session control/tombstone existed after clear;
- failed replacement-control restore/delete did not quarantine credentials;
- an uncommitted first-save slot could be bootstrapped after verification failure;
- duplicate and out-of-order realtime envelopes invalidated queries;
- `token_revoked` did not close or permanently stop the realtime client;
- action, command, queue, idempotency, ambiguous `token`, and credential fields
  were accepted by the generic snapshot validator.

The backend ticket regression failed at the missing endpoint:

```text
AssertionError: 404 != 401
```

After ticket transport existed, the real provider-stack RED run mounted
`SessionProvider -> ConnectionProvider -> MobileSessionProvider` and failed all
six lifecycle assertions for the intended reasons:

- a pairing claim resolving after clear installed the new token;
- a feed response resolving after clear repopulated the feed;
- authentication resolving after clear returned `true`;
- an old-session guarded action dispatched after replacement;
- an action response resolving after clear repopulated the cockpit;
- realtime revocation left the persisted token available for foreground reuse.

A final provider-boundary RED test proved that failed rollback restore left the
old token in memory even though storage had committed a tombstone.

## Fixes

- Added a verified generation control record and two credential slots. Active
  control records point to exactly one verified slot; credential-free tombstones
  remain authoritative after clear even when slot or legacy cleanup is
  interrupted.
- Replacement writes use the inactive slot, verify it, then commit the control
  pointer. Failed control rollback is verified; restore/delete failure commits a
  tombstone and raises `SecureSessionRollbackError`. The provider quarantines
  memory on that error.
- Session persistence mutations are serialized. A synchronous generation
  authority invalidates pairing, feed, unlock, cockpit, and guarded-action work
  before any late result can dispatch or publish.
- Realtime revocation permanently stops the client, cancels reconnect, closes
  the socket, refuses future `connect()`, and immediately quarantines the
  provider session before durable clear.
- Added `POST /api/mobile/ws-ticket`. Bearer authorization remains in the
  header. The service issues a cryptographically random ticket scoped to
  `mobile:monitor`, hashes it before bounded in-memory storage, binds it to the
  device, expires it after 30 seconds, and atomically removes it before current
  device/scope/revocation validation.
- `/ws/mobile` accepts only `ticket`, consumes it before `accept()`, and rejects
  expired, reused, revoked-device, missing, and legacy long-token query
  credentials.
- The mobile client requests a ticket immediately before connecting and puts
  only the one-time ticket in the WebSocket URL. The legacy provider no longer
  opens a token-query WebSocket; REST cockpit polling remains available.
- Replaced the generic snapshot object validator with discriminated version-1
  read-model DTOs for cockpit, portfolio, positions, trades, wallet, alerts,
  and feed. Every object has exact allowlisted fields. Public assets use
  explicit `assetIdentifier` and `assetMetadata` DTOs; ambiguous `token` and
  action/command/queue/idempotency/credential fields are rejected.
- Duplicate and out-of-order realtime envelopes no longer invalidate queries.

Raw bearer tokens, raw tickets after issuance, SQLCipher keys, and credentials
are not logged or serialized by the new paths.

## Verification

Focused backend mobile suites:

```powershell
$env:PYTHONPATH='backend'
& '..\..\CryptoARC-v2\.venv\Scripts\python.exe' -m unittest tests.test_mobile_api tests.test_mobile_command_center tests.test_mobile_revocation
```

Result: 25 tests passed.

Python compilation:

```powershell
& '..\..\CryptoARC-v2\.venv\Scripts\python.exe' -m py_compile backend\app\mobile\contracts.py backend\app\mobile\service.py backend\app\mobile\router.py backend\app\main.py tests\test_mobile_api.py tests\test_mobile_command_center.py
```

Result: exit 0.

Focused Task 3 and real-provider mobile suites:

```powershell
& 'C:\Users\Ari Rosner\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' 'node_modules\jest\bin\jest.js' --runInBand --runTestsByPath src/core/__tests__/client.test.ts src/core/__tests__/sessionStorage.test.ts src/core/__tests__/realtime.test.ts src/core/__tests__/snapshot.test.ts src/core/__tests__/providerLifecycle.test.tsx src/__tests__/api.test.ts src/__tests__/MobileSession.test.tsx
```

Result: 7 suites passed, 62 tests passed.

TypeScript:

```powershell
& 'C:\Users\Ari Rosner\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' 'node_modules\typescript\bin\tsc' --noEmit
```

Result: exit 0.

The first full mobile verifier attempt was blocked by sandbox access to the
configured `npm.cmd`; the same required command was rerun with approved elevated
execution:

```powershell
$env:CRYPTOARC_NPM='C:\Users\Ari Rosner\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.18.0-win-x64\npm.cmd'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-mobile.ps1
```

Result:

- TypeScript passed.
- 11 suites passed, 71 tests passed.
- Production audit found 0 vulnerabilities.
- Expo Doctor passed 20/20 checks.
- Android export succeeded with 3,511 modules bundled.

`git diff --check`, source-scope inspection, production bearer-query WebSocket
search, and staged diff checks passed. No shared runtime, shared database,
`scripts/verify.ps1`, trading/live/paper logic, runtime scripts, or
`tests/test_scripts.py` was touched or run.

## Remaining Verification

- Metro/Android export still does not prove native SQLCipher operation. The final
  EAS/internal Android artifact must confirm the database is encrypted and
  unreadable without the SecureStore key.
- The backend still sends its legacy cockpit payload immediately after the
  ticket-authenticated WebSocket connects. The modern realtime client continues
  to fail closed on that non-envelope payload while REST polling remains the
  compatibility path; a sequence-aware backend envelope remains future work.
