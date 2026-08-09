import { ShieldAlert } from "lucide-react-native";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "../../theme";

export function RiskEscalation({ reasons }: { reasons: string[] }) {
  if (!reasons.length) return null;
  return (
    <View style={styles.band}>
      <ShieldAlert color={colors.amber} size={20} />
      <View style={styles.copy}>
        <Text style={styles.title}>Elevated risk</Text>
        {reasons.map((reason) => (
          <Text key={reason} style={styles.reason}>
            {reason}
          </Text>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  band: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.amberSoft,
    borderColor: colors.amber,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  copy: {
    flex: 1,
    gap: 4,
  },
  title: {
    color: colors.amber,
    fontSize: 12,
    fontWeight: "900",
  },
  reason: {
    color: colors.text,
    fontSize: 11,
    lineHeight: 16,
  },
});
