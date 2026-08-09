import {
  MobileRealtimeClient,
  fullJitterReconnectDelay,
  initialRealtimeState,
  reduceRealtime,
} from "../connectivity/realtime";
import type { MobileRealtimeEnvelope } from "../connectivity/types";
import serverEnvelopeFixture from "../__fixtures__/mobile-realtime-envelope-v1.json";

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

  constructor(readonly url = "") {}

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
  it("accepts the backend v1 cockpit envelope contract fixture", () => {
    const state = reduceRealtime(
      initialRealtimeState,
      serverEnvelopeFixture as MobileRealtimeEnvelope,
      Date.parse(serverEnvelopeFixture.server_time),
    );

    expect(state).toMatchObject({
      lastSequence: 42,
      requiresSnapshot: false,
      status: "connected",
      reason: "",
    });
  });
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

  it("rebases a reconnect gap directly from the authenticated full cockpit snapshot", () => {
    const state = reduceRealtime(
      { ...initialRealtimeState, lastSequence: 8 },
      envelope({
        sequence: 12,
        event_type: "cockpit",
        payload: {
          artifact_type: "cryptoarc_mobile_cockpit",
          format_version: 1,
          server_time: "2026-07-28T12:00:00.000Z",
        },
      }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );

    expect(state).toMatchObject({
      lastSequence: 12,
      requiresSnapshot: false,
      status: "connected",
      reason: "",
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

  it("recovers a quarantined stream only from a current full cockpit snapshot", () => {
    const quarantined = reduceRealtime(
      { ...initialRealtimeState, lastSequence: 8 },
      envelope({ sequence: 10, event_type: "portfolio" }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );

    const unsupportedRecovery = reduceRealtime(
      quarantined,
      envelope({
        sequence: 10,
        event_type: "cockpit",
        schema_version: 2,
        payload: {
          artifact_type: "cryptoarc_mobile_cockpit",
          format_version: 1,
          server_time: "2026-07-28T12:00:00.000Z",
        },
      }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );
    expect(unsupportedRecovery).toMatchObject({
      lastSequence: 8,
      requiresSnapshot: true,
      status: "compatibility",
    });

    const recovered = reduceRealtime(
      quarantined,
      envelope({
        sequence: 10,
        event_type: "cockpit",
        payload: {
          artifact_type: "cryptoarc_mobile_cockpit",
          format_version: 1,
          server_time: "2026-07-28T12:00:00.000Z",
        },
      }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );
    expect(recovered).toMatchObject({
      lastSequence: 10,
      requiresSnapshot: false,
      status: "connected",
      reason: "",
    });

    const resumed = reduceRealtime(
      recovered,
      envelope({ sequence: 11, event_type: "portfolio" }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );
    const staleEnvelope = reduceRealtime(
      resumed,
      envelope({ sequence: 10, event_type: "portfolio" }),
      Date.parse("2026-07-28T12:00:00.000Z"),
    );
    expect(resumed.lastSequence).toBe(11);
    expect(staleEnvelope).toEqual(resumed);
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

  it("waits for and accepts a lower-sequence full baseline after backend restart", async () => {
    const socket = new FakeSocket();
    const invalidateQueries = jest.fn(async () => undefined);
    const client = new MobileRealtimeClient({
      urlFactory: async () => "wss://cryptoarc.test/ws/mobile?ticket=after-restart",
      initialState: { ...initialRealtimeState, lastSequence: 42 },
      webSocketFactory: () => socket,
      queryClient: { invalidateQueries },
      now: () => Date.parse("2026-07-28T12:00:00.000Z"),
    });

    client.connect();
    await Promise.resolve();
    await Promise.resolve();
    socket.emitOpen();
    expect(client.getState().status).toBe("connecting");

    socket.emitMessage(envelope({
      sequence: 1,
      event_type: "cockpit",
      payload: {
        artifact_type: "cryptoarc_mobile_cockpit",
        format_version: 1,
        server_time: "2026-07-28T12:00:00.000Z",
      },
    }));

    expect(client.getState()).toMatchObject({
      lastSequence: 1,
      requiresSnapshot: false,
      status: "connected",
    });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["mobile", "cockpit"] });
  });

  it("accepts an equal-sequence full baseline on a newly ticketed reconnect", async () => {
    const socket = new FakeSocket();
    const invalidateQueries = jest.fn(async () => undefined);
    const client = new MobileRealtimeClient({
      urlFactory: async () => "wss://cryptoarc.test/ws/mobile?ticket=reconnect",
      initialState: { ...initialRealtimeState, lastSequence: 8 },
      webSocketFactory: () => socket,
      queryClient: { invalidateQueries },
      now: () => Date.parse("2026-07-28T12:00:00.000Z"),
    });

    client.connect();
    await Promise.resolve();
    await Promise.resolve();
    socket.emitOpen();
    socket.emitMessage(envelope({
      sequence: 8,
      event_type: "cockpit",
      payload: {
        artifact_type: "cryptoarc_mobile_cockpit",
        format_version: 1,
        server_time: "2026-07-28T12:00:00.000Z",
      },
    }));

    expect(client.getState()).toMatchObject({ lastSequence: 8, status: "connected" });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["mobile", "cockpit"] });
  });

  it("does not create duplicate sockets and invalidates affected queries", async () => {
    const sockets: FakeSocket[] = [];
    const invalidateQueries = jest.fn(async () => undefined);
    const client = new MobileRealtimeClient({
      urlFactory: async () => "wss://cryptoarc.test/ws/mobile?ticket=one-time",
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
    await Promise.resolve();
    await Promise.resolve();
    expect(sockets).toHaveLength(1);

    sockets[0].emitOpen();
    sockets[0].emitMessage(envelope({
      event_type: "cockpit",
      payload: {
        artifact_type: "cryptoarc_mobile_cockpit",
        format_version: 1,
        server_time: "2026-07-28T12:00:00.000Z",
      },
    }));
    expect(client.getState()).toMatchObject({ lastSequence: 9, status: "connected" });
    sockets[0].emitMessage(envelope({ sequence: 10, event_type: "portfolio" }));
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["mobile", "portfolio"] });

    sockets[0].emitMessage(envelope({ sequence: 12 }));
    expect(client.getState()).toMatchObject({ requiresSnapshot: true, reason: "sequence_gap" });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["mobile"] });
  });

  it("does not invalidate queries for duplicate or out-of-order envelopes", async () => {
    const socket = new FakeSocket();
    const invalidateQueries = jest.fn(async () => undefined);
    const client = new MobileRealtimeClient({
      urlFactory: async () => "wss://cryptoarc.test/ws/mobile?ticket=one-time",
      initialState: { ...initialRealtimeState, lastSequence: 8 },
      webSocketFactory: () => socket,
      queryClient: { invalidateQueries },
      now: () => Date.parse("2026-07-28T12:00:00.000Z"),
    });

    client.connect();
    await Promise.resolve();
    await Promise.resolve();
    socket.emitMessage(envelope({
      sequence: 9,
      event_type: "cockpit",
      payload: {
        artifact_type: "cryptoarc_mobile_cockpit",
        format_version: 1,
        server_time: "2026-07-28T12:00:00.000Z",
      },
    }));
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
      urlFactory: async () => "wss://cryptoarc.test/ws/mobile?ticket=one-time",
      webSocketFactory: () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
      onRevoked,
      now: () => Date.parse("2026-07-28T12:00:00.000Z"),
    });

    client.connect();
    await Promise.resolve();
    await Promise.resolve();
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

  it("requests a fresh one-time ticket after an ordinary socket close", async () => {
    const sockets: FakeSocket[] = [];
    const onRevoked = jest.fn();
    const urlFactory = jest
      .fn<Promise<string>, []>()
      .mockResolvedValueOnce("wss://cryptoarc.test/ws/mobile?ticket=A")
      .mockResolvedValueOnce("wss://cryptoarc.test/ws/mobile?ticket=B");
    const client = new MobileRealtimeClient({
      urlFactory,
      random: () => 1,
      webSocketFactory: (url) => {
        const socket = new FakeSocket(url);
        sockets.push(socket);
        return socket;
      },
      onRevoked,
    });

    client.connect();
    await Promise.resolve();
    await Promise.resolve();
    expect(sockets.map((socket) => socket.url)).toEqual([
      "wss://cryptoarc.test/ws/mobile?ticket=A",
    ]);

    sockets[0].emitClose(1006);
    await jest.advanceTimersByTimeAsync(1000);

    expect(urlFactory).toHaveBeenCalledTimes(2);
    expect(sockets.map((socket) => socket.url)).toEqual([
      "wss://cryptoarc.test/ws/mobile?ticket=A",
      "wss://cryptoarc.test/ws/mobile?ticket=B",
    ]);
    expect(onRevoked).not.toHaveBeenCalled();
    expect(client.getState().revoked).toBe(false);
  });

  it("does not treat a generic policy close for a spent ticket as device revocation", async () => {
    const sockets: FakeSocket[] = [];
    const onRevoked = jest.fn();
    const urlFactory = jest
      .fn<Promise<string>, []>()
      .mockResolvedValueOnce("wss://cryptoarc.test/ws/mobile?ticket=spent")
      .mockResolvedValueOnce("wss://cryptoarc.test/ws/mobile?ticket=fresh");
    const client = new MobileRealtimeClient({
      urlFactory,
      random: () => 1,
      webSocketFactory: (url) => {
        const socket = new FakeSocket(url);
        sockets.push(socket);
        return socket;
      },
      onRevoked,
    });

    client.connect();
    await Promise.resolve();
    await Promise.resolve();
    sockets[0].emitClose(1008);
    await jest.advanceTimersByTimeAsync(1000);

    expect(urlFactory).toHaveBeenCalledTimes(2);
    expect(sockets).toHaveLength(2);
    expect(onRevoked).not.toHaveBeenCalled();
    expect(client.getState().revoked).toBe(false);
  });

  it("retries transient ticket acquisition failures with capped backoff", async () => {
    const sockets: FakeSocket[] = [];
    const urlFactory = jest
      .fn<Promise<string>, []>()
      .mockRejectedValueOnce(new Error("temporary tunnel failure"))
      .mockResolvedValueOnce("wss://cryptoarc.test/ws/mobile?ticket=recovered");
    const client = new MobileRealtimeClient({
      urlFactory,
      random: () => 1,
      webSocketFactory: (url) => {
        const socket = new FakeSocket(url);
        sockets.push(socket);
        return socket;
      },
    });

    client.connect();
    await Promise.resolve();
    await Promise.resolve();

    expect(client.getState()).toMatchObject({
      status: "offline",
      reason: "ticket_request_failed",
    });
    expect(jest.getTimerCount()).toBe(1);

    await jest.advanceTimersByTimeAsync(1000);
    expect(urlFactory).toHaveBeenCalledTimes(2);
    expect(sockets.map((socket) => socket.url)).toEqual([
      "wss://cryptoarc.test/ws/mobile?ticket=recovered",
    ]);
  });

  it("quarantines the session when authenticated ticket acquisition is denied", async () => {
    const authenticationFailure = Object.assign(new Error("session denied"), { status: 401 });
    const onRevoked = jest.fn();
    const client = new MobileRealtimeClient({
      urlFactory: jest.fn(async () => {
        throw authenticationFailure;
      }),
      isAuthenticationError: (error) =>
        typeof error === "object" &&
        error !== null &&
        "status" in error &&
        (error.status === 401 || error.status === 403),
      onRevoked,
    });

    client.connect();
    await Promise.resolve();
    await Promise.resolve();

    expect(onRevoked).toHaveBeenCalledTimes(1);
    expect(client.getState()).toMatchObject({
      revoked: true,
      status: "revoked",
      reason: "token_revoked",
    });
  });

  it("cleans up the socket and pending reconnect timer", async () => {
    const sockets: FakeSocket[] = [];
    const client = new MobileRealtimeClient({
      urlFactory: async () => "wss://cryptoarc.test/ws/mobile?ticket=one-time",
      random: () => 1,
      webSocketFactory: () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
    });

    client.connect();
    await Promise.resolve();
    await Promise.resolve();
    sockets[0].emitClose(1006);
    expect(jest.getTimerCount()).toBe(1);

    client.disconnect();
    await jest.runOnlyPendingTimersAsync();

    expect(jest.getTimerCount()).toBe(0);
    expect(sockets).toHaveLength(1);
  });
});
