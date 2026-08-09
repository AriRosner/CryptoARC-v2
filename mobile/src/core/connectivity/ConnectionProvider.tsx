import NetInfo from "@react-native-community/netinfo";
import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AppState, type AppStateStatus } from "react-native";

import {
  MobileApiError,
  mobileWebSocketTicketUrl,
  requestMobileWebSocketTicket,
} from "../../api";
import { mobileQueryClient } from "../api/queryClient";
import { useSession } from "../session/SessionProvider";
import { useSettingsStore } from "../settings/settingsStore";
import { initialRealtimeState, MobileRealtimeClient } from "./realtime";
import type { MobileRealtimeState } from "./types";

interface ConnectionContextValue {
  online: boolean;
  realtime: MobileRealtimeState;
}

const ConnectionContext = createContext<ConnectionContextValue | null>(null);

export function ConnectionProvider({ children }: { children: React.ReactNode }) {
  const session = useSession();
  const pollingIntervalMs = useSettingsStore((settings) => settings.refreshIntervalMs);
  const clientRef = useRef<MobileRealtimeClient | null>(null);
  const [appActive, setAppActive] = useState(AppState.currentState === "active");
  const [online, setOnline] = useState(true);
  const [realtime, setRealtime] = useState<MobileRealtimeState>(initialRealtimeState);

  useEffect(
    () =>
      NetInfo.addEventListener((state) => {
        setOnline(Boolean(state.isConnected && state.isInternetReachable !== false));
      }),
    [],
  );

  useEffect(() => {
    const onAppStateChange = (state: AppStateStatus) => setAppActive(state === "active");
    const subscription = AppState.addEventListener("change", onAppStateChange);
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    clientRef.current?.disconnect();
    clientRef.current = null;
    if (!session.record || !online || !appActive) {
      setRealtime((current) => ({
        ...current,
        reason: online ? "" : "offline",
        status: "offline",
      }));
      return;
    }

    const record = session.record;
    const client = new MobileRealtimeClient({
      urlFactory: async () => {
        const issued = await requestMobileWebSocketTicket(record.apiBaseUrl, record.token);
        return mobileWebSocketTicketUrl(record.apiBaseUrl, issued.ticket);
      },
      initialState: {
        ...realtime,
        status: realtime.requiresSnapshot ? realtime.status : "offline",
      },
      isAuthenticationError: (error) =>
        error instanceof MobileApiError &&
        error.status === 401,
      onStateChange: setRealtime,
      onRevoked: () => {
        void session.revokeSession();
      },
      queryClient: mobileQueryClient,
    });
    clientRef.current = client;
    client.connect();
    return () => {
      client.disconnect();
      if (clientRef.current === client) clientRef.current = null;
    };
  }, [appActive, online, session.record?.apiBaseUrl, session.record?.token]);

  useEffect(() => {
    if (!session.record || !online || !appActive || realtime.status === "connected") return;
    const timer = setInterval(() => {
      void mobileQueryClient.invalidateQueries({ queryKey: ["mobile"] });
    }, pollingIntervalMs);
    return () => clearInterval(timer);
  }, [appActive, online, pollingIntervalMs, realtime.status, session.record]);

  const value = useMemo(() => ({ online, realtime }), [online, realtime]);
  return <ConnectionContext.Provider value={value}>{children}</ConnectionContext.Provider>;
}

export function useConnection(): ConnectionContextValue {
  const value = useContext(ConnectionContext);
  if (!value) throw new Error("useConnection must be used inside ConnectionProvider");
  return value;
}
