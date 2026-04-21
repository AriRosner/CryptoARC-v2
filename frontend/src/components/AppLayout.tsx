import React from "react";
import { motion, AnimatePresence } from "framer-motion";
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
  onLiveWalletOpen: () => void;
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
  onLiveWalletOpen,
  walletPublicKey,
  walletBalance,
  toasts
}) => {
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(() => window.localStorage.getItem("cryptoarc_sidebar_collapsed") === "true");
  const sidebarWidth = sidebarCollapsed ? 92 : 310;

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
        onLiveWalletOpen={onLiveWalletOpen}
        walletPublicKey={walletPublicKey}
        walletBalance={walletBalance}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
      />

      <motion.main
        layout
        className="relative flex-1 p-8"
        animate={{ marginLeft: sidebarWidth }}
        transition={{ type: "spring", stiffness: 400, damping: 32 }}
      >
        <AnimatePresence mode="wait">
          <motion.div
            key={activePage}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
          >
            {children}
          </motion.div>
        </AnimatePresence>
      </motion.main>

      {/* Toast Notifications */}
      <div className="fixed right-6 top-6 z-50 flex flex-col gap-3 w-80">
        <AnimatePresence>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              initial={{ opacity: 0, x: 50, scale: 0.9 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 20, scale: 0.95 }}
              className="group relative overflow-hidden rounded-xl border border-white/10 bg-[#10121c]/90 p-4 shadow-2xl backdrop-blur-xl"
            >
              <div className="absolute inset-y-0 left-0 w-1 bg-amber-500" />
              <p className="text-xs font-bold text-white leading-tight">{toast.message}</p>
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
