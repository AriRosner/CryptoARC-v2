import React, { useState, useMemo } from "react";
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
  KeyRound
} from "lucide-react";
import { Modal } from "./Modal";
import { Button } from "./Button";
import { Badge } from "./Badge";
import { cn } from "./utils";
import { updatePassword, setupTotp, verifyTotp, disableTotp } from "../api";
import type { BotSettings } from "../types";

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
}> = ({ label, description, children }) => (
  <div className="flex flex-col gap-2 rounded-xl border border-white/5 bg-white/[0.01] p-4 transition-colors hover:bg-white/[0.03]">
    <div className="flex items-center justify-between gap-4">
      <span className="text-xs font-bold text-zinc-300">{label}</span>
      <div className="flex-shrink-0">{children}</div>
    </div>
    {description && <p className="text-[10px] text-zinc-500 leading-relaxed">{description}</p>}
  </div>
);

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
  if (settings.max_first_observed_move_pct > 1000) warnings.push("Very high first-move limits can let unit mismatches distort P&L.");
  if (settings.live_trading_enabled) warnings.push("Live trading request is set, but backend execution remains blocked unless explicitly enabled by environment.");
  return warnings;
}

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
      type="number"
      step={step}
      value={Number(draft[field] ?? 0)}
      onChange={(e) => updateNumber(field, e.target.value)}
      className={`${className} rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white text-right`}
    />
  );

  const Toggle = ({ field }: { field: keyof BotSettings }) => (
    <input
      type="checkbox"
      checked={Boolean(draft[field])}
      onChange={(e) => updateDraft(field, e.target.checked as never)}
      className="h-4 w-4 rounded border-white/10 bg-black/40 text-amber-500"
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

  const tabs = [
    { id: "source", label: "Source", icon: Database, keywords: "source launch pumpportal mock detect" },
    { id: "strategy", label: "Strategy", icon: Target, keywords: "strategy profile size slippage speed open positions weights" },
    { id: "risk", label: "Risk", icon: Shield, keywords: "risk tolerance score creator hold loss honeypot rug age trades cooldown" },
    { id: "exits", label: "Exits", icon: Clock, keywords: "exit profit loss hold time ticks trailing partial break even stalled pressure" },
    { id: "simulation", label: "Simulation", icon: Gauge, keywords: "simulation launch interval volatility wallet cap rpc address toasts live mode" },
    { id: "advanced", label: "Advanced", icon: SlidersHorizontal, keywords: "advanced stale reconnect backtest subscriptions confidence move market cap price impact fill" },
    { id: "security", label: "Security", icon: Lock, keywords: "security password 2fa totp authenticator" }
  ];

  const filteredTabs = useMemo(() => {
    if (!searchQuery) return tabs;
    const query = searchQuery.toLowerCase();
    return tabs.filter(tab => 
      tab.label.toLowerCase().includes(query) || 
      tab.keywords.toLowerCase().includes(query)
    );
  }, [searchQuery]);
  const navScrollable = filteredTabs.length > 8;

  const activeTabExists = filteredTabs.some(t => t.id === activeTab);
  React.useEffect(() => {
    if (!activeTabExists && filteredTabs.length > 0) {
      setActiveTab(filteredTabs[0].id);
    }
  }, [filteredTabs, activeTabExists]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="System Configuration"
      description="Fine-tune your sniper bot's behavior and risk parameters."
      className="max-w-4xl"
    >
      <div className="flex h-[600px] gap-6">
        <div className="flex w-52 flex-col space-y-1 border-r border-white/5 pr-4">
          <div className="relative mb-4">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              placeholder="Search..."
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
                  <SettingRow label="Live Signer Mode" description="Browser wallet works now; local signer remains future-gated.">
                    <select value={draft.live_signer_mode} onChange={(e) => updateDraft("live_signer_mode", e.target.value as BotSettings["live_signer_mode"])} className="dashboard-select rounded-lg border border-white/10 bg-black px-2 py-1 text-xs text-white">
                      <option value="browser_wallet">browser wallet</option>
                      <option value="local_signer_daemon">local signer daemon later</option>
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
                  <SettingRow label="Autonomous Live Request" description="Future-only request flag; no autonomous executor is enabled.">
                    <Toggle field="autonomous_live_enabled" />
                  </SettingRow>
                </div>
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
                   <SettingRow label="Paper Fee (BPS)" description="Simulated execution fee in basis points.">
                    <NumberInput field="paper_fee_bps" />
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
