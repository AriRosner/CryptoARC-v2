import { useEffect, useState } from "react";
import { AccessibilityInfo } from "react-native";

import {
  type MotionMode,
  useSettingsStore,
} from "../../core/settings/settingsStore";

export interface MotionPolicy {
  duration: { fast: number; normal: number; slow: number };
  spring: { damping: number; stiffness: number };
  shimmer: "full" | "restrained" | "static";
  sharedTransitions: boolean;
  haptics: boolean;
}

const expressive: Omit<MotionPolicy, "haptics"> = {
  duration: { fast: 120, normal: 220, slow: 360 },
  spring: { damping: 18, stiffness: 180 },
  shimmer: "full",
  sharedTransitions: true,
};

const balanced: Omit<MotionPolicy, "haptics"> = {
  duration: { fast: 90, normal: 160, slow: 240 },
  spring: { damping: 22, stiffness: 220 },
  shimmer: "restrained",
  sharedTransitions: false,
};

const minimal: Omit<MotionPolicy, "haptics"> = {
  duration: { fast: 0, normal: 0, slow: 0 },
  spring: { damping: 24, stiffness: 260 },
  shimmer: "static",
  sharedTransitions: false,
};

export function resolveMotionPolicy(
  mode: MotionMode,
  systemReducedMotion: boolean,
  hapticsEnabled: boolean,
): MotionPolicy {
  const resolved =
    mode === "minimal" || (mode === "system" && systemReducedMotion)
      ? minimal
      : mode === "balanced" || mode === "system"
        ? balanced
        : expressive;
  return { ...resolved, haptics: hapticsEnabled };
}

export function useMotionPolicy(): MotionPolicy {
  const mode = useSettingsStore((state) => state.motion);
  const hapticsEnabled = useSettingsStore((state) => state.hapticsEnabled);
  const [systemReducedMotion, setSystemReducedMotion] = useState(mode === "system");

  useEffect(() => {
    if (mode !== "system") {
      setSystemReducedMotion(false);
      return;
    }
    let mounted = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((enabled) => {
      if (mounted) setSystemReducedMotion(enabled);
    });
    const subscription = AccessibilityInfo.addEventListener(
      "reduceMotionChanged",
      setSystemReducedMotion,
    );
    return () => {
      mounted = false;
      subscription.remove();
    };
  }, [mode]);

  return resolveMotionPolicy(mode, systemReducedMotion, hapticsEnabled);
}
