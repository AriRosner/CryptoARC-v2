$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$errors = @()
$readmePath = Join-Path $root "README.md"
$badgePath = Join-Path $root "badges/code-lines.json"
$badge = Get-Content -LiteralPath $badgePath -Raw | ConvertFrom-Json
$badgeMessage = [Uri]::EscapeDataString([string]$badge.message)
$expectedBadge = "![Source lines](https://img.shields.io/badge/source%20lines-$badgeMessage-blue)"
$readme = [IO.File]::ReadAllText($readmePath)
if (-not $readme.Contains($expectedBadge)) {
  $errors += "README.md -> source-lines badge must match badges/code-lines.json and avoid private raw endpoints."
}

$markdownFiles = Get-ChildItem -LiteralPath $root -Recurse -Filter "*.md" |
  Where-Object {
    $_.FullName -notmatch "\\node_modules\\" -and
    $_.FullName -notmatch "\\.venv\\" -and
    $_.FullName -notmatch "\\dist\\" -and
    $_.FullName -notmatch "\\build\\"
  }

foreach ($file in $markdownFiles) {
  $matches = Select-String -LiteralPath $file.FullName -Pattern "\[[^\]]+\]\(([^)]+)\)" -AllMatches
  foreach ($lineMatch in $matches) {
    foreach ($match in $lineMatch.Matches) {
      $target = $match.Groups[1].Value
      if ($target -match "^(https?:|mailto:|#)") {
        continue
      }
      $targetPath = ($target -split "#")[0]
      if ([string]::IsNullOrWhiteSpace($targetPath)) {
        continue
      }
      $resolved = Join-Path $file.DirectoryName $targetPath
      if (-not (Test-Path -LiteralPath $resolved)) {
        $relativeFile = Resolve-Path -LiteralPath $file.FullName -Relative
        $errors += "$relativeFile -> $target"
      }
    }
  }
}

if ($errors.Count -gt 0) {
  $errors | ForEach-Object { Write-Error $_ }
  throw "Markdown link check failed."
}

Write-Host "All relative Markdown links resolve."
