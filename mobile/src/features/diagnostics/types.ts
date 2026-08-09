export type MobileDiagnosticStatus =
  | "healthy"
  | "warning"
  | "blocked"
  | "unavailable";

export interface MobileDiagnosticCheck {
  id:
    | "tunnel"
    | "api"
    | "websocket"
    | "token_scope"
    | "push"
    | "telegram"
    | "clock_drift"
    | "snapshot_age"
    | "rpc"
    | "signer";
  label: string;
  status: MobileDiagnosticStatus;
  detail: string;
  observed_at: string | null;
}

export interface MobileDiagnosticsPayload {
  artifact_type: "cryptoarc_mobile_diagnostics";
  format_version: 1;
  generated_at: string;
  freshness: {
    status: "fresh" | "stale" | "unavailable";
    age_seconds: number | null;
    stale_after_seconds: number;
  };
  checks: MobileDiagnosticCheck[];
  recovery_actions: Array<{
    id: string;
    label: string;
    detail: string;
    enabled: boolean;
  }>;
}
