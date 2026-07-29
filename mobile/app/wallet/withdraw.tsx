import { useNetInfo } from "@react-native-community/netinfo";
import { router, useLocalSearchParams } from "expo-router";
import { ArrowLeft } from "lucide-react-native";
import React, { useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ActionButton,
  EmptyState,
  PageHeader,
  Section,
} from "@/src/components/ui";
import { authenticatedRead } from "@/src/core/api/authenticatedRead";
import { useOptionalSession } from "@/src/core/session/SessionProvider";
import {
  executeTreasuryAction,
  fetchTreasuryAction,
  previewTreasuryAction,
} from "@/src/features/wallet/api";
import type { MobileTreasuryPreview } from "@/src/features/wallet/types";
import {
  TreasuryPendingRecovery,
  WithdrawalScreen,
} from "@/src/features/wallet/WithdrawalScreen";
import { TEST_PENDING_ACTION_OWNER } from "@/src/features/trades/pendingAction";
import { colors, radius, spacing } from "@/src/theme";

function parameter(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default function WithdrawalRoute() {
  const params = useLocalSearchParams<{
    authorizationId?: string;
    address?: string;
    asset?: string;
    maxAmount?: string;
  }>();
  const authorizationId = parameter(params.authorizationId);
  const address = parameter(params.address);
  const asset = parameter(params.asset) || "SOL";
  const maxAmount = parameter(params.maxAmount);
  const session = useOptionalSession();
  const netInfo = useNetInfo();
  const [amount, setAmount] = useState(maxAmount);
  const [preview, setPreview] = useState<MobileTreasuryPreview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const connection = session
    ? { apiBaseUrl: session.apiBaseUrl, token: session.token }
    : {};
  const online = Boolean(
    netInfo.isConnected && netInfo.isInternetReachable !== false,
  );

  const loadPreview = async () => {
    if (!online || loading || !authorizationId || !address || !amount) return;
    setLoading(true);
    setError("");
    try {
      const next = await authenticatedRead(session, () =>
        previewTreasuryAction(
          "withdrawal",
          {
            authorizationId,
            address,
            asset,
            amount,
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
          : "Withdrawal preview is unavailable",
      );
    } finally {
      setLoading(false);
    }
  };

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
          title="Withdrawal"
          subtitle="Destination and asset are fixed by the desktop-issued authorization."
        />
        {!authorizationId || !address ? (
          <Section title="Pending recovery">
            <TreasuryPendingRecovery
              reconcileAction={(actionId) =>
                authenticatedRead(session, () =>
                  fetchTreasuryAction(actionId, connection),
                )
              }
              pendingOwner={
                session
                  ? {
                      apiBaseUrl: session.apiBaseUrl,
                      deviceId:
                        session.device?.id || "unpaired-device",
                      sessionId:
                        session.record?.savedAt ||
                        `session-${session.generation}`,
                    }
                  : TEST_PENDING_ACTION_OWNER
              }
            />
            <EmptyState
              title="Authorization required"
              body="Open an active desktop-issued destination authorization from the Wallet tab to start a new withdrawal."
            />
          </Section>
        ) : preview ? (
          <Section title="Elevated confirmation">
            <WithdrawalScreen
              preview={preview}
              online={online}
              execute={(input) =>
                authenticatedRead(session, () =>
                  executeTreasuryAction("withdrawal", input, connection),
                )
              }
              reconcileAction={(actionId) =>
                authenticatedRead(session, () =>
                  fetchTreasuryAction(actionId, connection),
                )
              }
              pendingOwner={
                session
                  ? {
                      apiBaseUrl: session.apiBaseUrl,
                      deviceId:
                        session.device?.id || "unpaired-device",
                      sessionId:
                        session.record?.savedAt ||
                        `session-${session.generation}`,
                    }
                  : TEST_PENDING_ACTION_OWNER
              }
            />
          </Section>
        ) : (
          <Section title="Bound amount">
            <TextInput
              accessibilityLabel="Withdrawal amount"
              editable={online && !loading}
              keyboardType="decimal-pad"
              value={amount}
              onChangeText={setAmount}
              placeholder={maxAmount || "0.0"}
              placeholderTextColor={colors.faint}
              style={styles.input}
            />
            <ActionButton
              label={online ? "Create exact preview" : "Unavailable offline"}
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
  input: {
    minHeight: 48,
    color: colors.text,
    backgroundColor: colors.panelRaised,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    borderWidth: 1,
    fontSize: 16,
    paddingHorizontal: spacing.md,
  },
});
