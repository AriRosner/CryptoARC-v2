# 15 Mobile Operator Command Center

Use this runbook to install, pair, operate, upgrade, and revoke the internal Android Operator Command Center. Release `2.0.0` uses Android package `com.cryptoarc.cockpit` and `versionCode` `5`.

## Before You Begin

Require all of the following:

- an operator-owned Android device with a secure screen lock and current system updates;
- a workstation running CryptoARC with `LIVE_TRADING_ENABLED=false`;
- dashboard password authentication, preferably with TOTP;
- a Tailscale tailnet or equivalent authenticated private tunnel shared only with approved devices;
- the approved APK provenance, signing identity, build record, and SHA-256; and
- desktop access for pairing, scope selection, revocation, and recovery.

Never expose the mobile API through Tailscale Funnel or another public relay. Never send an APK, pairing code, mobile token, push token, Telegram token, private key, seed, transaction, or signature through chat or an issue tracker.

## 1. Prepare The Private Endpoint

1. Keep the backend bound locally and expose it through Tailscale Serve or an equivalent tailnet-only route.
2. In the workstation's local `.env`, set:

   ```dotenv
   LIVE_TRADING_ENABLED=false
   MOBILE_PUBLIC_API_BASE_URL=https://cryptoarc-node.tailnet.example
   MOBILE_PAIRING_TTL_SECONDS=300
   MOBILE_TOKEN_TTL_DAYS=30
   MOBILE_PUSH_TOKEN_ENCRYPTION_KEY=
   ```

3. Generate the Fernet push-token encryption key locally and store it as a secret. An absent or invalid key makes push registration fail closed.
4. From the phone, open the private `GET /api/mobile/health` URL and require `status: ok` before pairing.

Loss of the private tunnel is expected to make the app offline, not to fall back to a public route.

## 2. Configure Alert Transports

For Expo push, authenticate to the EAS project without adding `eas-cli` to `package.json`:

```powershell
cd mobile
npx eas-cli@latest login
npx eas-cli@latest credentials --platform android
```

Configure Android FCM V1 credentials through EAS and keep its service-account JSON outside the repository. A signed development or internal build is required for device push registration. Pair with `mobile:alerts`, grant Android notification permission, and check Push in More > Diagnostics.

Native delivery is not release evidence yet: the production backend currently has no Expo network sender wired into `MobileCommandCenterService`. Credential setup and encrypted token registration alone do not prove delivery.

For Telegram fallback, set the following only in local secrets and use the desktop test-alert workflow:

```dotenv
TELEGRAM_ALERTS_ENABLED=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALERT_MIN_INTERVAL_SECONDS=60
```

Native notification deep links expose only privacy-minimized routing metadata and require app unlock before navigation. The current Telegram sender emits redacted text and does not provide an app deep link. Any future Telegram deep link must enforce the same current-session and unlock checks. Neither transport authorizes an action.

## 3. Install Or Upgrade The Internal APK

The authorized packaging command, to be run only after release approval, is:

```powershell
cd mobile
npx eas-cli@latest build --platform android --profile internal --clear-cache
```

Task 10 leaves this cloud build deferred. Before downloading an artifact, obtain an independently trusted release approval record from the release owner through a channel separate from the APK download. It must identify the approved commit, EAS project/build ID, expected package/version/versionCode, expected signer certificate SHA-256 fingerprint, and expected APK SHA-256. Do not trust a checksum or certificate fingerprint supplied only as a sidecar beside the same APK.

For an approved artifact, capture and compare local evidence before installation:

```powershell
$apkPath = (Resolve-Path -LiteralPath 'C:\approved\cryptoarc-operator-command-center.apk').Path
Get-FileHash -LiteralPath $apkPath -Algorithm SHA256 | Format-List Algorithm,Hash,Path

apksigner verify --print-certs $apkPath

# Use either installed Android inspection tool.
apkanalyzer manifest application-id $apkPath
apkanalyzer manifest version-name $apkPath
apkanalyzer manifest version-code $apkPath
# Or: aapt dump badging $apkPath
```

Require the local SHA-256 to match the independently trusted release record. Require `apksigner` verification to succeed and its signer certificate SHA-256 digest to match the independently recorded fingerprint. Require the manifest to report package `com.cryptoarc.cockpit`, version `2.0.0`, and `versionCode` `5`. If `apksigner`, `apkanalyzer`, or `aapt` is not on `PATH`, invoke it from the installed Android SDK build-tools/cmdline-tools directory; do not skip the check.

Only after every comparison passes:

1. Archive the command outputs with the trusted approval record.
2. Choose exactly one installation path:
   - First install, when `com.cryptoarc.cockpit` is not installed: run `adb install $apkPath`.
   - In-place upgrade: keep the approved prior app installed so Android enforces the matching package and signing certificate, then run `adb install -r $apkPath`. This also preserves app data for the pairing-migration test.
