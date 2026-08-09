import { fireEvent, render, waitFor } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";

import { fetchMobileCockpit, setMobileKillSwitch } from "../../../api";
import { MoreScreen } from "../MoreScreen";

const mockAuthorizeControl = jest.fn();
const mockIsControlAuthorizationCurrent = jest.fn(() => true);
const mockConnection = { online: true };
const mockSession = {
  apiBaseUrl: "https://operator.test",
  token: "mobile-token",
  generation: 4,
  isCurrentGeneration: (generation: number) => generation === 4,
};

jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
  useLocalSearchParams: () => ({ section: "system" }),
}));

jest.mock("../../../api", () => ({
  fetchMobileCockpit: jest.fn(),
  setMobileKillSwitch: jest.fn(),
}));

jest.mock("../../../components/system/AppLock", () => ({
  useAppLock: () => ({
    authorizeControl: mockAuthorizeControl,
    isControlAuthorizationCurrent: mockIsControlAuthorizationCurrent,
  }),
}));

jest.mock("../../../core/connectivity/ConnectionProvider", () => ({
  useConnection: () => mockConnection,
}));

jest.mock("../../../core/session/SessionProvider", () => ({
  useSession: () => mockSession,
}));

const cockpit = {
  live: { kill_switch_enabled: false },
  readiness: { score: 90, entries_allowed: false },
  source: { health_score: 80 },
  open_risk: { live_open_positions: 0 },
};

describe("emergency kill switch", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(fetchMobileCockpit).mockResolvedValue(cockpit as never);
    jest.mocked(setMobileKillSwitch).mockResolvedValue({
      ...cockpit,
      live: { kill_switch_enabled: true },
    } as never);
    mockAuthorizeControl.mockResolvedValue({ bindingKey: "proof" });
    mockIsControlAuthorizationCurrent.mockReturnValue(true);
    jest.spyOn(Alert, "alert").mockImplementation(jest.fn());
  });

  afterEach(() => jest.restoreAllMocks());

  it("enables immediately with a deterministic audit reason when the field is empty", async () => {
    const screen = await render(<MoreScreen />);
    await screen.findByText("Enable Kill Switch");

    await fireEvent.press(screen.getByText("Enable Kill Switch"));

    await waitFor(() =>
      expect(setMobileKillSwitch).toHaveBeenCalledWith(
        "https://operator.test",
        "mobile-token",
        true,
        "Emergency mobile kill-switch enable",
      ),
    );
    expect(mockAuthorizeControl).toHaveBeenCalledTimes(1);
    expect(Alert.alert).not.toHaveBeenCalled();
  });

  it("does nothing when fresh centralized authorization is cancelled", async () => {
    mockAuthorizeControl.mockResolvedValueOnce(null);
    const screen = await render(<MoreScreen />);
    await screen.findByText("Enable Kill Switch");

    await fireEvent.press(screen.getByText("Enable Kill Switch"));

    expect(setMobileKillSwitch).not.toHaveBeenCalled();
    expect(mockAuthorizeControl).toHaveBeenCalledTimes(1);
  });

  it("reports an enable failure without queuing or changing the reviewed control", async () => {
    jest.mocked(setMobileKillSwitch).mockRejectedValueOnce(new Error("offline"));
    const screen = await render(<MoreScreen />);
    await screen.findByText("Enable Kill Switch");

    await fireEvent.press(screen.getByText("Enable Kill Switch"));

    expect(await screen.findByText("Kill-switch update failed.")).toBeTruthy();
    expect(setMobileKillSwitch).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Enable Kill Switch")).toBeTruthy();
  });

  it("keeps clearing stricter by requiring an operator-entered reason before authorization", async () => {
    jest.mocked(fetchMobileCockpit).mockResolvedValueOnce({
      ...cockpit,
      live: { kill_switch_enabled: true },
    } as never);
    const screen = await render(<MoreScreen />);
    await screen.findByText("Clear Kill Switch");

    await fireEvent.press(screen.getByText("Clear Kill Switch"));

    expect(Alert.alert).toHaveBeenCalledWith(
      "Reason required",
      "Enter a short reason before clearing the kill switch.",
    );
    expect(mockAuthorizeControl).not.toHaveBeenCalled();
    expect(setMobileKillSwitch).not.toHaveBeenCalled();
  });
});
