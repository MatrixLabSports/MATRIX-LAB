param(
  [int]$Port = 9222,
  [string]$ProfileDir = "$env:LOCALAPPDATA\MATRIX\BrowserProfile"
)

$ErrorActionPreference = "Stop"

$candidatePaths = @(
  "$env:LOCALAPPDATA\Programs\Opera GX\launcher.exe",
  "$env:LOCALAPPDATA\Programs\Opera\launcher.exe",
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
)

$candidates = @($candidatePaths | Where-Object { $_ -and (Test-Path -LiteralPath $_) })

if (-not $candidates) {
  throw "MATRIX_BROWSER_NOT_FOUND"
}

$browser = [string]$candidates[0]
Write-Output "MATRIX_BROWSER_DETECTED=$browser"
New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

$already = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($already) {
  Write-Output "MATRIX_BROWSER_CDP_ALREADY_LISTENING=http://127.0.0.1:$Port"
  exit 0
}

$args = @(
  "--remote-debugging-port=$Port",
  "--user-data-dir=$ProfileDir",
  "--no-first-run",
  "--no-default-browser-check"
)

Start-Process -FilePath $browser -ArgumentList $args
Start-Sleep -Seconds 3

$health = "http://127.0.0.1:$Port/json/version"
try {
  $resp = Invoke-RestMethod -Uri $health -TimeoutSec 5
  if (-not $resp.webSocketDebuggerUrl) { throw "CDP_WEBSOCKET_MISSING" }
} catch {
  throw "MATRIX_BROWSER_CDP_START_FAILED"
}

Write-Output "MATRIX_BROWSER_CDP_READY=http://127.0.0.1:$Port"
Write-Output "MATRIX_BROWSER_PROFILE=$ProfileDir"
Write-Output "MATRIX_BROWSER_READ_ONLY_COLLECTION=ENFORCED_BY_WORKFLOW"
