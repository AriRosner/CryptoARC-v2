import {
  BottomSheetBackdrop,
  BottomSheetModal,
  BottomSheetScrollView,
  type BottomSheetBackdropProps,
  type BottomSheetModal as BottomSheetModalType,
} from "@gorhom/bottom-sheet";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, ShieldAlert, SlidersHorizontal, X } from "lucide-react-native";
import React, { useCallback, useEffect, useMemo, useRef } from "react";
import {
  AccessibilityInfo,
  findNodeHandle,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { ActionButton, DetailRow, StatusBadge } from "../../components/ui";
import { authenticatedRead, mobileReadErrorMessage } from "../../core/api/authenticatedRead";
import { MobileApiError } from "../../core/api/errors";
import { useOptionalSession } from "../../core/session/SessionProvider";
import { colors, radius, spacing } from "../../theme";
import { fetchPositionDetail } from "./api";

export interface PositionSheetProps {
  positionId: string | null;
  onDismiss(): void;
  onOpenDetails(positionId: string): void;
  onAdjustExit(positionId: string): void;
  onClose(positionId: string): void;
}

export function PositionSheet({
  positionId,
  onDismiss,
  onOpenDetails,
  onAdjustExit,
  onClose,
}: PositionSheetProps) {
  const modalRef = useRef<BottomSheetModalType>(null);
  const titleRef = useRef<Text>(null);
  const session = useOptionalSession();
  const snapPoints = useMemo(() => ["60%", "88%"], []);
  const query = useQuery({
    queryKey: ["mobile", "position", positionId, session?.generation ?? "test"],
    queryFn: () =>
      authenticatedRead(session, () =>
        session
          ? fetchPositionDetail(positionId!, {
              apiBaseUrl: session.apiBaseUrl,
              token: session.token,
            })
          : fetchPositionDetail(positionId!),
      ),
    enabled: Boolean(positionId) && (session === null || Boolean(session.token)),
  });

  useEffect(() => {
    if (positionId) modalRef.current?.present();
    else modalRef.current?.dismiss();
  }, [positionId]);

  const accessDenied =
    query.error instanceof MobileApiError &&
    (query.error.status === 401 || query.error.status === 403);
  const position = accessDenied ? undefined : query.data;
  const totalPnl = position?.pnl.total_sol ?? 0;
  const notFound = query.error instanceof MobileApiError && query.error.status === 404;
  const renderBackdrop = useCallback(
    (props: BottomSheetBackdropProps) => (
      <BottomSheetBackdrop
        {...props}
        accessibilityLabel="Dismiss position sheet"
        accessibilityRole="button"
        appearsOnIndex={0}
        disappearsOnIndex={-1}
        pressBehavior="close"
      />
    ),
    [],
  );
  const focusSheet = useCallback((index: number) => {
    if (index < 0) return;
    const node = findNodeHandle(titleRef.current);
    if (node) AccessibilityInfo.setAccessibilityFocus(node);
  }, []);
  useEffect(() => {
    if (positionId && !query.isLoading) focusSheet(0);
  }, [focusSheet, positionId, query.isLoading]);

  return (
    <BottomSheetModal
      ref={modalRef}
      snapPoints={snapPoints}
      enablePanDownToClose
      backdropComponent={renderBackdrop}
      onChange={focusSheet}
      onDismiss={onDismiss}
      backgroundStyle={styles.sheet}
      handleIndicatorStyle={styles.handle}>
      <BottomSheetScrollView
        accessibilityViewIsModal
        importantForAccessibility="yes"
        contentContainerStyle={styles.content}>
        {query.isLoading ? (
          <PositionSheetSkeleton />
        ) : !position ? (
          <View style={styles.message}>
            <Text ref={titleRef} accessibilityRole="header" style={styles.messageTitle}>
              {notFound ? "Position not found" : "Position unavailable"}
            </Text>
            <Text style={styles.messageBody}>
              {notFound
                ? "This stable position ID is no longer present in the local ledger."
                : mobileReadErrorMessage(query.error, "positions")}
            </Text>
            {!notFound ? <ActionButton label="Retry" onPress={() => void query.refetch()} /> : null}
          </View>
        ) : (
          <>
            <View style={styles.header}>
              <View style={styles.headerCopy}>
                <View style={styles.titleLine}>
                  <Text ref={titleRef} accessibilityRole="header" style={styles.title}>{position.symbol}</Text>
                  <StatusBadge label={position.mode} tone={position.mode === "live" ? "warning" : "neutral"} />
                </View>
                <Text style={styles.mint} numberOfLines={1}>{position.mint}</Text>
              </View>
              <Pressable accessibilityLabel="Close position sheet" hitSlop={10} onPress={onDismiss} style={styles.iconButton}>
                <X size={20} color={colors.muted} />
              </Pressable>
            </View>

            {query.isError ? (
              <View style={styles.inlineError}>
                <Text style={styles.inlineErrorText}>The latest refresh failed. Showing the cached position.</Text>
                <ActionButton label="Retry" onPress={() => void query.refetch()} />
              </View>
            ) : null}

            <View style={styles.pnlBand}>
              <Text style={styles.pnlLabel}>Net performance</Text>
              <Text style={[styles.pnlValue, { color: totalPnl >= 0 ? colors.emerald : colors.rose }]}>
                {totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(4)} SOL
              </Text>
              <StatusBadge label={position.pnl.approximate ? "Approximate" : "Reconciled"} tone={position.pnl.approximate ? "warning" : "success"} />
            </View>

            <View>
              <DetailRow label="Tracked value" value={`${position.value_sol.toFixed(4)} SOL`} />
              <DetailRow label="Cost basis" value={`${position.cost_basis_sol.toFixed(4)} SOL`} />
              <DetailRow label="Realized PnL" value={`${position.pnl.realized_sol.toFixed(4)} SOL`} tone={position.pnl.realized_sol >= 0 ? "success" : "danger"} />
              <DetailRow label="Unrealized PnL" value={`${position.pnl.unrealized_sol.toFixed(4)} SOL`} tone={position.pnl.unrealized_sol >= 0 ? "success" : "danger"} />
              <DetailRow label="Mark" value={position.mark.fresh ? "Fresh" : "Stale"} tone={position.mark.fresh ? "success" : "warning"} />
              <DetailRow label="Confidence" value={position.pnl.confidence} />
            </View>

            <View style={styles.guard}>
              <ShieldAlert size={18} color={colors.amber} />
              <Text style={styles.guardText}>{position.allowed_actions.reason}</Text>
            </View>
            <View style={styles.actions}>
              <ActionButton
                label="Adjust exit"
                disabled={!position.allowed_actions.adjust_exit}
                onPress={() => onAdjustExit(position.id)}
                icon={<SlidersHorizontal size={16} color={colors.text} />}
                buttonStyle={styles.action}
              />
              <ActionButton
                label="Close position"
                tone="danger"
                disabled={!position.allowed_actions.close}
                onPress={() => onClose(position.id)}
                buttonStyle={styles.action}
              />
            </View>
            <ActionButton
              label="Full details"
              tone="primary"
              onPress={() => onOpenDetails(position.id)}
              icon={<ExternalLink size={16} color={colors.text} />}
            />
          </>
        )}
      </BottomSheetScrollView>
    </BottomSheetModal>
  );
}

function PositionSheetSkeleton() {
  return (
    <View accessibilityLabel="Loading position" style={styles.skeletonStack}>
      <View style={[styles.skeleton, styles.skeletonTitle]} />
      <View style={[styles.skeleton, styles.skeletonHero]} />
      <View style={[styles.skeleton, styles.skeletonRow]} />
      <View style={[styles.skeleton, styles.skeletonRow]} />
      <View style={[styles.skeleton, styles.skeletonButton]} />
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    backgroundColor: colors.panel,
    borderColor: colors.borderStrong,
    borderWidth: 1,
  },
  handle: {
    backgroundColor: colors.borderStrong,
    width: 42,
  },
  content: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xl,
    gap: spacing.md,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md,
  },
  headerCopy: {
    flex: 1,
    gap: 5,
  },
  titleLine: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  title: {
    color: colors.text,
    fontSize: 24,
    fontWeight: "900",
  },
  mint: {
    color: colors.faint,
    fontSize: 10,
  },
  iconButton: {
    alignItems: "center",
    justifyContent: "center",
    height: 44,
    width: 44,
    borderRadius: radius.md,
    backgroundColor: colors.panelRaised,
  },
  pnlBand: {
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    borderWidth: 1,
    backgroundColor: colors.deep,
    padding: spacing.md,
    gap: 6,
  },
  pnlLabel: {
    color: colors.faint,
    fontSize: 10,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  pnlValue: {
    fontSize: 24,
    fontWeight: "900",
  },
  guard: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    borderColor: colors.amber,
    borderRadius: radius.md,
    borderWidth: 1,
    backgroundColor: colors.amberSoft,
    padding: spacing.sm,
  },
  guardText: {
    color: colors.text,
    flex: 1,
    fontSize: 11,
    lineHeight: 16,
  },
  actions: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  action: {
    flex: 1,
  },
  message: {
    paddingVertical: spacing.xl,
    gap: spacing.xs,
  },
  messageTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: "900",
  },
  messageBody: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
  inlineError: {
    borderColor: colors.rose,
    borderRadius: radius.md,
    borderWidth: 1,
    backgroundColor: colors.roseSoft,
    padding: spacing.sm,
    gap: spacing.sm,
  },
  inlineErrorText: {
    color: colors.rose,
    fontSize: 11,
    lineHeight: 16,
  },
  skeletonStack: {
    gap: spacing.md,
  },
  skeleton: {
    backgroundColor: colors.panelRaised,
    borderRadius: radius.sm,
  },
  skeletonTitle: {
    height: 28,
    width: "44%",
  },
  skeletonHero: {
    height: 96,
  },
  skeletonRow: {
    height: 38,
  },
  skeletonButton: {
    height: 48,
  },
});
