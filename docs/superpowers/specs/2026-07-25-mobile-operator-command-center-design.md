# CryptoARC Mobile Operator Command Center Design

**Date:** 2026-07-25
**Status:** Approved design
**Primary platform:** Android-first Expo React Native, with iOS-compatible architecture

## 1. Purpose

Upgrade the CryptoARC mobile companion into a robust portfolio-first Operator
Command Center for monitoring and guarded live-trading operations.

The app must provide immediate portfolio visibility, reliable realtime state,
prepared-trade review, bounded trade adjustments, guarded position management,
wallet analytics, limited treasury operations, redundant alerting, safe offline
behavior, and strong recovery tooling.

The phone is an operator surface, not a private-key custodian or unrestricted
trading terminal. Live features remain gated by backend readiness and reliability
evidence.

## 2. Product Decisions

- Use the existing Expo app and verified pairing/security foundation.
- Refactor the mobile architecture into focused feature modules.
- Make Portfolio the first screen after unlock.
- Require full-app biometric or device authentication by default.
- Allow an optional setting for read-only portfolio visibility before unlock.
- Keep all financial and control actions locked in every privacy mode.
- Support guarded execution, not unrestricted mobile trading.
- Use native push and Telegram as redundant critical-alert channels.
- Cache only a last-verified read-only snapshot for offline use.
- Never queue financial, treasury, or control actions while offline.
- Use expressive motion by default, with adjustable motion and refresh profiles.
- Use layout-matched skeleton loaders for every content-loading surface.

## 3. Scope

### 3.1 Included

- Portfolio dashboard and selectable performance timeframes.
- Open, closed, and prepared trade views.
- Adaptive position bottom sheet and dedicated position detail screen.
- Prepared-trade approval and rejection.
- Bounded adjustment of size, slippage, stop, and target.
- Close-position and exit-adjustment workflows.
- Pause, stop, and kill-switch controls.
- Wallet balances, allocation, exposure, transaction history, fees, rent,
  reconciliation, signer health, and RPC health.
- Guarded withdrawals, profit sweeps, and rent recovery.
- Desktop-approved destination allowlist.
- Short-lived desktop authorization for exceptional destinations.
- Native push, Telegram redundancy, deep links, and alert acknowledgement.
- Full-app lock, privacy options, haptics, motion settings, and refresh profiles.
- Typed errors, automatic recovery, diagnostics, and redacted log export.
- Offline read-only snapshots with visible freshness information.

### 3.2 Explicitly Excluded

- Private-key or seed import, display, export, or backup on mobile.
- Raw signer unlock or arbitrary transaction signing on mobile.
- Arming a live backend from mobile.
- Bypassing readiness, simulation, risk, or source-trust gates.
- Arbitrary strategy creation or dangerous live configuration changes.
- Arbitrary withdrawal destinations without desktop authorization.
- Offline queuing of trades, withdrawals, kill-switch changes, or bot controls.

## 4. Navigation And Information Architecture

The authenticated app uses five primary tabs.

### 4.1 Portfolio

The Portfolio Pulse screen includes:

- Total portfolio equity.
- Daily and selected-period PnL.
- Realized and unrealized PnL.
- Performance chart with `1D`, `1W`, `1M`, and `ALL` timeframes.
- Win rate.
- System health score.
- Open-position count.
- Exposure and risk utilization.
- Drawdown.
- Asset allocation.
- Open-position list.
- Prepared-approval preview.
- Current connection and freshness state.

Portfolio data leads the visual hierarchy. Safety posture remains continuously
available through compact status surfaces and global safety controls.

### 4.2 Trades

The Trades tab includes:

- Prepared approval queue.
- Open positions.
- Closed positions and trade history.
- Pending, submitted, confirming, reconciled, failed, and review-required states.
- Search, filters, and sorting.
- Trade detail screens.
- Execution, strategy evidence, risk, and audit views.

### 4.3 Wallet

The Wallet tab includes:

- Total wallet value.
- Native and token balances.
- Available, committed, and reserved funds.
- Allocation and concentration.
- Realized and unrealized PnL.
- Transaction history.
- Network fees and rent.
- Last reconciliation time and result.
- RPC, signer, and backend health.
- Profit-sweep history.
- Rent-recovery status.
- Withdrawal history and authorization status.

