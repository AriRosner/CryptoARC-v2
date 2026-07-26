# Mobile Operator Command Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing Expo mobile companion into a portfolio-first Operator Command Center with resilient realtime monitoring, guarded live-trading approvals, wallet treasury controls, redundant alerts, diagnostics, expressive motion, and universal skeleton loading states.

**Architecture:** Preserve the current pairing and revocable-token foundation, but move mobile behavior into focused feature modules. Add a purpose-built scoped mobile API and service layer in the backend, TanStack Query for server state, small local stores for settings/session state, SQLCipher-backed encrypted read-only snapshots, and a sequence-aware WebSocket connection manager. Financial actions remain backend-gated, idempotent, non-queueable offline, and unable to import keys, sign arbitrary transactions, arm live execution, or bypass readiness.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite migrations, unittest, Expo SDK 57, React Native 0.86, React 19.2, Expo Router, TypeScript 6, TanStack Query, Zustand, Reanimated, React Native Gesture Handler, Gorhom Bottom Sheet v5, Victory Native, Expo SQLite with SQLCipher, Expo SecureStore, Expo LocalAuthentication, Expo Notifications, Expo Haptics, NetInfo, Jest, Testing Library, EAS internal Android builds.

## Global Constraints

- Work only in `C:\Users\Ari Rosner\Projects\CryptoARC\.worktrees\mobile-operator-command-center` on branch `mobile/operator-command-center`.
- Do not stage, move, revert, or clean changes in the main checkout.
- The other active task owns `scripts/start-dev.ps1`, `scripts/stop-dev.ps1`, `tests/test_scripts.py`, and shared runtime start/stop operations until its final handoff.
- Do not run `scripts/start-dev.ps1`, `scripts/stop-dev.ps1`, or the full repository verifier concurrently with another task.
- Rebase or merge the shutdown task's final commit before the first shared-runtime integration test and before final verification.
- Preserve Android package `com.cryptoarc.cockpit`; bump version and `android.versionCode` only in Task 10.
- Keep Expo SDK at `57.x`, React Native at `0.86.x`, and React at `19.2.x`.
- Install Expo-managed packages with `npx expo install`; do not guess incompatible package versions.
- No mobile private-key/seed import, display, export, backup, or arbitrary transaction signing.
- Mobile may not arm the live backend, clear readiness gates, or bypass source, quote, simulation, signer, exposure, or authentication checks.
- Offline snapshots are read-only and visibly stale; trades, treasury actions, bot controls, and kill-switch changes are never queued.
- Every financial action uses an idempotency key and reconciles ambiguous outcomes instead of retrying submission.
- Every content-loading surface uses a layout-matched skeleton; background refresh preserves existing content.
- Full-app authentication is the default; read-only pre-unlock visibility is optional and never unlocks actions.
- Expressive motion is the default, with Balanced, Minimal, and system reduced-motion settings.
- Native push payloads contain only event ID, severity, subsystem, and deep-link route; sensitive detail is fetched after unlock.
- Native push registration stays disabled unless `MOBILE_PUSH_TOKEN_ENCRYPTION_KEY` is configured; the database stores Fernet ciphertext and a fingerprint, never a raw push token.
- Use `scripts\verify-mobile.ps1` after every mobile-facing task and `scripts\verify.ps1` only at the coordinated final gate.

## File And Ownership Map

### Backend

- `backend/app/mobile/contracts.py`: Pydantic request/response and realtime-envelope contracts.
- `backend/app/mobile/service.py`: read aggregations, scope-safe action validation, idempotency, and redaction.
- `backend/app/mobile/router.py`: `/api/mobile/*` HTTP routes and dependency factories.
- `backend/app/core/models.py`: durable mobile action, destination authorization, push registration, and acknowledgement models.
- `backend/app/core/storage.py`: migration `010_mobile_command_center` and persistence methods.
- `backend/app/core/state.py`: narrow adapters to existing portfolio, intent, ledger, rent-recovery, alert, and live-safety methods.
- `backend/app/main.py`: router registration and sequence-aware `/ws/mobile`; no unrelated route refactor.
- `tests/test_mobile_command_center.py`: read contract, scopes, realtime sequence, and redaction tests.
- `tests/test_mobile_guarded_actions.py`: idempotency, bounded-edit, approval, close, and ambiguous-outcome tests.
- `tests/test_mobile_treasury.py`: allowlist, temporary authorization, withdrawal, sweep, and rent-recovery tests.
- `tests/test_mobile_notifications.py`: push registration, acknowledgement, payload privacy, and delivery-deduplication tests.

### Mobile Foundation

- `mobile/src/core/api/errors.ts`: typed mobile error model and HTTP mapping.
- `mobile/src/core/api/client.ts`: timeout-aware authenticated client and idempotent action request helper.
- `mobile/src/core/api/queryClient.ts`: retry, focus, and online integration.
- `mobile/src/core/session/types.ts`: atomic secure-session record.
- `mobile/src/core/session/storage.ts`: one-record SecureStore persistence and rollback-safe migration.
- `mobile/src/core/session/SessionProvider.tsx`: pairing, revocation, app lock, and session lifecycle.
- `mobile/src/core/connectivity/types.ts`: connection quality and realtime envelope types.
- `mobile/src/core/connectivity/realtime.ts`: sequence-aware WebSocket state machine with capped backoff.
- `mobile/src/core/connectivity/ConnectionProvider.tsx`: NetInfo, AppState, polling fallback, and freshness.
- `mobile/src/core/storage/snapshot.ts`: SQLCipher read-only snapshot persistence.
- `mobile/src/core/settings/settingsStore.ts`: privacy, motion, haptics, refresh, and notification preferences.
- `mobile/src/core/notifications/notifications.ts`: Expo push registration, channels, listeners, and deep-link extraction.

### Mobile Features

- `mobile/src/features/portfolio/`: portfolio types, API hooks, selectors, chart, metrics, allocation, and screen.
- `mobile/src/features/positions/`: position list, adaptive sheet, full details, and guarded position actions.
- `mobile/src/features/trades/`: approval queue, bounded draft, risk escalation, action reconciliation, and history.
- `mobile/src/features/wallet/`: wallet summary, transactions, authorizations, withdrawals, sweeps, and rent recovery.
- `mobile/src/features/alerts/`: unified event list, filters, acknowledgement, and delivery state.
- `mobile/src/features/diagnostics/`: health checks, recovery actions, and redacted export.
- `mobile/src/components/motion/`: motion policy, animated numbers, transitions, and haptic policy.
- `mobile/src/components/skeletons/`: layout-matched skeleton primitives and feature skeletons.
- `mobile/src/components/actions/HoldToConfirm.tsx`: accessible high-risk confirmation control.
- `mobile/src/components/system/ConnectionBanner.tsx`: connection, freshness, and offline status.
- `mobile/src/components/system/AppLock.tsx`: privacy shield and unlock UI.

### Routes

