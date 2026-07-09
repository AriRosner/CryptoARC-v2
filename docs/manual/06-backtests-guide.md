# 06 Backtests Guide

Backtests and replay flows are how CryptoARC validates strategies before trusting them in live observation or gated execution.

## Available Modes

- Replay backtest
- Raw replay backtest
- Strategy comparison
- A/B replay
- Backtesting v3
- Saved experiments

Screenshot: `assets/screenshots/backtests/backtests-page-overview.png`

## What Each Mode Is For

### Replay backtest

Replays normalized token history through the configured logic. Each saved run includes a deterministic fingerprint derived from the replay inputs, settings, metrics, and trade decisions. Re-running the same evidence should produce the same fingerprint even though the saved run id and timestamp change.

### Raw replay

Replays raw source material more directly for source-sensitive validation. Raw replay fingerprints ignore temporary normalized-token ids, so parser-generated replay rows can still be compared across repeated runs.

### Strategy comparison

Compares profiles or strategies against the same replay set.

### A/B replay

Used to compare two decision paths on similar input.

### Backtesting v3

The more advanced validation path with suite-level deterministic fingerprinting and comparison context.

## Saved Experiments

Saved experiments capture:

- name
- profile
- replay source
- notes
- fingerprint / settings-version context

## Reading Results

Important result fields include:

- wins / losses / scratches
- estimated PnL
- max drawdown
- profit factor
- deterministic fingerprint
- hold duration
- best / worst trades

## Recommended Workflow

1. Choose a profile and scope.
2. Run replay or comparison.
3. Inspect result summary and trade distribution.
4. Save the experiment if it is worth comparing later.
5. Cross-check settings and tuning ideas in Analysis.
