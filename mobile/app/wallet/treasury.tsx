import { useNetInfo } from "@react-native-community/netinfo";
import { router, useLocalSearchParams } from "expo-router";
import { ArrowLeft } from "lucide-react-native";
import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ActionButton,
  EmptyState,
  PageHeader,
  Section,
} from "@/src/components/ui";
import { authenticatedRead } from "@/src/core/api/authenticatedRead";
import { useOptionalSession } from "@/src/core/session/SessionProvider";
import type { PendingMobileAction } from "@/src/features/trades/pendingAction";
import {
  pendingActionRoute,
  TEST_PENDING_ACTION_OWNER,
} from "@/src/features/trades/pendingAction";
import {
  executeTreasuryAction,
  fetchTreasuryAction,
  previewTreasuryAction,
} from "@/src/features/wallet/api";
import { ProfitSweepSheet } from "@/src/features/wallet/ProfitSweepSheet";
import { RentRecoverySheet } from "@/src/features/wallet/RentRecoverySheet";
import type {
  MobileTreasuryPreview,
  TreasuryAction,
  TreasuryExecuteInput,
} from "@/src/features/wallet/types";
import { TreasuryPendingRecovery } from "@/src/features/wallet/WithdrawalScreen";
import { colors, radius, spacing } from "@/src/theme";

function parameter(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function treasuryAction(value: string): TreasuryAction | null {
  return value === "profit_sweep" || value === "rent_recovery"
    ? value
    : null;
}

export default function TreasuryRoute() {
  const params = useLocalSearchParams<{
    action?: string;
    authorizationId?: string;
    address?: string;
    asset?: string;
    amount?: string;
    tokenAccounts?: string;
  }>();
  const action = treasuryAction(parameter(params.action));
  const authorizationId = parameter(params.authorizationId);
  const address = parameter(params.address);
  const asset = parameter(params.asset) || "SOL";
  const amount = parameter(params.amount);
  const tokenAccounts = parameter(params.tokenAccounts)
    .split(",")
    .map((account) => account.trim())
    .filter(Boolean);
  const session = useOptionalSession();
  const netInfo = useNetInfo();
  const [preview, setPreview] = useState<MobileTreasuryPreview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const connection = session
    ? { apiBaseUrl: session.apiBaseUrl, token: session.token }
    : {};
  const pendingOwner = session
    ? {
        apiBaseUrl: session.apiBaseUrl,
        deviceId: session.device?.id || "unpaired-device",
        sessionId:
          session.record?.savedAt || `session-${session.generation}`,
      }
    : TEST_PENDING_ACTION_OWNER;
  const online = Boolean(
    netInfo.isConnected && netInfo.isInternetReachable !== false,
  );
  const title =
    action === "profit_sweep" ? "Profit sweep" : "Rent recovery";

  const loadPreview = async () => {
    if (
      !action ||
      !online ||
      loading ||
      !authorizationId ||
      !address ||
      !amount
    ) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const next = await authenticatedRead(session, () =>
        previewTreasuryAction(
          action,
          {
            authorizationId,
            address,
            asset,
            amount,
            tokenAccounts,
          },
          connection,
        ),
      );
      setPreview(next);
    } catch (caught) {
      setPreview(null);
      setError(
        caught instanceof Error
          ? caught.message
          : "Treasury preview is unavailable",
      );
    } finally {
      setLoading(false);
    }
  };

  const reconcileAction = (actionId: string) =>
    authenticatedRead(session, () =>
      fetchTreasuryAction(actionId, connection),
    );

  const openPendingAction = (pending: PendingMobileAction) => {
    const path = pendingActionRoute(pending);
    if (path) router.push(path);
  };

  const execute = (input: TreasuryExecuteInput) => {
    if (!action) {
      throw new Error("Unsupported treasury action");
    }
    return authenticatedRead(session, () =>
      executeTreasuryAction(action, input, connection),
    );
  };

  const actionProps = preview
    ? {
        preview,
        online,
        execute,
        reconcileAction,
        pendingOwner,
        onOpenPendingAction: openPendingAction,
      }
    : null;

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Pressable
          accessibilityLabel="Back to wallet"
          accessibilityRole="button"
          onPress={() => router.back()}
          style={styles.back}>
          <ArrowLeft color={colors.text} size={20} />
        </Pressable>
        <PageHeader
          eyebrow="Authorized treasury"
          title={action ? title : "Treasury recovery"}
          subtitle="Desktop policy, source wallet, amount, and destination are revalidated before local signing."
        />
        {!action ? (
          <EmptyState
            title="Unsupported treasury action"
            body="Return to Wallet and open an active treasury authorization."
          />
        ) : !authorizationId || !address ? (
          <Section title="Pending recovery">
            <TreasuryPendingRecovery
              reconcileAction={reconcileAction}
              pendingOwner={pendingOwner}
            />
            <EmptyState
              title="Authorization required"
              body="Open an active desktop-issued authorization from the Wallet tab to start a new treasury action."
            />
          </Section>
        ) : preview && actionProps ? (
          <Section title="Elevated confirmation">
            {action === "profit_sweep" ? (
              <ProfitSweepSheet {...actionProps} />
            ) : (
              <RentRecoverySheet {...actionProps} />
            )}
          </Section>
        ) : (
          <Section title="Policy-bound preview">
            <ActionButton
              label={
                online
                  ? `Create ${title.toLowerCase()} preview`
                  : "Unavailable offline"
              }
              disabled={!online || loading || !amount}
              loading={loading}
              onPress={() => void loadPreview()}
            />
            {error ? <View accessibilityLabel={error} /> : null}
          </Section>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    padding: spacing.lg,
    paddingBottom: spacing.xl,
    gap: spacing.md,
  },
  back: {
    alignItems: "center",
    justifyContent: "center",
    width: 44,
    height: 44,
    backgroundColor: colors.panel,
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
  },
});
