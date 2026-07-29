import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { StatusBadge } from "../../components/ui";
import { colors, spacing } from "../../theme";
import type { MobileWalletTransaction } from "./types";

function actionLabel(action: MobileWalletTransaction["action"]) {
  return {
    withdrawal: "Withdrawal",
    profit_sweep: "Profit sweep",
    rent_recovery: "Rent recovery",
  }[action];
}

export function TransactionList({
  transactions,
}: {
  transactions: MobileWalletTransaction[];
}) {
  if (!transactions.length) {
    return <Text style={styles.empty}>No treasury transaction history.</Text>;
  }
  return (
    <View style={styles.list}>
      {transactions.map((transaction) => (
        <View key={transaction.id} style={styles.row}>
          <View style={styles.copy}>
            <Text style={styles.action}>{actionLabel(transaction.action)}</Text>
            <Text style={styles.amount}>
              {transaction.amount} {transaction.asset}
            </Text>
            <Text style={styles.destination} numberOfLines={1}>
              {transaction.destination}
            </Text>
          </View>
          <StatusBadge
            label={transaction.status}
            tone={
              transaction.status === "confirmed"
                ? "success"
                : transaction.status === "failed"
                  ? "danger"
                  : "warning"
            }
          />
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: spacing.sm,
  },
  row: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md,
    borderTopColor: colors.border,
    borderTopWidth: 1,
    paddingTop: spacing.sm,
  },
  copy: {
    flex: 1,
    gap: 2,
  },
  action: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "800",
  },
  amount: {
    color: colors.amber,
    fontSize: 12,
    fontWeight: "800",
  },
  destination: {
    color: colors.faint,
    fontSize: 10,
  },
  empty: {
    color: colors.muted,
    fontSize: 12,
  },
});