### 4.4 Alerts

The Alerts tab combines:

- In-app operator events.
- Native push events.
- Telegram delivery status.
- Severity and subsystem filters.
- Acknowledgement state.
- Resolved and unresolved events.
- Deep links to affected trades, wallet actions, or diagnostics.

### 4.5 More

The More tab contains:

- System and source health.
- Diagnostics and Recovery Center.
- Device and pairing information.
- Notification preferences.
- Privacy and lock settings.
- Motion and haptic settings.
- Refresh profile.
- Redacted diagnostic export.
- App and API version information.

## 5. Position And Trade Interaction

Tapping an open position presents an adaptive bottom sheet. The sheet starts
with a compact summary and can expand to show:

- Position size and cost basis.
- Entry and current price.
- Realized and unrealized PnL.
- Stop, target, and trailing protection.
- Quote and price freshness.
- Execution and fee summary.
- Strategy evidence.
- Risk and exposure impact.
- Guarded actions.

A `Full details` command opens a dedicated routed screen with larger charts,
execution history, evidence, audit records, and all permitted controls.

The sheet and dedicated screen share a stable position identity and update from
the same normalized state. Navigating between them must not trigger duplicate
financial requests.

## 6. Guarded Execution

### 6.1 Prepared Trades

A prepared trade review includes:

- Instrument and direction.
- Proposed size.
- Quote age.
- Expected price and slippage.
- Simulation result.
- Expected fees and rent.
- Stop and target.
- Portfolio exposure after execution.
- Strategy and source evidence.
- Risk flags.
- Proposal reason.

The phone may change size, slippage tolerance, stop, and target only within
backend-enforced limits created by the desktop risk configuration. Values beyond
those limits require a new prepared trade.

### 6.2 Confirmation Levels

Routine approvals require biometric or device authentication.

Elevated-risk actions require:

1. Fresh biometric or device authentication.
2. A clear list of escalation reasons.
3. A deliberate hold-to-confirm gesture.

Elevated-risk conditions include:

- Large exposure relative to configured limits.
- Weak or stale evidence.
- Elevated slippage.
- Exit overrides.
- Early closure of a protected winning position.
- Treasury movement.
- An exceptional destination authorization.

Emergency actions must remain immediately reachable and must not be delayed by
decorative animation.

### 6.3 Action Lifecycle

Every financial or control action follows:

`Review -> validate fresh state -> authenticate -> confirm -> submit once -> pending -> reconcile -> final state`

Each submission uses an idempotency key. Duplicate taps, navigation changes,
reconnects, and app resumes must not create duplicate actions.

An ambiguous response never becomes a false success. The UI shows `Verifying
outcome`, blocks resubmission, and reconciles until the backend reports:

- Confirmed.
- Failed.
- Cancelled.
- Expired.
- Operator review required.

## 7. Wallet And Treasury Controls

### 7.1 Standard Destinations

Desktop settings own the withdrawal allowlist. Mobile may select an approved
destination but cannot create, edit, or remove allowlist entries.

### 7.2 Exceptional Destinations

A desktop operator may issue a short-lived authorization bound to:

- Destination address.
- Asset.
- Maximum amount.
- Mobile device.
- Expiry.
- Optional purpose.

Mobile cannot modify these fields. The backend validates them again at
submission.

### 7.3 Guarded Treasury Actions

Mobile supports:

- Withdrawals within authorization.
- Profit sweeps.
- Rent-recovery preview and execution.

Every treasury action shows the destination, amount, asset, expected fees,
remaining balance, authorization source, expiry, and risk warnings before
confirmation.

## 8. Security And Privacy

The default launch state is a full-app privacy lock.

Settings may allow read-only portfolio data before unlock. Regardless of that
setting:

- Financial and control actions always require authentication.
- Sensitive alert details require unlock.
- Background snapshots and app-switcher previews must not reveal protected data.
- Tokens remain in SecureStore.
- Mobile scopes remain revocable and least-privileged.
- Revoked or expired sessions fail closed and clear sensitive in-memory state.
- Push payloads contain only minimal routing and severity information.
- Secrets, keys, tokens, codes, and raw signer data never enter logs or exports.

