# Separately Authorized Manual-Live Proof

## Hard stop

Do not begin this runbook from an implementation, test, review, or fixture session. A real proof requires all of the following in a newly coordinated window:

- a fresh external authorization ID scoped to `manual-live-proof` and an unexpired window;
- actual deployment/recovery gates complete;
- one explicitly selected wallet, signer mode, and signer identity;
- an immutable micro-pilot policy based on a recorded session-start SOL/USD observation;
- explicit permission to set `LIVE_TRADING_ENABLED=true` only inside that window.

Without every item, the proof remains `DEFERRED`. Do not create or fund a wallet, import or unlock a signer, acknowledge or arm a backend, or submit a transaction.

## Future authorized capture sequence

Inside the later window, the operator records the exact response/evidence ID at each step and stops on any mismatch or debt:

1. Capture the fresh authorization, wallet, signer mode, signer identity, readiness, backup, and immutable pilot policy.
2. Request a fresh $2-$5 buy quote; capture quote, simulation, preflight, caps, and authorization identity.
3. Approve and submit the buy through the selected existing live path; capture the confirmed signature.
4. Confirm and reconcile the buy, including fees and balance changes.
5. Request the actual sell or guarded protective exit; repeat quote, simulation, preflight, and identity checks.
6. Approve, submit, confirm, and reconcile the sell; capture fees, realized PnL, and zero open position.
7. Export `/api/reports/manual-live-proof/export` and the associated incident/audit evidence.
8. Enable the kill switch, disarm the backend, and confirm zero unresolved audit, ledger, or review debt.

This document records the later sequence only. Running the software implementation does not perform any step above.

## Qualification and invalidation

Qualification requires exactly one actual confirmed buy and one actual confirmed sell/protective exit, each attributable to the authorized wallet and signer identity, with $2-$5 notional, complete signatures, reconciliation, fees, and PnL. Fixture evidence, expired or mismatched authorization, errors, unknown/unconfirmed transactions, incomplete accounting, manual database repair, open positions, or review debt invalidate the report.

The authenticated report and export endpoints are read-only. Qualification does not arm a signer, enable live trading, open an autonomous window, or grant any future authority.
