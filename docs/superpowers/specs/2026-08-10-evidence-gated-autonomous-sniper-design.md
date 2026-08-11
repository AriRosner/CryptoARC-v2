# Evidence-Gated Autonomous Sniper Design

**Date:** 2026-08-10

**Status:** Approved direction; written-spec review pending

**Target:** Local, single-operator Solana new-token sniper

**Capital envelope:** $100 initial isolated pilot wallet plus $100 reserve held outside the bot

## 1. Purpose

Finalize CryptoARC as a robust autonomous new-token sniper without treating live
trading or profitability as a software-completion checkbox. The launch sequence
must first establish trustworthy market data, positive shadow expectancy after
all modeled costs, safe local execution, and recoverable operations. Real-money
authority remains a separate, explicit operator decision.

The system is not a guaranteed-income product. Its launch claim is limited to:

> CryptoARC can autonomously execute one reviewed new-token strategy under a
> small, fail-closed capital envelope, and can explain, stop, and reconcile every
> live action.

## 2. Approved Decisions

- Use the evidence-gated autonomous approach.
- Launch one new-token sniper strategy before adding general scalping.
- Fund at most $100 in the initial isolated pilot wallet.
- Keep the additional $100 reserve outside the pilot wallet and unavailable to
  automatic replenishment.
- Reuse the existing intent, quote, simulation, signing, submission,
  confirmation, reconciliation, audit, ledger, readiness, and recovery paths.
- Keep `LIVE_TRADING_ENABLED=false` throughout implementation and non-live
  evidence collection.
- Treat every manual-live or autonomous-live action as a separately authorized
  operation after all machine-verifiable prerequisites pass.

The capital allocation is a design limit. It is not authority to create or fund
a wallet, unlock a signer, acknowledge risk, arm a backend, or submit a
transaction.

## 3. Scope

### 3.1 Included

- A versioned, deterministic new-token sniper strategy contract.
- Genuine launch, trade, price, quote, and source-health evidence.
- Independent source comparison and durable source-soak snapshots.
- Paper, replay, out-of-sample, and dry-run shadow evaluation.
- All-cost expectancy, drawdown, latency, landing, and failure reporting.
- A local-only signer selection and isolated pilot-wallet boundary.
- Persistent local authentication with TOTP.
- Backup, restore, shutdown, source-loss, signer-loss, and kill-switch drills.
- One tiny manual buy-and-exit proof before autonomy.
- A capped, attended autonomous pilot followed by complete reconciliation and
  post-run review.

### 3.2 Explicitly Excluded

- Profit guarantees, income targets, or a "money printing" claim.
- General-purpose scalping during the first launch campaign.
- Automatic strategy mutation, self-directed capital increases, martingale,
  loss chasing, or automatic wallet replenishment.
- Seed phrase storage, remote signer exposure, mobile signing, or arbitrary
  transaction signing.
- Public deployment of the control plane.
- Manipulative trading, sandwiching, deceptive order activity, or use of
  non-public/private order flow.
- Bypassing source, quote, simulation, cap, signer, backup, kill-switch,
  acknowledgement, audit, ledger, or reconciliation gates.
- Treating paper, replay, or shadow outcomes as live PnL.

## 4. Existing Architecture To Reuse

No parallel trading engine is needed. The design uses existing contracts:

- `GET /api/source-adapters` for configured source capabilities.
- `GET /api/source-events/solana-logs-verification` for direct-chain comparison.
- `GET /api/source-events/source-soak` and
  `POST /api/source-events/source-soak/snapshot` for source acceptance evidence.
- `GET /api/readiness/status` for strategy promotion and execution readiness.
- `GET /api/live/status` for source-degraded mode, execution backend,
  manual-live verification, backup status, and `full_sniper_gate`.
- `GET /api/reports/evidence-mode-separation` to prevent evidence contamination.
- `GET /api/reports/pilot-readiness` for the launch/run/stop/recover gate set.
- `GET /api/reports/post-run-review` for live-run closure.

The existing live flow remains authoritative:

```text
source observation
  -> deterministic strategy decision
  -> live intent
  -> fresh quote
  -> simulation and preflight checks
  -> local signing backend
  -> submission
  -> confirmation
  -> reconciliation
  -> audit, ledger, and post-run review
```

The strategy may create an intent only. It may not call a signer or transaction
sender directly.

## 5. Versioned Strategy Contract

The first strategy is a single new-token entry-and-exit policy. Its complete
configuration must be saved with each decision and must include:

