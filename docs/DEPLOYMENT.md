# Production Paper Deployment

CryptoARC v2 should be deployed as a paper-trading research app until the live execution design is complete, reviewed, and tested with tiny manual transactions.

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
- The Solana integration is read-only and only checks RPC health plus a public wallet balance.
- Manual live requests are audit records only. They do not sign or submit transactions.
- Autonomous live mode is a roadmap item, not a runtime feature.

## Recovery Flow

If the dashboard stops showing detections:

1. Open Data & Safety.
2. Check Watchdog, Source Quality, and Operational Monitoring.
3. Click `Recover Bot` once.
4. If the watchdog still reports stale ticks, restart the backend service.
5. Export source events and trades before clearing data.
