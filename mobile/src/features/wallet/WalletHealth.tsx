import React from "react";
import { StyleSheet, View } from "react-native";

import { DetailRow, StatusBadge } from "../../components/ui";
import { spacing } from "../../theme";
import type { MobileWalletPayload } from "./types";

export function WalletHealth({
  health,
}: {
  health: MobileWalletPayload["health"];
}) {
  const healthy =
    health.rpc === "healthy" &&
    health.signer === "healthy" &&
    health.backend === "armed" &&
    health.kill_switch === "clear";
  return (
    <View style={styles.stack}>
      <StatusBadge
        label={healthy ? "Execution health clear" : "Execution blocked"}
        tone={healthy ? "success" : "danger"}
      />
      <DetailRow
        label="RPC"
        value={`RPC ${health.rpc}`}
        tone={health.rpc === "healthy" ? "success" : "danger"}
      />
      <DetailRow
        label="Signer"
        value={`Signer ${health.signer}`}
        tone={health.signer === "healthy" ? "success" : "danger"}
      />
      <DetailRow label="Backend" value={health.backend} />
      <DetailRow label="Readiness" value={health.readiness} />
      <DetailRow
        label="Kill switch"
        value={health.kill_switch}
        tone={health.kill_switch === "clear" ? "success" : "danger"}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    gap: spacing.sm,
  },
});
