import React from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing } from "../../theme";
import type {
  MobileTradeDraft,
  MobileTradeLimits,
  NumericLimit,
} from "./types";

export interface BoundedTradeFormProps {
  draft: MobileTradeDraft;
  limits: MobileTradeLimits;
  disabled: boolean;
  onChange(draft: MobileTradeDraft): void;
}

function bounded(value: string, limit: NumericLimit): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "";
  return String(Math.max(limit.min, Math.min(limit.max, parsed)));
}

export function BoundedTradeForm({
  draft,
  limits,
  disabled,
  onChange,
}: BoundedTradeFormProps) {
  const field = (
    label: string,
    value: string | null,
    key: keyof MobileTradeDraft,
    limit: NumericLimit,
  ) => (
    <View style={styles.field}>
      <View style={styles.fieldHeader}>
        <Text style={styles.label}>{label}</Text>
        <Text style={styles.limit}>
          {limit.min} to {limit.max}
        </Text>
      </View>
      <TextInput
        accessibilityLabel={label}
        editable={!disabled}
        keyboardType="decimal-pad"
        onChangeText={(next) =>
          onChange({ ...draft, [key]: bounded(next, limit) })
        }
        selectTextOnFocus
        style={styles.input}
        testID={`trade-field-${String(key)}`}
        value={value ?? ""}
      />
    </View>
  );

  return (
    <View style={styles.form}>
      {field("Trade amount", draft.amount, "amount", limits.amount)}
      {field(
        "Slippage percent",
        draft.slippage_pct,
        "slippage_pct",
        limits.slippage_pct,
      )}
      <View style={styles.row}>
        <View style={styles.rowField}>
          {field("Stop percent", draft.stop_pct, "stop_pct", limits.stop_pct)}
        </View>
        <View style={styles.rowField}>
          {field(
            "Target percent",
            draft.target_pct,
            "target_pct",
            limits.target_pct,
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  form: {
    gap: spacing.md,
  },
  row: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  rowField: {
    flex: 1,
  },
  field: {
    gap: 6,
  },
  fieldHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  label: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
  },
  limit: {
    color: colors.faint,
    fontSize: 9,
  },
  input: {
    minHeight: 46,
    paddingHorizontal: spacing.sm,
    color: colors.text,
    backgroundColor: colors.deep,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    borderWidth: 1,
    fontSize: 14,
    fontWeight: "800",
  },
});
