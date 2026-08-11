# Separately Authorized Attended Autonomous Pilot

## Current state: DEFERRED

The implementation evaluates eligibility and stop conditions but deliberately never opens execution authority. `/api/autonomous-pilot/status` is authenticated and read-only. The live autonomy loop now refuses to run unless a persisted pilot window is explicitly marked open; this implementation has no endpoint or automated path that can create that state.

Do not create or fund a wallet, unlock or invoke a signer, acknowledge or arm a backend, enable live trading, or submit a transaction while implementing or testing this feature.

## Later authorization prerequisites

A future attended window requires all of the following, captured for the exact wallet and signer identity:

- a fresh authorization ID scoped to `attended-autonomous-pilot`, with an attended marker and a maximum 30-minute expiry;
- fresh actual full-sniper and tiny-pilot readiness reports;
- a qualified, non-fixture manual-live proof;
- the immutable `micro-pilot-risk-v1` policy with one-position and no-restart/replenishment/scale rules;
- fresh backup, zero audit/ledger debt, and an available kill switch;
- a newly coordinated physical window that explicitly authorizes the required live configuration and actions.

Eligibility is not an open window and grants no authority. A future reviewed change must provide the controlled opening mechanism.

## Mandatory stop conditions

Stop new entries and close the window on source loss/conflict, signer loss, wallet/signer identity mismatch, stale quote, failed simulation/preflight, any cap or loss boundary, drawdown, three consecutive losses, audit or ledger debt, stale backup, kill switch, or window expiry. Existing positions may use only the existing guarded protective-exit path; a stop never bypasses quote, simulation, preflight, signer, or recovery controls.

There is no automatic restart, cap increase, scale, or replenishment. End-of-window closure requires the kill switch enabled, backend disarmed, all state reconciled/accounted, and a post-run review before any later window.
