export type BotStatus = "stopped" | "running" | string;

export interface MobileDevice {
  id: string;
  name: string;
  platform: string;
  scopes: string[];
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  revoked_at: string;
}

export interface OperatorEvent {
  id: string;
  created_at: string;
  level: "info" | "warning" | "danger" | "error" | "success" | string;
  message: string;
  subsystem?: string;
  operator_action?: string;
}

export interface MobileCockpitPayload {
  artifact_type: "cryptoarc_mobile_cockpit";
  format_version: number;
  server_time: string;
  device?: MobileDevice | Record<string, unknown>;
  connection: {
    state: string;
    api: string;
    websocket: string;
    private_tunnel_required: boolean;
  };
  bot: {
    status: BotStatus;
    mode: string;
    launch_source: string;
    detected_tokens: number;
    auto_refresh: boolean;
  };
  source: {
    status?: string;
    status_message?: string;
    health_score?: number;
    trust_state?: string;
    events_per_minute?: number;
    last_event_age_seconds?: number | null;
    live_entry_blocked?: boolean;
    operator_action?: string;
  };
  readiness: {
    status?: string;
    score?: number;
    entries_allowed?: boolean;
    blockers: Array<Record<string, unknown>>;
    warnings: string[];
    sample_size?: Record<string, unknown>;
    paper_only?: boolean;
  };
  live: {
    kill_switch_enabled: boolean;
    blockers: string[];
    autonomy_blockers: string[];
    active_intent_count: number;
    unresolved_audit_count: number;
    recoverable_audit_count: number;
    mode_visibility?: Record<string, unknown>;
    full_sniper_gate?: Record<string, unknown>;
  };
  open_risk: {
    paper_open_positions: number;
    live_open_positions: number;
    active_live_intents: number;
    unresolved_live_audits: number;
    risk_blockers: string[];
  };
  pnl: {
    paper: {
      total_pnl_sol: number;
      win_rate_pct: number;
      closed_trades: number;
      open_positions: number;
      max_drawdown_sol: number;
    };
    live: {
      realized_pnl_sol: number;
      unrealized_pnl_sol: number;
      cost_basis_sol: number;
      open_positions: number;
      approximate: boolean;
    };
  };
  alerts: {
    telegram: Record<string, unknown>;
    latest: OperatorEvent[];
  };
  allowed_actions: {
    start: boolean;
    stop: boolean;
    kill_switch: boolean;
    clear_kill_switch: boolean;
    live_backend_arm: boolean;
    live_submit: boolean;
    hot_wallet_import: boolean;
  };
  next_operator_action: string;
}

export interface MobileFeedPayload {
  artifact_type: "cryptoarc_mobile_feed";
  format_version: number;
  generated_at: string;
  filters: Record<string, unknown>;
  summary: Record<string, unknown>;
  events: OperatorEvent[];
  action_items: string[];
}

export interface PairingClaimResponse {
  token: string;
  device: MobileDevice;
  scopes: string[];
  expires_at: string;
}

export interface MobilePairingPayload {
  artifact_type?: string;
  pairing_id?: string;
  code?: string;
  api_base_url?: string;
}