- strategy identifier and immutable version;
- eligible venue and token-program rules;
- token-age and entry-window bounds;
- minimum liquidity and maximum price-impact requirements;
- mint and freeze authority policy;
- creator and holder concentration limits when trustworthy data is available;
- source freshness and minimum source-confidence requirements;
- entry score, rejection reasons, and abstention behavior;
- minimum hold, take-profit, stop-loss, trailing-stop, break-even, stalled-trade,
  and maximum-hold exits;
- quote lifetime, slippage cap, priority-fee cap, and total execution-cost cap;
- maximum position count and exposure;
- session, daily, cumulative-drawdown, and consecutive-loss stops.

Missing or stale evidence fails closed. A candidate is skipped when any required
field cannot be established. Strategy changes create a new version and restart
the out-of-sample validation campaign; they do not rewrite prior evidence.

## 6. Source And Evidence Campaign

### 6.1 Genuine Source Requirement

The launch source must deliver accepted, timestamped trade-price observations,
not merely new-token announcements. PumpPortal may remain the primary source if
the required funded access is available. Otherwise, a replacement source needs
the same freshness, archival, and failure semantics.

Representative observations must be compared with the existing direct Solana
verification path. Conflicts, missing prices, future timestamps, excessive
staleness, or an unhealthy primary source block shadow promotion and live entry.

### 6.2 Economic Validation Target

The existing pilot gate of five recent evaluated shadows with non-negative PnL
remains a necessary freshness check, but is not sufficient evidence of an edge.
Before manual-live proof, the selected strategy version must have:

- at least 100 completed shadow comparisons;
- observations collected across at least seven calendar days and more than one
  volatility/liquidity condition;
- positive aggregate PnL after modeled entry and exit slippage, base fees,
  priority fees, optional inclusion tips, rent/setup costs, and failed attempts;
- profit factor of at least 1.20;
- maximum campaign drawdown no greater than 10% of the modeled $100 pilot
  capital;
- positive held-out or walk-forward performance without train/validation
  collapse;
- no unresolved evidence-mode contamination or live-audit recovery debt; and
- a cost-stress result that remains non-catastrophic when modeled variable
  execution costs are doubled.

If the source cannot produce enough eligible evidence, the campaign waits. Tests,
fixtures, replay rows, or manually fabricated prices may not satisfy these gates.

## 7. Initial Pilot Risk Policy

USD limits are converted once to SOL from a recorded, independently observed
session-start reference price and rounded down. Limits do not automatically rise
with the wallet balance or SOL price during a session.

- Pilot wallet funding: at most $100 equivalent.
- External reserve: $100, inaccessible to the bot.
- Maximum requested trade: the lower of $5 equivalent or 5% of session-start
  wallet equity.
- Maximum open positions: one.
- Maximum session and daily realized-plus-unrealized loss: $10 equivalent.
- Cumulative pilot loss freeze: $25 equivalent.
- Consecutive losing-position stop: three.
- Initial slippage cap: 3%; evidence may lower it. Raising it above 5% requires a
  new reviewed design decision.
- Maximum total estimated execution cost for an entry or exit: the lower of
  $0.25 equivalent or 5% of the requested notional.
- No automatic restart, cap increase, reserve transfer, or wallet replenishment
  following a stop.

If an emergency protective exit needs to exceed an entry-oriented fee or
slippage limit, it remains a separate explicit recovery decision. The system may
prepare the exit, but it must not silently widen policy.

## 8. Production Operations Gate

Before a manual-live proof, the actual deployment must demonstrate:

- tailnet-only access and no public signer or control-plane exposure;
- durable dashboard authentication with TOTP;
- one explicitly selected wallet and local signer mode;
- signer authentication, wallet match, availability, rotation, and fail-closed
  loss-of-signer behavior;
- source-loss behavior that blocks entries while preserving bounded protective
  exit preparation;
- immediate kill-switch prevention of new entries;
- fresh backup creation plus restore preview and restore smoke proof against the
  deployed schema;
- clean shutdown, restart, and state-recovery drills;
- observable caps with settings-version/operator-intent evidence;
- zero unresolved audits, recovery debt, or stale ledger confidence; and
- an explicit decision that the unexpired `image-size` build-time risk
  acceptance is acceptable for the pilot or a compatible remediation has landed.

Notification limitations, including an unwired native Expo sender or Telegram
without an app deep link, must be disclosed. They may not be represented as
working redundant alert delivery without production evidence.

