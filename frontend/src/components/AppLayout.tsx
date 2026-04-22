import React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sidebar } from "./Sidebar";

interface AppLayoutProps {
  children: React.ReactNode;
  activePage: string;
  setActivePage: (page: any) => void;
  status: "running" | "stopped" | "starting" | "stopping";
  apiState: string;
  onStart: () => void;
  onStop: () => void;
  onSettingsOpen: () => void;
  onAddWalletOpen: () => void;
  onManageWalletOpen: () => void;
  walletOptions: Array<{ value: string; label: string }>;
  activeWallet: string;
  canRemoveActiveWallet: boolean;
  onActiveWalletChange: (wallet: string) => void;
  onRemoveWallet: () => void;
  walletPublicKey: string;
  walletBalance: number | null;
  toasts: Array<{ id: string; created_at: string; message: string; level: string }>;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  children,
  activePage,
  setActivePage,
  status,
  apiState,
  onStart,
  onStop,
  onSettingsOpen,
  onAddWalletOpen,
  onManageWalletOpen,
  walletOptions,
  activeWallet,
  canRemoveActiveWallet,
  onActiveWalletChange,
  onRemoveWallet,
  walletPublicKey,
  walletBalance,
  toasts
}) => {
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(() => window.localStorage.getItem("cryptoarc_sidebar_collapsed") === "true");
  const sidebarWidth = sidebarCollapsed ? 92 : 310;

  const toastTone = (level: string) => {
    if (level === "success") {
      return {
        border: "border-emerald-500/20",
        rail: "bg-emerald-500",
        title: "text-emerald-100"
      };
    }
    if (level === "danger" || level === "error") {
      return {
        border: "border-rose-500/20",
        rail: "bg-rose-500",
        title: "text-rose-100"
      };
    }
    return {
      border: "border-amber-500/20",
      rail: "bg-amber-500",
      title: "text-white"
    };
  };

  React.useEffect(() => {
    window.localStorage.setItem("cryptoarc_sidebar_collapsed", String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  return (
    <div className="flex min-h-screen bg-[#08090f] text-zinc-100 selection:bg-amber-500/30 selection:text-white">
      {/* Dynamic Background */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-8%] left-[-8%] h-[30%] w-[30%] rounded-full bg-amber-500/4 blur-[64px]" />
        <div className="absolute bottom-[8%] right-[8%] h-[24%] w-[24%] rounded-full bg-emerald-500/4 blur-[64px]" />
        <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:40px_40px] opacity-25" />
      </div>

      <Sidebar
        activePage={activePage}
        setActivePage={setActivePage}
        status={status}
        apiState={apiState}
        onStart={onStart}
        onStop={onStop}
        onSettingsOpen={onSettingsOpen}
        onAddWalletOpen={onAddWalletOpen}
        onManageWalletOpen={onManageWalletOpen}
        walletOptions={walletOptions}
        activeWallet={activeWallet}
        canRemoveActiveWallet={canRemoveActiveWallet}
        onActiveWalletChange={onActiveWalletChange}
        onRemoveWallet={onRemoveWallet}
        walletPublicKey={walletPublicKey}
        walletBalance={walletBalance}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
      />

      <main className="relative flex-1 p-8" style={{ marginLeft: sidebarWidth }}>
        {children}
      </main>

      {/* Toast Notifications */}
      <div className="fixed right-6 top-6 z-50 flex flex-col gap-3 w-80">
        <AnimatePresence>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              initial={{ opacity: 0, x: 50, scale: 0.9 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 20, scale: 0.95 }}
              className={`group relative overflow-hidden rounded-xl border bg-[#10121c]/90 p-4 shadow-2xl backdrop-blur-xl ${toastTone(toast.level).border}`}
            >
              <div className={`absolute inset-y-0 left-0 w-1 ${toastTone(toast.level).rail}`} />
              <p className={`text-xs font-bold leading-tight ${toastTone(toast.level).title}`}>{toast.message}</p>
              <p className="mt-1 text-[10px] text-zinc-500">
                {new Date(toast.created_at).toLocaleTimeString()}
              </p>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
};
