import React, { useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "../../theme";

export interface HoldToConfirmProps {
  label: string;
  durationMs: number;
  disabled: boolean;
  onConfirm(): Promise<void> | void;
  accessibilityHint: string;
}

export function HoldToConfirm({
  label,
  durationMs,
  disabled,
  onConfirm,
  accessibilityHint,
}: HoldToConfirmProps) {
  const confirmed = useRef(false);
  const [holding, setHolding] = useState(false);

  const reset = () => {
    setHolding(false);
    confirmed.current = false;
  };

  return (
    <Pressable
      accessibilityHint={accessibilityHint}
      accessibilityLabel={label}
      accessibilityRole="button"
      delayLongPress={durationMs}
      disabled={disabled}
      onLongPress={() => {
        if (disabled || confirmed.current) return;
        confirmed.current = true;
        setHolding(false);
        void onConfirm();
      }}
      onPressIn={() => {
        if (!disabled) setHolding(true);
      }}
      onPressOut={reset}
      testID={`hold-to-confirm-${durationMs}`}
      style={[
        styles.control,
        holding && styles.holding,
        disabled && styles.disabled,
      ]}>
      <View style={styles.indicator} />
      <Text style={styles.label}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  control: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "center",
    minHeight: 52,
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
    backgroundColor: colors.roseSoft,
    borderColor: colors.rose,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  holding: {
    backgroundColor: colors.amberSoft,
    borderColor: colors.amber,
  },
  disabled: {
    opacity: 0.45,
  },
  indicator: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.rose,
  },
  label: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "900",
  },
});
