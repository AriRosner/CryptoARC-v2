import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ScriptSafetyTests(unittest.TestCase):
    @staticmethod
    def unused_local_port() -> int:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    def run_stop_dev_selection_fixture(
        self,
        *,
        processes: list[dict],
        port_owner_pid: int | None = None,
        ports_manifest: dict | str | None = None,
        processes_manifest: dict | str | None = None,
        cim_available: bool = True,
        backend_http_identity: bool = False,
        api_post_fails: bool = False,
        port_owner_lookup_available: bool = True,
        taskkill_exit_code: int = 0,
        taskkill_removes_process: bool = True,
        respawn_process: dict | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], list[str], bool, bool]:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(powershell, "PowerShell is required to exercise stop-dev.ps1")

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            scripts_root = temporary_root / "scripts"
            logs_root = temporary_root / "data" / "logs"
            scripts_root.mkdir(parents=True)
            logs_root.mkdir(parents=True)
            shutil.copy2(ROOT / "scripts" / "stop-dev.ps1", scripts_root / "stop-dev.ps1")
            escaped_root = str(temporary_root).replace("\\", "\\\\")
            ports_path = logs_root / "dev-ports.json"
            processes_path = logs_root / "dev-processes.json"
            manifest_generated_at = "2026-01-01T00:00:00.0000000Z"
            process_creation_date = "2025-12-31T23:59:59.0000000Z"
            port_owner_local_port = 0
            if isinstance(ports_manifest, dict):
                port_owner_local_port = int(ports_manifest.get("backend_port", 0))
            elif isinstance(processes_manifest, dict):
                port_owner_local_port = int(processes_manifest.get("backend_port", 0))
            if ports_manifest is not None:
                ports_content = (
                    ports_manifest
                    if isinstance(ports_manifest, str)
                    else json.dumps(ports_manifest).replace("__ROOT__", escaped_root)
                )
                ports_path.write_text(ports_content, encoding="utf-8")
            if processes_manifest is not None:
                if isinstance(processes_manifest, dict):
                    processes_manifest = {
                        "generated_at": manifest_generated_at,
                        "backend_executable": "__ROOT__\\.venv\\Scripts\\python.exe",
                        "backend_base_executable": "__ROOT__\\.venv\\Scripts\\python.exe",
                        **processes_manifest,
                    }
                processes_content = (
                    processes_manifest.replace("__ROOT__", escaped_root)
                    if isinstance(processes_manifest, str)
                    else json.dumps(processes_manifest).replace("__ROOT__", escaped_root)
                )
                processes_path.write_text(processes_content, encoding="utf-8")
            action_path = temporary_root / "actions.log"
            processes = [
                {"CreationDate": process_creation_date, **process}
                for process in processes
            ]
            if respawn_process is not None:
                respawn_process = {
                    "CreationDate": process_creation_date,
                    **respawn_process,
                }
            process_json = json.dumps(processes).replace("__ROOT__", escaped_root)
            respawn_json = json.dumps(respawn_process).replace("__ROOT__", escaped_root)
            wrapper_path = temporary_root / "run-stop-dev.ps1"
            wrapper_path.write_text(
                f"$actionPath = '{action_path}'\n"
                f"$processJson = @'\n{process_json}\n'@\n"
                f"$respawnJson = @'\n{respawn_json}\n'@\n"
                "$global:syntheticProcesses = @($processJson | ConvertFrom-Json | ForEach-Object { $_ })\n"
                "$global:respawnProcess = $respawnJson | ConvertFrom-Json\n"
                "$global:respawned = $false\n"
                "function Get-NetTCPConnection {\n"
                "  [CmdletBinding()]\n"
                "  param([int[]]$LocalPort, [string]$State)\n"
                + (
                    "  throw 'Get-NetTCPConnection unavailable'\n"
                    if not port_owner_lookup_available
                    else (
                        f"  if ($global:syntheticProcesses.ProcessId -contains {port_owner_pid}) {{\n"
                        f"    [pscustomobject]@{{ OwningProcess = {port_owner_pid}; "
                        f"State = 'Listen'; LocalPort = {port_owner_local_port} }}\n"
                        "  } elseif ($PSBoundParameters.ContainsKey('LocalPort')) {\n"
                        "    throw 'No matching MSFT_NetTCPConnection objects found'\n"
                        "  }\n"
                        if port_owner_pid is not None
                        else (
                            "  if ($PSBoundParameters.ContainsKey('LocalPort')) {\n"
                            "    throw 'No matching MSFT_NetTCPConnection objects found'\n"
                            "  }\n"
                            "  return @()\n"
                        )
                    )
                )
                + "}\n"
                "function Get-CimInstance {\n"
                "  [CmdletBinding()]\n"
                "  param([string]$ClassName)\n"
                + (
                    "  return $global:syntheticProcesses\n"
                    if cim_available
                    else "  throw 'Get-CimInstance unavailable'\n"
                )
                +
                "}\n"
                "function Invoke-RestMethod {\n"
                "  [CmdletBinding()]\n"
                "  param([string]$Uri, [string]$Method, [int]$TimeoutSec)\n"
                "  Add-Content -LiteralPath $actionPath -Value \"post:$Uri\"\n"
                "}\n"
                "function Invoke-WebRequest {\n"
                "  [CmdletBinding()]\n"
                "  param([switch]$UseBasicParsing, [string]$Uri, [string]$Method, "
                "[int]$TimeoutSec, [int]$MaximumRedirection)\n"
                "  if ($Method -eq 'Post') {\n"
                "    Add-Content -LiteralPath $actionPath "
                "-Value \"post:$Uri redirects:$MaximumRedirection timeout:$TimeoutSec\"\n"
                + (
                    "    throw 'Synthetic API stop failure'\n"
                    if api_post_fails
                    else "    return [pscustomobject]@{ StatusCode = 200; Content = '' }\n"
                )
                +
                "  }\n"
                + (
                    "  if ($Uri -like '*/openapi.json') {\n"
                    "    return [pscustomobject]@{ Content = '{\"info\":{\"title\":\"CryptoARC v2 API\"}}' }\n"
                    "  }\n"
                    if backend_http_identity
                    else ""
                )
                + "  throw [System.Net.Sockets.SocketException]::new("
                "[System.Net.Sockets.SocketError]::ConnectionRefused)\n"
                "}\n"
                "function taskkill.exe {\n"
                "  Add-Content -LiteralPath $actionPath -Value \"taskkill:$($args -join ' ')\"\n"
                f"  $global:LASTEXITCODE = {taskkill_exit_code}\n"
                + (
                    "  $targetIndex = [array]::IndexOf($args, '/PID') + 1\n"
                    "  if ($targetIndex -gt 0 -and $targetIndex -lt $args.Count) {\n"
                    "    $targetPid = [int]$args[$targetIndex]\n"
                    "    $global:syntheticProcesses = @("
                    "$global:syntheticProcesses | Where-Object { [int]$_.ProcessId -ne $targetPid })\n"
                    "    if ($global:respawnProcess -and -not $global:respawned) {\n"
                    "      $global:syntheticProcesses += $global:respawnProcess\n"
                    "      $global:respawned = $true\n"
                    "    }\n"
                    "  }\n"
                    if taskkill_removes_process
                    else ""
                )
                +
                "}\n"
                "function Stop-Process {\n"
                "  [CmdletBinding()]\n"
                "  param([int]$Id, [switch]$Force)\n"
                "  Add-Content -LiteralPath $actionPath -Value \"stop:$Id\"\n"
                "}\n"
                "try {\n"
                f"  & '{scripts_root / 'stop-dev.ps1'}'\n"
                "  exit 0\n"
                "} catch {\n"
                "  Write-Error $_\n"
                "  exit 1\n"
                "}\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(wrapper_path),
                ],
                cwd=temporary_root,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            actions = action_path.read_text(encoding="utf-8").splitlines() if action_path.exists() else []
            return completed, actions, ports_path.exists(), processes_path.exists()

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
        self.assertIn(
            "Get-NetTCPConnection -State Listen -ErrorAction Stop",
            stop_script,
        )
        self.assertIn("Where-Object { [int]$_.LocalPort -eq $BackendPort }", stop_script)
        self.assertNotIn("defaultBackendPorts", stop_script)

    def test_start_dev_records_process_manifest(self) -> None:
        script = (ROOT / "scripts" / "start-dev.ps1").read_text(encoding="utf-8")

        self.assertIn("dev-processes.json", script)
        self.assertIn("backend_launcher_pid", script)
        self.assertIn("frontend_launcher_pid", script)
        self.assertIn("backend_port_owner_pids", script)
        self.assertIn("frontend_port_owner_pids", script)
        self.assertIn("backend_executable", script)
        self.assertIn("backend_base_executable", script)
        self.assertIn("sys._base_executable", script)
        self.assertIn("Write-CryptoArcProcessManifest", script)

    def test_start_dev_refreshes_process_manifest_before_startup_rethrow(self) -> None:
        script = (ROOT / "scripts" / "start-dev.ps1").read_text(encoding="utf-8")
        startup_catch = script.rsplit("} catch {", 1)[1]

        self.assertIn("Write-CryptoArcProcessManifest", startup_catch)
        self.assertLess(
            startup_catch.index("Write-CryptoArcProcessManifest"),
            startup_catch.index("\n  throw"),
        )

    def test_stop_dev_uses_only_validated_processes_and_bounded_api_stop(self) -> None:
        script = (ROOT / "scripts" / "stop-dev.ps1").read_text(encoding="utf-8")

        self.assertIn("dev-processes.json", script)
        self.assertIn("multiprocessing-fork", script)
        self.assertIn("/api/stop", script)
        self.assertIn("-MaximumRedirection 0", script)
        self.assertIn("-TimeoutSec 1", script)
        self.assertNotIn("Invoke-RestMethod", script)
        self.assertIn("taskkill.exe", script)

    def test_stop_dev_deletes_manifests_fail_closed_before_reporting_success(self) -> None:
        script = (ROOT / "scripts" / "stop-dev.ps1").read_text(encoding="utf-8")

        self.assertIn("function Remove-CryptoArcManifest", script)
        cleanup_start = script.index("function Remove-CryptoArcManifest")
        cleanup_end = script.index("\n}", cleanup_start)
        cleanup = script[cleanup_start:cleanup_end]
        self.assertIn("Remove-Item", cleanup)
        self.assertIn("-ErrorAction Stop", cleanup)
        self.assertIn("Test-Path", cleanup)
        self.assertIn("throw", cleanup)
        self.assertLess(
            script.rindex("Remove-CryptoArcManifest"),
            script.index('Write-Host "CryptoARC dev processes stopped."'),
        )

    def test_stop_dev_does_not_target_default_port_occupants_without_a_manifest(self) -> None:
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 41001,
                    "ParentProcessId": 1,
                    "ExecutablePath": "C:\\Windows\\System32\\unrelated.exe",
                    "CommandLine": "unrelated-service",
                }
            ],
            port_owner_pid=41001,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])

    def test_stop_dev_does_not_kill_a_reused_manifest_pid(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 42001,
                    "ParentProcessId": 1,
                    "ExecutablePath": "C:\\Windows\\System32\\unrelated.exe",
                    "CommandLine": "unrelated-service",
                }
            ],
            port_owner_pid=42001,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 42001,
                "frontend_launcher_pid": 42001,
                "backend_child_pids": [],
                "backend_port_owner_pids": [42001],
                "frontend_port_owner_pids": [42001],
            },
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertFalse(any(action.startswith(("taskkill:", "stop:")) for action in actions), actions)
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_does_not_kill_a_reused_manifest_fork_pid_from_another_checkout(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 42002,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__-other\\.venv\\Scripts\\python.exe",
                    "CommandLine": "spawn_main(parent_pid=1) --multiprocessing-fork",
                }
            ],
            port_owner_pid=42002,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": None,
                "frontend_launcher_pid": None,
                "backend_child_pids": [42002],
                "backend_port_owner_pids": [42002],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertFalse(any(action.startswith(("post:", "taskkill:", "stop:")) for action in actions), actions)
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_does_not_kill_a_stale_global_frontend_manifest_pid(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 42003,
                    "ParentProcessId": 1,
                    "ExecutablePath": "C:\\Program Files\\nodejs\\node.exe",
                    "CommandLine": (
                        '"C:\\Program Files\\nodejs\\node.exe" '
                        "C:\\global\\vite.js --host 127.0.0.1"
                    ),
                    "CreationDate": "2026-01-01T00:00:01.0000000Z",
                }
            ],
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": None,
                "frontend_launcher_pid": 42003,
                "backend_child_pids": [],
                "backend_port_owner_pids": [],
                "frontend_port_owner_pids": [42003],
                "generated_at": "2026-01-01T00:00:00.0000000Z",
            },
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertFalse(any(action.startswith(("post:", "taskkill:", "stop:")) for action in actions), actions)
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_does_not_post_or_kill_a_stale_global_backend_manifest_pid(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 42004,
                    "ParentProcessId": 1,
                    "ExecutablePath": "C:\\Python\\python.exe",
                    "CommandLine": '"C:\\Python\\python.exe" -m uvicorn app.main:app',
                    "CreationDate": "2026-01-01T00:00:01.0000000Z",
                }
            ],
            port_owner_pid=42004,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 42004,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [42004],
                "frontend_port_owner_pids": [],
                "generated_at": "2026-01-01T00:00:00.0000000Z",
            },
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertFalse(any(action.startswith(("post:", "taskkill:", "stop:")) for action in actions), actions)
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_fails_closed_when_manifest_process_creation_proof_is_missing_or_invalid(self) -> None:
        for process_id, creation_date in ((42007, None), (42008, "not-a-timestamp")):
            with self.subTest(creation_date=creation_date):
                backend_port = self.unused_local_port()
                frontend_port = self.unused_local_port()
                completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
                    processes=[
                        {
                            "ProcessId": process_id,
                            "ParentProcessId": 1,
                            "ExecutablePath": "C:\\Python\\python.exe",
                            "CommandLine": '"C:\\Python\\python.exe" -m uvicorn app.main:app',
                            "CreationDate": creation_date,
                        }
                    ],
                    port_owner_pid=process_id,
                    ports_manifest={
                        "backend_port": backend_port,
                        "frontend_port": frontend_port,
                    },
                    processes_manifest={
                        "root": "__ROOT__",
                        "backend_port": backend_port,
                        "frontend_port": frontend_port,
                        "backend_launcher_pid": process_id,
                        "frontend_launcher_pid": None,
                        "backend_child_pids": [],
                        "backend_port_owner_pids": [process_id],
                        "frontend_port_owner_pids": [],
                    },
                )

                self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
                self.assertFalse(
                    any(action.startswith(("post:", "taskkill:", "stop:")) for action in actions),
                    actions,
                )
                self.assertTrue(ports_exist)
                self.assertTrue(processes_exist)

    def test_stop_dev_rejects_a_non_utc_process_manifest_timestamp(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[],
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": None,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [],
                "frontend_port_owner_pids": [],
                "generated_at": "2026-01-01T01:00:00.0000000+01:00",
            },
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_rejects_a_future_process_manifest_timestamp(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[],
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": None,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [],
                "frontend_port_owner_pids": [],
                "generated_at": "2099-01-01T00:00:00.0000000Z",
            },
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_quiesces_fresh_external_backend_and_frontend_manifest_processes(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 42005,
                    "ParentProcessId": 1,
                    "ExecutablePath": "D:\\Python\\python.exe",
                    "CommandLine": '"D:\\Python\\python.exe" -m uvicorn app.main:app',
                    "CreationDate": "2025-12-31T23:59:58.0000000Z",
                },
                {
                    "ProcessId": 42006,
                    "ParentProcessId": 1,
                    "ExecutablePath": "C:\\Program Files\\nodejs\\node.exe",
                    "CommandLine": (
                        '"C:\\Program Files\\nodejs\\node.exe" '
                        "C:\\global\\vite.js --host 127.0.0.1"
                    ),
                    "CreationDate": "2025-12-31T23:59:58.0000000Z",
                },
            ],
            port_owner_pid=42005,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 42005,
                "frontend_launcher_pid": 42006,
                "backend_executable": "D:\\Python\\python.exe",
                "backend_child_pids": [],
                "backend_port_owner_pids": [42005],
                "frontend_port_owner_pids": [42006],
                "generated_at": "2026-01-01T00:00:00.0000000Z",
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertTrue(any(action.startswith("post:") for action in actions), actions)
        self.assertTrue(
            any(action.startswith("taskkill:") and "/PID 42005 " in action for action in actions),
            actions,
        )
        self.assertTrue(
            any(action.startswith("taskkill:") and "/PID 42006 " in action for action in actions),
            actions,
        )
        self.assertFalse(ports_exist)
        self.assertFalse(processes_exist)

    def test_stop_dev_quiesces_a_fresh_recorded_shared_venv_backend(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        shared_python = "D:\\shared\\.venv\\Scripts\\python.exe"
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 42009,
                    "ParentProcessId": 1,
                    "ExecutablePath": shared_python,
                    "CommandLine": f'"{shared_python}" -m uvicorn app.main:app',
                    "CreationDate": "2025-12-31T23:59:58.0000000Z",
                }
            ],
            port_owner_pid=42009,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_executable": shared_python,
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 42009,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [42009],
                "frontend_port_owner_pids": [],
                "generated_at": "2026-01-01T00:00:00.0000000Z",
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertTrue(any(action.startswith("post:") for action in actions), actions)
        self.assertTrue(
            any(action.startswith("taskkill:") and "/PID 42009 " in action for action in actions),
            actions,
        )
        self.assertFalse(ports_exist)
        self.assertFalse(processes_exist)

    def test_stop_dev_quiesces_recorded_base_interpreter_reloader_and_worker(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        selected_python = "D:\\shared\\.venv\\Scripts\\python.exe"
        base_python = "C:\\Users\\Ari Rosner\\.cache\\uv\\python\\python.exe"
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 42010,
                    "ParentProcessId": 1,
                    "ExecutablePath": base_python,
                    "CommandLine": f'"{base_python}" -m uvicorn app.main:app',
                    "CreationDate": "2025-12-31T23:59:58.0000000Z",
                },
                {
                    "ProcessId": 42011,
                    "ParentProcessId": 42010,
                    "ExecutablePath": base_python,
                    "CommandLine": "spawn_main(parent_pid=42010) --multiprocessing-fork",
                    "CreationDate": "2025-12-31T23:59:58.0000000Z",
                },
            ],
            port_owner_pid=42010,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_executable": selected_python,
                "backend_base_executable": base_python,
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 42010,
                "frontend_launcher_pid": None,
                "backend_child_pids": [42011],
                "backend_port_owner_pids": [42010],
                "frontend_port_owner_pids": [],
                "generated_at": "2026-01-01T00:00:00.0000000Z",
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(
            [action for action in actions if action.startswith("post:")],
            [f"post:http://127.0.0.1:{backend_port}/api/stop redirects:0 timeout:1"],
        )
        taskkills = [action for action in actions if action.startswith("taskkill:")]
        self.assertTrue(any("/PID 42010 " in action for action in taskkills), actions)
        self.assertTrue(any("/PID 42011 " in action for action in taskkills), actions)
        self.assertFalse(ports_exist)
        self.assertFalse(processes_exist)

    def test_stop_dev_does_not_match_another_checkout_with_a_shared_path_prefix(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 43001,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__-other\\.venv\\Scripts\\python.exe",
                    "CommandLine": '"__ROOT__-other\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app',
                }
            ],
            port_owner_pid=43001,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 43001,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [43001],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_never_posts_to_a_same_title_other_checkout_endpoint(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        _, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 43501,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__-other\\.venv\\Scripts\\python.exe",
                    "CommandLine": '"__ROOT__-other\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app',
                }
            ],
            port_owner_pid=43501,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 43501,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [43501],
                "frontend_port_owner_pids": [],
            },
            backend_http_identity=True,
        )

        self.assertFalse(any(action.startswith("post:") for action in actions), actions)
        self.assertFalse(any(action.startswith("taskkill:") for action in actions), actions)

    def test_stop_dev_does_not_select_system_wide_multiprocessing_forks(self) -> None:
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 44001,
                    "ParentProcessId": 1,
                    "ExecutablePath": "C:\\Python\\python.exe",
                    "CommandLine": "spawn_main(parent_pid=12345) --multiprocessing-fork",
                }
            ],
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])

    def test_stop_dev_kills_only_validated_same_checkout_processes(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46001,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": (
                        '"__ROOT__\\.venv\\Scripts\\python.exe" '
                        "-m uvicorn app.main:app --host 127.0.0.1"
                    ),
                },
                {
                    "ProcessId": 46002,
                    "ParentProcessId": 46001,
                    "ExecutablePath": "C:\\Python\\python.exe",
                    "CommandLine": "spawn_main(parent_pid=46001) --multiprocessing-fork",
                },
            ],
            port_owner_pid=46001,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 46001,
                "frontend_launcher_pid": None,
                "backend_child_pids": [46002],
                "backend_port_owner_pids": [46001],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        taskkills = [action for action in actions if action.startswith("taskkill:")]
        self.assertTrue(any("/PID 46001 " in action for action in taskkills), actions)
        self.assertTrue(any("/PID 46002 " in action for action in taskkills), actions)
        parent_kill = next(i for i, action in enumerate(taskkills) if "/PID 46001 " in action)
        child_kill = next(i for i, action in enumerate(taskkills) if "/PID 46002 " in action)
        self.assertLess(parent_kill, child_kill, actions)
        self.assertFalse(any("/T" in action for action in taskkills), actions)

    def test_stop_dev_kills_a_validated_same_checkout_fork_child(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46101,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": (
                        '"__ROOT__\\.venv\\Scripts\\python.exe" '
                        "-m uvicorn app.main:app --host 127.0.0.1"
                    ),
                },
                {
                    "ProcessId": 46102,
                    "ParentProcessId": 46101,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": "spawn_main(parent_pid=46101) --multiprocessing-fork",
                },
            ],
            port_owner_pid=46101,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 46101,
                "frontend_launcher_pid": None,
                "backend_child_pids": [46102],
                "backend_port_owner_pids": [46101],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        taskkills = [action for action in actions if action.startswith("taskkill:")]
        self.assertTrue(any("/PID 46101 " in action for action in taskkills), actions)
        self.assertTrue(any("/PID 46102 " in action for action in taskkills), actions)
        self.assertLess(
            next(index for index, action in enumerate(taskkills) if "/PID 46101 " in action),
            next(index for index, action in enumerate(taskkills) if "/PID 46102 " in action),
        )
        self.assertFalse(any("/T" in action for action in taskkills), actions)

    def test_stop_dev_kills_a_manifest_authorized_orphan_fork_worker(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46151,
                    "ParentProcessId": 99999,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": "spawn_main(parent_pid=99999) --multiprocessing-fork",
                }
            ],
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": None,
                "frontend_launcher_pid": None,
                "backend_child_pids": [46151],
                "backend_port_owner_pids": [46151],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertTrue(
            any(action.startswith("taskkill:") and "/PID 46151 " in action for action in actions),
            actions,
        )

    def test_stop_dev_leaves_a_same_root_unrelated_orphan_fork_untouched(self) -> None:
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46150,
                    "ParentProcessId": 99999,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": "spawn_main(parent_pid=99999) --multiprocessing-fork",
                }
            ],
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertFalse(any(action.startswith("taskkill:") for action in actions), actions)

    def test_stop_dev_rechecks_an_exact_checkout_orphan_worker_after_taskkill(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, _, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46152,
                    "ParentProcessId": 99999,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": "spawn_main(parent_pid=99999) --multiprocessing-fork",
                }
            ],
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": None,
                "frontend_launcher_pid": None,
                "backend_child_pids": [46152],
                "backend_port_owner_pids": [46152],
                "frontend_port_owner_pids": [],
            },
            taskkill_removes_process=False,
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_uses_final_state_when_taskkill_races_an_exited_process(self) -> None:
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46153,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": '"__ROOT__\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app',
                }
            ],
            taskkill_exit_code=1,
            taskkill_removes_process=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertTrue(any(action.startswith("taskkill:") for action in actions), actions)

    def test_stop_dev_rescans_and_stops_an_exact_checkout_respawn(self) -> None:
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46154,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": '"__ROOT__\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app',
                }
            ],
            respawn_process={
                "ProcessId": 46155,
                "ParentProcessId": 46154,
                "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                "CommandLine": "spawn_main(parent_pid=46154) --multiprocessing-fork",
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertTrue(
            any(action.startswith("taskkill:") and "/PID 46155 " in action for action in actions),
            actions,
        )

    def test_stop_dev_posts_only_to_a_fresh_exact_backend_port_owner(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46161,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": '"__ROOT__\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app',
                }
            ],
            port_owner_pid=46161,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 46161,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [46161],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        posts = [action for action in actions if action.startswith("post:")]
        self.assertEqual(
            posts,
            [f"post:http://127.0.0.1:{backend_port}/api/stop redirects:0 timeout:1"],
        )
        self.assertTrue(any(action.startswith("taskkill:") for action in actions), actions)

    def test_stop_dev_quiesces_manifest_authorized_external_python_backend(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46164,
                    "ParentProcessId": 1,
                    "ExecutablePath": "D:\\Python\\python.exe",
                    "CommandLine": '"D:\\Python\\python.exe" -m uvicorn app.main:app',
                },
                {
                    "ProcessId": 46165,
                    "ParentProcessId": 46164,
                    "ExecutablePath": "D:\\Python\\python.exe",
                    "CommandLine": "spawn_main(parent_pid=46164) --multiprocessing-fork",
                },
            ],
            port_owner_pid=46164,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 46164,
                "frontend_launcher_pid": None,
                "backend_executable": "D:\\Python\\python.exe",
                "backend_child_pids": [46165],
                "backend_port_owner_pids": [46164],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        taskkills = [action for action in actions if action.startswith("taskkill:")]
        self.assertTrue(any("/PID 46164 " in action for action in taskkills), actions)
        self.assertTrue(any("/PID 46165 " in action for action in taskkills), actions)
        self.assertTrue(any(action.startswith("post:") for action in actions), actions)

    def test_stop_dev_cleans_exact_root_launcher_but_preserves_malformed_manifest(self) -> None:
        completed, actions, ports_exist, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46166,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": '"__ROOT__\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app',
                }
            ],
            ports_manifest="{malformed",
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertTrue(any(action.startswith("taskkill:") for action in actions), actions)
        self.assertTrue(ports_exist)

    def test_stop_dev_treats_a_legacy_manifest_without_backend_executable_as_untrusted(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        legacy_manifest = json.dumps(
            {
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 46168,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [46168],
                "frontend_port_owner_pids": [],
                "generated_at": "2026-01-01T00:00:00.0000000Z",
            }
        )
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46168,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": '"__ROOT__\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app',
                }
            ],
            port_owner_pid=46168,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest=legacy_manifest,
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertFalse(any(action.startswith("post:") for action in actions), actions)
        self.assertTrue(
            any(action.startswith("taskkill:") and "/PID 46168 " in action for action in actions),
            actions,
        )
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_accepts_a_legacy_manifest_without_backend_base_executable(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        legacy_manifest = json.dumps(
            {
                "root": "__ROOT__",
                "backend_executable": "D:\\Python\\python.exe",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 46169,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [46169],
                "frontend_port_owner_pids": [],
                "generated_at": "2026-01-01T00:00:00.0000000Z",
            }
        )
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46169,
                    "ParentProcessId": 1,
                    "ExecutablePath": "D:\\Python\\python.exe",
                    "CommandLine": '"D:\\Python\\python.exe" -m uvicorn app.main:app',
                }
            ],
            port_owner_pid=46169,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest=legacy_manifest,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertTrue(any(action.startswith("post:") for action in actions), actions)
        self.assertTrue(
            any(action.startswith("taskkill:") and "/PID 46169 " in action for action in actions),
            actions,
        )
        self.assertFalse(ports_exist)
        self.assertFalse(processes_exist)

    def test_stop_dev_rejects_an_invalid_backend_base_executable_without_broadening_authority(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46170,
                    "ParentProcessId": 1,
                    "ExecutablePath": "C:\\Python\\python.exe",
                    "CommandLine": '"C:\\Python\\python.exe" -m uvicorn app.main:app',
                }
            ],
            port_owner_pid=46170,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_executable": "__ROOT__\\.venv\\Scripts\\python.exe",
                "backend_base_executable": "python.exe",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 46170,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [46170],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertFalse(
            any(action.startswith(("post:", "taskkill:", "stop:")) for action in actions),
            actions,
        )
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_fails_closed_on_unknown_recorded_backend_port_owner(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46167,
                    "ParentProcessId": 1,
                    "ExecutablePath": "C:\\Windows\\unrelated.exe",
                    "CommandLine": "unrelated-listener",
                }
            ],
            port_owner_pid=46167,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": None,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertFalse(any(action.startswith("post:") for action in actions), actions)
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_falls_back_to_exact_process_kill_when_api_stop_fails(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46162,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": '"__ROOT__\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app',
                }
            ],
            port_owner_pid=46162,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 46162,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [46162],
                "frontend_port_owner_pids": [],
            },
            api_post_fails=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertTrue(any(action.startswith("post:") for action in actions), actions)
        self.assertTrue(any(action.startswith("taskkill:") for action in actions), actions)

    def test_stop_dev_skips_api_when_recorded_port_owner_lookup_is_unavailable(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46163,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": '"__ROOT__\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app',
                }
            ],
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 46163,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [46163],
                "frontend_port_owner_pids": [],
            },
            port_owner_lookup_available=False,
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertFalse(any(action.startswith("post:") for action in actions), actions)
        self.assertTrue(any(action.startswith("taskkill:") for action in actions), actions)
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_fails_closed_when_taskkill_reports_failure(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, _, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46201,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": '"__ROOT__\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app',
                }
            ],
            port_owner_pid=46201,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 46201,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [46201],
                "frontend_port_owner_pids": [],
            },
            taskkill_exit_code=1,
            taskkill_removes_process=False,
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_fails_closed_when_taskkill_target_survives(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, _, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[
                {
                    "ProcessId": 46301,
                    "ParentProcessId": 1,
                    "ExecutablePath": "__ROOT__\\.venv\\Scripts\\python.exe",
                    "CommandLine": '"__ROOT__\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app',
                }
            ],
            port_owner_pid=46301,
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": 46301,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [46301],
                "frontend_port_owner_pids": [],
            },
            taskkill_exit_code=0,
            taskkill_removes_process=False,
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_fails_closed_when_process_discovery_is_unavailable_without_manifests(self) -> None:
        completed, actions, _, _ = self.run_stop_dev_selection_fixture(
            processes=[],
            cim_available=False,
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])

    def test_stop_dev_rejects_a_malformed_ports_manifest_before_destructive_action(self) -> None:
        completed, actions, ports_exist, _ = self.run_stop_dev_selection_fixture(
            processes=[],
            ports_manifest="{malformed",
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": 45001,
                "frontend_port": 45002,
                "backend_launcher_pid": None,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])
        self.assertTrue(ports_exist)

    def test_stop_dev_rejects_a_malformed_process_manifest_before_destructive_action(self) -> None:
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[],
            ports_manifest={
                "backend_port": 45101,
                "frontend_port": 45102,
            },
            processes_manifest="{malformed",
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_rejects_a_process_manifest_from_another_checkout(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[],
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__-other",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": None,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertNotEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])
        self.assertTrue(ports_exist)
        self.assertTrue(processes_exist)

    def test_stop_dev_accepts_a_valid_ports_only_manifest_after_interrupted_startup(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, _ = self.run_stop_dev_selection_fixture(
            processes=[],
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])
        self.assertFalse(ports_exist)

    def test_stop_dev_accepts_a_valid_process_only_manifest_after_interrupted_startup(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, _, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[],
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": None,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])
        self.assertFalse(processes_exist)

    def test_stop_dev_removes_valid_manifests_when_no_checkout_processes_exist(self) -> None:
        backend_port = self.unused_local_port()
        frontend_port = self.unused_local_port()
        completed, actions, ports_exist, processes_exist = self.run_stop_dev_selection_fixture(
            processes=[],
            ports_manifest={
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            },
            processes_manifest={
                "root": "__ROOT__",
                "backend_port": backend_port,
                "frontend_port": frontend_port,
                "backend_launcher_pid": None,
                "frontend_launcher_pid": None,
                "backend_child_pids": [],
                "backend_port_owner_pids": [],
                "frontend_port_owner_pids": [],
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)
        self.assertEqual(actions, [])
        self.assertFalse(ports_exist)
        self.assertFalse(processes_exist)

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
