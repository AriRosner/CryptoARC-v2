import { ChevronDown, ChevronRight } from "lucide-react-native";
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, spacing } from "../theme";
import type { OperatorEvent } from "../types";
import { AnimatedPanel, DetailRow, EmptyState, StatusBadge, type Tone } from "./ui";

export function filterFeedEvents(events: OperatorEvent[], level: string, subsystem: string): OperatorEvent[] {
  const cleanLevel = level.trim().toLowerCase();
  const cleanSubsystem = subsystem.trim().toLowerCase();
  return events.filter((event) => {
    if (cleanLevel && event.level.toLowerCase() !== cleanLevel) return false;
    if (cleanSubsystem && String(event.subsystem || "").toLowerCase() !== cleanSubsystem) return false;
    return true;
  });
}

export function summarizeFeed(events: OperatorEvent[]) {
  return events.reduce(
    (summary, event) => {
      const level = event.level.toLowerCase();
      if (level === "danger" || level === "error") summary.danger += 1;
      else if (level === "warning") summary.warning += 1;
      else if (level === "info") summary.info += 1;
      else summary.other += 1;
      return summary;
    },
    { danger: 0, warning: 0, info: 0, other: 0 },
  );
}

function toneForLevel(level: string): Tone {
  if (level === "danger" || level === "error") return "danger";
  if (level === "warning") return "warning";
  if (level === "success") return "success";
  if (level === "info") return "info";
  return "neutral";
}

export function FeedList({ events }: { events: OperatorEvent[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  if (!events.length) {
    return <EmptyState title="No events" body="The selected feed filters have no matching operator events." />;
  }
  return (
    <View style={styles.list}>
      {events.map((event, index) => {
        const expanded = expandedId === event.id;
        const level = event.level.toLowerCase();
        return (
          <AnimatedPanel key={event.id} delay={Math.min(index * 25, 180)}>
            <Pressable onPress={() => setExpandedId(expanded ? null : event.id)} style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}>
              <View style={styles.rowTop}>
                <View style={styles.rowMeta}>
                  <StatusBadge label={event.level} tone={toneForLevel(level)} />
                  <Text style={styles.subsystem}>{event.subsystem || "app"}</Text>
                </View>
                {expanded ? <ChevronDown size={17} color={colors.muted} /> : <ChevronRight size={17} color={colors.faint} />}
              </View>
              <Text style={styles.message}>{event.message}</Text>
              {event.operator_action ? <Text style={styles.action}>{event.operator_action}</Text> : null}
              {expanded ? (
                <View style={styles.detailBlock}>
                  <DetailRow label="Created" value={new Date(event.created_at).toLocaleString()} />
                  <DetailRow label="Subsystem" value={event.subsystem || "app"} />
                  <DetailRow label="Level" value={event.level} tone={toneForLevel(level)} />
                </View>
              ) : (
                <Text style={styles.time}>{new Date(event.created_at).toLocaleTimeString()}</Text>
              )}
            </Pressable>
          </AnimatedPanel>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: spacing.sm,
  },
  row: {
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 8,
    backgroundColor: colors.panel,
    padding: spacing.md,
    gap: spacing.sm,
  },
  rowPressed: {
    backgroundColor: colors.panelRaised,
  },
  rowTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  rowMeta: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  subsystem: {
    color: colors.faint,
    fontSize: 10,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  message: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "800",
    lineHeight: 19,
  },
  action: {
    color: colors.amber,
    fontSize: 12,
    lineHeight: 18,
  },
  time: {
    color: colors.faint,
    fontSize: 10,
    fontWeight: "700",
  },
  detailBlock: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
});
