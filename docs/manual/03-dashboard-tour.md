# 03 Dashboard Tour

CryptoARC uses a persistent shell with a left sidebar and page-based main content area.

## Global Shell

The dashboard shell includes:

- Sidebar navigation
- Bot start/stop and API state
- Wallet manager area
- Page content region
- Settings modal
- Toast notifications
- Page-specific modals and workspaces

Screenshot: `assets/screenshots/dashboard/dashboard-shell.png`

## Sidebar

### Navigation

- Monitor
- Analysis
- Backtests
- Trade Review
- Project Data

### Status card

- Bot state
- API connectivity
- Start/Stop action
- Settings shortcut

### Wallet manager section

- Active wallet selector
- Paper wallet option
- Remove selected tracked wallet
- Add wallet
- Manage wallet

Screenshot: `assets/screenshots/dashboard/sidebar-wallet-manager.png`

## Common UI Patterns

### Cards

Most information appears in bordered dashboard cards with compact labels and operator-oriented summaries.

### Tables And Lists

- Monitor tokens
- Intents
- Audits
- Trade records
- Experiments

### Modals

- Settings modal
- Token detail
- Guided live-wallet modal/workspace
- Confirmation flows

### Status Signals

- Green / emerald: healthy, ready, success
- Amber: warning, review, caution
- Rose: blocked, destructive, failing
- Zinc: neutral metadata

### Toasts

Settings and action completions surface success/error toasts in the shell.

## Page Summary

- Monitor: scanning and primary operator workflow
- Analysis: diagnostics and tuning
- Backtests: controlled experimentation
- Trade Review: closed-trade investigation
- Project Data: integrity, safety, monitoring, maintenance

## Settings Modal

The settings modal contains grouped tabs for source, strategy, risk, exits, simulation, advanced settings, and security.

Screenshot: `assets/screenshots/dashboard/settings-modal-overview.png`

## Live Wallet Modal

The live wallet surface starts as a guided setup flow and transitions into an operator workspace after setup completes.

Screenshot: `assets/screenshots/dashboard/live-wallet-setup-stepper.png`

## Practical Navigation Pattern

For daily operation:

1. Use Monitor as the default working page.
2. Open Analysis when tuning or diagnosing.
3. Use Backtests for replay and comparison work.
4. Use Trade Review for post-trade inspection.
5. Use Project Data for maintenance, health, and recovery.
