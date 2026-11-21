# One-time, opt-in installation: run on the Windows 10 computer that hosts Opera.
# Does NOT run on GitHub-hosted runners, alter API/provider limits, or authorize bets.
[CmdletBinding()]
param(
    [string]$RunnerRoot = 'C:\actions-runner',
    [switch]$StartNow
)
$ErrorActionPreference = 'Stop'
$runnerMarker = Join-Path $RunnerRoot '.runner'
$runnerCmd = Join-Path $RunnerRoot 'run.cmd'
if (-not (Test-Path -LiteralPath $runnerMarker -PathType Leaf) -or
    -not (Test-Path -LiteralPath $runnerCmd -PathType Leaf)) {
    throw "MATRIX_RUNNER_INSTALLATION_NOT_FOUND: $RunnerRoot"
}
$RunnerRoot = (Resolve-Path -LiteralPath $RunnerRoot).Path
# Keep startup launcher outside a git working tree; never store any credentials.
$installDir = Join-Path $env:LOCALAPPDATA 'MATRIX\runner-autostart'
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
$launcherPath = Join-Path $installDir 'start_matrix_runner.ps1'
$escapedRoot = $RunnerRoot.Replace("'", "''")
$launcherTemplate = @'
$ErrorActionPreference = 'Stop'
$RunnerRoot = '__RUNNER_ROOT__'
$runner = Join-Path $RunnerRoot 'run.cmd'
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "MATRIX_RUNNER_COMMAND_NOT_FOUND"
}
# Do not create a second Runner.Listener if it is already active in this session.
$active = @(Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue)
if ($active.Count -gt 0) {
    Write-Output 'MATRIX_RUNNER_ALREADY_RUNNING_LOCAL'
    return
}
Start-Process -FilePath $env:ComSpec -ArgumentList '/d /c run.cmd' -WorkingDirectory $RunnerRoot -WindowStyle Minimized
Write-Output 'MATRIX_RUNNER_START_REQUESTED_LOCAL_GITHUB_ONLINE_NOT_YET_VERIFIED'
'@
$launcherTemplate.Replace('__RUNNER_ROOT__', $escapedRoot) |
    Set-Content -LiteralPath $launcherPath -Encoding UTF8
$startup = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
if (-not $startup) { throw 'WINDOWS_USER_STARTUP_FOLDER_UNAVAILABLE' }
$shortcutPath = Join-Path $startup 'MATRIX-Browser-Runner.lnk'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcutPath)
$link.TargetPath = Join-Path $PSHOME 'powershell.exe'
$link.Arguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Minimized -File "' + $launcherPath + '"'
$link.WorkingDirectory = $RunnerRoot
$link.WindowStyle = 7
$link.Description = 'Start authorized MATRIX GitHub Actions browser runner on user login'
$link.Save()
if (-not (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) {
    throw 'MATRIX_RUNNER_AUTOSTART_LINK_NOT_PERSISTED'
}
if ($StartNow) {
    & $launcherPath
    Start-Sleep -Seconds 4
}
$listenerCount = @(Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue).Count
$report = @{
    schema = 'MATRIX_WINDOWS_RUNNER_LOGIN_AUTOSTART_V1'
    runner_root = $RunnerRoot
    startup_shortcut_present = $true
    launcher_present = (Test-Path -LiteralPath $launcherPath -PathType Leaf)
    local_listener_count = $listenerCount
    github_online_verified = $false
    requires_user_login = $true
    real_money = 'BLOCKED'
    automatic_wagering = $false
}
$report | ConvertTo-Json -Depth 4
if ($StartNow -and $listenerCount -lt 1) {
    throw 'MATRIX_LISTENER_NOT_STARTED_LOCAL: check run.cmd output and runner registration'
}
