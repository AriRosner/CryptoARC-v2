# CryptoARC v2 Roadmap

## Product Decisions

- App name: CryptoARC v2.
- Initial deployment: local-only.
- Future deployment: hosted web app capable.
- Stack: Python backend, React frontend.
- Trading mode: paper trading only for MVP.
- Venue: Pump.fun only for MVP.
- Token detection: brand-new launches first, customizable later.
- Default trade size: `0.1 SOL`.
- Default take profit: `50%`.
- Default stop loss: `30%`.
- Future live daily loss cap: `1 SOL`.
- Future wallet model: manual signing first, optional local encrypted hot wallet later.
- UI direction: clean original dashboard inspired by the reference screenshot.
- Layout target: desktop first.

## Phase 1: Paper MVP

- Dashboard shell with sidebar controls, stats, event feed, and token table.
- FastAPI backend with REST endpoints and WebSocket snapshots.
- Mock Pump.fun launch generator.
- Explainable scoring engine.
- Hard risk engine.
- Paper buy/sell lifecycle.
- Take-profit and stop-loss simulation.
- Settings for trade size, take profit, stop loss, loss cap, and wallet cap.
- Audit-style event stream.

Success criteria:

- User can start and stop the paper bot.
- New mock token launches appear live.
- Each token is bought or skipped for a visible reason.
- Paper trades close through take profit or stop loss.
- P&L, win rate, skipped count, and event toasts update.
- No private keys, wallet prompts, or live transactions exist.

## Phase 2: Real Pump.fun Monitoring

- Choose RPC/indexer provider.
- Monitor Pump.fun new token activity.
- Normalize token metadata into the existing `TokenSignal` model.
- Preserve paper-only execution.
- Add source health and reconnect status.
- Add raw event logging for debugging.

## Phase 3: Configurable Strategy

- Score threshold setting.
- Max open paper positions setting.
- Token metadata filters.
- Creator blacklist.
- Minimum buy velocity.
- Maximum sell pressure.
- Duplicate symbol/name/image warning.
- Strategy presets.

## Phase 4: Manual Live Trading

- Browser wallet connection.
- Manual transaction confirmation.
- Transaction preview.
- Solscan links.
- Wallet balance cap enforcement.
- Live mode confirmation every app start.
- Emergency stop.

## Phase 5: Limited Automation

- Local encrypted hot wallet support.
- Per-start risk acknowledgement.
- Max wallet balance cap.
- Daily loss cap enforcement.
- Max trade size enforcement.
- Live audit log export.
- Kill switch.

## Phase 6: Deployment Hardening

- PostgreSQL persistence.
- User authentication.
- Secrets management.
- HTTPS deployment.
- Background worker separation.
- RPC failover.
- Structured logging.
- Monitoring and alerting.
- Test coverage for strategy, risk, and execution.
