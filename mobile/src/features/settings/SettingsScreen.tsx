import { SlidersHorizontal } from "lucide-react-native";
import React from "react";
import { ScrollView, StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ActionButton, PageHeader, Section, SegmentedControl } from "../../components/ui";
import {
  type MotionMode,
  type PrivacyMode,
  type RefreshProfile,
  useSettingsStore,
} from "../../core/settings/settingsStore";
import { colors, spacing } from "../../theme";

export function SettingsScreen() {
  const settings = useSettingsStore();
  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader
          eyebrow="Local preferences"
          title="Settings"
          subtitle="Privacy and display choices stay on this device."
          right={<SlidersHorizontal color={colors.amber} size={22} />}
        />
        <Section title="Privacy mode">
          <SegmentedControl
            options={[
              { label: "Full lock", value: "full_lock" },
              { label: "Read-only before unlock", value: "read_only_before_unlock" },
            ]}
            value={settings.privacyMode}
            onChange={(privacyMode) => settings.update({ privacyMode: privacyMode as PrivacyMode })}
          />
        </Section>
        <Section title="Lock timeout">
          <SegmentedControl
            options={[
              { label: "Immediately", value: "0" },
              { label: "1 minute", value: "60000" },
              { label: "5 minutes", value: "300000" },
            ]}
            value={String(settings.lockTimeoutMs)}
            onChange={(value) => settings.update({ lockTimeoutMs: Number(value) })}
          />
        </Section>
        <Section title="Motion">
          <SegmentedControl
            options={[
              { label: "Expressive", value: "expressive" },
              { label: "Balanced", value: "balanced" },
              { label: "Minimal", value: "minimal" },
              { label: "System", value: "system" },
            ]}
            value={settings.motion}
            onChange={(motion) => settings.update({ motion: motion as MotionMode })}
          />
        </Section>
        <Section title="Refresh profile">
          <SegmentedControl
            options={[
              { label: "Performance", value: "performance" },
              { label: "Balanced", value: "balanced" },
              { label: "Battery saver", value: "battery_saver" },
            ]}
            value={settings.refreshProfile}
            onChange={(refreshProfile) => settings.update({ refreshProfile: refreshProfile as RefreshProfile })}
          />
        </Section>
        <Section title="Feedback and previews">
          <ActionButton
            accessibilityState={{ checked: settings.hapticsEnabled }}
            label={settings.hapticsEnabled ? "Haptics on" : "Haptics off"}
            onPress={() => settings.update({ hapticsEnabled: !settings.hapticsEnabled })}
          />
          <ActionButton
            accessibilityState={{ checked: settings.notificationPreviewsEnabled }}
            label={settings.notificationPreviewsEnabled ? "Previews on" : "Previews off"}
            onPress={() => settings.update({ notificationPreviewsEnabled: !settings.notificationPreviewsEnabled })}
          />
        </Section>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.background },
  content: { gap: spacing.md, padding: spacing.lg, paddingBottom: 96 },
});
