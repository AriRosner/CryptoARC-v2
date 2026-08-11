param(
    [switch]$FixtureOnly,
    [switch]$PhysicalWindowAuthorized,
    [string]$AuthorizationRecord = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($PhysicalWindowAuthorized) {
    if (-not $AuthorizationRecord) {
        throw "Physical mode requires -AuthorizationRecord pointing to a fresh JSON authorization."
    }
    $recordPath = (Resolve-Path -LiteralPath $AuthorizationRecord).Path
    $authorization = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    if ($authorization.scope -ne "production-rehearsal" -or -not $authorization.authorization_id) {
        throw "Authorization record must include scope=production-rehearsal and authorization_id."
    }
    $expiresAt = [DateTimeOffset]::Parse([string]$authorization.expires_at)
    if ($expiresAt -le [DateTimeOffset]::UtcNow) {
        throw "Physical rehearsal authorization is expired."
    }
    if ($env:LIVE_TRADING_ENABLED -and $env:LIVE_TRADING_ENABLED.Trim().ToLowerInvariant() -eq "true") {
        throw "Production recovery rehearsal is non-live; LIVE_TRADING_ENABLED must remain false."
    }
}

$python = if ($env:CRYPTOARC_PYTHON) {
    $env:CRYPTOARC_PYTHON
} elseif (Test-Path (Join-Path $repoRoot ".venv\Scripts\python.exe")) {
    Join-Path $repoRoot ".venv\Scripts\python.exe"
} else {
    "python"
}

Push-Location $repoRoot
try {
    $env:PYTHONPATH = "backend"
    & $python -m unittest tests.test_production_gate_rehearsal tests.test_restore_atomic tests.test_hot_wallet tests.test_signer_daemon -v
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

$mode = if ($PhysicalWindowAuthorized) { "AUTHORIZED_RECORD_VALIDATED" } else { "FIXTURE_ONLY" }
[ordered]@{
    status = "DEFERRED"
    mode = $mode
    fixture_only = -not $PhysicalWindowAuthorized
    ready = $false
    authority_changed = $false
    physical_steps = @(
        "password and TOTP restart rehearsal",
        "tailnet-only exposure verification",
        "wallet and signer identity/loss/rotation rehearsal",
        "source-loss and guarded protective-exit rehearsal",
        "backup, restore, restart, reconciliation, and kill-switch rehearsal"
    )
    operator_action = "Capture actual evidence only in the separately coordinated physical window; this script invokes no wallet or signer."
} | ConvertTo-Json -Depth 4
