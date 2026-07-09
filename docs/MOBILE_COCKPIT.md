# CryptoARC Mobile Cockpit

The mobile cockpit is an Android-first Expo companion app in `mobile/`. V1 is a private-tunnel monitor and control surface for one operator, not desktop parity.

## V1 Scope

Included:

- Pair by short-lived QR or manual code from the desktop Security settings.
- Store the mobile token in Expo SecureStore.
- Require local device unlock before mobile start, stop, or kill-switch controls.
- Show cockpit safety, blockers, source health, readiness, open risk, PnL, event feed, and Telegram alert status.
- Start and stop the paper/source loop, and enable or clear the live kill switch.
- Stream cockpit updates over `WS /ws/mobile?token=...` while the app is open, with polling fallback.

Excluded:

- Mobile private-key import, seed phrases, hot-wallet import, live backend arming, live transaction submission, public cloud relay, push notifications, and Play Store release.

## Private Tunnel

Use Tailscale first. Keep the backend reachable only inside your tailnet.

Do:

- Run the backend locally on `127.0.0.1:8000`.
- Expose that local backend to tailnet devices with Tailscale Serve or an equivalent tailnet-only route.
- Put the tailnet URL in `.env` as `MOBILE_PUBLIC_API_BASE_URL`.
- Pair only while the phone and workstation are on the same trusted tailnet.

Do not:

- Use Tailscale Funnel for this app.
- Publish `/api/mobile/*` or `/ws/mobile` on the public internet.
- Put Telegram tokens, mobile tokens, or pairing codes in docs, screenshots, or issue reports.

Example `.env` values:

```dotenv
MOBILE_PUBLIC_API_BASE_URL=https://cryptoarc-node.tailnet.example
MOBILE_PAIRING_TTL_SECONDS=300
MOBILE_TOKEN_TTL_DAYS=30
```

Before pairing, verify from the phone:

- `GET /api/mobile/health` returns `status: ok`.
- Dashboard auth is configured, preferably with TOTP.
- The desktop Security tab can create a fresh mobile pairing code.

## Pairing Flow

1. Start the backend and desktop dashboard.
2. Open desktop Settings, then Security, then Mobile Devices.
3. Enter or confirm the private tunnel API base URL.
4. Press Pair to generate a short-lived QR and manual code.
5. In the Android app, open Pair.
6. Check the tunnel, then scan the QR or enter API URL, pairing ID, and manual code.
7. After pairing, open Device and unlock controls with Android device authentication.

Revocation is desktop-owned:

- Open Settings, Security, Mobile Devices.
- Press Revoke for the device.
- The mobile token is denied on the next cockpit/feed/action request.

## Mobile API

Desktop-auth endpoints:

- `POST /api/mobile/pairing/start`
- `GET /api/mobile/devices`
- `POST /api/mobile/devices/{id}/revoke`

Mobile pairing endpoint:

- `POST /api/mobile/pairing/claim`

Mobile-token endpoints:

- `GET /api/mobile/cockpit`
- `GET /api/mobile/feed`
- `GET /api/mobile/alerts/status`
- `POST /api/mobile/actions/start`
- `POST /api/mobile/actions/stop`
- `POST /api/mobile/actions/kill-switch`
- `WS /ws/mobile?token=...`

Mobile tokens are scope-limited. `mobile:monitor` can read cockpit/feed/alerts. `mobile:control` is required for start, stop, and kill switch. Mobile tokens cannot arm live backends, submit live trades, import hot wallets, or change dangerous live settings.

## Development

```powershell
cd mobile
npm install
npm run typecheck
npm test
npm run diagnostics
npm run export:android
```

Internal Android APK distribution uses EAS:

```powershell
cd mobile
npx eas build --platform android --profile internal
```

Install the resulting APK only on operator-owned Android devices.