## 9. Client Architecture

Replace the all-in-one mobile session design with focused modules.

### 9.1 Secure Session

Owns pairing, token persistence, revocation, expiry, biometric state, privacy
mode, and secure logout.

### 9.2 Portfolio Store

Owns balances, positions, PnL, allocation, win rate, drawdown, chart series,
snapshot freshness, and portfolio-derived selectors.

### 9.3 Trading Store

Owns prepared trades, bounded drafts, approvals, orders, action status,
reconciliation, and trade history.

### 9.4 Wallet Store

Owns wallet balances, transactions, fees, rent, reconciliation, destination
authorization, profit sweeps, rent recovery, and withdrawals.

### 9.5 Connection Manager

Owns WebSocket state, sequence tracking, exponential backoff with jitter,
polling fallback, clock-drift checks, connection quality, and stale-data state.

### 9.6 Notification Manager

Owns native push registration, Telegram status, alert deduplication, deep-link
routing, and acknowledgement synchronization.

### 9.7 Settings Store

Owns privacy mode, motion mode, haptics, refresh profile, notification settings,
and display preferences.

## 10. Backend And Realtime Contracts

The mobile app uses purpose-built, scope-limited endpoints. It must not inherit
desktop authorization merely because the desktop has a matching capability.

The expanded mobile API should provide:

- Portfolio summary and chart history.
- Position lists and details.
- Prepared-trade queue and details.
- Bounded trade draft validation.
- Approval, rejection, exit adjustment, and close-position actions.
- Wallet summary, balances, transactions, fees, rent, and health.
- Withdrawal authorizations and guarded treasury actions.
- Alert preferences, acknowledgement, and native push registration.
- Diagnostics and recovery checks.

Realtime messages use typed envelopes containing:

- Event type.
- Schema version.
- Server time.
- Sequence number.
- Entity identity.
- Payload.

Missing or out-of-order sequence numbers trigger a safe snapshot refresh. Schema
versions unknown to the app produce a visible compatibility error rather than
silently applying partial state.

## 11. Offline And Refresh Behavior

The app stores an encrypted last-verified read-only snapshot containing only the
data required for offline monitoring.

Offline state must:

- Display a persistent offline banner.
- Show the snapshot timestamp and age.
- Mark charts and values as stale.
- Disable every financial and control action.
- Never imply that cached data is current.

Refresh profiles are:

- **Performance:** highest supported foreground update rate.
- **Balanced:** realtime primary state with moderated secondary refreshes.
- **Battery Saver:** slower secondary refreshes and reduced noncritical motion.

When backgrounded, the app relies on native push and Telegram. It does not keep
an unrestricted background trading connection alive.

## 12. Error And Recovery Design

Errors are normalized into:

- Connection.
- Authentication.
- Authorization.
- Validation.
- Stale state.
- Conflict.
- Rate limit.
- Server.
- Compatibility.
- Ambiguous outcome.

Safe reads retry automatically with capped exponential backoff and jitter.
Financial actions never retry by issuing a second submission. They reconcile
using their idempotency and action identity.

The UI provides:

- Concise inline messages.
- A persistent connection-quality banner.
- Last successful sync time.
- Region-specific retry controls.
- Recovery paths that preserve navigation and form state when safe.
- Session-expired and revoked-device flows.
- Crash boundaries around navigation and major features.

The Diagnostics and Recovery Center checks:

- Private tunnel reachability.
- Backend health and compatibility.
- Mobile token validity and scopes.
- WebSocket connectivity and sequence health.
- Native push registration.
- Telegram status.
- Clock drift.
- Snapshot freshness.
- RPC and signer health.

Diagnostic exports are redacted and safe to share.

## 13. Notifications

Critical alerts use native push and Telegram. The two channels are redundant,
not mutually exclusive.

Alerts are deduplicated by stable event identity and support:

- Severity.
- Subsystem.
- Resolution state.
- Acknowledgement state.
- Deep-link target.
- Delivery status.

Push notifications contain minimal private data. Full details are fetched after
the app is opened and unlocked.

## 14. Visual And Motion System

The visual language retains the CryptoARC workstation identity:

