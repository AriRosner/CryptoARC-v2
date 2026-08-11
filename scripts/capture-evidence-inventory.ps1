param(
  [string]$BaseRef = 'origin/main',
  [string]$OutputPath = 'data/evidence/evidence-inventory.json'
)

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$insideWorktreeLines = @(git -C $root rev-parse --is-inside-work-tree 2>$null)
$insideWorktreeExit = $LASTEXITCODE
$insideWorktree = $insideWorktreeLines | Select-Object -First 1
if ($insideWorktreeExit -ne 0 -or $insideWorktree -ne 'true') {
  throw "Not a Git worktree: $root"
}

$statusLines = @(git -C $root status --porcelain)
if ($LASTEXITCODE -ne 0) {
  throw 'Unable to inspect Git worktree status.'
}
if ($statusLines.Count -gt 0) {
  throw 'Evidence inventory requires a clean worktree. Commit or isolate the current changes first.'
}

$headLines = @(git -C $root rev-parse HEAD)
$headExit = $LASTEXITCODE
$head = $headLines | Select-Object -First 1
if ($headExit -ne 0 -or -not $head) {
  throw 'Unable to resolve HEAD.'
}
$originMainLines = @(git -C $root rev-parse $BaseRef)
$originMainExit = $LASTEXITCODE
$originMain = $originMainLines | Select-Object -First 1
if ($originMainExit -ne 0 -or -not $originMain) {
  throw "Unable to resolve base ref: $BaseRef"
}
$mergeBaseLines = @(git -C $root merge-base HEAD $BaseRef)
$mergeBaseExit = $LASTEXITCODE
$mergeBase = $mergeBaseLines | Select-Object -First 1
if ($mergeBaseExit -ne 0 -or -not $mergeBase) {
  throw "Unable to resolve merge-base for HEAD and $BaseRef"
}
$branchLines = @(git -C $root branch --show-current)
$branchExit = $LASTEXITCODE
$branch = $branchLines | Select-Object -First 1
if ($branchExit -ne 0) {
  throw 'Unable to resolve the current branch.'
}
if ([string]::IsNullOrWhiteSpace([string]$branch)) {
  $branch = '(detached)'
}

$report = [ordered]@{
  artifact_type = 'cryptoarc_evidence_inventory'
  format_version = 1
  generated_at = [DateTime]::UtcNow.ToString('o')
  code_state = [ordered]@{
    head = $head.Trim()
    origin_main = $originMain.Trim()
    merge_base = $mergeBase.Trim()
    branch = $branch.Trim()
    dirty = $false
    origin_main_is_ancestor = $mergeBase.Trim() -eq $originMain.Trim()
    exact_main_state_captured = $true
  }
  source_access = [ordered]@{ state = 'unknown'; adapters = @() }
  evidence = [ordered]@{
    genuine_source_observations = 0
    fixture_source_observations = 0
    rejected_source_observations = 0
    shadow_samples = 0
    evaluated_shadow_samples = 0
    mode_separation_status = 'unknown'
  }
  machine_verifiable_readiness = [ordered]@{
    ready = $false
    blockers = @(
      'runtime readiness reports were not supplied to the Git-only capture'
      'source access is unknown'
      'genuine source and shadow evidence remain deferred'
    )
  }
  deferred_physical_evidence = @(
    'genuine source soak'
    'all-cost shadow campaign'
    'production deployment rehearsal'
    'manual-live proof'
    'attended autonomous-live pilot'
    'post-run scale/hold/revise/stop decision'
  )
  authority = [ordered]@{
    live_trading_enabled = $false
    authority_changed = $false
    read_only = $true
  }
  privacy_note = 'Git-only inventory; no credentials, wallet material, auth tokens, or runtime data are collected.'
}

$resolvedOutput = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
  [System.IO.Path]::GetFullPath($OutputPath)
} else {
  [System.IO.Path]::GetFullPath((Join-Path $root $OutputPath))
}
$outputDirectory = Split-Path -Parent $resolvedOutput
if ($outputDirectory) {
  New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resolvedOutput -Encoding UTF8
Write-Output $resolvedOutput
