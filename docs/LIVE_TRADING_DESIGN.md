# Live Trading Design

CryptoARC v2 currently has no private-key storage, signer, or transaction sender. This document defines the intended path from paper trading to live trading without weakening the paper-only boundary.

## Phase 1: Read-Only Solana Integration

Implemented foundation:

- Configure a Solana RPC URL from Settings.
- Configure a public wallet address for balance checks.
- Check RPC health and wallet SOL balance.
- Never request, store, or derive private keys.
- Never build, sign, simulate, or submit a transaction.

## Phase 2: Manual Live Execution MVP

Current MVP:

- Dashboard/backend can store a manual live request with action, mint, amount, status, and reason.
- Requests are audit-only and blocked by default.
- Requests are subject to a manual amount cap.
- Requests record why execution did not happen.

Future manual execution requirements:

- Environment-level `LIVE_TRADING_ENABLED=true`.
- Explicit dashboard setting for manual live requests.
- Strong dashboard password and 2FA.
- Hardware wallet or external signer. No raw private keys in app storage.
- Transaction simulation before signing.
- Human confirmation for every transaction.
- Durable audit record with simulation result, signer address, transaction signature, and final confirmation status.

## Phase 3: Live Executor Module

The executor should be a separate backend module with a narrow interface:

```text
prepare_quote(request) -> quote
simulate_transaction(quote) -> simulation
request_signature(simulation) -> signed_transaction
submit_transaction(signed_transaction) -> signature
confirm_transaction(signature) -> final_status
```

The strategy engine should never call the executor directly. It should create an execution intent that the safety controller reviews.

## Phase 4: Autonomous Live Mode Later

Autonomous live mode stays disabled until all of these are true:

- At least 30 days of stable production paper trading.
- Replay confidence and price-observation coverage stay above configured thresholds.
- Manual live execution has been tested with tiny amounts and full audit logs.
- Source reliability has alerting and fallback behavior.
- A separate risk controller can halt entries, exits, and all live actions.
- Deployment has HTTPS, auth, 2FA, backup, monitoring, and incident recovery.

## Non-Negotiable Safety Boundary

- Paper mode remains the default.
- `LIVE_TRADING_ENABLED=false` must be the default environment value.
- Autonomous live mode must require both environment and dashboard gates.
- Any future live path must produce an audit record before and after every action.
