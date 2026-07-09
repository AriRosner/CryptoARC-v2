import type { MobileCockpitPayload, OperatorEvent } from "./types";

export const sampleCockpit: MobileCockpitPayload = {
  artifact_type: "cryptoarc_mobile_cockpit",
  format_version: 1,
  server_time: "2026-07-02T20:00:00Z",
  connection: { state: "connected", api: "ok", websocket: "available", private_tunnel_required: true },
  bot: { status: "stopped", mode: "paper", launch_source: "pumpportal", detected_tokens: 12, auto_refresh: true },
  source: { status: "offline", status_message: "degraded", health_score: 42, trust_state: "degraded" },
  readiness: {
    status: "blocked",
    score: 48,
    entries_allowed: false,
    blockers: [{ id: "source_health", label: "Source health" }],
    warnings: ["Inspect source health."],
    paper_only: true,
  },
  live: {
    kill_switch_enabled: false,
    blockers: ["LIVE_TRADING_ENABLED is false"],
    autonomy_blockers: [],
    active_intent_count: 0,
    unresolved_audit_count: 1,
    recoverable_audit_count: 0,
  },
  open_risk: {
    paper_open_positions: 1,
    live_open_positions: 0,
    active_live_intents: 0,
    unresolved_live_audits: 1,
    risk_blockers: ["Unresolved live audit"],
  },
  pnl: {
    paper: { total_pnl_sol: 0.12, win_rate_pct: 55, closed_trades: 20, open_positions: 1, max_drawdown_sol: -0.04 },
    live: { realized_pnl_sol: 0, unrealized_pnl_sol: 0, cost_basis_sol: 0, open_positions: 0, approximate: true },
  },
  alerts: {
    telegram: { telegram_configured: true },
    latest: [],
  },
  allowed_actions: {
    start: true,
    stop: false,
    kill_switch: true,
    clear_kill_switch: true,
    live_backend_arm: false,
    live_submit: false,
    hot_wallet_import: false,
  },
  next_operator_action: "Inspect source health.",
};

export const sampleEvents: OperatorEvent[] = [
  { id: "evt1", created_at: "2026-07-02T20:00:00Z", level: "warning", subsystem: "source", message: "Source degraded" },
  { id: "evt2", created_at: "2026-07-02T20:01:00Z", level: "info", subsystem: "mobile", message: "Mobile cockpit started bot" },
  { id: "evt3", created_at: "2026-07-02T20:02:00Z", level: "danger", subsystem: "live", message: "Live kill switch enabled" },
];