- Near-black foundations.
- Layered graphite surfaces.
- Amber actions.
- Emerald gains and ready states.
- Rose danger.
- Cool blue connectivity.

Motion uses Reanimated and gesture-driven primitives:

- Animated portfolio totals and PnL changes.
- Drawn chart transitions between timeframes.
- Shared transitions from position rows to sheets and detail screens.
- Spring-based sheets.
- Gesture-driven expansion and dismissal.
- Coordinated list insertion and removal.
- Smooth tab and filter transitions.
- Expandable evidence sections.
- Purposeful success, warning, and error haptics.

Motion modes are:

- **Expressive** by default.
- **Balanced**.
- **Minimal**.
- **Follow system reduced motion**.

No motion mode may delay an urgent acknowledgement, close-position action,
pause, stop, or kill switch.

## 15. Loading States

Every content-loading surface uses a layout-matched skeleton:

- Portfolio totals and charts.
- Metric tiles.
- Position and trade rows.
- Position details.
- Wallet balances and transactions.
- Alerts.
- Diagnostics.
- Settings that depend on remote state.

Initial loading uses skeletons. Background refresh preserves current content and
shows a subtle sync indicator. Financial actions retain stable control
dimensions and show their pending state inside the existing control.

Skeletons match final dimensions to prevent layout shifting.

- Expressive mode uses a refined shimmer.
- Balanced mode uses restrained shimmer.
- Minimal and reduced-motion modes use static or gently fading skeletons.
- Errors replace only the affected skeleton region with recovery controls.

## 16. Delivery Phases

1. Modular foundation, secure lock, settings, typed errors, connection manager,
   and offline snapshots.
2. Portfolio Pulse, charts, skeleton system, position sheets, full details, and
   trade history.
3. Prepared-trade approvals, bounded adjustments, reconciliation, and guarded
   controls.
4. Wallet analytics, destination authorization, withdrawals, profit sweeps, and
   rent recovery.
5. Native push, Telegram redundancy, deep links, acknowledgement, and
   diagnostics.
6. Expressive motion, haptics, accessibility, performance tuning, and Android
   release packaging.

## 17. Verification

### 17.1 Backend

- Scope and authorization tests.
- Snapshot and realtime schema tests.
- Sequence and compatibility tests.
- Bounded adjustment enforcement.
- Idempotency and duplicate-submission tests.
- Ambiguous-outcome reconciliation.
- Destination authorization binding and expiry.
- Revocation and token-expiry behavior.
- Push-payload privacy and diagnostic redaction.

### 17.2 Mobile

- Store and reducer tests.
- API error normalization.
- Reconnection and backoff behavior.
- Offline snapshot freshness.
- Full-app lock and privacy modes.
- Skeleton and error-state rendering.
- Position sheet and detail navigation.
- Risk-tiered confirmations.
- Deep-link routing.
- Notification deduplication.
- Refresh and motion profiles.

### 17.3 Device And Integration

- Pairing and upgrade installation on Android.
- Biometric resume behavior.
- Tunnel loss and recovery.
- Backend restart.
- WebSocket interruption and sequence gaps.
- Background native push and Telegram delivery.
- Interrupted financial actions.
- Revoked-device denial.
- Expressive and reduced-motion behavior.
- Frame-rate and responsiveness checks on target Android hardware.

## 18. Acceptance Criteria

- Portfolio Pulse is the first authenticated screen.
- Portfolio includes win rate, health, timeframe charts, allocation, exposure,
  drawdown, positions, and approval preview.
- Position tap opens an adaptive bottom sheet.
- Dedicated position details remain available.
- Wallet exposes complete operational statistics and guarded treasury actions.
- Full-app lock is enabled by default and configurable.
- Expressive motion is fluid and configurable.
- Every content-loading state has an appropriate skeleton.
- Existing content remains visible during background refresh.
- Offline data is visibly stale and strictly read-only.
- Financial actions cannot double-submit.
- Ambiguous outcomes reconcile without false success.
- Revoked and expired sessions fail closed.
- Native push and Telegram deliver critical alerts without leaking sensitive
  content.
- Emergency controls remain responsive in every motion mode.
- Existing backend, desktop, and mobile verification remains green.
- The Android build has a visible version marker and upgrades the installed app.
