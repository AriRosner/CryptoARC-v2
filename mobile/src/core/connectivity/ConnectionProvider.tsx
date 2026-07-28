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

function websocketUrl(apiBaseUrl: string, token: string): string {
  const wsBase = apiBaseUrl.replace(/^https:/i, "wss:").replace(/^http:/i, "ws:").replace(/\/+$/, "");
  return `${wsBase}/ws/mobile?token=${encodeURIComponent(token)}`;
}

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

    const client = new MobileRealtimeClient({
      url: websocketUrl(session.record.apiBaseUrl, session.record.token),
      initialState: {
        ...realtime,
        status: realtime.requiresSnapshot ? realtime.status : "offline",
      },
      onStateChange: setRealtime,
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
