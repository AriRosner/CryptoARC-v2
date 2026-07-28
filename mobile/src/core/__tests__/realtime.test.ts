import {
  MobileRealtimeClient,
  fullJitterReconnectDelay,
  initialRealtimeState,
  reduceRealtime,
} from "../connectivity/realtime";
import type { MobileRealtimeEnvelope } from "../connectivity/types";

function envelope(overrides: Partial<MobileRealtimeEnvelope> = {}): MobileRealtimeEnvelope {
  return {
    sequence: 9,
    schema_version: 1,
    event_type: "portfolio",
    server_time: "2026-07-28T12:00:00.000Z",
    payload: {},
    ...overrides,
  };
}

class FakeSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readyState = FakeSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  close = jest.fn(() => {
    this.readyState = FakeSocket.CLOSED;
  });

  emitOpen() {
    this.readyState = FakeSocket.OPEN;
    this.onopen?.();
  }

  emitMessage(value: unknown) {
    this.onmessage?.({ data: JSON.stringify(value) });
  }

  emitClose(code: number) {
    this.readyState = FakeSocket.CLOSED;
    this.onclose?.({ code });
  }
}

describe("realtime reducer", () => {
  it("invalidates on a sequence gap", () => {
    const state = reduceRealtime(
      { ...initialRealtimeState, lastSequence: 8 },
      envelope({ sequence: 10 }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );

    expect(state).toMatchObject({
      lastSequence: 8,
      requiresSnapshot: true,
      status: "stale",
      reason: "sequence_gap",
    });
  });

  it("fails closed on an unknown schema version", () => {
    const state = reduceRealtime(
      { ...initialRealtimeState, lastSequence: 8 },
      envelope({ schema_version: 2 }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );

    expect(state).toMatchObject({
      lastSequence: 8,
      requiresSnapshot: true,
      status: "compatibility",
      reason: "schema_mismatch",
    });
  });

  it("marks a revoked session and requires a fresh authenticated snapshot", () => {
    const state = reduceRealtime(
      { ...initialRealtimeState, lastSequence: 8 },
      envelope({
        event_type: "invalidate",
        payload: { reason: "token_revoked" },
      }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );

    expect(state).toMatchObject({
      revoked: true,
      requiresSnapshot: true,
      status: "revoked",
      reason: "token_revoked",
    });
  });

  it("invalidates when server clock drift exceeds thirty seconds", () => {
    const state = reduceRealtime(
      { ...initialRealtimeState, lastSequence: 8 },
      envelope({ server_time: "2026-07-28T11:59:29.999Z" }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );

    expect(state).toMatchObject({
      requiresSnapshot: true,
      status: "stale",
      reason: "clock_drift",
    });
    expect(state.clockDriftMs).toBe(30001);
  });

  it("accepts an in-order event at the clock-drift boundary", () => {
    const state = reduceRealtime(
      { ...initialRealtimeState, lastSequence: 8 },
      envelope({ server_time: "2026-07-28T11:59:30.000Z" }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );

    expect(state).toMatchObject({
      lastSequence: 9,
      requiresSnapshot: false,
      status: "connected",
      reason: "",
      clockDriftMs: 30000,
    });
  });

  it("does not treat a later delta as recovery from a required full snapshot", () => {
    const stale = reduceRealtime(
      { ...initialRealtimeState, lastSequence: 8 },
      envelope({ sequence: 10 }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );

    const stillStale = reduceRealtime(
      stale,
      envelope({ sequence: 9 }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );

    expect(stillStale).toEqual(stale);
    expect(stillStale).toMatchObject({
      lastSequence: 8,
      requiresSnapshot: true,
      reason: "sequence_gap",
    });
  });

  it("uses capped full-jitter reconnect delays", () => {
    expect([0, 1, 2, 3, 4, 5, 6].map((attempt) => fullJitterReconnectDelay(attempt, () => 1))).toEqual([
      1000, 2000, 4000, 8000, 16000, 30000, 30000,
    ]);
    expect(fullJitterReconnectDelay(3, () => 0.25)).toBe(2000);
  });
});

describe("MobileRealtimeClient", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("does not create duplicate sockets and invalidates affected queries", () => {
    const sockets: FakeSocket[] = [];
    const invalidateQueries = jest.fn(async () => undefined);
    const client = new MobileRealtimeClient({
      url: "wss://cryptoarc.test/ws/mobile?ticket=one-time",
      initialState: { ...initialRealtimeState, lastSequence: 8 },
      webSocketFactory: () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
      queryClient: { invalidateQueries },
      now: () => Date.parse("2026-07-28T12:00:00.000Z"),
    });

    client.connect();
    client.connect();
    expect(sockets).toHaveLength(1);

    sockets[0].emitOpen();
    sockets[0].emitMessage(envelope());
    expect(client.getState()).toMatchObject({ lastSequence: 9, status: "connected" });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["mobile", "portfolio"] });

    sockets[0].emitMessage(envelope({ sequence: 11 }));
    expect(client.getState()).toMatchObject({ requiresSnapshot: true, reason: "sequence_gap" });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["mobile"] });
  });

  it("does not invalidate queries for duplicate or out-of-order envelopes", () => {
    const socket = new FakeSocket();
    const invalidateQueries = jest.fn(async () => undefined);
    const client = new MobileRealtimeClient({
      url: "wss://cryptoarc.test/ws/mobile?ticket=one-time",
      initialState: { ...initialRealtimeState, lastSequence: 8 },
      webSocketFactory: () => socket,
      queryClient: { invalidateQueries },
      now: () => Date.parse("2026-07-28T12:00:00.000Z"),
    });

    client.connect();
    socket.emitMessage(envelope({ sequence: 9 }));
    invalidateQueries.mockClear();

    socket.emitMessage(envelope({ sequence: 9 }));
    socket.emitMessage(envelope({ sequence: 8 }));

    expect(client.getState().lastSequence).toBe(9);
    expect(invalidateQueries).not.toHaveBeenCalled();
  });

  it("closes and permanently stops after an envelope revokes the session", async () => {
    const sockets: FakeSocket[] = [];
    const onRevoked = jest.fn();
    const client = new MobileRealtimeClient({
      url: "wss://cryptoarc.test/ws/mobile?ticket=one-time",
      webSocketFactory: () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
      onRevoked,
      now: () => Date.parse("2026-07-28T12:00:00.000Z"),
    });

    client.connect();
    sockets[0].emitMessage(
      envelope({
        event_type: "invalidate",
        payload: { reason: "token_revoked" },
      }),
    );
    client.connect();
    await jest.runOnlyPendingTimersAsync();

    expect(sockets[0].close).toHaveBeenCalledTimes(1);
    expect(sockets).toHaveLength(1);
    expect(onRevoked).toHaveBeenCalledTimes(1);
    expect(client.getState()).toMatchObject({ revoked: true, status: "revoked" });
  });

  it("treats policy-close as revocation and does not reconnect", async () => {
    const sockets: FakeSocket[] = [];
    const invalidateQueries = jest.fn(async () => undefined);
    const client = new MobileRealtimeClient({
      url: "wss://cryptoarc.test/ws/mobile?ticket=one-time",
      webSocketFactory: () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
      queryClient: { invalidateQueries },
    });

    client.connect();
    sockets[0].emitClose(1008);
    await jest.runOnlyPendingTimersAsync();

    expect(client.getState()).toMatchObject({
      revoked: true,
      requiresSnapshot: true,
      status: "revoked",
      reason: "token_revoked",
    });
    expect(sockets).toHaveLength(1);
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["mobile"] });
  });

  it("cleans up the socket and pending reconnect timer", async () => {
    const sockets: FakeSocket[] = [];
    const client = new MobileRealtimeClient({
      url: "wss://cryptoarc.test/ws/mobile?ticket=one-time",
      random: () => 1,
      webSocketFactory: () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
    });

    client.connect();
    sockets[0].emitClose(1006);
    expect(jest.getTimerCount()).toBe(1);

    client.disconnect();
    await jest.runOnlyPendingTimersAsync();

    expect(jest.getTimerCount()).toBe(0);
    expect(sockets).toHaveLength(1);
  });
});
