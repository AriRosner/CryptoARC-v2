# Task 7 Report: Alerts, Native Push, And Diagnostics

## Status

Implemented the scoped alerts, native registration lifecycle, unlock-gated push
routing, durable acknowledgement/delivery records, and read-only recovery
diagnostics in the isolated `mobile/operator-command-center` worktree.

## RED Evidence

- Backend RED:
  `python -m unittest tests.test_mobile_notifications -v`
  ran 9 tests and failed as expected with 4 assertion failures and 5 missing
  service-method errors. Missing behavior included alerts/diagnostics routes,
  push sender injection, delivery deduplication, recursive redaction,
  unregister, and single-active-token rotation.
- Mobile RED:
  `npm test -- --runTestsByPath
  src/features/alerts/__tests__/Notifications.test.tsx
  src/features/diagnostics/__tests__/Diagnostics.test.tsx`
  failed both suites before implementation because the notification,
  alerts-screen, diagnostics-screen, and redaction modules did not exist.

## Verification Totals

- Focused backend integration:
  `tests.test_mobile_notifications tests.test_mobile_command_center`
  passed 39/39 tests.
- Focused mobile alerts/diagnostics:
  2/2 suites and 11/11 tests passed with no console warnings.
- TypeScript:
  `npm run typecheck` passed.
- Full `scripts/verify-mobile.ps1`:
  21/21 suites and 163/163 tests passed; production dependency audit found
  0 vulnerabilities; Expo Doctor passed 20/20 checks; Android export completed.
- `git diff --check` exited 0. Git reported only the repository's existing
  Windows LF-to-CRLF conversion notices.

The isolated worktree has no local `.venv`, so focused backend tests used
`..\..\CryptoARC-v2\.venv\Scripts\python.exe` with `PYTHONPATH=backend`.

## Privacy And Plaintext Proof

- Push `data` keys are exactly `event_id`, `severity`, `subsystem`, and `route`.
  Titles and bodies are generic and do not include event messages, wallet
  details, token details, transaction material, or trade values.
- Server and client validate bounded event/entity IDs and an allowlist of
  `/alerts`, `/diagnostics`, `/trade/{id}`, and `/position/{id}` routes.
- Registration reuses Task 2 Fernet ciphertext/fingerprint persistence. Raw
  Expo tokens exist only as transient registration arguments and a local value
  immediately before the injected sender call; that local value is cleared in
  `finally`.
- Tests prove the raw token is absent from database bytes, API responses,
  alerts, diagnostics, diagnostic export, operator events, backups, and
  ordinary exports. Sender failures return generic counts and do not reflect
  provider error text or plaintext.
- Diagnostic export is depth-, key-, string-, and collection-bounded, recursively
  redacts secret/private/signature/pairing/authorization/raw-transaction/log/path
  material, and omits wallet/public identifiers by default. Explicit public
  identifiers are shortened rather than emitted raw.

## Delivery, Unlock, And Recovery Proof

- Rotation leaves one active registration per device; unregister and device
  revocation invalidate active registrations.
- Delivery claims are durable and unique by event, device, and channel.
  Duplicate delivery attempts are suppressed before decryption/sending.
- Acknowledgements are unique by device and event, owner-scoped, and
  idempotent.
- The mobile coordinator configures the required Android channels, waits for
  connectivity before obtaining/registering a token, refetches the Expo token
  on native rotation, and uses the Task 3 session generation for 401 revocation.
- Push response tests prove no trade navigation occurs until local unlock
  resolves successfully. Malformed routes are quarantined and stale session
  generations cannot navigate.
- Alerts and Diagnostics/Recovery Center provide loading skeletons, error and
  empty states, refresh/export actions, deduplicated alert rows, and accessible
  acknowledgement controls.

## No-Network Evidence

- Backend delivery tests use an injected mock sender; no Expo push request was
  made.
- Telegram status testing installs a sender that raises if called and proves it
  was never invoked.
- Diagnostics read only SQLite and bounded in-memory state. They do not probe
  RPC, signer, wallet, Telegram, or shared runtime endpoints.
- No shared runtime/database, signer, wallet, RPC, push, Telegram, shutdown
  script, `pnpm`, or full-repository verification command was used.
- The required mobile gate did run its dependency-audit and Expo diagnostic
  tooling; those are packaging checks, not operator/runtime connections.

## Concerns

- Live Expo provider delivery remains behind the injected backend sender
  boundary and was intentionally not exercised. A release-owned sender can be
  connected without changing token storage, payload construction, or durable
  deduplication.
- Metro export proves JavaScript bundling, not SQLCipher presence in a signed
  Android artifact; final EAS/internal-artifact verification remains required.
