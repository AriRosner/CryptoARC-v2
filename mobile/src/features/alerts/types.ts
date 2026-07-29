export type MobileAlertSeverity = "info" | "warning" | "danger" | "error";

export interface MobileAlert {
  event_id: string;
  created_at: string;
  severity: MobileAlertSeverity;
  subsystem: string;
  title: string;
  summary: string;
  route: string;
  acknowledged: boolean;
  acknowledged_at: string | null;
}

export interface MobileAlertsPayload {
  artifact_type: "cryptoarc_mobile_alerts";
  format_version: 1;
  generated_at: string;
  alerts: MobileAlert[];
}

export interface PushRegistrationContext {
  apiBaseUrl: string;
  token: string;
  generation: number;
}

export interface PushRoutingData {
  event_id: string;
  severity: MobileAlertSeverity;
  subsystem: string;
  route: string;
}
