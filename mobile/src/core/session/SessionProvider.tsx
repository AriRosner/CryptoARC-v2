import * as LocalAuthentication from "expo-local-authentication";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { AppState, type AppStateStatus } from "react-native";

import type { MobileDevice } from "../../types";
import { secureSessionStorage } from "./storage";
import type { SecureSessionRecord, SessionState } from "./types";

const SESSION_LOAD_FAILED = "Secure session could not be loaded. Pair this device again.";
const SESSION_SAVE_FAILED = "Secure session could not be saved. The previous session remains active.";
const SESSION_CLEAR_FAILED = "Disconnect failed. Session remains active.";

export interface SessionContextValue extends SessionState {
  apiBaseUrl: string;
  token: string | null;
  device: MobileDevice | null;
  replaceSession(apiBaseUrl: string, token: string, device: MobileDevice): Promise<void>;
  clearSession(): Promise<boolean>;
  lock(): void;
  unlockControls(): Promise<boolean>;
  setError(value: string): void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<SessionState>({
    record: null,
    loading: true,
    locked: true,
    error: "",
  });

  useEffect(() => {
    let active = true;
    void secureSessionStorage.loadOrMigrate().then(
      (record) => {
        if (active) {
          setState({
            record,
            loading: false,
            locked: Boolean(record),
            error: "",
          });
        }
      },
      () => {
        if (active) {
          setState({
            record: null,
            loading: false,
            locked: true,
            error: SESSION_LOAD_FAILED,
          });
        }
      },
    );
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const onAppStateChange = (nextState: AppStateStatus) => {
      if (nextState !== "active") {
        setState((current) => ({ ...current, locked: Boolean(current.record) }));
      }
    };
    const subscription = AppState.addEventListener("change", onAppStateChange);
    return () => subscription.remove();
  }, []);

  const replaceSession = useCallback(
    async (apiBaseUrl: string, token: string, device: MobileDevice): Promise<void> => {
      const record: SecureSessionRecord = {
        version: 2,
        apiBaseUrl,
        token,
        device,
        savedAt: new Date().toISOString(),
      };
      setState((current) => ({ ...current, loading: true, error: "" }));
      try {
        await secureSessionStorage.save(record);
        setState({ record, loading: false, locked: true, error: "" });
      } catch (error) {
        setState((current) => ({ ...current, loading: false, error: SESSION_SAVE_FAILED }));
        throw error;
      }
    },
    [],
  );

  const clearSession = useCallback(async (): Promise<boolean> => {
    try {
      await secureSessionStorage.clear();
      setState({ record: null, loading: false, locked: true, error: "" });
      return true;
    } catch {
      setState((current) => ({ ...current, error: SESSION_CLEAR_FAILED }));
      return false;
    }
  }, []);

  const lock = useCallback(() => {
    setState((current) => ({ ...current, locked: Boolean(current.record) }));
  }, []);

  const unlockControls = useCallback(async (): Promise<boolean> => {
    if (!state.record) return false;
    try {
      const [hasHardware, enrolled] = await Promise.all([
        LocalAuthentication.hasHardwareAsync(),
        LocalAuthentication.isEnrolledAsync(),
      ]);
      if (!hasHardware || !enrolled) {
        setState((current) => ({
          ...current,
          error: "Device unlock is not configured for guarded controls.",
        }));
        return false;
      }
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: "Unlock CryptoARC controls",
        cancelLabel: "Cancel",
        disableDeviceFallback: false,
      });
      if (!result.success) {
        setState((current) => ({ ...current, error: "Controls remain locked." }));
        return false;
      }
      setState((current) => ({ ...current, locked: false, error: "" }));
      return true;
    } catch {
      setState((current) => ({ ...current, error: "Local unlock failed." }));
      return false;
    }
  }, [state.record]);

  const setError = useCallback((error: string) => {
    setState((current) => ({ ...current, error }));
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      ...state,
      apiBaseUrl: state.record?.apiBaseUrl ?? "",
      token: state.record?.token ?? null,
      device: state.record?.device ?? null,
      clearSession,
      lock,
      replaceSession,
      setError,
      unlockControls,
    }),
    [clearSession, lock, replaceSession, setError, state, unlockControls],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useOptionalSession(): SessionContextValue | null {
  return useContext(SessionContext);
}

export function useSession(): SessionContextValue {
  const value = useOptionalSession();
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
