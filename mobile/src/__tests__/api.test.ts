import {
  fetchMobileCockpit,
  mobileWebSocketTicketUrl,
  requestMobileWebSocketTicket,
} from "../api";

describe("fetchMobileCockpit", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    jest.useRealTimers();
    Object.defineProperty(globalThis, "fetch", { configurable: true, value: originalFetch });
  });

  it("aborts and rejects with a sanitized error when the cockpit request exceeds its budget", async () => {
    jest.useFakeTimers();
    let requestSignal: AbortSignal | undefined;
    const fetchMock = jest.fn((_url: string | URL | Request, init?: RequestInit) => {
      requestSignal = init?.signal ?? undefined;
      return new Promise<Response>(() => undefined);
    });
    Object.defineProperty(globalThis, "fetch", { configurable: true, value: fetchMock });

    const requestOutcome = fetchMobileCockpit("https://cryptoarc.test", "mobile-secret-token").then(
      () => ({ kind: "resolved" as const, message: "" }),
      (err: unknown) => ({
        kind: "rejected" as const,
        message: err instanceof Error ? err.message : String(err),
      }),
    );

    await jest.advanceTimersByTimeAsync(10000);
    const outcome = await Promise.race([
      requestOutcome,
      Promise.resolve({ kind: "pending" as const, message: "" }),
    ]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(requestSignal?.aborted).toBe(true);
    expect(outcome).toEqual({ kind: "rejected", message: "Cockpit refresh timed out" });
    expect(outcome.message).not.toContain("mobile-secret-token");
    expect(outcome.message).not.toContain("cryptoarc.test");
    expect(jest.getTimerCount()).toBe(0);
  });
});

describe("mobile WebSocket tickets", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    Object.defineProperty(globalThis, "fetch", { configurable: true, value: originalFetch });
  });

  it("uses the bearer only in the ticket request header and puts only the one-time ticket in the URL", async () => {
    const fetchMock = jest.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({
        ticket: "one-time-ticket",
        scope: "mobile:monitor",
        ttl_seconds: 30,
      }),
    })) as unknown as typeof fetch;
    Object.defineProperty(globalThis, "fetch", { configurable: true, value: fetchMock });

    const issued = await requestMobileWebSocketTicket(
      "https://cryptoarc.test",
      "long-lived-bearer-secret",
    );
    const websocketUrl = mobileWebSocketTicketUrl(
      "https://cryptoarc.test",
      issued.ticket,
    );

    const [requestUrl, requestInit] = jest.mocked(fetchMock).mock.calls[0];
    const headers = new Headers(requestInit?.headers);
    expect(requestUrl).toBe("https://cryptoarc.test/api/mobile/ws-ticket");
    expect(requestInit?.method).toBe("POST");
    expect(headers.get("Authorization")).toBe("Bearer long-lived-bearer-secret");
    expect(websocketUrl).toBe("wss://cryptoarc.test/ws/mobile?ticket=one-time-ticket");
    expect(websocketUrl).not.toContain("long-lived-bearer-secret");
  });
});
