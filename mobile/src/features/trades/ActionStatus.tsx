import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { StatusBadge } from "../../components/ui";
import { colors, radius, spacing } from "../../theme";
import type { MobileActionReceipt } from "./types";

const labels = {
  pending: "Pending",
  verifying: "Verifying outcome",
  confirmed: "Confirmed",
  failed: "Failed",
  cancelled: "Cancelled",
  expired: "Expired",
  review_required: "Review required",
} as const;

export function ActionStatus({ receipt }: { receipt: MobileActionReceipt }) {
  const caution = ["pending", "verifying", "review_required"].includes(
    receipt.status,
  );
  return (
    <View
      accessibilityLiveRegion="polite"
      style={[styles.band, caution && styles.caution]}>
      <View style={styles.header}>
        <Text style={styles.title}>{labels[receipt.status]}</Text>
        <StatusBadge
          label={receipt.status.replace("_", " ")}
          tone={
            receipt.status === "confirmed"
              ? "success"
              : receipt.status === "failed"
                ? "danger"
                : "warning"
          }
        />
      </View>
      <Text style={styles.message}>{receipt.operator_message}</Text>
      {receipt.status === "verifying" ? (
        <Text style={styles.note}>No automatic resubmission</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  band: {
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.panelRaised,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  caution: {
    backgroundColor: colors.amberSoft,
    borderColor: colors.amber,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  title: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "900",
  },
  message: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
  note: {
    color: colors.amber,
    fontSize: 10,
    fontWeight: "800",
  },
});
