import { WifiOff } from "lucide-react-native";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { useConnection } from "../../core/connectivity/ConnectionProvider";
import { colors, spacing } from "../../theme";

export function ConnectionBanner() {
  const connection = useConnection();
  if (connection.online) return null;
  return (
    <View accessibilityRole="alert" style={styles.banner}>
      <WifiOff color={colors.amber} size={16} />
      <Text style={styles.text}>Offline · showing saved data · controls unavailable</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    minHeight: 42,
    borderBottomColor: colors.borderStrong,
    borderBottomWidth: 1,
    backgroundColor: colors.panel,
    paddingHorizontal: spacing.md,
  },
  text: { color: colors.amber, flex: 1, fontSize: 11, fontWeight: "800" },
});
