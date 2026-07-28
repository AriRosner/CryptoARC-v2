import type {
  MobileRealtimeEnvelope,
  MobileRealtimeEventType,
  MobileRealtimeState,
} from "./types";

const RECONNECT_CAPS_MS = [1000, 2000, 4000, 8000, 16000, 30000] as const;
const MAX_CLOCK_DRIFT_MS = 30000;

export const initialRealtimeState: MobileRealtimeState = {
  lastSequence: 0,
  requiresSnapshot: false,
  revoked: false,
  status: "offline",
  reason: "",
  clockDriftMs: 0,
  lastServerTime: "",
};

export function fullJitterReconnectDelay(attempt: number, random: () => number = Math.random): number {
  const cap = RECONNECT_CAPS_MS[Math.min(Math.max(0, attempt), RECONNECT_CAPS_MS.length - 1)];
  const sample = Math.min(1, Math.max(0, random()));
  return Math.floor(cap * sample);
}

function invalidState(
  state: MobileRealtimeState,
  status: MobileRealtimeState["status"],
  reason: string,
  extra: Partial<MobileRealtimeState> = {},
): MobileRealtimeState {
  return { ...state, requiresSnapshot: true, status, reason, ...extra };
}

export function reduceRealtime(
  state: MobileRealtimeState,
  envelope: MobileRealtimeEnvelope,
  nowMs = Date.now(),
): MobileRealtimeState {
  if (envelope.schema_version !== 1) return invalidState(state, "compatibility", "schema_mismatch");
  if (!Number.isInteger(envelope.sequence) || envelope.sequence < 1) {
    return invalidState(state, "compatibility", "invalid_sequence");
  }
  const serverTimeMs = Date.parse(envelope.server_time);
  if (!Number.isFinite(serverTimeMs)) return invalidState(state, "compatibility", "invalid_server_time");
  const clockDriftMs = Math.abs(nowMs - serverTimeMs);
  if (clockDriftMs > MAX_CLOCK_DRIFT_MS) {
    return invalidState(state, "stale", "clock_drift", {
      clockDriftMs,
      lastServerTime: envelope.server_time,
    });
  }
  if (envelope.event_type === "invalidate" && envelope.payload.reason === "token_revoked") {
    return invalidState(state, "revoked", "token_revoked", {
      clockDriftMs,
      lastServerTime: envelope.server_time,
      revoked: true,
    });
  }
  if (state.revoked || state.requiresSnapshot) return state;
  if (state.lastSequence > 0 && envelope.sequence > state.lastSequence + 1) {
    return invalidState(state, "stale", "sequence_gap", {
      clockDriftMs,
      lastServerTime: envelope.server_time,
    });
  }
  if (envelope.sequence <= state.lastSequence) return state;
  if (envelope.event_type === "invalidate") {
    return invalidState(state, "stale", "server_invalidation", {
      clockDriftMs,
      lastSequence: envelope.sequence,
      lastServerTime: envelope.server_time,
    });
  }
  return {
    ...state,
    clockDriftMs,
    lastSequence: envelope.sequence,
    lastServerTime: envelope.server_time,
    reason: "",
    requiresSnapshot: false,
    status: "connected",
  };
}

interface RealtimeSocket {
  readyState: number;
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onerror: (() => void) | null;
  onclose: ((event: { code: number }) => void) | null;
  close(): void;
}

interface QueryInvalidator {
  invalidateQueries(options: { queryKey: readonly string[] }): Promise<unknown>;
}

interface MobileRealtimeClientOptions {
  url: string;
  initialState?: MobileRealtimeState;
  now?: () => number;
  onRevoked?: () => void;
  onStateChange?: (state: MobileRealtimeState) => void;
  queryClient?: QueryInvalidator;
  random?: () => number;
  webSocketFactory?: (url: string) => RealtimeSocket;
}

const eventQueryKeys: Record<Exclude<MobileRealtimeEventType, "invalidate">, readonly string[]> = {
  alert: ["mobile", "alert"],
  cockpit: ["mobile", "cockpit"],
  portfolio: ["mobile", "portfolio"],
  position: ["mobile", "position"],
  trade: ["mobile", "trade"],
  wallet: ["mobile", "wallet"],
};
const mobileRealtimeEventTypes = new Set<MobileRealtimeEventType>([
  "alert",
  "cockpit",
  "invalidate",
  "portfolio",
  "position",
  "trade",
  "wallet",
]);