- `mobile/app/(tabs)/index.tsx`: Portfolio.
- `mobile/app/(tabs)/trades.tsx`: Trades.
- `mobile/app/(tabs)/wallet.tsx`: Wallet.
- `mobile/app/(tabs)/alerts.tsx`: Alerts.
- `mobile/app/(tabs)/more.tsx`: More.
- `mobile/app/position/[positionId].tsx`: full position detail.
- `mobile/app/trade/[intentId].tsx`: prepared trade detail.
- `mobile/app/wallet/withdraw.tsx`: guarded withdrawal.
- `mobile/app/diagnostics.tsx`: Diagnostics and Recovery Center.
- `mobile/app/pairing.tsx`: pairing outside authenticated tabs.

---

### Task 1: Dependency, Audit, And Native Capability Foundation

**Files:**
- Modify: `mobile/package.json`
- Modify: `mobile/package-lock.json`
- Modify: `mobile/app.json`
- Modify: `mobile/jest.setup.ts`
- Modify: `scripts/verify-mobile.ps1`
- Create: `mobile/src/__tests__/nativeCapabilities.test.ts`

**Interfaces:**
- Produces: Expo SDK-aligned notification, haptic, SQLite, gesture, chart, network, query, and local-store dependencies.
- Produces: `npm run audit:prod` with zero high or critical production vulnerabilities.
- Produces: SQLCipher and notification config plugins for internal/release builds.
- Consumes: existing Expo SDK 57 and EAS project ID.

- [ ] **Step 1: Add a failing native-capability configuration test.**

```ts
import app from "../../app.json";
import pkg from "../../package.json";

test("command center native capabilities are pinned and configured", () => {
  expect(pkg.dependencies).toEqual(
    expect.objectContaining({
      "@gorhom/bottom-sheet": expect.any(String),
      "@react-native-community/netinfo": expect.any(String),
      "@tanstack/react-query": expect.any(String),
      "expo-haptics": expect.any(String),
      "expo-notifications": expect.any(String),
      "expo-sqlite": expect.any(String),
      "react-native-gesture-handler": expect.any(String),
      "victory-native": expect.any(String),
      "zustand": expect.any(String),
    }),
  );
  expect(app.expo.plugins).toEqual(
    expect.arrayContaining([
      expect.arrayContaining(["expo-notifications"]),
      expect.arrayContaining(["expo-sqlite"]),
    ]),
  );
});
```

- [ ] **Step 2: Run the focused test and verify RED.**

Run:

```powershell
Set-Location mobile
npm test -- --runTestsByPath src/__tests__/nativeCapabilities.test.ts
```

Expected: FAIL because command-center dependencies and plugins are absent.

- [ ] **Step 3: Install SDK-managed and React Native dependencies.**

Run:

```powershell
Set-Location mobile
npx expo install expo-haptics expo-notifications expo-sqlite react-native-gesture-handler @react-native-community/netinfo @shopify/react-native-skia
npm install @tanstack/react-query zustand @gorhom/bottom-sheet@^5 victory-native
```

Add these scripts and overrides:

```json
{
  "scripts": {
    "audit:prod": "npm audit --omit=dev --audit-level=high"
  },
  "overrides": {
    "brace-expansion@1.1.15": "1.1.16",
    "brace-expansion@5.0.7": "5.0.8",
    "xcode": {
      "uuid": "^11.1.1"
    }
  }
}
```

- [ ] **Step 4: Configure native plugins without exposing private notification content.**

Add to `app.json`:

```json
[
  "expo-notifications",
  {
    "icon": "./assets/images/android-icon-monochrome.png",
    "color": "#E89A4A",
    "defaultChannel": "critical"
  }
],
[
  "expo-sqlite",
  {
    "useSQLCipher": true
  }
]
```

Also change the splash background to `#08090F` and add
`NSFaceIDUsageDescription: "Unlock CryptoARC monitoring and guarded controls."`.

- [ ] **Step 5: Make Jest mock the added native modules and add the production audit to mobile verification.**

In `jest.setup.ts`, mock notification, haptic, SQLite, NetInfo, Skia, and bottom-sheet native boundaries. In `scripts/verify-mobile.ps1`, run:

```powershell
Invoke-Checked -Label "mobile production dependency audit" -ScriptBlock {
    Push-Location $mobileRoot
    try { & npm audit --omit=dev --audit-level=high }
    finally { Pop-Location }
}
```

- [ ] **Step 6: Verify GREEN and commit.**

Run:

```powershell
Set-Location mobile
npm run audit:prod
npm test -- --runTestsByPath src/__tests__/nativeCapabilities.test.ts
Set-Location ..
& .\scripts\verify-mobile.ps1
git diff --check
```

Expected: audit has zero high/critical production findings; focused test and full mobile verifier pass.

Commit:

```powershell
git add mobile/package.json mobile/package-lock.json mobile/app.json mobile/jest.setup.ts mobile/src/__tests__/nativeCapabilities.test.ts scripts/verify-mobile.ps1
git commit -m "Build mobile command center foundation"
```

### Task 2: Scoped Backend Contracts And Persistence

**Files:**
- Create: `backend/app/mobile/__init__.py`
- Create: `backend/app/mobile/contracts.py`
- Create: `backend/app/mobile/service.py`
- Create: `backend/app/mobile/router.py`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Modify: `backend/app/config.py`
- Modify: `backend/requirements.txt`
- Modify: `.env.example`
- Modify: `backend/app/main.py`
- Create: `tests/test_mobile_command_center.py`
- Modify: `tests/test_mobile_api.py`

**Interfaces:**
- Produces: `MobileScope` constants for portfolio, trade review, trade execute, wallet read, treasury request, alerts, and diagnostics.
- Produces: `MobileRealtimeEnvelope` with `event_type`, `schema_version`, `server_time`, `sequence`, `entity_id`, and `payload`.
- Produces: migration `010_mobile_command_center`.
- Produces: `create_mobile_router(service, require_scope) -> APIRouter`.
- Preserves: existing pairing, cockpit, feed, start, stop, kill-switch, and `/ws/mobile` behavior.

- [ ] **Step 1: Write failing scope, migration, and contract tests.**

```python
from datetime import datetime, timezone

class MobileCommandCenterContractTests(unittest.TestCase):
    def test_new_scopes_are_not_granted_by_legacy_control(self) -> None:
        pairing = self.state.create_mobile_pairing(
            api_base_url="https://node.tailnet.ts.net",
            scopes=["mobile:monitor", "mobile:control"],
        )
        claim = self.state.claim_mobile_pairing(
            pairing["id"], pairing["code"], "Pixel", "android"
        )
        self.assertNotIn("mobile:trade:execute", claim["scopes"])
        self.assertNotIn("mobile:treasury:request", claim["scopes"])

    def test_realtime_envelope_requires_monotonic_sequence(self) -> None:
        first = MobileRealtimeEnvelope(
            event_type="cockpit",
            server_time=datetime.now(timezone.utc),
            sequence=41,
            payload={"ok": True},
        )
        second = MobileRealtimeEnvelope(
            event_type="cockpit",
            server_time=datetime.now(timezone.utc),
            sequence=42,
            payload={"ok": True},
        )
        self.assertEqual(first.sequence + 1, second.sequence)
        self.assertEqual(second.schema_version, 1)
```

Add an HTTP test asserting a monitor-only token receives `403` from
`GET /api/mobile/wallet` and `POST /api/mobile/trades/intent-1/approve`.

- [ ] **Step 2: Run contract tests and verify RED.**

