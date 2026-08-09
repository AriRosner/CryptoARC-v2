# Mobile Operator Command Center — Final Branch Fix Report

Date: 2026-08-08

Base reviewed: `ffefb854f9bcc44bdfc3c6e679fb2b18684f693f`

Scope: six Important findings in `.superpowers/sdd/final-branch-review.md`

## Safety and isolation

- Work stayed in the isolated `mobile-operator-command-center` worktree. `handoff.md` was preserved and is not staged.
- No shared runtime/database, `start-dev.ps1`, `stop-dev.ps1`, `verify.ps1`, EAS, phone, signer, wallet, RPC, arming, acknowledgement, or transaction path was started.
- `LIVE_TRADING_ENABLED` remains false. No key, seed, token, raw transaction, or readiness bypass was added.

## 1. Atomic one-time pairing

Root cause: `BotState.claim_mobile_pairing` performed a read, validation, device insert, and pairing update as separate database operations. Two independent processes could both validate the same stale unclaimed row and each mint a device/token.

Architecture: `Storage.claim_mobile_pairing_request` owns validation, failed-attempt mutation, conditional claim, and device insertion inside one SQLite `BEGIN IMMEDIATE` transaction. The conditional update is a final CAS. Wrong-code attempt increments commit atomically; insert/CAS failures roll back the claim. `BotState` generates candidate credentials, delegates the atomic mutation, and audits only after success.

TDD evidence:

- RED: a barrier test with two independent `BotState` instances produced two successful claimers on the legacy read-then-write path.
- GREEN: exactly one result is a token/device, one is the preserved claim error, one device exists, scopes/expiry are preserved, and the pairing points at that device.
- RED/GREEN rollback: a duplicate-device insert failure leaves `claimed_at` and `claimed_device_id` empty; the same pairing can then be claimed successfully.
- Existing wrong-code, lockout/reuse, token hashing, requested-scope, expiry, revocation, and audit tests remain green.

Files: `backend/app/core/state.py`, `backend/app/core/storage.py`, `tests/test_mobile_api.py`.

## 2. Realtime contract and recovery

Root cause: `/ws/mobile` sent a raw cockpit object while the client reducer required `MobileRealtimeEnvelope`; the reducer then permanently returned an already-quarantined state even after a valid full snapshot.

Architecture: the backend now serializes Pydantic `MobileRealtimeEnvelope` objects with schema version 1, event type, UTC server time, one process-global monotonic broadcast sequence, and payload. All recipients of one logical broadcast share one sequence. A new authenticated ticket connection gets the current full cockpit sequence. The client quarantines unsupported schemas/delta gaps, accepts only a current v1 `cryptoarc_mobile_cockpit` full snapshot for recovery, rebases immediately when a reconnect gap itself carries that authenticated full snapshot, resumes from its sequence, and ignores stale envelopes.

TDD evidence:

- RED: websocket tests could not find `event_type`/`payload`; gap/schema tests remained permanently quarantined.
- GREEN: backend websocket shape/sequence tests and the client realtime suite cover gaps, schema mismatch, recovery, reconnect ticket rotation, duplicates, stale envelopes, and revocation.
- Cross-layer contract: `mobile-realtime-envelope-v1.json` is validated by backend Pydantic and consumed by the TypeScript reducer.

Files: `backend/app/main.py`, `mobile/src/core/connectivity/realtime.ts`, fixture and tests.

## 3. Centralized financial control authorization

Root cause: trade, position, and treasury components imported `expo-local-authentication` directly. Those calls lacked Task 8 lifecycle/session generation checks and were not bound to the reviewed version/draft/preview.

Architecture: `AppLock` now issues a 30-second control proof bound to `{actionType, entityId, reviewKey}`, session generation, lifecycle generation, and active app state. Trade approval/rejection, position adjust/close, and treasury execution use only this central service. Each flow rechecks the exact current version/draft/escalation or preview/address/amount/account tuple after authentication, after pending-store reads, after durable pending persistence, and immediately before dispatch. Late, backgrounded, unmounted, re-paired, expired, or changed-review proofs cannot dispatch; any just-created pending row is cleared before return. Backend idempotency/preflight was unchanged.

TDD evidence:

- RED: central authorization callback count was zero in legacy flows; a changed treasury preview could retain a direct biometric result.
- GREEN: trade/wallet focused suites cover re-pair, unmount, late completion, changed preview, and dispatch/persistence suppression; AppLock separately rejects a control result completed after background/resume.
- Production source scan shows `expo-local-authentication` only in `SessionProvider`, the centralized implementation.

Files: `AppLock.tsx`, `TradeDetailScreen.tsx`, `GuardedPositionActions.tsx`, `WithdrawalScreen.tsx`, and their tests.

## 4. Encrypted offline verified snapshot

