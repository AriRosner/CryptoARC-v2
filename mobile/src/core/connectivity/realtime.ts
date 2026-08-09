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

function isCurrentCockpitSnapshot(
  envelope: MobileRealtimeEnvelope,
  nowMs: number,
): boolean {
  if (envelope.event_type !== "cockpit") return false;
  const artifactType = envelope.payload.artifact_type;
  const formatVersion = envelope.payload.format_version;
  const snapshotServerTime = envelope.payload.server_time;
  if (
    artifactType !== "cryptoarc_mobile_cockpit" ||
    formatVersion !== 1 ||
    typeof snapshotServerTime !== "string"
  ) {
    return false;
  }
  const snapshotServerTimeMs = Date.parse(snapshotServerTime);
  return (
    Number.isFinite(snapshotServerTimeMs) &&
    Math.abs(nowMs - snapshotServerTimeMs) <= MAX_CLOCK_DRIFT_MS
  );
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
  if (state.revoked) return state;
  if (state.requiresSnapshot) {
    if (
      envelope.sequence >= state.lastSequence &&
      isCurrentCockpitSnapshot(envelope, nowMs)
    ) {
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
    return state;
  }
  if (state.lastSequence > 0 && envelope.sequence > state.lastSequence + 1) {
    if (isCurrentCockpitSnapshot(envelope, nowMs)) {
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
  urlFactory: () => Promise<string>;
  initialState?: MobileRealtimeState;
  isAuthenticationError?: (error: unknown) => boolean;
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
  private requestPending = false;
  private socket: RealtimeSocket | null = null;
  private stopped = true;
  private state: MobileRealtimeState;
  private lifecycleGeneration = 0;

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
    if (this.socket !== null || this.reconnectTimer !== null || this.requestPending) return;
    this.updateState({ ...this.state, status: "connecting", reason: "" });
    const generation = this.lifecycleGeneration;
    this.requestPending = true;
    void this.openSocket(generation);
  }

  private async openSocket(generation: number): Promise<void> {
    try {
      const url = await this.options.urlFactory();
      if (this.stopped || generation !== this.lifecycleGeneration) return;
      this.requestPending = false;
      const socket = this.webSocketFactory(url);
      this.attachSocket(socket);
    } catch (error) {
      if (this.stopped || generation !== this.lifecycleGeneration) return;
      this.requestPending = false;
      if (this.options.isAuthenticationError?.(error)) {
        this.revoke();
        return;
      }
      this.updateState({ ...this.state, status: "offline", reason: "ticket_request_failed" });
      this.scheduleReconnect();
    }
  }

  private attachSocket(socket: RealtimeSocket): void {
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
      this.updateState({ ...this.state, status: "offline", reason: "connection_closed" });
      this.scheduleReconnect();
    };
  }

  disconnect(): void {
    this.stopped = true;
    this.lifecycleGeneration += 1;
    this.requestPending = false;
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
    this.lifecycleGeneration += 1;
    this.requestPending = false;
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
