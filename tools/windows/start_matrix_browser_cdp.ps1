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

$health = "http://127.0.0.1:$Port/json/version"
function Test-MatrixCdpHealth {
  try {
    $resp=Invoke-RestMethod -Uri $health -TimeoutSec 3
    return ($null -ne $resp -and -not [string]::IsNullOrWhiteSpace($resp.webSocketDebuggerUrl) -and
      ($resp.webSocketDebuggerUrl.StartsWith("ws://127.0.0.1:$Port/") -or
       $resp.webSocketDebuggerUrl.StartsWith("ws://localhost:$Port/")))
  } catch {
    return $false
  }
}

$already = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($already) {
  if (Test-MatrixCdpHealth) {
    Write-Output "MATRIX_BROWSER_CDP_ALREADY_HEALTHY=http://127.0.0.1:$Port"
    Write-Output "MATRIX_BROWSER_READ_ONLY_COLLECTION=ENFORCED_BY_WORKFLOW"
    exit 0
  }
  throw "MATRIX_BROWSER_PORT_OCCUPIED_BUT_CDP_UNVERIFIED"
}

$args = @(
  "--remote-debugging-port=$Port",
  "--remote-debugging-address=127.0.0.1",
  "--user-data-dir=$ProfileDir",
  "--no-first-run",
  "--no-default-browser-check"
)

Start-Process -FilePath $browser -ArgumentList $args | Out-Null
# Browser profile initialization is variable on Windows; never assume
# a fixed 3-second launch is enough. A bounded polling window prevents
# false failures without evading a real HTTP/403/429 access restriction.
$ready=$false
for ($attempt=1; $attempt -le 12; $attempt++) {
  Start-Sleep -Seconds 2
  if (Test-MatrixCdpHealth) {
    $ready=$true
    Write-Output "MATRIX_BROWSER_CDP_HEALTHY_ATTEMPT=$attempt"
    break
  }
}
if (-not $ready) {
  $listener=Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  Write-Output ("MATRIX_BROWSER_CDP_PORT_LISTENER_PRESENT=" + [bool]$listener)
  throw "MATRIX_BROWSER_CDP_START_FAILED_AFTER_BOUNDED_HEALTH_PROBES"
}
Write-Output "MATRIX_BROWSER_CDP_READY=http://127.0.0.1:$Port"
Write-Output "MATRIX_BROWSER_PROFILE=$ProfileDir"
Write-Output "MATRIX_BROWSER_READ_ONLY_COLLECTION=ENFORCED_BY_WORKFLOW"
