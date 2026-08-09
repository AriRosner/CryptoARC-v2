# Contributing to CryptoARC

## Before opening a pull request

1. Open or reference an issue that explains the problem and intended outcome.
2. Keep changes narrowly scoped and preserve the default fail-closed trading posture.
3. Never commit credentials, seed phrases, API keys, wallet material, transaction signatures, or production data.
4. Run the smallest relevant check; run `scripts/verify.ps1` for cross-cutting, release-critical, or safety-critical work.
5. Complete the pull request template, including verification and rollback details.

## Trading and security changes

Changes touching live trading, signing, wallets, recovery, credentials, authorization, or kill-switch behavior require an explicit risk explanation, tests for the changed invariant, and a safe rollback plan. Keep `LIVE_TRADING_ENABLED=false` unless the documented operator gates have been satisfied.

## Reporting problems

Use the issue forms for reproducible bugs and feature requests. Use the [security policy](.github/SECURITY.md) to report vulnerabilities privately.