function isEnvelope(value: unknown): value is MobileRealtimeEnvelope {
  if (!value || typeof value !== "object") return false;
  const envelope = value as Partial<MobileRealtimeEnvelope>;
  return (
    typeof envelope.event_type === "string" &&
    mobileRealtimeEventTypes.has(envelope.event_type as MobileRealtimeEventType) &&
    typeof envelope.schema_version === "number" &&
    typeof envelope.server_time === "string" &&
    typeof envelope.sequence === "number" &&
    envelope.payload !== null &&
    typeof envelope.payload === "object"
  );
}

export class MobileRealtimeClient {
  private readonly now: () => number;
  private readonly onStateChange?: (state: MobileRealtimeState) => void;
  private readonly queryClient?: QueryInvalidator;
  private readonly random: () => number;
  private readonly webSocketFactory: (url: string) => RealtimeSocket;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private socket: RealtimeSocket | null = null;
  private stopped = true;
  private state: MobileRealtimeState;

  constructor(private readonly options: MobileRealtimeClientOptions) {
    this.state = options.initialState ?? initialRealtimeState;
    this.now = options.now ?? Date.now;
    this.onStateChange = options.onStateChange;
    this.queryClient = options.queryClient;
    this.random = options.random ?? Math.random;
    this.webSocketFactory =
      options.webSocketFactory ?? ((url) => new WebSocket(url) as unknown as RealtimeSocket);
  }

  getState(): MobileRealtimeState {
    return this.state;
  }

  connect(): void {
    if (this.state.revoked) return;
    this.stopped = false;
    if (this.socket !== null || this.reconnectTimer !== null) return;
    this.updateState({ ...this.state, status: "connecting", reason: "" });
    const socket = this.webSocketFactory(this.options.url);
    this.socket = socket;
    socket.onopen = () => {
      if (this.socket !== socket || this.stopped) return;
      this.reconnectAttempt = 0;
      if (!this.state.requiresSnapshot) {
        this.updateState({ ...this.state, status: "connected", reason: "" });
      }
    };
    socket.onmessage = (event) => {
      if (this.socket !== socket || this.stopped) return;
      this.onMessage(event.data);
    };
    socket.onerror = () => {
      if (this.socket === socket && !this.stopped) {
        this.updateState({ ...this.state, status: "offline", reason: "connection_error" });
      }
    };
    socket.onclose = (event) => {
      if (this.socket !== socket) return;
      this.socket = null;
      if (this.stopped) return;
      if (event.code === 1008) {
        this.revoke();
        return;
      }
      this.updateState({ ...this.state, status: "offline", reason: "connection_closed" });
      this.scheduleReconnect();
    };
  }

  disconnect(): void {
    this.stopped = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    const socket = this.socket;
    this.socket = null;
    if (socket !== null) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      socket.close();
    }
    if (!this.state.revoked) {
      this.updateState({ ...this.state, status: "offline", reason: "" });
    }
  }

  private onMessage(data: unknown): void {
    let value: unknown;
    try {
      value = JSON.parse(String(data));
    } catch {
      this.updateState(invalidState(this.state, "compatibility", "invalid_payload"));
      this.invalidateAll();
      return;
    }
    if (!isEnvelope(value)) {
      this.updateState(invalidState(this.state, "compatibility", "invalid_payload"));
      this.invalidateAll();
      return;
    }
    const next = reduceRealtime(this.state, value, this.now());
    const stateAdvanced = next !== this.state;
    this.updateState(next);
    if (next.revoked) {
      this.revoke();
      return;
    }
    if (next.requiresSnapshot) {
      this.invalidateAll();
    } else if (stateAdvanced && value.event_type !== "invalidate") {
      void this.queryClient?.invalidateQueries({ queryKey: eventQueryKeys[value.event_type] });
    }
  }

  private invalidateAll(): void {
    void this.queryClient?.invalidateQueries({ queryKey: ["mobile"] });
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.state.revoked || this.reconnectTimer !== null) return;
    const delay = fullJitterReconnectDelay(this.reconnectAttempt, this.random);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private updateState(state: MobileRealtimeState): void {
    this.state = state;
    this.onStateChange?.(state);
  }

  private revoke(): void {
    if (!this.state.revoked) {
      this.updateState(
        invalidState(this.state, "revoked", "token_revoked", {
          revoked: true,
        }),
      );
    }
    this.stopped = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    const socket = this.socket;
    this.socket = null;
    if (socket !== null) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      socket.close();
    }
    this.invalidateAll();
    this.options.onRevoked?.();
  }
}
