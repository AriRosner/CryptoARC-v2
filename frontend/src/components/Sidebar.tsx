import React from "react";
import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  Bot,
  Database,
  History,
  Shield,
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
  status: "running" | "stopped" | "starting";
  apiState: string;
  onStart: () => void;
  onStop: () => void;
  onSettingsOpen: () => void;
  onLiveWalletOpen: () => void;
  walletPublicKey: string;
  walletBalance: number | null;
}

const NavItem: React.FC<{
  id: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  onClick: () => void;
}> = ({ id, label, icon: Icon, active, onClick }) => (
  <button
    onClick={onClick}
    className={cn(
      "group relative flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm font-bold transition-all duration-200",
      active
        ? "bg-white/10 text-white shadow-lg shadow-black/20"
        : "text-zinc-400 hover:bg-white/5 hover:text-white"
    )}
  >
    <Icon size={18} className={cn("transition-colors", active ? "text-amber-500" : "text-zinc-500 group-hover:text-amber-500")} />
    {label}
    {active && (
      <motion.div
        layoutId="activeNav"
        className="absolute left-0 h-6 w-1 rounded-r-full bg-amber-500"
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
  walletBalance
}) => {
  const navItems = [
    { id: "monitor", label: "Monitor", icon: Activity },
    { id: "analysis", label: "Analysis", icon: BarChart3 },
    { id: "backtests", label: "Backtests", icon: History },
    { id: "review", label: "Trade Review", icon: Target },
    { id: "data", label: "Project Data", icon: Database }
  ];

  return (
    <aside className="fixed inset-y-0 left-0 z-40 w-[310px] border-r border-white/5 bg-[#08090f]/80 backdrop-blur-2xl">
      <div className="flex h-full flex-col p-6">
        <div className="mb-10 flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-400 to-amber-600 shadow-xl shadow-amber-500/20">
            <Bot size={28} className="text-[#160f08]" strokeWidth={2.5} />
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tight text-white uppercase italic">CryptoArc</h1>
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Sniper Bot v2.0</p>
          </div>
        </div>

        <div className="mb-8 space-y-1">
          {navItems.map((item) => (
            <NavItem
              key={item.id}
              {...item}
              active={activePage === item.id}
              onClick={() => setActivePage(item.id)}
            />
          ))}
        </div>

        <div className="mt-auto space-y-4">
          <Card className="border-amber-500/20 bg-amber-500/[0.03] p-4" hover={false}>
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Status</span>
              <Badge variant={apiState === "connected" ? "success" : "danger"}>
                {apiState}
              </Badge>
            </div>
            <div className="mb-4">
              <div className="flex items-center gap-2">
                <div className={cn("h-2 w-2 rounded-full", status === "running" ? "bg-emerald-500 animate-pulse" : "bg-rose-500")} />
                <span className="text-sm font-bold text-white capitalize">{status}</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button
                size="sm"
                variant={status === "running" ? "danger" : "primary"}
                onClick={status === "running" ? onStop : onStart}
                className="w-full"
              >
                {status === "running" ? "Stop" : "Start"}
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
          </Card>

          <Card className="p-4" hover={false}>
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
          </Card>
        </div>
      </div>
    </aside>
  );
};