3. Open More > Device and require `Operator Command Center v2.0.0 (2026-07-26)` and `2.0.0 / Android 5`.

Stop if Android asks for an uninstall to accept an alleged upgrade, the displayed version differs, or artifact provenance cannot be established. Uninstalling deletes local app state and prevents an in-place migration check.

## 4. Pair With Least Privilege

1. Put phone and workstation on the private tunnel.
2. Open desktop Settings > Security > Mobile Devices.
3. Choose only the necessary scopes, create a short-lived pairing, and immediately scan its QR or enter the URL, pairing ID, and code.
4. On More > Device, compare device name, expiry, private API URL, and scopes with the desktop record.

Recommended scope bundles:

- Read-only operator: `mobile:monitor`, `mobile:portfolio:read`, `mobile:wallet:read`, `mobile:diagnostics`. This bundle cannot acknowledge alerts or register/unregister notification delivery.
- Alert-enabled observer: add `mobile:alerts`. This is not read-only: it authorizes alert acknowledgement and native notification registration/unregistration, which mutate server state.
- Trade reviewer: add `mobile:trade:review`.
- Guarded executor: add `mobile:trade:execute` only after an explicit operator decision.
- Treasury requester: add `mobile:treasury:request` only for the device and period that needs it.
- Legacy runtime controls: add `mobile:control` only if start, stop, or kill-switch control is required.

The phone cannot import keys, arm live mode, sign a transaction, enable live trading, or bypass readiness regardless of its scopes.

## 5. Confirm Lock And Offline Safety

Full-app lock is the default. Confirm device authentication is required on cold launch and after the configured resume timeout. The optional read-only-before-unlock setting may show limited cached state; it never unlocks guarded actions or notification deep links.

Disconnect the private tunnel and confirm:

- the last verified SQLCipher snapshot is timestamped and visibly stale;
- controls are disabled and no action is queued;
- refresh does not blank valid cached data; and
- reconnect requires a fresh authenticated snapshot before realtime deltas become current.

Treat schema mismatch, sequence gaps, clock drift, token expiry, revocation, and ambiguous action state as fail-closed conditions requiring the displayed recovery step.

## 6. Use Guarded Actions

Before approving a prepared trade, adjusting an exit, closing a position, or requesting treasury movement:

1. Confirm the app reports current state, the expected wallet and position/trade, the required scope, and no readiness blocker.
2. Review the server-bounded values and warnings; mobile cannot expand them beyond backend limits.
3. Complete fresh biometrics. For elevated or destructive requests, complete the deliberate hold.
4. Wait for the idempotent receipt. Do not tap repeatedly or invent a new request identity after a timeout.
5. If the result is ambiguous or `review_required`, reconcile it in the app or desktop before any retry.

The backend remains authoritative for readiness, caps, kill switch, wallet state, quotes, signer availability, and final execution. A phone approval never carries a private key, raw transaction, or signature.

## 7. Diagnose And Recover

Open More > Diagnostics to inspect private tunnel, API, websocket, token scope, push, Telegram, clock drift, snapshot age, RPC, and signer observations. Follow enabled recovery guidance in order.

Use Export redacted diagnostics only when support evidence is needed. Keep public identifiers excluded by default and inspect the JSON before sharing. The artifact is designed to exclude tokens, credentials, pairing material, seeds, private keys, signatures, raw transactions, and detailed logs.

If an action is ambiguous, preserve the receipt and diagnose before clearing state. If the device is expired or revoked, stop troubleshooting the old token and pair again only after desktop review.

## 8. Disconnect, Revoke, Or Replace A Device

More > Device > Disconnect removes local credentials but does not prove server revocation.

To revoke:

1. Open desktop Settings > Security > Mobile Devices.
2. Revoke the exact device record and confirm it is shown revoked.
3. Confirm the phone's next authenticated request is denied and the app returns to pairing.
4. Remove its notification registration. For loss or suspected compromise, revoke first, then rotate push/Telegram credentials if exposure is plausible.

For a replacement phone, create a new pairing with newly reviewed scopes. Never copy SecureStore, SQLCipher, or pairing data between devices.

## Deferred Release Evidence

Repository checks do not substitute for device evidence. Until separately performed, do not claim:

- a successful EAS internal APK build or approved signing/provenance;
- SQLCipher behavior in the signed artifact;
- physical biometric launch/resume behavior;
- layout stability, TalkBack, haptics, reduced motion, or performance on target hardware;
- private-tunnel loss/recovery on the target network;
- native push or Telegram deep-link delivery; or
- live signer, wallet, RPC, acknowledgement, transaction, or integration behavior.
