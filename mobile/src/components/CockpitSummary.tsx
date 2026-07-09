import { Bell, Play, RefreshCw, ShieldAlert, Square, TriangleAlert, Unlock, Zap } from "lucide-react-native";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, spacing } from "../theme";
import type { MobileCockpitPayload } from "../types";
import { ActionButton, DetailRow, EmptyState, MetricTile, ProgressBar, Section, StatusBadge, type Tone } from "./ui";

function statusTone(value?: string): Tone {
  const normalized = String(value || "").toLowerCase();
  if (["ready", "running", "connected", "trusted", "pass"].includes(normalized)) return "success";
  if (["blocked", "offline", "danger", "fail"].includes(normalized)) return "danger";
  if (["warning", "degraded", "not_enough_data"].includes(normalized)) return "warning";
  return "neutral";
}

function scoreTone(value: number): Tone {
  if (value >= 75) return "success";
  if (value >= 50) return "warning";
  return "danger";
}

export function CockpitSummary({
  cockpit,
  locked,
  loading,
  onRefresh,
  onUnlock,
  onStart,
  onStop,
}: {
  cockpit: MobileCockpitPayload | null;
  locked: boolean;
  loading: boolean;
  onRefresh: () => void;
  onUnlock: () => void;
  onStart: () => void;
  onStop: () => void;
}) {
  if (!cockpit) {
    return <EmptyState title="No cockpit payload" body="Pair the Android app or refresh after the private tunnel is reachable." />;
  }

  const readinessScore = Number(cockpit.readiness.score ?? 0);
  const sourceScore = Number(cockpit.source.health_score ?? 0);
  const readinessBlockers = cockpit.readiness.blockers.map((blocker) => String(blocker.label || blocker.id || "Readiness blocker"));
  const blockers = [...readinessBlockers, ...cockpit.live.blockers, ...cockpit.open_risk.risk_blockers].slice(0, 8);
  const alert = cockpit.alerts.latest[0];
  const openRisk = cockpit.open_risk.paper_open_positions + cockpit.open_risk.live_open_positions + cockpit.open_risk.unresolved_live_audits;

  return (
    <View style={styles.stack}>
      <Section
        title="Command"
        delay={20}
        right={<StatusBadge label={cockpit.bot.status} tone={statusTone(cockpit.bot.status)} />}>
        <View style={styles.commandBand}>
          <View style={styles.commandMain}>
            <Text style={styles.commandLabel}>Next operator action</Text>
            <Text style={styles.commandText}>{cockpit.next_operator_action}</Text>
          </View>
          <View style={styles.commandIcon}>
            <Zap size={22} color={colors.amber} />
          </View>
        </View>
        <View style={styles.scoreStack}>
          <View style={styles.scoreRow}>
            <Text style={styles.scoreLabel}>Readiness</Text>
            <Text style={styles.scoreValue}>{readinessScore}</Text>
          </View>
          <ProgressBar value={readinessScore} tone={scoreTone(readinessScore)} />
          <View style={styles.scoreRow}>
            <Text style={styles.scoreLabel}>Source health</Text>
            <Text style={styles.scoreValue}>{sourceScore}</Text>
          </View>
          <ProgressBar value={sourceScore} tone={scoreTone(sourceScore)} />
        </View>
      </Section>

      <View style={styles.metricGrid}>
        <MetricTile label="Mode" value={cockpit.bot.mode} detail={cockpit.bot.launch_source} />
        <MetricTile label="Risk" value={openRisk} tone={openRisk > 0 ? "warning" : "success"} detail="open/audit" />
        <MetricTile label="PnL SOL" value={cockpit.pnl.paper.total_pnl_sol.toFixed(3)} tone={cockpit.pnl.paper.total_pnl_sol >= 0 ? "success" : "danger"} detail={`${cockpit.pnl.paper.closed_trades} closed`} />
        <MetricTile label="Alerts" value={cockpit.alerts.latest.length} tone={cockpit.alerts.latest.length ? "warning" : "neutral"} detail="recent" />
      </View>

      <Section title="Blockers" delay={70} right={<StatusBadge label={`${blockers.length}`} tone={blockers.length ? "danger" : "success"} />}>
        {blockers.length ? (
          <View style={styles.blockerList}>
            {blockers.map((blocker, index) => (
              <View key={`${blocker}-${index}`} style={styles.blockerRow}>
                <TriangleAlert size={15} color={colors.rose} />
                <Text style={styles.blockerText}>{blocker}</Text>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.muted}>No mobile-visible blockers right now.</Text>
        )}
      </Section>

      <Section title="Latest Alert" delay={100} right={<Bell size={16} color={alert ? colors.amber : colors.faint} />}>
        {alert ? (
          <View style={styles.alertPreview}>
            <StatusBadge label={alert.level} tone={statusTone(alert.level)} />
            <Text style={styles.alertMessage}>{alert.message}</Text>
            {alert.operator_action ? <Text style={styles.alertAction}>{alert.operator_action}</Text> : null}
          </View>
        ) : (
          <Text style={styles.muted}>No unresolved operator alerts in the mobile window.</Text>
        )}
      </Section>

      <Section
        title="Controls"
        delay={130}
        right={locked ? <StatusBadge label="Locked" tone="warning" /> : <StatusBadge label="Unlocked" tone="success" />}>
        <View style={styles.detailBlock}>
          <DetailRow label="Kill switch" value={cockpit.live.kill_switch_enabled ? "Enabled" : "Clear"} tone={cockpit.live.kill_switch_enabled ? "danger" : "success"} />
          <DetailRow label="Websocket" value={cockpit.connection.websocket} tone="info" />
          <DetailRow label="Telegram" value={cockpit.alerts.telegram.telegram_configured ? "Configured" : "Not configured"} tone={cockpit.alerts.telegram.telegram_configured ? "success" : "warning"} />
        </View>
        <View style={styles.controlGrid}>
          {locked ? (
            <ActionButton label="Unlock" tone="primary" onPress={onUnlock} icon={<Unlock size={16} color={colors.text} />} />
          ) : null}
          <ActionButton
            label="Start"
            tone="primary"
            onPress={onStart}
            disabled={locked || loading || !cockpit.allowed_actions.start}
            loading={loading && cockpit.bot.status !== "running"}
            icon={<Play size={16} color={colors.text} />}
          />
          <ActionButton
            label="Stop"
            onPress={onStop}
            disabled={locked || loading || !cockpit.allowed_actions.stop}
            icon={<Square size={16} color={colors.text} />}
          />
          <ActionButton label="Refresh" onPress={onRefresh} disabled={loading} icon={<RefreshCw size={16} color={colors.text} />} />
        </View>
      </Section>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    gap: spacing.md,
  },
  commandBand: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.md,
    borderColor: colors.borderStrong,
    borderWidth: 1,
    backgroundColor: colors.deep,
    padding: spacing.md,
    borderRadius: 8,
  },
  commandMain: {
    flex: 1,
    gap: 5,
  },
  commandLabel: {
    color: colors.faint,
    fontSize: 10,
    fontWeight: "900",
    textTransform: "uppercase",
  },
  commandText: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "900",
    lineHeight: 20,
  },
  commandIcon: {
    alignItems: "center",
    justifyContent: "center",
    height: 42,
    width: 42,
    borderRadius: 8,
    backgroundColor: colors.amberSoft,
    borderWidth: 1,
    borderColor: colors.amber,
  },
  scoreStack: {
    gap: 8,
  },
  scoreRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  scoreLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  scoreValue: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "900",
  },
  metricGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  blockerList: {
    gap: spacing.sm,
  },
  blockerRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
  },
  blockerText: {
    color: colors.text,
    flex: 1,
    fontSize: 12,
    lineHeight: 18,
  },
  muted: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
  alertPreview: {
    gap: spacing.sm,
  },
  alertMessage: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "900",
    lineHeight: 19,
  },
  alertAction: {
    color: colors.amber,
    fontSize: 12,
    lineHeight: 18,
  },
  detailBlock: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  controlGrid: {
    gap: spacing.sm,
  },
});
