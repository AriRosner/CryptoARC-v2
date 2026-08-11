# Pump.fun Monitoring Research

Research date: 2026-04-16

CryptoARC v2 should keep the current mock source until a real RPC/indexer provider is chosen. The next backend step is to introduce a `LaunchSource` interface with `MockLaunchSource` and `PumpFunLaunchSource` implementations that both emit the existing `TokenSignal` shape.

## Option A: Direct Solana Logs

Chainstack documents a current approach for detecting newly created Pump.fun tokens through Solana `logsSubscribe`. The monitor subscribes to logs mentioning the Pump.fun program, watches for `Instruction: Create`, decodes `Program data`, and extracts token name, symbol, metadata URI, mint, bonding curve, and creator. The guide also notes that the associated bonding curve address can be computed locally, avoiding extra `getTransaction` calls for the create event.

Source: https://docs.chainstack.com/docs/solana-listening-to-pumpfun-token-mint-using-only-logssubscribe

The authoritative event discriminator and Borsh field order come from Pump's public IDL. CryptoARC validates the eight-byte `CreateEvent` discriminator before decoding bounded strings and public keys, and treats other `Program data` payloads as unrelated events.

Source: https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump.json

Pros:

- Direct on-chain path.
- No vendor-specific Pump.fun data API dependency.
- Good fit for paper-only monitoring first.

Cons:

- Requires a reliable Solana WebSocket endpoint.
- Decoder must track Pump.fun program/event changes.
- `blockSubscribe` and high-traffic streams can be unstable depending on provider.

## Option B: PumpPortal Data WebSocket

PumpPortal documents a real-time WebSocket at `wss://pumpportal.fun/api/data` with `subscribeNewToken`, `subscribeTokenTrade`, `subscribeAccountTrade`, and `subscribeMigration`. Their docs specifically warn to use one WebSocket connection and multiplex subscriptions through it.

Source: https://pumpportal.fun/data-api/real-time/

Pros:

- Fastest integration path.
- Purpose-built new-token and trade events.
- Useful for validating our UI and paper strategy quickly.

Cons:

- Third-party dependency.
- Needs rate-limit and outage handling.
- Must review terms before serious use or deployment.

## Option C: PumpArchive

PumpArchive advertises historical token, creator, migration, holder snapshot, webhook, and WebSocket feeds. This looks most useful for creator history, backtesting, and enriching scoring once live new-token monitoring works.

Source: https://pumparchive.com/docs

Pros:

- Better for creator reputation and historical analysis.
- Could power risk-scoring features.

Cons:

- May require account/API key.
- Not the first dependency needed for local paper-mode MVP.

## Recommendation

For the next implementation phase:

1. Add a source adapter interface while keeping `MockLaunchSource`.
2. Add config fields for `SOLANA_WSS_ENDPOINT` and `PUMPFUN_SOURCE`.
3. Implement `PumpPortalLaunchSource` first if the goal is a quick real-data paper feed.
4. Implement direct `logsSubscribe` next if the goal is less vendor dependence.
5. Keep all execution paper-only until the monitor has produced reliable launch records for multiple sessions.
