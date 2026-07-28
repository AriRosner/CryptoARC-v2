import { create } from "zustand";

export type MotionPreference = "expressive" | "balanced" | "minimal" | "system";

interface MobileSettings {
  hapticsEnabled: boolean;
  motion: MotionPreference;
  notificationPreviewsEnabled: boolean;
  readOnlyBeforeUnlock: boolean;
  refreshIntervalMs: number;
}

interface MobileSettingsState extends MobileSettings {
  reset(): void;
  update(values: Partial<MobileSettings>): void;
}

const defaultSettings: MobileSettings = {
  hapticsEnabled: true,
  motion: "expressive",
  notificationPreviewsEnabled: false,
  readOnlyBeforeUnlock: false,
  refreshIntervalMs: 12000,
};

export const useSettingsStore = create<MobileSettingsState>((set) => ({
  ...defaultSettings,
  reset: () => set(defaultSettings),
  update: (values) =>
    set((current) => ({
      ...values,
      refreshIntervalMs: Math.min(60000, Math.max(5000, values.refreshIntervalMs ?? current.refreshIntervalMs)),
    })),
}));
