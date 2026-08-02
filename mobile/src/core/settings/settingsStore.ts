import * as SecureStore from "expo-secure-store";
import { create } from "zustand";

export type PrivacyMode = "full_lock" | "read_only_before_unlock";
export type MotionMode = "expressive" | "balanced" | "minimal" | "system";
export type MotionPreference = MotionMode;
export type RefreshProfile = "performance" | "balanced" | "battery_saver";

export const SETTINGS_STORAGE_KEY = "cryptoarc.mobile.settings.v1";

export interface MobileSettings {
  hapticsEnabled: boolean;
  lockTimeoutMs: number;
  motion: MotionMode;
  notificationPreviewsEnabled: boolean;
  privacyMode: PrivacyMode;
  refreshProfile: RefreshProfile;
  refreshIntervalMs: number;
}

interface MobileSettingsState extends MobileSettings {
  reset(): void;
  update(values: Partial<MobileSettings>): void;
}

const refreshIntervals: Record<RefreshProfile, number> = {
  performance: 5_000,
  balanced: 12_000,
  battery_saver: 30_000,
};

export const defaultSettings: MobileSettings = {
  hapticsEnabled: true,
  lockTimeoutMs: 0,
  motion: "expressive",
  notificationPreviewsEnabled: false,
  privacyMode: "full_lock",
  refreshProfile: "balanced",
  refreshIntervalMs: refreshIntervals.balanced,
};

let persistenceQueue: Promise<void> = Promise.resolve();
let settingsRevision = 0;

function durableSettings(settings: MobileSettings): Omit<MobileSettings, "refreshIntervalMs"> {
  const { refreshIntervalMs: _derived, ...durable } = settings;
  return durable;
}

function persist(settings: MobileSettings): void {
  const serialized = JSON.stringify(durableSettings(settings));
  persistenceQueue = persistenceQueue
    .catch(() => undefined)
    .then(() => SecureStore.setItemAsync(SETTINGS_STORAGE_KEY, serialized))
    .catch(() => undefined);
}

function normalize(values: Partial<MobileSettings>, current: MobileSettings): MobileSettings {
  const refreshProfile = values.refreshProfile ?? current.refreshProfile;
  return {
    hapticsEnabled: values.hapticsEnabled ?? current.hapticsEnabled,
    lockTimeoutMs: Math.max(0, values.lockTimeoutMs ?? current.lockTimeoutMs),
    motion: values.motion ?? current.motion,
    notificationPreviewsEnabled:
      values.notificationPreviewsEnabled ?? current.notificationPreviewsEnabled,
    privacyMode: values.privacyMode ?? current.privacyMode,
    refreshProfile,
    refreshIntervalMs: refreshIntervals[refreshProfile],
  };
}

export const useSettingsStore = create<MobileSettingsState>((set) => ({
  ...defaultSettings,
  reset: () => {
    settingsRevision += 1;
    set(defaultSettings);
    persist(defaultSettings);
  },
  update: (values) =>
    set((current) => {
      settingsRevision += 1;
      const next = normalize(values, current);
      persist(next);
      return next;
    }),
}));

function validPersistedSettings(value: unknown): value is Omit<MobileSettings, "refreshIntervalMs"> {
  if (!value || typeof value !== "object") return false;
  const settings = value as Partial<MobileSettings>;
  return (
    typeof settings.hapticsEnabled === "boolean" &&
    typeof settings.notificationPreviewsEnabled === "boolean" &&
    typeof settings.lockTimeoutMs === "number" &&
    Number.isFinite(settings.lockTimeoutMs) &&
    settings.lockTimeoutMs >= 0 &&
    ["expressive", "balanced", "minimal", "system"].includes(settings.motion ?? "") &&
    ["full_lock", "read_only_before_unlock"].includes(settings.privacyMode ?? "") &&
    ["performance", "balanced", "battery_saver"].includes(settings.refreshProfile ?? "")
  );
}

export async function hydrateSettings(): Promise<void> {
  const hydrationRevision = settingsRevision;
  try {
    const raw = await SecureStore.getItemAsync(SETTINGS_STORAGE_KEY);
    if (settingsRevision !== hydrationRevision) return;
    if (raw === null) return;
    const parsed: unknown = JSON.parse(raw);
    if (!validPersistedSettings(parsed)) throw new Error("Invalid mobile settings");
    const next = normalize(parsed, defaultSettings);
    useSettingsStore.setState(next);
  } catch {
    if (settingsRevision !== hydrationRevision) return;
    useSettingsStore.setState(defaultSettings);
  }
}

export function resetSettings(options: { persist?: boolean } = {}): void {
  settingsRevision += 1;
  useSettingsStore.setState(defaultSettings);
  if (options.persist !== false) persist(defaultSettings);
}

export async function setPrivacyMode(privacyMode: PrivacyMode): Promise<void> {
  useSettingsStore.getState().update({ privacyMode });
  await flushSettingsPersistence();
}

export async function flushSettingsPersistence(): Promise<void> {
  await persistenceQueue;
}
