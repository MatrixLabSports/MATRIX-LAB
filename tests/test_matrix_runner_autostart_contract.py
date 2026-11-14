"""Offline contract for the opt-in Windows Runner user-login recovery helper."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "tools/windows/install_matrix_browser_runner_autostart.ps1"


def test_autostart_requires_existing_registered_runner_and_is_opt_in():
    body = INSTALLER.read_text(encoding="utf-8")
    assert "[switch]$StartNow" in body
    assert "'.runner'" in body
    assert "'run.cmd'" in body
    assert "MATRIX_RUNNER_INSTALLATION_NOT_FOUND" in body
    assert "[Environment+SpecialFolder]::Startup" in body
    assert "MATRIX-Browser-Runner.lnk" in body


def test_autostart_is_not_an_odds_or_money_bypass():
    body = INSTALLER.read_text(encoding="utf-8")
    assert "Get-Process -Name 'Runner.Listener'" in body
    assert "github_online_verified = $false" in body
    assert "requires_user_login = $true" in body
    assert "automatic_wagering = $false" in body
    assert "real_money = 'BLOCKED'" in body
    assert "Invoke-WebRequest" not in body
    assert "curl.exe" not in body
    assert "TELEGRAM_BOT_TOKEN" not in body
