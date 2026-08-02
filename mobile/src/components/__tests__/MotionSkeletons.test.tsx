import * as Haptics from "expo-haptics";
import React from "react";
import { fireEvent, render } from "@testing-library/react-native";

import { ActionButton } from "../ui";
import { triggerHaptic } from "../motion/haptics";
import { resolveMotionPolicy } from "../motion/policy";
import { runEmergencyAction } from "../motion/transitions";
import { Skeleton } from "../skeletons/Skeleton";
import { PortfolioSkeleton } from "../skeletons/PortfolioSkeleton";
import { PositionSkeleton } from "../skeletons/PositionSkeleton";
import { TradeSkeleton } from "../skeletons/TradeSkeleton";
import { WalletSkeleton } from "../skeletons/WalletSkeleton";
import { AlertsSkeleton } from "../skeletons/AlertsSkeleton";
import { DiagnosticsSkeleton } from "../skeletons/DiagnosticsSkeleton";

describe("motion, haptics, and loading contracts", () => {
  beforeEach(() => jest.clearAllMocks());

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
    expect(view.getByTestId("skeleton-shimmer")).toHaveProp("animated", false);
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
