import { render } from "@testing-library/react-native";
import React from "react";

import { DeviceScreen } from "../DeviceScreen";

jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
}));

jest.mock("../../../core/connectivity/ConnectionProvider", () => ({
  useConnection: () => ({ online: true, realtime: { status: "connected" } }),
}));

jest.mock("../../../core/session/SessionProvider", () => ({
  useSession: () => ({
    apiBaseUrl: "https://cryptoarc-node.tailnet.example",
    clearSession: jest.fn(async () => undefined),
    device: null,
    error: "",
    locked: true,
    token: null,
  }),
}));

describe("Device release marker", () => {
  it("shows the Operator Command Center version and Android build before pairing", async () => {
    const screen = await render(<DeviceScreen />);

    expect(
      screen.getByText("Operator Command Center v2.0.0 (2026-07-26)"),
    ).toBeTruthy();
    expect(screen.getByText("2.0.0 / Android 5")).toBeTruthy();
  });
});
