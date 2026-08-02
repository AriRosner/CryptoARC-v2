# CryptoARC Mobile Operator Command Center

The Android-first Expo app in `mobile/` is a private-tunnel operator companion. Release `2.0.0` adds portfolio, trade-review, position, wallet, notification, diagnostics, offline snapshot, and guarded-action surfaces. It is not a second signing environment and does not replace desktop readiness controls.

For the step-by-step operator runbook, see [`manual/15-mobile-operator-command-center.md`](manual/15-mobile-operator-command-center.md).

## Safety Boundary

The phone can monitor scoped data and submit narrowly defined, version-bound requests. It cannot:

- import or reveal a private key, seed phrase, signer credential, or raw transaction;
- arm live mode or enable `LIVE_TRADING_ENABLED`;
- sign a transaction or bypass backend readiness, caps, kill-switch, wallet, quote-freshness, or signer checks;
- queue an action while offline; or
- turn a stale snapshot into current state.

Keep `LIVE_TRADING_ENABLED=false` throughout installation, pairing, and release validation. A mobile approval is only a request to the backend's guarded workflow; it is not proof that a transaction was signed or submitted.

## Private Tunnel And Backend Setup

Use Tailscale Serve or an equivalent authenticated private tunnel. Keep the backend unavailable from the public internet.

1. Run the backend locally and expose it only to the operator's tailnet.
2. Set the tailnet-only URL and mobile lifetimes in the local `.env`:

   ```dotenv
   LIVE_TRADING_ENABLED=false
   MOBILE_PUBLIC_API_BASE_URL=https://cryptoarc-node.tailnet.example
   MOBILE_PAIRING_TTL_SECONDS=300
   MOBILE_TOKEN_TTL_DAYS=30
   MOBILE_PUSH_TOKEN_ENCRYPTION_KEY=
   ```

3. Generate a Fernet key with the project's Python environment and place it only in the local secret store or `.env`; never commit, log, screenshot, or paste it into a pairing message:

   ```powershell
   & .\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

4. Configure dashboard password authentication and preferably TOTP before exposing the dashboard to the tailnet.
5. From the phone, confirm `GET /api/mobile/health` returns `{"status":"ok"}` over the private URL. Do not use Tailscale Funnel.

`MOBILE_PUSH_TOKEN_ENCRYPTION_KEY` protects Expo push tokens at rest. If it is absent or invalid, registration fails closed and stores nothing.

## Pairing And Scopes

Create pairings from desktop Settings > Security > Mobile Devices. Select only the scopes the device needs:

| Scope | Capability |
| --- | --- |
| `mobile:monitor` | Command Center health, blockers, feed, and base realtime session |
| `mobile:portfolio:read` | Portfolio, timeframes, positions, and position details |
| `mobile:trade:review` | Prepared-trade listing, detail, validation, and rejection review |
| `mobile:trade:execute` | Guarded prepared-trade approval and position actions |
| `mobile:wallet:read` | Wallet health, balances, allocation, transactions, and destinations |
| `mobile:treasury:request` | Allowlisted or explicitly temporary-authorized withdrawal requests |
| `mobile:alerts` | Alerts, acknowledgement, and native notification registration |
| `mobile:diagnostics` | Diagnostics and redacted diagnostic export |
| `mobile:control` | Legacy start, stop, and kill-switch controls |

Pairing procedure:

1. Confirm the phone and workstation are on the trusted private tunnel.
2. In desktop Mobile Devices, choose the minimum scopes and create a short-lived pairing.
3. In the Android app, scan the QR or enter the API URL, pairing ID, and code manually.
4. Confirm the device name, expiry, API URL, and granted scopes on More > Device.
5. Let unused pairing codes expire; never reuse or publish them.

The mobile bearer token is revocable and stored in Expo SecureStore. Server-side expiry and revocation remain authoritative.

## App Lock And Guarded Actions

Full-app lock is the default. Android device authentication is required on initial launch and after the configured background timeout. An operator may choose read-only-before-unlock in Settings, but that option never unlocks guarded actions, alert deep links, or sensitive details.

Guarded trade approvals, elevated-risk approvals, exit adjustments, full-position closes, and treasury requests require the relevant scope, current server state, backend policy approval, an idempotency key, and fresh local authentication. Elevated or destructive actions also require a deliberate hold. Repeated taps reuse or reconcile the pending action instead of silently submitting another request. Ambiguous results stay pending or require review; do not retry with a new identity until diagnostics or desktop state resolves the receipt.

## Offline Behavior

The app may display the last verified portfolio snapshot from its SQLCipher database. The SQLCipher key is stored separately in SecureStore. Offline data is timestamped, visibly stale, and strictly read-only:

- no trade, position, treasury, alert-acknowledgement, start, stop, or kill-switch request is queued;
- a sequence gap, schema mismatch, clock drift, expiry, or revocation invalidates current-state assumptions;
- reconnecting requires a fresh authenticated full snapshot before realtime deltas are trusted; and
- cached content never satisfies readiness or action freshness checks.

## Native Push And Telegram Fallback

### Expo push credentials

1. Use the EAS project already identified by `expo.extra.eas.projectId` in `mobile/app.json` and authenticate without adding `eas-cli` to project dependencies:

   ```powershell
   cd mobile
   npx eas-cli@latest login
   npx eas-cli@latest credentials --platform android
   ```

2. Configure the Android FCM V1 service account through EAS. Keep the downloaded service-account JSON out of Git, docs, diagnostics, and support bundles.
3. Set a valid local `MOBILE_PUSH_TOKEN_ENCRYPTION_KEY`, pair with `mobile:alerts`, install a signed development/internal build, grant Android notification permission, and reopen the app so its Expo token can register.
4. Check More > Diagnostics for Push status and test only with privacy-minimized events. Push payloads contain event ID, severity, subsystem, and route; detail is fetched after unlock.

The repository currently does not wire an Expo network sender into the production `MobileCommandCenterService`; diagnostics therefore reports push delivery unavailable even if credential and token registration setup is complete. Do not claim native push delivery until that sender path and a signed artifact are independently verified.

### Telegram fallback

Configure Telegram only in local environment secrets:

```dotenv
TELEGRAM_ALERTS_ENABLED=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALERT_MIN_INTERVAL_SECONDS=60
```

Use the desktop alert test before relying on it, then confirm Telegram status in mobile Diagnostics. Never include the bot token or chat ID in screenshots or exports. Telegram is redundant transport, not an authorization path. The current `AlertRouter` sends redacted text without an app deep link; if Telegram deep links are added later, they must require the app lock and a current mobile session before navigation.

## Internal APK Installation And Upgrade

`mobile/eas.json` defines `internal` as an internal-distribution Android APK and keeps app versioning local. The release metadata is:

- Expo version: `2.0.0`
- Android version code: `3`
- package: `com.cryptoarc.cockpit`
- visible label: `Operator Command Center`

After isolated verification and an approved release window, start the cloud build from `mobile/`:

```powershell
npx eas-cli@latest build --platform android --profile internal --clear-cache
```

Task 10 does not execute that cloud build. Before downloading an APK, obtain a release-owner-approved record through a channel separate from the artifact download. Record the approved commit, EAS project/build ID, package/version/versionCode, APK SHA-256, and signer certificate SHA-256 fingerprint there. A checksum or fingerprint sidecar downloaded beside the APK is not an independent trust source.

After download, verify locally on Windows before any installation:

```powershell
$apkPath = (Resolve-Path -LiteralPath 'C:\approved\cryptoarc-operator-command-center.apk').Path
Get-FileHash -LiteralPath $apkPath -Algorithm SHA256 | Format-List Algorithm,Hash,Path
apksigner verify --print-certs $apkPath

