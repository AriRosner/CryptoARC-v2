import { router } from "expo-router";
import {
  ArrowUpRight,
  BadgeDollarSign,
  RotateCcw,
} from "lucide-react-native";
import React from "react";
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ActionButton,
  DetailRow,
  EmptyState,
  ErrorBanner,
  PageHeader,
  Section,
  StatusBadge,
} from "../../components/ui";
import { WalletSkeleton } from "../../components/skeletons/WalletSkeleton";
import { colors, spacing } from "../../theme";
import { useDestinationsQuery, useWalletQuery, useWalletTransactionsQuery } from "./queries";
import { TransactionList } from "./TransactionList";
import type {
  MobileDestinationAuthorization,
  MobileWalletPayload,
  MobileWalletTransaction,
} from "./types";
import { WalletHealth } from "./WalletHealth";

export interface WalletScreenProps {
  wallet?: MobileWalletPayload;
  transactions?: MobileWalletTransaction[];
  destinations?: MobileDestinationAuthorization[];
  loading?: boolean;
  error?: string;
  onRefresh?(): void;
  onWithdraw?(): void;
  onProfitSweep?(): void;
  onRentRecovery?(): void;
}

function sol(value: number) {
  return `${value.toFixed(6)} SOL`;
}

function WalletView({
  wallet,
  transactions = [],
  destinations = [],
  loading = false,
  error = "",
  onRefresh = () => undefined,
  onWithdraw = () => undefined,
  onProfitSweep = () => undefined,
  onRentRecovery = () => undefined,
}: WalletScreenProps) {
  const hasAuthorization = (action: MobileDestinationAuthorization["action"]) =>
    destinations.some(
      (destination) =>
        destination.status === "active" && destination.action === action,
    );

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            tintColor={colors.amber}
            onRefresh={onRefresh}
          />
        }>
        <PageHeader
          eyebrow="Treasury evidence"
          title="Wallet"
          subtitle="Public wallet state, allocation, costs, reconciliation, and guarded treasury actions."
          right={
            wallet ? (
              <View style={styles.headerStatus}>
                {loading ? <Text accessibilityLabel="Syncing wallet" style={styles.syncing}>Syncing</Text> : null}
                <StatusBadge
                  label={wallet.freshness.approximate ? "Approximate" : "Exact"}
                  tone={wallet.freshness.status === "fresh" ? "success" : "warning"}
                />
              </View>
            ) : null
          }
        />
        <ErrorBanner message={error} />
        {!wallet && !loading ? (
          <EmptyState
            title="Wallet unavailable"
            body="Reconnect to the private mobile API before reviewing treasury state."
          />
        ) : wallet ? (
          <>
            <Section title="Funds">
              {wallet.balances.map((balance) => (
                <View key={balance.asset} style={styles.balance}>
                  <View style={styles.balanceHeader}>
                    <Text style={styles.asset}>{balance.asset}</Text>
                    <Text style={styles.total}>{sol(balance.total)}</Text>
                  </View>
                  <DetailRow
                    label="Committed"
                    value={sol(balance.committed)}
                  />
                  <DetailRow
                    label="Available"
                    value={sol(balance.available)}
                    tone="success"
                  />
                  <DetailRow
                    label="Reserved"
                    value={sol(balance.reserved)}
                    tone={balance.reserved > 0 ? "warning" : "neutral"}
                  />
                </View>
              ))}
            </Section>
            <Section title="Allocation">
              {wallet.allocation.map((allocation) => (
                <DetailRow
                  key={allocation.asset}
                  label={allocation.asset}
                  value={`${allocation.percentage.toFixed(1)}%`}
                />
              ))}
            </Section>
            <Section title="PnL and costs">
              <DetailRow
                label="Realized"
                value={sol(wallet.pnl.realized_sol)}
              />
              <DetailRow
                label="Unrealized"
                value={sol(wallet.pnl.unrealized_sol)}
              />
              <DetailRow
                label="Network fees"
                value={sol(wallet.fees.network_sol)}
              />
              <DetailRow
                label="Priority fees"
                value={sol(wallet.fees.priority_sol)}
              />
              <DetailRow
                label="Total fees"
                value={sol(wallet.fees.total_sol)}
              />
              <DetailRow
                label="Recoverable rent"
                value={sol(wallet.rent.recoverable_sol)}
              />
              <DetailRow
                label="Eligible accounts"
                value={wallet.rent.eligible_accounts}
              />
            </Section>
            <Section title="Reconciliation">
              <DetailRow
                label="Result"
                value={wallet.reconciliation.status}
                tone={
                  wallet.reconciliation.status === "matched"
                    ? "success"
                    : "warning"
                }
              />
              <DetailRow
                label="Last checked"
                value={
                  wallet.reconciliation.last_reconciled_at
                    ? new Date(
                        wallet.reconciliation.last_reconciled_at,
                      ).toLocaleString()
                    : "Not reconciled"
                }
              />
            </Section>
            <Section title="Execution health">
              <WalletHealth health={wallet.health} />
            </Section>
            <Section title="Authorized treasury">
              <ActionButton
                accessibilityHint="Reviews the authorized destination, amount, limits, and fees before submission"
                label="Review withdrawal"
                icon={<ArrowUpRight color={colors.text} size={16} />}
                disabled={!hasAuthorization("withdrawal")}
                onPress={onWithdraw}
              />
              <ActionButton
                accessibilityHint="Reviews the authorized profit sweep destination, amount, and limits before submission"
                label="Review profit sweep"
                icon={<BadgeDollarSign color={colors.text} size={16} />}
                disabled={!hasAuthorization("profit_sweep")}
                onPress={onProfitSweep}
              />
              <ActionButton
                accessibilityHint="Reviews eligible accounts, authorization, and expected rent recovery before submission"
                label="Review rent recovery"
                icon={<RotateCcw color={colors.text} size={16} />}
                disabled={
                  !hasAuthorization("rent_recovery") ||
                  wallet.rent.eligible_token_accounts.length === 0
                }
                onPress={onRentRecovery}
              />
              {!destinations.some(
                (destination) => destination.status === "active",
              ) ? (
                <Text style={styles.note}>
                  Issue a short-lived destination authorization from the
                  desktop before reviewing a treasury action.
                </Text>
              ) : null}
            </Section>
            <Section title="Transactions">
              <TransactionList transactions={transactions} />
            </Section>
          </>
        ) : (
          <WalletSkeleton />
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function ConnectedWalletScreen() {
  const walletQuery = useWalletQuery();
  const transactionsQuery = useWalletTransactionsQuery();
  const destinationsQuery = useDestinationsQuery();
  const destinations = destinationsQuery.data?.destinations ?? [];
  const activeAuthorization = (
    action: MobileDestinationAuthorization["action"],
  ) =>
    destinations.find(
      (destination) =>
        destination.status === "active" && destination.action === action,
    );
  const treasuryParams = (
    action: MobileDestinationAuthorization["action"],
  ) => {
    const authorization = activeAuthorization(action);
    if (!authorization) return null;
    return {
      action,
      authorizationId: authorization.id,
      address: authorization.address,
      asset: authorization.asset,
      amount: authorization.max_amount,
    };
  };
  const refresh = () => {
    void walletQuery.refetch();
    void transactionsQuery.refetch();
    void destinationsQuery.refetch();
  };
  return (
    <WalletView
      wallet={walletQuery.data}
      transactions={transactionsQuery.data?.transactions}
      destinations={destinations}
      loading={
        walletQuery.isLoading ||
        walletQuery.isRefetching ||
        transactionsQuery.isRefetching ||
        destinationsQuery.isRefetching
      }
      error={
        walletQuery.isError
          ? "Wallet data is unavailable over the private mobile connection."
          : ""
      }
      onRefresh={refresh}
      onWithdraw={() => {
        const active = activeAuthorization("withdrawal");
        if (!active) return;
        router.push({
          pathname: "/wallet/withdraw",
          params: {
            authorizationId: active.id,
            address: active.address,
            asset: active.asset,
            maxAmount: active.max_amount,
          },
        });
      }}
      onProfitSweep={() => {
        const params = treasuryParams("profit_sweep");
        if (!params) return;
        router.push({ pathname: "/wallet/treasury", params });
      }}
      onRentRecovery={() => {
        const params = treasuryParams("rent_recovery");
        if (!params || !walletQuery.data) return;
        router.push({
          pathname: "/wallet/treasury",
          params: {
            ...params,
            tokenAccounts:
              walletQuery.data.rent.eligible_token_accounts.join(","),
          },
        });
      }}
    />
  );
}

export function WalletScreen(props: WalletScreenProps = {}) {
  if (props.wallet || props.loading !== undefined || props.error !== undefined) {
    return <WalletView {...props} />;
  }
  return <ConnectedWalletScreen />;
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    padding: spacing.lg,
    paddingBottom: 96,
    gap: spacing.md,
  },
  balance: {
    gap: spacing.sm,
    borderTopColor: colors.border,
    borderTopWidth: 1,
    paddingTop: spacing.sm,
  },
  balanceHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md,
  },
  asset: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "900",
  },
  total: {
    color: colors.amber,
    fontSize: 13,
    fontWeight: "900",
  },
  note: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 17,
  },
  headerStatus: {
    alignItems: "flex-end",
    gap: spacing.xs,
  },
  syncing: {
    color: colors.amber,
    fontSize: 10,
    fontWeight: "800",
  },
});
