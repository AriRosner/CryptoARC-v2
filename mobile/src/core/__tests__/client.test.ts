import { MobileApiError } from "../api/errors";
import { mobileAction, mobileGet } from "../api/client";

function jsonResponse(status: number, body: unknown, statusText = ""): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: jest.fn(async () => body),
  } as unknown as Response;
}

describe("mobile API client", () => {
  const originalFetch = globalThis.fetch;
  const fetchMock = jest.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    Object.defineProperty(globalThis, "fetch", { configurable: true, value: fetchMock });
  });

  afterAll(() => {
    Object.defineProperty(globalThis, "fetch", { configurable: true, value: originalFetch });
  });

  it("does not retry an ambiguous financial submission", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("network lost"));

    await expect(
      mobileAction("/api/mobile/trades/i1/approve", {
        apiBaseUrl: "https://cryptoarc.test",
        token: "mobile-token",
        idempotencyKey: "action-1",
        body: { expected_version: 3 },
      }),
    ).rejects.toMatchObject({
      category: "ambiguous_outcome",
      retryable: false,
      status: null,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends authentication and idempotency headers exactly once", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { action_id: "receipt-1", status: "confirmed" }));

    await expect(
      mobileAction<{ action_id: string }>("/api/mobile/actions/start", {
        apiBaseUrl: "https://cryptoarc.test/",
        token: "mobile-token",
        idempotencyKey: "action-1",
        body: { expected_version: 3 },
      }),
    ).resolves.toEqual({ action_id: "receipt-1", status: "confirmed" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(url).toBe("https://cryptoarc.test/api/mobile/actions/start");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ expected_version: 3 }));
    expect(headers.get("Authorization")).toBe("Bearer mobile-token");
    expect(headers.get("Idempotency-Key")).toBe("action-1");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    [401, "authentication", false],
    [403, "authorization", false],
    [409, "conflict", false],
    [412, "stale_state", false],
    [422, "validation", false],
    [429, "rate_limit", true],
    [500, "server", true],
  ] as const)("maps HTTP %s to %s", async (status, category, retryable) => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(status, {
        detail: "request rejected",
        action_id: "receipt-2",
      }),
    );

    const outcome = mobileGet("/api/mobile/cockpit", {
      apiBaseUrl: "https://cryptoarc.test",
      token: "mobile-token",
    });

    await expect(outcome).rejects.toBeInstanceOf(MobileApiError);
    await expect(outcome).rejects.toMatchObject({
      category,
      retryable,
      status,
      actionId: "receipt-2",
      message: "request rejected",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("marks a failed safe read as retryable without retrying inside the transport", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));

    await expect(
      mobileGet("/api/mobile/portfolio", {
        apiBaseUrl: "https://cryptoarc.test",
        token: "mobile-token",
      }),
    ).rejects.toMatchObject({
      category: "connection",
      retryable: true,
      status: null,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("requires a non-empty idempotency key before dispatch", async () => {
    await expect(
      mobileAction("/api/mobile/trades/i1/approve", {
        apiBaseUrl: "https://cryptoarc.test",
        token: "mobile-token",
        idempotencyKey: " ",
        body: {},
      }),
    ).rejects.toMatchObject({
      category: "validation",
      retryable: false,
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("never marks a server-rejected financial action as retryable", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(500, { detail: "receipt reconciliation required" }));

    await expect(
      mobileAction("/api/mobile/trades/i1/approve", {
        apiBaseUrl: "https://cryptoarc.test",
        token: "mobile-token",
        idempotencyKey: "action-1",
        body: { expected_version: 3 },
      }),
    ).rejects.toMatchObject({
      category: "server",
      retryable: false,
      status: 500,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
