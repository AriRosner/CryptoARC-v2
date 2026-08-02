import { LockKeyhole, ShieldCheck } from "lucide-react-native";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AppState,
  type AppStateStatus,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { useSession } from "../../core/session/SessionProvider";
import {
  type PrivacyMode,
  useSettingsStore,
} from "../../core/settings/settingsStore";
import { colors, radius, spacing } from "../../theme";

export interface AppLockState {
  locked: boolean;
  privacyMode: PrivacyMode;
  unlock(reason: "app_open" | "financial_action"): Promise<boolean>;
  lock(): void;
}

const AppLockContext = createContext<AppLockState | null>(null);

interface AppLockProps {
  children: React.ReactNode;
  initialAppState?: AppStateStatus;
  now?: () => number;
}

export function AppLock({
  children,
  initialAppState = AppState.currentState,
  now = Date.now,
}: AppLockProps) {
  const session = useSession();
  const privacyMode = useSettingsStore((state) => state.privacyMode);
  const lockTimeoutMs = useSettingsStore((state) => state.lockTimeoutMs);
  const [unlockedGeneration, setUnlockedGeneration] = useState<number | null>(null);
  const [appState, setAppState] = useState<AppStateStatus>(initialAppState);
  const appStateRef = useRef<AppStateStatus>(initialAppState);
  const backgroundedAt = useRef<number | null>(null);
  const lifecycleGeneration = useRef(0);
  const hasSession = Boolean(session.record);
  const locked = hasSession && unlockedGeneration !== session.generation;

  const lock = useCallback(() => {
    setUnlockedGeneration(null);
    session.lock();
  }, [session.lock]);

  const unlock = useCallback(
    async (reason: "app_open" | "financial_action"): Promise<boolean> => {
      const generation = session.generation;
      const lifecycle = lifecycleGeneration.current;
      if (!session.record) return reason === "app_open";
      const authenticated =
        reason === "app_open"
          ? await session.authenticateView()
          : await session.authenticateControl();
      if (
        !authenticated ||
        !session.isCurrentGeneration(generation) ||
        lifecycleGeneration.current !== lifecycle ||
        appStateRef.current !== "active"
      ) {
        session.lock();
        return false;
      }
      if (reason === "app_open") setUnlockedGeneration(generation);
      return true;
    },
    [session],
  );

  useEffect(() => {
    const onAppStateChange = (nextState: AppStateStatus) => {
      if (nextState !== "active") {
        lifecycleGeneration.current += 1;
        backgroundedAt.current = now();
        session.lock();
      } else if (
        backgroundedAt.current !== null &&
        now() - backgroundedAt.current >= lockTimeoutMs
      ) {
        setUnlockedGeneration(null);
      }
      appStateRef.current = nextState;
      setAppState(nextState);
    };
    const subscription = AppState.addEventListener("change", onAppStateChange);
    return () => subscription.remove();
  }, [lockTimeoutMs, now, session.lock]);

  useEffect(() => {
    if (!hasSession) setUnlockedGeneration(null);
  }, [hasSession, session.generation]);

  const value = useMemo<AppLockState>(
    () => ({ locked, privacyMode, unlock, lock }),
    [lock, locked, privacyMode, unlock],
  );

  if (session.loading) {
    return <View accessibilityLabel="Loading secure session" style={styles.shield} />;
  }
  if (appState !== "active") {
    return (
      <View accessibilityViewIsModal style={styles.shield}>
        <ShieldCheck color={colors.amber} size={30} />
        <Text style={styles.title}>CryptoARC protected</Text>
      </View>
    );
  }

  return (
    <AppLockContext.Provider value={value}>
      {locked && privacyMode === "full_lock" ? (
        <View accessibilityViewIsModal style={styles.lockScreen}>
          <View style={styles.lockIcon}>
            <LockKeyhole color={colors.amber} size={28} />
          </View>
          <Text style={styles.title}>CryptoARC is locked</Text>
          <Text style={styles.body}>Authenticate locally to view operator data.</Text>
          <Pressable
            accessibilityLabel="Unlock CryptoARC"
            accessibilityRole="button"
            onPress={() => void unlock("app_open")}
            style={styles.unlockButton}>
            <Text style={styles.unlockLabel}>Unlock CryptoARC</Text>
          </Pressable>
        </View>
      ) : (
        <View style={styles.content}>
          <View
            accessibilityElementsHidden={locked}
            importantForAccessibility={locked ? "no-hide-descendants" : "auto"}
            pointerEvents={locked ? "none" : "auto"}
            style={styles.protectedContent}
            testID="locked-read-only-boundary">
            {children}
          </View>
          {locked ? (
            <View accessibilityRole="summary" style={styles.controlsBanner}>
              <LockKeyhole color={colors.amber} size={16} />
              <Text style={styles.controlsText}>Controls locked</Text>
              <Pressable
                accessibilityLabel="Unlock CryptoARC controls"
                accessibilityRole="button"
                onPress={() => void unlock("app_open")}>
                <Text style={styles.controlsAction}>Unlock</Text>
              </Pressable>
            </View>
          ) : null}
        </View>
      )}
    </AppLockContext.Provider>
  );
}

export function useAppLock(): AppLockState {
  const value = useContext(AppLockContext);
  if (!value) throw new Error("useAppLock must be used inside AppLock");
  return value;
}

const styles = StyleSheet.create({
  content: { flex: 1 },
  protectedContent: { flex: 1 },
  shield: {
    alignItems: "center",
    flex: 1,
    gap: spacing.md,
    justifyContent: "center",
    backgroundColor: colors.background,
  },
  lockScreen: {
    alignItems: "center",
    flex: 1,
    gap: spacing.md,
    justifyContent: "center",
    backgroundColor: colors.background,
    padding: spacing.xl,
  },
  lockIcon: {
    alignItems: "center",
    justifyContent: "center",
    height: 64,
    width: 64,
    borderRadius: radius.lg,
    borderColor: colors.borderStrong,
    borderWidth: 1,
    backgroundColor: colors.panel,
  },
  title: { color: colors.text, fontSize: 20, fontWeight: "900" },
  body: { color: colors.muted, fontSize: 13, textAlign: "center" },
  unlockButton: {
    alignItems: "center",
    minHeight: 48,
    minWidth: 200,
    justifyContent: "center",
    borderRadius: radius.md,
    backgroundColor: colors.amber,
    paddingHorizontal: spacing.lg,
  },
  unlockLabel: { color: colors.black, fontSize: 14, fontWeight: "900" },
  controlsBanner: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    minHeight: 48,
    borderTopColor: colors.borderStrong,
    borderTopWidth: 1,
    backgroundColor: colors.panel,
    paddingHorizontal: spacing.md,
  },
  controlsText: { color: colors.text, flex: 1, fontSize: 12, fontWeight: "800" },
  controlsAction: { color: colors.amber, fontSize: 12, fontWeight: "900" },
});
