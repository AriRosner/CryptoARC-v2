import { fetchMobileCockpit } from "../api";

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
