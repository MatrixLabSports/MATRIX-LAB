"""Fail-closed operational supervisor must never silently pass as live."""
import pytest
from tools import telegram_green_signal_alerts as supervisor

def test_missing_paid_authorization_emits_structured_blocker(monkeypatch, capsys):
    monkeypatch.delenv("MATRIX_SUPERVISOR_OFFLINE_PREFLIGHT", raising=False)
    monkeypatch.delenv("MATRIX_INDEPENDENT_SOURCE_READINESS", raising=False)
    monkeypatch.delenv("MATRIX_API_FOOTBALL_AUTHORIZED", raising=False)
    with pytest.raises(SystemExit, match="API_FOOTBALL_SUBSCRIPTION_NOT_VERIFIED_FAIL_CLOSED"):
        supervisor.main()
    import json
    output = capsys.readouterr().out.strip()
    result = json.loads(output)
    assert result["status"] == "BLOCKED_PAID_API_DEPENDENCY"
    assert result["independent_operational_path_certified"] is False
    assert result["telegram_messages_sent"] == 0
    assert result["real_money"] == "BLOCKED"
    assert result["automatic_wagering"] is False
