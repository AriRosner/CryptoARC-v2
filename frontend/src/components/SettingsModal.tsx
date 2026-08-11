import React, { useState, useMemo } from "react";
import QRCode from "qrcode";
import { 
  Database, 
  Target, 
  Shield, 
  Clock, 
  Gauge, 
  SlidersHorizontal, 
  Search,
  Save,
  Lock,
  Smartphone,
  AlertTriangle,
  Radio,
  Brain,
  Sparkles,
  TimerReset,
  Cpu,
  KeyRound,
  QrCode,
  RefreshCw,
  Copy,
  Ban,
  Landmark,
  History,
  WalletCards
} from "lucide-react";
import { Modal } from "./Modal";
import { Button } from "./Button";
import { Badge } from "./Badge";
import { cn } from "./utils";
import { updatePassword, setupTotp, verifyTotp, disableTotp, startMobilePairing, fetchMobileDevices, revokeMobileDevice, fetchProfitSweepHistory, fetchPilotRiskStatus } from "../api";
import type { BotSettings, LiveExecutionAudit, MobileDevice, MobilePairingStartResponse, PilotRiskStatus } from "../types";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: BotSettings;
  onSave: (next: BotSettings) => Promise<void>;
  sourceStatus: any;
  serverStrategyPresets: any[];
  onSaveStrategyPreset: () => void;
}

const NavItem: React.FC<{
  id: string;
  label: string;
  icon: any;
  active: boolean;
  onClick: () => void;
}> = ({ label, icon: Icon, active, onClick }) => (
  <button
    onClick={onClick}
    className={cn(
      "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-bold transition-all",
      active
        ? "bg-amber-500/10 text-amber-500 shadow-inner"
        : "text-zinc-500 hover:bg-white/5 hover:text-zinc-300"
    )}
  >
    <Icon size={16} />
    {label}
  </button>
);

const SettingRow: React.FC<{
  label: string;
  description?: string;
  children: React.ReactNode;
}> = ({ label, description, children }) => {
  const labelledChildren = React.Children.map(children, (child) => {
    if (!React.isValidElement(child) || typeof child.type !== "string") return child;
    if (!["input", "select", "textarea"].includes(child.type)) return child;
    const props = child.props as { "aria-label"?: string };
    return React.cloneElement(child, { "aria-label": props["aria-label"] ?? label } as Record<string, unknown>);
  });

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-white/5 bg-white/[0.01] p-4 transition-colors hover:bg-white/[0.03]">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <span className="text-xs font-bold text-zinc-300">{label}</span>
        <div className="min-w-0 max-w-full sm:flex-shrink-0">{labelledChildren}</div>
      </div>
      {description && <p className="text-[10px] text-zinc-500 leading-relaxed">{description}</p>}
    </div>
  );
};

const FieldControl: React.FC<{
  label: string;
  unit?: string;
  children: React.ReactNode;
}> = ({ label, unit, children }) => (
  <label className="flex min-w-0 flex-col gap-1">
    <span className="text-[10px] font-bold text-zinc-400">
      {label}
      {unit ? <span className="font-medium text-zinc-600"> ({unit})</span> : null}
    </span>
    {children}
  </label>
);

function formatMobileTime(value?: string): string {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleString();
}

function formatSol(value: unknown, digits = 6): string {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return "0 SOL";
  return `${numeric.toFixed(digits).replace(/\.?0+$/, "")} SOL`;
}

function compactAddress(value: unknown): string {
  const text = String(value || "").trim();
  if (!text) return "Not recorded";
  if (text.length <= 16) return text;
  return `${text.slice(0, 8)}...${text.slice(-6)}`;
}

function statusVariant(status: string): "success" | "danger" | "warning" | "neutral" {
  if (["submitted", "confirmed", "reconciled"].includes(status)) return "success";
  if (["failed", "needs_review"].includes(status)) return "danger";
  if (["ready", "pending"].includes(status)) return "warning";
  return "neutral";
}

const strategyPresets: Record<string, Partial<BotSettings>> = {
  conservative: {
    trade_size_sol: 0.05,
    slippage_tolerance_pct: 0.6,
    score_threshold: 72,
    max_creator_hold_pct: 6,
    max_open_positions: 2,
    take_profit_pct: 35,
    stop_loss_pct: 18,
    max_hold_time_seconds: 420,
    risk_tolerance: "low",
    trading_speed: "slow"
  },
  balanced: {
    trade_size_sol: 0.1,
    slippage_tolerance_pct: 1,
    score_threshold: 62,
    max_creator_hold_pct: 10,
    max_open_positions: 3,
    take_profit_pct: 50,
    stop_loss_pct: 30,
    max_hold_time_seconds: 600,
    risk_tolerance: "medium",
    trading_speed: "normal"
  },
  aggressive: {
    trade_size_sol: 0.15,
    slippage_tolerance_pct: 1.8,
    score_threshold: 54,
    max_creator_hold_pct: 16,
    max_open_positions: 5,
    take_profit_pct: 70,
    stop_loss_pct: 38,
    max_hold_time_seconds: 720,
    risk_tolerance: "high",
    trading_speed: "fast"
  },
  scalper: {
    trade_size_sol: 0.08,
    slippage_tolerance_pct: 1.2,
    score_threshold: 58,
    max_creator_hold_pct: 12,
    max_open_positions: 4,
    take_profit_pct: 22,
    stop_loss_pct: 16,
    max_hold_time_seconds: 180,
    risk_tolerance: "medium",
    trading_speed: "turbo"
  }
};

function validateSettings(settings: BotSettings): string[] {
  const warnings: string[] = [];
  if (settings.trade_size_sol > settings.daily_loss_cap_sol) warnings.push("Trade size is larger than the daily loss cap.");
  if (settings.slippage_tolerance_pct > 5) warnings.push("Slippage above 5% can make paper fills unrealistically generous.");
  if (settings.risk_tolerance === "degen" && settings.trading_speed === "turbo") warnings.push("Degen risk plus turbo speed is an intentionally high-risk profile.");
  if (!settings.filter_honeypots || !settings.filter_rug_risk) warnings.push("One or more safety filters are disabled.");
  if (settings.paper_failed_fill_pct > 20) warnings.push("Failed fill rate above 20% can heavily skew replay results.");
  if (settings.min_price_confidence < 0.45) warnings.push("Low price confidence can allow weaker PumpPortal price hints into P&L.");
  if (!settings.entry_confirmation_enabled) warnings.push("Entry confirmation gate is disabled; weak launches can enter on score alone.");
  if (settings.max_first_observed_move_pct > 1000) warnings.push("Very high first-move limits can let unit mismatches distort P&L.");
  if (settings.direct_solana_paper_enabled && settings.direct_solana_min_confidence < 0.65) warnings.push("Direct Solana paper normalization is safest with decoded-create confidence at 0.65 or higher.");
  if (settings.live_trading_enabled) warnings.push("Live trading request is set, but backend execution remains blocked unless explicitly enabled by environment.");
  if (settings.profit_sweep_enabled) {
    const hasMinimumProfit = (settings.profit_sweep_min_profit_sol || settings.profit_sweep_threshold_sol) > 0;
    const hasSweepAmount = settings.profit_sweep_mode === "percentage" ? settings.profit_sweep_percentage > 0 : settings.profit_sweep_amount_sol > 0;
    if (!settings.profit_sweep_destination_wallet || !hasMinimumProfit || !hasSweepAmount) warnings.push("Profit sweep is enabled but needs a vault wallet, minimum profit, and sweep amount or percentage.");
  }
  return warnings;
}

