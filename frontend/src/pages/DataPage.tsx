import React from "react";
import { 
  Database, 
  Download, 
  Upload,
  Trash2, 
  RotateCcw, 
  Shield, 
  Activity, 
  Gauge, 
  Clock, 
  Target, 
  Bell,
  Save,
  ChevronRight,
  FileText
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { Badge } from "../components/Badge";
import { Skeleton } from "../components/Skeleton";
import { cn } from "../components/utils";
import { exportUrl, backupDatabase, backupRestoreExportUrl, confirmRestoreArtifact, createBackupArtifact, downloadAuthenticatedExport, evidenceModeSeparationExportUrl, fetchEvidenceModeSeparation, fetchManualLiveProof, fetchOperatorLogs, fetchOutcomeExplanations, fetchPilotReadiness, fetchPostPilotReview, fetchPostRunReview, fetchReleaseReadiness, fetchSessionReport, fetchSetupReadiness, fetchSolanaLogsVerification, fetchSourceParserReplay, fetchSourceSoakAcceptance, incidentExportUrl, manualLiveProofExportUrl, operatorLogsExportUrl, outcomeExplanationsExportUrl, pilotReadinessExportUrl, postPilotReviewExportUrl, postRunReviewExportUrl, previewRestoreArtifact, recordIncidentExportReview, recordReleaseVerification, recordSourceSoakSnapshot, releaseReadinessExportUrl, runRestoreSmokeTest, sessionReportExportUrl, setupReadinessExportUrl, solanaLogsVerificationExportUrl, sourceHealthExportUrl, sourceParserReplayExportUrl, sourceSoakAcceptanceExportUrl } from "../api";
import type { 
  BackupRestoreHistoryEntry,
  DataSummary, 
  EvidenceModeSeparationReport,
  RestoreArtifactPreview,
  RestoreSmokeTestReport,
  SourceEvent, 
  SourceHealth, 
  AlertStatus,
  SecurityStatus, 
  TradeRecord, 
  PriceObservation, 
  StrategyDecisionRecord, 
  TradeSession, 
  SettingsVersion, 
  DataIntegrityReport, 
  PriceDiagnostics, 
  PumpFunReport, 
  SafetyStatus, 
  ReadinessStatus, 
  ReleaseReadinessReport,
  OperationalMonitoring, 
  OperatorLogsReport,
  OperatorSessionReport,
  OutcomeExplanationsReport,
  PilotReadinessReport,
  ManualLiveProofReport,
  PostRunReviewReport,
  PostPilotReviewReport,
  SetupReadinessReport,
  SourceAdapterStatus, 
  SolanaLogsVerificationReport,
  SourceSoakAcceptanceReport,
  SourceParserReplayReport,
  WatchdogStatus, 
  SolanaStatus, 
  LiveExecutionRequest, 
  LiveExecutionAudit, 
  TradeEvent 
  , WorkloadPressure
} from "../types";

export type DataClearTarget =
  | "tokens" | "events" | "source_events" | "backtests" | "trades"
  | "price_observations" | "strategy_decisions" | "trade_sessions"
  | "settings_versions" | "experiments" | "trade_labels" | "strategy_presets"
  | "live_execution_requests" | "live_sessions" | "live_execution_audits"
  | "live_intents" | "live_ledger_positions" | "source_soak_history" | "all";

interface DataPageProps {
  summary: DataSummary | null;
  sourceEvents: SourceEvent[];
  sourceHealth: SourceHealth | null;
  securityStatus: SecurityStatus | null;
  alertStatus: AlertStatus | null;
  trades: TradeRecord[];
  priceObservations: PriceObservation[];
  strategyDecisions: StrategyDecisionRecord[];
  tradeSessions: TradeSession[];
  settingsVersions: SettingsVersion[];
  dataIntegrity: DataIntegrityReport | null;
  priceDiagnostics: PriceDiagnostics | null;
  pumpfunReport: PumpFunReport | null;
  safetyStatus: SafetyStatus | null;
  readinessStatus: ReadinessStatus | null;
  opsMonitoring: OperationalMonitoring | null;
  workloadPressure: WorkloadPressure | null;
  sourceAdapters: SourceAdapterStatus[];
  watchdogStatus: WatchdogStatus | null;
  solanaStatus: SolanaStatus | null;
  liveRequests: LiveExecutionRequest[];
  liveAudit: LiveExecutionAudit[];
  auditEvents: TradeEvent[];
  onRefresh: () => Promise<void>;
  onRecover: () => Promise<void>;
  onSendTestAlert: () => Promise<void>;
  onReviewLiveRequest: (requestId: string, status: "reviewed" | "rejected") => Promise<void>;
  onRecoverPaperPositions: () => Promise<void>;
  onClear: (target: DataClearTarget) => Promise<void>;
}

const DataMetric: React.FC<{ label: string; value: string | number; color?: string; loading?: boolean }> = ({ label, value, color = "text-white", loading = false }) => (
  <div className="flex flex-col gap-1 rounded-xl border border-white/5 bg-white/[0.02] p-3 transition-colors hover:bg-white/[0.04]">
    <span className="text-[9px] font-black uppercase tracking-widest text-zinc-500">{label}</span>
    {loading ? <Skeleton className="h-5 w-20" /> : <span className={cn("text-sm font-black tracking-tight", color)}>{value}</span>}
  </div>
);

function auditLevelTone(level: string): string {
  const normalized = level.toLowerCase();
  if (normalized === "error" || normalized === "danger") return "border-rose-500/20 bg-rose-500/10 text-rose-300";
  if (normalized === "warn" || normalized === "warning") return "border-amber-500/20 bg-amber-500/10 text-amber-300";
  if (normalized === "success") return "border-emerald-500/20 bg-emerald-500/10 text-emerald-300";
  return "border-blue-500/20 bg-blue-500/10 text-blue-300";
}

function pilotGateAction(gateId: string): { href: string; label: string; detail: string } {
  const actions: Record<string, { href: string; label: string; detail: string }> = {
    env_live_enabled: { href: "#readiness-panel", label: "Review Live Readiness", detail: "Confirm the local live unlock and readiness state." },
    session_acknowledged: { href: "#readiness-panel", label: "Acknowledge Session", detail: "Use the live workspace session controls before pilot mode." },
    source_trust: { href: "#source-inspector", label: "Inspect Source", detail: "Check source trust, raw events, and malformed launch data." },
    source_soak: { href: "#source-inspector", label: "Review Source Soak", detail: "Check direct/PumpPortal match rate and decoded create coverage." },
    source_soak_history: { href: "#source-inspector", label: "Save Source Soak", detail: "Record a ready source-soak snapshot before pilot mode when direct verification is required." },
    strategy_promotion: { href: "#readiness-panel", label: "Review Strategy Gates", detail: "Inspect paper promotion gates and recommended actions." },
    execution_shadow: { href: "#readiness-panel", label: "Review Shadow Evidence", detail: "Check quote, stale-rate, and shadow execution gates." },
    shadow_samples: { href: "#live-audit-panel", label: "Collect Shadow Audits", detail: "Run more dry-run quotes and shadow comparisons." },
    shadow_pnl: { href: "#live-audit-panel", label: "Inspect Shadow PnL", detail: "Review shadow outcomes before risking capital." },
    policy_caps: { href: "#readiness-panel", label: "Fix Caps", detail: "Set tiny pilot caps and policy limits." },
    signer_health: { href: "#signer-panel", label: "Check Signer", detail: "Verify signer mode, health, and local transport." },
    manual_live_proof: { href: "#live-audit-panel", label: "Prove Wallet", detail: "Complete and reconcile a tiny browser-wallet manual live proof for the selected wallet." },
    autonomy_entry: { href: "#readiness-panel", label: "Review Entry Autonomy", detail: "Resolve entry autonomy blockers before pilot buys." },
    autonomy_exit: { href: "#readiness-panel", label: "Review Exit Autonomy", detail: "Protective exits must be available first." },
    recovery_debt: { href: "#live-audit-panel", label: "Recover Audits", detail: "Clear unresolved live audit debt." },
    ledger_confidence: { href: "#live-audit-panel", label: "Review Ledger Evidence", detail: "Resolve stale balance or needs-review reconciliation." },
    backup: { href: "#restore-panel", label: "Create Backup", detail: "Download a backup artifact before pilot mode." },
    kill_switch: { href: "#readiness-panel", label: "Review Kill Switch", detail: "Clear the audited kill switch only after blockers are reviewed." }
  };
  return actions[gateId] ?? { href: "#system-audit-log", label: "Review Evidence", detail: "Inspect the audit log and exported report." };
}

function setupGateAction(gateId: string): { href: string; label: string } {
  const actions: Record<string, { href: string; label: string }> = {
    mode: { href: "#readiness-panel", label: "Review Mode" },
    source_selection: { href: "#source-inspector", label: "Inspect Source" },
    source_detection: { href: "#source-inspector", label: "Inspect Source" },
    schema: { href: "#migration-panel", label: "View Schema" },
    paper_settings: { href: "#readiness-panel", label: "Review Settings" },
    source_health: { href: "#source-inspector", label: "Inspect Health" },
    auth: { href: "#security-panel", label: "Security" },
    backup: { href: "#restore-panel", label: "Create Backup" },
    live_disabled: { href: "#readiness-panel", label: "Live Gates" }
  };
  return actions[gateId] ?? { href: "#system-audit-log", label: "Review" };
}

const setupWizardStages = [
  { id: "environment", label: "Environment", gateIds: ["mode", "schema"] },
  { id: "source", label: "Source", gateIds: ["source_selection", "source_detection", "source_health"] },
  { id: "paper", label: "Paper", gateIds: ["paper_settings"] },
  { id: "security", label: "Security", gateIds: ["auth"] },
  { id: "recovery", label: "Backup", gateIds: ["backup"] },
  { id: "live_guard", label: "Live Guard", gateIds: ["live_disabled"] }
];

function outcomeTone(type: string): "success" | "warning" | "danger" | "info" {
  if (type === "buy" || type === "sell") return "success";
  if (type === "block") return "danger";
  if (type === "override" || type === "recovery") return "warning";
  return "info";
}

export const DataPage: React.FC<DataPageProps> = ({
  summary,
  sourceEvents,
  sourceHealth,
  securityStatus,
  alertStatus,
  trades,
  priceObservations,
  strategyDecisions,
  tradeSessions,
  settingsVersions,
  dataIntegrity,
  priceDiagnostics,
  pumpfunReport,
  safetyStatus,
  readinessStatus,
  opsMonitoring,
  workloadPressure,
  sourceAdapters,
  watchdogStatus,
  solanaStatus,
  liveRequests,
  liveAudit,
  auditEvents,
  onRefresh,
  onRecover,
  onSendTestAlert,
  onReviewLiveRequest,
  onRecoverPaperPositions,
  onClear
}) => {
  const loadingCore = !summary || !dataIntegrity || !readinessStatus || !sourceHealth || !solanaStatus || !watchdogStatus;
  const clearTargets: DataClearTarget[] = [
    "tokens", "events", "source_events", "backtests", "trades", 
    "price_observations", "strategy_decisions", "trade_sessions", 
    "settings_versions", "experiments", "trade_labels", "strategy_presets", 
    "live_execution_requests", "live_sessions", "live_execution_audits", 
    "live_intents", "live_ledger_positions", "source_soak_history"
  ];

  const exportTargets: Exclude<DataClearTarget, "events">[] = [
    "tokens", "source_events", "backtests", "trades", "price_observations", 
    "strategy_decisions", "trade_sessions", "settings_versions", 
    "experiments", "trade_labels", "strategy_presets", 
    "live_execution_requests", "live_sessions", "live_execution_audits", 
    "live_intents", "live_ledger_positions", "source_soak_history", "all"
  ];
  const readinessTone =
    readinessStatus?.status === "ready"
      ? "success"
      : readinessStatus?.status === "warning" || readinessStatus?.status === "not_enough_data"
        ? "warning"
        : "danger";
  const sourceHealthTone =
    (sourceHealth?.health_score ?? 0) >= 70
      ? "text-emerald-500"
      : (sourceHealth?.health_score ?? 0) >= 50
        ? "text-amber-400"
        : "text-rose-400";
  const sourceTrustTone =
    sourceHealth?.trust_state === "trusted"
      ? "text-emerald-500"
      : sourceHealth?.trust_state === "unknown"
        ? "text-zinc-400"
        : sourceHealth?.trust_state === "stale" || sourceHealth?.trust_state === "conflicting"
          ? "text-rose-400"
          : "text-amber-400";
  const [restorePreview, setRestorePreview] = React.useState<RestoreArtifactPreview | null>(null);
  const [restoreArtifact, setRestoreArtifact] = React.useState<Record<string, unknown> | null>(null);
  const [restoreFileName, setRestoreFileName] = React.useState("");
  const [restoreBusy, setRestoreBusy] = React.useState(false);
  const [restoreMessage, setRestoreMessage] = React.useState("");
  const [restoreSmokeTest, setRestoreSmokeTest] = React.useState<RestoreSmokeTestReport | null>(null);
  const [sourceEventStatusFilter, setSourceEventStatusFilter] = React.useState("");
  const [sourceEventSourceFilter, setSourceEventSourceFilter] = React.useState("");
  const [sourceEventKindFilter, setSourceEventKindFilter] = React.useState("");
  const [sourceEventParserFilter, setSourceEventParserFilter] = React.useState("");
  const [sourceEventMintFilter, setSourceEventMintFilter] = React.useState("");
  const [pilotReadiness, setPilotReadiness] = React.useState<PilotReadinessReport | null>(null);
  const [pilotReadinessError, setPilotReadinessError] = React.useState("");
  const [manualLiveProof, setManualLiveProof] = React.useState<ManualLiveProofReport | null>(null);
  const [manualLiveProofError, setManualLiveProofError] = React.useState("");
  const [setupReadiness, setSetupReadiness] = React.useState<SetupReadinessReport | null>(null);
  const [setupReadinessError, setSetupReadinessError] = React.useState("");
  const [releaseReadiness, setReleaseReadiness] = React.useState<ReleaseReadinessReport | null>(null);
  const [releaseReadinessError, setReleaseReadinessError] = React.useState("");
  const [releaseVerificationBusy, setReleaseVerificationBusy] = React.useState(false);
  const [postRunReview, setPostRunReview] = React.useState<PostRunReviewReport | null>(null);
  const [postRunReviewError, setPostRunReviewError] = React.useState("");
  const [postPilotReview, setPostPilotReview] = React.useState<PostPilotReviewReport | null>(null);
  const [postPilotReviewError, setPostPilotReviewError] = React.useState("");
  const [reviewingIncidentAuditId, setReviewingIncidentAuditId] = React.useState("");
  const [sessionReport, setSessionReport] = React.useState<OperatorSessionReport | null>(null);
  const [sessionReportError, setSessionReportError] = React.useState("");
  const [evidenceModeSeparation, setEvidenceModeSeparation] = React.useState<EvidenceModeSeparationReport | null>(null);
  const [evidenceModeSeparationError, setEvidenceModeSeparationError] = React.useState("");
  const [operatorLogs, setOperatorLogs] = React.useState<OperatorLogsReport | null>(null);
  const [operatorLogsError, setOperatorLogsError] = React.useState("");
  const [outcomeExplanations, setOutcomeExplanations] = React.useState<OutcomeExplanationsReport | null>(null);
  const [outcomeExplanationsError, setOutcomeExplanationsError] = React.useState("");
  const [sourceParserReplay, setSourceParserReplay] = React.useState<SourceParserReplayReport | null>(null);
  const [sourceParserReplayError, setSourceParserReplayError] = React.useState("");
  const [solanaLogsVerification, setSolanaLogsVerification] = React.useState<SolanaLogsVerificationReport | null>(null);
  const [solanaLogsVerificationError, setSolanaLogsVerificationError] = React.useState("");
  const [sourceSoakAcceptance, setSourceSoakAcceptance] = React.useState<SourceSoakAcceptanceReport | null>(null);
  const [sourceSoakBusy, setSourceSoakBusy] = React.useState(false);
  const [sourceSoakError, setSourceSoakError] = React.useState("");
  const restoreInputRef = React.useRef<HTMLInputElement | null>(null);
  const backupRestoreHistory = opsMonitoring?.backup_restore?.history ?? [];
  const signerDaemon = opsMonitoring?.signer_daemon;
  const pilotPassedGates = pilotReadiness?.gates.filter((gate) => gate.status === "pass").length ?? 0;
  const pilotFailedGates = pilotReadiness?.gates.filter((gate) => gate.status !== "pass").length ?? 0;
  const pilotFailedGateItems = pilotReadiness?.gates.filter((gate) => gate.status !== "pass").slice(0, 5) ?? [];
  const pilotRunbook = pilotReadiness?.runbook_checklist ?? [];
  const setupPassedGates = setupReadiness?.gates.filter((gate) => gate.status === "pass").length ?? 0;
  const setupWarningGates = setupReadiness?.gates.filter((gate) => gate.status === "warn").length ?? 0;
  const setupFailedGates = setupReadiness?.gates.filter((gate) => gate.status === "fail").length ?? 0;
  const setupActionItems = setupReadiness?.next_steps.slice(0, 5) ?? [];
  const releasePassedGates = releaseReadiness?.gates.filter((gate) => gate.status === "pass").length ?? 0;
  const releaseWarningGates = releaseReadiness?.gates.filter((gate) => gate.status === "warn").length ?? 0;
  const releaseFailedGates = releaseReadiness?.gates.filter((gate) => gate.status === "fail").length ?? 0;
  const releaseActionItems = releaseReadiness?.next_steps.slice(0, 5) ?? [];
  const setupWizard = React.useMemo(() => {
    const gates = setupReadiness?.gates ?? [];
    const byId = new Map(gates.map((gate) => [gate.id, gate]));
    const stages = setupWizardStages.map((stage) => {
      const stageGates = stage.gateIds.map((id) => byId.get(id)).filter(Boolean) as SetupReadinessReport["gates"];
      const failed = stageGates.filter((gate) => gate.status === "fail");
      const warnings = stageGates.filter((gate) => gate.status === "warn");
      const status = failed.length ? "fail" : warnings.length ? "warn" : stageGates.length ? "pass" : "pending";
      const gate = failed[0] ?? warnings[0] ?? stageGates[0] ?? null;
      return { ...stage, gates: stageGates, status, gate };
    });
    const completed = stages.filter((stage) => stage.status === "pass").length;
    const active = stages.find((stage) => stage.status === "fail") ?? stages.find((stage) => stage.status === "warn") ?? stages.find((stage) => stage.status !== "pass") ?? stages[stages.length - 1];
    return {
      stages,
      active,
      completed,
      progressPct: stages.length ? Math.round((completed / stages.length) * 100) : 0
    };
  }, [setupReadiness]);
  const postRunChecklistIssues = postRunReview?.checklist.filter((item) => item.status !== "pass" && item.status !== "empty").slice(0, 4) ?? [];
  const openRisk = sessionReport?.open_risk;
  const liveRecoverySummary = opsMonitoring?.live_recovery?.summary ?? {};
  const sourceEventStatuses = React.useMemo(() => Array.from(new Set(sourceEvents.map((event) => event.status).filter(Boolean))).sort(), [sourceEvents]);
  const sourceEventSources = React.useMemo(() => Array.from(new Set(sourceEvents.map((event) => event.source).filter(Boolean))).sort(), [sourceEvents]);
  const sourceEventKinds = React.useMemo(() => Array.from(new Set(sourceEvents.map((event) => event.event_kind).filter(Boolean))).sort(), [sourceEvents]);
  const sourceEventParserResults = React.useMemo(() => Array.from(new Set(sourceEvents.map((event) => event.parser_result).filter(Boolean))).sort(), [sourceEvents]);
  const downloadExport = React.useCallback((url: string, fallbackFilename = "cryptoarc-export.json") => {
    downloadAuthenticatedExport(url, fallbackFilename).catch((error) => {
      setRestoreMessage(error instanceof Error ? error.message : "Export download failed");
    });
  }, []);
  const filteredSourceEvents = React.useMemo(() => {
    const mintFilter = sourceEventMintFilter.trim().toLowerCase();
    return sourceEvents.filter((event) => {
      const mint = sourceEventMint(event).toLowerCase();
      return (
        (!sourceEventStatusFilter || event.status === sourceEventStatusFilter) &&
        (!sourceEventSourceFilter || event.source === sourceEventSourceFilter) &&
        (!sourceEventKindFilter || event.event_kind === sourceEventKindFilter) &&
        (!sourceEventParserFilter || event.parser_result === sourceEventParserFilter) &&
        (!mintFilter || mint.includes(mintFilter))
      );
    });
  }, [sourceEvents, sourceEventKindFilter, sourceEventMintFilter, sourceEventParserFilter, sourceEventSourceFilter, sourceEventStatusFilter]);

  function sourceEventMint(event: SourceEvent): string {
    const payload = event.raw_payload ?? {};
    for (const key of ["mint", "tokenMint", "token", "ca", "normalized_mint"]) {
      const value = payload[key];
      if (typeof value === "string" && value.trim()) return value.trim();
    }
    return "";
  }

  async function refreshPilotReadiness() {
    try {
      const report = await fetchPilotReadiness();
      setPilotReadiness(report);
      setPilotReadinessError("");
    } catch (error) {
      setPilotReadinessError(error instanceof Error ? error.message : "Pilot readiness failed");
    }
  }

  async function refreshManualLiveProof() {
    try {
      setManualLiveProof(await fetchManualLiveProof());
      setManualLiveProofError("");
    } catch (error) {
      setManualLiveProofError(error instanceof Error ? error.message : "Manual-live proof report failed");
    }
  }

  async function refreshPostPilotReview() {
    try {
      setPostPilotReview(await fetchPostPilotReview());
      setPostPilotReviewError("");
    } catch (error) {
      setPostPilotReviewError(error instanceof Error ? error.message : "Post-pilot review failed");
    }
  }

  async function refreshSetupReadiness() {
    try {
      const report = await fetchSetupReadiness();
      setSetupReadiness(report);
      setSetupReadinessError("");
    } catch (error) {
      setSetupReadinessError(error instanceof Error ? error.message : "Setup readiness failed");
    }
  }

  async function refreshReleaseReadiness() {
    try {
      const report = await fetchReleaseReadiness();
      setReleaseReadiness(report);
      setReleaseReadinessError("");
    } catch (error) {
      setReleaseReadinessError(error instanceof Error ? error.message : "Release readiness failed");
    }
  }

  async function refreshPostRunReview() {
    try {
      const report = await fetchPostRunReview();
      setPostRunReview(report);
      setPostRunReviewError("");
    } catch (error) {
      setPostRunReviewError(error instanceof Error ? error.message : "Post-run review failed");
    }
  }

  async function refreshSessionReport() {
    try {
      const report = await fetchSessionReport("24h");
      setSessionReport(report);
      setSessionReportError("");
    } catch (error) {
      setSessionReportError(error instanceof Error ? error.message : "Session report failed");
    }
  }

  async function refreshEvidenceModeSeparation() {
    try {
      const report = await fetchEvidenceModeSeparation();
      setEvidenceModeSeparation(report);
      setEvidenceModeSeparationError("");
    } catch (error) {
      setEvidenceModeSeparationError(error instanceof Error ? error.message : "Evidence mode separation failed");
    }
  }

  async function refreshOperatorLogs() {
    try {
      const report = await fetchOperatorLogs("24h", "", "", 200);
      setOperatorLogs(report);
      setOperatorLogsError("");
    } catch (error) {
      setOperatorLogsError(error instanceof Error ? error.message : "Operator logs failed");
    }
  }

  async function refreshOutcomeExplanations() {
    try {
      const report = await fetchOutcomeExplanations("24h", 80);
      setOutcomeExplanations(report);
      setOutcomeExplanationsError("");
    } catch (error) {
      setOutcomeExplanationsError(error instanceof Error ? error.message : "Outcome explanations failed");
    }
  }

  async function refreshSourceParserReplay() {
    try {
      const report = await fetchSourceParserReplay(120);
      setSourceParserReplay(report);
      setSourceParserReplayError("");
    } catch (error) {
      setSourceParserReplayError(error instanceof Error ? error.message : "Source parser replay failed");
    }
  }

  async function refreshSolanaLogsVerification() {
    try {
      const report = await fetchSolanaLogsVerification(500);
      setSolanaLogsVerification(report);
      setSolanaLogsVerificationError("");
    } catch (error) {
      setSolanaLogsVerificationError(error instanceof Error ? error.message : "Solana logs verification failed");
    }
  }

  async function refreshSourceSoakAcceptance() {
    try {
      const report = await fetchSourceSoakAcceptance(500);
      setSourceSoakAcceptance(report);
      setSourceSoakError("");
    } catch (error) {
      setSourceSoakError(error instanceof Error ? error.message : "Source soak acceptance failed");
    }
  }

  async function recordSourceSoak() {
    setSourceSoakBusy(true);
    try {
      const report = await recordSourceSoakSnapshot(500);
      setSourceSoakAcceptance(report);
      setSourceSoakError("");
      await onRefresh();
    } catch (error) {
      setSourceSoakError(error instanceof Error ? error.message : "Source soak snapshot failed");
    } finally {
      setSourceSoakBusy(false);
    }
  }

  async function markIncidentReviewed(auditId: string) {
    setReviewingIncidentAuditId(auditId);
    try {
      await recordIncidentExportReview(auditId, {
        exported: true,
        reviewed: true,
        note: "Incident bundle exported and reviewed from Data workspace.",
      });
      setPostRunReviewError("");
      await Promise.all([refreshPostRunReview(), refreshSessionReport()]);
    } catch (error) {
      setPostRunReviewError(error instanceof Error ? error.message : "Incident review failed");
    } finally {
      setReviewingIncidentAuditId("");
    }
  }

  async function recordReleaseVerifier() {
    setReleaseVerificationBusy(true);
    try {
      await recordReleaseVerification({
        app_version: releaseReadiness?.app_version,
        verify_passed: true,
        diff_reviewed: true,
        docs_reviewed: true,
        note: "Local verification, git diff, and release docs reviewed from Data workspace.",
      });
      setReleaseReadinessError("");
      await refreshReleaseReadiness();
    } catch (error) {
      setReleaseReadinessError(error instanceof Error ? error.message : "Release verification failed");
    } finally {
      setReleaseVerificationBusy(false);
    }
  }

  React.useEffect(() => {
    void refreshPilotReadiness();
    void refreshManualLiveProof();
    void refreshPostPilotReview();
    void refreshSetupReadiness();
    void refreshReleaseReadiness();
    void refreshPostRunReview();
    void refreshSessionReport();
    void refreshEvidenceModeSeparation();
    void refreshOperatorLogs();
    void refreshOutcomeExplanations();
    void refreshSourceParserReplay();
    void refreshSolanaLogsVerification();
    void refreshSourceSoakAcceptance();
  }, []);

  async function refreshAll() {
    await Promise.all([onRefresh(), refreshPilotReadiness(), refreshManualLiveProof(), refreshPostPilotReview(), refreshSetupReadiness(), refreshReleaseReadiness(), refreshPostRunReview(), refreshSessionReport(), refreshEvidenceModeSeparation(), refreshOperatorLogs(), refreshOutcomeExplanations(), refreshSourceParserReplay(), refreshSolanaLogsVerification(), refreshSourceSoakAcceptance()]);
  }

  function downloadSourceEventBundle() {
    const artifact = {
      artifact_type: "cryptoarc_source_event_bundle",
      format_version: 1,
      created_at: new Date().toISOString(),
      filters: {
        status: sourceEventStatusFilter || null,
        source: sourceEventSourceFilter || null,
        event_kind: sourceEventKindFilter || null,
        parser_result: sourceEventParserFilter || null,
        mint: sourceEventMintFilter || null
      },
      source_health: sourceHealth,
      events: filteredSourceEvents
    };
    const blob = new Blob([JSON.stringify(artifact, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `cryptoarc-source-events-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function downloadBackupArtifact() {
    setRestoreMessage("");
    const result = await createBackupArtifact();
    const blob = new Blob([JSON.stringify(result.artifact, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = result.filename;
    anchor.click();
    URL.revokeObjectURL(url);
    setRestoreMessage(`Backup artifact downloaded as ${result.filename}.`);
    await onRefresh();
  }

  async function handleRestoreFile(file: File | null) {
    if (!file) return;
    setRestoreBusy(true);
    setRestoreMessage("");
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as Record<string, unknown>;
      const preview = await previewRestoreArtifact(parsed);
      setRestoreArtifact(parsed);
      setRestorePreview(preview);
      setRestoreFileName(file.name);
    } catch (error) {
      setRestorePreview(null);
      setRestoreArtifact(null);
      setRestoreMessage(error instanceof Error ? error.message : "Restore preview failed");
    } finally {
      setRestoreBusy(false);
      if (restoreInputRef.current) restoreInputRef.current.value = "";
    }
  }

  async function confirmRestore() {
    if (!restoreArtifact) return;
    setRestoreBusy(true);
    setRestoreMessage("");
    try {
      const result = await confirmRestoreArtifact(restoreArtifact);
      setRestorePreview(result);
      setRestoreMessage("Restore completed. Review migration/runtime status before trading.");
      await onRefresh();
    } catch (error) {
      setRestoreMessage(error instanceof Error ? error.message : "Restore failed");
    } finally {
      setRestoreBusy(false);
    }
  }

  async function runRestoreDrill() {
    setRestoreBusy(true);
    setRestoreMessage("");
    try {
      const result = await runRestoreSmokeTest();
      setRestoreSmokeTest(result);
      setRestoreMessage(result.passed ? "Restore smoke test passed." : "Restore smoke test needs review.");
      await onRefresh();
    } catch (error) {
      setRestoreMessage(error instanceof Error ? error.message : "Restore smoke test failed");
    } finally {
      setRestoreBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Data & Intelligence" 
        description="Core signal storage, audit logs, and system maintenance."
        className="mb-6 p-6"
      >
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={refreshAll}>
            <RotateCcw size={14} className="mr-2" />
            Refresh
          </Button>
          <Button variant="primary" size="sm" onClick={() => backupDatabase()}>
            <Save size={14} className="mr-2" />
            Backup Database
          </Button>
          <Button variant="secondary" size="sm" onClick={downloadBackupArtifact}>
            <Download size={14} className="mr-2" />
            Backup Artifact
          </Button>
          <Button variant="secondary" size="sm" onClick={onRecoverPaperPositions} disabled={loadingCore}>
            <RotateCcw size={14} className="mr-2" />
            Recover Paper
          </Button>
          <Button variant="secondary" size="sm" onClick={() => downloadExport(sessionReportExportUrl("24h"), "cryptoarc-session-report.json")}>
            <Download size={14} className="mr-2" />
            Session Report
          </Button>
          <Button variant="secondary" size="sm" onClick={() => downloadExport(pilotReadinessExportUrl(), "cryptoarc-pilot-readiness.json")}>
            <Download size={14} className="mr-2" />
            Pilot Gate
          </Button>
          <Button variant="secondary" size="sm" onClick={() => downloadExport(postRunReviewExportUrl("24h"), "cryptoarc-post-run-review.json")}>
            <Download size={14} className="mr-2" />
            Post-Run Review
          </Button>
          <Button variant="secondary" size="sm" onClick={() => downloadExport(releaseReadinessExportUrl(), "cryptoarc-release-readiness.json")}>
            <Download size={14} className="mr-2" />
            Release Gate
          </Button>
        </div>
      </PageHeader>

      {/* High-Density Metrics Grid */}
      <Card id="pilot-gate-panel" className="p-4" hover={false}>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
          <DataMetric label="Tokens" value={summary?.tokens ?? 0} loading={!summary} />
          <DataMetric label="Audit" value={summary?.events ?? 0} loading={!summary} />
          <DataMetric label="Signals" value={summary?.source_events ?? 0} loading={!summary} />
          <DataMetric label="Trades" value={summary?.trades ?? 0} loading={!summary} />
          <DataMetric label="Decisions" value={summary?.strategy_decisions ?? 0} loading={!summary} />
          <DataMetric label="Prices" value={summary?.price_observations ?? 0} loading={!summary} />
          <DataMetric label="Readiness" value={`${readinessStatus?.score ?? 0}%`} color="text-amber-500" loading={!readinessStatus} />
          <DataMetric label="Integrity" value={`${dataIntegrity?.score ?? 0}%`} color="text-emerald-500" loading={!dataIntegrity} />
          <DataMetric label="Health" value={`${sourceHealth?.health_score ?? 0}% ${sourceHealth?.status_message ? `| ${sourceHealth.status_message}` : ""}`} color={sourceHealthTone} loading={!sourceHealth} />
          <DataMetric label="Trust" value={sourceHealth?.trust_state ?? "unknown"} color={sourceTrustTone} loading={!sourceHealth} />
          <DataMetric label="RPC" value={solanaStatus?.health ?? "unknown"} color={solanaStatus?.health === "ok" ? "text-emerald-500" : "text-rose-500"} loading={!solanaStatus} />
          <DataMetric label="Watchdog" value={watchdogStatus?.status ?? "unknown"} loading={!watchdogStatus} />
          <DataMetric label="Live Reqs" value={liveRequests.length} color="text-rose-500" loading={!summary && !liveRequests.length} />
          <DataMetric label="Migrations" value={`${opsMonitoring?.schema?.current_version ?? 0}/${opsMonitoring?.schema?.expected_version ?? 0}`} loading={!opsMonitoring?.schema} />
          <DataMetric label="Restore Log" value={summary?.backup_restore_history ?? 0} loading={!summary} />
          <DataMetric label="Soak Snapshots" value={summary?.source_soak_history ?? 0} loading={!summary} />
        </div>
      </Card>

      <Card id="setup-checklist-panel" className="p-4" hover={false}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
                <Gauge size={14} />
                First-Run Setup Wizard
              </h3>
              <Badge variant={setupReadiness?.ready_for_paper ? "success" : "warning"}>{setupReadiness?.status ?? "loading"}</Badge>
              {setupReadiness?.generated_at ? <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-600">{new Date(setupReadiness.generated_at).toLocaleTimeString()}</span> : null}
            </div>
            {setupReadiness ? (
              <div className="space-y-2">
                <p className="text-xs text-zinc-400">{setupReadiness.operator_action}</p>
                <div className="space-y-2 rounded-xl border border-white/5 bg-black/20 p-3">
                  <div className="flex items-center justify-between gap-3 text-[11px]">
                    <span className="font-black uppercase tracking-widest text-zinc-500">{setupWizard.completed}/{setupWizard.stages.length} stages ready</span>
                    <span className={cn("font-black", setupFailedGates ? "text-rose-400" : setupWarningGates ? "text-amber-300" : "text-emerald-400")}>{setupWizard.progressPct}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-white/5">
                    <div className={cn("h-full rounded-full", setupFailedGates ? "bg-rose-500" : setupWarningGates ? "bg-amber-400" : "bg-emerald-500")} style={{ width: `${setupWizard.progressPct}%` }} />
                  </div>
                  <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-6">
                    {setupWizard.stages.map((stage) => {
                      const gateAction = stage.gate ? setupGateAction(stage.gate.id) : { href: "#system-audit-log", label: "Review" };
                      return (
                        <a key={stage.id} href={gateAction.href} className={cn("group rounded-lg border p-2 transition-colors", stage.status === "pass" ? "border-emerald-500/20 bg-emerald-500/10" : stage.status === "fail" ? "border-rose-500/20 bg-rose-500/10" : stage.status === "warn" ? "border-amber-500/20 bg-amber-500/10" : "border-white/5 bg-white/[0.03]")}>
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-[10px] font-black uppercase tracking-widest text-zinc-300">{stage.label}</span>
                            <ChevronRight size={12} className="shrink-0 text-zinc-500 transition-transform group-hover:translate-x-0.5" />
                          </div>
                          <div className={cn("mt-1 text-[10px] font-black uppercase tracking-wider", stage.status === "pass" ? "text-emerald-300" : stage.status === "fail" ? "text-rose-300" : stage.status === "warn" ? "text-amber-200" : "text-zinc-500")}>{stage.status}</div>
                        </a>
                      );
                    })}
                  </div>
                  {setupWizard.active?.gate ? (
                    <div className="rounded-lg border border-white/5 bg-white/[0.03] p-3 text-xs">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-black uppercase tracking-wider text-white">Current step: {setupWizard.active.label}</span>
                        <a className="text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" href={setupGateAction(setupWizard.active.gate.id).href}>{setupGateAction(setupWizard.active.gate.id).label}</a>
                      </div>
                      <p className="mt-1 text-zinc-400">{setupWizard.active.gate.reason}</p>
                    </div>
                  ) : null}
                </div>
                <div className="grid grid-cols-3 gap-2 sm:max-w-md">
                  <DataMetric label="Ready" value={setupPassedGates} color="text-emerald-400" />
                  <DataMetric label="Warnings" value={setupWarningGates} color={setupWarningGates ? "text-amber-300" : "text-emerald-400"} />
                  <DataMetric label="Blocked" value={setupFailedGates} color={setupFailedGates ? "text-rose-400" : "text-emerald-400"} />
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <Skeleton className="h-4 w-72" />
                <Skeleton className="h-12 w-full max-w-md" />
              </div>
            )}
            {setupReadinessError ? <p className="mt-2 text-xs text-rose-300">{setupReadinessError}</p> : null}
          </div>
          <div className="w-full max-w-xl rounded-xl border border-white/5 bg-black/20 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Next actions</span>
              <button type="button" className="text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(setupReadinessExportUrl(), "cryptoarc-setup-readiness.json")}>Export</button>
            </div>
            <div className="space-y-2">
              {setupReadiness?.gates.filter((gate) => gate.status !== "pass").slice(0, 4).map((gate) => {
                const action = setupGateAction(gate.id);
                const tone = gate.status === "fail" ? "border-rose-500/20 bg-rose-500/10 text-rose-100" : "border-amber-500/20 bg-amber-500/10 text-amber-100";
                return (
                  <div key={gate.id} className={cn("rounded-lg border p-2 text-xs", tone)}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-black uppercase tracking-wider">{gate.label}</span>
                      <a className="text-[10px] font-black uppercase tracking-widest text-white/80 hover:text-white" href={action.href}>{action.label}</a>
                    </div>
                    <p className="mt-1 opacity-80">{gate.reason}</p>
                  </div>
                );
              })}
              {setupActionItems.map((item) => (
                <div key={item} className="rounded-lg border border-white/5 bg-white/[0.03] p-2 text-xs text-zinc-300">{item}</div>
              ))}
              {setupReadiness && !setupReadiness.gates.some((gate) => gate.status !== "pass") ? <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs text-emerald-100">First-run setup is clean for paper monitoring.</div> : null}
              {!setupReadiness ? <Skeleton className="h-16 w-full" /> : null}
            </div>
            <div className="mt-3 rounded-lg border border-white/5 bg-white/[0.03] p-3 text-xs">
              <div className="flex items-center justify-between gap-3">
                <span className="font-black uppercase tracking-widest text-zinc-400">Manual-live proof</span>
                <div className="flex items-center gap-3">
                  <Badge variant={manualLiveProof?.qualified ? "success" : "warning"}>{manualLiveProof?.status ?? "loading"}</Badge>
                  <button type="button" className="text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(manualLiveProofExportUrl(), "cryptoarc-manual-live-proof.json")}>Export</button>
                </div>
              </div>
              <p className="mt-2 text-zinc-400">{manualLiveProof?.operator_action ?? "Loading read-only proof status."}</p>
              {manualLiveProof?.blockers?.length ? <p className="mt-1 text-amber-300">{manualLiveProof.blockers.length} blocker(s); no authority changed.</p> : null}
              {manualLiveProofError ? <p className="mt-1 text-rose-300">{manualLiveProofError}</p> : null}
            </div>
          </div>
        </div>
      </Card>

      <Card id="release-readiness-panel" className="p-4" hover={false}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
                <Shield size={14} />
                Release Readiness
              </h3>
              <Badge variant={releaseReadiness?.ready ? "success" : releaseReadiness?.status === "blocked" ? "danger" : "warning"}>{releaseReadiness?.status ?? "loading"}</Badge>
              {releaseReadiness?.generated_at ? <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-600">{new Date(releaseReadiness.generated_at).toLocaleTimeString()}</span> : null}
            </div>
            {releaseReadiness ? (
              <div className="space-y-2">
                <p className="text-xs text-zinc-400">{releaseReadiness.operator_action}</p>
                <div className="grid grid-cols-4 gap-2 sm:max-w-xl">
                  <DataMetric label="Version" value={releaseReadiness.app_version} />
                  <DataMetric label="Passed" value={releasePassedGates} color="text-emerald-400" />
                  <DataMetric label="Warnings" value={releaseWarningGates} color={releaseWarningGates ? "text-amber-300" : "text-emerald-400"} />
                  <DataMetric label="Blocked" value={releaseFailedGates} color={releaseFailedGates ? "text-rose-400" : "text-emerald-400"} />
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <Skeleton className="h-4 w-72" />
                <Skeleton className="h-12 w-full max-w-md" />
              </div>
            )}
            {releaseReadinessError ? <p className="mt-2 text-xs text-rose-300">{releaseReadinessError}</p> : null}
          </div>
          <div className="w-full max-w-xl rounded-xl border border-white/5 bg-black/20 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Release actions</span>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={!releaseReadiness || releaseVerificationBusy}
                  onClick={() => void recordReleaseVerifier()}
                >
                  {releaseVerificationBusy ? "Recording" : "Record Verified"}
                </button>
                <button type="button" className="text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(releaseReadinessExportUrl(), "cryptoarc-release-readiness.json")}>Export</button>
              </div>
            </div>
            <div className="space-y-2">
              {releaseReadiness?.gates.filter((gate) => gate.status !== "pass").slice(0, 4).map((gate) => {
                const tone = gate.status === "fail" ? "border-rose-500/20 bg-rose-500/10 text-rose-100" : "border-amber-500/20 bg-amber-500/10 text-amber-100";
                return (
                  <div key={gate.id} className={cn("rounded-lg border p-2 text-xs", tone)}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-black uppercase tracking-wider">{gate.label}</span>
                      <span className="text-[10px] font-black uppercase tracking-widest opacity-80">{gate.status}</span>
                    </div>
                    <p className="mt-1 opacity-80">{gate.reason}</p>
                  </div>
                );
              })}
              {releaseActionItems.map((item) => (
                <div key={item} className="rounded-lg border border-white/5 bg-white/[0.03] p-2 text-xs text-zinc-300">{item}</div>
              ))}
              {releaseReadiness && !releaseReadiness.gates.some((gate) => gate.status !== "pass") ? <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs text-emerald-100">Release gate is clear after the verifier result is recorded.</div> : null}
              {!releaseReadiness ? <Skeleton className="h-16 w-full" /> : null}
            </div>
          </div>
        </div>
      </Card>

      <Card id="session-summary-panel" className="p-4" hover={false}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
                <Clock size={14} />
                Session Summary
              </h3>
              <Badge variant={openRisk?.status === "clear" ? "success" : openRisk?.status === "blocked" ? "danger" : "warning"}>{openRisk?.status ?? "loading"}</Badge>
              {sessionReport?.generated_at ? <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-600">{new Date(sessionReport.generated_at).toLocaleTimeString()}</span> : null}
            </div>
            {sessionReport ? (
              <div className="space-y-2">
                <p className="text-xs text-zinc-400">{openRisk?.operator_action ?? "Review current session risk before ending the run."}</p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <DataMetric label="Open Pos" value={openRisk?.open_positions ?? 0} color={(openRisk?.open_positions ?? 0) ? "text-amber-300" : "text-emerald-400"} />
                  <DataMetric label="Exposure" value={`${(openRisk?.cost_basis_sol ?? 0).toFixed(4)} SOL`} color={(openRisk?.exposure_ratio ?? 0) >= 0.8 ? "text-rose-400" : "text-zinc-200"} />
                  <DataMetric label="Live PnL" value={`${(openRisk?.total_live_pnl_sol ?? 0).toFixed(4)} SOL`} color={(openRisk?.total_live_pnl_sol ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"} />
                  <DataMetric label="Unresolved" value={openRisk?.unresolved_audits ?? 0} color={(openRisk?.unresolved_audits ?? 0) ? "text-rose-400" : "text-emerald-400"} />
                </div>
                <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
                  {Object.entries(sessionReport.mode_comparison ?? {}).map(([mode, row]) => (
                    <div key={mode} className="rounded-lg border border-white/5 bg-black/20 p-2 text-[10px]">
                      <span className="block font-black uppercase tracking-widest text-zinc-500">{row.mode}</span>
                      <span className={cn("mt-1 block font-black", row.pnl_sol >= 0 ? "text-emerald-400" : "text-rose-400")}>{row.pnl_sol.toFixed(4)} SOL</span>
                      <span className="mt-1 block truncate text-zinc-600">{row.samples} samples / {row.confidence}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <Skeleton className="h-4 w-72" />
                <Skeleton className="h-12 w-full max-w-xl" />
              </div>
            )}
            {sessionReportError ? <p className="mt-2 text-xs text-rose-300">{sessionReportError}</p> : null}
          </div>
          <div className="w-full max-w-xl rounded-xl border border-white/5 bg-black/20 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Open risk actions</span>
              <button type="button" className="text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(sessionReportExportUrl("24h"), "cryptoarc-session-report.json")}>Export</button>
            </div>
            <div className="space-y-2">
              {openRisk?.blockers.slice(0, 3).map((item) => (
                <div key={item} className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-2 text-xs text-rose-100">{item}</div>
              ))}
              {openRisk?.warnings.slice(0, 3).map((item) => (
                <div key={item} className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-100">{item}</div>
              ))}
              {openRisk?.action_items.slice(0, 4).map((item) => (
                <div key={item} className="rounded-lg border border-white/5 bg-white/[0.03] p-2 text-xs text-zinc-300">{item}</div>
              ))}
              {sessionReport?.source_quality ? (
                <div className={cn("rounded-lg border p-2 text-xs", sessionReport.source_quality.status === "clear" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-100" : sessionReport.source_quality.status === "unknown" ? "border-zinc-500/20 bg-white/[0.03] text-zinc-300" : "border-amber-500/20 bg-amber-500/10 text-amber-100")}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-black uppercase tracking-wider">Source quality / {sessionReport.source_quality.status}</span>
                    <span className="font-mono">{Math.round(sessionReport.source_quality.normalized_ratio * 100)}%</span>
                  </div>
                  <p className="mt-1 opacity-80">{sessionReport.source_quality.operator_action}</p>
                </div>
              ) : null}
              {sessionReport && openRisk && !openRisk.blockers.length && !openRisk.warnings.length && !openRisk.action_items.length ? <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs text-emerald-100">No open risk actions for this session.</div> : null}
              {!sessionReport ? <Skeleton className="h-16 w-full" /> : null}
            </div>
          </div>
        </div>
      </Card>

      <Card id="evidence-mode-separation-panel" className="p-4" hover={false}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
                <FileText size={14} />
                Evidence Mode Separation
              </h3>
              <Badge variant={evidenceModeSeparation?.ready ? "success" : "warning"}>{evidenceModeSeparation?.status ?? "loading"}</Badge>
              {evidenceModeSeparation?.generated_at ? <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-600">{new Date(evidenceModeSeparation.generated_at).toLocaleTimeString()}</span> : null}
            </div>
            {evidenceModeSeparation ? (
              <div className="space-y-3">
                <p className="text-xs text-zinc-400">{evidenceModeSeparation.operator_action}</p>
                <div className="grid grid-cols-2 gap-2 xl:grid-cols-5">
                  {evidenceModeSeparation.modes.map((row) => (
                    <div key={row.mode} className={cn("rounded-lg border p-2 text-[10px]", row.status === "clear" ? "border-emerald-500/20 bg-emerald-500/10" : row.status === "review" ? "border-amber-500/20 bg-amber-500/10" : "border-white/5 bg-black/20")}>
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-black uppercase tracking-widest text-zinc-300">{row.label}</span>
                        <span className={cn("font-black uppercase", row.status === "clear" ? "text-emerald-300" : row.status === "review" ? "text-amber-200" : "text-zinc-500")}>{row.status}</span>
                      </div>
                      <div className={cn("mt-2 text-sm font-black", row.pnl_sol >= 0 ? "text-emerald-400" : "text-rose-400")}>{row.pnl_sol.toFixed(4)} SOL</div>
                      <div className="mt-1 text-zinc-500">{row.samples} samples{row.evaluated !== undefined ? ` / ${row.evaluated} evaluated` : ""}{row.submitted !== undefined ? ` / ${row.submitted} submitted` : ""}</div>
                      <div className="mt-2 text-zinc-400">{row.boundary}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <Skeleton className="h-4 w-72" />
                <Skeleton className="h-20 w-full" />
              </div>
            )}
            {evidenceModeSeparationError ? <p className="mt-2 text-xs text-rose-300">{evidenceModeSeparationError}</p> : null}
          </div>
          <div className="w-full max-w-xl rounded-xl border border-white/5 bg-black/20 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Mode boundaries</span>
              <button type="button" className="text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(evidenceModeSeparationExportUrl(), "cryptoarc-evidence-mode-separation.json")}>Export</button>
            </div>
            <div className="space-y-2">
              {evidenceModeSeparation?.contamination_warnings.slice(0, 4).map((warning) => (
                <div key={warning} className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-100">{warning}</div>
              ))}
              {evidenceModeSeparation?.modes.filter((row) => row.status !== "clear").slice(0, 4).map((row) => (
                <div key={row.mode} className="rounded-lg border border-white/5 bg-white/[0.03] p-2 text-xs text-zinc-300">
                  <span className="font-black uppercase tracking-wider text-white">{row.label}</span>
                  <p className="mt-1 text-zinc-400">{row.operator_action}</p>
                </div>
              ))}
              {evidenceModeSeparation?.ready && !evidenceModeSeparation.modes.some((row) => row.status !== "clear") ? <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs text-emerald-100">Paper, replay, shadow, manual live, and autonomous live evidence are separated.</div> : null}
              {!evidenceModeSeparation ? <Skeleton className="h-16 w-full" /> : null}
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-4" hover={false}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
                <Shield size={14} />
                Tiny Pilot Gate
              </h3>
              <Badge variant={pilotReadiness?.ready ? "success" : "warning"}>{pilotReadiness?.status ?? "loading"}</Badge>
              {pilotReadiness?.generated_at ? <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-600">{new Date(pilotReadiness.generated_at).toLocaleTimeString()}</span> : null}
            </div>
            {pilotReadiness ? (
              <div className="space-y-3">
                <p className="text-xs text-zinc-400">{pilotReadiness.operator_action}</p>
                <div className="grid grid-cols-3 gap-2 sm:max-w-md">
                  <DataMetric label="Passed" value={pilotPassedGates} color="text-emerald-400" />
                  <DataMetric label="Blocked" value={pilotFailedGates} color={pilotFailedGates ? "text-rose-400" : "text-emerald-400"} />
                  <DataMetric label="Blockers" value={pilotReadiness.blockers.length} color={pilotReadiness.blockers.length ? "text-amber-300" : "text-emerald-400"} />
                </div>
                {pilotRunbook.length ? (
                  <div className="grid gap-2 sm:grid-cols-5">
                    {pilotRunbook.map((stage) => (
                      <div key={stage.id} className={cn("rounded-lg border p-2 text-[10px]", stage.status === "ready" ? "border-emerald-500/20 bg-emerald-500/10" : "border-amber-500/20 bg-amber-500/10")}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-black uppercase tracking-widest text-zinc-200">{stage.label}</span>
                          <span className={cn("font-black uppercase", stage.status === "ready" ? "text-emerald-300" : "text-amber-200")}>{stage.status}</span>
                        </div>
                        <p className="mt-1 line-clamp-2 text-zinc-400">{stage.operator_action}</p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="space-y-2">
                <Skeleton className="h-4 w-72" />
                <Skeleton className="h-12 w-full max-w-md" />
              </div>
            )}
            {pilotReadinessError ? <p className="mt-2 text-xs text-rose-300">{pilotReadinessError}</p> : null}
          </div>
          <div className="w-full max-w-xl rounded-xl border border-white/5 bg-black/20 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Runbook and gates</span>
              <button type="button" className="text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(pilotReadinessExportUrl(), "cryptoarc-pilot-readiness.json")}>Export</button>
            </div>
            <div className="space-y-2">
              {pilotRunbook.slice(0, 5).map((stage) => (
                <div key={stage.id} className={cn("rounded-lg border p-2 text-xs", stage.status === "ready" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-100" : "border-amber-500/20 bg-amber-500/10 text-amber-100")}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-black uppercase tracking-wider">{stage.label}</span>
                    <span className="text-[10px] font-black uppercase tracking-widest opacity-80">{stage.blockers.length ? `${stage.blockers.length} blockers` : stage.status}</span>
                  </div>
                  <div className="mt-1 space-y-1">
                    {stage.actions.slice(0, 2).map((action) => (
                      <p key={`${stage.id}-${action.label}`} className="text-[11px] opacity-80">
                        {action.command ? <span className="font-mono">{action.command}</span> : action.label}
                      </p>
                    ))}
                  </div>
                </div>
              ))}
              {pilotFailedGateItems.map((gate) => {
                const action = pilotGateAction(gate.id);
                return (
                  <div key={gate.id} className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-100">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-black uppercase tracking-wider">{gate.label}</span>
                      <a className="text-[10px] font-black uppercase tracking-widest text-amber-200 hover:text-white" href={action.href}>{action.label}</a>
                    </div>
                    <p className="mt-1 text-amber-100/80">{action.detail}</p>
                    <p className="mt-1 text-amber-100/70">{gate.reason}</p>
                  </div>
                );
              })}
              {pilotReadiness && !pilotFailedGateItems.length ? <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs text-emerald-100">All tiny pilot gates are clear.</div> : null}
              {!pilotReadiness ? <Skeleton className="h-16 w-full" /> : null}
            </div>
          </div>
        </div>
      </Card>

      <Card id="post-run-review-panel" className="p-4" hover={false}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h3 className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-zinc-500">
                <Activity size={14} />
                Post-Run Review
              </h3>
              <Badge variant={postRunReview?.ready ? "success" : "warning"}>{postRunReview?.status ?? "loading"}</Badge>
              {postRunReview?.generated_at ? <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-600">{new Date(postRunReview.generated_at).toLocaleTimeString()}</span> : null}
            </div>
            {postRunReview ? (
              <div className="space-y-2">
                <p className="text-xs text-zinc-400">{postRunReview.operator_action}</p>
                <div className="grid grid-cols-4 gap-2 sm:max-w-xl">
                  <DataMetric label="Audits" value={postRunReview.summary.audits} />
                  <DataMetric label="Unresolved" value={postRunReview.summary.unresolved} color={postRunReview.summary.unresolved ? "text-rose-400" : "text-emerald-400"} />
                  <DataMetric label="Review" value={postRunReview.summary.needs_review} color={postRunReview.summary.needs_review ? "text-amber-300" : "text-emerald-400"} />
                  <DataMetric label="Pending" value={postRunReview.summary.pending_incident_exports} color={postRunReview.summary.pending_incident_exports ? "text-amber-300" : "text-emerald-400"} />
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <Skeleton className="h-4 w-72" />
                <Skeleton className="h-12 w-full max-w-md" />
              </div>
            )}
            {postRunReviewError ? <p className="mt-2 text-xs text-rose-300">{postRunReviewError}</p> : null}
            <div className="mt-3 rounded-lg border border-white/5 bg-white/[0.03] p-3 text-xs">
              <div className="flex items-center justify-between gap-3">
                <span className="font-black uppercase tracking-widest text-zinc-400">Post-pilot decision</span>
                <div className="flex items-center gap-3">
                  <Badge variant={postPilotReview?.clear ? "success" : "warning"}>{postPilotReview?.status ?? "loading"}</Badge>
                  <button type="button" className="text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(postPilotReviewExportUrl(), "cryptoarc-post-pilot-review.json")}>Export</button>
                </div>
              </div>
              <p className="mt-2 text-zinc-400">{postPilotReview?.operator_action ?? "Waiting for a closed attended pilot."}</p>
              <p className="mt-1 text-zinc-500">{postPilotReview?.decision ? `Recorded: ${postPilotReview.decision.decision}; no scaling applied.` : "No operator decision recorded."}</p>
              {postPilotReviewError ? <p className="mt-1 text-rose-300">{postPilotReviewError}</p> : null}
            </div>
          </div>
          <div className="w-full max-w-xl rounded-xl border border-white/5 bg-black/20 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Incident review</span>
              <button type="button" className="text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(postRunReviewExportUrl("24h"), "cryptoarc-post-run-review.json")}>Export</button>
            </div>
            <div className="space-y-2">
              {postRunReview?.incident_exports.slice(0, 3).map((item) => (
                <div key={item.audit_id} className={cn("rounded-lg border p-2 text-xs", item.reviewed ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-100" : "border-amber-500/20 bg-amber-500/10 text-amber-100")}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-black uppercase tracking-wider">{item.action} / {item.final_status}</span>
                    <div className="flex flex-wrap items-center gap-2">
                      <button type="button" className={cn("text-[10px] font-black uppercase tracking-widest hover:text-white", item.reviewed ? "text-emerald-200" : "text-amber-200")} onClick={() => downloadExport(incidentExportUrl(item.audit_id), "cryptoarc-incident-export.json")}>Incident Export</button>
                      {item.reviewed ? (
                        <span className="text-[10px] font-black uppercase tracking-widest text-emerald-200">Reviewed</span>
                      ) : (
                        <button
                          type="button"
                          className="text-[10px] font-black uppercase tracking-widest text-amber-200 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                          disabled={reviewingIncidentAuditId === item.audit_id}
                          onClick={() => void markIncidentReviewed(item.audit_id)}
                        >
                          {reviewingIncidentAuditId === item.audit_id ? "Recording" : "Mark Reviewed"}
                        </button>
                      )}
                    </div>
                  </div>
                  <p className={cn("mt-1 truncate", item.reviewed ? "text-emerald-100/80" : "text-amber-100/80")}>{item.mint}</p>
                  <p className={cn("mt-1", item.reviewed ? "text-emerald-100/70" : "text-amber-100/70")}>{item.reviewed ? item.review_note || "Incident bundle has been exported and reviewed." : item.reason}</p>
                </div>
              ))}
              {postRunChecklistIssues.map((item) => (
                <div key={item.id} className="rounded-lg border border-white/5 bg-white/[0.03] p-2 text-xs text-zinc-300">
                  <span className="font-black uppercase tracking-wider text-white">{item.label}</span>
                  <p className="mt-1 text-zinc-400">{item.reason}</p>
                </div>
              ))}
              {postRunReview && !postRunReview.incident_exports.length && !postRunChecklistIssues.length ? <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs text-emerald-100">Post-run review is clear for the selected timeframe.</div> : null}
              {!postRunReview ? <Skeleton className="h-16 w-full" /> : null}
            </div>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left Column: Logs & Events */}
        <div className="space-y-6 lg:col-span-2">
          <Card id="source-parser-replay-panel" className="p-4" hover={false}>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Activity size={14} />
                Parser Replay Evidence
              </h3>
              <div className="flex items-center gap-2">
                <Badge variant={(sourceParserReplay?.summary.normalization_rate ?? 0) >= 0.75 ? "success" : (sourceParserReplay?.summary.normalization_rate ?? 0) >= 0.5 ? "warning" : "danger"}>
                  {Math.round((sourceParserReplay?.summary.normalization_rate ?? 0) * 100)}%
                </Badge>
                <Button variant="secondary" size="sm" onClick={() => downloadExport(sourceParserReplayExportUrl(120), "cryptoarc-parser-replay.json")}>
                  <Download size={14} className="mr-2" />
                  Export
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              <DataMetric label="Raw Events" value={sourceParserReplay?.summary.raw_events ?? 0} loading={!sourceParserReplay && !sourceParserReplayError} />
              <DataMetric label="Normalized" value={sourceParserReplay?.summary.normalized ?? 0} color="text-emerald-400" loading={!sourceParserReplay && !sourceParserReplayError} />
              <DataMetric label="Failures" value={sourceParserReplay?.summary.normalization_failures ?? 0} color={(sourceParserReplay?.summary.normalization_failures ?? 0) ? "text-rose-400" : "text-emerald-400"} loading={!sourceParserReplay && !sourceParserReplayError} />
              <DataMetric label="Trades" value={sourceParserReplay?.summary.trade_events ?? 0} loading={!sourceParserReplay && !sourceParserReplayError} />
              <DataMetric label="Replay PnL" value={`${(sourceParserReplay?.dry_backtest.estimated_pnl_sol ?? 0).toFixed(4)} SOL`} color={(sourceParserReplay?.dry_backtest.estimated_pnl_sol ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"} loading={!sourceParserReplay && !sourceParserReplayError} />
            </div>
            <div className="mt-4 space-y-2">
              {sourceParserReplay?.failures.slice(0, 4).map((failure) => (
                <div key={failure.event_id} className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-[11px] text-amber-100">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-black uppercase tracking-wider">{failure.parser_result} / {failure.event_kind}</span>
                    <span className="font-mono text-amber-100/70">{failure.event_id}</span>
                  </div>
                  <p className="mt-1 text-amber-100/80">{failure.failure_reason || "Parser could not normalize this event."}</p>
                  <p className="mt-1 truncate font-mono text-amber-100/60" title={failure.mint || "missing mint"}>{failure.mint || "missing mint"}</p>
                </div>
              ))}
              {sourceParserReplay && !sourceParserReplay.failures.length ? <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-emerald-100">Recent parser replay has no launch normalization failures.</div> : null}
              {sourceParserReplayError ? <div className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-3 text-xs text-rose-100">{sourceParserReplayError}</div> : null}
            </div>
          </Card>

          <Card id="source-inspector" className="flex flex-col" hover={false}>
            <div className="flex flex-col gap-3 border-b border-white/5 p-4 lg:flex-row lg:items-center lg:justify-between">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Database size={14} />
                Source Event Inspector
              </h3>
              <div className="flex flex-wrap gap-2">
                <select
                  className="h-8 rounded-lg border border-white/10 bg-black/40 px-2 text-[11px] font-bold text-zinc-200"
                  value={sourceEventStatusFilter}
                  onChange={(event) => setSourceEventStatusFilter(event.target.value)}
                  aria-label="Source event status filter"
                >
                  <option value="">All statuses</option>
                  {sourceEventStatuses.map((status) => <option key={status} value={status}>{status}</option>)}
                </select>
                <select
                  className="h-8 rounded-lg border border-white/10 bg-black/40 px-2 text-[11px] font-bold text-zinc-200"
                  value={sourceEventSourceFilter}
                  onChange={(event) => setSourceEventSourceFilter(event.target.value)}
                  aria-label="Source event source filter"
                >
                  <option value="">All sources</option>
                  {sourceEventSources.map((source) => <option key={source} value={source}>{source}</option>)}
                </select>
                <select
                  className="h-8 rounded-lg border border-white/10 bg-black/40 px-2 text-[11px] font-bold text-zinc-200"
                  value={sourceEventKindFilter}
                  onChange={(event) => setSourceEventKindFilter(event.target.value)}
                  aria-label="Source event kind filter"
                >
                  <option value="">All kinds</option>
                  {sourceEventKinds.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
                </select>
                <select
                  className="h-8 rounded-lg border border-white/10 bg-black/40 px-2 text-[11px] font-bold text-zinc-200"
                  value={sourceEventParserFilter}
                  onChange={(event) => setSourceEventParserFilter(event.target.value)}
                  aria-label="Source event parser result filter"
                >
                  <option value="">All parser results</option>
                  {sourceEventParserResults.map((result) => <option key={result} value={result}>{result}</option>)}
                </select>
                <input
                  className="h-8 w-36 rounded-lg border border-white/10 bg-black/40 px-2 text-[11px] font-bold text-zinc-200 placeholder-zinc-600"
                  value={sourceEventMintFilter}
                  onChange={(event) => setSourceEventMintFilter(event.target.value)}
                  placeholder="Mint filter"
                  aria-label="Source event mint filter"
      />

      {workloadPressure?.status === "degraded_observability" ? (
        <div data-critical-projection="data" className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-[11px] text-amber-100">
          {workloadPressure.operator_action} Health, kill switch, positions, and alerts remain readable.
        </div>
      ) : null}
                <Button variant="secondary" size="sm" onClick={downloadSourceEventBundle} disabled={!filteredSourceEvents.length}>
                  <Download size={14} className="mr-2" />
                  Export Bundle
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 border-b border-white/5 p-4 sm:grid-cols-4">
              <DataMetric label="Loaded" value={sourceEvents.length} />
              <DataMetric label="Matched" value={filteredSourceEvents.length} />
              <DataMetric label="Unique Mints" value={new Set(filteredSourceEvents.map(sourceEventMint).filter(Boolean)).size} />
              <DataMetric label="Malformed" value={filteredSourceEvents.filter((event) => !sourceEventMint(event)).length} />
            </div>
            <div className="max-h-[360px] overflow-auto p-0 scrollbar-thin scrollbar-thumb-white/10">
              <table className="w-full min-w-[1040px] table-fixed border-separate border-spacing-0 text-left text-[11px]">
                <colgroup>
                  <col className="w-28" />
                  <col className="w-24" />
                  <col className="w-24" />
                  <col className="w-24" />
                  <col className="w-32" />
                  <col className="w-52" />
                  <col />
                </colgroup>
                <thead className="sticky top-0 z-20 bg-[#10121c] shadow-[0_1px_0_rgba(255,255,255,0.05)]">
                  <tr className="border-b border-white/5">
                    <th className="h-10 whitespace-nowrap bg-[#10121c] px-4 py-0 align-middle font-black text-zinc-600">Received</th>
                    <th className="h-10 whitespace-nowrap bg-[#10121c] px-4 py-0 align-middle font-black text-zinc-600">Source</th>
                    <th className="h-10 whitespace-nowrap bg-[#10121c] px-4 py-0 align-middle font-black text-zinc-600">Status</th>
                    <th className="h-10 whitespace-nowrap bg-[#10121c] px-4 py-0 align-middle font-black text-zinc-600">Kind</th>
                    <th className="h-10 whitespace-nowrap bg-[#10121c] px-4 py-0 align-middle font-black text-zinc-600">Parser</th>
                    <th className="h-10 whitespace-nowrap bg-[#10121c] px-4 py-0 align-middle font-black text-zinc-600">Mint</th>
                    <th className="h-10 whitespace-nowrap bg-[#10121c] px-4 py-0 align-middle font-black text-zinc-600">Message</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono">
                  {filteredSourceEvents.slice(0, 80).map((event) => {
                    const mint = sourceEventMint(event);
                    return (
                      <tr key={event.id} className="hover:bg-white/[0.02]">
                        <td className="align-top px-4 py-2 text-zinc-500">{new Date(event.received_at).toLocaleTimeString()}</td>
                        <td className="align-top px-4 py-2 text-zinc-300">{event.source}</td>
                        <td className="align-top px-4 py-2"><Badge variant={event.status === "normalized" ? "success" : event.status === "trade" ? "info" : "warning"}>{event.status}</Badge></td>
                        <td className="align-top px-4 py-2 text-zinc-400">{event.event_kind ?? "unknown"}</td>
                        <td className="align-top px-4 py-2 text-zinc-400">{event.parser_result ?? "unknown"}</td>
                        <td className="truncate align-top px-4 py-2 text-zinc-400" title={mint || "missing"}>{mint || "missing"}</td>
                        <td className="align-top px-4 py-2 text-zinc-400">{event.message || event.normalized_token_id || "raw source event"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {!filteredSourceEvents.length ? <p className="p-4 text-xs text-zinc-500">No source events match the current filters.</p> : null}
            </div>
          </Card>

          <Card id="system-audit-log" className="flex flex-col h-[500px]" hover={false}>
            <div className="flex items-center justify-between border-b border-white/5 p-4">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Bell size={14} />
                System Audit Log
              </h3>
              <Badge variant="info">{auditEvents.length} Events</Badge>
            </div>
            <div className="flex-1 overflow-auto p-0 scrollbar-thin scrollbar-thumb-white/10">
              <div className="min-w-[560px] text-[11px]">
                <div className="sticky top-0 z-10 grid h-10 grid-cols-[140px_88px_minmax(0,1fr)] border-b border-white/5 bg-[#10121c]">
                  <div className="flex items-center px-4 font-black text-zinc-600">Timestamp</div>
                  <div className="flex items-center px-4 font-black text-zinc-600">Level</div>
                  <div className="flex items-center px-4 font-black text-zinc-600">Message</div>
                </div>
                <div className="divide-y divide-white/5 font-mono">
                  {auditEvents.map((event) => (
                    <div key={event.id} className="grid min-h-10 grid-cols-[140px_88px_minmax(0,1fr)] hover:bg-white/[0.02]">
                      <div className="flex items-center whitespace-nowrap px-4 text-zinc-500">
                        {new Date(event.created_at).toLocaleTimeString()}
                      </div>
                      <div className="flex items-center px-4">
                        <span className={cn("inline-flex items-center rounded-md border px-2 py-1 text-[10px] font-black uppercase tracking-wider", auditLevelTone(event.level))}>
                          {event.level}
                        </span>
                      </div>
                      <div className="flex items-center px-4 py-2 text-zinc-300">{event.message}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          <Card id="outcome-explanations-panel" className="flex flex-col" hover={false}>
            <div className="flex items-center justify-between gap-3 border-b border-white/5 p-4">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Activity size={14} />
                Outcome Explanations
              </h3>
              <div className="flex items-center gap-2">
                <Badge variant="info">{outcomeExplanations?.summary.total ?? 0} Rows</Badge>
                <Button variant="secondary" size="sm" onClick={() => downloadExport(outcomeExplanationsExportUrl("24h", 80), "cryptoarc-outcomes.json")}>
                  <Download size={14} className="mr-2" />
                  Export
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 border-b border-white/5 p-4 sm:grid-cols-6">
              {["buy", "skip", "sell", "block", "override", "recovery"].map((type) => (
                <DataMetric key={type} label={type} value={outcomeExplanations?.summary.by_type[type] ?? 0} color={type === "block" ? "text-rose-400" : type === "override" || type === "recovery" ? "text-amber-300" : "text-zinc-200"} loading={!outcomeExplanations && !outcomeExplanationsError} />
              ))}
            </div>
            <div className="max-h-[360px] overflow-auto p-0 scrollbar-thin scrollbar-thumb-white/10">
              <div className="min-w-[720px] text-[11px]">
                <div className="sticky top-0 z-10 grid h-10 grid-cols-[120px_96px_120px_minmax(0,1.2fr)_minmax(0,1fr)] border-b border-white/5 bg-[#10121c]">
                  <div className="flex items-center px-4 font-black text-zinc-600">Time</div>
                  <div className="flex items-center px-4 font-black text-zinc-600">Type</div>
                  <div className="flex items-center px-4 font-black text-zinc-600">Subject</div>
                  <div className="flex items-center px-4 font-black text-zinc-600">Reason</div>
                  <div className="flex items-center px-4 font-black text-zinc-600">Action</div>
                </div>
                <div className="divide-y divide-white/5 font-mono">
                  {(outcomeExplanations?.outcomes ?? []).slice(0, 30).map((outcome) => (
                    <div key={outcome.id} className="grid min-h-12 grid-cols-[120px_96px_120px_minmax(0,1.2fr)_minmax(0,1fr)] hover:bg-white/[0.02]">
                      <div className="flex items-center whitespace-nowrap px-4 text-zinc-500">{new Date(outcome.at).toLocaleTimeString()}</div>
                      <div className="flex items-center px-4">
                        <Badge variant={outcomeTone(outcome.outcome_type)}>{outcome.outcome_type}</Badge>
                      </div>
                      <div className="flex min-w-0 items-center px-4 text-zinc-300">
                        <span className="truncate" title={outcome.mint || outcome.token_id}>{outcome.subject}</span>
                      </div>
                      <div className="flex min-w-0 items-center px-4 py-2 text-zinc-300">
                        <span className="truncate" title={outcome.reason}>{outcome.reason || outcome.status}</span>
                      </div>
                      <div className="flex min-w-0 items-center px-4 py-2 text-zinc-500">
                        <span className="truncate" title={outcome.recommended_action}>{outcome.recommended_action}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              {outcomeExplanationsError ? <p className="p-4 text-xs text-rose-300">{outcomeExplanationsError}</p> : null}
              {outcomeExplanations && !outcomeExplanations.outcomes.length ? <p className="p-4 text-xs text-zinc-500">No recent outcomes found for this timeframe.</p> : null}
            </div>
          </Card>

          <Card id="manual-live-requests" className="flex flex-col" hover={false}>
            <div className="flex items-center justify-between border-b border-white/5 p-4">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Target size={14} />
                Manual Live Requests
              </h3>
              <Badge variant="warning">{liveRequests.length} Requests</Badge>
            </div>
            <div className="max-h-[320px] overflow-auto p-0 scrollbar-thin scrollbar-thumb-white/10">
              <table className="min-w-full table-fixed border-collapse text-left text-[11px]">
                <colgroup>
                  <col className="w-28" />
                  <col className="w-20" />
                  <col className="w-24" />
                  <col className="w-24" />
                  <col />
                </colgroup>
                <thead className="sticky top-0 z-10 bg-[#10121c]">
                  <tr className="border-b border-white/5">
                    <th className="w-28 px-4 py-2 font-black text-zinc-600">Created</th>
                    <th className="w-20 px-4 py-2 font-black text-zinc-600">Action</th>
                    <th className="w-24 px-4 py-2 font-black text-zinc-600">Amount</th>
                    <th className="w-24 px-4 py-2 font-black text-zinc-600">Status</th>
                    <th className="px-4 py-2 font-black text-zinc-600 text-right">Review</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono">
                  {liveRequests.slice(0, 30).map((request) => (
                    <tr key={request.id} className="hover:bg-white/[0.02]">
                      <td className="px-4 py-2 text-zinc-500">{new Date(request.created_at).toLocaleTimeString()}</td>
                      <td className="px-4 py-2 text-zinc-300">{request.action}</td>
                      <td className="px-4 py-2 text-zinc-300">{request.amount_sol} SOL</td>
                      <td className="px-4 py-2"><Badge variant={request.status === "pending" ? "warning" : request.status === "rejected" ? "danger" : "success"}>{request.status}</Badge></td>
                      <td className="px-4 py-2 text-right">
                        {request.status === "pending" ? (
                          <div className="flex justify-end gap-2">
                            <Button variant="secondary" size="sm" onClick={() => onReviewLiveRequest(request.id, "reviewed")}>Review</Button>
                            <Button variant="danger" size="sm" onClick={() => onReviewLiveRequest(request.id, "rejected")}>Reject</Button>
                          </div>
                        ) : <span className="text-zinc-600">closed</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!liveRequests.length ? <p className="p-4 text-xs text-zinc-500">No manual live requests recorded.</p> : null}
            </div>
          </Card>

          <Card id="live-audit-panel" className="flex flex-col" hover={false}>
            <div className="flex items-center justify-between border-b border-white/5 p-4">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Shield size={14} />
                Live Execution Audit
              </h3>
              <Badge variant="info">{liveAudit.length} Rows</Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 border-b border-white/5 p-4 sm:grid-cols-4">
              <DataMetric label="Unresolved" value={opsMonitoring?.live_recovery?.unresolved_audits ?? 0} color={(opsMonitoring?.live_recovery?.unresolved_audits ?? 0) ? "text-rose-400" : "text-emerald-400"} />
              <DataMetric label="Last Checked" value={String(liveRecoverySummary.checked ?? 0)} />
              <DataMetric label="Needs Review" value={String(liveRecoverySummary.needs_review ?? 0)} color={Number(liveRecoverySummary.needs_review ?? 0) ? "text-amber-300" : "text-emerald-400"} />
              <DataMetric label="Retry Cap" value={String(liveRecoverySummary.max_recovery_attempts ?? 3)} color="text-zinc-300" />
            </div>
            <div className="max-h-[360px] overflow-auto p-0 scrollbar-thin scrollbar-thumb-white/10">
              <table className="min-w-full table-fixed border-collapse text-left text-[11px]">
                <colgroup>
                  <col className="w-28" />
                  <col className="w-20" />
                  <col className="w-52" />
                  <col className="w-24" />
                  <col />
                  <col className="w-32" />
                  <col className="w-32" />
                  <col className="w-24" />
                </colgroup>
                <thead className="sticky top-0 z-10 bg-[#10121c]">
                  <tr className="border-b border-white/5">
                    <th className="w-28 px-4 py-2 font-black text-zinc-600">Created</th>
                    <th className="w-20 px-4 py-2 font-black text-zinc-600">Action</th>
                    <th className="w-52 px-4 py-2 font-black text-zinc-600">Mint</th>
                    <th className="w-24 px-4 py-2 font-black text-zinc-600">Status</th>
                    <th className="px-4 py-2 font-black text-zinc-600">Signature</th>
                    <th className="w-32 px-4 py-2 font-black text-zinc-600">Preflight</th>
                    <th className="w-32 px-4 py-2 font-black text-zinc-600">Recovery</th>
                    <th className="w-24 px-4 py-2 font-black text-zinc-600">Export</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono">
                  {liveAudit.slice(0, 40).map((audit) => (
                    <tr key={audit.id} className="hover:bg-white/[0.02]">
                      <td className="px-4 py-2 text-zinc-500">{new Date(audit.created_at).toLocaleTimeString()}</td>
                      <td className="px-4 py-2 text-zinc-300">{audit.action}</td>
                      <td className="max-w-[180px] truncate px-4 py-2 text-zinc-500" title={audit.mint}>{audit.mint}</td>
                      <td className="px-4 py-2"><Badge variant={audit.final_status === "confirmed" ? "success" : audit.final_status === "failed" ? "danger" : "warning"}>{audit.final_status || audit.status}</Badge></td>
                      <td className="max-w-[220px] truncate px-4 py-2 text-zinc-500">
                        {audit.transaction_signature ? (
                          <a className="text-blue-400 hover:text-blue-300" href={`https://solscan.io/tx/${audit.transaction_signature}`} target="_blank" rel="noreferrer">{audit.transaction_signature}</a>
                        ) : "not submitted"}
                      </td>
                      <td className="px-4 py-2 text-zinc-500">
                        <div className="font-black text-zinc-300">
                          {(audit.preflight_checks ?? []).filter((check) => check.status === "pass").length}/{audit.preflight_checks?.length ?? 0} pass
                        </div>
                        <div className="truncate text-[10px]" title={(audit.preflight_checks ?? []).find((check) => check.status !== "pass")?.reason || "preflight clear"}>
                          {(audit.preflight_checks ?? []).find((check) => check.status !== "pass")?.label || "clear"}
                        </div>
                      </td>
                      <td className="px-4 py-2 text-zinc-500">
                        <div className="font-black text-zinc-300">{audit.recovery_attempts} tries</div>
                        <div className="truncate text-[10px]" title={audit.last_recovery_error || audit.recommended_action}>
                          {audit.last_recovery_error || audit.recommended_action || "no action"}
                        </div>
                      </td>
                      <td className="px-4 py-2">
                        <button type="button" className="text-amber-300 hover:text-amber-200" onClick={() => downloadExport(incidentExportUrl(audit.id), "cryptoarc-incident-export.json")}>incident</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!liveAudit.length ? <p className="p-4 text-xs text-zinc-500">No live execution audit rows recorded.</p> : null}
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
             <Card className="p-4" hover={false}>
              <h3 className="mb-4 text-xs font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Trash2 size={14} className="text-rose-500" />
                Data Purge
              </h3>
              <div className="grid grid-cols-2 gap-1.5">
                {clearTargets.map((target) => (
                  <Button 
                    key={target} 
                    variant="ghost" 
                    size="sm" 
                    className="h-8 justify-start border border-white/5 bg-white/[0.02] px-3 py-1.5 text-[10px] font-bold tracking-normal text-zinc-400 hover:border-rose-500/20 hover:bg-rose-500/10 hover:text-rose-500"
                    onClick={() => onClear(target)}
                  >
                    {target.replace(/_/g, " ")}
                  </Button>
                ))}
              </div>
            </Card>

            <Card className="p-4" hover={false}>
              <h3 className="mb-4 text-xs font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Download size={14} className="text-blue-500" />
                Export Portal
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {exportTargets.map((target) => (
                  <button
                    type="button"
                    key={target}
                    onClick={() => downloadExport(exportUrl(target as any), `cryptoarc-${target}.json`)}
                    className="flex items-center rounded-lg border border-white/5 bg-white/[0.02] px-3 py-1.5 text-[10px] font-bold text-zinc-400 transition-all hover:bg-blue-500/10 hover:text-blue-500 hover:border-blue-500/20"
                  >
                    {target.replace(/_/g, " ")}
                  </button>
                ))}
              </div>
            </Card>
          </div>
        </div>

        {/* Right Column: Status & Health */}
        <div className="space-y-6">
          <Card id="migration-panel" className="p-6" hover={false}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Database size={16} />
                Migration Status
              </h3>
              <Badge variant={opsMonitoring?.schema?.ok ? "success" : "warning"}>{opsMonitoring?.schema?.status ?? "pending"}</Badge>
            </div>
            {!opsMonitoring?.schema ? (
              <div className="space-y-3">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : (
              <div className="space-y-3 text-[11px]">
                <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3">
                  <span className="text-zinc-500">Schema Version</span>
                  <span className="font-black text-white">{opsMonitoring.schema.current_version} / {opsMonitoring.schema.expected_version}</span>
                </div>
                {opsMonitoring.schema.startup_error ? (
                  <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-rose-200">{opsMonitoring.schema.startup_error}</div>
                ) : null}
                <div className="space-y-2">
                  {opsMonitoring.schema.migrations.slice(0, 5).map((migration) => (
                    <div key={migration.migration_id} className="rounded-xl bg-white/[0.02] p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-black text-white">{migration.migration_id}</span>
                        <span className="text-zinc-500">{new Date(migration.applied_at).toLocaleDateString()}</span>
                      </div>
                      <p className="mt-1 text-zinc-400">{migration.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          <Card id="restore-panel" className="p-6" hover={false}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Upload size={16} />
                Import / Restore
              </h3>
              <input
                ref={restoreInputRef}
                type="file"
                aria-label="Restore artifact file"
                accept="application/json"
                className="hidden"
                onChange={(event) => void handleRestoreFile(event.target.files?.[0] ?? null)}
              />
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" size="sm" onClick={() => downloadExport(backupRestoreExportUrl(), "cryptoarc-backup-restore.json")}>
                  <Download size={14} className="mr-2" />
                  Evidence
                </Button>
                <Button variant="secondary" size="sm" onClick={() => restoreInputRef.current?.click()} disabled={restoreBusy}>
                  Select Artifact
                </Button>
                <Button variant="secondary" size="sm" onClick={runRestoreDrill} disabled={restoreBusy}>
                  Smoke Test
                </Button>
              </div>
            </div>
            <div className="space-y-3 text-[11px]">
              <p className="text-zinc-400">Preview a local backup artifact before replacing the SQLite state. Restore always creates a safety copy first.</p>
              {restoreSmokeTest ? (
                <div className={cn("space-y-3 rounded-xl border p-3", restoreSmokeTest.passed ? "border-emerald-500/20 bg-emerald-500/10" : "border-amber-500/20 bg-amber-500/10")}>
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-black text-white">Restore smoke test</span>
                    <Badge variant={restoreSmokeTest.passed ? "success" : "warning"}>{restoreSmokeTest.status}</Badge>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Integrity</span>
                      <span className="font-black text-white">{restoreSmokeTest.integrity_check ?? "unknown"}</span>
                    </div>
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Risk</span>
                      <span className={cn("font-black", restoreSmokeTest.risk_level === "low" ? "text-emerald-400" : "text-amber-300")}>{restoreSmokeTest.risk_level ?? "unknown"}</span>
                    </div>
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Payload</span>
                      <span className="font-black text-white">{restoreSmokeTest.payload_bytes ?? 0}</span>
                    </div>
                  </div>
                  {restoreSmokeTest.operator_action ? <p className="text-zinc-200">{restoreSmokeTest.operator_action}</p> : null}
                </div>
              ) : null}
              {restoreFileName ? <div className="rounded-xl bg-white/[0.02] p-3 text-zinc-300">{restoreFileName}</div> : null}
              {restorePreview ? (
                <div className="space-y-3 rounded-xl border border-white/5 bg-white/[0.02] p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-zinc-500">Schema</span>
                    <span className="font-black text-white">{restorePreview.schema_version} {"->"} {restorePreview.current_schema_version}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Risk</span>
                      <span className={cn("font-black", restorePreview.risk_level === "blocked" ? "text-rose-400" : restorePreview.risk_level === "review" ? "text-amber-300" : "text-emerald-400")}>{restorePreview.risk_level ?? "low"}</span>
                    </div>
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Integrity</span>
                      <span className="font-black text-white">{restorePreview.integrity_check ?? "unknown"}</span>
                    </div>
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Changed</span>
                      <span className="font-black text-white">{restorePreview.changed_tables?.length ?? 0}</span>
                    </div>
                  </div>
                  {restorePreview.table_deltas ? (
                    <div className="max-h-32 overflow-auto rounded-lg border border-white/5">
                      {Object.entries(restorePreview.table_deltas)
                        .filter(([, delta]) => delta.delta !== 0)
                        .slice(0, 8)
                        .map(([table, delta]) => (
                          <div key={table} className="grid grid-cols-[minmax(0,1fr)_70px_70px_64px] gap-2 border-b border-white/5 px-3 py-2 last:border-b-0">
                            <span className="truncate text-zinc-300">{table}</span>
                            <span className="text-right text-zinc-500">{delta.current}</span>
                            <span className="text-right text-zinc-500">{delta.artifact}</span>
                            <span className={cn("text-right font-black", delta.delta > 0 ? "text-emerald-400" : "text-amber-300")}>{delta.delta > 0 ? "+" : ""}{delta.delta}</span>
                          </div>
                        ))}
                      {!restorePreview.changed_tables?.length ? <div className="px-3 py-2 text-zinc-500">No table count changes detected.</div> : null}
                    </div>
                  ) : null}
                  <div className="space-y-2">
                    {restorePreview.warnings.map((warning) => (
                      <div key={warning} className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-amber-100">{warning}</div>
                    ))}
                  </div>
                  {restorePreview.recommended_actions?.length ? (
                    <div className="space-y-1 rounded-lg bg-black/20 p-3 text-zinc-300">
                      {restorePreview.recommended_actions.map((action) => <p key={action}>{action}</p>)}
                    </div>
                  ) : null}
                  <Button variant="danger" size="sm" onClick={confirmRestore} disabled={!restorePreview.compatible || restoreBusy}>
                    Confirm Restore
                  </Button>
                </div>
              ) : null}
              {restoreMessage ? <div className="rounded-xl bg-white/[0.02] p-3 text-zinc-300">{restoreMessage}</div> : null}
            </div>
          </Card>

          <Card id="signer-panel" className="p-6" hover={false}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Shield size={16} />
                Signer Daemon
              </h3>
              <Badge variant={signerDaemon?.healthy ? "success" : "warning"}>{signerDaemon?.healthy ? "healthy" : "blocked"}</Badge>
            </div>
            <div className="space-y-3 text-[11px]">
              <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3">
                <span className="text-zinc-500">Transport</span>
                <span className="font-black text-white">{signerDaemon?.transport ?? "localhost_http"}</span>
              </div>
              <div className="rounded-xl bg-white/[0.02] p-3 text-zinc-300 break-all">{signerDaemon?.endpoint || "http://127.0.0.1:8799"}</div>
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-amber-100">
                {signerDaemon?.disabled_reason || "Browser wallet remains the only active signer path in this phase."}
              </div>
            </div>
          </Card>

          <Card id="readiness-panel" className="p-6" hover={false}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                <Shield size={16} />
                Readiness
              </h3>
              <Badge variant={readinessTone}>
                {readinessStatus?.status?.replace(/_/g, " ") || "unknown"}
              </Badge>
            </div>
            <div className="space-y-4">
              {!readinessStatus ? (
                <div className="space-y-3">
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                </div>
              ) : readinessStatus.gates.map((gate) => (
                <div key={gate.id} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-bold text-zinc-400">{gate.label}</span>
                    <span className={cn("font-black", gate.status === "pass" ? "text-emerald-500" : gate.status === "warn" ? "text-amber-400" : "text-rose-500")}>
                      {String(gate.value)} / {gate.target}
                    </span>
                  </div>
                  <div className="h-1 w-full rounded-full bg-white/5">
                    <div 
                      className={cn("h-full rounded-full", gate.status === "pass" ? "bg-emerald-500" : gate.status === "warn" ? "bg-amber-400" : "bg-rose-500")}
                      style={{ width: `${gate.status === "pass" ? 100 : gate.status === "warn" ? 60 : 28}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-zinc-600">{gate.reason}</span>
                </div>
              ))}
              {readinessStatus?.recommended_actions?.length ? (
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px] text-zinc-400">
                  {readinessStatus.recommended_actions.slice(0, 3).map((action) => (
                    <div key={action} className="flex gap-2 py-1">
                      <ChevronRight size={12} className="mt-0.5 shrink-0 text-amber-300" />
                      <span>{action}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </Card>

          <Card id="operations-panel" className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Activity size={16} />
              Operations
            </h3>
            <div className="space-y-3">
              {loadingCore ? (
                <>
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </>
              ) : (
                <>
                  <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <span className="text-zinc-500">Watchdog</span>
                    <span className="font-black text-white">{watchdogStatus?.status} ({watchdogStatus?.tick_age_seconds}s)</span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <span className="text-zinc-500">Source Health</span>
                    <span className={cn("font-black", sourceHealthTone)}>{sourceHealth?.health_score}%</span>
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-zinc-500">Source Trust</span>
                      <span className={cn("font-black uppercase", sourceTrustTone)}>{sourceHealth?.trust_state ?? "unknown"}</span>
                    </div>
                    <p className="mt-2 text-zinc-400">{sourceHealth?.operator_action}</p>
                    {sourceHealth?.trust_blockers?.length ? (
                      <div className="mt-2 space-y-1">
                        {sourceHealth.trust_blockers.slice(0, 3).map((blocker) => (
                          <div key={blocker} className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-2 text-rose-100">{blocker}</div>
                        ))}
                      </div>
                    ) : null}
                    {sourceHealth?.trust_warnings?.length ? (
                      <div className="mt-2 space-y-1">
                        {sourceHealth.trust_warnings.slice(0, 2).map((warning) => (
                          <div key={warning} className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-2 text-amber-100">{warning}</div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <span className="text-zinc-500">Source Adapters</span>
                      <span className="font-black text-white">{sourceAdapters.length}</span>
                    </div>
                    <div className="space-y-2">
                      {sourceAdapters.map((adapter) => (
                        <div key={adapter.name} className="rounded-lg border border-white/5 bg-black/20 p-2">
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-black uppercase tracking-widest text-white">{adapter.name.replace(/_/g, " ")}</span>
                            <Badge variant={adapter.enabled ? "success" : "warning"}>{adapter.status.replace(/_/g, " ")}</Badge>
                          </div>
                          <p className="mt-1 text-zinc-500">{String(adapter.details?.operator_action ?? adapter.capabilities.join(", "))}</p>
                          {adapter.name === "solana_logs" ? (
                            <p className="mt-1 text-[10px] text-zinc-600">logsSubscribe / {String(adapter.details?.filter ?? "mentions")} / {String(adapter.details?.subscription_limit ?? "single address filter")}</p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <span className="text-zinc-500">Solana Logs Verification</span>
                      <Badge variant={solanaLogsVerification?.status === "matching" ? "success" : solanaLogsVerification?.status === "review" || solanaLogsVerification?.status === "no_matches" ? "danger" : "warning"}>{solanaLogsVerification?.status?.replace(/_/g, " ") ?? "loading"}</Badge>
                    </div>
                    {solanaLogsVerification ? (
                      <div className="space-y-2">
                        <div className="grid grid-cols-3 gap-2">
                          <div className="rounded-lg bg-black/20 p-2">
                            <span className="text-zinc-500">Direct creates</span>
                            <div className="font-black text-white">{solanaLogsVerification.summary.direct_create_hints}</div>
                          </div>
                          <div className="rounded-lg bg-black/20 p-2">
                            <span className="text-zinc-500">Create matches</span>
                            <div className="font-black text-emerald-300">{solanaLogsVerification.summary.create_matches}</div>
                          </div>
                          <div className="rounded-lg bg-black/20 p-2">
                            <span className="text-zinc-500">Review</span>
                            <div className={cn("font-black", solanaLogsVerification.summary.conflicts ? "text-rose-300" : "text-zinc-300")}>{solanaLogsVerification.summary.conflicts + solanaLogsVerification.summary.unmatched_direct}</div>
                          </div>
                        </div>
                        <div className="grid grid-cols-3 gap-2">
                          <div className="rounded-lg bg-black/20 p-2">
                            <span className="text-zinc-500">Match rate</span>
                            <div className={cn("font-black", solanaLogsVerification.source_soak.match_rate >= 0.6 ? "text-emerald-300" : "text-amber-300")}>{Math.round(solanaLogsVerification.source_soak.match_rate * 100)}%</div>
                          </div>
                          <div className="rounded-lg bg-black/20 p-2">
                            <span className="text-zinc-500">Decoded</span>
                            <div className={cn("font-black", solanaLogsVerification.source_soak.decoded_create_rate >= 0.5 ? "text-emerald-300" : "text-amber-300")}>{Math.round(solanaLogsVerification.source_soak.decoded_create_rate * 100)}%</div>
                          </div>
                          <div className="rounded-lg bg-black/20 p-2">
                            <span className="text-zinc-500">Soak target</span>
                            <div className="font-black text-zinc-300">{solanaLogsVerification.source_soak.matches}/10</div>
                          </div>
                        </div>
                        <div className="rounded-lg border border-white/5 bg-black/20 p-2">
                          <div className="mb-2 flex items-center justify-between gap-3">
                            <span className="text-zinc-500">Durable soak history</span>
                            <Badge variant={sourceSoakAcceptance?.history_summary?.latest_ready ? "success" : "warning"}>{sourceSoakAcceptance?.history_summary?.snapshots ?? 0} saved</Badge>
                          </div>
                          <div className="grid grid-cols-3 gap-2">
                            <div>
                              <span className="text-zinc-500">Ready</span>
                              <div className="font-black text-white">{sourceSoakAcceptance?.history_summary?.ready_snapshots ?? 0}</div>
                            </div>
                            <div>
                              <span className="text-zinc-500">Avg match</span>
                              <div className="font-black text-white">{Math.round((sourceSoakAcceptance?.history_summary?.average_match_rate ?? 0) * 100)}%</div>
                            </div>
                            <div>
                              <span className="text-zinc-500">Avg decoded</span>
                              <div className="font-black text-white">{Math.round((sourceSoakAcceptance?.history_summary?.average_decoded_create_rate ?? 0) * 100)}%</div>
                            </div>
                          </div>
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <Button size="sm" variant="secondary" onClick={recordSourceSoak} disabled={sourceSoakBusy}>
                              <Save size={14} className="mr-2" />
                              {sourceSoakBusy ? "Saving..." : "Snapshot Soak"}
                            </Button>
                            <button type="button" className="inline-flex text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(sourceSoakAcceptanceExportUrl(500), "cryptoarc-source-soak.json")}>Export soak history</button>
                          </div>
                        </div>
                        <p className="text-zinc-500">{solanaLogsVerification.operator_action}</p>
                        {solanaLogsVerification.action_items.slice(0, 3).map((item) => (
                          <div key={item} className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-2 text-amber-100">{item}</div>
                        ))}
                        <button type="button" className="inline-flex text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(solanaLogsVerificationExportUrl(500), "cryptoarc-solana-logs-verification.json")}>Export direct evidence</button>
                      </div>
                    ) : (
                      <Skeleton className="h-16 w-full" />
                    )}
                    {solanaLogsVerificationError ? <p className="mt-2 text-xs text-rose-300">{solanaLogsVerificationError}</p> : null}
                    {sourceSoakError ? <p className="mt-2 text-xs text-rose-300">{sourceSoakError}</p> : null}
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <span className="text-zinc-500">Raw Event Inspection</span>
                      <span className="font-black text-white">{sourceHealth?.raw_event_inspection?.recent_events ?? 0}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="rounded-lg bg-black/20 p-2">
                        <span className="text-zinc-500">Unique mints</span>
                        <div className="font-black text-white">{sourceHealth?.raw_event_inspection?.unique_mints ?? 0}</div>
                      </div>
                      <div className="rounded-lg bg-black/20 p-2">
                        <span className="text-zinc-500">Malformed</span>
                        <div className="font-black text-white">{sourceHealth?.raw_event_inspection?.malformed_events ?? 0}</div>
                      </div>
                    </div>
                    <p className="mt-2 text-zinc-500">Filters: {(sourceHealth?.raw_event_inspection?.filterable_fields ?? []).join(", ")}</p>
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <span className="text-zinc-500">Source Quality History</span>
                      <div className="flex items-center gap-2">
                        <button type="button" className="text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(sourceHealthExportUrl(300), "cryptoarc-source-health.json")}>Export</button>
                        <span className="font-black text-white">{sourceHealth?.quality_history?.filter((bucket) => bucket.events > 0).length ?? 0} active</span>
                      </div>
                    </div>
                    <div className="grid grid-cols-6 gap-1">
                      {(sourceHealth?.quality_history ?? []).slice(-12).map((bucket) => {
                        const tone =
                          bucket.trust_state === "trusted"
                            ? "bg-emerald-500/70"
                            : bucket.trust_state === "conflicting"
                              ? "bg-rose-500/70"
                              : bucket.trust_state === "degraded"
                                ? "bg-amber-500/70"
                                : "bg-white/10";
                        return (
                          <div
                            key={bucket.bucket_start}
                            className="h-8 rounded-lg border border-white/5 bg-black/20 p-1"
                            title={`${new Date(bucket.bucket_start).toLocaleTimeString()} - ${bucket.events} events, ${(bucket.normalized_ratio * 100).toFixed(0)}% normalized, ${bucket.trust_state}`}
                          >
                            <div className={cn("h-full rounded", tone)} style={{ opacity: bucket.events ? 1 : 0.35 }} />
                          </div>
                        );
                      })}
                    </div>
                    <div className="mt-2 flex items-center justify-between text-[10px] text-zinc-500">
                      <span>Recent source soak buckets</span>
                      <span>N/R/M tracked</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-white/[0.02] p-3 text-[11px]">
                    <span className="text-zinc-500">RPC Health</span>
                    <span className="font-black text-emerald-500">{solanaStatus?.health}</span>
                  </div>
                </>
              )}
              <Button variant="secondary" size="sm" className="w-full mt-2" onClick={onRecover}>
                <RotateCcw size={14} className="mr-2" />
                Recover System
              </Button>
            </div>
          </Card>

          <Card id="security-panel" className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Gauge size={16} />
              Security Boundary
            </h3>
            <div className="space-y-2 text-[11px]">
              {!securityStatus ? (
                <>
                  <Skeleton className="h-6 w-full" />
                  <Skeleton className="h-6 w-full" />
                  <Skeleton className="h-6 w-full" />
                  <Skeleton className="h-6 w-full" />
                </>
              ) : (
                <>
                  <div className="flex justify-between border-b border-white/5 pb-2">
                    <span className="text-zinc-500 font-bold uppercase tracking-tighter">Auth</span>
                    <span className={cn("font-black", securityStatus?.auth_enabled ? "text-emerald-500" : "text-amber-500")}>{securityStatus?.auth_enabled ? "Enabled" : "Disabled"}</span>
                  </div>
                  <div className="flex justify-between border-b border-white/5 py-2">
                    <span className="text-zinc-500 font-bold uppercase tracking-tighter">2FA</span>
                    <span className={cn("font-black", securityStatus?.totp_enabled ? "text-emerald-500" : "text-zinc-400")}>{securityStatus?.totp_enabled ? "Active" : "Off"}</span>
                  </div>
                  <div className="flex justify-between border-b border-white/5 py-2">
                    <span className="text-zinc-500 font-bold uppercase tracking-tighter">Live Env</span>
                    <span className="text-rose-500 font-black">Blocked by default</span>
                  </div>
                  <div className="flex justify-between pt-2">
                    <span className="text-zinc-500 font-bold uppercase tracking-tighter">Boundary</span>
                    <span className="text-zinc-300 font-black italic">Paper Only</span>
                  </div>
                </>
              )}
            </div>
          </Card>

          <Card id="alerts-panel" className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Bell size={16} />
              Operator Alerts
            </h3>
            <div className="space-y-2 text-[11px]">
              {!alertStatus ? (
                <>
                  <Skeleton className="h-6 w-full" />
                  <Skeleton className="h-6 w-full" />
                  <Skeleton className="h-6 w-full" />
                </>
              ) : (
                <>
                  <div className="flex justify-between border-b border-white/5 pb-2">
                    <span className="text-zinc-500 font-bold uppercase tracking-tighter">Telegram</span>
                    <span className={cn("font-black", alertStatus.telegram_enabled && alertStatus.telegram_configured ? "text-emerald-500" : "text-amber-500")}>
                      {alertStatus.telegram_enabled && alertStatus.telegram_configured ? "Ready" : alertStatus.telegram_enabled ? "Needs config" : "Disabled"}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-white/5 py-2">
                    <span className="text-zinc-500 font-bold uppercase tracking-tighter">Throttle</span>
                    <span className="font-black text-white">{alertStatus.min_interval_seconds}s</span>
                  </div>
                  <div className="rounded-xl bg-white/[0.02] p-3">
                    <span className="block text-zinc-500 font-bold uppercase tracking-tighter">Last result</span>
                    <span className="mt-1 block font-black text-white">{alertStatus.last_result.status}</span>
                    <span className="mt-1 block text-zinc-400">{alertStatus.last_result.reason}</span>
                  </div>
                  <Button variant="secondary" size="sm" className="w-full" onClick={onSendTestAlert}>
                    <Bell size={14} className="mr-2" />
                    Send Test Alert
                  </Button>
                </>
              )}
            </div>
          </Card>

          <Card id="observability-panel" className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Activity size={16} />
              Observability
            </h3>
            <div className="space-y-3 text-[11px]">
              {!opsMonitoring?.observability ? (
                <>
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-8 w-full" />
                </>
              ) : (
                <>
                  <p className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-zinc-300">{opsMonitoring.observability.operator_action}</p>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Events</span>
                      <span className="font-black text-white">{opsMonitoring.observability.event_count}</span>
                    </div>
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Warnings</span>
                      <span className="font-black text-amber-300">{opsMonitoring.observability.level_counts.warning ?? 0}</span>
                    </div>
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Errors</span>
                      <span className="font-black text-rose-400">{(opsMonitoring.observability.level_counts.error ?? 0) + (opsMonitoring.observability.level_counts.danger ?? 0)}</span>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Source trust</span>
                      <span className="font-black text-white">{String(opsMonitoring.observability.source_metrics.trust_state ?? "unknown")}</span>
                    </div>
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Signer</span>
                      <span className="font-black text-white">{String(opsMonitoring.observability.signer_metrics.mode ?? "unknown")}</span>
                    </div>
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Sessions</span>
                      <span className="font-black text-white">{opsMonitoring.observability.session_metrics?.sessions_seen ?? 0}</span>
                    </div>
                    <div className="rounded-lg bg-black/20 p-2">
                      <span className="block text-zinc-500">Tagged events</span>
                      <span className="font-black text-white">{opsMonitoring.observability.session_metrics?.session_event_count ?? 0}</span>
                    </div>
                  </div>
                  <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="flex items-center gap-2 font-black uppercase tracking-widest text-white">
                        <FileText size={14} />
                        Operator Logs
                      </span>
                      <Badge variant={operatorLogs?.summary.errors ? "danger" : operatorLogs?.summary.warnings ? "warning" : "success"}>
                        {operatorLogs ? `${operatorLogs.summary.returned_events}/${operatorLogs.summary.total_events}` : "loading"}
                      </Badge>
                    </div>
                    {operatorLogs ? (
                      <>
                        <div className="mt-3 grid grid-cols-3 gap-2">
                          <div className="rounded-lg bg-black/20 p-2">
                            <span className="block text-zinc-500">Recovery</span>
                            <span className="font-black text-white">{operatorLogs.summary.recovery_related_events}</span>
                          </div>
                          <div className="rounded-lg bg-black/20 p-2">
                            <span className="block text-zinc-500">Source</span>
                            <span className="font-black text-white">{operatorLogs.summary.source_related_events}</span>
                          </div>
                          <div className="rounded-lg bg-black/20 p-2">
                            <span className="block text-zinc-500">Live</span>
                            <span className="font-black text-white">{operatorLogs.summary.live_related_events}</span>
                          </div>
                        </div>
                        <p className="mt-2 text-zinc-400">{operatorLogs.operator_action}</p>
                        <button type="button" className="mt-2 inline-flex text-[10px] font-black uppercase tracking-widest text-amber-300 hover:text-amber-200" onClick={() => downloadExport(operatorLogsExportUrl("24h", "", "", 200), "cryptoarc-operator-logs.json")}>Export structured logs</button>
                      </>
                    ) : (
                      <Skeleton className="mt-3 h-10 w-full" />
                    )}
                    {operatorLogsError ? <p className="mt-2 text-xs text-rose-300">{operatorLogsError}</p> : null}
                  </div>
                  <div className="space-y-2">
                    {opsMonitoring.observability.high_severity.slice(0, 3).map((event) => (
                      <div key={event.id} className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-black uppercase tracking-widest text-white">{event.subsystem}</span>
                          <Badge variant={event.level === "danger" || event.level === "error" ? "danger" : "warning"}>{event.level}</Badge>
                        </div>
                        <p className="mt-1 text-zinc-400">{event.message}</p>
                      </div>
                    ))}
                    {!opsMonitoring.observability.high_severity.length ? <p className="text-zinc-500">No high-severity events in the recent local log.</p> : null}
                  </div>
                </>
              )}
            </div>
          </Card>

          <Card id="backup-history-panel" className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Clock size={16} />
              Backup / Restore History
            </h3>
            <div className="space-y-2 text-[11px]">
              {backupRestoreHistory.slice(0, 6).map((item: BackupRestoreHistoryEntry, index) => (
                <div key={`${item.created_at ?? "entry"}-${index}`} className="rounded-xl bg-white/[0.02] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-black uppercase tracking-widest text-white">{String(item.action ?? "event")}</span>
                    <Badge variant={item.status === "restored" ? "warning" : "info"}>{String(item.status ?? "recorded")}</Badge>
                  </div>
                  <p className="mt-1 text-zinc-400">{String(item.operator_action ?? "Operator history entry")}</p>
                </div>
              ))}
              {!backupRestoreHistory.length ? <p className="text-zinc-500">No backup or restore history yet.</p> : null}
            </div>
          </Card>

          <Card id="subsystem-events-panel" className="p-6" hover={false}>
            <h3 className="mb-4 text-sm font-black uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <Bell size={16} />
              By Subsystem
            </h3>
            <div className="space-y-2 text-[11px]">
              {Object.entries(opsMonitoring?.events_by_subsystem ?? {}).slice(0, 8).map(([subsystem, events]) => (
                <div key={subsystem} className="rounded-xl bg-white/[0.02] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-black uppercase tracking-widest text-white">{subsystem}</span>
                    <Badge variant="info">{events.length}</Badge>
                  </div>
                  <p className="mt-1 text-zinc-400">{events[0]?.message ?? "No recent events"}</p>
                </div>
              ))}
              {!Object.keys(opsMonitoring?.events_by_subsystem ?? {}).length ? <p className="text-zinc-500">No subsystem groups available yet.</p> : null}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
