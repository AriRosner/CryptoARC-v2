$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runtime.ps1")

$root = Get-CryptoArcRoot
$policy = Get-Content -LiteralPath (Join-Path $PSScriptRoot "mobile-audit-exception.json") -Raw | ConvertFrom-Json
$packageManager = Resolve-CryptoArcPackageManager
if ($packageManager.Name -ne "npm") {
  throw "Mobile audit upstream check requires npm."
}

$latest = (& $packageManager.FilePath view image-size version) -join ""
if ($LASTEXITCODE -ne 0 -or -not $latest) {
  throw "Unable to read the current image-size release from npm."
}
if ($latest -ne [string]$policy.known_latest_version) {
  throw "image-size changed from known latest $($policy.known_latest_version) to $latest; re-evaluate and remove the exception if patched."
}
$majorOneText = (& $packageManager.FilePath view "image-size@1" version --json) -join "`n"
if ($LASTEXITCODE -ne 0 -or -not $majorOneText) {
  throw "Unable to read compatible image-size 1.x releases from npm."
}
$parsedMajorOneVersions = $majorOneText | ConvertFrom-Json
$majorOneVersions = @($parsedMajorOneVersions | ForEach-Object { [version][string]$_ })
$latestCompatible = [string]($majorOneVersions | Sort-Object -Descending | Select-Object -First 1)
if ($latestCompatible -ne [string]$policy.known_latest_compatible_version) {
  throw "A compatible image-size 1.x release changed from $($policy.known_latest_compatible_version) to $latestCompatible; re-evaluate and remove the exception if patched."
}
if ([DateTimeOffset]::UtcNow -gt [DateTimeOffset]::Parse([string]$policy.expires_at)) {
  throw "The mobile image-size exception expired at $($policy.expires_at)."
}

Write-Host "image-size remains at reviewed compatible/latest versions $latestCompatible/$latest; exception expires $($policy.expires_at)."
