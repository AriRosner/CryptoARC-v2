# Local Signer Daemon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal localhost-only signer daemon that CryptoARC can probe safely before any autonomous live trading.

**Architecture:** Ship a standalone FastAPI daemon with bearer-authenticated health and execute endpoints. The first implementation keeps signing/submission guarded by explicit policy and keeps the bot disarmed until health and policy are verified.

**Tech Stack:** Python, FastAPI/Uvicorn, solders, unittest, PowerShell.

## Global Constraints

- Do not paste or store seed phrases in chat, docs, or logs.
- Keep signer daemon localhost-only.
- Default execute behavior must be deny-safe unless explicitly configured.
- Do not arm the backend or submit autonomous buys as part of this implementation.
- Use `scripts\verify.ps1` as the final gate.

---

### Task 1: Daemon Contract Tests

**Files:**
- Create: `tests/test_signer_daemon.py`
- Create: `tools/local_signer_daemon.py`

**Interfaces:**
- Produces: `create_app(config: SignerDaemonConfig) -> FastAPI`
- Produces: `SignerDaemonConfig` with auth, host, RPC, wallet, and policy fields

- [ ] **Step 1: Write failing tests for health/auth/local-only behavior.**
- [ ] **Step 2: Run `python -m unittest tests.test_signer_daemon -q` and verify it fails because the module does not exist.**
- [ ] **Step 3: Implement minimal daemon config and `/health`.**
- [ ] **Step 4: Re-run the test and verify it passes.**

### Task 2: Guarded Execute Endpoint

**Files:**
- Modify: `tools/local_signer_daemon.py`
- Modify: `tests/test_signer_daemon.py`

**Interfaces:**
- Consumes: `create_app(config)`
- Produces: `POST /execute` with bearer auth and deny-safe policy failures

- [ ] **Step 1: Write failing tests for missing transaction and submit-disabled rejection.**
- [ ] **Step 2: Run targeted tests and verify failure.**
- [ ] **Step 3: Implement minimal guarded execute response.**
- [ ] **Step 4: Run targeted tests and verify pass.**

### Task 3: Operator Scripts And Docs

**Files:**
- Create: `scripts/start-signer-daemon.ps1`
- Create: `scripts/check-signer-daemon.ps1`
- Modify: `docs/manual/10-wallets-and-live-trading.md`
- Modify: `docs/LIVE_TRADING_DESIGN.md`

**Interfaces:**
- Consumes: daemon CLI and `/health`
- Produces: no-trade startup and health-check commands

- [ ] **Step 1: Add wrappers that never print private key material.**
- [ ] **Step 2: Add docs for env vars, auth token, and no-trade smoke check.**
- [ ] **Step 3: Run docs link check through final verification.**

### Task 4: Verification

**Files:**
- No direct edits unless verification exposes a narrow bug.

- [ ] **Step 1: Run targeted daemon tests.**
- [ ] **Step 2: Run relevant backend tests.**
- [ ] **Step 3: Run `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`.**
- [ ] **Step 4: Commit and push only after the gate passes.**
