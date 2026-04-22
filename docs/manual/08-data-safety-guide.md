# 08 Data & Safety Guide

The Project Data / Data & Safety area is where CryptoARC exposes the health of the runtime, data quality, and recovery surfaces.

## Main Sections

- Data integrity
- Safety status
- Watchdog
- Operational monitoring
- Security status
- Backup / restore

Screenshot: `assets/screenshots/data-safety/data-safety-page.png`

## Data Integrity

Use this section to inspect:

- replay confidence
- missing records
- rejected prices
- malformed source events
- source normalization quality

## Safety Status

Safety status summarizes runtime risk gates such as:

- kill switch
- loss caps
- replay confidence halts
- readiness-linked constraints

## Watchdog

The watchdog detects stale runtime conditions such as:

- stale bot ticks
- stale source events
- launch ingestion age issues

If stale conditions persist, use the recovery flow first, then escalate to restart.

Screenshot: `assets/screenshots/data-safety/watchdog-status.png`

## Operational Monitoring

Operational monitoring provides a broader system-health view:

- source health
- storage counts
- warnings
- errors
- runtime status

## Security Status

Security status covers:

- auth enabled
- TOTP enabled
- live-trading environment state
- allowed origins
- session / lockout state

## Backup And Restore

Backup/restore is critical for local reliability.

Key rules:

- create a backup before risky operations or upgrades
- preview restore artifacts before confirm
- treat restore as operator-confirmed state replacement

Screenshot: `assets/screenshots/data-safety/restore-preview.png`

## After Restore Checklist

1. Review schema/migration state.
2. Review source health.
3. Review readiness and safety status.
4. Review live-wallet audit and recovery state if live features were in use.
