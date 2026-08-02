import * as LocalAuthentication from "expo-local-authentication";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AppState, type AppStateStatus } from "react-native";

import type { MobileDevice } from "../../types";
import { unregisterPushToken } from "../../features/alerts/api";
import { mobileQueryClient } from "../api/queryClient";
import {
  SecureSessionRollbackError,
  secureSessionStorage,
} from "./storage";
import type { SecureSessionRecord, SessionState } from "./types";

const SESSION_LOAD_FAILED = "Secure session could not be loaded. Pair this device again.";
const SESSION_SAVE_FAILED = "Secure session could not be saved. The previous session remains active.";
const SESSION_CLEAR_FAILED = "Disconnect failed. Session remains active.";

async function bestEffortUnregister(record: SecureSessionRecord | null): Promise<void> {
  if (!record) return;
  try {
    await unregisterPushToken({
      apiBaseUrl: record.apiBaseUrl,
      token: record.token,
    });
  } catch {
    // Server-side device expiry/revocation remains authoritative while offline.
  }
}

export interface SessionContextValue extends SessionState {
  apiBaseUrl: string;
  token: string | null;
  device: MobileDevice | null;
  replaceSession(
    apiBaseUrl: string,
    token: string,
    device: MobileDevice,
    expectedGeneration?: number,
  ): Promise<boolean>;
  clearSession(): Promise<boolean>;
  revokeSession(expectedGeneration?: number): Promise<boolean>;
  isCurrentGeneration(generation: number): boolean;
  lock(): void;
  unlockControls(): Promise<boolean>;
  setError(value: string): void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const initialState: SessionState = {
    record: null,
    generation: 0,
    loading: true,
    locked: true,
    error: "",
  };
  const [state, setState] = useState<SessionState>(initialState);
  const stateRef = useRef(initialState);
  const generationRef = useRef(0);
  const mutationQueueRef = useRef<Promise<void>>(Promise.resolve());

  const updateState = useCallback((update: (current: SessionState) => SessionState) => {
    const next = update(stateRef.current);
    stateRef.current = next;
    setState(next);
  }, []);

  const nextGeneration = useCallback((): number => {
    generationRef.current += 1;
    return generationRef.current;
  }, []);

  const isCurrentGeneration = useCallback(
    (generation: number): boolean => generationRef.current === generation,
    [],
  );

  const enqueueMutation = useCallback(<T,>(operation: () => Promise<T>): Promise<T> => {
    const result = mutationQueueRef.current.then(operation, operation);
    mutationQueueRef.current = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }, []);

  useEffect(() => {
    let active = true;
    const initializationGeneration = generationRef.current;
    void enqueueMutation(() => secureSessionStorage.loadOrMigrate()).then(
      (record) => {
        if (active && isCurrentGeneration(initializationGeneration)) {
          const generation = nextGeneration();
          updateState(() => ({
            record,
            generation,
            loading: false,
            locked: Boolean(record),
            error: "",
          }));
        }
      },
      () => {
        if (active && isCurrentGeneration(initializationGeneration)) {
          const generation = nextGeneration();
          updateState(() => ({
            record: null,
            generation,
            loading: false,
            locked: true,
            error: SESSION_LOAD_FAILED,
          }));
        }
      },
    );
    return () => {
      active = false;
    };
  }, [enqueueMutation, isCurrentGeneration, nextGeneration, updateState]);

  useEffect(() => {
    const onAppStateChange = (nextState: AppStateStatus) => {
      if (nextState !== "active") {
        updateState((current) => ({ ...current, locked: Boolean(current.record) }));
      }
    };
    const subscription = AppState.addEventListener("change", onAppStateChange);
    return () => subscription.remove();
  }, [updateState]);

