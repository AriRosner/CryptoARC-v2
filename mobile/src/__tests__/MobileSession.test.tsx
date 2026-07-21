import * as SecureStore from "expo-secure-store";
import { act, render, waitFor } from "@testing-library/react-native";
import React, { useEffect } from "react";

import { claimMobilePairing, fetchMobileCockpit } from "../api";
import { MobileSessionProvider, useMobileSession } from "../MobileSession";
import { sampleCockpit } from "../testPayloads";

jest.mock("../api", () => ({
  ...jest.requireActual("../api"),
  claimMobilePairing: jest.fn(),
  fetchMobileCockpit: jest.fn(),
  mobileWebSocketUrl: jest.fn(() => "ws://localhost/mobile"),
}));

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: Error) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

type SessionValue = ReturnType<typeof useMobileSession>;

function SessionProbe({ onSessionReady }: { onSessionReady: (session: SessionValue) => void }) {
  const session = useMobileSession();

  useEffect(() => {
    onSessionReady(session);
  }, [onSessionReady, session]);

  return null;
}

class MockWebSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  close = jest.fn();
}

describe("MobileSessionProvider cockpit refresh", () => {
  const claimMobilePairingMock = jest.mocked(claimMobilePairing);
  const fetchMobileCockpitMock = jest.mocked(fetchMobileCockpit);
  const getItemAsyncMock = jest.mocked(SecureStore.getItemAsync);
  const setItemAsyncMock = jest.mocked(SecureStore.setItemAsync);
  const deleteItemAsyncMock = jest.mocked(SecureStore.deleteItemAsync);

  beforeEach(() => {
    jest.clearAllMocks();
    Object.defineProperty(globalThis, "WebSocket", { configurable: true, value: MockWebSocket });
    setItemAsyncMock.mockResolvedValue(undefined);
    deleteItemAsyncMock.mockResolvedValue(undefined);
    getItemAsyncMock.mockImplementation(async (key) => {
      if (key === "cryptoarc.mobile.token") return "mobile-token";
      if (key === "cryptoarc.mobile.apiBaseUrl") return "https://cryptoarc.test";
      if (key === "cryptoarc.mobile.device") return null;
      return null;
    });
  });

  it("coalesces overlapping refreshes and releases the guard after success", async () => {
    const firstRequest = deferred<typeof sampleCockpit>();
    fetchMobileCockpitMock.mockReturnValueOnce(firstRequest.promise).mockResolvedValue(sampleCockpit);
    let session: SessionValue | undefined;
    const onSessionReady = (nextSession: SessionValue) => {
      session = nextSession;
    };

    const view = await render(
      <MobileSessionProvider>
        <SessionProbe onSessionReady={onSessionReady} />
      </MobileSessionProvider>,
    );

    await waitFor(() => expect(fetchMobileCockpitMock).toHaveBeenCalledTimes(1));
    expect(session).toBeDefined();

    let overlappingRefreshes!: Promise<void[]>;
    await act(async () => {
      overlappingRefreshes = Promise.all([session!.refreshCockpit(), session!.refreshCockpit()]);
    });
    const fetchesWhilePending = fetchMobileCockpitMock.mock.calls.length;

    firstRequest.resolve(sampleCockpit);
    await act(async () => {
      await overlappingRefreshes;
    });

    await act(async () => {
      await session!.refreshCockpit();
    });
    const fetchesAfterRelease = fetchMobileCockpitMock.mock.calls.length;
    view.unmount();

    expect(fetchesWhilePending).toBe(1);
    expect(fetchesAfterRelease).toBe(2);
  });

  it("releases the guard after a failed refresh", async () => {
    const firstRequest = deferred<typeof sampleCockpit>();
    fetchMobileCockpitMock.mockReturnValueOnce(firstRequest.promise).mockResolvedValue(sampleCockpit);
    let session: SessionValue | undefined;
    const onSessionReady = (nextSession: SessionValue) => {
      session = nextSession;
    };

    const view = await render(
      <MobileSessionProvider>
        <SessionProbe onSessionReady={onSessionReady} />
      </MobileSessionProvider>,
    );

    await waitFor(() => expect(fetchMobileCockpitMock).toHaveBeenCalledTimes(1));
    expect(session).toBeDefined();

    let overlappingRefresh!: Promise<void>;
    await act(async () => {
      overlappingRefresh = session!.refreshCockpit();
    });
    const fetchesWhilePending = fetchMobileCockpitMock.mock.calls.length;

    firstRequest.reject(new Error("Cockpit refresh timed out"));
    await act(async () => {
      await overlappingRefresh;
    });
    expect(session?.error).toBe("Cockpit refresh timed out");

    await act(async () => {
      await session!.refreshCockpit();
    });
    const fetchesAfterRelease = fetchMobileCockpitMock.mock.calls.length;
    const errorAfterRelease = session?.error;
    view.unmount();

    expect(fetchesWhilePending).toBe(1);
    expect(fetchesAfterRelease).toBe(2);
    expect(errorAfterRelease).toBe("");
  });

  it.each(["success", "failure"] as const)(
    "lets a re-paired session refresh while the cleared session finishes with late %s",
    async (oldRequestOutcome) => {
      const oldRequest = deferred<typeof sampleCockpit>();
      const newPayload = {
        ...sampleCockpit,
        server_time: "2026-07-20T21:00:00Z",
        connection: { ...sampleCockpit.connection, state: "new-session-connected" },
      };
      fetchMobileCockpitMock.mockReturnValueOnce(oldRequest.promise).mockResolvedValue(newPayload);
      claimMobilePairingMock.mockResolvedValue({
        token: "new-mobile-token",
        scopes: ["mobile:read"],
        expires_at: "2026-08-20T20:00:00Z",
        device: {
          id: "mobile-new",
          name: "New Android cockpit",
          platform: "android",
          scopes: ["mobile:read"],
          created_at: "2026-07-20T20:00:00Z",
          last_seen_at: "2026-07-20T20:00:00Z",
          expires_at: "2026-08-20T20:00:00Z",
          revoked_at: "",
        },
      });
      let session: SessionValue | undefined;
      const onSessionReady = (nextSession: SessionValue) => {
        session = nextSession;
      };

      const view = await render(
        <MobileSessionProvider>
          <SessionProbe onSessionReady={onSessionReady} />
        </MobileSessionProvider>,
      );

      await waitFor(() => expect(fetchMobileCockpitMock).toHaveBeenCalledTimes(1));
      await act(async () => {
        await session!.clearSession();
        await session!.pairWithManualCode({
          apiBaseUrl: "https://cryptoarc-new.test",
          pairingId: "pair-new",
          code: "123456",
          deviceName: "New Android cockpit",
        });
      });

      await waitFor(() => expect(fetchMobileCockpitMock).toHaveBeenCalledTimes(2));
      await waitFor(() => expect(session?.cockpit).toEqual(newPayload));
      expect(session?.token).toBe("new-mobile-token");
      expect(session?.connected).toBe(true);
      expect(session?.error).toBe("");

      if (oldRequestOutcome === "success") {
        oldRequest.resolve({ ...sampleCockpit, server_time: "stale-old-session" });
      } else {
        oldRequest.reject(new Error("stale old-session failure"));
      }
      await act(async () => {
        await Promise.resolve();
      });

      expect(session?.cockpit).toEqual(newPayload);
      expect(session?.connected).toBe(true);
      expect(session?.error).toBe("");
      view.unmount();
    },
  );

  it("restores the existing session with a fresh epoch when replacement persistence fails", async () => {
    const originalRequest = deferred<typeof sampleCockpit>();
    const recoveredPayload = { ...sampleCockpit, server_time: "recovered-old-session" };
    fetchMobileCockpitMock.mockReturnValueOnce(originalRequest.promise).mockResolvedValue(recoveredPayload);
    claimMobilePairingMock.mockResolvedValue({
      token: "replacement-token",
      scopes: ["mobile:read"],
      expires_at: "2026-08-20T20:00:00Z",
      device: {
        id: "mobile-replacement",
        name: "Replacement Android cockpit",
        platform: "android",
        scopes: ["mobile:read"],
        created_at: "2026-07-20T20:00:00Z",
        last_seen_at: "2026-07-20T20:00:00Z",
        expires_at: "2026-08-20T20:00:00Z",
        revoked_at: "",
      },
    });
    setItemAsyncMock.mockRejectedValueOnce(new Error("secure store unavailable"));
    let session: SessionValue | undefined;
    const onSessionReady = (nextSession: SessionValue) => {
      session = nextSession;
    };

    const view = await render(
      <MobileSessionProvider>
        <SessionProbe onSessionReady={onSessionReady} />
      </MobileSessionProvider>,
    );

    await waitFor(() => expect(fetchMobileCockpitMock).toHaveBeenCalledTimes(1));
    await act(async () => {
      await expect(
        session!.pairWithManualCode({
          apiBaseUrl: "https://cryptoarc-replacement.test",
          pairingId: "pair-replacement",
          code: "123456",
          deviceName: "Replacement Android cockpit",
        }),
      ).rejects.toThrow("secure store unavailable");
    });
    expect(session?.token).toBe("mobile-token");

    await act(async () => {
      await session!.refreshCockpit();
    });
    expect(fetchMobileCockpitMock).toHaveBeenCalledTimes(2);
    expect(session?.cockpit).toEqual(recoveredPayload);

    originalRequest.resolve({ ...sampleCockpit, server_time: "stale-before-replacement" });
    await act(async () => {
      await Promise.resolve();
    });
    expect(session?.cockpit).toEqual(recoveredPayload);
    expect(session?.connected).toBe(true);
    expect(session?.error).toBe("");
    view.unmount();
  });

  it.each([
    { failedWrite: 1, priorDeviceStored: true },
    { failedWrite: 2, priorDeviceStored: false },
    { failedWrite: 3, priorDeviceStored: true },
  ])(
    "rolls back durable session data when replacement write $failedWrite fails",
    async ({ failedWrite, priorDeviceStored }) => {
      const oldDevice = {
        id: "mobile-old",
        name: "Old Android cockpit",
        platform: "android",
        scopes: ["mobile:read"],
        created_at: "2026-07-01T20:00:00Z",
        last_seen_at: "2026-07-01T20:00:00Z",
        expires_at: "2026-08-01T20:00:00Z",
        revoked_at: "",
      };
      const replacementDevice = {
        ...oldDevice,
        id: "mobile-replacement",
        name: "Replacement Android cockpit",
      };
      const storedValues = new Map<string, string>([
        ["cryptoarc.mobile.apiBaseUrl", "https://cryptoarc-old.test"],
        ["cryptoarc.mobile.token", "old-mobile-token"],
      ]);
      if (priorDeviceStored) {
        storedValues.set("cryptoarc.mobile.device", JSON.stringify(oldDevice));
      }
      getItemAsyncMock.mockImplementation(async (key) => storedValues.get(key) ?? null);
      deleteItemAsyncMock.mockImplementation(async (key) => {
        storedValues.delete(key);
      });
      let replacementWriteCount = 0;
      const persistenceError = new Error(`replacement write ${failedWrite} failed`);
      setItemAsyncMock.mockImplementation(async (key, value) => {
        replacementWriteCount += 1;
        if (replacementWriteCount === failedWrite) throw persistenceError;
        storedValues.set(key, value);
      });
      claimMobilePairingMock.mockResolvedValue({
        token: "replacement-token",
        scopes: ["mobile:read"],
        expires_at: "2026-08-20T20:00:00Z",
        device: replacementDevice,
      });
      const oldPayload = { ...sampleCockpit, server_time: `old-session-write-${failedWrite}` };
      fetchMobileCockpitMock.mockResolvedValue(oldPayload);
      let session: SessionValue | undefined;
      const onSessionReady = (nextSession: SessionValue) => {
        session = nextSession;
      };

      const firstView = await render(
        <MobileSessionProvider>
          <SessionProbe onSessionReady={onSessionReady} />
        </MobileSessionProvider>,
      );
      await waitFor(() => expect(fetchMobileCockpitMock).toHaveBeenCalledTimes(1));

      await act(async () => {
        await expect(
          session!.pairWithManualCode({
            apiBaseUrl: "https://cryptoarc-replacement.test",
            pairingId: "pair-replacement",
            code: "123456",
            deviceName: replacementDevice.name,
          }),
        ).rejects.toBe(persistenceError);
      });
      await act(async () => {
        await session!.refreshCockpit();
      });
      const inMemorySession = {
        apiBaseUrl: session?.apiBaseUrl,
        token: session?.token,
        device: session?.device,
        cockpit: session?.cockpit,
      };
      const recoveryFetchArgs = fetchMobileCockpitMock.mock.lastCall;
      await firstView.unmount();

      expect(inMemorySession).toEqual({
        apiBaseUrl: "https://cryptoarc-old.test",
        token: "old-mobile-token",
        device: priorDeviceStored ? oldDevice : null,
        cockpit: oldPayload,
      });
      expect(recoveryFetchArgs).toEqual(["https://cryptoarc-old.test", "old-mobile-token"]);

      let remountedSessionValue: SessionValue | undefined;
      const onRemountedSessionReady = (nextSession: SessionValue) => {
        remountedSessionValue = nextSession;
      };
      const secondView = await render(
        <MobileSessionProvider>
          <SessionProbe onSessionReady={onRemountedSessionReady} />
        </MobileSessionProvider>,
      );
      await waitFor(() => expect(remountedSessionValue?.loading).toBe(false));
      await waitFor(() => expect(fetchMobileCockpitMock).toHaveBeenCalledTimes(3));
      await waitFor(() => expect(remountedSessionValue?.cockpit).toEqual(oldPayload));
      const remountedSession = {
        apiBaseUrl: remountedSessionValue?.apiBaseUrl,
        token: remountedSessionValue?.token,
        device: remountedSessionValue?.device,
        cockpit: remountedSessionValue?.cockpit,
      };
      const remountFetchArgs = fetchMobileCockpitMock.mock.lastCall;
      await secondView.unmount();

      expect(remountedSession).toEqual({
        apiBaseUrl: "https://cryptoarc-old.test",
        token: "old-mobile-token",
        device: priorDeviceStored ? oldDevice : null,
        cockpit: oldPayload,
      });
      expect(remountFetchArgs).toEqual(["https://cryptoarc-old.test", "old-mobile-token"]);
    },
  );

  it("rolls back a partial clear without rejecting and allows a successful retry", async () => {
    const oldDevice = {
      id: "mobile-old-clear",
      name: "Old clear-session cockpit",
      platform: "android",
      scopes: ["mobile:read"],
      created_at: "2026-07-01T20:00:00Z",
      last_seen_at: "2026-07-01T20:00:00Z",
      expires_at: "2026-08-01T20:00:00Z",
      revoked_at: "",
    };
    const oldApiBaseUrl = "https://cryptoarc-old-clear.test";
    const oldToken = "old-clear-token";
    const oldPayload = { ...sampleCockpit, server_time: "old-clear-session" };
    const storedValues = new Map<string, string>([
      ["cryptoarc.mobile.apiBaseUrl", oldApiBaseUrl],
      ["cryptoarc.mobile.token", oldToken],
      ["cryptoarc.mobile.device", JSON.stringify(oldDevice)],
    ]);
    getItemAsyncMock.mockImplementation(async (key) => storedValues.get(key) ?? null);
    setItemAsyncMock.mockImplementation(async (key, value) => {
      storedValues.set(key, value);
    });
    let failTokenDelete = true;
    deleteItemAsyncMock.mockImplementation(async (key) => {
      if (key === "cryptoarc.mobile.token" && failTokenDelete) {
        failTokenDelete = false;
        throw new Error("private delete failure: old-clear-token");
      }
      storedValues.delete(key);
    });
    fetchMobileCockpitMock.mockResolvedValue(oldPayload);
    let session: SessionValue | undefined;
    const onSessionReady = (nextSession: SessionValue) => {
      session = nextSession;
    };

    const firstView = await render(
      <MobileSessionProvider>
        <SessionProbe onSessionReady={onSessionReady} />
      </MobileSessionProvider>,
    );
    await waitFor(() => expect(fetchMobileCockpitMock).toHaveBeenCalledTimes(1));

    let firstClearOutcome = "pending";
    await act(async () => {
      firstClearOutcome = await session!.clearSession().then(
        () => "resolved",
        () => "rejected",
      );
    });
    const failedClearSession = {
      apiBaseUrl: session?.apiBaseUrl,
      token: session?.token,
      device: session?.device,
      error: session?.error,
    };
    const durableValuesAfterFailure = new Map(storedValues);

    await act(async () => {
      await session!.refreshCockpit();
    });
    const refreshCallsAfterFailure = fetchMobileCockpitMock.mock.calls.length;
    const refreshArgsAfterFailure = fetchMobileCockpitMock.mock.lastCall;
    await firstView.unmount();

    let remountedSession: SessionValue | undefined;
    const onRemountedSessionReady = (nextSession: SessionValue) => {
      remountedSession = nextSession;
    };
    const secondView = await render(
      <MobileSessionProvider>
        <SessionProbe onSessionReady={onRemountedSessionReady} />
      </MobileSessionProvider>,
    );
    await waitFor(() => expect(remountedSession?.loading).toBe(false));
    await act(async () => {
      await Promise.resolve();
    });
    const sessionAfterRemount = {
      apiBaseUrl: remountedSession?.apiBaseUrl,
      token: remountedSession?.token,
      device: remountedSession?.device,
    };
    const refreshCallsAfterRemount = fetchMobileCockpitMock.mock.calls.length;

    let retryOutcome = "pending";
    await act(async () => {
      retryOutcome = await remountedSession!.clearSession().then(
        () => "resolved",
        () => "rejected",
      );
    });
    const sessionAfterRetry = {
      apiBaseUrl: remountedSession?.apiBaseUrl,
      token: remountedSession?.token,
      device: remountedSession?.device,
      error: remountedSession?.error,
    };
    const durableValuesAfterRetry = new Map(storedValues);
    await secondView.unmount();

    expect(firstClearOutcome).toBe("resolved");
    expect(failedClearSession).toEqual({
      apiBaseUrl: oldApiBaseUrl,
      token: oldToken,
      device: oldDevice,
      error: "Disconnect failed. Session remains active.",
    });
    expect(failedClearSession.error).not.toContain("old-clear-token");
    expect(durableValuesAfterFailure).toEqual(
      new Map([
        ["cryptoarc.mobile.apiBaseUrl", oldApiBaseUrl],
        ["cryptoarc.mobile.token", oldToken],
        ["cryptoarc.mobile.device", JSON.stringify(oldDevice)],
      ]),
    );
    expect(refreshCallsAfterFailure).toBe(2);
    expect(refreshArgsAfterFailure).toEqual([oldApiBaseUrl, oldToken]);
    expect(sessionAfterRemount).toEqual({ apiBaseUrl: oldApiBaseUrl, token: oldToken, device: oldDevice });
    expect(refreshCallsAfterRemount).toBe(3);
    expect(retryOutcome).toBe("resolved");
    expect(sessionAfterRetry).toEqual({ apiBaseUrl: "", token: null, device: null, error: "" });
    expect(durableValuesAfterRetry.size).toBe(0);
  });
});
