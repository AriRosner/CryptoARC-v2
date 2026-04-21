import React from "react";
import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  Bot,
  ChevronLeft,
  ChevronRight,
  Database,
  History,
  Play,
  Shield,
  Square,
  Target,
  Wallet,
  LucideIcon
} from "lucide-react";
import { Card } from "./Card";
import { Button } from "./Button";
import { Badge } from "./Badge";
import { cn } from "./utils";

interface SidebarProps {
  activePage: string;
  setActivePage: (page: any) => void;
  status: "running" | "stopped" | "starting" | "stopping";
  apiState: string;
  onStart: () => void;
  onStop: () => void;
  onSettingsOpen: () => void;
  onLiveWalletOpen: () => void;
  walletPublicKey: string;
  walletBalance: number | null;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

const Tooltip: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="group relative flex overflow-visible">
    {children}
    <div className="pointer-events-none absolute left-[calc(100%+12px)] top-1/2 z-[90] -translate-y-1/2 whitespace-nowrap rounded-lg border border-white/10 bg-[#0f121c]/98 px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wider text-zinc-200 opacity-0 shadow-2xl shadow-black/40 transition-all duration-200 group-hover:opacity-100">
      {label}
    </div>
  </div>
);

const NavItem: React.FC<{
  id: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  onClick: () => void;
  collapsed: boolean;
}> = ({ id, label, icon: Icon, active, onClick, collapsed }) => (
  <button
    title={collapsed ? label : undefined}
    onClick={onClick}
    className={cn(
      "group relative flex w-full items-center rounded-xl text-sm font-bold transition-all duration-200",
      collapsed ? "mx-auto h-12 w-12 justify-center px-0 py-0" : "gap-3 px-4 py-3",
      active
        ? "bg-white/10 text-white shadow-lg shadow-black/20"
        : "text-zinc-400 hover:bg-white/5 hover:text-white"
    )}
  >
    <Icon size={18} className={cn("transition-colors", active ? "text-amber-500" : "text-zinc-500 group-hover:text-amber-500")} />
    {!collapsed ? label : null}
    {active && (
      <motion.div
        layoutId="activeNav"
        className={cn("absolute h-6 rounded-full bg-amber-500", collapsed ? "left-1/2 top-1 -translate-x-1/2 w-6 h-1 rounded-b-full rounded-t-none" : "left-0 w-1 rounded-r-full")}
      />
    )}
  </button>
);

