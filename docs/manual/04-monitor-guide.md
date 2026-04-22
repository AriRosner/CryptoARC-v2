# 04 Monitor Guide

The Monitor page is the primary operator workspace for scanning new launches and managing the day-to-day paper or live review loop.

## Main Areas

- Token queue/table
- Event stream and status context
- Watchlist interactions
- PnL summary/chart context
- Token detail modal

Screenshot: `assets/screenshots/monitor/monitor-page-full.png`

## Token Table

The token table is optimized for high-speed scanning. Typical fields include:

- symbol and name
- mint
- age
- score and reason
- buy velocity
- sell pressure
- metadata score
- creator hold and creator behavior signals
- price and PnL context
- lifecycle status

## Primary Monitor Workflow

1. Watch new tokens enter the queue.
2. Filter obvious weak candidates.
3. Open token detail for promising launches.
4. Add candidates to the watchlist if they need closer tracking.
5. Observe paper-trade or live-intent state changes.

## Watchlist

The watchlist is the short list of launches worth continued attention. It supports:

- saving likely candidates
- revisiting tokens later
- using watchlist entries as inputs to live-intent generation flows

## Token Detail

Token detail provides a deeper inspection surface for:

- metadata
- price context
- score breakdown
- decision log
- creator signals
- market-cap / launch information

Screenshot: `assets/screenshots/monitor/token-detail-modal.png`

## PnL Context

Monitor also includes wallet-scoped PnL views and charting to keep the current operating wallet in context.

## Best Practices

- Keep the bot in paper mode while tuning thresholds.
- Do not treat a high score as sufficient by itself; use the detail view and risk context.
- Prefer watchlist curation over reacting to every queue item.
- Use Review and Analysis after the monitor session to validate decisions.
