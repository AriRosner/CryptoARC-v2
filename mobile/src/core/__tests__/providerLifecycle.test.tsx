import * as LocalAuthentication from "expo-local-authentication";
import * as SecureStore from "expo-secure-store";
import { act, render, waitFor } from "@testing-library/react-native";
import React, { useEffect } from "react";
import { AppState, type AppStateStatus } from "react-native";

import {
  claimMobilePairing,
  fetchMobileCockpit,
  fetchMobileFeed,
  MobileApiError,
  requestMobileWebSocketTicket,
  startMobileBot,
} from "../../api";
import { MobileSessionProvider, useMobileSession } from "../../MobileSession";
import { sampleCockpit } from "../../testPayloads";
import type { MobileDevice, MobileFeedPayload } from "../../types";
import { ConnectionProvider } from "../connectivity/ConnectionProvider";
import {
  LEGACY_DEVICE_KEY,
  SESSION_CONTROL_KEY,
} from "../session/storage";
import {
  SessionProvider,
  useSession,
} from "../session/SessionProvider";

jest.mock("../../api", () => ({
  ...jest.requireActual("../../api"),
  claimMobilePairing: jest.fn(),
  fetchMobileCockpit: jest.fn(),
  fetchMobileFeed: jest.fn(),
  requestMobileWebSocketTicket: jest.fn(),
  startMobileBot: jest.fn(),
}));