export const Sidebar: React.FC<SidebarProps> = ({
  activePage,
  setActivePage,
  status,
  apiState,
  onStart,
  onStop,
  onSettingsOpen,
  onLiveWalletOpen,
  walletPublicKey,
  walletBalance,
  collapsed,
  onToggleCollapsed
}) => {
  const statusPending = status === "starting" || status === "stopping";
  const statusTone = status === "running" || status === "starting" ? "bg-emerald-500 animate-pulse" : status === "stopping" ? "bg-amber-500 animate-pulse" : "bg-rose-500";
  const actionLabel = status === "running" ? "Stop" : status === "stopping" ? "Stopping..." : status === "starting" ? "Starting..." : "Start";
  const compactApiLabel = apiState === "connected" ? "Linked" : apiState === "offline" ? "Offline" : apiState;
  const compactStatusLabel = status === "running" ? "Running" : status === "stopped" ? "Stopped" : status === "starting" ? "Starting" : "Stopping";
  const navItems = [
    { id: "monitor", label: "Monitor", icon: Activity },
    { id: "analysis", label: "Analysis", icon: BarChart3 },
    { id: "backtests", label: "Backtests", icon: History },
    { id: "review", label: "Trade Review", icon: Target },
    { id: "data", label: "Project Data", icon: Database }
  ];

  return (
    <motion.aside
      animate={{ width: collapsed ? 92 : 310 }}
      transition={{ type: "spring", stiffness: 400, damping: 32 }}
      className="fixed inset-y-0 left-0 z-[70] overflow-visible border-r border-white/5 bg-[#08090f]/80 backdrop-blur-2xl"
    >
      <div className={cn("flex h-full flex-col overflow-visible", collapsed ? "items-center p-3" : "p-6")}>
        <div className={cn("mb-8 flex items-center", collapsed ? "w-full flex-col gap-3" : "gap-3")}>
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-400 to-amber-600 shadow-xl shadow-amber-500/20">
            <Bot size={28} className="text-[#160f08]" strokeWidth={2.5} />
          </div>
          {!collapsed ? (
            <div className="min-w-0">
              <h1 className="text-xl font-black tracking-tight text-white uppercase italic">CryptoArc</h1>
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Sniper Bot v2.0</p>
            </div>
          ) : null}
          {collapsed ? (
            <Tooltip label="Expand Sidebar">
              <button
                type="button"
                onClick={onToggleCollapsed}
                className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-zinc-400 transition-colors hover:border-amber-500/30 hover:text-amber-300"
              >
                <ChevronRight size={16} />
              </button>
            </Tooltip>
          ) : (
            <button
              type="button"
              onClick={onToggleCollapsed}
              title="Collapse sidebar"
              className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-zinc-400 transition-colors hover:border-amber-500/30 hover:text-amber-300"
            >
              <ChevronLeft size={16} />
            </button>
          )}
        </div>

        <div className={cn("mb-8", collapsed ? "w-full space-y-1" : "space-y-1")}>
          {navItems.map((item) => (
            collapsed ? (
              <Tooltip key={item.id} label={item.label}>
                <div className="flex w-full justify-center">
                  <NavItem
                    {...item}
                    active={activePage === item.id}
                    onClick={() => setActivePage(item.id)}
                    collapsed={collapsed}
                  />
                </div>
              </Tooltip>
            ) : (
              <NavItem
                key={item.id}
                {...item}
                active={activePage === item.id}
                onClick={() => setActivePage(item.id)}
                collapsed={collapsed}
              />
            )
          ))}
        </div>

        <div className={cn("mt-auto", collapsed ? "w-full space-y-3" : "space-y-4")}>
          <Card className={cn("border-amber-500/20 bg-amber-500/[0.03]", collapsed ? "mx-auto w-[64px] px-2 py-3" : "p-4")} hover={false}>
            {!collapsed ? (
              <>
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Status</span>
                  <Badge variant={apiState === "connected" ? "success" : "danger"}>
                    {apiState}
                  </Badge>
                </div>
                <div className="mb-4">
                  <div className="flex items-center gap-2">
                    <div className={cn("h-2 w-2 rounded-full", statusTone)} />
                    <span className="text-sm font-bold text-white capitalize">{status}</span>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    size="sm"
                    variant={status === "running" || status === "stopping" ? "danger" : "primary"}
                    onClick={status === "running" ? onStop : onStart}
                    className="w-full"
                    disabled={statusPending}
                  >
                    {actionLabel}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={onSettingsOpen}
                    className="w-full"
                  >
                    Settings
                  </Button>
                </div>
              </>
            ) : (
              <div className="flex min-w-0 flex-col items-center justify-center gap-2">
                <Tooltip label={`Bot ${compactStatusLabel}`}>
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-white/10 bg-black/20">
                    <div className={cn("h-2.5 w-2.5 rounded-full", statusTone)} />
                  </div>
                </Tooltip>
                <Tooltip label={`API ${compactApiLabel}`}>
                  <div className={cn(
                    "flex h-6 w-10 items-center justify-center rounded-md border px-1 text-[9px] font-bold uppercase tracking-wider",
                    apiState === "connected" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-rose-500/20 bg-rose-500/10 text-rose-300"
                  )}>
                    {apiState === "connected" ? "API" : "OFF"}
                  </div>
                </Tooltip>
                <div className="flex flex-col items-center gap-2">
                  <Tooltip label={actionLabel}>
                    <div>
                      <Button
                        size="icon"
                        variant={status === "running" || status === "stopping" ? "danger" : "primary"}
                        onClick={status === "running" ? onStop : onStart}
                        className="h-9 w-9"
                        disabled={statusPending}
                      >
                        {status === "running" || status === "stopping" ? <Square size={12} /> : <Play size={12} />}
                      </Button>
                    </div>
                  </Tooltip>
                  <Tooltip label="Settings">
                    <div>
                      <Button size="icon" variant="secondary" onClick={onSettingsOpen} className="h-9 w-9">
                        <Shield size={14} />
                      </Button>
                    </div>
                  </Tooltip>
                </div>
              </div>
            )}
          </Card>

          <Card className={cn(collapsed ? "mx-auto w-[64px] px-2 py-3" : "p-4")} hover={false}>
            {!collapsed ? (
              <>
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Live Wallet</span>
                  <Wallet size={14} className="text-zinc-500" />
                </div>
                {walletPublicKey ? (
                  <div className="space-y-2">
                    <div className="rounded-lg bg-white/5 p-2 font-mono text-[10px] text-zinc-400">
                      {walletPublicKey.slice(0, 8)}...{walletPublicKey.slice(-8)}
                    </div>
                    <div className="flex items-center justify-between text-xs font-bold">
                      <span className="text-zinc-500">Balance</span>
                      <span className="text-white">{walletBalance?.toFixed(3) ?? "0.000"} SOL</span>
                    </div>
                  </div>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full border-amber-500/30 text-amber-500 hover:bg-amber-500/10"
                    onClick={onLiveWalletOpen}
                  >
                    Connect Wallet
                  </Button>
                )}
                {walletPublicKey ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="mt-3 w-full"
                    onClick={onLiveWalletOpen}
                  >
                    Manage Live Wallet
                  </Button>
                ) : null}
              </>
            ) : (
              <div className="flex min-w-0 flex-col items-center justify-center gap-2">
                <Tooltip label={walletPublicKey ? `Wallet ${walletPublicKey}` : "Live Wallet"}>
                  <button
                    type="button"
                    onClick={onLiveWalletOpen}
                    className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-zinc-400 transition-colors hover:border-amber-500/30 hover:text-amber-300"
                  >
                    <Wallet size={16} />
                  </button>
                </Tooltip>
                <div className="min-h-[1.1rem] text-center text-[9px] font-bold uppercase tracking-wider leading-none text-zinc-500">
                  {walletPublicKey ? "Live" : "None"}
                </div>
                {walletPublicKey ? (
                  <div className="text-center text-[10px] font-black leading-none text-white">
                    {walletBalance?.toFixed(2) ?? "0.00"}
                    <span className="ml-1 text-[8px] font-bold uppercase tracking-wider text-zinc-500">SOL</span>
                  </div>
                ) : (
                  <div className="text-center text-[9px] font-bold uppercase tracking-wider leading-none text-zinc-600">Wallet</div>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </motion.aside>
  );
};

