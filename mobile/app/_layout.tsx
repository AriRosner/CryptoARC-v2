import "react-native-gesture-handler";

import { BottomSheetModalProvider } from "@gorhom/bottom-sheet";
import { useFonts } from "expo-font";
import { DarkTheme, Stack, ThemeProvider } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import "react-native-reanimated";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import { MobileSessionProvider } from "@/src/MobileSession";
import { mobileQueryClient } from "@/src/core/api/queryClient";
import { ConnectionProvider } from "@/src/core/connectivity/ConnectionProvider";
import { NotificationBridge } from "@/src/core/notifications/notifications";
import { SessionProvider } from "@/src/core/session/SessionProvider";

export {
  // Catch any errors thrown by the Layout component.
  ErrorBoundary,
} from 'expo-router';

export const unstable_settings = {
  // Ensure that reloading on `/modal` keeps a back button present.
  initialRouteName: '(tabs)',
};

// Prevent the splash screen from auto-hiding before asset loading is complete.
SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [loaded, error] = useFonts({
    SpaceMono: require("../assets/fonts/SpaceMono-Regular.ttf"),
  });

  // Expo Router uses Error Boundaries to catch errors in the navigation tree.
  useEffect(() => {
    if (error) throw error;
  }, [error]);

  useEffect(() => {
    if (loaded) {
      SplashScreen.hideAsync();
    }
  }, [loaded]);

  if (!loaded) {
    return null;
  }

  return <RootLayoutNav />;
}

export function RootLayoutNav() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <BottomSheetModalProvider>
        <QueryClientProvider client={mobileQueryClient}>
          <SessionProvider>
            <NotificationBridge />
            <ConnectionProvider>
              <MobileSessionProvider>
                <ThemeProvider value={DarkTheme}>
                  <StatusBar style="light" />
                  <Stack>
                    <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
                    <Stack.Screen name="position/[positionId]" options={{ headerShown: false }} />
                    <Stack.Screen name="trade/[intentId]" options={{ headerShown: false }} />
                    <Stack.Screen name="diagnostics" options={{ headerShown: false }} />
                  </Stack>
                </ThemeProvider>
              </MobileSessionProvider>
            </ConnectionProvider>
          </SessionProvider>
        </QueryClientProvider>
      </BottomSheetModalProvider>
    </GestureHandlerRootView>
  );
}
