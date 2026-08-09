import React, { useEffect, useRef } from "react";
import {
  Animated,
  Easing,
  StyleSheet,
  View,
  type DimensionValue,
} from "react-native";

import type { MotionMode } from "../../core/settings/settingsStore";
import { colors, radius } from "../../theme";
import { resolveMotionPolicy, useMotionPolicy } from "../motion/policy";

export function Skeleton({
  width = "100%",
  height,
  motionMode,
  reduceMotion = false,
}: {
  width?: DimensionValue;
  height: DimensionValue;
  motionMode?: MotionMode;
  reduceMotion?: boolean;
}) {
  const activePolicy = useMotionPolicy();
  const policy = motionMode
    ? resolveMotionPolicy(motionMode, reduceMotion, activePolicy.haptics)
    : activePolicy;
  const opacity = useRef(new Animated.Value(0.35)).current;
  const shouldAnimate = policy.shimmer !== "static";

  useEffect(() => {
    if (!shouldAnimate) {
      opacity.stopAnimation();
      opacity.setValue(0.5);
      return;
    }
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: policy.shimmer === "full" ? 0.9 : 0.65,
          duration: policy.duration.slow,
          easing: Easing.inOut(Easing.cubic),
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 0.35,
          duration: policy.duration.slow,
          easing: Easing.inOut(Easing.cubic),
          useNativeDriver: true,
        }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [opacity, policy.duration.slow, policy.shimmer, shouldAnimate]);

  return (
    <View style={[styles.track, { width, height }]}>
      <Animated.View
        accessibilityValue={{
          text: shouldAnimate
            ? "Animated loading placeholder"
            : "Static loading placeholder",
        }}
        testID="skeleton-shimmer"
        style={[StyleSheet.absoluteFill, styles.shimmer, { opacity }]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    overflow: "hidden",
    borderRadius: radius.md,
    backgroundColor: colors.panelRaised,
  },
  shimmer: { backgroundColor: colors.borderStrong },
});