type Deferred<T> = {
  promise: Promise<T>;
  resolve(value: T): void;
  reject(reason: Error): void;
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

const newDevice: MobileDevice = {
  ...oldDevice,
  id: "mobile-new",
  name: "New operator phone",
};

type SessionValue = ReturnType<typeof useMobileSession>;
type CoreSessionValue = ReturnType<typeof useSession>;

function Probe({ onValue }: { onValue(value: SessionValue): void }) {
  const value = useMobileSession();
  useEffect(() => {
    onValue(value);
  }, [onValue, value]);
  return null;
}

function ProviderStack({ onValue }: { onValue(value: SessionValue): void }) {
  return (
    <SessionProvider>
      <ConnectionProvider>
        <MobileSessionProvider>
          <Probe onValue={onValue} />
        </MobileSessionProvider>
      </ConnectionProvider>
    </SessionProvider>
  );
}

function CoreProbe({ onValue }: { onValue(value: CoreSessionValue): void }) {
  const value = useSession();
  useEffect(() => {
    onValue(value);
  }, [onValue, value]);
  return null;
}

function CoreProviderStack({ onValue }: { onValue(value: CoreSessionValue): void }) {
  return (
    <SessionProvider>
      <ConnectionProvider>
        <CoreProbe onValue={onValue} />
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

describe("modern provider lifecycle guards", () => {
  const claimMock = jest.mocked(claimMobilePairing);
  const cockpitMock = jest.mocked(fetchMobileCockpit);
  const feedMock = jest.mocked(fetchMobileFeed);
  const ticketMock = jest.mocked(requestMobileWebSocketTicket);
  const startMock = jest.mocked(startMobileBot);
  const authMock = jest.mocked(LocalAuthentication.authenticateAsync);
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
    cockpitMock.mockResolvedValue(sampleCockpit);
    ticketMock.mockResolvedValue({
      ticket: "one-time-ticket",
      scope: "mobile:monitor",
      ttl_seconds: 30,
    });
    authMock.mockResolvedValue({ success: true });
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
    Object.defineProperty(AppState, "currentState", {
      configurable: true,
      value: "active",
    });
    appStateSpy = jest.spyOn(AppState, "addEventListener").mockImplementation(
      (_event, listener) => {
        appStateListeners.push(listener);
        return { remove: jest.fn() };
      },
    );
  });

  afterEach(() => {
    appStateSpy.mockRestore();
  });

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
    let session: CoreSessionValue | undefined;
    const view = await render(
      <CoreProviderStack onValue={(value) => (session = value)} />,
    );
    await waitFor(() => expect(initialDeviceReadStarted).toBe(true));
    await waitFor(() => expect(session).toBeDefined());

    let clearing!: Promise<boolean>;
    await act(async () => {
      clearing = session!.clearSession();
      await Promise.resolve();
    });
    initialDeviceRead.resolve(JSON.stringify(oldDevice));
    await act(async () => {
      await clearing;
      await Promise.resolve();
      await Promise.resolve();
    });
    await waitFor(() => expect(session?.loading).toBe(false));

    expect(session?.token).toBeNull();
    expect(ticketMock).not.toHaveBeenCalled();
    expect(values.get(SESSION_CONTROL_KEY)).toContain('"status":"cleared"');
    view.unmount();
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
    let session: CoreSessionValue | undefined;
    const view = await render(
      <CoreProviderStack onValue={(value) => (session = value)} />,
    );
    await waitFor(() => expect(initialDeviceReadStarted).toBe(true));
    await waitFor(() => expect(session).toBeDefined());

    let replacing!: Promise<boolean>;
    await act(async () => {
      replacing = session!.replaceSession(
        "https://cryptoarc-new.test",
        "new-long-lived-token",
        newDevice,
      );
      await Promise.resolve();
    });
    initialDeviceRead.resolve(JSON.stringify(oldDevice));
    await act(async () => {
      await replacing;
      await Promise.resolve();
      await Promise.resolve();
    });
    await waitFor(() => expect(session?.loading).toBe(false));
    await waitFor(() => expect(ticketMock).toHaveBeenCalled());

    expect(session?.token).toBe("new-long-lived-token");
    expect(ticketMock).toHaveBeenCalledTimes(1);
    expect(ticketMock).toHaveBeenCalledWith(
      "https://cryptoarc-new.test",
      "new-long-lived-token",
    );
    view.unmount();
  });

  it("acquires a fresh ticket after socket close without clearing the active session", async () => {
    const randomSpy = jest.spyOn(Math, "random").mockReturnValue(0);
    ticketMock
      .mockResolvedValueOnce({
        ticket: "ticket-A",
        scope: "mobile:monitor",
        ttl_seconds: 30,
      })
      .mockResolvedValueOnce({
        ticket: "ticket-B",
        scope: "mobile:monitor",
        ttl_seconds: 30,
      });
    const mounted = await mountStack();
    await waitFor(() => expect(sockets).toHaveLength(1));

    await act(async () => {
      sockets[0].emitClose(1006);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    await waitFor(() => expect(ticketMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(sockets).toHaveLength(2));

    expect(sockets.map((socket) => socket.url)).toEqual([
      "wss://cryptoarc-old.test/ws/mobile?ticket=ticket-A",
      "wss://cryptoarc-old.test/ws/mobile?ticket=ticket-B",
    ]);
    expect(mounted.session.token).toBe("old-long-lived-token");
    randomSpy.mockRestore();
    mounted.view.unmount();
  });

  it("quarantines the session when authenticated ticket acquisition returns 401", async () => {
    ticketMock.mockRejectedValue(
      new MobileApiError("session denied", "authentication", 401, false),
    );
    let session: SessionValue | undefined;
    const view = await render(<ProviderStack onValue={(value) => (session = value)} />);

    await waitFor(() => expect(ticketMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(session?.token).toBeNull());

    expect(sockets).toHaveLength(0);
    expect(values.get(SESSION_CONTROL_KEY)).toContain('"status":"cleared"');
    view.unmount();
  });

  it("does not install a pairing claim that resolves after clear", async () => {
    const claim = deferred<Awaited<ReturnType<typeof claimMobilePairing>>>();
    claimMock.mockReturnValue(claim.promise);
    const mounted = await mountStack();

    let pairing!: Promise<void>;
    await act(async () => {
      pairing = mounted.session.pairWithManualCode({
        apiBaseUrl: "https://cryptoarc-new.test",
        pairingId: "pair-new",
        code: "123456",
        deviceName: newDevice.name,
      });
      await Promise.resolve();
      await mounted.session.clearSession();
    });
    claim.resolve({
      token: "new-long-lived-token",
      device: newDevice,
      scopes: newDevice.scopes,
      expires_at: newDevice.expires_at,
    });
    await act(async () => pairing);

    expect(mounted.session.token).toBeNull();
    expect(JSON.stringify([...values.values()])).not.toContain("new-long-lived-token");
    mounted.view.unmount();
  });

  it("quarantines memory when replacement rollback cannot restore the prior control record", async () => {
    claimMock.mockResolvedValue({
      token: "new-long-lived-token",
      device: newDevice,
      scopes: newDevice.scopes,
      expires_at: newDevice.expires_at,
    });
    const mounted = await mountStack();
    const previousControl = values.get(SESSION_CONTROL_KEY);
    expect(previousControl).toBeDefined();
    let corruptNextControlRead = false;
    jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key) => {
      if (key === SESSION_CONTROL_KEY && corruptNextControlRead) {
        corruptNextControlRead = false;
        return JSON.stringify({ version: 999 });
      }
      return values.get(key) ?? null;
    });
    jest.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value) => {
      if (
        key === SESSION_CONTROL_KEY &&
        value !== previousControl &&
        JSON.parse(value).status === "active"
      ) {
        values.set(key, value);
        corruptNextControlRead = true;
        return;
      }
      if (key === SESSION_CONTROL_KEY && value === previousControl) {
        throw new Error("rollback restore failed");
      }
      values.set(key, value);
    });

    await act(async () => {
      await expect(
        mounted.session.pairWithManualCode({
          apiBaseUrl: "https://cryptoarc-new.test",
          pairingId: "pair-new",
          code: "123456",
          deviceName: newDevice.name,
        }),
      ).rejects.toThrow("Secure session rollback failed");
    });

    expect(mounted.session.token).toBeNull();
    expect(values.get(SESSION_CONTROL_KEY)).toContain('"status":"cleared"');
    mounted.view.unmount();
  });

  it("does not publish a feed response that resolves after clear", async () => {
    const feed = deferred<MobileFeedPayload>();
    feedMock.mockReturnValue(feed.promise);
    const mounted = await mountStack();

    let loadingFeed!: Promise<void>;
    await act(async () => {
      loadingFeed = mounted.session.loadFeed();
      await Promise.resolve();
      await mounted.session.clearSession();
    });
    feed.resolve({
      artifact_type: "cryptoarc_mobile_feed",
      format_version: 1,
      generated_at: "2026-07-28T12:00:00.000Z",
      filters: {},
      summary: {},
      events: [],
      action_items: ["stale"],
    });
    await act(async () => loadingFeed);

    expect(mounted.session.feed).toBeNull();
    mounted.view.unmount();
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
    let unlocked = true;
    await act(async () => {
      unlocked = await unlocking;
    });

    expect(unlocked).toBe(false);
    expect(mounted.session.locked).toBe(true);
    mounted.view.unmount();
  });

  it("does not dispatch an old-session action after unlock finishes under a replacement", async () => {
    const authentication = deferred<{ success: true }>();
    authMock.mockReturnValue(authentication.promise);
    claimMock.mockResolvedValue({
      token: "new-long-lived-token",
      device: newDevice,
      scopes: newDevice.scopes,
      expires_at: newDevice.expires_at,
    });
    const mounted = await mountStack();

    let action!: Promise<void>;
    await act(async () => {
      action = mounted.session.startBot();
      await Promise.resolve();
      await mounted.session.pairWithManualCode({
        apiBaseUrl: "https://cryptoarc-new.test",
        pairingId: "pair-new",
        code: "123456",
        deviceName: newDevice.name,
      });
    });
    await act(async () => {
      authentication.resolve({ success: true });
      await action;
    });

    expect(startMock).not.toHaveBeenCalled();
    expect(mounted.session.token).toBe("new-long-lived-token");
    mounted.view.unmount();
  });

  it("does not publish an action response that resolves after clear", async () => {
    const actionResponse = deferred<typeof sampleCockpit>();
    startMock.mockReturnValue(actionResponse.promise);
    const mounted = await mountStack();

    let action!: Promise<void>;
    await act(async () => {
      action = mounted.session.startBot();
      await Promise.resolve();
      await Promise.resolve();
    });
    await waitFor(() => expect(startMock).toHaveBeenCalledTimes(1));
    await act(async () => {
      await mounted.session.clearSession();
    });
    actionResponse.resolve({
      ...sampleCockpit,
      server_time: "stale-action-response",
    });
    await act(async () => action);

    expect(mounted.session.cockpit).toBeNull();
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
    expect(sockets).toHaveLength(1);
    expect(sockets[0].close).toHaveBeenCalled();
    expect(values.get(SESSION_CONTROL_KEY)).toContain('"status":"cleared"');
    expect(values.get(SESSION_CONTROL_KEY)).not.toContain("old-long-lived-token");
    mounted.view.unmount();
  });
});
