import React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Bell, CheckCheck } from "lucide-react";
import { Sidebar } from "./Sidebar";
import type { LatencyStatus } from "../types";

interface AppLayoutProps {
  children: React.ReactNode;
  activePage: string;
  setActivePage: (page: any) => void;
  status: "running" | "stopped" | "starting" | "stopping" | "connecting" | "reconnecting" | "disconnected";
  apiState: string;
  latencyStatus: LatencyStatus | null;
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
  notifications: Array<{ id: string; created_at: string; message: string; level: string; subsystem?: string; operator_action?: string; session_id?: string }>;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  children,
  activePage,
  setActivePage,
  status,
  apiState,
  latencyStatus,
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
  toasts,
  notifications
}) => {
  const shouldReduceMotion = useReducedMotion();
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(() => window.localStorage.getItem("cryptoarc_sidebar_collapsed") === "true");
  const [compactViewport, setCompactViewport] = React.useState(() => window.matchMedia("(max-width: 900px)").matches);
  const [notificationsOpen, setNotificationsOpen] = React.useState(false);
  const [lastReadNotificationAt, setLastReadNotificationAt] = React.useState(() => window.localStorage.getItem("cryptoarc_notifications_read_at") || "");
  const effectiveSidebarCollapsed = compactViewport || sidebarCollapsed;
  const sidebarWidth = effectiveSidebarCollapsed ? (compactViewport ? 76 : 92) : 310;

  React.useEffect(() => {
    document.documentElement.style.setProperty("--cryptoarc-sidebar-width", `${sidebarWidth}px`);
    return () => {
      document.documentElement.style.removeProperty("--cryptoarc-sidebar-width");
    };
  }, [sidebarWidth]);

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

  React.useEffect(() => {
    const query = window.matchMedia("(max-width: 900px)");
    const handleChange = () => setCompactViewport(query.matches);
    handleChange();
    query.addEventListener("change", handleChange);
    return () => query.removeEventListener("change", handleChange);
  }, []);

  const sortedNotifications = React.useMemo(
    () => [...notifications].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).slice(0, 20),
    [notifications]
  );
  const unreadCount = React.useMemo(
    () => sortedNotifications.filter((item) => !lastReadNotificationAt || item.created_at > lastReadNotificationAt).length,
    [lastReadNotificationAt, sortedNotifications]
  );
  const criticalCount = sortedNotifications.filter((item) => item.level === "danger" || item.level === "error" || item.level === "warning").length;
  const markNotificationsRead = () => {
    const latest = sortedNotifications[0]?.created_at || new Date().toISOString();
    setLastReadNotificationAt(latest);
    window.localStorage.setItem("cryptoarc_notifications_read_at", latest);
  };

  return (
    <div className="min-h-screen overflow-x-hidden bg-[#08090f] text-zinc-100 selection:bg-amber-500/30 selection:text-white">
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
        latencyStatus={latencyStatus}
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
        collapsed={effectiveSidebarCollapsed}
        onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
        compactViewport={compactViewport}
      />

      <main
        className="relative min-w-0 overflow-x-hidden p-4 sm:p-5 lg:p-8"
        style={{
          marginLeft: sidebarWidth,
          width: `calc(100vw - ${sidebarWidth}px)`,
          maxWidth: `calc(100vw - ${sidebarWidth}px)`,
          boxSizing: "border-box"
        }}
      >
        <div className="fixed right-3 top-3 z-40 flex items-center gap-2 sm:right-6 sm:top-6">
          <button
            type="button"
            onClick={() => setNotificationsOpen((current) => !current)}
            className="relative inline-flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-[#10121c]/95 text-zinc-300 shadow-2xl shadow-black/30 backdrop-blur-xl transition hover:border-amber-500/40 hover:text-white"
            aria-label="Open notification center"
          >
            <Bell size={17} />
            {unreadCount ? (
              <span className="absolute -right-1 -top-1 min-w-5 rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-black text-black">{unreadCount}</span>
            ) : null}
          </button>
        </div>

        <AnimatePresence>
          {notificationsOpen ? (
            <motion.div
              initial={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 420, damping: 34 }}
              className="fixed right-3 top-16 z-50 w-[min(360px,calc(100vw-1.5rem))] overflow-hidden rounded-xl border border-white/10 bg-[#10121c]/98 shadow-2xl shadow-black/50 backdrop-blur-xl sm:right-6 sm:top-20"
              role="dialog"
              aria-label="Notification Center"
            >
              <div className="flex items-center justify-between border-b border-white/10 p-4">
                <div>
                  <p className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Notifications</p>
                  <p className="mt-1 text-xs font-bold text-zinc-300">{criticalCount} recent operator events need attention</p>
                </div>
                <button
                  type="button"
                  onClick={markNotificationsRead}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 text-zinc-400 transition hover:border-emerald-500/40 hover:text-emerald-200"
                  aria-label="Mark notifications read"
                >
                  <CheckCheck size={15} />
                </button>
              </div>
              <div className="max-h-[460px] overflow-y-auto p-2">
                {sortedNotifications.map((event) => {
                  const unread = !lastReadNotificationAt || event.created_at > lastReadNotificationAt;
                  const tone = toastTone(event.level);
                  return (
                    <div key={event.id} className={`mb-2 rounded-lg border bg-black/20 p-3 ${tone.border}`}>
                      <div className="flex items-start justify-between gap-3">
                        <span className={`text-xs font-bold leading-tight ${tone.title}`}>{event.message}</span>
                        {unread ? <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-amber-400" /> : null}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-wider text-zinc-600">
                        <span>{event.subsystem || "app"}</span>
                        <span>{event.level}</span>
                        <span>{new Date(event.created_at).toLocaleTimeString()}</span>
                        {event.session_id ? <span>session</span> : null}
                      </div>
                      {event.operator_action ? <p className="mt-2 line-clamp-2 text-[11px] text-zinc-400">{event.operator_action}</p> : null}
                    </div>
                  );
                })}
                {!sortedNotifications.length ? <p className="p-4 text-center text-xs text-zinc-500">No operator events yet.</p> : null}
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
        {children}
      </main>

      {/* Toast Notifications */}
      <div className="fixed right-3 top-16 z-40 flex w-[min(20rem,calc(100vw-1.5rem))] flex-col gap-3 sm:right-6 sm:top-20" aria-live="polite" aria-relevant="additions">
        <AnimatePresence>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              initial={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, x: 50, scale: 0.9 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, x: 20, scale: 0.95 }}
              transition={{ type: "spring", stiffness: 480, damping: 34 }}
              className={`group relative overflow-hidden rounded-xl border bg-[#10121c]/90 p-4 shadow-2xl backdrop-blur-xl ${toastTone(toast.level).border}`}
              role="status"
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
