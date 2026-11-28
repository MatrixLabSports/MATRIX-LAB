# Install MATRIX local runner recovery in Task Scheduler for the signed-in user.
# One-time, opt-in installation. No elevated/system privileges required.
# User's PC and interactive login must remain active for browser collection.
[CmdletBinding()]
param(
    [string]$RunnerRoot = 'C:\actions-runner',
    [switch]$StartNow
)
$ErrorActionPreference = 'Stop'
$taskName = 'MATRIX-Browser-Runner-Watchdog'
$scriptSource = Join-Path $PSScriptRoot 'matrix_runner_local_watchdog.ps1'
if (-not (Test-Path -LiteralPath $scriptSource -PathType Leaf)) {
    throw 'MATRIX_WATCHDOG_SOURCE_NOT_FOUND'
}
if (-not (Test-Path -LiteralPath (Join-Path $RunnerRoot '.runner') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $RunnerRoot 'run.cmd') -PathType Leaf)) {
    throw 'MATRIX_REGISTERED_RUNNER_NOT_FOUND'
}
$RunnerRoot = (Resolve-Path -LiteralPath $RunnerRoot).Path
$targetDir = Join-Path $env:LOCALAPPDATA 'MATRIX\runner-watchdog'
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
$installedScript = Join-Path $targetDir 'matrix_runner_local_watchdog.ps1'
Copy-Item -LiteralPath $scriptSource -Destination $installedScript -Force
if (-not (Test-Path -LiteralPath $installedScript -PathType Leaf)) {
    throw 'MATRIX_LOCAL_WATCHDOG_NOT_INSTALLED'
}
$escapedRoot = $RunnerRoot.Replace("'", "''")
# A separate launch file avoids nested PowerShell quoting in task arguments.
$launcher = Join-Path $targetDir 'matrix_runner_health_task.ps1'
$launcherText = @'
$ErrorActionPreference = 'Stop'
& '__WATCHDOG_SCRIPT__' -RunnerRoot '__RUNNER_ROOT__'
'@
$launcherText.Replace('__WATCHDOG_SCRIPT__', $installedScript.Replace("'", "''")).Replace('__RUNNER_ROOT__', $escapedRoot) |
    Set-Content -LiteralPath $launcher -Encoding UTF8

# Every five minutes for the next ten years, with a single task instance.
# The existing login Startup shortcut can coexist: the watchdog never duplicates
# a Runner.Listener and never runs without an interactive user session.
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$action = New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') `
    -Argument ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcher + '"') `
    -WorkingDirectory $RunnerRoot
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
$installed = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
if ($installed.TaskName -ne $taskName) {
    throw 'MATRIX_WATCHDOG_TASK_REGISTRATION_NOT_VERIFIED'
}
if ($StartNow) {
    & $launcher
}
$report = [ordered]@{
    schema = 'MATRIX_WINDOWS_RUNNER_TASK_INSTALL_V1'
    task_name = $taskName
    schedule_interval_minutes = 5
    registered = $true
    task_state = [string]$installed.State
    watchdog_script_present = (Test-Path -LiteralPath $installedScript -PathType Leaf)
    needs_interactive_user_session = $true
    github_runner_online_verified = $false
    real_money = 'BLOCKED'
    automatic_wagering = $false
}
$report | ConvertTo-Json -Compress
