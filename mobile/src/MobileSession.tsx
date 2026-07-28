import * as LocalAuthentication from "expo-local-authentication";
import * as SecureStore from "expo-secure-store";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { AppState, type AppStateStatus } from "react-native";

import {
  claimMobilePairing,
  fetchMobileCockpit,
  fetchMobileFeed,
  normalizeApiBaseUrl,
  probeMobileHealth,
  setMobileKillSwitch,
  startMobileBot,
  stopMobileBot,
} from "./api";
import { useConnection } from "./core/connectivity/ConnectionProvider";
import {
  type SessionContextValue,
  useOptionalSession,
} from "./core/session/SessionProvider";
import { parsePairingPayload, sanitizeReason } from "./security";
import type { MobileCockpitPayload, MobileDevice, MobileFeedPayload } from "./types";

const TOKEN_KEY = "cryptoarc.mobile.token";
const API_BASE_KEY = "cryptoarc.mobile.apiBaseUrl";
const DEVICE_KEY = "cryptoarc.mobile.device";
const DISCONNECT_FAILED_MESSAGE = "Disconnect failed. Session remains active.";

type StoredMobileSessionValues = [string | null, string | null, string | null];

async function restoreStoredSessionValues(values: StoredMobileSessionValues): Promise<void> {
  const restoreStoredValue = (key: string, value: string | null) =>
    Promise.resolve().then(() =>
      value === null ? SecureStore.deleteItemAsync(key) : SecureStore.setItemAsync(key, value),
    );
  // Restore every key independently; rollback failures must not mask the operation's original failure.
  await Promise.allSettled([
    restoreStoredValue(API_BASE_KEY, values[0]),
    restoreStoredValue(TOKEN_KEY, values[1]),
    restoreStoredValue(DEVICE_KEY, values[2]),
  ]);
}

function mobileSessionIdentity(apiBaseUrl: string, token: string): string {
  return JSON.stringify([apiBaseUrl, token]);
}

interface ActiveMobileSession {
  identity: string;
  epoch: number;
}

interface CockpitRefreshInFlight extends ActiveMobileSession {
  promise: Promise<void>;
}

interface MobileSessionValue {
  apiBaseUrl: string;
  token: string | null;
  device: MobileDevice | null;
  cockpit: MobileCockpitPayload | null;
  feed: MobileFeedPayload | null;
  connected: boolean;
  locked: boolean;
  loading: boolean;
  error: string;
  setError: (value: string) => void;
  pairWithManualCode: (input: { apiBaseUrl: string; pairingId: string; code: string; deviceName: string }) => Promise<void>;
  pairWithQrPayload: (payload: string, fallbackApiBaseUrl: string, deviceName: string) => Promise<void>;
  probeHealth: (apiBaseUrl: string) => Promise<void>;
  refreshCockpit: () => Promise<void>;
  loadFeed: (level?: string, subsystem?: string) => Promise<void>;
  unlockControls: () => Promise<boolean>;
  startBot: () => Promise<void>;
  stopBot: () => Promise<void>;
  setKillSwitch: (enabled: boolean, reason: string) => Promise<void>;
  clearSession: () => Promise<void>;
}

const MobileSessionContext = createContext<MobileSessionValue | null>(null);

