# Post-Launch Backlog

## Rule

After usable launch, improve profit, safety, and operator comfort in focused slices. Do not promote a backlog item into a launch blocker unless it prevents catastrophic loss, unsafe signing, bad source input, or unrecoverable accounting.

Every backlog item should answer one question: does this improve profit, safety, or usability enough to justify the time?

## Priority A: Strategy Quality And Edge

- improve labels for profitable and dangerous launch patterns
- add stronger creator and wallet reputation scoring
- tune filters using replay and post-run evidence
- compare strategy variants in clearer replay dashboards
- add better false-positive and false-negative review workflows
- add small automated reports for why a token was entered or skipped

## Priority B: Source Reliability

- run direct Solana `logsSubscribe` as a stronger verifier after launch
- compare PumpPortal and direct Solana streams over longer source-soak windows
- add provider failover if local results justify paid infrastructure
- improve raw-event inspection and source-drift summaries
- alert on source-quality degradation before it becomes a hard outage

## Priority C: Execution Speed

- measure quote-to-submit and event-to-decision latency
- tune transaction preparation and retry behavior
- automate priority-fee suggestions inside configured caps
- improve slippage policy by market state
- precompute safe execution plans where possible

## Priority D: Operator UI And Alerts

- simplify the launch dashboard into start, arm, run, stop, recover, review
- add clearer blocker explanations
- add Telegram alerts for launch blockers, fills, cap hits, kill-switch events, and recovery tasks
- improve empty states and error states
- add compact run summaries for daily use

## Priority E: Product Expansion

- hosted mode only after local autonomy proves useful
- multi-user auth only if another operator needs access
- paid RPC and data providers only if they improve measurable results
- richer analytics only when launch data shows which decisions matter
- packaging and installer polish after the local launch path is stable

