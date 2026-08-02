import * as SecureStore from "expo-secure-store";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react-native";
import React from "react";
import { AppState, Text } from "react-native";

import { FINAL_TABS } from "../../../../app/(tabs)/_layout";
import DeviceRedirect from "../../../../app/device";
import FeedRedirect from "../../../../app/feed";
import RiskRedirect from "../../../../app/risk";
import { AppLock, useAppLock } from "../../../components/system/AppLock";
import {
  SETTINGS_STORAGE_KEY,
  flushSettingsPersistence,
  hydrateSettings,
  resetSettings,
  setPrivacyMode,
  useSettingsStore,
} from "../../../core/settings/settingsStore";
import { MoreScreen } from "../MoreScreen";
import { SettingsScreen } from "../SettingsScreen";

jest.mock("expo-router", () => {
  const ReactModule = jest.requireActual("react");
  const { Text: MockText, View: MockView } = jest.requireActual("react-native");
  const Tabs = Object.assign(
    ({ children }: { children?: React.ReactNode }) => <MockView>{children}</MockView>,
    {
      Screen: ({ name, options }: { name: string; options: { title: string } }) => (
        <MockText>{`${name}:${options.title}`}</MockText>
      ),
    },
  );
  return {
    Redirect: ({ href }: { href: string }) => <MockText>{`redirect:${href}`}</MockText>,
    Tabs,
    router: { push: jest.fn() },
    useLocalSearchParams: () => ({}),
  };
});

const unlockControls = jest.fn(async () => true);
const lockControls = jest.fn();
const session = {
  record: { token: "mobile-token" },
  generation: 4,
  loading: false,
  locked: true,
  unlockControls,
  lock: lockControls,
  isCurrentGeneration: (generation: number) => generation === 4,
};

jest.mock("../../../core/session/SessionProvider", () => ({
  useSession: () => session,
}));

function FinancialActionProbe() {
  const appLock = useAppLock();
  return (
    <Text accessibilityRole="button" onPress={() => void appLock.unlock("financial_action")}>
      Guarded action
    </Text>
  );
}

