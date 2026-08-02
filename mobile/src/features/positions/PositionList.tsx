import { ChevronRight } from "lucide-react-native";
import React, { useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { LinearTransition, ReduceMotion } from "react-native-reanimated";

import { AnimatedPanel, StatusBadge } from "../../components/ui";
import { useMotionPolicy } from "../../components/motion/policy";
import { listTransitionDelay } from "../../components/motion/transitions";
import { colors, radius, spacing } from "../../theme";
import type { PositionSummary } from "./types";

export function PositionList({
  positions,
  onPress,
}: {
  positions: PositionSummary[];
  onPress(positionId: string): void;
}) {
  const motionPolicy = useMotionPolicy();
  const layoutTransition = useMemo(
    () =>
      motionPolicy.sharedTransitions
        ? LinearTransition.springify()
            .damping(motionPolicy.spring.damping)
            .stiffness(motionPolicy.spring.stiffness)
            .reduceMotion(ReduceMotion.Never)
        : undefined,
    [
      motionPolicy.sharedTransitions,
      motionPolicy.spring.damping,
      motionPolicy.spring.stiffness,
    ],
  );
  if (!positions.length) {
    return <Text style={styles.empty}>No open paper or live positions are tracked.</Text>;
  }
  return (
    <View style={styles.list}>
      {positions.map((position, index) => {
        const pnl = position.realized_pnl_sol + position.unrealized_pnl_sol;
        return (
          <Animated.View
            key={position.id}
            testID={`position-transition-${position.id}`}
            layout={layoutTransition}>
            <AnimatedPanel delay={listTransitionDelay(motionPolicy, index)}>
              <Pressable
                accessibilityLabel={`Open ${position.symbol} position, ${position.mode}, ${position.mark_fresh ? "fresh" : "stale"} mark`}
                accessibilityRole="button"
                onPress={() => onPress(position.id)}
                style={({ pressed }) => [styles.row, pressed && styles.pressed]}>
                <View style={styles.identity}>
                  <View style={styles.symbolLine}>
                    <Text style={styles.symbol}>{position.symbol}</Text>
                    <StatusBadge label={position.mode} tone={position.mode === "live" ? "warning" : "neutral"} />
                  </View>
                  <Text style={styles.meta}>
                    {position.mark_fresh ? "Fresh mark" : "Stale mark"} | {position.mark_source || "No mark source"}
                  </Text>
                </View>
                <View style={styles.pnl}>
                  <Text style={[styles.pnlValue, { color: pnl >= 0 ? colors.emerald : colors.rose }]}>
                    {pnl >= 0 ? "+" : ""}{pnl.toFixed(4)}
                  </Text>
                  <Text style={styles.pnlPct}>{position.pnl_pct.toFixed(1)}%</Text>
                </View>
                <ChevronRight size={18} color={colors.faint} />
              </Pressable>
            </AnimatedPanel>
          </Animated.View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: spacing.xs,
  },
  row: {
    minHeight: 64,
    alignItems: "center",
    flexDirection: "row",
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
    backgroundColor: colors.panelRaised,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  pressed: {
    backgroundColor: colors.panelLifted,
  },
  identity: {
    flex: 1,
    gap: 6,
  },
  symbolLine: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  symbol: {
    color: colors.text,
    flexShrink: 1,
    fontSize: 14,
    fontWeight: "900",
  },
  meta: {
    color: colors.faint,
    fontSize: 10,
  },
  pnl: {
    alignItems: "flex-end",
  },
  pnlValue: {
    fontSize: 12,
    fontWeight: "900",
  },
  pnlPct: {
    color: colors.muted,
    fontSize: 10,
    marginTop: 3,
  },
  empty: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
});