apkanalyzer manifest application-id $apkPath
apkanalyzer manifest version-name $apkPath
apkanalyzer manifest version-code $apkPath
# Or: aapt dump badging $apkPath
```

Compare the file hash and `apksigner` certificate SHA-256 digest to the independently trusted record. Require package `com.cryptoarc.cockpit`, version `2.0.0`, and `versionCode` `3` from `apkanalyzer` or `aapt`. Resolve missing tools from the installed Android SDK; never skip a check. Only after every comparison passes may an operator run `adb install --replace $apkPath`. Android upgrades require the same package and signing certificate and a higher `versionCode`; do not uninstall first if pairing migration is being tested.

After install or upgrade, open More > Device and confirm the header reads `Operator Command Center v2.0.0 (2026-07-26)` and Build reads `2.0.0 / Android 3`. If the hash, approved build identity, package metadata, or signing identity differs, stop and quarantine the artifact without installing it.

## Revocation And Diagnostics

Disconnect removes the local session but does not prove server revocation. To revoke access, use desktop Settings > Security > Mobile Devices > Revoke. The next authenticated mobile request is denied; the app quarantines the session and requires fresh pairing. Also remove the device's notification registration and, for a lost device, revoke it before rotating related notification credentials.

More > Diagnostics reports private-tunnel, API, websocket, token-scope, push, Telegram, clock-drift, snapshot-age, RPC, and signer observations with recovery guidance. Export only the redacted diagnostic artifact. It excludes tokens, credentials, seeds, private keys, signatures, raw transactions, pairing material, and detailed logs. Review the export before sharing it and leave public identifiers excluded unless the recipient explicitly needs them.

## Local Verification

From the repository root:

```powershell
$env:PYTHONPATH='backend'
& .\.venv\Scripts\python.exe -m unittest tests.test_mobile_release_contract -v
& .\scripts\verify-mobile.ps1
git diff --check
```

The internal EAS build, signed-artifact SQLCipher proof, physical biometrics, layout, TalkBack, haptics, performance, private-tunnel behavior, native push, Telegram deep links, and live integration remain separate physical/internal verification gates.
