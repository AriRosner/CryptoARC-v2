import NetInfo from "@react-native-community/netinfo";
import * as Notifications from "expo-notifications";
import React from "react";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import {
  NOTIFICATION_CHANNELS,
  processNotificationResponse,
  startNativePushRegistration,
} from "../../../core/notifications/notifications";
import { AlertsScreen } from "../AlertsScreen";
import type { MobileAlert } from "../types";

const alert: MobileAlert = {
  event_id: "evt_trade_123",
  created_at: "2026-07-29T14:00:00Z",
  severity: "danger",
  subsystem: "trade",
  title: "Critical trade alert",
  summary: "Review this event on the trusted backend.",
  route: "/trade/intent_abc123",
  acknowledged: false,
  acknowledged_at: null,
};

describe("native notifications and alerts", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it("defines the required Android channels and importance levels", () => {
    expect(NOTIFICATION_CHANNELS).toEqual({
      critical: { name: "Critical trading alerts", importance: 5 },
      warning: { name: "Trading warnings", importance: 4 },
      activity: { name: "Operator activity", importance: 3 },
    });
  });

  it("waits for app unlock before navigating a validated trade route", async () => {
    let releaseUnlock: ((value: boolean) => void) | undefined;
    const unlockControls = jest.fn(
      () =>
        new Promise<boolean>((resolve) => {
          releaseUnlock = resolve;
        }),
    );
    const navigate = jest.fn();
    const session = {
      generation: 7,
      locked: true,
      isCurrentGeneration: jest.fn(() => true),
      revokeSession: jest.fn(async () => true),
      unlockControls,
    };

    const pending = processNotificationResponse(
      {
        event_id: "evt_trade_123",
        severity: "danger",
        subsystem: "trade",
        route: "/trade/intent_abc123",
      },
      session,
      navigate,
    );

    expect(unlockControls).toHaveBeenCalledTimes(1);
    expect(navigate).not.toHaveBeenCalled();
    releaseUnlock?.(true);
    await pending;
    expect(navigate).toHaveBeenCalledWith("/trade/intent_abc123");
  });

  it("rejects malformed routes and generation-stale unlocks", async () => {
    const navigate = jest.fn();
    const quarantine = jest.fn();
    const session = {
      generation: 8,
      locked: true,
      isCurrentGeneration: jest.fn(() => false),
      revokeSession: jest.fn(async () => true),
      unlockControls: jest.fn(async () => true),
    };

    await processNotificationResponse(
      {
        event_id: "evt_trade_123",
        severity: "danger",
        subsystem: "trade",
        route: "/trade/../../diagnostics",
      },
      session,
      navigate,
      quarantine,
    );
    await processNotificationResponse(
      {
        event_id: "evt_trade_123",
        severity: "danger",
        subsystem: "trade",
        route: "/trade/intent_abc123",
      },
      session,
      navigate,
      quarantine,
    );

    expect(navigate).not.toHaveBeenCalled();
    expect(quarantine).toHaveBeenCalledWith("invalid_notification_route");
  });

  it("retries registration when connectivity returns and handles token rotation", async () => {
    let connectivityListener:
      | ((state: { isConnected: boolean; isInternetReachable: boolean }) => void)
      | undefined;
    (NetInfo.fetch as jest.Mock).mockResolvedValueOnce({
      isConnected: false,
      isInternetReachable: false,
    });
    (NetInfo.addEventListener as jest.Mock).mockImplementation((listener) => {
      connectivityListener = listener;
      return jest.fn();
    });
    (Notifications.getExpoPushTokenAsync as jest.Mock)
      .mockResolvedValueOnce({
        data: "ExponentPushToken[first-transient]",
      })
      .mockResolvedValueOnce({
        data: "ExponentPushToken[rotated-transient]",
      });
    let rotationListener: (() => void) | undefined;
    (
      Notifications.addPushTokenListener as unknown as jest.Mock
    ).mockImplementation((listener) => {
      rotationListener = listener;
      return { remove: jest.fn() };
    });
    const register = jest.fn(async () => undefined);
    const session = {
      apiBaseUrl: "https://node.tailnet.ts.net",
      token: "mobile-session-secret",
      generation: 11,
      isCurrentGeneration: jest.fn(() => true),
      revokeSession: jest.fn(async () => true),
    };

    const cleanup = await startNativePushRegistration({
      projectId: "project-id",
      session,
      register,
    });
    expect(register).not.toHaveBeenCalled();

    connectivityListener?.({
      isConnected: true,
      isInternetReachable: true,
    });
    await waitFor(() =>
      expect(register).toHaveBeenCalledWith(
        "ExponentPushToken[first-transient]",
        expect.objectContaining({ generation: 11 }),
      ),
    );

    rotationListener?.();
    await waitFor(() =>
      expect(register).toHaveBeenCalledWith(
        "ExponentPushToken[rotated-transient]",
        expect.objectContaining({ generation: 11 }),
      ),
    );
    cleanup();
  });

  it("renders duplicate event IDs once and exposes accessible acknowledgement", async () => {
    const acknowledge = jest.fn();
    const view = await render(
      <AlertsScreen
        alerts={[alert, { ...alert, summary: "Duplicate delivery" }]}
        loading={false}
        error=""
        onRefresh={jest.fn()}
        onAcknowledge={acknowledge}
      />,
    );

    expect(view.getAllByText("Critical trade alert")).toHaveLength(1);
    const button = view.getByRole("button", {
      name: "Acknowledge critical trade alert",
    });
    fireEvent.press(button);
    expect(acknowledge).toHaveBeenCalledWith("evt_trade_123");
  });

  it("renders the alert loading skeleton", async () => {
    const loading = await render(
      <AlertsScreen
        alerts={[]}
        loading
        error=""
        onRefresh={jest.fn()}
        onAcknowledge={jest.fn()}
      />,
    );
    expect(loading.getByLabelText("Loading alerts")).toBeTruthy();
  });

  it("renders the alert error and empty state", async () => {
    const empty = await render(
      <AlertsScreen
        alerts={[]}
        loading={false}
        error="Unable to load alerts"
        onRefresh={jest.fn()}
        onAcknowledge={jest.fn()}
      />,
    );
    expect(empty.getByText("No active alerts")).toBeTruthy();
    expect(empty.getByRole("alert")).toBeTruthy();
  });
});
