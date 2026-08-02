import * as LocalAuthentication from "expo-local-authentication";
import * as SecureStore from "expo-secure-store";
import { act, render, waitFor } from "@testing-library/react-native";
import React, { useEffect } from "react";
import { AppState, type AppStateStatus } from "react-native";

import { MobileApiError, requestMobileWebSocketTicket } from "../../api";
import { unregisterPushToken } from "../../features/alerts/api";
import type { MobileDevice } from "../../types";
import { ConnectionProvider } from "../connectivity/ConnectionProvider";
import { LEGACY_DEVICE_KEY, SESSION_CONTROL_KEY } from "../session/storage";
import { SessionProvider, useSession } from "../session/SessionProvider";

jest.mock("../../api", () => ({
  ...jest.requireActual("../../api"),
  requestMobileWebSocketTicket: jest.fn(),
}));

jest.mock("../../features/alerts/api", () => ({
  unregisterPushToken: jest.fn(async () => undefined),
}));

type Deferred<T> = {
  promise: Promise<T>;
  resolve(value: T): void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

const oldDevice: MobileDevice = {
  id: "mobile-old",
  name: "Old operator phone",
  platform: "android",
  scopes: ["mobile:monitor", "mobile:control"],
  created_at: "2026-07-28T10:00:00.000Z",
  last_seen_at: "2026-07-28T10:00:00.000Z",
  expires_at: "2026-08-28T10:00:00.000Z",
  revoked_at: "",
};

const newDevice: MobileDevice = { ...oldDevice, id: "mobile-new", name: "New operator phone" };
type SessionValue = ReturnType<typeof useSession>;

function Probe({ onValue }: { onValue(value: SessionValue): void }) {
  const value = useSession();
  useEffect(() => {
    onValue(value);
  }, [onValue, value]);
  return null;
}

function ProviderStack({ onValue }: { onValue(value: SessionValue): void }) {
  return (
    <SessionProvider>
      <ConnectionProvider>
        <Probe onValue={onValue} />
      </ConnectionProvider>
    </SessionProvider>
  );
}

class FakeSocket {
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  close = jest.fn();

  constructor(readonly url: string) {}

  emitMessage(value: unknown) {
    this.onmessage?.({ data: JSON.stringify(value) });
  }

  emitClose(code: number) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

describe("core provider lifecycle guards", () => {
  const ticketMock = jest.mocked(requestMobileWebSocketTicket);
  const authMock = jest.mocked(LocalAuthentication.authenticateAsync);
  const unregisterMock = jest.mocked(unregisterPushToken);
  const values = new Map<string, string>();
  const sockets: FakeSocket[] = [];
  const appStateListeners: Array<(state: AppStateStatus) => void> = [];
  let appStateSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    values.clear();
    values.set("cryptoarc.mobile.apiBaseUrl", "https://cryptoarc-old.test");
    values.set("cryptoarc.mobile.token", "old-long-lived-token");
    values.set("cryptoarc.mobile.device", JSON.stringify(oldDevice));
    jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key) => values.get(key) ?? null);
    jest.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value) => {
      values.set(key, value);
    });
    jest.mocked(SecureStore.deleteItemAsync).mockImplementation(async (key) => {
      values.delete(key);
    });
    ticketMock.mockReset().mockResolvedValue({ ticket: "one-time-ticket", scope: "mobile:monitor", ttl_seconds: 30 });
    authMock.mockReset().mockResolvedValue({ success: true });
    unregisterMock.mockReset().mockResolvedValue(undefined);
    Object.defineProperty(globalThis, "WebSocket", {
      configurable: true,
      value: class extends FakeSocket {
        constructor(url: string) {
          super(url);
          sockets.push(this);
        }
      },
    });
    sockets.length = 0;
    appStateListeners.length = 0;
    Object.defineProperty(AppState, "currentState", { configurable: true, value: "active" });
    appStateSpy = jest.spyOn(AppState, "addEventListener").mockImplementation((_event, listener) => {
      appStateListeners.push(listener);
      return { remove: jest.fn() };
    });
  });

  afterEach(() => appStateSpy.mockRestore());

  async function mountStack() {
    let session: SessionValue | undefined;
    const view = await render(<ProviderStack onValue={(value) => (session = value)} />);
    await waitFor(() => expect(session?.loading).toBe(false));
    await waitFor(() => expect(session?.token).toBe("old-long-lived-token"));
    await waitFor(() => expect(ticketMock).toHaveBeenCalledTimes(1));
    return { get session() { return session!; }, view };
  }

  it("does not publish or reconnect a stale initial session after clear begins", async () => {
    const initialDeviceRead = deferred<string | null>();
    let initialDeviceReadStarted = false;
    jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key) => {
      if (key === LEGACY_DEVICE_KEY && !initialDeviceReadStarted) {
        initialDeviceReadStarted = true;
        return initialDeviceRead.promise;
      }
      return values.get(key) ?? null;
    });
    let session: SessionValue | undefined;
    const view = await render(<ProviderStack onValue={(value) => (session = value)} />);
    await waitFor(() => expect(initialDeviceReadStarted).toBe(true));

    let clearing!: Promise<boolean>;
    await act(async () => {
      clearing = session!.clearSession();
      await Promise.resolve();
    });
    initialDeviceRead.resolve(JSON.stringify(oldDevice));
    await act(async () => clearing);
    await waitFor(() => expect(session?.loading).toBe(false));

    expect(session?.token).toBeNull();
    expect(ticketMock).not.toHaveBeenCalled();
    expect(values.get(SESSION_CONTROL_KEY)).toContain('"status":"cleared"');
    view.unmount();
  });

  it("best-effort unregisters push on explicit clear and backend replacement", async () => {
    const mounted = await mountStack();
    await act(async () => {
      await mounted.session.replaceSession("https://cryptoarc-new.test", "new-long-lived-token", newDevice);
    });
    expect(unregisterMock).toHaveBeenCalledWith({ apiBaseUrl: "https://cryptoarc-old.test", token: "old-long-lived-token" });

    unregisterMock.mockRejectedValueOnce(new Error("offline"));
    await act(async () => {
      await expect(mounted.session.clearSession()).resolves.toBe(true);
    });
    expect(unregisterMock).toHaveBeenLastCalledWith({ apiBaseUrl: "https://cryptoarc-new.test", token: "new-long-lived-token" });
    expect(mounted.session.token).toBeNull();
    mounted.view.unmount();
  });

  it("does not let a stale initial load replace a newer session or acquire its ticket", async () => {
    const initialDeviceRead = deferred<string | null>();
    let initialDeviceReadStarted = false;
    jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key) => {
      if (key === LEGACY_DEVICE_KEY && !initialDeviceReadStarted) {
        initialDeviceReadStarted = true;
        return initialDeviceRead.promise;
      }
      return values.get(key) ?? null;
    });
    let session: SessionValue | undefined;
    const view = await render(<ProviderStack onValue={(value) => (session = value)} />);
    await waitFor(() => expect(initialDeviceReadStarted).toBe(true));

    let replacing!: Promise<boolean>;
    await act(async () => {
      replacing = session!.replaceSession("https://cryptoarc-new.test", "new-long-lived-token", newDevice);
      await Promise.resolve();
    });
    initialDeviceRead.resolve(JSON.stringify(oldDevice));
    await act(async () => replacing);
    await waitFor(() => expect(ticketMock).toHaveBeenCalled());

    expect(session?.token).toBe("new-long-lived-token");
    expect(ticketMock).toHaveBeenCalledTimes(1);
    expect(ticketMock).toHaveBeenCalledWith("https://cryptoarc-new.test", "new-long-lived-token");
    view.unmount();
  });

  it("acquires a fresh ticket after socket close without clearing the active session", async () => {
    const randomSpy = jest.spyOn(Math, "random").mockReturnValue(0);
    ticketMock
      .mockResolvedValueOnce({ ticket: "ticket-A", scope: "mobile:monitor", ttl_seconds: 30 })
      .mockResolvedValueOnce({ ticket: "ticket-B", scope: "mobile:monitor", ttl_seconds: 30 });
    const mounted = await mountStack();
    await waitFor(() => expect(sockets).toHaveLength(1));

    await act(async () => {
      sockets[0].emitClose(1006);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    await waitFor(() => expect(ticketMock).toHaveBeenCalledTimes(2));

    expect(sockets.map((socket) => socket.url)).toEqual([
      "wss://cryptoarc-old.test/ws/mobile?ticket=ticket-A",
      "wss://cryptoarc-old.test/ws/mobile?ticket=ticket-B",
    ]);
    expect(mounted.session.token).toBe("old-long-lived-token");
    randomSpy.mockRestore();
    mounted.view.unmount();
  });

  it("quarantines a 401 ticket session", async () => {
    ticketMock.mockRejectedValue(new MobileApiError("session denied", "authentication", 401, false));
    let session: SessionValue | undefined;
    const view = await render(<ProviderStack onValue={(value) => (session = value)} />);
    await waitFor(() => expect(session?.token).toBeNull());
    expect(values.get(SESSION_CONTROL_KEY)).toContain('"status":"cleared"');
    await act(async () => view.unmount());
  });

  it("keeps a 403 ticket scope denial mounted", async () => {
    ticketMock.mockRejectedValue(new MobileApiError("monitor scope required", "authorization", 403, false));
    let session: SessionValue | undefined;
    const view = await render(<ProviderStack onValue={(value) => (session = value)} />);
    await waitFor(() => expect(session?.token).toBe("old-long-lived-token"));
    expect(values.get(SESSION_CONTROL_KEY)).not.toContain('"status":"cleared"');
    await act(async () => view.unmount());
  });

  it("does not unlock controls when authentication resolves after clear", async () => {
    const authentication = deferred<{ success: true }>();
    authMock.mockReturnValue(authentication.promise);
    const mounted = await mountStack();
    let unlocking!: Promise<boolean>;
    await act(async () => {
      unlocking = mounted.session.unlockControls();
      await Promise.resolve();
      await mounted.session.clearSession();
    });
    authentication.resolve({ success: true });
    await act(async () => {
      await expect(unlocking).resolves.toBe(false);
    });
    expect(mounted.session.locked).toBe(true);
    mounted.view.unmount();
  });

  it("quarantines a revoked persisted session before foreground can reconnect it", async () => {
    const mounted = await mountStack();
    await waitFor(() => expect(sockets).toHaveLength(1));
    await act(async () => {
      sockets[0].emitMessage({
        event_type: "invalidate",
        schema_version: 1,
        server_time: new Date().toISOString(),
        sequence: 1,
        payload: { reason: "token_revoked" },
      });
      await Promise.resolve();
    });
    await waitFor(() => expect(mounted.session.token).toBeNull());
    const ticketRequestsAfterRevocation = ticketMock.mock.calls.length;
    await act(async () => {
      appStateListeners.forEach((listener) => listener("background"));
      appStateListeners.forEach((listener) => listener("active"));
      await Promise.resolve();
    });
    expect(ticketMock).toHaveBeenCalledTimes(ticketRequestsAfterRevocation);
    expect(sockets[0].close).toHaveBeenCalled();
    expect(values.get(SESSION_CONTROL_KEY)).toContain('"status":"cleared"');
    mounted.view.unmount();
  });
});
