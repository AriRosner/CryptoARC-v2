import NetInfo from "@react-native-community/netinfo";
import { QueryClient, focusManager, onlineManager } from "@tanstack/react-query";
import { AppState, type AppStateStatus } from "react-native";

import { MobileApiError } from "./errors";

export const mobileQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      gcTime: 30 * 60 * 1000,
      refetchOnReconnect: true,
      retry: (failureCount, error) =>
        failureCount < 2 && error instanceof MobileApiError && error.retryable,
      staleTime: 15000,
    },
    mutations: {
      retry: false,
    },
  },
});

focusManager.setEventListener((setFocused) => {
  const onAppStateChange = (state: AppStateStatus) => setFocused(state === "active");
  const subscription = AppState.addEventListener("change", onAppStateChange);
  return () => subscription.remove();
});

onlineManager.setEventListener((setOnline) =>
  NetInfo.addEventListener((state) => {
    setOnline(Boolean(state.isConnected && state.isInternetReachable !== false));
  }),
);
