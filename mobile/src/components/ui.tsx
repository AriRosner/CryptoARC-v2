import React, { useEffect, useMemo, useRef } from "react";
import {
  ActivityIndicator,
  Animated,
  Easing,
  Pressable,
  StyleSheet,
  Text,
  View,
  type PressableProps,
  type ViewStyle,
} from "react-native";

import { colors, radius, shadow, spacing } from "../theme";

export type Tone = "success" | "danger" | "warning" | "info" | "neutral";

function toneColor(tone: Tone) {
  return {
    success: { backgroundColor: colors.emeraldSoft, borderColor: colors.emerald, color: colors.emerald },
    danger: { backgroundColor: colors.roseSoft, borderColor: colors.rose, color: colors.rose },
    warning: { backgroundColor: colors.amberSoft, borderColor: colors.amber, color: colors.amber },
    info: { backgroundColor: colors.blueSoft, borderColor: colors.blue, color: colors.blue },
    neutral: { backgroundColor: colors.panelRaised, borderColor: colors.borderStrong, color: colors.muted },
  }[tone];
}

export function Screen({ children }: { children: React.ReactNode }) {
  return <View style={styles.screen}>{children}</View>;
}

export function AnimatedPanel({
  children,
  delay = 0,
  style,
}: {
  children: React.ReactNode;
  delay?: number;
  style?: ViewStyle;
}) {
  const progress = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(progress, {
      toValue: 1,
      duration: 240,
      delay,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [delay, progress]);

  const animatedStyle = {
    opacity: progress,
    transform: [
      {
        translateY: progress.interpolate({ inputRange: [0, 1], outputRange: [12, 0] }),
      },
    ],
  };

  return <Animated.View style={[animatedStyle, style]}>{children}</Animated.View>;
}

export function PageHeader({
  eyebrow,
  title,
  right,
  subtitle,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
}) {
  return (
    <AnimatedPanel>
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>{eyebrow}</Text>
          <Text style={styles.title}>{title}</Text>
          {subtitle ? <Text style={styles.headerSubtitle}>{subtitle}</Text> : null}
        </View>
        {right}
      </View>
    </AnimatedPanel>
  );
}

export function Section({ title, children, right, delay = 0 }: { title: string; children: React.ReactNode; right?: React.ReactNode; delay?: number }) {
  return (
    <AnimatedPanel delay={delay}>
      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>{title}</Text>
          {right}
        </View>
        {children}
      </View>
    </AnimatedPanel>
  );
}

export function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: Tone }) {
  const toneStyles = toneColor(tone);
  return (
    <View style={[styles.badge, { backgroundColor: toneStyles.backgroundColor, borderColor: toneStyles.borderColor }]}>
      <Text style={[styles.badgeText, { color: toneStyles.color }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

export function LiveIndicator({ connected, label }: { connected: boolean; label: string }) {
  const scale = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (!connected) {
      scale.stopAnimation();
      scale.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(scale, { toValue: 1, duration: 900, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
        Animated.timing(scale, { toValue: 0, duration: 900, easing: Easing.in(Easing.cubic), useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [connected, scale]);

  return (
    <View style={styles.livePill}>
      <View style={[styles.liveDot, { backgroundColor: connected ? colors.emerald : colors.amber }]}>
        {connected ? (
          <Animated.View
            style={[
              styles.liveRing,
              {
                opacity: scale.interpolate({ inputRange: [0, 1], outputRange: [0.55, 0] }),
                transform: [{ scale: scale.interpolate({ inputRange: [0, 1], outputRange: [1, 2.3] }) }],
              },
            ]}
          />
        ) : null}
      </View>
      <Text style={styles.liveText}>{label}</Text>
    </View>
  );
}

export function ProgressBar({ value, tone = "neutral" }: { value: number; tone?: Tone }) {
  const clamped = Math.max(0, Math.min(100, value));
  const toneStyles = toneColor(tone);
  return (
    <View style={styles.progressTrack}>
      <View style={[styles.progressFill, { width: `${clamped}%`, backgroundColor: toneStyles.color }]} />
    </View>
  );
}

export function MetricTile({
  label,
  value,
  tone = "neutral",
  detail,
}: {
  label: string;
  value: string | number;
  tone?: "success" | "danger" | "warning" | "neutral";
  detail?: string;
}) {
  const valueColor = tone === "success" ? colors.emerald : tone === "danger" ? colors.rose : tone === "warning" ? colors.amber : colors.text;
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color: valueColor }]} numberOfLines={1}>
        {value}
      </Text>
      {detail ? <Text style={styles.metricDetail} numberOfLines={1}>{detail}</Text> : null}
    </View>
  );
}

export function DetailRow({ label, value, tone = "neutral" }: { label: string; value: string | number; tone?: Tone }) {
  const toneStyles = toneColor(tone);
  return (
    <View style={styles.detailRow}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={[styles.detailValue, { color: tone === "neutral" ? colors.text : toneStyles.color }]} numberOfLines={2}>
        {value}
      </Text>
    </View>
  );
}

export function SegmentedControl({
  options,
  value,
  onChange,
}: {
  options: Array<{ label: string; value: string; tone?: Tone }>;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <View style={styles.segmented}>
      {options.map((option) => {
        const selected = option.value === value;
        const tone = toneColor(option.tone ?? "warning");
        return (
          <Pressable
            key={option.value}
            onPress={() => onChange(option.value)}
            style={({ pressed }) => [
              styles.segment,
              selected && { backgroundColor: tone.backgroundColor, borderColor: tone.borderColor },
              pressed && styles.buttonPressed,
            ]}>
            <Text style={[styles.segmentText, selected && { color: tone.color }]}>{option.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function ActionButton({
  label,
  tone = "secondary",
  loading,
  icon,
  buttonStyle,
  ...props
}: PressableProps & {
  label: string;
  tone?: "primary" | "secondary" | "danger";
  loading?: boolean;
  icon?: React.ReactNode;
  buttonStyle?: ViewStyle;
}) {
  const toneStyle = tone === "primary" ? styles.primaryButton : tone === "danger" ? styles.dangerButton : styles.secondaryButton;
  const scale = useRef(new Animated.Value(1)).current;
  const animatedStyle = useMemo(() => ({ transform: [{ scale }] }), [scale]);
  return (
    <Pressable
      {...props}
      onPressIn={(event) => {
        Animated.timing(scale, { toValue: 0.98, duration: 80, useNativeDriver: true }).start();
        props.onPressIn?.(event);
      }}
      onPressOut={(event) => {
        Animated.timing(scale, { toValue: 1, duration: 120, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
        props.onPressOut?.(event);
      }}>
      {({ pressed }) => (
        <Animated.View style={[styles.button, toneStyle, props.disabled && styles.buttonDisabled, pressed && !props.disabled && styles.buttonPressed, animatedStyle, buttonStyle]}>
          {loading ? <ActivityIndicator color={colors.text} size="small" /> : icon}
          <Text style={styles.buttonText}>{label}</Text>
        </Animated.View>
      )}
    </Pressable>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <AnimatedPanel>
      <View style={styles.empty}>
        <Text style={styles.emptyTitle}>{title}</Text>
        <Text style={styles.emptyBody}>{body}</Text>
      </View>
    </AnimatedPanel>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  if (!message) return null;
  return (
    <AnimatedPanel>
      <View style={styles.error}>
        <Text style={styles.errorText}>{message}</Text>
      </View>
    </AnimatedPanel>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    alignItems: "flex-end",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md,
  },
  headerCopy: {
    flex: 1,
    gap: 4,
  },
  eyebrow: {
    color: colors.amber,
    fontSize: 11,
    fontWeight: "900",
    textTransform: "uppercase",
  },
  title: {
    color: colors.text,
    fontSize: 32,
    fontWeight: "900",
    letterSpacing: 0,
  },
  headerSubtitle: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
  section: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.panel,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.md,
    ...shadow.panel,
  },
  sectionHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "800",
    letterSpacing: 0,
    textTransform: "uppercase",
  },
  badge: {
    borderRadius: radius.sm,
    borderWidth: 1,
    maxWidth: 160,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  badgeText: {
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 0,
    textTransform: "uppercase",
  },
  livePill: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    backgroundColor: colors.panelRaised,
    borderRadius: radius.md,
    paddingHorizontal: spacing.sm,
    paddingVertical: 8,
  },
  liveDot: {
    position: "relative",
    height: 9,
    width: 9,
    borderRadius: 999,
  },
  liveRing: {
    position: "absolute",
    left: -1,
    top: -1,
    height: 11,
    width: 11,
    borderRadius: 999,
    backgroundColor: colors.emerald,
  },
  liveText: {
    color: colors.text,
    fontSize: 11,
    fontWeight: "900",
  },
  progressTrack: {
    overflow: "hidden",
    height: 8,
    borderRadius: 999,
    backgroundColor: colors.deep,
  },
  progressFill: {
    height: "100%",
    borderRadius: 999,
  },
  metric: {
    flex: 1,
    minWidth: 104,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: colors.panelRaised,
    padding: spacing.sm,
    gap: 6,
  },
  metricLabel: {
    color: colors.faint,
    fontSize: 10,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  metricValue: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "900",
  },
  metricDetail: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: "700",
  },
  detailRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    paddingVertical: 9,
  },
  detailLabel: {
    color: colors.faint,
    fontSize: 11,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  detailValue: {
    flex: 1,
    textAlign: "right",
    color: colors.text,
    fontSize: 12,
    fontWeight: "800",
    lineHeight: 17,
  },
  segmented: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: colors.deep,
    padding: 4,
  },
  segment: {
    minHeight: 36,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "transparent",
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
  },
  segmentText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "900",
    textTransform: "uppercase",
  },
  button: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: spacing.xs,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
  },
  primaryButton: {
    backgroundColor: colors.amber,
  },
  secondaryButton: {
    borderWidth: 1,
    borderColor: colors.borderStrong,
    backgroundColor: colors.panelRaised,
  },
  dangerButton: {
    backgroundColor: colors.rose,
  },
  buttonPressed: {
    opacity: 0.86,
  },
  buttonDisabled: {
    opacity: 0.44,
  },
  buttonText: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "900",
  },
  empty: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: colors.panel,
    padding: spacing.lg,
    gap: spacing.xs,
  },
  emptyTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "900",
  },
  emptyBody: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
  error: {
    borderWidth: 1,
    borderColor: colors.rose,
    borderRadius: radius.md,
    backgroundColor: colors.roseSoft,
    padding: spacing.md,
  },
  errorText: {
    color: colors.rose,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 18,
  },
});
