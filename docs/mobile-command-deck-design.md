# Mobile Command Deck Design

## Goal

Upgrade the CryptoARC mobile app from a basic companion shell into a safety-first operator cockpit. The app should feel dense, calm, and useful on Android without becoming flashy or casino-like.

## Direction

- Preserve the workstation identity: dark surfaces, amber actions, emerald ready states, rose danger, blue connectivity.
- Lead with safety state, then evidence, then controls.
- Add purposeful motion for connection, loading, press feedback, screen/card entry, lock/unlock, and event updates.
- Keep motion short and readable; no decorative crypto spectacle.

## Feature Pass

- Cockpit gets a command header, live pulse, score strip, blocker stack, quick telemetry, alert preview, and guarded controls.
- Feed gets severity chips, event expansion, summary counts, and richer empty states.
- Risk gets a kill-switch command panel, blocker/audit/recovery summaries, and stronger destructive-state emphasis.
- Device gets tunnel/session diagnostics, WebSocket status, token scope details, and clearer disconnect guidance.
- Pairing gets a clearer step flow for tunnel check, QR scan, and manual code fallback.

## Component System

Add reusable animated primitives: screen shell, animated section, progress bar, connection indicator, segmented control, detail rows, and refined action buttons. Components must keep stable dimensions and readable labels.

## Verification

Run mobile TypeScript, mobile tests, Expo diagnostics, Android export sanity, and full repo verification if backend/frontend surfaces are touched.
