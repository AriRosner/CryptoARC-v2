import React, { useEffect, useRef, useState } from "react";
import { Animated, Easing, StyleSheet, Text, type TextStyle } from "react-native";

import { colors } from "../../theme";
import { useMotionPolicy } from "./policy";

export function AnimatedNumber({
  value,
  format = (next) => String(next),
  accessibilityLabel,
  style,
}: {
  value: number;
  format?: (value: number) => string;
  accessibilityLabel?: string;
  style?: TextStyle;
}) {
  const policy = useMotionPolicy();
  const animated = useRef(new Animated.Value(value)).current;
  const [displayed, setDisplayed] = useState(value);

  useEffect(() => {
    if (policy.duration.normal === 0) {
      animated.setValue(value);
      setDisplayed(value);
      return;
    }
    const listener = animated.addListener(({ value: next }) => setDisplayed(next));
    const animation = Animated.timing(animated, {
      toValue: value,
      duration: policy.duration.normal,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    });
    animation.start();
    return () => {
      animation.stop();
      animated.removeListener(listener);
    };
  }, [animated, policy.duration.normal, value]);

  return (
    <Text
      accessibilityLabel={accessibilityLabel ?? format(value)}
      style={[styles.value, style]}>
      {format(displayed)}
    </Text>
  );
}

const styles = StyleSheet.create({
  value: { color: colors.text, fontVariant: ["tabular-nums"] },
});
