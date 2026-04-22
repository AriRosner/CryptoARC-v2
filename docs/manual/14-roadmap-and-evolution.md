# 14 Roadmap And Evolution

This section is intentionally separated from the current-state manuals. Use it to understand where the project is heading without confusing planned behavior with implemented behavior.

## Current-State Priority Themes

- stronger research and tuning loops
- richer replay and experiment ergonomics
- tighter recovery and operational confidence
- more mature wallet-ledger accounting
- better signer-daemon verification story

## Near-Term Evolution

- improve Pump.fun intelligence and source trust layering
- add richer replay filters and experiment usability
- continue hardening live reconciliation and review workflows
- improve architecture clarity and runtime smoothness

## Live-System Evolution Notes

Current live behavior is already explicit and usable in localhost-only form, but future work may still improve:

- signer-daemon contract maturity
- operator ergonomics
- recovery depth
- reporting and audit summaries

Non-negotiable constraints for future work:

- localhost-only live execution should remain the default safety boundary
- seed phrases stay out of scope
- remote signer exposure stays out of scope
- paper-first posture remains the recommended operating model

## Relationship To Existing Roadmap

See [`../ROADMAP.md`](../ROADMAP.md) for broader planning notes. This manual section is meant to translate roadmap thinking into practical “what may change next” guidance for operators and developers.
