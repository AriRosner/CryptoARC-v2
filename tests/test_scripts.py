import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ScriptSafetyTests(unittest.TestCase):
    def run_frontend_audit_fixture(
        self,
        audit: dict,
        *,
        audit_exit_code: int = 0,
        strict: bool = False,
        expected_exit_code: int = 0,
    ) -> dict:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(powershell, "PowerShell is required to exercise audit-frontend.ps1")

        with tempfile.TemporaryDirectory() as temporary_directory:
            mock_npm = Path(temporary_directory) / "mock-npm.ps1"
            mock_npm.write_text(
                "$auditJson = @'\n"
                f"{json.dumps(audit)}\n"
                "'@\n"
                "Write-Output $auditJson\n"
                f"exit {audit_exit_code}\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["CRYPTOARC_NPM"] = str(mock_npm)
            command = [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts" / "audit-frontend.ps1"),
                "-Json",
            ]
            if strict:
                command.append("-Strict")
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, expected_exit_code, completed.stderr or completed.stdout)
        return json.loads(completed.stdout)

    def test_frontend_audit_omits_acknowledged_exception_when_clear(self) -> None:
        report = self.run_frontend_audit_fixture(
            {
                "auditReportVersion": 2,
                "vulnerabilities": {},
                "metadata": {
                    "vulnerabilities": {
                        "info": 0,
                        "low": 0,
                        "moderate": 0,
                        "high": 0,
                        "critical": 0,
                        "total": 0,
                    }
                },
            }
        )

        self.assertEqual(report["status"], "ready")
        self.assertIsNone(report["acknowledged_exception"])

    def test_frontend_audit_preserves_matching_acknowledged_exception(self) -> None:
        report = self.run_frontend_audit_fixture(
            {
                "auditReportVersion": 2,
                "vulnerabilities": {
                    "uuid": {
                        "name": "uuid",
                        "severity": "moderate",
                        "isDirect": False,
                        "via": ["jayson"],
                        "effects": [],
                        "range": "<11.1.1",
                        "nodes": ["node_modules/uuid"],
                        "fixAvailable": {
                            "name": "@solana/web3.js",
                            "version": "0.0.3",
                            "isSemVerMajor": True,
                        },
                    }
                },
                "metadata": {
                    "vulnerabilities": {
                        "info": 0,
                        "low": 0,
                        "moderate": 1,
                        "high": 0,
                        "critical": 0,
                        "total": 1,
                    }
                },
            },
            audit_exit_code=1,
            strict=True,
        )

        self.assertEqual(report["status"], "review")
        self.assertTrue(report["vulnerabilities"][0]["acknowledged_exception"])
        self.assertIn("@solana/web3.js -> jayson -> uuid", report["acknowledged_exception"])
        self.assertIsNone(report["tooling_error"])

    def test_frontend_audit_strict_blocks_tooling_exit_with_acknowledged_advisory(self) -> None:
        report = self.run_frontend_audit_fixture(
            {
                "auditReportVersion": 2,
                "vulnerabilities": {
                    "uuid": {
                        "name": "uuid",
                        "severity": "moderate",
                        "isDirect": False,
                        "via": ["jayson"],
                        "effects": [],
                        "range": "<11.1.1",
                        "nodes": ["node_modules/uuid"],
                        "fixAvailable": {
                            "name": "@solana/web3.js",
                            "version": "0.0.3",
                            "isSemVerMajor": True,
                        },
                    }
                },
                "metadata": {
                    "vulnerabilities": {
                        "info": 0,
                        "low": 0,
                        "moderate": 1,
                        "high": 0,
                        "critical": 0,
                        "total": 1,
                    }
                },
            },
            audit_exit_code=2,
            strict=True,
            expected_exit_code=1,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("npm audit exited with code 2" in blocker for blocker in report["blockers"]))
        self.assertIn("tooling or registry failure", report["tooling_error"])
        self.assertIsNotNone(report["acknowledged_exception"])

    def test_frontend_audit_strict_blocks_unexplained_nonzero_npm_exit(self) -> None:
        report = self.run_frontend_audit_fixture(
            {
                "auditReportVersion": 2,
                "vulnerabilities": {},
                "metadata": {
                    "vulnerabilities": {
                        "info": 0,
                        "low": 0,
                        "moderate": 0,
                        "high": 0,
                        "critical": 0,
                        "total": 0,
                    }
                },
            },
            audit_exit_code=2,
            strict=True,
            expected_exit_code=1,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("npm audit exited with code 2" in blocker for blocker in report["blockers"]))

    def test_frontend_audit_strict_blocks_invalid_success_schema(self) -> None:
        valid_counts = {
            "info": 0,
            "low": 0,
            "moderate": 0,
            "high": 0,
            "critical": 0,
            "total": 0,
        }
        fixtures = {
            "empty": {},
            "wrong_report_version": {
                "auditReportVersion": 1,
                "vulnerabilities": {},
                "metadata": {"vulnerabilities": valid_counts},
            },
            "missing_vulnerabilities": {
                "auditReportVersion": 2,
                "metadata": {"vulnerabilities": valid_counts},
            },
            "missing_counts": {
                "auditReportVersion": 2,
                "vulnerabilities": {},
                "metadata": {"vulnerabilities": {"total": 0}},
            },
            "inconsistent_counts": {
                "auditReportVersion": 2,
                "vulnerabilities": {},
                "metadata": {
                    "vulnerabilities": {
                        "info": 0,
                        "low": 0,
                        "moderate": 0,
                        "high": 1,
                        "critical": 0,
                        "total": 1,
                    }
                },
            },
        }

        for fixture_name, audit in fixtures.items():
            with self.subTest(fixture=fixture_name):
                report = self.run_frontend_audit_fixture(
                    audit,
                    strict=True,
                    expected_exit_code=1,
                )

                self.assertEqual(report["status"], "blocked")
                self.assertIn("invalid npm audit JSON schema", report["tooling_error"])
                self.assertTrue(report["blockers"])

    def test_frontend_audit_documented_commands_use_strict_mode(self) -> None:
        quickstart = (ROOT / "docs" / "manual" / "02-quickstart.md").read_text(encoding="utf-8")
        release_checklist = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

        self.assertIn(
            "powershell -ExecutionPolicy Bypass -File scripts\\audit-frontend.ps1 -Strict",
            quickstart,
        )
        self.assertIn(
            "powershell -ExecutionPolicy Bypass -File scripts\\audit-frontend.ps1 -Strict",
            release_checklist,
        )

    def test_signer_health_callers_allow_rpc_probe_timeout_margin(self) -> None:
        daemon = (ROOT / "tools" / "local_signer_daemon.py").read_text(encoding="utf-8")
        state = (ROOT / "backend" / "app" / "core" / "state.py").read_text(encoding="utf-8")
        start_script = (ROOT / "scripts" / "start-signer-daemon.ps1").read_text(encoding="utf-8")

        daemon_timeout = float(re.search(r"RPC_HEALTH_TIMEOUT_SECONDS\s*=\s*([0-9.]+)", daemon).group(1))
        health_start = state.index("    def _local_signer_daemon_status")
        health_end = state.index("\n    def _local_signer_daemon_endpoint_allowed", health_start)
        health_block = state[health_start:health_end]
        backend_timeout = float(re.search(r"urlopen\(request, timeout=([0-9.]+)\)", health_block).group(1))
        startup_timeout = float(re.search(r"Invoke-RestMethod[^\r\n]+-TimeoutSec\s+([0-9.]+)", start_script).group(1))

        self.assertEqual(daemon_timeout, 1.0)
        with self.subTest(caller="backend"):
            self.assertGreaterEqual(backend_timeout, daemon_timeout + 0.5)
        with self.subTest(caller="startup_script"):
            self.assertGreaterEqual(startup_timeout, daemon_timeout + 1.0)

    def test_background_loop_and_compact_websocket_payload_skip_discarded_snapshot_work(self) -> None:
        main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        websocket_start = main.index("def websocket_snapshot_payload()")
        websocket_end = main.index("\n\nasync def broadcast_snapshot", websocket_start)
        websocket_payload = main[websocket_start:websocket_end]
        loop_start = main.index("async def bot_loop()")
        loop_end = main.index("\n\nasync def live_audit_poll_loop", loop_start)
        bot_loop = main[loop_start:loop_end]

        self.assertIn("state.snapshot(include_tokens=False).to_dict()", websocket_payload)
        self.assertNotIn('payload["tokens"] = []', websocket_payload)
        self.assertIn("state.tick(build_snapshot=False)", bot_loop)

    def test_verify_runs_polling_stability_check_before_frontend_build(self) -> None:
        script = (ROOT / "scripts" / "verify.ps1").read_text(encoding="utf-8")
        frontend_block = script[
            script.index("if (-not $SkipFrontendBuild)") : script.index("if (-not $SkipMobileBuild)")
        ]

        polling_check = 'Arguments @("run", "check:polling")'
        execution_readiness_check = 'Arguments @("run", "check:execution-readiness")'
        frontend_build = 'Arguments @("run", "build")'
        self.assertIn(polling_check, frontend_block)
        self.assertIn(execution_readiness_check, frontend_block)
        self.assertLess(frontend_block.index(polling_check), frontend_block.index(execution_readiness_check))
        self.assertLess(frontend_block.index(execution_readiness_check), frontend_block.index(frontend_build))
        self.assertLess(frontend_block.index(polling_check), frontend_block.index(frontend_build))

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
        self.assertIn("$hasConfiguredKey", start_script)
        self.assertIn('if (($hasConfiguredKey -or $AllowSubmit) -and $effectiveAuthToken.Length -lt 32)', start_script)
        self.assertIn("A configured signer key or AllowSubmit requires a signer auth token of at least 32 characters", start_script)
        self.assertIn('$healthUrl = "http://$HostName`:$Port/health"', start_script)
        self.assertIn('"Authorization" = "Bearer $effectiveAuthToken"', start_script)
        self.assertIn("Invoke-RestMethod", start_script)
        self.assertIn("$process.HasExited", start_script)
        self.assertIn("$health.ready_to_submit", start_script)
        self.assertIn('$readyToSubmit = $health.ready_to_submit -is [bool] -and $health.ready_to_submit -eq $true', start_script)
        self.assertIn('(-not $AllowSubmit -or $readyToSubmit)', start_script)
        self.assertIn("Stop-Process -Id $process.Id", start_script)
        self.assertLess(start_script.index("Invoke-RestMethod"), start_script.index("Signer daemon started"))
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

    def test_live_sign_send_disables_on_api_disconnect_and_wallet_mismatch(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("apiDisconnected", app)
        self.assertIn("activeAuditWalletMismatch", app)
        self.assertIn("quoteBlocked || apiDisconnected || activeAuditWalletMismatch || activeQuoteStale", app)

    def test_live_sign_send_records_pending_browser_signature_before_backend_submit(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("cryptoarc_pending_live_signature", app)
        self.assertIn("recordPendingLiveSignature", app)
        self.assertLess(app.index("recordPendingLiveSignature(activeLiveAudit, signature)"), app.index("await submitLiveAudit(activeLiveAudit.id, signature)"))
        self.assertIn("pendingLiveSignature", app)
        self.assertIn("A browser-wallet transaction was signed but is not yet recorded by the backend", app)

    def test_live_quick_fix_defaults_are_dust_pilot_caps(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("settings.live_max_trade_sol : 0.001", app)
        self.assertIn("settings.live_daily_loss_cap_sol : 0.005", app)
        self.assertIn("settings.live_wallet_exposure_cap_sol : 0.01", app)
        self.assertIn("settings.live_max_open_positions : 1", app)
        self.assertIn("settings.live_priority_fee_cap_sol : 0.00001", app)
        self.assertIn("recommended: 0.001", app)
        self.assertIn("recommended: 0.005", app)

    def test_live_workspace_displays_runtime_connectivity_guard(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("const runtimeConnectivity = liveStatus?.runtime_connectivity", app)
        self.assertIn("Runtime Connectivity", app)
        self.assertIn("runtimeConnectivity.safe_for_new_entry", app)
        self.assertIn("runtimeConnectivity.blockers", app)

    def test_settings_search_indexes_actual_setting_labels(self) -> None:
        modal = (ROOT / "frontend" / "src" / "components" / "SettingsModal.tsx").read_text(encoding="utf-8")

        self.assertIn("settingsSearchIndex", modal)
        self.assertIn("normalizeSettingsSearch", modal)
        self.assertIn("queryTerms.every", modal)
        for label in [
            "Paper Priority Fee",
            "Live Signer Mode",
            "Manual Kill Switch",
            "Profit Vault",
            "Source Max Reconnects",
            "Entry Confirmation Gate",
            "Watched Wallet Address",
        ]:
            self.assertIn(label, modal)

    def test_pnl_chart_has_stable_responsive_container_bounds(self) -> None:
        chart = (ROOT / "frontend" / "src" / "components" / "PnlChart.tsx").read_text(encoding="utf-8")

        self.assertIn("ResizeObserver", chart)
        self.assertIn("containerReady", chart)
        self.assertIn("containerSize.width", chart)
        self.assertIn("width={containerSize.width}", chart)
        self.assertNotIn("ResponsiveContainer", chart)


if __name__ == "__main__":
    unittest.main()
