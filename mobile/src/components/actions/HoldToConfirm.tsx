import React, { useEffect, useRef, useState } from "react";
import { AppState, Pressable, StyleSheet, Text, View } from "react-native";

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
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [holding, setHolding] = useState(false);
  const [accessibilityArmedAt, setAccessibilityArmedAt] = useState<
    number | null
  >(null);

  const cancelPhysicalHold = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setHolding(false);
  };

  const begin = () => {
    if (disabled || confirmed.current || timer.current) return;
    setAccessibilityArmedAt(null);
    setHolding(true);
    timer.current = setTimeout(() => {
      timer.current = null;
      confirmed.current = true;
      setHolding(false);
      void onConfirm();
    }, durationMs);
  };

  const resetAll = () => {
    cancelPhysicalHold();
    confirmed.current = false;
    setAccessibilityArmedAt(null);
  };

  const activateAccessibilityConfirmation = () => {
    if (disabled || confirmed.current) return;
    const now = Date.now();
    if (
      accessibilityArmedAt === null ||
      now - accessibilityArmedAt > 30000
    ) {
      setAccessibilityArmedAt(now);
      return;
    }
    if (now - accessibilityArmedAt < durationMs) return;
    confirmed.current = true;
    setAccessibilityArmedAt(null);
    void onConfirm();
  };

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state !== "active") resetAll();
    });
    return () => {
      subscription.remove();
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  useEffect(() => {
    if (disabled) resetAll();
  }, [disabled]);

  return (
    <View style={styles.stack}>
      <Pressable
        accessibilityActions={[
          {
            name: "activate",
            label:
              accessibilityArmedAt === null
                ? `Arm ${label}`
                : `Confirm ${label}`,
          },
          ...(accessibilityArmedAt === null
            ? []
            : [{ name: "escape", label: "Cancel confirmation" }]),
        ]}
        accessibilityHint={
          accessibilityArmedAt === null
            ? `${accessibilityHint}. Accessibility activation arms a separate confirmation and cannot submit by itself.`
            : "Activate again after the safety delay to confirm, or use escape to cancel."
        }
        accessibilityLabel={label}
        accessibilityRole="button"
        disabled={disabled}
        onAccessibilityAction={(event) => {
          if (event.nativeEvent.actionName === "activate") {
            activateAccessibilityConfirmation();
          } else if (event.nativeEvent.actionName === "escape") {
            resetAll();
          }
        }}
        onPressIn={begin}
        onPressOut={cancelPhysicalHold}
        testID={`hold-to-confirm-${durationMs}`}
        style={[
          styles.control,
          holding && styles.holding,
          disabled && styles.disabled,
        ]}>
        <View style={styles.indicator} />
        <Text style={styles.label}>{label}</Text>
      </Pressable>
      {accessibilityArmedAt !== null ? (
        <Text accessibilityLiveRegion="polite" style={styles.safetyNote}>
          Accessibility confirmation armed. Activate again after the safety
          delay.
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    gap: spacing.sm,
  },
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
  safetyNote: {
    color: colors.amber,
    fontSize: 11,
    lineHeight: 17,
  },
});
