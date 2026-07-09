# Design

## Overview

CryptoARC v2 is a dark, local-first operations dashboard for crypto launch monitoring and staged live execution. The visual system should preserve the current workstation identity: blackened surfaces, amber primary action accents, emerald positive states, rose danger states, compact panels, Lucide line icons, and dense operator-first data views.

## Color

### Palette

- Background: `#08090f`
- Deep surface: `#090b13`
- Surface: `#10121c`
- Raised surface: `#151824`
- Border: `#242632`
- Strong border: `#343848`
- Primary accent: `#e89a4a`
- Positive: `#79e0a6`
- Danger: `#ff7d86`
- Muted text: `#9096a6`
- Primary text: `#f6f2ea`

### Usage

Use amber for primary operator actions, selected navigation, current filters, focus rings, and attention states. Use emerald only for confirmed safe, ready, profitable, connected, or successful states. Use rose only for danger, losses, rejected actions, kill-switch states, or destructive controls. Do not use saturated accent color for inactive decoration.

## Typography

Use the existing system sans stack: `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`. Keep product UI type fixed in `rem` or Tailwind text steps, not viewport-scaled. Use uppercase micro-labels sparingly for panel labels, status chips, and operational metadata. Use tabular numerals for prices, PnL, balances, timers, and scores.

## Layout

The primary layout is an operator workstation with persistent left navigation, a scrollable main workspace, compact metric cards, tables, side panels, and modal workflows. Desktop density is intentional. Do not add marketing heroes or explanatory feature sections to app screens.

Mobile and tablet behavior currently needs a larger responsive pass because the app uses a fixed minimum workstation width. Until that pass is approved, design new work for the existing desktop-first dashboard and avoid pretending narrow viewports are supported.

## Components

- Cards: 8px radius unless the existing component uses a larger tool-surface radius; avoid cards nested inside cards.
- Buttons: use Lucide icons for icon actions, clear text for dangerous or irreversible actions, and explicit labels for icon-only controls.
- Forms: visible labels, inline errors, disabled/loading states, and recovery text for failed operations.
- Tables: compact, sortable, and stable; prefer truncation with accessible full values for long wallet addresses or mints.
- Modals: use semantic dialogs, strong scrims, clear close controls, and confirmation for destructive actions.
- Alerts: pair color with copy and iconography; include the operator action when one exists.

## Motion

Motion should be short, stateful, and interruptible. Use Framer Motion for entry, exit, selection, panel, modal, toast, skeleton, and shared-layout transitions when it clarifies state. Default to spring transitions around 150-300ms. Respect `prefers-reduced-motion` through Framer Motion's `useReducedMotion` or CSS media queries. Avoid page-load choreography, decorative infinite motion, and animation of layout-heavy properties such as width, height, top, or left except where a constrained shared component already owns the behavior.

## Accessibility

Maintain visible `focus-visible` rings, semantic controls, `aria-label` for icon-only actions, `aria-live` for async operator messages, and `role="dialog"` / `aria-modal` for modals. Keep contrast at WCAG AA or better. Never rely on color alone for risk or status. Keep reduced-motion mode functional and visually stable.

## Anti-patterns

- Casino, hype, or game-like crypto visual language.
- Purple-blue AI gradient branding as the dominant theme.
- Decorative animation not tied to feedback, loading, reveal, or state.
- Hidden safety gates or ambiguous live-execution controls.
- Mobile claims without a real responsive layout pass.