function LegacyMobileSessionProvider({ children }: { children: React.ReactNode }) {
  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [device, setDevice] = useState<MobileDevice | null>(null);
  const [cockpit, setCockpit] = useState<MobileCockpitPayload | null>(null);
  const [feed, setFeed] = useState<MobileFeedPayload | null>(null);
  const [connected, setConnected] = useState(false);
  const [locked, setLocked] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const sessionEpochRef = useRef(0);
  const activeSessionRef = useRef<ActiveMobileSession | null>(null);
  const cockpitRefreshInFlightRef = useRef<CockpitRefreshInFlight | null>(null);

  const refreshCockpit = useCallback((): Promise<void> => {
    if (!token || !apiBaseUrl) return Promise.resolve();
    const identity = mobileSessionIdentity(apiBaseUrl, token);
    const activeSession = activeSessionRef.current;
    if (!activeSession || activeSession.identity !== identity) return Promise.resolve();
    const currentRequest = cockpitRefreshInFlightRef.current;
    if (currentRequest?.identity === identity && currentRequest.epoch === activeSession.epoch) {
      return currentRequest.promise;
    }
    const epoch = activeSession.epoch;

    const request = (async () => {
      try {
        const payload = await fetchMobileCockpit(apiBaseUrl, token);
        if (activeSessionRef.current?.identity !== identity || activeSessionRef.current.epoch !== epoch) return;
        setCockpit(payload);
        setConnected(true);
        setError("");
      } catch (err) {
        if (activeSessionRef.current?.identity !== identity || activeSessionRef.current.epoch !== epoch) return;
        setConnected(false);
        setError(err instanceof Error ? err.message : "Cockpit refresh failed");
      }
    })();
    cockpitRefreshInFlightRef.current = { identity, epoch, promise: request };
    const release = () => {
      const current = cockpitRefreshInFlightRef.current;
      if (current?.identity === identity && current.epoch === epoch && current.promise === request) {
        cockpitRefreshInFlightRef.current = null;
      }
    };
    void request.then(release, release);
    return request;
  }, [apiBaseUrl, token]);

  useEffect(() => {
    let cancelled = false;
    async function loadStoredSession() {
      try {
        const [storedToken, storedApiBaseUrl, storedDevice] = await Promise.all([
          SecureStore.getItemAsync(TOKEN_KEY),
          SecureStore.getItemAsync(API_BASE_KEY),
          SecureStore.getItemAsync(DEVICE_KEY),
        ]);
        if (cancelled) return;
        const epoch = sessionEpochRef.current + 1;
        sessionEpochRef.current = epoch;
        activeSessionRef.current =
          storedToken && storedApiBaseUrl
            ? { identity: mobileSessionIdentity(storedApiBaseUrl, storedToken), epoch }
            : null;
        cockpitRefreshInFlightRef.current = null;
        setToken(storedToken);
        setApiBaseUrl(storedApiBaseUrl ?? "");
        setDevice(storedDevice ? (JSON.parse(storedDevice) as MobileDevice) : null);
        setLocked(Boolean(storedToken));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Secure session load failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadStoredSession();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!token || !apiBaseUrl) return;
    void refreshCockpit();
    const interval = setInterval(() => {
      void refreshCockpit();
    }, 12000);
    return () => clearInterval(interval);
  }, [apiBaseUrl, refreshCockpit, token]);

  useEffect(() => {
    const onChange = (nextState: AppStateStatus) => {
      if (nextState === "active" && token) {
        setLocked(true);
        void refreshCockpit();
      }
    };
    const subscription = AppState.addEventListener("change", onChange);
    return () => subscription.remove();
  }, [refreshCockpit, token]);

  const saveSession = useCallback(async (nextApiBaseUrl: string, nextToken: string, nextDevice: MobileDevice) => {
    const previousSession = activeSessionRef.current;
    const epoch = sessionEpochRef.current + 1;
    sessionEpochRef.current = epoch;
    activeSessionRef.current = { identity: mobileSessionIdentity(nextApiBaseUrl, nextToken), epoch };
    cockpitRefreshInFlightRef.current = null;
    let previousStoredValues: StoredMobileSessionValues | null = null;
    try {
      previousStoredValues = await Promise.all([
        SecureStore.getItemAsync(API_BASE_KEY),
        SecureStore.getItemAsync(TOKEN_KEY),
        SecureStore.getItemAsync(DEVICE_KEY),
      ]);
      await SecureStore.setItemAsync(API_BASE_KEY, nextApiBaseUrl);
      await SecureStore.setItemAsync(TOKEN_KEY, nextToken);
      await SecureStore.setItemAsync(DEVICE_KEY, JSON.stringify(nextDevice));
    } catch (err) {
      if (previousStoredValues) {
        await restoreStoredSessionValues(previousStoredValues);
      }
      const rollbackEpoch = sessionEpochRef.current + 1;
      sessionEpochRef.current = rollbackEpoch;
      activeSessionRef.current = previousSession ? { identity: previousSession.identity, epoch: rollbackEpoch } : null;
      cockpitRefreshInFlightRef.current = null;
      throw err;
    }
    setApiBaseUrl(nextApiBaseUrl);
    setToken(nextToken);
    setDevice(nextDevice);
    setLocked(true);
  }, []);

  const pairWithManualCode = useCallback(
    async (input: { apiBaseUrl: string; pairingId: string; code: string; deviceName: string }) => {
      setLoading(true);
      try {
        const normalizedBaseUrl = normalizeApiBaseUrl(input.apiBaseUrl);
        const claimed = await claimMobilePairing({
          apiBaseUrl: normalizedBaseUrl,
          pairingId: input.pairingId,
          code: input.code,
          deviceName: input.deviceName || "Android cockpit",
          platform: "android",
        });
        await saveSession(normalizedBaseUrl, claimed.token, claimed.device);
        setError("");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Pairing failed");
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [saveSession],
  );

  const pairWithQrPayload = useCallback(
    async (payload: string, fallbackApiBaseUrl: string, deviceName: string) => {
      const parsed = parsePairingPayload(payload);
      await pairWithManualCode({
        apiBaseUrl: parsed.apiBaseUrl || fallbackApiBaseUrl,
        pairingId: parsed.pairingId,
        code: parsed.code,
        deviceName,
      });
    },
    [pairWithManualCode],
  );

  const probeHealth = useCallback(async (nextApiBaseUrl: string) => {
    setLoading(true);
    try {
      await probeMobileHealth(nextApiBaseUrl);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Health check failed");
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const loadFeed = useCallback(
    async (level = "", subsystem = "") => {
      if (!token || !apiBaseUrl) return;
      try {
        setFeed(await fetchMobileFeed(apiBaseUrl, token, level, subsystem));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Feed load failed");
      }
    },
    [apiBaseUrl, token],
  );

  const unlockControls = useCallback(async () => {
    if (!token) return false;
    try {
      const hasHardware = await LocalAuthentication.hasHardwareAsync();
      const enrolled = await LocalAuthentication.isEnrolledAsync();
      if (!hasHardware || !enrolled) {
        setError("Device unlock is not configured for guarded controls.");
        return false;
      }
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: "Unlock CryptoARC controls",
        cancelLabel: "Cancel",
        disableDeviceFallback: false,
      });
      if (result.success) {
        setLocked(false);
        setError("");
        return true;
      }
      setError("Controls remain locked.");
      return false;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Local unlock failed");
      return false;
    }
  }, [token]);

  const runGuardedAction = useCallback(
    async (action: () => Promise<MobileCockpitPayload>) => {
      if (locked) {
        const unlocked = await unlockControls();
        if (!unlocked) return;
      }
      setLoading(true);
      try {
        setCockpit(await action());
        setError("");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Action failed");
      } finally {
        setLoading(false);
      }
    },
    [locked, unlockControls],
  );

  const startBot = useCallback(async () => {
    if (!token || !apiBaseUrl) return;
    await runGuardedAction(() => startMobileBot(apiBaseUrl, token));
  }, [apiBaseUrl, runGuardedAction, token]);

  const stopBot = useCallback(async () => {
    if (!token || !apiBaseUrl) return;
    await runGuardedAction(() => stopMobileBot(apiBaseUrl, token));
  }, [apiBaseUrl, runGuardedAction, token]);

  const setKillSwitch = useCallback(
    async (enabled: boolean, reason: string) => {
      if (!token || !apiBaseUrl) return;
      await runGuardedAction(() => setMobileKillSwitch(apiBaseUrl, token, enabled, sanitizeReason(reason)));
    },
    [apiBaseUrl, runGuardedAction, token],
  );

  const clearSession = useCallback(async () => {
    const previousSession = activeSessionRef.current;
    const restorePreviousSession = () => {
      const rollbackEpoch = sessionEpochRef.current + 1;
      sessionEpochRef.current = rollbackEpoch;
      activeSessionRef.current = previousSession ? { identity: previousSession.identity, epoch: rollbackEpoch } : null;
      cockpitRefreshInFlightRef.current = null;
    };
    sessionEpochRef.current += 1;
    activeSessionRef.current = null;
    cockpitRefreshInFlightRef.current = null;
    let previousStoredValues: StoredMobileSessionValues;
    try {
      previousStoredValues = await Promise.all([
        SecureStore.getItemAsync(API_BASE_KEY),
        SecureStore.getItemAsync(TOKEN_KEY),
        SecureStore.getItemAsync(DEVICE_KEY),
      ]);
    } catch {
      restorePreviousSession();
      setError(DISCONNECT_FAILED_MESSAGE);
      return;
    }
    const deleteStoredValue = (key: string) => Promise.resolve().then(() => SecureStore.deleteItemAsync(key));
    const deleteResults = await Promise.allSettled([
      deleteStoredValue(API_BASE_KEY),
      deleteStoredValue(TOKEN_KEY),
      deleteStoredValue(DEVICE_KEY),
    ]);
    if (deleteResults.some((result) => result.status === "rejected")) {
      await restoreStoredSessionValues(previousStoredValues);
      restorePreviousSession();
      setError(DISCONNECT_FAILED_MESSAGE);
      return;
    }
    setToken(null);
    setApiBaseUrl("");
    setDevice(null);
    setCockpit(null);
    setFeed(null);
    setConnected(false);
    setLocked(true);
    setError("");
  }, []);

  const value = useMemo<MobileSessionValue>(
    () => ({
      apiBaseUrl,
      token,
      device,
      cockpit,
      feed,
      connected,
      locked,
      loading,
      error,
      setError,
      pairWithManualCode,
      pairWithQrPayload,
      probeHealth,
      refreshCockpit,
      loadFeed,
      unlockControls,
      startBot,
      stopBot,
      setKillSwitch,
      clearSession,
    }),
    [
      apiBaseUrl,
      token,
      device,
      cockpit,
      feed,
      connected,
      locked,
      loading,
      error,
      pairWithManualCode,
      pairWithQrPayload,
      probeHealth,
      refreshCockpit,
      loadFeed,
      unlockControls,
      startBot,
      stopBot,
      setKillSwitch,
      clearSession,
    ],
  );

  return <MobileSessionContext.Provider value={value}>{children}</MobileSessionContext.Provider>;
}

function useCockpitCompatibility(): MobileSessionValue {
  const value = useContext(MobileSessionContext);
  if (!value) {
    throw new Error("useMobileSession must be used inside MobileSessionProvider");
  }
  return value;
}

function ModernCockpitCompatibilityProvider({
  children,
  session,
}: {
  children: React.ReactNode;
  session: SessionContextValue;
}) {
  const connection = useConnection();
  const [cockpit, setCockpit] = useState<MobileCockpitPayload | null>(null);
  const [feed, setFeed] = useState<MobileFeedPayload | null>(null);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const activeSessionRef = useRef<ActiveMobileSession | null>(null);
  const cockpitRefreshInFlightRef = useRef<CockpitRefreshInFlight | null>(null);

  useEffect(() => {
    const epoch = session.generation;
    activeSessionRef.current =
      session.token && session.apiBaseUrl
        ? {
            identity: mobileSessionIdentity(session.apiBaseUrl, session.token),
            epoch,
          }
        : null;
    cockpitRefreshInFlightRef.current = null;
    setLoading(false);
    if (!session.token) {
      setCockpit(null);
      setFeed(null);
      setConnected(false);
    }
  }, [session.apiBaseUrl, session.generation, session.token]);

  const refreshCockpit = useCallback((): Promise<void> => {
    if (!session.token || !session.apiBaseUrl) return Promise.resolve();
    const identity = mobileSessionIdentity(session.apiBaseUrl, session.token);
    const activeSession = activeSessionRef.current;
    if (!activeSession || activeSession.identity !== identity) return Promise.resolve();
    const currentRequest = cockpitRefreshInFlightRef.current;
    if (currentRequest?.identity === identity && currentRequest.epoch === activeSession.epoch) {
      return currentRequest.promise;
    }
    const epoch = activeSession.epoch;
    const request = (async () => {
      try {
        const payload = await fetchMobileCockpit(session.apiBaseUrl, session.token!);
        if (
          !session.isCurrentGeneration(epoch) ||
          activeSessionRef.current?.identity !== identity ||
          activeSessionRef.current.epoch !== epoch
        ) {
          return;
        }
        setCockpit(payload);
        setConnected(true);
        setError("");
      } catch (cause) {
        if (
          !session.isCurrentGeneration(epoch) ||
          activeSessionRef.current?.identity !== identity ||
          activeSessionRef.current.epoch !== epoch
        ) {
          return;
        }
        setConnected(false);
        setError(cause instanceof Error ? cause.message : "Cockpit refresh failed");
      }
    })();
    cockpitRefreshInFlightRef.current = { identity, epoch, promise: request };
    const release = () => {
      const current = cockpitRefreshInFlightRef.current;
      if (current?.identity === identity && current.epoch === epoch && current.promise === request) {
        cockpitRefreshInFlightRef.current = null;
      }
    };
    void request.then(release, release);
    return request;
  }, [session]);

  useEffect(() => {
    if (!session.token || !session.apiBaseUrl) return;
    void refreshCockpit();
    const interval = setInterval(() => void refreshCockpit(), 12000);
    return () => clearInterval(interval);
  }, [refreshCockpit, session.apiBaseUrl, session.token]);

  useEffect(() => {
    const onChange = (nextState: AppStateStatus) => {
      if (nextState === "active" && session.token) {
        session.lock();
        void refreshCockpit();
      }
    };
    const subscription = AppState.addEventListener("change", onChange);
    return () => subscription.remove();
  }, [refreshCockpit, session]);

  const pairWithManualCode = useCallback(
    async (input: { apiBaseUrl: string; pairingId: string; code: string; deviceName: string }) => {
      const generation = session.generation;
      let replacementCompleted = false;
      setLoading(true);
      try {
        const apiBaseUrl = normalizeApiBaseUrl(input.apiBaseUrl);
        const claimed = await claimMobilePairing({
          apiBaseUrl,
          pairingId: input.pairingId,
          code: input.code,
          deviceName: input.deviceName || "Android cockpit",
          platform: "android",
        });
        if (!session.isCurrentGeneration(generation)) return;
        replacementCompleted = await session.replaceSession(
          apiBaseUrl,
          claimed.token,
          claimed.device,
          generation,
        );
        if (replacementCompleted) setError("");
      } catch (cause) {
        if (session.isCurrentGeneration(generation)) {
          setError(cause instanceof Error ? cause.message : "Pairing failed");
        }
        throw cause;
      } finally {
        if (replacementCompleted || session.isCurrentGeneration(generation)) {
          setLoading(false);
        }
      }
    },
    [session],
  );

  const pairWithQrPayload = useCallback(
    async (payload: string, fallbackApiBaseUrl: string, deviceName: string) => {
      const parsed = parsePairingPayload(payload);
      await pairWithManualCode({
        apiBaseUrl: parsed.apiBaseUrl || fallbackApiBaseUrl,
        pairingId: parsed.pairingId,
        code: parsed.code,
        deviceName,
      });
    },
    [pairWithManualCode],
  );

  const probeHealth = useCallback(async (apiBaseUrl: string) => {
    setLoading(true);
    try {
      await probeMobileHealth(apiBaseUrl);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Health check failed");
      throw cause;
    } finally {
      setLoading(false);
    }
  }, []);

  const loadFeed = useCallback(
    async (level = "", subsystem = "") => {
      if (!session.token || !session.apiBaseUrl) return;
      const generation = session.generation;
      try {
        const payload = await fetchMobileFeed(
          session.apiBaseUrl,
          session.token,
          level,
          subsystem,
        );
        if (!session.isCurrentGeneration(generation)) return;
        setFeed(payload);
      } catch (cause) {
        if (session.isCurrentGeneration(generation)) {
          setError(cause instanceof Error ? cause.message : "Feed load failed");
        }
      }
    },
    [session],
  );

  const runGuardedAction = useCallback(
    async (action: () => Promise<MobileCockpitPayload>) => {
      const generation = session.generation;
      if (session.locked && !(await session.unlockControls())) return;
      if (!session.isCurrentGeneration(generation)) return;
      setLoading(true);
      try {
        const payload = await action();
        if (!session.isCurrentGeneration(generation)) return;
        setCockpit(payload);
        setError("");
      } catch (cause) {
        if (session.isCurrentGeneration(generation)) {
          setError(cause instanceof Error ? cause.message : "Action failed");
        }
      } finally {
        if (session.isCurrentGeneration(generation)) setLoading(false);
      }
    },
    [session],
  );

  const startBot = useCallback(async () => {
    if (!session.token || !session.apiBaseUrl) return;
    await runGuardedAction(() => startMobileBot(session.apiBaseUrl, session.token!));
  }, [runGuardedAction, session.apiBaseUrl, session.token]);

  const stopBot = useCallback(async () => {
    if (!session.token || !session.apiBaseUrl) return;
    await runGuardedAction(() => stopMobileBot(session.apiBaseUrl, session.token!));
  }, [runGuardedAction, session.apiBaseUrl, session.token]);

  const setKillSwitch = useCallback(
    async (enabled: boolean, reason: string) => {
      if (!session.token || !session.apiBaseUrl) return;
      await runGuardedAction(() =>
        setMobileKillSwitch(session.apiBaseUrl, session.token!, enabled, sanitizeReason(reason)),
      );
    },
    [runGuardedAction, session.apiBaseUrl, session.token],
  );

  const clearSession = useCallback(async () => {
    const cleared = await session.clearSession();
    if (cleared) {
      setCockpit(null);
      setFeed(null);
      setConnected(false);
      setError("");
    }
  }, [session]);

  const value = useMemo<MobileSessionValue>(
    () => ({
      apiBaseUrl: session.apiBaseUrl,
      token: session.token,
      device: session.device,
      cockpit,
      feed,
      connected: connected && connection.online,
      locked: session.locked,
      loading: loading || session.loading,
      error: session.error || error,
      setError,
      pairWithManualCode,
      pairWithQrPayload,
      probeHealth,
      refreshCockpit,
      loadFeed,
      unlockControls: session.unlockControls,
      startBot,
      stopBot,
      setKillSwitch,
      clearSession,
    }),
    [
      clearSession,
      cockpit,
      connected,
      connection.online,
      error,
      feed,
      loadFeed,
      loading,
      pairWithManualCode,
      pairWithQrPayload,
      probeHealth,
      refreshCockpit,
      session,
      setKillSwitch,
      startBot,
      stopBot,
    ],
  );

  return <MobileSessionContext.Provider value={value}>{children}</MobileSessionContext.Provider>;
}

export function MobileSessionProvider({ children }: { children: React.ReactNode }) {
  const session = useOptionalSession();
  if (session) {
    return <ModernCockpitCompatibilityProvider session={session}>{children}</ModernCockpitCompatibilityProvider>;
  }
  return <LegacyMobileSessionProvider>{children}</LegacyMobileSessionProvider>;
}

function mapLegacyMobileSession(
  session: SessionContextValue | null,
  cockpit: MobileSessionValue,
): MobileSessionValue {
  if (!session) return cockpit;
  return {
    ...cockpit,
    apiBaseUrl: session.apiBaseUrl,
    token: session.token,
    device: session.device,
    locked: session.locked,
    loading: session.loading || cockpit.loading,
    error: session.error || cockpit.error,
  };
}

export function useMobileSession(): MobileSessionValue {
  const session = useOptionalSession();
  const cockpit = useCockpitCompatibility();
  return mapLegacyMobileSession(session, cockpit);
}
