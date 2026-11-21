"""Guardrails for MATRIX's opt-in user-session Windows runner recovery."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / "tools/windows/matrix_runner_local_watchdog.ps1"
INSTALL = ROOT / "tools/windows/install_matrix_runner_watchdog_task.ps1"


def test_runner_watchdog_requires_real_registered_runner_and_never_claims_online():
    source = WATCHDOG.read_text(encoding="utf-8")
    assert "Join-Path $RunnerRoot '.runner'" in source
    assert "Join-Path $RunnerRoot 'run.cmd'" in source
    assert "RUNNER_ALREADY_RUNNING_LOCAL_NOT_GITHUB_VERIFIED" in source
    assert "github_online_verified = $false" in source
    assert "Get-Process -Name 'Runner.Listener'" in source
    assert "Local\\MATRIX_Browser_Runner_Health" in source


def test_runner_restart_is_serialized_and_throttled():
    source = WATCHDOG.read_text(encoding="utf-8")
    assert "$mutex.WaitOne(0)" in source
    assert "RESTART_COOLDOWN_NO_DUPLICATE" in source
    assert "TotalSeconds -lt 240" in source
    assert "Set-Content -LiteralPath $stateFile" in source
    assert "Start-Process -FilePath $env:ComSpec" in source
    assert "RUNNER_START_REQUESTED_ON_LOCAL_HOST" in source


def test_installer_persists_5m_task_only_in_interactive_user_session():
    source = INSTALL.read_text(encoding="utf-8")
    assert "[switch]$StartNow" in source
    assert "New-ScheduledTaskTrigger" in source
    assert "New-TimeSpan -Minutes 5" in source
    assert "Register-ScheduledTask -TaskName $taskName" in source
    assert "Get-ScheduledTask -TaskName $taskName" in source
    assert "-LogonType Interactive -RunLevel Limited" in source
    assert "needs_interactive_user_session = $true" in source
    assert "github_runner_online_verified = $false" in source


def test_neither_script_can_override_prices_or_real_money():
    content = WATCHDOG.read_text(encoding="utf-8") + INSTALL.read_text(encoding="utf-8")
    assert content.count("automatic_wagering = $false") >= 2
    assert content.count("real_money = 'BLOCKED'") >= 2
    for forbidden in ("Invoke-WebRequest", "Invoke-RestMethod", "TELEGRAM_BOT_TOKEN",
                      "ODDS_API_NET_KEY", "API_FOOTBALL_KEY", "p_matrix",
                      "Write-Host 'Online'", "REAL_MONEY=ENABLED"):
        assert forbidden not in content
