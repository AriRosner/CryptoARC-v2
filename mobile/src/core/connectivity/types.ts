export type MobileRealtimeEventType =
  | "cockpit"
  | "portfolio"
  | "position"
  | "trade"
  | "wallet"
  | "alert"
  | "invalidate";

export interface MobileRealtimeEnvelope {
  event_type: MobileRealtimeEventType;
  schema_version: number;
  server_time: string;
  sequence: number;
  entity_id?: string;
  payload: Record<string, unknown>;
}

export type MobileConnectionStatus =
  | "offline"
  | "connecting"
  | "connected"
  | "stale"
  | "compatibility"
  | "revoked";

export interface MobileRealtimeState {
  lastSequence: number;
  requiresSnapshot: boolean;
  revoked: boolean;
  status: MobileConnectionStatus;
  reason: string;
  clockDriftMs: number;
  lastServerTime: string;
}