describe("AppLock and persisted settings", () => {
  let appStateListener: ((state: "active" | "background" | "inactive") => void) | undefined;
  let now = 1_000;

  beforeEach(async () => {
    jest.clearAllMocks();
    session.unlockControls = unlockControls;
    session.lock = lockControls;
    unlockControls.mockReset().mockResolvedValue(true);
    lockControls.mockReset();
    now = 1_000;
    appStateListener = undefined;
    jest.spyOn(AppState, "addEventListener").mockImplementation((_event, listener) => {
      appStateListener = listener as typeof appStateListener;
      return { remove: jest.fn() };
    });
    jest.mocked(SecureStore.getItemAsync).mockResolvedValue(null);
    jest.mocked(SecureStore.setItemAsync).mockResolvedValue(undefined);
    resetSettings({ persist: false });
  });

  afterEach(async () => {
    await cleanup();
    jest.restoreAllMocks();
  });

  it("defaults to a full-app lock that hides financial data", async () => {
    const screen = await render(
      <AppLock initialAppState="active" now={() => now}>
        <Text>Total portfolio</Text>
      </AppLock>,
    );

    expect(screen.getByText("Unlock CryptoARC")).toBeTruthy();
    expect(screen.queryByText("Total portfolio")).toBeNull();
  });

  it("allows read-only content before unlock without unlocking controls", async () => {
    await setPrivacyMode("read_only_before_unlock");
    const screen = await render(
      <AppLock initialAppState="active" now={() => now}>
        <Text>Total portfolio</Text>
      </AppLock>,
    );

    expect(screen.getByText("Total portfolio")).toBeTruthy();
    expect(screen.getByText("Controls locked")).toBeTruthy();
    expect(unlockControls).not.toHaveBeenCalled();
  });

  it("keeps cancellation locked", async () => {
    unlockControls.mockResolvedValueOnce(false);
    const screen = await render(
      <AppLock initialAppState="active" now={() => now}>
        <Text>Total portfolio</Text>
      </AppLock>,
    );

    await fireEvent.press(screen.getByText("Unlock CryptoARC"));

    expect(screen.getByText("Unlock CryptoARC")).toBeTruthy();
    expect(screen.queryByText("Total portfolio")).toBeNull();
  });

  it("covers content with an app-switcher privacy shield", async () => {
    const screen = await render(
      <AppLock initialAppState="active" now={() => now}>
        <Text>Total portfolio</Text>
      </AppLock>,
    );
    await fireEvent.press(screen.getByText("Unlock CryptoARC"));
    expect(screen.getByText("Total portfolio")).toBeTruthy();

    await act(async () => appStateListener?.("inactive"));

    expect(screen.getByText("CryptoARC protected")).toBeTruthy();
    expect(screen.queryByText("Total portfolio")).toBeNull();
  });

  it("locks on resume after the configured timeout", async () => {
    useSettingsStore.getState().update({ lockTimeoutMs: 60_000 });
    const screen = await render(
      <AppLock initialAppState="active" now={() => now}>
        <Text>Total portfolio</Text>
      </AppLock>,
    );
    await fireEvent.press(screen.getByText("Unlock CryptoARC"));
    expect(screen.getByText("Total portfolio")).toBeTruthy();

    await act(async () => appStateListener?.("background"));
    now += 60_001;
    await act(async () => appStateListener?.("active"));

    expect(screen.getByText("Unlock CryptoARC")).toBeTruthy();
    expect(screen.queryByText("Total portfolio")).toBeNull();
  });

  it("preserves an unlocked read-only view on a resume inside the timeout while controls relock", async () => {
    useSettingsStore.getState().update({ lockTimeoutMs: 60_000 });
    const screen = await render(
      <AppLock initialAppState="active" now={() => now}>
        <Text>Total portfolio</Text>
      </AppLock>,
    );
    await fireEvent.press(screen.getByText("Unlock CryptoARC"));
    expect(screen.getByText("Total portfolio")).toBeTruthy();

    await act(async () => appStateListener?.("background"));
    now += 5_000;
    await act(async () => appStateListener?.("active"));

    expect(screen.getByText("Total portfolio")).toBeTruthy();
    expect(lockControls).toHaveBeenCalled();
  });

  it("requests a fresh unlock for every financial action", async () => {
    const screen = await render(
      <AppLock initialAppState="active" now={() => now}>
        <FinancialActionProbe />
      </AppLock>,
    );
    await fireEvent.press(screen.getByText("Unlock CryptoARC"));
    expect(screen.getByText("Guarded action")).toBeTruthy();
    unlockControls.mockClear();

    await fireEvent.press(screen.getByText("Guarded action"));
    await fireEvent.press(screen.getByText("Guarded action"));

    expect(unlockControls).toHaveBeenCalledTimes(2);
  });

  it("rejects an app-open unlock that resolves after a background-resume cycle", async () => {
    let resolveAuthentication!: (success: boolean) => void;
    unlockControls.mockReturnValueOnce(
      new Promise<boolean>((resolve) => {
        resolveAuthentication = resolve;
      }),
    );
    const screen = await render(
      <AppLock initialAppState="active" now={() => now}>
        <Text>Total portfolio</Text>
      </AppLock>,
    );

    const unlocking = fireEvent.press(screen.getByText("Unlock CryptoARC"));
    appStateListener?.("background");
    now += 1;
    appStateListener?.("active");
    resolveAuthentication(true);
    await unlocking;

    expect(screen.getByText("Unlock CryptoARC")).toBeTruthy();
    expect(screen.queryByText("Total portfolio")).toBeNull();
  });

  it("persists and hydrates every privacy, motion, refresh, feedback, and timeout setting", async () => {
    useSettingsStore.getState().update({
      hapticsEnabled: false,
      lockTimeoutMs: 300_000,
      motion: "minimal",
      notificationPreviewsEnabled: true,
      privacyMode: "read_only_before_unlock",
      refreshProfile: "battery_saver",
    });
    await flushSettingsPersistence();
    const serialized = jest.mocked(SecureStore.setItemAsync).mock.lastCall?.[1];
    expect(jest.mocked(SecureStore.setItemAsync).mock.lastCall?.[0]).toBe(SETTINGS_STORAGE_KEY);

    resetSettings({ persist: false });
    jest.mocked(SecureStore.getItemAsync).mockResolvedValue(serialized ?? null);
    await hydrateSettings();

    expect(useSettingsStore.getState()).toMatchObject({
      hapticsEnabled: false,
      lockTimeoutMs: 300_000,
      motion: "minimal",
      notificationPreviewsEnabled: true,
      privacyMode: "read_only_before_unlock",
      refreshProfile: "battery_saver",
      refreshIntervalMs: 30_000,
    });
  });

  it("fails closed to defaults when persisted settings are malformed", async () => {
    jest.mocked(SecureStore.getItemAsync).mockResolvedValue('{"privacyMode":"open"}');

    await hydrateSettings();

    await waitFor(() =>
      expect(useSettingsStore.getState()).toMatchObject({
        privacyMode: "full_lock",
        motion: "expressive",
        refreshProfile: "balanced",
        lockTimeoutMs: 0,
      }),
    );
  });

  it("does not let late settings hydration overwrite a newer operator choice", async () => {
    let resolveStored!: (value: string | null) => void;
    jest.mocked(SecureStore.getItemAsync).mockReturnValueOnce(
      new Promise<string | null>((resolve) => {
        resolveStored = resolve;
      }),
    );
    const hydration = hydrateSettings();

    useSettingsStore.getState().update({ motion: "minimal" });
    resolveStored(
      JSON.stringify({
        hapticsEnabled: false,
        lockTimeoutMs: 300_000,
        motion: "expressive",
        notificationPreviewsEnabled: true,
        privacyMode: "read_only_before_unlock",
        refreshProfile: "battery_saver",
      }),
    );
    await hydration;

    expect(useSettingsStore.getState().motion).toBe("minimal");
    expect(useSettingsStore.getState().privacyMode).toBe("full_lock");
  });

  it("exposes exactly Portfolio, Trades, Wallet, Alerts, and More as final tabs", () => {
    expect(FINAL_TABS).toEqual([
      ["index", "Portfolio"],
      ["trades", "Trades"],
      ["wallet", "Wallet"],
      ["alerts", "Alerts"],
      ["more", "More"],
    ]);
  });

  it("preserves legacy feed, risk, and device deep links through replacements", async () => {
    const feed = await render(<FeedRedirect />);
    expect(feed.getByText("redirect:/(tabs)/alerts")).toBeTruthy();
    await cleanup();
    const risk = await render(<RiskRedirect />);
    expect(risk.getByText("redirect:/(tabs)/more?section=system")).toBeTruthy();
    await cleanup();
    const deviceRoute = await render(<DeviceRedirect />);
    expect(deviceRoute.getByText("redirect:/(tabs)/more?section=device")).toBeTruthy();
  });

  it("offers system, device, settings, pairing, and diagnostics from More", async () => {
    const screen = await render(<MoreScreen />);
    expect(screen.getByText("System")).toBeTruthy();
    expect(screen.getByText("Device")).toBeTruthy();
    expect(screen.getByText("Settings")).toBeTruthy();
    expect(screen.getByText("Pair Device")).toBeTruthy();
    expect(screen.getByText("Diagnostics")).toBeTruthy();
  });

  it("updates every persisted setting from the Settings screen", async () => {
    const screen = await render(<SettingsScreen />);

    await fireEvent.press(screen.getByText("Read-only before unlock"));
    await fireEvent.press(screen.getByText("Minimal"));
    await fireEvent.press(screen.getByText("Battery saver"));
    await fireEvent.press(screen.getByText("5 minutes"));
    await fireEvent.press(screen.getByText("Haptics on"));
    await fireEvent.press(screen.getByText("Previews off"));
    await flushSettingsPersistence();

    expect(useSettingsStore.getState()).toMatchObject({
      hapticsEnabled: false,
      lockTimeoutMs: 300_000,
      motion: "minimal",
      notificationPreviewsEnabled: true,
      privacyMode: "read_only_before_unlock",
      refreshProfile: "battery_saver",
    });
  });
});
