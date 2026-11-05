# MATRIX self-hosted browser runner self-healing watchdog.
# Runs only on the user's authorized Windows machine, under an interactive user.
# Never reads or stores betting credentials, bypasses a provider quota, or sends signals.
[CmdletBinding()]
param(
    [string]$RunnerRoot = 'C:\actions-runner',
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA 'MATRIX\runner-watchdog')
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath (Join-Path $RunnerRoot '.runner') -PathType Leaf)) {
    throw "MATRIX_RUNNER_NOT_REGISTERED: $RunnerRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $RunnerRoot 'run.cmd') -PathType Leaf)) {
    throw "MATRIX_RUNNER_RUN_CMD_NOT_FOUND: $RunnerRoot"
}
$RunnerRoot = (Resolve-Path -LiteralPath $RunnerRoot).Path
New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
$mutex = New-Object System.Threading.Mutex($false, 'Local\MATRIX_Browser_Runner_Health')
$acquired = $false
try {
    $acquired = $mutex.WaitOne(0)
    if (-not $acquired) {
        Write-Output '{"status":"SKIPPED_ANOTHER_WATCHDOG_ACTIVE","real_money":"BLOCKED"}'
        return
    }
    $now = [DateTime]::UtcNow
    $stateFile = Join-Path $StateRoot 'last_start_attempt_utc.txt'
    $active = @(Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue)
    $report = [ordered]@{
        schema = 'MATRIX_WINDOWS_RUNNER_LOCAL_WATCHDOG_V1'
        checked_at_utc = $now.ToString('o')
        runner_root = $RunnerRoot
        listener_count = $active.Count
        status = 'RUNNER_ALREADY_RUNNING_LOCAL_NOT_GITHUB_VERIFIED'
        restart_requested = $false
        github_online_verified = $false
        automatic_wagering = $false
        real_money = 'BLOCKED'
    }
    if ($active.Count -eq 0) {
        $last = [DateTime]::MinValue
        if (Test-Path -LiteralPath $stateFile -PathType Leaf) {
            $raw = Get-Content -LiteralPath $stateFile -Raw -ErrorAction SilentlyContinue
            $parsed = [DateTime]::MinValue
            if ([DateTime]::TryParse($raw, [ref]$parsed)) {
                $last = $parsed.ToUniversalTime()
            }
        }
        if (($now - $last).TotalSeconds -lt 240) {
            $report.status = 'RESTART_COOLDOWN_NO_DUPLICATE'
        } else {
            # Persist attempt BEFORE starting: a failed process must not be
            # relaunched in an endless loop every time Task Scheduler fires.
            $now.ToString('o') | Set-Content -LiteralPath $stateFile -Encoding ASCII
            Start-Process -FilePath $env:ComSpec -ArgumentList '/d /c run.cmd' -WorkingDirectory $RunnerRoot -WindowStyle Minimized
            $report.status = 'RUNNER_START_REQUESTED_ON_LOCAL_HOST'
            $report.restart_requested = $true
        }
    }
    $json = $report | ConvertTo-Json -Depth 4 -Compress
    $json | Set-Content -LiteralPath (Join-Path $StateRoot 'last_status.json') -Encoding UTF8
    Write-Output $json
}
finally {
    if ($acquired) { $mutex.ReleaseMutex() | Out-Null }
    $mutex.Dispose()
}