Run:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_command_center -v
```

Expected: FAIL because the mobile command-center module, scopes, and routes do not exist.

- [ ] **Step 3: Define exact contracts.**

`contracts.py` must define:

```python
class MobileScope:
    MONITOR = "mobile:monitor"
    CONTROL = "mobile:control"
    PORTFOLIO_READ = "mobile:portfolio:read"
    TRADE_REVIEW = "mobile:trade:review"
    TRADE_EXECUTE = "mobile:trade:execute"
    WALLET_READ = "mobile:wallet:read"
    TREASURY_REQUEST = "mobile:treasury:request"
    ALERTS = "mobile:alerts"
    DIAGNOSTICS = "mobile:diagnostics"

class MobileRealtimeEnvelope(BaseModel):
    event_type: Literal["cockpit", "portfolio", "position", "trade", "wallet", "alert", "invalidate"]
    schema_version: Literal[1] = 1
    server_time: datetime
    sequence: int = Field(ge=1)
    entity_id: str = ""
    payload: dict[str, Any]

class MobileActionStatus(str, Enum):
    PENDING = "pending"
    VERIFYING = "verifying"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REVIEW_REQUIRED = "review_required"
```

- [ ] **Step 4: Add migration `010_mobile_command_center`.**

Create tables:

```sql
CREATE TABLE IF NOT EXISTS mobile_action_receipts (
    id TEXT PRIMARY KEY,
    idempotency_key_hash TEXT NOT NULL UNIQUE,
    device_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mobile_destination_authorizations (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
);
CREATE TABLE IF NOT EXISTS mobile_push_registrations (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    token_ciphertext TEXT NOT NULL,
    token_fingerprint TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS mobile_alert_acknowledgements (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    acknowledged_at TEXT NOT NULL,
    UNIQUE(device_id, event_id)
);
```

Push tokens must be excluded from every public serialization, diagnostic export, backup summary, and log message.

Pin `cryptography==49.0.0` in `backend/requirements.txt`. Add
`MOBILE_PUSH_TOKEN_ENCRYPTION_KEY=` to `.env.example` and config. Use
`cryptography.fernet.Fernet`; push registration returns `503` and does not persist
anything when the key is absent or invalid.

- [ ] **Step 5: Extract mobile routing without changing desktop endpoints.**

Implement:

```python
def create_mobile_router(
    service: MobileCommandCenterService,
    require_scope: Callable[[str], Callable[..., dict[str, object]]],
) -> APIRouter:
    router = APIRouter(prefix="/api/mobile", tags=["mobile"])
    return router
```

Move only `/api/mobile/*` handlers into this router. Keep `main.py` responsible for constructing the service, including the router, broadcasting, and WebSocket registration.

- [ ] **Step 6: Verify compatibility and commit.**

Run:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_api tests.test_mobile_revocation tests.test_mobile_command_center -v
git diff --check
```

Expected: existing mobile tests and new scope/contract tests pass.

Commit:

```powershell
git add backend/app/mobile backend/app/core/models.py backend/app/core/storage.py backend/app/core/state.py backend/app/config.py backend/requirements.txt .env.example backend/app/main.py tests/test_mobile_api.py tests/test_mobile_command_center.py
git commit -m "Add scoped mobile command center contracts"
```

### Task 3: Resilient Mobile Client, Atomic Session, And Offline Snapshot

**Files:**
- Create: `mobile/src/core/api/errors.ts`
- Create: `mobile/src/core/api/client.ts`
- Create: `mobile/src/core/api/queryClient.ts`
- Create: `mobile/src/core/session/types.ts`
- Create: `mobile/src/core/session/storage.ts`
- Create: `mobile/src/core/session/SessionProvider.tsx`
- Create: `mobile/src/core/connectivity/types.ts`
- Create: `mobile/src/core/connectivity/realtime.ts`
- Create: `mobile/src/core/connectivity/ConnectionProvider.tsx`
- Create: `mobile/src/core/storage/snapshot.ts`
- Create: `mobile/src/core/settings/settingsStore.ts`
- Modify: `mobile/app/_layout.tsx`
- Modify: `mobile/src/api.ts`
- Modify: `mobile/src/MobileSession.tsx`
- Create: `mobile/src/core/__tests__/client.test.ts`
- Create: `mobile/src/core/__tests__/sessionStorage.test.ts`
- Create: `mobile/src/core/__tests__/realtime.test.ts`
- Create: `mobile/src/core/__tests__/snapshot.test.ts`

**Interfaces:**
- Produces: `MobileApiError`.
- Produces: `mobileGet<T>()` and `mobileAction<T>()`.
- Produces: atomic `SecureSessionRecord`.
- Produces: `MobileRealtimeClient`.
- Produces: `saveVerifiedSnapshot()` and `loadVerifiedSnapshot()`.
- Preserves: existing pairing and session recovery tests.

- [ ] **Step 1: Write failing client/session/realtime/snapshot tests.**

```ts
it("does not retry an ambiguous financial submission", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("network lost"));
  await expect(
    mobileAction("/api/mobile/trades/i1/approve", {
      idempotencyKey: "action-1",
      body: { expected_version: 3 },
    }),
  ).rejects.toMatchObject({ category: "ambiguous_outcome", retryable: false });
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("invalidates on a sequence gap", () => {
  const state = reduceRealtime(
    { lastSequence: 8, requiresSnapshot: false },
    { sequence: 10, schema_version: 1, event_type: "portfolio", payload: {} },
  );
  expect(state.requiresSnapshot).toBe(true);
});
```

Add a remount test proving migration from the old three SecureStore keys creates one
`cryptoarc.mobile.session.v2` record and removes old keys only after the new record is verified.

- [ ] **Step 2: Run the focused tests and verify RED.**

Run:

```powershell
Set-Location mobile
npm test -- --runTestsByPath src/core/__tests__/client.test.ts src/core/__tests__/sessionStorage.test.ts src/core/__tests__/realtime.test.ts src/core/__tests__/snapshot.test.ts
```

- [ ] **Step 3: Implement typed request behavior.**

```ts
export type MobileErrorCategory =
  | "connection"
  | "authentication"
  | "authorization"
  | "validation"
  | "stale_state"
  | "conflict"
  | "rate_limit"
  | "server"
  | "compatibility"
  | "ambiguous_outcome";

export class MobileApiError extends Error {
  constructor(
    message: string,
    readonly category: MobileErrorCategory,
    readonly status: number | null,
    readonly retryable: boolean,
    readonly actionId = "",
  ) {
    super(message);
  }
}
```

`mobileGet` may retry safe reads through TanStack Query. `mobileAction` sends
`Idempotency-Key`, uses one request attempt, and maps a lost response after submission
to `ambiguous_outcome`.

- [ ] **Step 4: Implement the atomic secure session and SQLCipher snapshot.**

```ts
export interface SecureSessionRecord {
  version: 2;
  apiBaseUrl: string;
  token: string;
  device: MobileDevice;
  savedAt: string;
}

export interface VerifiedSnapshot<T> {
  schemaVersion: 1;
  verifiedAt: string;
  serverTime: string;
  sequence: number;
  payload: T;
}
```

Generate the SQLCipher key once with a cryptographically secure random source, keep the
key in SecureStore, set `PRAGMA key` immediately after open, and store only read models.

- [ ] **Step 5: Implement realtime backoff and Query integration.**

Use capped delays of `1s, 2s, 4s, 8s, 16s, 30s` with full jitter. A sequence gap,
unknown schema, token revocation, or server clock drift beyond 30 seconds invalidates
affected queries and displays a compatibility/freshness state.

- [ ] **Step 6: Replace the legacy provider incrementally.**

Keep `MobileSession.tsx` as a compatibility adapter during this task:

```ts
export function useMobileSession(): MobileSessionValue {
  const session = useSession();
  const cockpit = useCockpitCompatibility();
  return mapLegacyMobileSession(session, cockpit);
}
```

Do not delete the adapter until Task 8 moves every route.

- [ ] **Step 7: Verify and commit.**

Run:

```powershell
Set-Location mobile
npm run typecheck
npm test -- --runTestsByPath src/core/__tests__/client.test.ts src/core/__tests__/sessionStorage.test.ts src/core/__tests__/realtime.test.ts src/core/__tests__/snapshot.test.ts src/__tests__/MobileSession.test.tsx
Set-Location ..
& .\scripts\verify-mobile.ps1
git diff --check
```

Commit:

```powershell
git add mobile/src/core mobile/src/api.ts mobile/src/MobileSession.tsx mobile/app/_layout.tsx
git commit -m "Harden mobile session and realtime state"
```

### Task 4: Portfolio And Position Read Models

**Files:**
- Modify: `backend/app/mobile/contracts.py`
- Modify: `backend/app/mobile/service.py`
- Modify: `backend/app/mobile/router.py`
- Modify: `backend/app/core/state.py`
- Modify: `tests/test_mobile_command_center.py`
- Create: `mobile/src/features/portfolio/types.ts`
- Create: `mobile/src/features/portfolio/api.ts`
- Create: `mobile/src/features/portfolio/queries.ts`
- Create: `mobile/src/features/portfolio/PortfolioScreen.tsx`
- Create: `mobile/src/features/portfolio/PerformanceChart.tsx`
- Create: `mobile/src/features/portfolio/PortfolioMetrics.tsx`
- Create: `mobile/src/features/portfolio/AllocationList.tsx`
- Create: `mobile/src/features/positions/types.ts`
- Create: `mobile/src/features/positions/api.ts`
- Create: `mobile/src/features/positions/PositionList.tsx`
- Create: `mobile/src/features/positions/PositionSheet.tsx`
- Create: `mobile/src/features/positions/PositionDetailScreen.tsx`
- Modify: `mobile/app/(tabs)/index.tsx`
- Create: `mobile/app/position/[positionId].tsx`
- Create: `mobile/src/features/portfolio/__tests__/PortfolioScreen.test.tsx`
- Create: `mobile/src/features/positions/__tests__/PositionSheet.test.tsx`

**Interfaces:**
- Produces: `GET /api/mobile/portfolio?timeframe=1d|1w|1m|all`.
- Produces: `GET /api/mobile/positions`.
- Produces: `GET /api/mobile/positions/{position_id}`.
- Produces: `PortfolioPayload`, `PositionSummary`, and `PositionDetail`.
- Requires: `mobile:portfolio:read`.

- [ ] **Step 1: Write failing backend payload tests.**

```python
def test_portfolio_payload_is_complete_and_contains_no_secret_fields(self) -> None:
    payload = self.service.portfolio(device=self.portfolio_device, timeframe="1d")
    self.assertEqual(payload["artifact_type"], "cryptoarc_mobile_portfolio")
    self.assertIn("equity_sol", payload["summary"])
    self.assertIn("win_rate_pct", payload["summary"])
    self.assertIn("health_score", payload["summary"])
    self.assertIn("allocation", payload)
    self.assertIn("series", payload)
    self.assertNotRegex(json.dumps(payload).lower(), r"private_key|seed|token_hash")
```

Test all four timeframes, stable position IDs, mark freshness, approximate PnL flags,
and `404` for an unknown position.

- [ ] **Step 2: Write failing mobile component tests.**

```tsx
render(<PortfolioScreen />);
expect(screen.getByText("Total portfolio")).toBeTruthy();
expect(screen.getByText("Win rate")).toBeTruthy();
expect(screen.getByText("Health")).toBeTruthy();
fireEvent.press(screen.getByText("1W"));
expect(mockFetchPortfolio).toHaveBeenLastCalledWith("1w");
```

For the position sheet, press a position, assert summary fields and guarded actions,
then press `Full details` and assert routing to `/position/{id}`.

- [ ] **Step 3: Run focused backend and mobile tests and verify RED.**

Run:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_command_center -v
Set-Location mobile
npm test -- --runTestsByPath src/features/portfolio/__tests__/PortfolioScreen.test.tsx src/features/positions/__tests__/PositionSheet.test.tsx
```

- [ ] **Step 4: Implement read contracts and aggregations.**

```python
class MobilePortfolioPayload(BaseModel):
    artifact_type: Literal["cryptoarc_mobile_portfolio"] = "cryptoarc_mobile_portfolio"
    format_version: Literal[1] = 1
    generated_at: datetime
    timeframe: Literal["1d", "1w", "1m", "all"]
    freshness: MobileFreshness
    summary: MobilePortfolioSummary
    series: list[MobilePortfolioPoint]
    allocation: list[MobileAllocation]
    positions: list[MobilePositionSummary]
```

Reuse existing ledger, PnL, readiness, source-health, and price-observation data.
Do not duplicate execution calculations in the mobile service.

- [ ] **Step 5: Implement the Portfolio Pulse and position drill-down.**

Use Victory Native for the chart and Gorhom Bottom Sheet for the adaptive sheet.
The initial component contract is:

```ts
export interface PositionSheetProps {
  positionId: string | null;
  onDismiss(): void;
  onOpenDetails(positionId: string): void;
  onAdjustExit(positionId: string): void;
  onClose(positionId: string): void;
}
```

Preserve chart data during timeframe refresh and show a compact syncing indicator.

- [ ] **Step 6: Verify and commit.**

Run:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_command_center tests.test_mobile_api -v
Set-Location mobile
npm run typecheck
npm test -- --runTestsByPath src/features/portfolio/__tests__/PortfolioScreen.test.tsx src/features/positions/__tests__/PositionSheet.test.tsx
Set-Location ..
& .\scripts\verify-mobile.ps1
git diff --check
```

Commit:

```powershell
git add -- backend/app/mobile backend/app/core/state.py tests/test_mobile_command_center.py mobile/src/features/portfolio mobile/src/features/positions "mobile/app/(tabs)/index.tsx" mobile/app/position
git commit -m "Add portfolio and position command views"
```

### Task 5: Guarded Trade Review And Execution Authorization

**Files:**
- Modify: `backend/app/mobile/contracts.py`
- Modify: `backend/app/mobile/service.py`
- Modify: `backend/app/mobile/router.py`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Create: `tests/test_mobile_guarded_actions.py`
- Create: `mobile/src/features/trades/types.ts`
- Create: `mobile/src/features/trades/api.ts`
- Create: `mobile/src/features/trades/queries.ts`
- Create: `mobile/src/features/trades/TradesScreen.tsx`
- Create: `mobile/src/features/trades/TradeDetailScreen.tsx`
- Create: `mobile/src/features/trades/BoundedTradeForm.tsx`
- Create: `mobile/src/features/trades/RiskEscalation.tsx`
- Create: `mobile/src/features/trades/ActionStatus.tsx`
- Create: `mobile/src/components/actions/HoldToConfirm.tsx`
- Create: `mobile/app/(tabs)/trades.tsx`
- Create: `mobile/app/trade/[intentId].tsx`
- Create: `mobile/src/features/trades/__tests__/GuardedTradeFlow.test.tsx`

**Interfaces:**
- Produces: `GET /api/mobile/trades`.
- Produces: `GET /api/mobile/trades/{intent_id}`.
- Produces: `POST /api/mobile/trades/{intent_id}/validate`.
- Produces: `POST /api/mobile/trades/{intent_id}/approve`.
- Produces: `POST /api/mobile/trades/{intent_id}/reject`.
- Produces: `POST /api/mobile/positions/{position_id}/adjust-exit`.
- Produces: `POST /api/mobile/positions/{position_id}/close`.
- Produces: `GET /api/mobile/actions/{action_id}` for reconciliation.
- Requires: review scope for reads/rejects; execute scope for approvals and position actions.

- [ ] **Step 1: Write failing state-machine and idempotency tests.**

Cover:

```python
def test_duplicate_approval_returns_same_receipt_without_second_execution(self) -> None:
    first = self.service.approve_trade(
        device=self.execute_device,
        intent_id=self.intent.id,
        expected_version=3,
        draft=self.valid_draft,
        idempotency_key="same-key",
    )
    second = self.service.approve_trade(
        device=self.execute_device,
        intent_id=self.intent.id,
        expected_version=3,
        draft=self.valid_draft,
        idempotency_key="same-key",
    )
    self.assertEqual(first["action_id"], second["action_id"])
    self.assertEqual(self.signer_submit_calls, 1)
```

Also test stale version conflict, out-of-bounds size/slippage/stop/target, missing
simulation, stale quote, readiness blocker, signer not ready, backend not armed,
kill switch, high-risk escalation reasons, ambiguous result, and review-required
reconciliation.

- [ ] **Step 2: Write failing mobile flow tests.**

Assert:

- routine approval requires biometric confirmation;
- elevated risk requires biometric plus hold-to-confirm;
- a disabled/offline action cannot submit;
- one tap produces one idempotency key and one request;
- an ambiguous response routes to `Verifying outcome`;
- bounded fields cannot exceed backend-provided limits.

- [ ] **Step 3: Run focused tests and verify RED.**

Run:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_guarded_actions -v
Set-Location mobile
npm test -- --runTestsByPath src/features/trades/__tests__/GuardedTradeFlow.test.tsx
```

- [ ] **Step 4: Implement the backend authorization envelope.**

```python
class MobileTradeDraft(BaseModel):
    amount: Decimal
    slippage_pct: Decimal
    stop_pct: Decimal | None = None
    target_pct: Decimal | None = None

class MobileGuardedActionRequest(BaseModel):
    expected_version: int = Field(ge=1)
    draft: MobileTradeDraft
    escalation_acknowledged: bool = False

class MobileActionReceipt(BaseModel):
    action_id: str
    status: MobileActionStatus
    submitted_at: datetime
    updated_at: datetime
    operator_message: str
    reconcile_after_ms: int = Field(ge=250, le=30000)
```

The mobile endpoint authorizes an existing prepared intent. It never accepts a
private key, seed, signed transaction, raw transaction, backend-arm request, or
readiness override.

- [ ] **Step 5: Implement the mobile review, bounded draft, and reconciliation UI.**

`HoldToConfirm` must expose:

```ts
export interface HoldToConfirmProps {
  label: string;
  durationMs: number;
  disabled: boolean;
  onConfirm(): Promise<void> | void;
  accessibilityHint: string;
}
```

Use `durationMs={1400}` for elevated-risk financial actions. Cancellation or
gesture interruption resets progress without submitting.

- [ ] **Step 6: Verify and commit.**

Run:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_guarded_actions tests.test_mobile_command_center tests.test_mobile_api -v
Set-Location mobile
npm run typecheck
npm test -- --runTestsByPath src/features/trades/__tests__/GuardedTradeFlow.test.tsx
Set-Location ..
& .\scripts\verify-mobile.ps1
git diff --check
```

Commit:

```powershell
git add -- backend/app/mobile backend/app/core/models.py backend/app/core/storage.py backend/app/core/state.py tests/test_mobile_guarded_actions.py mobile/src/features/trades mobile/src/components/actions "mobile/app/(tabs)/trades.tsx" mobile/app/trade
git commit -m "Add guarded mobile trade approvals"
```

### Task 6: Wallet Analytics And Guarded Treasury

**Files:**
- Modify: `backend/app/mobile/contracts.py`
- Modify: `backend/app/mobile/service.py`
- Modify: `backend/app/mobile/router.py`
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Create: `tests/test_mobile_treasury.py`
- Create: `mobile/src/features/wallet/types.ts`
- Create: `mobile/src/features/wallet/api.ts`
- Create: `mobile/src/features/wallet/queries.ts`
- Create: `mobile/src/features/wallet/WalletScreen.tsx`
- Create: `mobile/src/features/wallet/WalletHealth.tsx`
- Create: `mobile/src/features/wallet/TransactionList.tsx`
- Create: `mobile/src/features/wallet/WithdrawalScreen.tsx`
- Create: `mobile/src/features/wallet/ProfitSweepSheet.tsx`
- Create: `mobile/src/features/wallet/RentRecoverySheet.tsx`
- Create: `mobile/app/(tabs)/wallet.tsx`
- Create: `mobile/app/wallet/withdraw.tsx`
- Create: `mobile/src/features/wallet/__tests__/WalletTreasury.test.tsx`

**Interfaces:**
- Produces: `GET /api/mobile/wallet`.
- Produces: `GET /api/mobile/wallet/transactions`.
- Produces: `GET /api/mobile/wallet/destinations`.
- Produces: `POST /api/mobile/wallet/withdrawals/preview`.
- Produces: `POST /api/mobile/wallet/withdrawals`.
- Produces: `POST /api/mobile/wallet/profit-sweeps/preview`.
- Produces: `POST /api/mobile/wallet/profit-sweeps`.
- Produces: `POST /api/mobile/wallet/rent-recovery/preview`.
- Produces: `POST /api/mobile/wallet/rent-recovery`.
- Produces: desktop-authenticated `POST /api/mobile/destination-authorizations`.

- [ ] **Step 1: Write failing treasury authorization tests.**

```python
def test_temporary_destination_authorization_is_bound_and_single_use(self) -> None:
    authorization = self.service.authorize_destination(
        desktop_operator=self.desktop_operator,
        device_id=self.device["id"],
        address=self.destination,
        asset="SOL",
        max_amount=Decimal("0.25"),
        expires_in_seconds=300,
        purpose="manual profit transfer",
    )
    receipt = self.service.request_withdrawal(
        device=self.treasury_device,
        authorization_id=authorization["id"],
        address=self.destination,
        asset="SOL",
        amount=Decimal("0.20"),
        idempotency_key="withdraw-1",
    )
    self.assertEqual(receipt["status"], "pending")
    with self.assertRaisesRegex(ValueError, "already used"):
        self.service.request_withdrawal(
            device=self.treasury_device,
            authorization_id=authorization["id"],
            address=self.destination,
            asset="SOL",
            amount=Decimal("0.01"),
            idempotency_key="withdraw-2",
        )
```

Also test wrong address, asset, device, excess amount, expiry, missing preview,
kill switch/readiness/signer failure, duplicate idempotency, and redaction.

- [ ] **Step 2: Write failing wallet UI tests.**

Assert balance groups, committed/available/reserved funds, allocation, fees, rent,
reconciliation, signer/RPC health, and transaction history render. Verify treasury
actions remain disabled offline and always use elevated-risk confirmation.

- [ ] **Step 3: Run focused tests and verify RED.**

Run:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_treasury -v
Set-Location mobile
npm test -- --runTestsByPath src/features/wallet/__tests__/WalletTreasury.test.tsx
```

- [ ] **Step 4: Implement wallet read models and preview-first actions.**

```python
class MobileTreasuryPreview(BaseModel):
    preview_id: str
    action: Literal["withdrawal", "profit_sweep", "rent_recovery"]
    destination: str
    asset: str
    amount: Decimal
    expected_fee_sol: Decimal
    remaining_balance_sol: Decimal
    authorization_id: str
    expires_at: datetime
    warnings: list[str]
```

Every execute call must reference an unexpired preview and the same destination,
asset, amount, device, authorization, and idempotency key context.

- [ ] **Step 5: Implement wallet and treasury UI.**

Wallet actions present preview data, require fresh biometric authentication plus
hold-to-confirm, and show reconciliation state. Never render full push tokens,
auth tokens, private keys, seed material, or unsigned/signed transaction blobs.

- [ ] **Step 6: Verify and commit.**

Run:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_treasury tests.test_mobile_guarded_actions tests.test_mobile_command_center -v
Set-Location mobile
npm run typecheck
npm test -- --runTestsByPath src/features/wallet/__tests__/WalletTreasury.test.tsx
Set-Location ..
& .\scripts\verify-mobile.ps1
git diff --check
```

Commit:

```powershell
git add -- backend/app/mobile backend/app/core/models.py backend/app/core/storage.py backend/app/core/state.py tests/test_mobile_treasury.py mobile/src/features/wallet "mobile/app/(tabs)/wallet.tsx" mobile/app/wallet
git commit -m "Add guarded mobile wallet operations"
```

### Task 7: Alerts, Native Push, And Diagnostics

**Files:**
- Modify: `backend/app/mobile/contracts.py`
- Modify: `backend/app/mobile/service.py`
- Modify: `backend/app/mobile/router.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/core/state.py`
- Create: `tests/test_mobile_notifications.py`
- Create: `mobile/src/core/notifications/notifications.ts`
- Create: `mobile/src/features/alerts/types.ts`
- Create: `mobile/src/features/alerts/api.ts`
- Create: `mobile/src/features/alerts/AlertsScreen.tsx`
- Create: `mobile/src/features/diagnostics/types.ts`
- Create: `mobile/src/features/diagnostics/api.ts`
- Create: `mobile/src/features/diagnostics/DiagnosticsScreen.tsx`
- Create: `mobile/src/features/diagnostics/redaction.ts`
- Create: `mobile/app/(tabs)/alerts.tsx`
- Create: `mobile/app/diagnostics.tsx`
- Create: `mobile/src/features/alerts/__tests__/Notifications.test.tsx`
- Create: `mobile/src/features/diagnostics/__tests__/Diagnostics.test.tsx`

**Interfaces:**
- Produces: `POST /api/mobile/notifications/register`.
- Produces: `POST /api/mobile/notifications/unregister`.
- Produces: `GET /api/mobile/alerts`.
- Produces: `POST /api/mobile/alerts/{event_id}/acknowledge`.
- Produces: `GET /api/mobile/diagnostics`.
- Produces: `GET /api/mobile/diagnostics/export`.

- [ ] **Step 1: Write failing notification privacy and deduplication tests.**

```python
def test_push_payload_contains_only_minimal_routing_data(self) -> None:
    payload = self.service.build_push_payload(self.critical_event)
    self.assertEqual(
        set(payload["data"]),
        {"event_id", "severity", "subsystem", "route"},
    )
    self.assertNotIn("wallet", json.dumps(payload).lower())
    self.assertNotIn("token", json.dumps(payload).lower())
```

Test token registration rotation, revoked-device invalidation, duplicate event
suppression, acknowledgement idempotency, Telegram delivery status, and redacted
diagnostic export.

Assert raw Expo push tokens never appear in SQLite payload reads, API responses,
operator events, logs, backups, or diagnostics. Decrypt only at the send boundary,
then discard the plaintext value.

- [ ] **Step 2: Write failing notification/deep-link/diagnostics UI tests.**

Assert that tapping a push for a trade event routes to `/trade/{intentId}` only
after unlock. Assert duplicate event IDs render once. Assert diagnostics reports
tunnel, API, WebSocket, token scope, push, Telegram, clock drift, snapshot age,
RPC, and signer state.

- [ ] **Step 3: Run focused tests and verify RED.**

Run:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_notifications -v
Set-Location mobile
npm test -- --runTestsByPath src/features/alerts/__tests__/Notifications.test.tsx src/features/diagnostics/__tests__/Diagnostics.test.tsx
```

- [ ] **Step 4: Implement native push registration and Android channels.**

Create channels:

```ts
export const NOTIFICATION_CHANNELS = {
  critical: { name: "Critical trading alerts", importance: 5 },
  warning: { name: "Trading warnings", importance: 4 },
  activity: { name: "Operator activity", importance: 3 },
} as const;
```

Register with `Notifications.getExpoPushTokenAsync({ projectId })`, retry token
registration only after connectivity returns, and listen for token rotation.

- [ ] **Step 5: Implement alerts and Diagnostics/Recovery Center.**

Diagnostic export must pass:

```ts
export function redactDiagnosticValue(key: string, value: unknown): unknown {
  return /token|secret|seed|private|signature|pairing|authorization/i.test(key)
    ? "[REDACTED]"
    : value;
}
```

Also omit raw wallet addresses by default; expose shortened public identifiers
only when the operator explicitly includes them.

- [ ] **Step 6: Verify and commit.**

Run:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_notifications tests.test_mobile_command_center -v
Set-Location mobile
npm run typecheck
npm test -- --runTestsByPath src/features/alerts/__tests__/Notifications.test.tsx src/features/diagnostics/__tests__/Diagnostics.test.tsx
Set-Location ..
& .\scripts\verify-mobile.ps1
git diff --check
```

Commit:

```powershell
git add -- backend/app/mobile backend/app/core/storage.py backend/app/core/state.py tests/test_mobile_notifications.py mobile/src/core/notifications mobile/src/features/alerts mobile/src/features/diagnostics "mobile/app/(tabs)/alerts.tsx" mobile/app/diagnostics.tsx
git commit -m "Add mobile alerts and recovery diagnostics"
```

### Task 8: App Lock, Navigation, Settings, And Legacy Route Removal

**Files:**
- Create: `mobile/src/components/system/AppLock.tsx`
- Create: `mobile/src/components/system/ConnectionBanner.tsx`
- Create: `mobile/src/features/settings/MoreScreen.tsx`
- Create: `mobile/src/features/settings/SettingsScreen.tsx`
- Create: `mobile/src/features/settings/DeviceScreen.tsx`
- Modify: `mobile/app/_layout.tsx`
- Modify: `mobile/app/(tabs)/_layout.tsx`
- Create: `mobile/app/(tabs)/more.tsx`
- Create: `mobile/app/pairing.tsx`
- Delete: `mobile/app/(tabs)/feed.tsx`
- Delete: `mobile/app/(tabs)/risk.tsx`
- Delete: `mobile/app/(tabs)/device.tsx`
- Delete: `mobile/app/(tabs)/pairing.tsx`
- Modify: `mobile/src/MobileSession.tsx`
- Create: `mobile/src/features/settings/__tests__/AppLockSettings.test.tsx`
- Modify: `mobile/src/__tests__/MobileSession.test.tsx`

**Interfaces:**
- Produces: five tabs: Portfolio, Trades, Wallet, Alerts, More.
- Produces: `PrivacyMode = "full_lock" | "read_only_before_unlock"`.
- Produces: `MotionMode = "expressive" | "balanced" | "minimal" | "system"`.
- Produces: `RefreshProfile = "performance" | "balanced" | "battery_saver"`.
- Preserves: pairing QR/manual flow and revocable device behavior.

- [ ] **Step 1: Write failing full-app lock and settings tests.**

```tsx
render(<AppRoot initialAppState="active" />);
expect(screen.getByText("Unlock CryptoARC")).toBeTruthy();
expect(screen.queryByText("Total portfolio")).toBeNull();

await setPrivacyMode("read_only_before_unlock");
render(<AppRoot initialAppState="active" />);
expect(screen.getByText("Total portfolio")).toBeTruthy();
expect(screen.getByText("Controls locked")).toBeTruthy();
```

Test app resume, app-switcher privacy shield, biometric cancellation, unavailable
biometric fallback, lock timeout, and persistence of all settings.

- [ ] **Step 2: Run focused tests and verify RED.**

Run:

```powershell
Set-Location mobile
npm test -- --runTestsByPath src/features/settings/__tests__/AppLockSettings.test.tsx src/__tests__/MobileSession.test.tsx
```

- [ ] **Step 3: Implement full-app lock and privacy modes.**

```ts
export interface AppLockState {
  locked: boolean;
  privacyMode: "full_lock" | "read_only_before_unlock";
  unlock(reason: "app_open" | "financial_action"): Promise<boolean>;
  lock(): void;
}
```

Use Android `biometricsSecurityLevel: "strong"` when available and device
credential fallback otherwise. A financial action always requests a fresh unlock.

- [ ] **Step 4: Replace tab navigation and preserve deep links.**

Tabs use Lucide icons and stable dimensions. Pairing moves outside authenticated
tabs. Old feed events map to Alerts, risk controls map to More/System, and device
controls map to More/Device before deleting legacy tab routes.

- [ ] **Step 5: Remove the legacy session adapter after all consumers migrate.**

Delete `MobileSession.tsx` only after:

```powershell
rg -n "useMobileSession|MobileSessionProvider" mobile/app mobile/src
```

returns no production consumers. Move still-valid tests to the new providers
before deletion.

- [ ] **Step 6: Verify and commit.**

Run:

```powershell
Set-Location mobile
npm run typecheck
npm test -- --runTestsByPath src/features/settings/__tests__/AppLockSettings.test.tsx
Set-Location ..
& .\scripts\verify-mobile.ps1
git diff --check
```

Commit:

```powershell
git add -A mobile/app mobile/src
git commit -m "Restructure mobile navigation and privacy lock"
```

### Task 9: Skeletons, Expressive Motion, Haptics, Accessibility, And Performance

**Files:**
- Create: `mobile/src/components/motion/policy.ts`
- Create: `mobile/src/components/motion/AnimatedNumber.tsx`
- Create: `mobile/src/components/motion/transitions.ts`
- Create: `mobile/src/components/motion/haptics.ts`
- Create: `mobile/src/components/skeletons/Skeleton.tsx`
- Create: `mobile/src/components/skeletons/PortfolioSkeleton.tsx`
- Create: `mobile/src/components/skeletons/PositionSkeleton.tsx`
- Create: `mobile/src/components/skeletons/TradeSkeleton.tsx`
- Create: `mobile/src/components/skeletons/WalletSkeleton.tsx`
- Create: `mobile/src/components/skeletons/AlertsSkeleton.tsx`
- Create: `mobile/src/components/skeletons/DiagnosticsSkeleton.tsx`
- Modify: all feature screens created in Tasks 4-8.
- Create: `mobile/src/components/__tests__/MotionSkeletons.test.tsx`
- Create: `mobile/src/components/__tests__/Accessibility.test.tsx`

**Interfaces:**
- Produces: `useMotionPolicy()`.
- Produces: layout-stable skeletons for every content route.
- Produces: haptic events for selection, warning, rejection, and confirmation.
- Guarantees: emergency controls do not wait for animations.

- [ ] **Step 1: Write failing skeleton, motion-mode, and accessibility tests.**

```tsx
it("preserves content during a background refresh", () => {
  render(<PortfolioScreen seededData={portfolio} fetching />);
  expect(screen.getByText("12.842 SOL")).toBeTruthy();
  expect(screen.getByLabelText("Syncing portfolio")).toBeTruthy();
  expect(screen.queryByTestId("portfolio-initial-skeleton")).toBeNull();
});

it("uses a static skeleton in reduced motion", () => {
  render(<Skeleton width={120} height={20} motionMode="system" reduceMotion />);
  expect(screen.getByTestId("skeleton-shimmer")).toHaveProp("animated", false);
});
```

Assert every icon-only control has an accessibility label, every financial action
has a hint, dynamic type does not clip key labels, and color is not the only status
signal.

- [ ] **Step 2: Run focused tests and verify RED.**

Run:

```powershell
Set-Location mobile
npm test -- --runTestsByPath src/components/__tests__/MotionSkeletons.test.tsx src/components/__tests__/Accessibility.test.tsx
```

- [ ] **Step 3: Implement the motion policy.**

```ts
export interface MotionPolicy {
  duration: { fast: number; normal: number; slow: number };
  spring: { damping: number; stiffness: number };
  shimmer: "full" | "restrained" | "static";
  sharedTransitions: boolean;
  haptics: boolean;
}
```

Expressive uses spring sheets, drawn chart transitions, animated values, shared
position transitions, coordinated list changes, and full shimmer. Balanced reduces
duration and list choreography. Minimal/system-reduced-motion remove nonessential
movement.

- [ ] **Step 4: Add layout-matched skeletons and stable pending controls.**

Initial loads render feature skeletons. Background refresh retains data. Action
buttons keep their dimensions and show pending/reconciling state in place.
Affected-region errors replace only that region's skeleton.

- [ ] **Step 5: Profile Android render behavior.**

Use a release/internal build and record:

- portfolio first meaningful content time;
- chart timeframe transition duration;
- position-sheet open/close frame stability;
- 200-row alert-list scroll stability;
- memory before and after 20 navigation cycles.

Acceptance: no blank canvas, no overlapping text at 360x800 or 412x915, no urgent
action delayed by motion, and no repeated navigation leak.

- [ ] **Step 6: Verify and commit.**

Run:

```powershell
Set-Location mobile
npm run typecheck
npm test -- --runTestsByPath src/components/__tests__/MotionSkeletons.test.tsx src/components/__tests__/Accessibility.test.tsx
Set-Location ..
& .\scripts\verify-mobile.ps1
git diff --check
```

Commit:

```powershell
git add mobile/src/components mobile/src/features
git commit -m "Polish mobile motion and loading states"
```

### Task 10: Coordination, Full Verification, Versioning, And Internal Android Release

**Files:**
- Modify: `mobile/app.json`
- Modify: `mobile/src/buildInfo.ts`
- Modify: `mobile/eas.json`
- Modify: `docs/MOBILE_COCKPIT.md`
- Modify: `docs/manual/INDEX.md`
- Modify: `scripts/verify.ps1` only if the other task's final handoff explicitly permits it.
- Create: `docs/manual/15-mobile-operator-command-center.md`
- Create: `tests/test_mobile_release_contract.py`

**Interfaces:**
- Produces: visible Command Center version marker.
- Produces: Android `versionCode` greater than `2`.
- Produces: internal APK profile and install/upgrade runbook.
- Produces: one coordinated full-repository verification result.

- [ ] **Step 1: Obtain and record the shutdown task handoff.**

Read task `019f71af-0fc6-79f0-9600-2c4c7f570756` and require:

- final commit hash;
- clean status for `scripts/stop-dev.ps1` and `tests/test_scripts.py`;
- focused shutdown-test result;
- confirmation that no mobile/shared contract files changed.

Fetch and integrate its commit before runtime tests:

```powershell
git fetch origin main
git rebase origin/main
git status --short
```

Expected: clean branch or explicit, reviewed conflict resolution. Never overwrite
the other task's shutdown logic.

- [ ] **Step 2: Write the failing release contract test.**

```python
def test_command_center_android_version_is_bumped(self) -> None:
    app = json.loads((ROOT / "mobile" / "app.json").read_text(encoding="utf-8"))
    build_info = (ROOT / "mobile" / "src" / "buildInfo.ts").read_text(encoding="utf-8")
    self.assertGreater(app["expo"]["android"]["versionCode"], 2)
    self.assertIn(app["expo"]["version"], build_info)
    self.assertIn("Operator Command Center", build_info)
```

- [ ] **Step 3: Bump and expose the version.**

Set:

```json
{
  "expo": {
    "version": "2.0.0",
    "android": {
      "versionCode": 3
    }
  }
}
```

Set:

```ts
export const buildInfo = {
  version: "2.0.0",
  androidVersionCode: 3,
  label: "Operator Command Center",
  date: "2026-07-26",
} as const;
```

- [ ] **Step 4: Document setup, scopes, notifications, offline behavior, and guarded actions.**

The runbook must include:

- Tailscale/private-tunnel requirement;
- pairing and scope selection;
- full-app lock;
- Expo push credential setup;
- Telegram fallback;
- internal APK installation and upgrade;
- version confirmation;
- revocation;
- diagnostics;
- explicit statement that the phone cannot import keys, arm live mode, or bypass readiness.

- [ ] **Step 5: Run focused and full verification in the coordinated runtime window.**

Run:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_api tests.test_mobile_revocation tests.test_mobile_command_center tests.test_mobile_guarded_actions tests.test_mobile_treasury tests.test_mobile_notifications tests.test_mobile_release_contract -v
& .\scripts\verify-mobile.ps1
& .\scripts\verify.ps1
git diff --check
git status --short
```

Expected: all focused tests pass; mobile typecheck/tests/audit/Expo diagnostics/
Android export pass; full backend/frontend/mobile/docs gate passes; worktree is
clean after committing.

- [ ] **Step 6: Build and test the internal APK.**

Run from `mobile`:

```powershell
npx eas-cli@latest build --platform android --profile internal --clear-cache
```

On the physical Android device verify:

- installed app shows `Operator Command Center v2.0.0`;
- existing pairing migrates atomically or requests re-pair without mixed state;
- full-app lock works after launch and resume;
- private-tunnel loss shows a stale read-only snapshot;
- position sheet and full details work;
- guarded actions cannot double-submit;
- revoked device is denied;
- native push and Telegram deep links require unlock;
- Expressive, Balanced, Minimal, and reduced-motion modes work;
- all skeleton states are layout-stable.

- [ ] **Step 7: Commit the release slice and prepare integration.**

```powershell
git add mobile/app.json mobile/src/buildInfo.ts mobile/eas.json docs/MOBILE_COCKPIT.md docs/manual/INDEX.md docs/manual/15-mobile-operator-command-center.md tests/test_mobile_release_contract.py scripts/verify.ps1
git commit -m "Prepare mobile operator command center release"
git log --oneline origin/main..HEAD
git status --short
```

Do not push or merge until the user reviews the final verification evidence and
the other task confirms its own branch is stable.

## Official Implementation References

- Expo SDK 57 reference: https://docs.expo.dev/versions/v57.0.0/
- Expo Notifications: https://docs.expo.dev/versions/v57.0.0/sdk/notifications/
- Expo LocalAuthentication: https://docs.expo.dev/versions/v57.0.0/sdk/local-authentication/
- Expo Haptics: https://docs.expo.dev/versions/v57.0.0/sdk/haptics/
- Expo SQLite and SQLCipher: https://docs.expo.dev/versions/latest/sdk/sqlite/
- Cryptography Fernet: https://cryptography.io/en/latest/fernet/
- Expo Router: https://docs.expo.dev/versions/v57.0.0/sdk/router/
- TanStack Query React Native online state: https://tanstack.com/query/latest/docs/reference/onlineManager
- Gorhom Bottom Sheet v5: https://gorhom.dev/react-native-bottom-sheet/

## Final Acceptance Matrix

- Portfolio-first home includes equity, PnL, win rate, health, exposure, drawdown, allocation, timeframes, positions, and approval preview.
- Position tap opens the adaptive sheet; full detail remains directly routable.
- Trading supports review, bounded adjustment, approval/rejection, exit adjustment, close, idempotency, and reconciliation.
- Wallet shows complete operational data and supports allowlisted or temporary-authorized treasury requests.
- Full-app lock defaults on and remains configurable without weakening action locks.
- Offline mode is encrypted, timestamped, visibly stale, and strictly read-only.
- Connection loss, revocation, expiry, schema mismatch, sequence gaps, and ambiguous actions fail closed with recovery guidance.
- Native push and Telegram are deduplicated, deep-linked, and privacy-minimized.
- Expressive motion is fluid and configurable; reduced motion is complete.
- Every initial content load has a matching skeleton; background refresh never blanks valid data.
- No key, seed, auth token, pairing code, push token, raw transaction, or signature leaks through API responses, logs, diagnostics, notifications, or docs.
- Existing desktop behavior and canonical verification remain green.