Root cause: SQLCipher storage existed but production code never saved a verified read model and diagnostics was the only loader. Snapshot rows had no owner/device/session binding.

Architecture: snapshots now contain allowlisted metadata plus SHA-256 owner and session identifiers and device ID; the token itself is never persisted. Load requires the exact current binding. Root/payload key allowlists reject credential/action material. Corruption, schema mismatch, or binding mismatch deletes the row and returns no data. Session replacement, clear, and revocation actively clear the row; binding validation remains the fail-closed backstop if deletion fails. A successful authenticated Portfolio HTTP read saves a reduced public read model. After restart/offline, only a matching snapshot is shown as an explicit `Stale offline snapshot` / `Read-only` section, with no position/control affordance. Fresh data supersedes and rewrites it.

TDD evidence:

- Structural RED: there was no production `saveVerifiedSnapshot` caller and `loadVerifiedSnapshot` accepted no identity.
- GREEN: snapshot storage tests cover round-trip, root/payload secret rejection, mismatch, corruption, schema mismatch, key failure, and clearing; authenticated lifecycle tests cover production save, restart load, fresh replacement, and revocation.

Files: `snapshot.ts`, `offlineSnapshot.ts`, `PortfolioScreen.tsx`, `SessionProvider.tsx`, `DiagnosticsScreen.tsx`, and tests.

## 5. Active websocket invalidation

Root cause: `mobile_clients` retained the device object captured at ticket consumption, so later sends trusted stale expiry/revocation/scope state.

Architecture: active sockets retain only device ID. Before every cockpit send, the service reloads the current device and validates existence, revocation, expiry, and `mobile:monitor`. Failure sends one envelope with a deterministic invalidation reason and closes code 4003. Revoke invalidates matching sockets immediately; restore invalidates all sockets as `credentials_replaced`; expiry/scope/removal are caught before the next send. Other sockets receive current scoped cockpit data, not the revoked device object.

TDD evidence: connect-then-revoke, expire, scope removal, and restore tests all receive `invalidate`, then disconnect, with no later cockpit payload. The shared envelope contract test covers the emitted shape.

Files: `backend/app/main.py`, `backend/app/mobile/service.py`, `tests/test_mobile_api.py`.

## 6. Emergency kill switch

Root cause: enabling returned before authentication when the reason field was empty and used the older generic unlock API.

Architecture: enable uses the deterministic audit reason `Emergency mobile kill-switch enable` when empty and immediately requests a fresh binding-aware centralized control proof. It has no hold, motion, or haptic delay. The reviewed current kill state/reason and session/proof are rechecked before the API call. Cancel and failure never queue work. Clearing remains stricter and requires a typed reason before fresh authorization.

TDD evidence: the new kill-switch suite covers immediate empty-reason enable, cancellation, failure/no queue, and stricter clear; 4/4 green.

## Verification

- Backend focused: `tests.test_mobile_api tests.test_mobile_command_center tests.test_mobile_notifications tests.test_mobile_treasury` — 86/86 passed.
- Mobile focused/full Jest — 26 suites, 227/227 passed.
- TypeScript: `tsc --noEmit` passed.
- Expo Doctor: 20/20 passed after SDK 57 patch alignment.
- Android export: succeeded; 4,574 modules bundled to `dist-android`.
- `git diff --check`: passed (only configured LF/CRLF notices).
- Production source scan: no direct feature-level LocalAuthentication; `LIVE_TRADING_ENABLED=false` unchanged.
- `scripts/verify-mobile.ps1`: typecheck and 227/227 tests passed, then the audit step stopped the script. Audit is reduced to the single transitive `image-size@1.2.1` root cause, reported as a ten-package Metro/Expo cascade. GitHub advisories `GHSA-w3rx-r6r6-pgpr` and `GHSA-5p2g-fcmc-qvqq` currently mark every published `image-size` version (`<=2.0.2`) vulnerable; npm latest is 2.0.2, upstream main has no fix commit/release, and npm proposes an unsafe Expo/React Native downgrade. Patchable `brace-expansion` and `nanoid` advisories were resolved. No audit suppression or forced downgrade was used.

## Self-review and deferred evidence

- Reviewed every changed production path for fail-closed behavior, generation/lifecycle drift, binding drift, durable pending state, raw credential persistence, and post-invalidation data. `git diff --check` is clean and `handoff.md` remains untracked.
- Dependency updates are patch-only within Expo SDK 57 and were required to restore Doctor 20/20; `expo-sharing`'s config plugin was added by Expo's compatibility tool.
- Deferred external evidence: audit 0 awaits a patched `image-size` release compatible with Metro. The full script therefore cannot honestly be reported green today even though its remaining Doctor/export stages were run directly and passed.
- Deferred by original safety boundary: physical-device biometric/lifecycle UX, private-tunnel reconnect, notification delivery, and shared/live runtime evidence were not exercised.
