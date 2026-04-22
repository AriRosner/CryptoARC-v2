# Production Paper Deployment

CryptoARC v2 should still be deployed as a paper-trading research app for any network-reachable environment. The repo now includes localhost live-execution capabilities, but those are intended for single-user localhost operation only.

## Paper Production Checklist

1. Copy `.env.production.example` to `.env.production`.
2. Set `DASHBOARD_PASSWORD` to a long random value.
3. Restrict `ALLOWED_ORIGINS` to the deployed dashboard domain.
4. Keep `LIVE_TRADING_ENABLED=false`.
5. Use HTTPS at the reverse proxy.
6. Mount `/app/data` to persistent storage.
7. Start with `docker compose -f docker-compose.production.yml up --build -d`.
8. Confirm `/health/deep`, `/api/watchdog/status`, `/api/safety/status`, and `/api/solana/status`.
9. Enable authenticator-app 2FA from the dashboard before exposing it outside localhost.
10. Back up the SQLite database before upgrades.

## Runtime Expectations

- The bot can monitor PumpPortal, paper trade, replay, and backtest.
- The Solana integration includes read-only RPC checks plus gated live-wallet execution surfaces.
- Assisted browser-wallet execution, encrypted local hot-wallet execution, and active-backend arming exist for localhost use.
- Network deployment should still keep `LIVE_TRADING_ENABLED=false` and treat live execution as out of scope.

## Recovery Flow

If the dashboard stops showing detections:

1. Open Data & Safety.
2. Check Watchdog, Source Quality, and Operational Monitoring.
3. Click `Recover Bot` once.
4. If the watchdog still reports stale ticks, restart the backend service.
5. Export source events and trades before clearing data.

## Local Backup / Restore Notes

- Create a full restore artifact before upgrades or risky data operations.
- Restore preview now validates the embedded SQLite payload itself, not just the artifact metadata.
- After any restore, review schema status, source health, readiness, armed-backend state, and live-wallet recovery status before resuming active monitoring.
