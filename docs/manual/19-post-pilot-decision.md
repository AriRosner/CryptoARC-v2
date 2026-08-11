# Post-Pilot Review And Decision

No later pilot may proceed until the previous attended window is closed, every live action and balance is explained, and exactly one operator decision is recorded.

## Review closure

The additive review requires:

- the window closed with kill switch enabled, backend disarmed, and final reconciliation complete;
- every transaction signature attributable and explained;
- complete balance, fee, realized/unrealized PnL, fill, latency, exit, cap, drawdown, audit, and reconciliation evidence;
- zero open positions, unknown transactions, unresolved audits, or ledger debt;
- no manual database repair or cap bypass;
- attributable deterministic grades for the reviewed actions;
- cumulative pilot loss below the immutable $25 freeze.

An unexplained transaction, cap bypass, unresolved position/debt, manual repair, or cumulative loss at or above $25 blocks the next pilot and routes the system to non-live investigation. Missing evidence also fails closed.

## Explicit operator decision

The operator records exactly one append-only `scale`, `hold`, `revise`, or `stop` decision with a rationale and external authorization ID. A blocked review permits only `revise` or `stop`. The authenticated decision endpoint is:

`POST /api/reports/post-pilot-review/{review_id}/decision`

`scale` records intent only. It cannot change wallet funding, risk caps, strategy selection, signer state, live settings, or execution authority. Any actual scale requires a later reviewed design and a new immutable policy.

Use `GET /api/reports/post-pilot-review` for the current read-only state and `/api/reports/post-pilot-review/export` for the bounded evidence artifact. Until a real pilot closes, the report remains `DEFERRED` and the next pilot remains blocked.