## 9. Manual-Live Proof

Manual-live proof is a distinct, operator-authorized session. It uses the same
wallet and signer path proposed for autonomy and performs one $2-$5 equivalent
round trip:

1. Produce a fresh quote and complete simulation/preflight review.
2. Submit the buy through the selected local path with explicit approval.
3. Confirm it on chain and reconcile the resulting position.
4. Exercise the actual sell/protective-exit path.
5. Reconcile wallet balances, fees, transaction records, ledger state, and PnL.
6. Export and review the resulting evidence.

Any recorded error, wallet mismatch, unconfirmed transaction, manual database
repair, incomplete reconciliation, or review debt invalidates the proof.

## 10. Autonomous Pilot

Autonomy is authorized only in a new, bounded window after
`full_sniper_gate.ready` and the pilot-readiness report are freshly true for the
selected wallet and signer. The first sessions are attended.

During a pilot, the bot stops new entries on:

- source degradation or conflict;
- signer health or wallet-identity change;
- stale quote, failed simulation, or failed preflight row;
- position, exposure, slippage, fee, session-loss, daily-loss, drawdown, or
  consecutive-loss cap;
- unresolved submission, confirmation, reconciliation, audit, or ledger state;
- stale/missing backup evidence; or
- operator kill switch.

Protective exits may continue only through the existing guarded exit path and
only while its signer, wallet, session, and exit-specific checks pass.

Every session ends with the kill switch engaged, backend disarmed, open state
accounted for, and a post-run review. The next pilot remains blocked until the
prior report is clear.

## 11. Scaling Policy

The pilot does not automatically scale. A later capital increase requires a new
review of live net expectancy, drawdown, fill quality, latency, exit reliability,
cap behavior, audit completeness, and reconciliation.

Scaling is prohibited after a loss merely to recover capital. A $25 cumulative
pilot loss, any unexplained transaction, any cap bypass, or any unreconciled
position returns the strategy to non-live investigation. Any approved increase
must be small, recorded, and reversible.

## 12. Verification Strategy

Implementation planning must preserve strict evidence separation and use
test-driven changes. At minimum, the later plan must cover:

- source freshness, timestamp, acceptance, conflict, archival, and funded-access
  failure tests;
- deterministic strategy-version and rejection-reason tests;
- all-cost shadow accounting and cost-stress tests;
- out-of-sample and evidence-contamination tests;
- USD-to-SOL cap conversion, round-down, immutability, and cap-boundary tests;
- session, daily, drawdown, consecutive-loss, slippage, fee, exposure, and
  position-stop tests;
- signer/wallet replacement and lifecycle invalidation tests;
- source-loss, kill-switch, restart, backup, restore, and reconciliation tests;
- manual-live proof qualification and invalidation tests;
- attended autonomous-pilot stop and post-run closure tests; and
- canonical repository verification before any separately authorized live
  session.

No automated test may fund a wallet, contact a live transaction sender, or
manufacture readiness evidence. Live proof must be captured only during an
explicitly authorized operator window.

## 13. Delivery Boundaries

This design decomposes into independently reviewable work packages:

1. exact-main readiness refresh and evidence inventory;
2. source access and genuine source-soak proof;
3. versioned sniper strategy contract;
4. all-cost shadow evaluation and economic report;
5. micro-pilot risk-policy enforcement;
6. production authentication, signer, backup, and recovery rehearsal;
7. separately authorized manual-live proof;
8. separately authorized attended autonomous pilot; and
9. post-pilot review and explicit scale/no-scale decision.

Work packages 1-6 contain no real-money authority. Packages 7 and 8 cannot be
scheduled solely because code is complete; their evidence prerequisites and
operator authorizations must be freshly satisfied.

## 14. Definition Of Done

CryptoARC is a finished first-version autonomous sniper only when:

- one immutable strategy version meets the genuine source and economic evidence
  targets;
- the actual deployment passes authentication, signer, backup, restore,
  kill-switch, source-loss, restart, and reconciliation drills;
- one recent clean manual-live round trip qualifies for the selected signer;
- the full sniper and pilot-readiness gates are freshly true;
- at least one attended autonomous session completes inside the approved risk
  envelope;
- every live action and resulting balance is explained by audit and ledger
  evidence;
- the post-run report is clear; and
- the operator makes an explicit scale, hold, revise, or stop decision.

Completion does not mean the strategy is guaranteed to remain profitable.
Changing market conditions can revoke the edge and must return the system to
paper/shadow validation.
