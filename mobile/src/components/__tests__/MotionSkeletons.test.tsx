import * as Haptics from "expo-haptics";
import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { Animated } from "react-native";

import { ActionButton } from "../ui";
import { AnimatedNumber } from "../motion/AnimatedNumber";
import { triggerHaptic } from "../motion/haptics";
import { resolveMotionPolicy } from "../motion/policy";
import { runEmergencyAction } from "../motion/transitions";
import { Skeleton } from "../skeletons/Skeleton";
import { PortfolioSkeleton } from "../skeletons/PortfolioSkeleton";
import { PositionSkeleton } from "../skeletons/PositionSkeleton";
import { TradeSkeleton } from "../skeletons/TradeSkeleton";
import { TradeDetailSkeleton } from "../skeletons/TradeDetailSkeleton";
import { WalletSkeleton } from "../skeletons/WalletSkeleton";
import { AlertsSkeleton } from "../skeletons/AlertsSkeleton";
import { DiagnosticsSkeleton } from "../skeletons/DiagnosticsSkeleton";
import { useSettingsStore } from "../../core/settings/settingsStore";

describe("motion, haptics, and loading contracts", () => {
  beforeEach(() => jest.clearAllMocks());

  afterEach(() => {
    jest.useRealTimers();
    useSettingsStore.setState({ motion: "expressive" });
  });

  it("renders animated values by policy and cleans animation listeners", async () => {
    const stop = jest.fn();
    jest.spyOn(Animated, "timing").mockReturnValue({
      reset: jest.fn(),
      start: jest.fn(),
      stop,
    } as ReturnType<typeof Animated.timing>);
    useSettingsStore.setState({ motion: "expressive" });
    const view = await render(
      <AnimatedNumber value={1} format={(value) => value.toFixed(0)} />,
    );
    expect(view.getByTestId("animated-number")).toHaveProp(
      "accessibilityValue",
      { text: "Animated value" },
    );
    await view.rerender(
      <AnimatedNumber value={9} format={(value) => value.toFixed(0)} />,
    );
    await view.unmount();
    expect(stop).toHaveBeenCalled();

    await act(async () => useSettingsStore.setState({ motion: "minimal" }));
    const minimal = await render(
      <AnimatedNumber value={1} format={(value) => value.toFixed(0)} />,
    );
    await minimal.rerender(
      <AnimatedNumber value={9} format={(value) => value.toFixed(0)} />,
    );
    await waitFor(() => expect(minimal.getByText("9")).toBeTruthy());
    expect(minimal.getByTestId("animated-number")).toHaveProp(
      "accessibilityValue",
      { text: "Static value" },
    );
    await minimal.unmount();
    jest.restoreAllMocks();
  });

  it("uses full expressive motion and removes nonessential minimal motion", () => {
    expect(resolveMotionPolicy("expressive", false, true)).toMatchObject({
      shimmer: "full",
      sharedTransitions: true,
      haptics: true,
    });
    expect(resolveMotionPolicy("balanced", false, true).duration.normal).toBeLessThan(
      resolveMotionPolicy("expressive", false, true).duration.normal,
    );
    expect(resolveMotionPolicy("minimal", false, true)).toMatchObject({
      duration: { fast: 0, normal: 0, slow: 0 },
      shimmer: "static",
      sharedTransitions: false,
    });
    expect(resolveMotionPolicy("system", true, true).shimmer).toBe("static");
  });

  it("uses a static skeleton in reduced motion", async () => {
    const view = await render(
      <Skeleton width={120} height={20} motionMode="system" reduceMotion />,
    );
    expect(view.getByTestId("skeleton-shimmer")).toHaveProp(
      "accessibilityValue",
      { text: "Static loading placeholder" },
    );
    expect(view.getByTestId("skeleton-shimmer")).not.toHaveProp("animated");
  });

  it("provides a distinct layout-matched skeleton for every content route", async () => {
    const view = await render(
      <>
        <PortfolioSkeleton />
        <PositionSkeleton />
        <TradeSkeleton />
        <WalletSkeleton />
        <AlertsSkeleton />
        <DiagnosticsSkeleton />
      </>,
    );
    for (const id of [
      "portfolio-initial-skeleton",
      "position-initial-skeleton",
      "trade-initial-skeleton",
      "wallet-initial-skeleton",
      "alerts-initial-skeleton",
      "diagnostics-initial-skeleton",
    ]) {
      expect(view.getByTestId(id)).toBeTruthy();
    }
  });

  it("matches trade detail header, evidence, form, and authentication regions", async () => {
    const view = await render(<TradeDetailSkeleton />);
    expect(view.getByTestId("trade-detail-header-skeleton")).toHaveStyle({ height: 48 });
    expect(view.getByTestId("trade-detail-evidence-skeleton")).toHaveStyle({ height: 180 });
    expect(view.getByTestId("trade-detail-form-skeleton")).toHaveStyle({ height: 260 });
    expect(view.getByTestId("trade-detail-auth-skeleton")).toHaveStyle({ height: 64 });
    expect(view.queryByTestId("trade-initial-skeleton")).toBeNull();
  });

  it("retains stable action dimensions and pending text in place", async () => {
    const view = await render(
      <ActionButton label="Confirm withdrawal" loading onPress={jest.fn()} />,
    );
    const button = view.getByRole("button", { name: "Confirm withdrawal" });
    expect(button).toHaveProp("accessibilityState", {
      busy: true,
      disabled: true,
    });
    expect(view.getByText("Confirm withdrawal")).toBeTruthy();
  });

  it("maps selection, warning, rejection, and confirmation haptics", async () => {
    await triggerHaptic("selection", true);
    await triggerHaptic("warning", true);
    await triggerHaptic("rejection", true);
    await triggerHaptic("confirmation", true);

    expect(Haptics.selectionAsync).toHaveBeenCalledTimes(1);
    expect(Haptics.notificationAsync).toHaveBeenNthCalledWith(
      1,
      Haptics.NotificationFeedbackType.Warning,
    );
    expect(Haptics.notificationAsync).toHaveBeenNthCalledWith(
      2,
      Haptics.NotificationFeedbackType.Error,
    );
    expect(Haptics.notificationAsync).toHaveBeenNthCalledWith(
      3,
      Haptics.NotificationFeedbackType.Success,
    );
  });

  it("does not emit haptics when disabled", async () => {
    await triggerHaptic("confirmation", false);
    expect(Haptics.notificationAsync).not.toHaveBeenCalled();
  });

  it("runs emergency controls immediately without animation completion", () => {
    const emergency = jest.fn();
    const pending = Promise.resolve();
    runEmergencyAction(emergency, pending);
    expect(emergency).toHaveBeenCalledTimes(1);
  });
});
