# 07 Review Guide

Trade Review is where you inspect outcomes after the fact and convert raw activity into useful learning.

## Main Uses

- Review closed paper trades
- Understand why entries/exits occurred
- Inspect PnL components
- Apply operator labels
- Connect trade outcomes back to settings versions

Screenshot: `assets/screenshots/review/trade-review-page.png`

## Key Review Data

- entry / exit reason
- lifecycle status
- hold duration
- fees
- slippage
- price impact
- settings version
- decision log
- replay timeline context
- review workflow position, previous/next trade, and suggested labels
- evidence checklist for source events, decisions, price observations, and PnL

## Labels

Typical labels include:

- good entry
- bad entry
- bad exit
- bad price data
- held too long
- exited too early
- rug-like behavior
- ignore from tuning

## Recommended Post-Trade Loop

1. Start with the Review Queues strip, especially unlabeled losses or bad price evidence.
2. Use Next Review or the first sample trade from the highest-value queue.
3. Inspect the PnL breakdown and evidence checklist.
4. Read the decision stack and lifecycle timeline.
5. Apply a suggested label or choose a more accurate operator label.
6. Use Previous/Next to keep moving through the queue.
7. Cross-reference the settings version if behavior looked surprising.
