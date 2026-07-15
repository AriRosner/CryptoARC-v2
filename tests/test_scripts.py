import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ScriptSafetyTests(unittest.TestCase):
    def test_start_dev_records_dynamic_ports_and_frontend_api_base(self) -> None:
        script = (ROOT / "scripts" / "start-dev.ps1").read_text(encoding="utf-8")

        self.assertIn("Resolve-CryptoArcDevPort", script)
        self.assertIn("dev-ports.json", script)
        self.assertIn("VITE_API_BASE_URL", script)
        self.assertIn("--port $backendPort", script)
        self.assertIn("--port $frontendPort", script)

    def test_start_dev_frontend_uses_strict_manifest_port(self) -> None:
        script = (ROOT / "scripts" / "start-dev.ps1").read_text(encoding="utf-8")

        self.assertIn("--strictPort", script)
        self.assertIn("--port $frontendPort --strictPort", script)

    def test_stop_and_status_use_recorded_dev_ports(self) -> None:
        stop_script = (ROOT / "scripts" / "stop-dev.ps1").read_text(encoding="utf-8")
        status_script = (ROOT / "scripts" / "status-dev.ps1").read_text(encoding="utf-8")

        self.assertIn("dev-ports.json", stop_script)
        self.assertIn("dev-ports.json", status_script)
        self.assertIn("backend_port", status_script)
        self.assertIn("frontend_port", status_script)
        self.assertIn("Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue", stop_script)

    def test_start_dev_records_process_manifest(self) -> None:
        script = (ROOT / "scripts" / "start-dev.ps1").read_text(encoding="utf-8")

        self.assertIn("dev-processes.json", script)
        self.assertIn("backend_launcher_pid", script)
        self.assertIn("frontend_launcher_pid", script)
        self.assertIn("backend_port_owner_pids", script)
        self.assertIn("frontend_port_owner_pids", script)
        self.assertIn("Write-CryptoArcProcessManifest", script)

    def test_stop_dev_cleans_reload_children_and_verifies_ports(self) -> None:
        script = (ROOT / "scripts" / "stop-dev.ps1").read_text(encoding="utf-8")

        self.assertIn("dev-processes.json", script)
        self.assertIn("multiprocessing-fork", script)
        self.assertIn("/api/stop", script)
        self.assertIn("Assert-CryptoArcDevPortsStopped", script)
        self.assertIn("taskkill.exe", script)

    def test_reset_runtime_state_exists_and_preserves_configuration(self) -> None:
        script_path = ROOT / "scripts" / "reset-runtime-state.ps1"
        self.assertTrue(script_path.exists())
        script = script_path.read_text(encoding="utf-8")

        self.assertIn("cryptoarc-before-fresh-slate", script)
        self.assertIn("settings_versions", script)
        self.assertIn("backup_restore_history", script)
        self.assertIn("strategy_presets", script)
        self.assertIn("/api/data/clear", script)
        self.assertIn("scripts\\start-dev.ps1", script)
        self.assertNotIn("/api/start", script)
        self.assertIn("fee_totals", script)
        self.assertIn("entry_fees_sol", script)
        self.assertIn("exit_fees_sol", script)
        self.assertIn("total_fees_sol", script)

    def test_local_signer_daemon_scripts_are_no_trade_and_do_not_echo_private_key(self) -> None:
        start_path = ROOT / "scripts" / "start-signer-daemon.ps1"
        check_path = ROOT / "scripts" / "check-signer-daemon.ps1"

        self.assertTrue(start_path.exists())
        self.assertTrue(check_path.exists())
        start_script = start_path.read_text(encoding="utf-8")
        check_script = check_path.read_text(encoding="utf-8")

        self.assertIn("tools.local_signer_daemon", start_script)
        self.assertIn("CRYPTOARC_SIGNER_PRIVATE_KEY", start_script)
        self.assertNotIn("Write-Host $env:CRYPTOARC_SIGNER_PRIVATE_KEY", start_script)
        self.assertIn("/health", check_script)
        self.assertIn("Authorization", check_script)
        self.assertNotIn("/execute", check_script)
        self.assertNotIn("CRYPTOARC_SIGNER_PRIVATE_KEY", check_script)

    def test_frontend_uses_backend_wallet_balance_and_scopes_live_tokens(self) -> None:
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        types = (ROOT / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")

        self.assertIn("fetchLiveWalletBalance", api)
        self.assertIn("/api/live/wallet/balance", api)
        self.assertIn("fetchLiveWalletBalance", app)
        self.assertIn("setWalletBalanceSol(Number(balance.balance_sol ?? 0))", app)
        balance_block = app[app.index("const refreshConnectedWalletBalance"):app.index("React.useEffect(() => {", app.index("const refreshConnectedWalletBalance"))]
        self.assertNotIn("new Connection", balance_block)
        self.assertIn("wallet_public_key", types)
        self.assertIn("token.wallet_public_key", app)
        self.assertIn("selectedLivePnlWallet", app)

    def test_settings_modal_exposes_paper_trade_hour_limit(self) -> None:
        modal = (ROOT / "frontend" / "src" / "components" / "SettingsModal.tsx").read_text(encoding="utf-8")

        self.assertIn('field="max_trades_per_hour_enabled"', modal)
        self.assertIn('field="max_trades_per_hour"', modal)

    def test_settings_modal_exposes_entry_confirmation_gate(self) -> None:
        modal = (ROOT / "frontend" / "src" / "components" / "SettingsModal.tsx").read_text(encoding="utf-8")

        self.assertIn('field="entry_confirmation_enabled"', modal)
        self.assertIn('field="entry_confirmation_min_buy_velocity"', modal)
        self.assertIn('field="entry_confirmation_min_observed_trades"', modal)
        self.assertIn("Max Trades Per Hour", modal)
        self.assertIn("hourly paper-entry throttle", modal)
        self.assertIn("hourly", modal)

    def test_settings_save_errors_keep_modal_open(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        save_start = app.index("async function saveSettings")
        save_end = app.index("async function replayBacktest", save_start)
        save_block = app[save_start:save_end]

        self.assertIn("throw error", save_block)

    def test_animated_number_keeps_rolling_motion(self) -> None:
        component = (ROOT / "frontend" / "src" / "components" / "AnimatedNumber.tsx").read_text(encoding="utf-8")

        self.assertIn("useMotionValue", component)
        self.assertIn("animate(", component)
        self.assertIn("useReducedMotion", component)
        self.assertIn("prefers reduced motion", component)

    def test_token_table_accessible_icon_actions_and_search(self) -> None:
        table = (ROOT / "frontend" / "src" / "components" / "TokenTable.tsx").read_text(encoding="utf-8")

        self.assertIn('aria-label="Search tokens"', table)
        self.assertIn('aria-label={`View ${token.symbol} details`}', table)
        self.assertIn("event.stopPropagation()", table)

    def test_fee_surfaces_exist_on_dashboard_table_and_token_detail(self) -> None:
        stats = (ROOT / "frontend" / "src" / "components" / "StatsGrid.tsx").read_text(encoding="utf-8")
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        table = (ROOT / "frontend" / "src" / "components" / "TokenTable.tsx").read_text(encoding="utf-8")
        detail = (ROOT / "frontend" / "src" / "components" / "TokenDetail.tsx").read_text(encoding="utf-8")
        types = (ROOT / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")

        self.assertIn("Fees Paid", stats)
        self.assertIn("total_fees_sol", stats)
        self.assertIn("feeDisplayValue", stats)
        self.assertIn("showUsd ? stats.total_fees_sol * solUsdPrice", stats)
        self.assertIn("paperTimeframeFees", app)
        self.assertIn("displayedStats", app)
        self.assertIn("Fees", table)
        self.assertIn("totalTokenFeesSol", table)
        self.assertIn("Entry Fee", detail)
        self.assertIn("Exit Fee", detail)
        self.assertIn("Provider Fee", detail)
        self.assertIn("Network Fee", detail)
        self.assertIn("Priority Fee", detail)
        self.assertIn("Slippage Cost", detail)
        self.assertIn("Impact Cost", detail)
        self.assertIn("Total Fees", detail)
        self.assertIn("Shadow Quote Cost", detail)
        self.assertIn("exit_fee_sol", types)
        self.assertIn("entry_priority_fee_sol", types)
        self.assertIn("entry_provider_fee_sol", types)
        self.assertIn("quote_shadow_total_cost_sol", types)
        self.assertIn("total_fees_sol", types)

    def test_live_workspace_uses_safe_priority_fee_minimum_and_rent_recovery(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")
        types = (ROOT / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")
        main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")

        self.assertIn('min="0.00001"', app)
        self.assertNotIn('Priority fee SOL\n                    <input className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-black/40 px-3 text-xs font-bold normal-case tracking-normal text-white" type="number" min="0.001"', app)
        self.assertIn("fetchRentRecoveryScan", api)
        self.assertIn("createRentRecoveryPreview", api)
        self.assertIn("Rent Recovery", app)
        self.assertIn("rentRecoveryScan", app)
        self.assertIn("signAndSendRentRecovery", app)
        self.assertIn("RentRecoveryScan", types)
        self.assertIn("/api/live/rent-recovery", main)

    def test_dashboard_exposes_net_pnl_and_live_fill_audit(self) -> None:
        stats = (ROOT / "frontend" / "src" / "components" / "StatsGrid.tsx").read_text(encoding="utf-8")
        monitor = (ROOT / "frontend" / "src" / "pages" / "MonitorPage.tsx").read_text(encoding="utf-8")
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        types = (ROOT / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")

        self.assertIn("Net P&L", stats)
        self.assertIn("timeframePnlSol", app)
        self.assertIn("total_pnl_sol: timeframePnlSol", app)
        self.assertIn("liveTimeframeFees", app)
        self.assertIn("Live Fill Audit", monitor)
        self.assertIn("recent_fills", monitor)
        self.assertIn("wallet_sol_delta_sol", monitor)
        self.assertIn("net_pnl_sol", types)
        self.assertIn("recent_fills", types)

    def test_exports_do_not_put_auth_tokens_in_urls(self) -> None:
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")
        data_page = (ROOT / "frontend" / "src" / "pages" / "DataPage.tsx").read_text(encoding="utf-8")

        export_block = api[api.index("export function sourceParserReplayExportUrl"):api.index("export function openSnapshotSocket")]
        self.assertNotIn('params.set("token"', export_block)
        self.assertNotIn("?token=", export_block)
        self.assertIn("downloadAuthenticatedExport", api)
        self.assertIn("downloadAuthenticatedExport", data_page)

    def test_sidebar_latency_uses_backend_fallbacks(self) -> None:
        sidebar = (ROOT / "frontend" / "src" / "components" / "Sidebar.tsx").read_text(encoding="utf-8")

        self.assertIn("serverLatencyMs", sidebar)
        self.assertIn("latencyStatus?.api_loop_ms", sidebar)
        self.assertIn("sourceLatencyText", sidebar)
        self.assertIn("latencyStatus?.source_connection?.state", sidebar)

    def test_latency_endpoint_primes_first_request(self) -> None:
        main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        endpoint = main[main.index("async def latency_status_endpoint"):main.index("@app.post(\"/api/mobile/pairing/start\"")]

        self.assertIn("await update_latency_status()", endpoint)
        self.assertIn('not latency_status.get("updated_at")', endpoint)

    def test_latency_poll_failure_preserves_last_dashboard_rtt(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertNotIn("dashboard_rtt_ms: null, latency_error: message, latency_stale: true", app)
        self.assertIn("? { ...current, latency_error: message, latency_stale: true }", app)

    def test_pnl_chart_has_stable_responsive_container_bounds(self) -> None:
        chart = (ROOT / "frontend" / "src" / "components" / "PnlChart.tsx").read_text(encoding="utf-8")

        self.assertIn("ResizeObserver", chart)
        self.assertIn("containerReady", chart)
        self.assertIn("containerSize.width", chart)
        self.assertIn("width={containerSize.width}", chart)
        self.assertNotIn("ResponsiveContainer", chart)


if __name__ == "__main__":
    unittest.main()