function normalizeSettingsSearch(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

const settingsSearchIndex: Record<string, string[]> = {
  source: [
    "Launch Source",
    "Auto-Detection",
    "Direct Solana Paper",
    "Direct Confidence",
    "source launch pumpportal mock detect logsSubscribe confidence",
  ],
  strategy: [
    "Active Profile",
    "Trade Size (SOL)",
    "Slippage Tolerance (%)",
    "Max Open Positions",
    "Trading Speed",
    "Save Current Strategy Preset",
    "strategy profile size slippage speed open positions weights",
  ],
  risk: [
    "Risk Tolerance",
    "Score Threshold",
    "Max Creator Hold (%)",
    "Daily Loss Cap (SOL)",
    "Min Buy Velocity",
    "Max Sell Pressure",
    "Min Metadata Score",
    "Entry Confirmation Gate",
    "Gate Buy Velocity",
    "Gate Sell Pressure",
    "Gate Metadata Score",
    "Gate Initial Buy SOL",
    "Gate Price Confidence",
    "Gate Observed Trades",
    "Max Token Age Seconds",
    "Filter Honeypots",
    "Filter Rug Risks",
    "Duplicate Symbol Penalty",
    "Strict Metadata Checks",
    "Stop On Source Degraded",
    "Manual Kill Switch",
    "Consecutive Loss Halt",
    "Low Replay Confidence Halt",
    "risk tolerance score creator hold loss honeypot rug age trades cooldown entry confirmation velocity pressure metadata observed",
  ],
  exits: [
    "Take Profit (%)",
    "Stop Loss (%)",
    "Trailing Stop",
    "Break-Even Stop",
    "Minimum Hold Seconds",
    "Max Hold Time (Seconds)",
    "Max Position Ticks",
    "Partial Take Profit",
    "Stalled Trade Exit",
    "Sell Pressure Exit",
    "Cooldown After Loss",
    "exit profit loss hold time ticks trailing partial break even stalled pressure",
  ],
  simulation: [
    "RPC URL",
    "Watched Wallet Address",
    "Launch Interval (s)",
    "Paper Volatility (%)",
    "Future Wallet Cap SOL",
    "Manual Live Max SOL",
    "Live Caps",
    "Live Signer Mode",
    "Readiness Halt",
    "Trade Toasts",
    "Compact Token Table",
    "Request Live Trading Unlock",
    "Manual Live Request Capture",
    "Autonomous Live Request",
    "simulation launch interval volatility wallet cap rpc address toasts live mode signer browser hot wallet daemon",
  ],
  "profit-vault": [
    "Profit Vault",
    "Enable Auto-Sweep",
    "Minimum Profit",
    "Sweep Mode",
    "Vault Wallet",
    "Reserve And Rate Limits",
    "profit vault sweep auto send sol wallet reserve history audit local hot wallet",
  ],
  advanced: [
    "Source Stale (s)",
    "Source Max Reconnects",
    "Backtest Replay Limit",
    "Raw Replay Limit",
    "Max Trade Subscriptions",
    "Max Trades Per Hour",
    "Min Price Confidence",
    "Max First Observed Move %",
    "Rejected Price Streak Guard",
    "Paper Fill Delay (Ticks)",
    "Paper Provider Fee (BPS)",
    "Paper Priority Fee",
    "Paper Price Impact %",
    "Paper Failed Fill %",
    "Velocity Slippage",
    "Max Same Creator Buys",
    "Use Observed Prices",
    "Prefer Market-Cap Price",
    "advanced stale reconnect backtest subscriptions confidence move market cap price impact fill hourly paper throttle priority fee",
  ],
  security: [
    "Security",
    "Update Password",
    "Two-Factor Authentication",
    "Mobile Devices",
    "security password 2fa totp authenticator mobile pairing revoke",
  ],
};

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onSave,
  sourceStatus,
  serverStrategyPresets,
  onSaveStrategyPreset
}) => {
  const [activeTab, setActiveTab] = useState("source");
  const [draft, setDraft] = useState<BotSettings>(settings);
  const [isSaving, setIsSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  // Security States
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [totpSetup, setTotpSetup] = useState<{ secret: string; otpauth_url: string } | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [securityMessage, setSecurityMessage] = useState("");
  const [mobileDevices, setMobileDevices] = useState<MobileDevice[]>([]);
  const [mobileApiBaseUrl, setMobileApiBaseUrl] = useState("");
  const [mobilePairing, setMobilePairing] = useState<MobilePairingStartResponse | null>(null);
  const [mobileQrDataUrl, setMobileQrDataUrl] = useState("");
  const [mobileLoading, setMobileLoading] = useState(false);
  const [sweepHistory, setSweepHistory] = useState<LiveExecutionAudit[]>([]);
  const [sweepHistoryLoading, setSweepHistoryLoading] = useState(false);
  const [sweepHistoryError, setSweepHistoryError] = useState("");
  const [pilotRiskStatus, setPilotRiskStatus] = useState<PilotRiskStatus | null>(null);
  const [pilotRiskError, setPilotRiskError] = useState("");
  const warnings = validateSettings(draft);

  const updateDraft = <K extends keyof BotSettings>(key: K, value: BotSettings[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const updateNumber = (key: keyof BotSettings, value: string) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    updateDraft(key, numeric as never);
  };

  const applyProfile = (profile: BotSettings["strategy_profile"]) => {
    setDraft((prev) => ({
      ...prev,
      ...(strategyPresets[profile] ?? {}),
      strategy_profile: profile
    }));
  };

  const NumberInput = ({ field, step = "1", className = "w-24" }: { field: keyof BotSettings; step?: string; className?: string }) => (
    <input
      aria-label={String(field).replace(/_/g, " ")}
      type="number"
      step={step}
      value={Number(draft[field] ?? 0)}
      onChange={(e) => updateNumber(field, e.target.value)}
      className={`${className} rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white text-right`}
    />
  );

  const Toggle = ({ field }: { field: keyof BotSettings }) => (
    <input
      aria-label={String(field).replace(/_/g, " ")}
      type="checkbox"
      checked={Boolean(draft[field])}
      onChange={(e) => updateDraft(field, e.target.checked as never)}
      className="h-4 w-4 rounded border-white/10 bg-black/40 text-amber-500"
    />
  );

  const TextInput = ({ field, placeholder = "" }: { field: keyof BotSettings; placeholder?: string }) => (
    <input
      aria-label={String(field).replace(/_/g, " ")}
      type="text"
      value={String(draft[field] ?? "")}
      placeholder={placeholder}
      onChange={(e) => updateDraft(field, e.target.value as never)}
      className="w-96 max-w-full rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white placeholder-zinc-600"
    />
  );

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSave(draft);
      onClose();
    } finally {
      setIsSaving(false);
    }
  };

  const refreshMobileDevices = async () => {
    setMobileLoading(true);
    try {
      const response = await fetchMobileDevices(true);
      setMobileDevices(response.devices);
    } catch (err: any) {
      setSecurityMessage(`Error: ${err.message}`);
    } finally {
      setMobileLoading(false);
    }
  };

  const handleStartMobilePairing = async () => {
    setMobileLoading(true);
    try {
      const pairing = await startMobilePairing(mobileApiBaseUrl);
      setMobilePairing(pairing);
      const qrText = JSON.stringify(pairing.qr_payload);
      setMobileQrDataUrl(await QRCode.toDataURL(qrText, { width: 180, margin: 1 }));
      setSecurityMessage("Mobile pairing code created.");
      await refreshMobileDevices();
    } catch (err: any) {
      setSecurityMessage(`Error: ${err.message}`);
      setMobileQrDataUrl("");
    } finally {
      setMobileLoading(false);
    }
  };

  const handleCopyMobilePayload = async () => {
    if (!mobilePairing) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(mobilePairing.qr_payload));
      setSecurityMessage("Mobile pairing payload copied.");
    } catch {
      setSecurityMessage("Clipboard permission was denied.");
    }
  };

  const handleRevokeMobileDevice = async (device: MobileDevice) => {
    const confirmed = window.confirm(`Revoke ${device.name || "this mobile device"}?`);
    if (!confirmed) return;
    setMobileLoading(true);
    try {
      await revokeMobileDevice(device.id);
      setSecurityMessage("Mobile device revoked.");
      await refreshMobileDevices();
    } catch (err: any) {
      setSecurityMessage(`Error: ${err.message}`);
    } finally {
      setMobileLoading(false);
    }
  };

  const refreshSweepHistory = async () => {
    setSweepHistoryLoading(true);
    setSweepHistoryError("");
    try {
      setSweepHistory(await fetchProfitSweepHistory(100));
    } catch (err: any) {
      setSweepHistoryError(`Unable to load sweep history: ${err.message}`);
    } finally {
      setSweepHistoryLoading(false);
    }
  };

  const tabs = [
    { id: "source", label: "Source", icon: Database, keywords: "source launch pumpportal mock detect" },
    { id: "strategy", label: "Strategy", icon: Target, keywords: "strategy profile size slippage speed open positions weights" },
    { id: "risk", label: "Risk", icon: Shield, keywords: "risk tolerance score creator hold loss honeypot rug age trades cooldown entry confirmation gate velocity pressure metadata initial buy observed" },
    { id: "exits", label: "Exits", icon: Clock, keywords: "exit profit loss hold time ticks trailing partial break even stalled pressure" },
    { id: "simulation", label: "Simulation", icon: Gauge, keywords: "simulation launch interval volatility wallet cap rpc address toasts live mode" },
    { id: "profit-vault", label: "Profit Vault", icon: Landmark, keywords: "profit vault sweep auto send sol wallet reserve history audit local hot wallet" },
    { id: "advanced", label: "Advanced", icon: SlidersHorizontal, keywords: "advanced stale reconnect backtest subscriptions confidence move market cap price impact fill hourly paper throttle" },
    { id: "security", label: "Security", icon: Lock, keywords: "security password 2fa totp authenticator" }
  ];

  const filteredTabs = useMemo(() => {
    const normalizedQuery = normalizeSettingsSearch(searchQuery);
    if (!normalizedQuery) return tabs;
    const queryTerms = normalizedQuery.split(/\s+/).filter(Boolean);
    return tabs.filter((tab) => {
      const indexedText = normalizeSettingsSearch([tab.label, tab.keywords, ...(settingsSearchIndex[tab.id] ?? [])].join(" "));
      return queryTerms.every((term) => indexedText.includes(term));
    });
  }, [searchQuery]);
  const navScrollable = filteredTabs.length > 8;

  const activeTabExists = filteredTabs.some(t => t.id === activeTab);
  React.useEffect(() => {
    if (!activeTabExists && filteredTabs.length > 0) {
      setActiveTab(filteredTabs[0].id);
    }
  }, [filteredTabs, activeTabExists]);

  React.useEffect(() => {
    if (isOpen && activeTab === "security") {
      void refreshMobileDevices();
    }
  }, [isOpen, activeTab]);

  React.useEffect(() => {
    if (isOpen && activeTab === "profit-vault") {
      void refreshSweepHistory();
    }
  }, [isOpen, activeTab]);

  React.useEffect(() => {
    if (!isOpen || activeTab !== "simulation") return;
    setPilotRiskError("");
    void fetchPilotRiskStatus()
      .then(setPilotRiskStatus)
      .catch((error: unknown) => setPilotRiskError(error instanceof Error ? error.message : "Unable to load pilot risk policy"));
  }, [isOpen, activeTab]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="System Configuration"
      description="Fine-tune your sniper bot's behavior and risk parameters."
      className="max-w-5xl"
    >
      <div className="flex h-[600px] gap-6">
        <div className="flex w-52 flex-col space-y-1 border-r border-white/5 pr-4">
          <div className="relative mb-4">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              aria-label="Search settings"
              placeholder="Search settings…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="dashboard-search-input h-9 w-full rounded-lg border border-white/10 bg-black/40 pr-3 text-xs text-white focus:border-amber-500/50 focus:outline-none"
            />
          </div>
          <div className={cn("space-y-1", navScrollable ? "max-h-72 overflow-y-auto pr-1 crypto-scrollbar" : "overflow-visible")}>
            {filteredTabs.map((tab) => (
              <NavItem
                key={tab.id}
                {...tab}
                active={activeTab === tab.id}
                onClick={() => setActiveTab(tab.id)}
              />
            ))}
            {filteredTabs.length === 0 && (
              <p className="px-2 py-4 text-center text-[10px] text-zinc-600 italic">No settings found</p>
            )}
          </div>
          <div className="mt-4 pt-4 border-t border-white/5">
            <Button
              className="w-full"
              onClick={handleSave}
              disabled={isSaving}
            >
              <Save size={16} className="mr-2" />
              {isSaving ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-white/10">
          <div className="space-y-6 pb-6">
            {warnings.length ? (
              <div className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.04] p-4">
                <div className="mb-2 flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-500">
                  <AlertTriangle size={14} />
                  Validation warnings
                </div>
                <div className="space-y-1 text-[11px] text-amber-100/80">
                  {warnings.map((warning) => <p key={warning}>{warning}</p>)}
                </div>
              </div>
            ) : null}

            {activeTab === "source" && (
              <>
                <h4 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-500/80">
                  <Radio size={13} />
                  Launch Configuration
                </h4>
                <div className="grid gap-3">
                  <SettingRow label="Launch Source" description="Choose where new token launches come from.">
                    <select
                      value={draft.launch_source}
                      onChange={(e) => updateDraft("launch_source", e.target.value as BotSettings["launch_source"])}
                      className="dashboard-select rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white"
                    >
                      <option value="mock">Mock stream</option>
                      <option value="pumpportal">PumpPortal Real-time</option>
                    </select>
                  </SettingRow>
                  <SettingRow label="Auto-Detection" description="Automatically add new tokens to the monitoring queue.">
                    <input
                      type="checkbox"
                      checked={draft.detect_new_tokens}
                      onChange={(e) => updateDraft("detect_new_tokens", e.target.checked)}
                      className="h-4 w-4 rounded border-white/10 bg-black/40 text-amber-500"
                    />
                  </SettingRow>
                  <SettingRow label="Direct Solana Paper" description="Let high-confidence logsSubscribe create evidence enter paper monitoring only.">
                    <input
                      type="checkbox"
                      checked={draft.direct_solana_paper_enabled}
                      onChange={(e) => updateDraft("direct_solana_paper_enabled", e.target.checked)}
                      className="h-4 w-4 rounded border-white/10 bg-black/40 text-amber-500"
                    />
                  </SettingRow>
                  <SettingRow label="Direct Confidence" description="Minimum decoded direct-create confidence before paper normalization.">
                    <NumberInput field="direct_solana_min_confidence" step="0.05" />
                  </SettingRow>
                </div>

                <section className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.03] p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h4 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-500">
                      <Database size={13} />
                      Source Health
                    </h4>
                    <Badge variant={sourceStatus.status === "connected" ? "success" : "danger"}>
                      {sourceStatus.status}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-[10px]">
                    <div className="flex flex-col gap-1">
                      <span className="text-zinc-500 font-bold uppercase tracking-tight">Normalized Events</span>
                      <span className="font-black text-white">{sourceStatus.events_received}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="text-zinc-500 font-bold uppercase tracking-tight">Raw Events Seen</span>
                      <span className="font-black text-white">{sourceStatus.raw_events_seen}</span>
                    </div>
                    <div className="col-span-2 mt-1">
                      <span className="text-zinc-500 font-bold uppercase tracking-tight">Status Message</span>
                      <div className="mt-1 rounded-lg bg-black/40 p-2 font-mono text-[9px] text-zinc-400 leading-relaxed border border-white/5">
                        {sourceStatus.message}
                      </div>
                    </div>
                  </div>
                </section>
              </>
            )}

            {activeTab === "strategy" && (
              <>
                <h4 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-500/80">
                  <Brain size={13} />
                  Strategy Profiles
                </h4>
                <div className="grid gap-3">
                  <SettingRow label="Active Profile" description="Start from a preset, then customize weights.">
                    <select
                      value={draft.strategy_profile}
                      onChange={(e) => applyProfile(e.target.value as BotSettings["strategy_profile"])}
                      className="dashboard-select rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white"
                    >
                      <option value="conservative">Conservative</option>
                      <option value="balanced">Balanced</option>
                      <option value="aggressive">Aggressive</option>
                      <option value="scalper">Scalper</option>
                      <option value="custom">Custom</option>
                    </select>
                  </SettingRow>
                  <SettingRow label="Trade Size (SOL)" description="Amount of SOL to use for each paper trade.">
                    <NumberInput field="trade_size_sol" step="0.01" />
                  </SettingRow>
                  <SettingRow label="Slippage Tolerance (%)" description="Max price slippage allowed for execution.">
                    <NumberInput field="slippage_tolerance_pct" step="0.1" />
                  </SettingRow>
                  <SettingRow label="Max Open Positions" description="Upper limit on concurrent active trades.">
                    <NumberInput field="max_open_positions" />
                  </SettingRow>
                  <SettingRow label="Trading Speed" description="Controls paper execution cadence and strategy aggression.">
                    <select value={draft.trading_speed} onChange={(e) => updateDraft("trading_speed", e.target.value as BotSettings["trading_speed"])} className="dashboard-select rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white">
                      <option value="slow">slow</option>
                      <option value="normal">normal</option>
                      <option value="fast">fast</option>
                      <option value="turbo">turbo</option>
                    </select>
                  </SettingRow>
                  <SettingRow label="Save Current Strategy Preset" description={`${serverStrategyPresets.length} server presets are available. Save this tuned strategy for reuse.`}>
                    <Button variant="secondary" size="sm" onClick={onSaveStrategyPreset}>Save Preset</Button>
                  </SettingRow>
                </div>

                <h4 className="mt-4 flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-500/80">
                  <Sparkles size={13} />
                  Scoring Intelligence
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  {["metadata", "momentum", "pressure", "creator"].map((weight) => (
                    <div key={weight} className="rounded-xl border border-white/5 bg-white/[0.01] p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-tight">{weight} weight</span>
                        <input
                          type="number"
                          step="0.1"
                          value={(draft as any)[`strategy_weight_${weight}`]}
                          onChange={(e) => updateDraft(`strategy_weight_${weight}` as any, parseFloat(e.target.value))}
                          className="w-14 rounded-lg border border-white/10 bg-black px-2 py-1 text-[10px] text-white text-right"
                        />
                      </div>
                      <div className="h-1 w-full rounded-full bg-white/5">
                        <div 
                          className="h-full rounded-full bg-amber-500/50"
                          style={{ width: `${Math.min(100, ((draft as any)[`strategy_weight_${weight}`] / 2) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {activeTab === "risk" && (
              <>
                <h4 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-500/80">
                  <Shield size={13} />
                  Risk Filters
                </h4>
                <div className="grid gap-3">
                   <SettingRow label="Risk Tolerance" description="Overall aggressiveness of entry signals.">
                    <select
                      value={draft.risk_tolerance}
                      onChange={(e) => updateDraft("risk_tolerance", e.target.value as BotSettings["risk_tolerance"])}
                      className="dashboard-select rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white"
                    >
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                      <option value="degen">Degen</option>
                    </select>
                  </SettingRow>
                  <SettingRow label="Score Threshold" description="Minimum strategy score required to enter a trade.">
                    <input
                      type="number"
                      value={draft.score_threshold}
                      onChange={(e) => updateDraft("score_threshold", parseInt(e.target.value))}
                      className="w-24 rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white text-right"
                    />
                  </SettingRow>
                  <SettingRow label="Max Creator Hold (%)" description="Max percentage of supply held by the creator.">
                    <input
                      type="number"
                      step="0.1"
                      value={draft.max_creator_hold_pct}
                      onChange={(e) => updateDraft("max_creator_hold_pct", parseFloat(e.target.value))}
                      className="w-24 rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white text-right"
                    />
                  </SettingRow>
                  <SettingRow label="Daily Loss Cap (SOL)" description="Stop all entries if cumulative daily P&L hits this loss.">
                    <NumberInput field="daily_loss_cap_sol" step="0.1" />
                  </SettingRow>
                  <SettingRow label="Min Buy Velocity" description="Require minimum observed buy velocity before entries.">
                    <NumberInput field="min_buy_velocity" step="0.01" />
                  </SettingRow>
                  <SettingRow label="Max Sell Pressure" description="Reject entries above this sell-pressure threshold.">
                    <NumberInput field="max_sell_pressure" step="0.01" />
                  </SettingRow>
                  <SettingRow label="Min Metadata Score" description="Reject entries below this metadata quality floor.">
                    <NumberInput field="min_metadata_score" step="0.01" />
                  </SettingRow>
                  <SettingRow label="Entry Confirmation Gate" description="Require early source or launch confirmation before a paper buy can be queued.">
                    <Toggle field="entry_confirmation_enabled" />
                  </SettingRow>
                  <SettingRow label="Gate Buy Velocity" description="Minimum early buy velocity needed for launch confirmation.">
                    <NumberInput field="entry_confirmation_min_buy_velocity" step="0.01" />
                  </SettingRow>
                  <SettingRow label="Gate Sell Pressure" description="Maximum sell pressure allowed for launch confirmation.">
                    <NumberInput field="entry_confirmation_max_sell_pressure" step="0.01" />
                  </SettingRow>
                  <SettingRow label="Gate Metadata Score" description="Minimum metadata score required for launch confirmation.">
                    <NumberInput field="entry_confirmation_min_metadata_score" step="0.01" />
                  </SettingRow>
                  <SettingRow label="Gate Initial Buy SOL" description="Initial buy size that can confirm a fresh launch.">
                    <NumberInput field="entry_confirmation_min_initial_buy_sol" step="0.01" />
                  </SettingRow>
                  <SettingRow label="Gate Price Confidence" description="Minimum accepted price confidence for observation-based confirmation.">
                    <NumberInput field="entry_confirmation_min_price_confidence" step="0.05" />
                  </SettingRow>
                  <SettingRow label="Gate Observed Trades" description="Accepted observed trade updates needed for observation-based confirmation.">
                    <NumberInput field="entry_confirmation_min_observed_trades" className="w-16" />
                  </SettingRow>
                  <SettingRow label="Max Token Age Seconds" description="Reject launches older than this age.">
                    <NumberInput field="max_token_age_seconds" />
                  </SettingRow>
                  <SettingRow label="Filter Honeypots" description="Reject tokens with high honeypot risk indicators.">
                    <Toggle field="filter_honeypots" />
                  </SettingRow>
                  <SettingRow label="Filter Rug Risks" description="Reject tokens with identified rug-pull patterns.">
                    <Toggle field="filter_rug_risk" />
                  </SettingRow>
                  <SettingRow label="Duplicate Symbol Penalty" description="Penalize repeated ticker launches.">
                    <Toggle field="duplicate_symbol_penalty" />
                  </SettingRow>
                  <SettingRow label="Strict Metadata Checks" description="Require stricter metadata quality during scoring.">
                    <Toggle field="strict_metadata_checks" />
                  </SettingRow>
                  <SettingRow label="Stop On Source Degraded" description="Block paper entries when source health is degraded.">
                    <Toggle field="stop_on_source_degraded" />
                  </SettingRow>
                  <SettingRow label="Manual Kill Switch" description="Immediately block new entries when enabled.">
                    <Toggle field="kill_switch_enabled" />
                  </SettingRow>
                  <SettingRow label="Consecutive Loss Halt" description="Enable a stop after repeated losing trades.">
                    <div className="flex items-center gap-2"><Toggle field="max_consecutive_losses_enabled" /><NumberInput field="max_consecutive_losses" className="w-16" /></div>
                  </SettingRow>
                  <SettingRow label="Low Replay Confidence Halt" description="Block entries when replay confidence drops below the configured floor.">
                    <div className="flex items-center gap-2"><Toggle field="halt_on_low_replay_confidence" /><NumberInput field="min_replay_confidence" className="w-16" /></div>
                  </SettingRow>
                </div>
              </>
            )}

            {activeTab === "exits" && (
              <>
                <h4 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-500/80">
                  <TimerReset size={13} />
                  Profit & Loss Controls
                </h4>
                <div className="grid gap-3">
                  <SettingRow label="Take Profit (%)" description="Exit position when target profit is reached.">
                    <input
                      type="number"
                      step="1"
                      value={draft.take_profit_pct}
                      onChange={(e) => updateDraft("take_profit_pct", parseFloat(e.target.value))}
                      className="w-24 rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white text-right"
                    />
                  </SettingRow>
                  <SettingRow label="Stop Loss (%)" description="Exit position if price drops to this limit.">
                    <input
                      type="number"
                      step="1"
                      value={draft.stop_loss_pct}
                      onChange={(e) => updateDraft("stop_loss_pct", parseFloat(e.target.value))}
                      className="w-24 rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white text-right"
                    />
                  </SettingRow>
                  <SettingRow label="Trailing Stop" description="Enable dynamic stop-loss that follows price upwards.">
                    <div className="flex items-center gap-3">
                      <Toggle field="trailing_stop_enabled" />
                      <NumberInput field="trailing_stop_pct" step="0.5" className="w-16" />
                    </div>
                  </SettingRow>
                  <SettingRow label="Break-Even Stop" description="Move stop-loss to entry price after hitting initial profit.">
                     <div className="flex items-center gap-3">
                      <Toggle field="break_even_stop_enabled" />
                      <NumberInput field="break_even_after_profit_pct" step="0.5" className="w-16" />
                    </div>
                  </SettingRow>
                  <SettingRow label="Minimum Hold Seconds" description="Do not exit before this hold duration unless safety rules force it.">
                    <NumberInput field="minimum_hold_time_seconds" />
                  </SettingRow>
                  <SettingRow label="Max Hold Time (Seconds)" description="Force exit position after this duration.">
                    <NumberInput field="max_hold_time_seconds" />
                  </SettingRow>
                  <SettingRow label="Max Position Ticks" description="Force close after this number of monitoring ticks.">
                    <NumberInput field="max_position_ticks" />
                  </SettingRow>
                  <SettingRow label="Partial Take Profit" description="Sell a fraction at an early profit target.">
                    <div className="flex items-center gap-2"><Toggle field="partial_take_profit_enabled" /><NumberInput field="partial_take_profit_pct" step="0.5" className="w-16" /><NumberInput field="partial_take_profit_fraction" step="0.05" className="w-16" /></div>
                  </SettingRow>
                  <SettingRow label="Stalled Trade Exit" description="Exit trades that fail to move after the configured duration.">
                    <div className="flex items-center gap-2"><Toggle field="stalled_trade_exit_enabled" /><NumberInput field="stalled_trade_seconds" className="w-16" /><NumberInput field="stalled_trade_min_move_pct" step="0.5" className="w-16" /></div>
                  </SettingRow>
                  <SettingRow label="Sell Pressure Exit" description="Exit when observed sell pressure exceeds this threshold.">
                    <div className="flex items-center gap-2"><Toggle field="sell_pressure_exit_enabled" /><NumberInput field="sell_pressure_exit_threshold" step="0.01" className="w-16" /></div>
                  </SettingRow>
                  <SettingRow label="Cooldown After Loss" description="Pause new entries after a losing trade.">
                    <div className="flex items-center gap-2"><Toggle field="cooldown_after_loss_enabled" /><NumberInput field="cooldown_after_loss_seconds" className="w-20" /></div>
                  </SettingRow>
                </div>
              </>
            )}

            {activeTab === "simulation" && (
              <>
                <h4 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-500/80">
                  <Gauge size={13} />
                  Environment Tuning
                </h4>
                <div className="grid gap-3">
                  <SettingRow label="RPC URL" description="Custom Solana RPC endpoint for balance and price data.">
                    <input
                      type="text"
                      value={draft.solana_rpc_url}
                      onChange={(e) => updateDraft("solana_rpc_url", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white"
                    />
                  </SettingRow>
                  <SettingRow label="Watched Wallet Address" description="Read-only wallet public key for balance checks.">
                    <input
                      type="text"
                      value={draft.watch_wallet_address}
                      onChange={(e) => updateDraft("watch_wallet_address", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white"
                    />
                  </SettingRow>
                  <SettingRow label="Launch Interval (s)" description="Minimum time between simulated launch events.">
                    <NumberInput field="launch_interval_seconds" step="0.1" />
                  </SettingRow>
                  <SettingRow label="Paper Volatility (%)" description="Simulated price swing magnitude for paper feed.">
                    <NumberInput field="paper_price_volatility_pct" />
                  </SettingRow>
                  <SettingRow label="Future Wallet Cap SOL" description="Paper safety cap for simulated wallet exposure.">
                    <NumberInput field="wallet_balance_cap_sol" step="0.001" />
                  </SettingRow>
                  <SettingRow label="Manual Live Max SOL" description="Legacy audit-only manual request cap.">
                    <NumberInput field="manual_live_max_sol" step="0.001" />
                  </SettingRow>
                  <SettingRow label="Live Caps" description="Required user caps for manual live quote/sign flows.">
                    <div className="grid grid-cols-3 gap-2">
                      <NumberInput field="live_max_trade_sol" step="0.001" className="w-20" />
                      <NumberInput field="live_daily_loss_cap_sol" step="0.001" className="w-20" />
                      <NumberInput field="live_wallet_exposure_cap_sol" step="0.001" className="w-20" />
                      <NumberInput field="live_max_open_positions" className="w-20" />
                      <NumberInput field="live_max_slippage_pct" step="0.1" className="w-20" />
                      <NumberInput field="live_priority_fee_cap_sol" step="0.00001" className="w-20" />
                    </div>
                  </SettingRow>
                  <SettingRow label="Immutable Micro-Pilot Policy" description="Read-only reference. This display cannot raise caps, arm a signer, or enable live trading.">
                    {pilotRiskError ? (
                      <span className="text-xs text-red-400">{pilotRiskError}</span>
                    ) : pilotRiskStatus?.policy ? (
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-zinc-400">
                        <span>Version</span><span className="text-right text-zinc-200">{pilotRiskStatus.policy.policy_version}</span>
                        <span>Reference observation</span><span className="truncate text-right text-zinc-200" title={pilotRiskStatus.policy.reference_observation_id}>{pilotRiskStatus.policy.reference_observation_id}</span>
                        <span>Observed SOL/USD</span><span className="text-right text-zinc-200">${pilotRiskStatus.policy.reference_usd_per_sol}</span>
                        <span>Trade cap</span><span className="text-right text-zinc-200">{pilotRiskStatus.policy.max_trade_sol} SOL</span>
                        <span>Status</span><span className="text-right text-amber-400">configured, zero authority</span>
                      </div>
                    ) : (
                      <span className="text-xs text-zinc-500">No immutable pilot policy is configured.</span>
                    )}
                  </SettingRow>
                  <SettingRow label="Live Signer Mode" description="Browser wallet is manual; local hot wallet is the encrypted local executor; signer daemon remains localhost-gated.">
                    <select value={draft.live_signer_mode} onChange={(e) => updateDraft("live_signer_mode", e.target.value as BotSettings["live_signer_mode"])} className="dashboard-select rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white">
                      <option value="browser_wallet">browser wallet</option>
                      <option value="local_hot_wallet">local hot wallet</option>
                      <option value="local_signer_daemon">local signer daemon</option>
                    </select>
                  </SettingRow>
                  <SettingRow label="Readiness Halt" description="Optionally halt paper entries after enough evidence when readiness is low.">
                    <div className="flex items-center gap-2"><Toggle field="halt_on_low_readiness" /><NumberInput field="min_readiness_score" className="w-16" /></div>
                  </SettingRow>
                  <SettingRow label="Trade Toasts" description="Show popup notifications for buy/sell events.">
                    <Toggle field="enable_trade_toasts" />
                  </SettingRow>
                  <SettingRow label="Compact Token Table" description="Use the denser queue presentation.">
                    <Toggle field="compact_table_mode" />
                  </SettingRow>
                  <SettingRow label="Request Live Trading Unlock" description="UI request flag only; backend environment still controls live execution.">
                    <Toggle field="live_trading_enabled" />
                  </SettingRow>
                  <SettingRow label="Manual Live Request Capture" description="Enable audit capture for manual live requests.">
                    <Toggle field="manual_live_enabled" />
                  </SettingRow>
                  <SettingRow label="Autonomous Live Request" description="Allows the armed local backend to execute only when every autonomy gate passes.">
                    <Toggle field="autonomous_live_enabled" />
                  </SettingRow>
                </div>
              </>
            )}

            {activeTab === "profit-vault" && (
              <>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h4 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-500/80">
                      <Landmark size={13} />
                      Profit Vault Sweep
                    </h4>
                    <p className="mt-2 max-w-3xl text-xs leading-6 text-zinc-400">
                      Profit Vault Sweep only acts on realized live PnL from the live ledger. When the threshold is reached, the armed local hot wallet builds a SOL transfer to your vault wallet, simulates it, and submits only if the simulation passes. Every attempt is stored as a live audit with action <span className="font-mono text-zinc-200">profit_sweep</span>.
                    </p>
                  </div>
                  <Badge variant={draft.profit_sweep_enabled ? "success" : "neutral"}>
                    {draft.profit_sweep_enabled ? "Enabled" : "Disabled"}
                  </Badge>
                </div>

                <section className="rounded-2xl border border-white/5 bg-white/[0.015] p-5">
                  <div className="mb-4 flex items-center gap-2 text-xs font-black text-white">
                    <WalletCards size={15} className="text-amber-500" />
                    Sweep Controls
                  </div>
                  <div className="grid gap-3">
                    <SettingRow label="Enable Auto-Sweep" description="Turns on automatic profit transfer after realized live profit crosses the configured threshold.">
                      <Toggle field="profit_sweep_enabled" />
                    </SettingRow>
                    <SettingRow label="Minimum Profit" description="The sweep will not run until realized live profit reaches this SOL amount. This is a SOL number, not a percentage.">
                      <div className="w-full min-w-0 sm:w-48">
                        <FieldControl label="Minimum profit to sweep" unit="SOL number">
                          <NumberInput field="profit_sweep_min_profit_sol" step="0.001" className="w-full" />
                        </FieldControl>
                      </div>
                    </SettingRow>
                    <SettingRow label="Sweep Mode" description="Choose whether the bot sends a fixed SOL amount or a percentage of realized live profit.">
                      <div className="grid w-full min-w-0 grid-cols-1 gap-3 sm:w-[26rem] sm:grid-cols-2">
                        <FieldControl label="Mode">
                          <select
                            value={draft.profit_sweep_mode}
                            onChange={(e) => updateDraft("profit_sweep_mode", e.target.value as BotSettings["profit_sweep_mode"])}
                            className="dashboard-select h-[30px] w-full rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white"
                          >
                            <option value="fixed_sol">Fixed SOL</option>
                            <option value="percentage">Percentage of profit</option>
                          </select>
                        </FieldControl>
                        {draft.profit_sweep_mode === "percentage" ? (
                          <FieldControl label="Sweep percentage" unit="% number">
                            <NumberInput field="profit_sweep_percentage" step="0.1" className="w-full" />
                          </FieldControl>
                        ) : (
                          <FieldControl label="Fixed sweep amount" unit="SOL number">
                            <NumberInput field="profit_sweep_amount_sol" step="0.001" className="w-full" />
                          </FieldControl>
                        )}
                      </div>
                    </SettingRow>
                    <SettingRow label="Vault Wallet" description="Destination wallet for protected profits. Use a different wallet than the trading hot wallet.">
                      <FieldControl label="Destination wallet" unit="public key">
                        <TextInput field="profit_sweep_destination_wallet" placeholder="Vault wallet public key" />
                      </FieldControl>
                    </SettingRow>
                    <SettingRow label="Reserve And Rate Limits" description="Reserve is a SOL amount. Cooldown and daily cap are plain numbers, not percentages.">
                      <div className="grid w-full min-w-0 grid-cols-1 gap-3 sm:w-[36rem] sm:grid-cols-3">
                        <FieldControl label="Minimum reserve" unit="SOL number">
                          <NumberInput field="profit_sweep_min_reserve_sol" step="0.001" className="w-full" />
                        </FieldControl>
                        <FieldControl label="Cooldown" unit="seconds">
                          <NumberInput field="profit_sweep_cooldown_seconds" className="w-full" />
                        </FieldControl>
                        <FieldControl label="Max sweeps/day" unit="count">
                          <NumberInput field="profit_sweep_max_per_day" className="w-full" />
                        </FieldControl>
                      </div>
                    </SettingRow>
                  </div>
                </section>

                <section className="rounded-2xl border border-white/5 bg-black/20 p-5">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <div>
                      <h5 className="flex items-center gap-2 text-xs font-black text-white">
                        <History size={15} className="text-amber-500" />
                        Sweep History
                      </h5>
                      <p className="mt-1 text-[10px] leading-5 text-zinc-500">Latest recorded profit-sweep audits. Failed attempts stay visible so you can inspect blockers before the next run.</p>
                    </div>
                    <Button variant="ghost" size="sm" onClick={refreshSweepHistory} disabled={sweepHistoryLoading} title="Refresh sweep history">
                      <RefreshCw size={13} />
                    </Button>
                  </div>

                  {sweepHistoryError ? (
                    <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 text-[11px] text-rose-200">
                      {sweepHistoryError}
                    </div>
                  ) : sweepHistoryLoading ? (
                    <div className="space-y-2">
                      {[0, 1, 2].map((item) => (
                        <div key={item} className="h-12 animate-pulse rounded-lg bg-white/[0.04]" />
                      ))}
                    </div>
                  ) : sweepHistory.length === 0 ? (
                    <div className="rounded-xl border border-white/5 bg-white/[0.015] p-4 text-[11px] leading-5 text-zinc-500">
                      No profit sweeps have been recorded yet. Once a sweep is attempted, it will appear here with status, amount, destination, signature, and any errors.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[760px] text-left text-[11px]">
                        <thead className="border-b border-white/10 text-[9px] font-black uppercase tracking-wider text-zinc-500">
                          <tr>
                            <th className="px-2 py-2">Time</th>
                            <th className="px-2 py-2">Status</th>
                            <th className="px-2 py-2 text-right">Amount</th>
                            <th className="px-2 py-2 text-right">Trigger PnL</th>
                            <th className="px-2 py-2">Vault</th>
                            <th className="px-2 py-2">Signature</th>
                            <th className="px-2 py-2">Notes</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                          {sweepHistory.map((audit) => {
                            const status = audit.final_status || audit.status;
                            const destination = audit.quote?.destination_wallet;
                            const realizedPnl = audit.quote?.realized_pnl_sol;
                            const notes = [...(audit.errors || []), ...(audit.warnings || [])].filter(Boolean);
                            return (
                              <tr key={audit.id} className="align-top text-zinc-300">
                                <td className="px-2 py-3 text-zinc-500">{formatMobileTime(audit.created_at)}</td>
                                <td className="px-2 py-3"><Badge variant={statusVariant(status)}>{status}</Badge></td>
                                <td className="px-2 py-3 text-right font-mono text-zinc-100">{formatSol(audit.amount)}</td>
                                <td className="px-2 py-3 text-right font-mono text-emerald-300">{formatSol(realizedPnl)}</td>
                                <td className="px-2 py-3 font-mono" title={String(destination || "")}>{compactAddress(destination)}</td>
                                <td className="px-2 py-3 font-mono" title={audit.transaction_signature}>{compactAddress(audit.transaction_signature)}</td>
                                <td className="px-2 py-3 text-zinc-500">
                                  {notes.length ? notes.slice(0, 2).join("; ") : audit.recommended_action || "Recorded"}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              </>
            )}

            {activeTab === "advanced" && (
              <>
                <h4 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-500/80">
                  <Cpu size={13} />
                  Engine Optimization
                </h4>
                <div className="grid gap-3">
                  <SettingRow label="Source Stale (s)" description="Time before source data is considered disconnected.">
                    <NumberInput field="source_stale_seconds" />
                  </SettingRow>
                  <SettingRow label="Source Max Reconnects" description="Reconnect attempts before source is considered unhealthy.">
                    <NumberInput field="source_max_reconnects" />
                  </SettingRow>
                  <SettingRow label="Backtest Replay Limit" description="Default replay limit for saved token backtests.">
                    <NumberInput field="backtest_replay_limit" />
                  </SettingRow>
                  <SettingRow label="Raw Replay Limit" description="Default replay limit for raw source-event backtests.">
                    <NumberInput field="raw_replay_limit" />
                  </SettingRow>
                  <SettingRow label="Max Trade Subscriptions" description="Maximum active PumpPortal trade subscriptions.">
                    <NumberInput field="max_trade_subscriptions" />
                  </SettingRow>
                  <SettingRow label="Max Trades Per Hour" description="Enable and tune the hourly paper-entry throttle used while collecting evidence. Live hard caps are configured separately.">
                    <div className="flex items-center gap-2">
                      <Toggle field="max_trades_per_hour_enabled" />
                      <NumberInput field="max_trades_per_hour" className="w-20" />
                    </div>
                  </SettingRow>
                  <SettingRow label="Min Price Confidence" description="Minimum confidence score for PumpPortal price hints.">
                    <NumberInput field="min_price_confidence" step="0.05" />
                  </SettingRow>
                  <SettingRow label="Max First Observed Move %" description="Reject impossible first observed price moves above this percentage.">
                    <NumberInput field="max_first_observed_move_pct" step="10" />
                  </SettingRow>
                  <SettingRow label="Rejected Price Streak Guard" description="Stop entries after consecutive rejected price observations.">
                    <div className="flex items-center gap-2"><Toggle field="max_rejected_price_streak_enabled" /><NumberInput field="max_rejected_price_streak" className="w-16" /></div>
                  </SettingRow>
                  <SettingRow label="Paper Fill Delay (Ticks)" description="Ticks to wait before considering a buy order filled.">
                    <NumberInput field="paper_fill_delay_ticks" />
                   </SettingRow>
                   <SettingRow label="Paper Provider Fee (BPS)" description="Simulated PumpPortal Local provider fee in basis points. PumpPortal Local is currently 50 bps.">
                    <NumberInput field="paper_fee_bps" />
                  </SettingRow>
                  <SettingRow label="Paper Priority Fee" description="Simulated Solana priority fee per paper transaction.">
                    <NumberInput field="paper_priority_fee_sol" step="0.000001" />
                  </SettingRow>
                  <SettingRow label="Paper Price Impact %" description="Simulated price impact applied to paper fills.">
                    <NumberInput field="paper_price_impact_pct" step="0.01" />
                  </SettingRow>
                  <SettingRow label="Paper Failed Fill %" description="Simulated failed-fill rate for backtesting realism.">
                    <NumberInput field="paper_failed_fill_pct" step="0.1" />
                  </SettingRow>
                  <SettingRow label="Velocity Slippage" description="Add slippage based on buy velocity.">
                    <Toggle field="velocity_slippage_enabled" />
                  </SettingRow>
                  <SettingRow label="Max Same Creator Buys" description="Limit repeated buys from one creator.">
                    <div className="flex items-center gap-2"><Toggle field="max_same_creator_buys_enabled" /><NumberInput field="max_same_creator_buys" className="w-16" /></div>
                  </SettingRow>
                  <SettingRow label="Use Observed Prices" description="Use PumpPortal trade observations for paper marking.">
                    <Toggle field="use_observed_prices" />
                  </SettingRow>
                  <SettingRow label="Prefer Market-Cap Price" description="Prefer market-cap normalized price hints when available.">
                    <Toggle field="prefer_market_cap_price" />
                  </SettingRow>
                </div>
              </>
            )}

            {activeTab === "security" && (
              <>
                <h4 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-500/80">
                  <KeyRound size={13} />
                  Access Control
                </h4>
                <div className="grid gap-3">
                  <section className="rounded-2xl border border-white/5 bg-white/[0.01] p-5">
                    <h5 className="mb-3 text-xs font-bold text-white flex items-center gap-2">
                      <Lock size={14} className="text-zinc-500" />
                      Update Password
                    </h5>
                    <div className="space-y-3">
                      <input
                        type="password"
                        placeholder="Current Password"
                        value={currentPassword}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-black px-3 py-2 text-xs text-white"
                      />
                      <input
                        type="password"
                        placeholder="New Password (min 8 chars)"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-black px-3 py-2 text-xs text-white"
                      />
                      <Button 
                        variant="secondary" 
                        size="sm" 
                        className="w-full"
                        onClick={async () => {
                          try {
                            await updatePassword(currentPassword, newPassword);
                            setSecurityMessage("Password updated successfully.");
                          } catch (err: any) {
                            setSecurityMessage(`Error: ${err.message}`);
                          }
                        }}
                      >
                        Update Credentials
                      </Button>
                    </div>
                  </section>

                  <section className="rounded-2xl border border-white/5 bg-white/[0.01] p-5">
                    <h5 className="mb-3 text-xs font-bold text-white flex items-center gap-2">
                      <Smartphone size={14} className="text-zinc-500" />
                      Two-Factor Authentication
                    </h5>
                    <div className="space-y-4">
                      {totpSetup ? (
                        <div className="flex flex-col items-center gap-3">
                          <div className="rounded-xl bg-white p-2">
                            <img 
                              alt="QR Code" 
                              src={`https://api.qrserver.com/v1/create-qr-code/?size=140x140&data=${encodeURIComponent(totpSetup.otpauth_url)}`} 
                              className="h-32 w-32"
                            />
                          </div>
                          <p className="text-[9px] font-mono text-zinc-500">Secret: {totpSetup.secret}</p>
                          <div className="flex w-full gap-2">
                            <input
                              type="text"
                              placeholder="6-digit code"
                              value={totpCode}
                              onChange={(e) => setTotpCode(e.target.value)}
                              className="flex-1 rounded-lg border border-white/10 bg-black px-3 py-2 text-xs text-white"
                            />
                            <Button 
                              size="sm"
                              onClick={async () => {
                                try {
                                  await verifyTotp(totpSetup.secret, totpCode);
                                  setSecurityMessage("2FA enabled successfully.");
                                  setTotpSetup(null);
                                } catch (err: any) {
                                  setSecurityMessage(`Error: ${err.message}`);
                                }
                              }}
                            >
                              Verify
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex gap-2">
                          <Button 
                            variant="secondary" 
                            size="sm" 
                            className="flex-1"
                            onClick={async () => {
                              try {
                                const setup = await setupTotp();
                                setTotpSetup(setup);
                              } catch (err: any) {
                                setSecurityMessage(`Error: ${err.message}`);
                              }
                            }}
                          >
                            Setup 2FA
                          </Button>
                          <Button 
                            variant="danger" 
                            size="sm" 
                            className="flex-1"
                            onClick={async () => {
                              try {
                                await disableTotp();
                                setSecurityMessage("2FA disabled.");
                              } catch (err: any) {
                                setSecurityMessage(`Error: ${err.message}`);
                              }
                            }}
                          >
                            Disable 2FA
                          </Button>
                        </div>
                      )}
                    </div>
                  </section>

                  <section className="rounded-2xl border border-white/5 bg-white/[0.01] p-5">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <h5 className="text-xs font-bold text-white flex items-center gap-2">
                        <Smartphone size={14} className="text-zinc-500" />
                        Mobile Devices
                      </h5>
                      <Button variant="ghost" size="sm" onClick={refreshMobileDevices} disabled={mobileLoading} title="Refresh mobile devices">
                        <RefreshCw size={13} />
                      </Button>
                    </div>
                    <div className="space-y-4">
                      <div className="flex gap-2">
                        <input
                          type="url"
                          placeholder="Private tunnel API base URL"
                          value={mobileApiBaseUrl}
                          onChange={(e) => setMobileApiBaseUrl(e.target.value)}
                          className="h-9 min-w-0 flex-1 rounded-lg border border-white/10 bg-black px-3 text-xs text-white placeholder-zinc-600"
                        />
                        <Button size="sm" variant="outline" onClick={handleStartMobilePairing} disabled={mobileLoading} className="gap-2">
                          <QrCode size={13} />
                          Pair
                        </Button>
                      </div>

                      {mobilePairing && (
                        <div className="grid gap-4 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 sm:grid-cols-[auto_1fr]">
                          <div className="flex items-center justify-center rounded-lg bg-white p-2">
                            {mobileQrDataUrl ? (
                              <img src={mobileQrDataUrl} alt="Mobile pairing QR code" className="h-36 w-36" />
                            ) : (
                              <QrCode className="h-16 w-16 text-zinc-900" />
                            )}
                          </div>
                          <div className="min-w-0 space-y-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="warning">Expires {formatMobileTime(mobilePairing.expires_at)}</Badge>
                              {mobilePairing.dashboard_totp_enabled ? <Badge variant="success">TOTP</Badge> : <Badge variant="neutral">TOTP off</Badge>}
                            </div>
                            <div>
                              <span className="text-[10px] font-black uppercase tracking-wider text-zinc-500">Manual Code</span>
                              <p className="mt-1 font-mono text-2xl font-black tracking-[0.22em] text-amber-300">{mobilePairing.manual_code}</p>
                            </div>
                            <p className="break-all text-[10px] leading-5 text-zinc-400">{mobilePairing.api_base_url || "Set MOBILE_PUBLIC_API_BASE_URL or enter the private tunnel URL before pairing."}</p>
                            <div className="flex flex-wrap gap-2">
                              <Button size="sm" variant="secondary" onClick={handleCopyMobilePayload} className="gap-2">
                                <Copy size={13} />
                                Payload
                              </Button>
                              <span className="flex items-center text-[10px] text-zinc-500">{mobilePairing.pairing_security_note}</span>
                            </div>
                          </div>
                        </div>
                      )}

                      <div className="space-y-2">
                        {mobileDevices.length === 0 ? (
                          <div className="rounded-xl border border-white/5 bg-black/20 p-4 text-[10px] text-zinc-500">
                            No paired mobile devices.
                          </div>
                        ) : (
                          mobileDevices.map((device) => {
                            const revoked = Boolean(device.revoked_at);
                            return (
                              <div key={device.id} className="flex flex-col gap-3 rounded-xl border border-white/5 bg-black/20 p-4 sm:flex-row sm:items-center sm:justify-between">
                                <div className="min-w-0">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="truncate text-xs font-black text-white">{device.name || "Mobile device"}</span>
                                    <Badge variant={revoked ? "danger" : "success"}>{revoked ? "Revoked" : "Active"}</Badge>
                                    <Badge variant="neutral">{device.platform || "unknown"}</Badge>
                                  </div>
                                  <p className="mt-2 text-[10px] leading-5 text-zinc-500">
                                    Last seen {formatMobileTime(device.last_seen_at)} | Scopes {device.scopes.join(", ")}
                                  </p>
                                </div>
                                <Button
                                  variant="danger"
                                  size="sm"
                                  onClick={() => handleRevokeMobileDevice(device)}
                                  disabled={mobileLoading || revoked}
                                  className="gap-2"
                                >
                                  <Ban size={13} />
                                  Revoke
                                </Button>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </div>
                  </section>

                  {securityMessage && (
                    <div className="flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-[10px] text-amber-500">
                      <AlertTriangle size={14} />
                      {securityMessage}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
};
