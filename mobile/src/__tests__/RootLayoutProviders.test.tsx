import { render } from "@testing-library/react-native";
import React from "react";

jest.mock("react-native-reanimated", () => ({}));

jest.mock("@gorhom/bottom-sheet", () => {
  const { View: MockView } = jest.requireActual("react-native");
  return {
    BottomSheetModalProvider: ({ children }: { children?: React.ReactNode }) => (
      <MockView testID="bottom-sheet-provider">{children}</MockView>
    ),
  };
});

jest.mock("react-native-gesture-handler", () => {
  const { View: MockView } = jest.requireActual("react-native");
  return {
    GestureHandlerRootView: ({ children }: { children?: React.ReactNode }) => (
      <MockView testID="gesture-handler-root">{children}</MockView>
    ),
  };
});

jest.mock("@tanstack/react-query", () => ({
  QueryClient: jest.fn(),
  QueryClientProvider: () => null,
  focusManager: { setEventListener: jest.fn() },
  onlineManager: { setEventListener: jest.fn() },
}));

jest.mock("expo-router", () => ({
  DarkTheme: {},
  Stack: Object.assign(() => null, { Screen: () => null }),
  ThemeProvider: ({ children }: { children?: React.ReactNode }) => children ?? null,
}));

jest.mock("expo-status-bar", () => ({
  StatusBar: () => null,
}));

import { RootLayoutNav } from "../../app/_layout";

describe("RootLayoutNav", () => {
  it("installs gesture and bottom-sheet providers for modal sheets", async () => {
    const view = await render(<RootLayoutNav />);

    expect(view.getByTestId("gesture-handler-root")).toBeTruthy();
    expect(view.getByTestId("bottom-sheet-provider")).toBeTruthy();
  });
});