  const replaceSession = useCallback(
    async (
      apiBaseUrl: string,
      token: string,
      device: MobileDevice,
      expectedGeneration?: number,
    ): Promise<boolean> => {
      if (
        expectedGeneration !== undefined &&
        !isCurrentGeneration(expectedGeneration)
      ) {
        return false;
      }
      const record: SecureSessionRecord = {
        version: 2,
        apiBaseUrl,
        token,
        device,
        savedAt: new Date().toISOString(),
      };
      const previousRecord = stateRef.current.record;
      const generation = nextGeneration();
      updateState((current) => ({
        ...current,
        generation,
        loading: true,
        error: "",
      }));
      try {
        await enqueueMutation(() => secureSessionStorage.save(record));
        if (!isCurrentGeneration(generation)) return false;
        if (
          previousRecord &&
          (previousRecord.apiBaseUrl !== record.apiBaseUrl ||
            previousRecord.token !== record.token)
        ) {
          await bestEffortUnregister(previousRecord);
        }
        updateState(() => ({
          record,
          generation,
          loading: false,
          locked: true,
          error: "",
        }));
        return true;
      } catch (error) {
        if (isCurrentGeneration(generation)) {
          updateState((current) =>
            error instanceof SecureSessionRollbackError
              ? {
                  record: null,
                  generation,
                  loading: false,
                  locked: true,
                  error: SESSION_SAVE_FAILED,
                }
              : {
                  ...current,
                  loading: false,
                  error: SESSION_SAVE_FAILED,
                },
          );
        }
        throw error;
      }
    },
    [
      enqueueMutation,
      isCurrentGeneration,
      nextGeneration,
      updateState,
    ],
  );

  const clearSession = useCallback(async (): Promise<boolean> => {
    const previousRecord = stateRef.current.record;
    const generation = nextGeneration();
    updateState((current) => ({
      ...current,
      generation,
      loading: true,
    }));
    try {
      await bestEffortUnregister(previousRecord);
      await enqueueMutation(() => secureSessionStorage.clear());
      if (isCurrentGeneration(generation)) {
        updateState(() => ({
          record: null,
          generation,
          loading: false,
          locked: true,
          error: "",
        }));
      }
      return true;
    } catch {
      if (isCurrentGeneration(generation)) {
        updateState((current) => ({
          ...current,
          loading: false,
          error: SESSION_CLEAR_FAILED,
        }));
      }
      return false;
    }
  }, [
    enqueueMutation,
    isCurrentGeneration,
    nextGeneration,
    updateState,
  ]);

  const revokeSession = useCallback(async (
    expectedGeneration?: number,
  ): Promise<boolean> => {
    if (
      expectedGeneration !== undefined &&
      !isCurrentGeneration(expectedGeneration)
    ) {
      return false;
    }
    const generation = nextGeneration();
    updateState(() => ({
      record: null,
      generation,
      loading: false,
      locked: true,
      error: "Mobile session was revoked. Pair this device again.",
    }));
    mobileQueryClient.removeQueries({ queryKey: ["mobile"] });
    try {
      await enqueueMutation(() => secureSessionStorage.clear());
    } catch {
      if (isCurrentGeneration(generation)) {
        updateState((current) => ({
          ...current,
          error: "Revoked mobile credentials could not be removed from secure storage.",
        }));
      }
    }
    return true;
  }, [
    enqueueMutation,
    isCurrentGeneration,
    nextGeneration,
    updateState,
  ]);

  const lock = useCallback(() => {
    updateState((current) => ({ ...current, locked: Boolean(current.record) }));
  }, [updateState]);

  const unlockControls = useCallback(async (): Promise<boolean> => {
    const generation = generationRef.current;
    if (!stateRef.current.record) return false;
    try {
      const [hasHardware, enrolled] = await Promise.all([
        LocalAuthentication.hasHardwareAsync(),
        LocalAuthentication.isEnrolledAsync(),
      ]);
      if (!isCurrentGeneration(generation)) return false;
      if (!hasHardware || !enrolled) {
        updateState((current) => ({
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
      if (!isCurrentGeneration(generation)) return false;
      if (!result.success) {
        updateState((current) => ({ ...current, error: "Controls remain locked." }));
        return false;
      }
      updateState((current) => ({ ...current, locked: false, error: "" }));
      return true;
    } catch {
      if (isCurrentGeneration(generation)) {
        updateState((current) => ({ ...current, error: "Local unlock failed." }));
      }
      return false;
    }
  }, [isCurrentGeneration, updateState]);

  const setError = useCallback((error: string) => {
    updateState((current) => ({ ...current, error }));
  }, [updateState]);

  const value = useMemo<SessionContextValue>(
    () => ({
      ...state,
      apiBaseUrl: state.record?.apiBaseUrl ?? "",
      token: state.record?.token ?? null,
      device: state.record?.device ?? null,
      clearSession,
      isCurrentGeneration,
      lock,
      replaceSession,
      revokeSession,
      setError,
      unlockControls,
    }),
    [
      clearSession,
      isCurrentGeneration,
      lock,
      replaceSession,
      revokeSession,
      setError,
      state,
      unlockControls,
    ],
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
