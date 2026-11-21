"""Fail-closed independent supervisor never mistakes expired paid transport for authorization."""
import json
import pytest
from tools import telegram_green_signal_alerts as supervisor


def test_missing_paid_authorization_emits_structured_blocker(monkeypatch, capsys):
    monkeypatch.delenv("MATRIX_SUPERVISOR_OFFLINE_PREFLIGHT", raising=False)
    monkeypatch.delenv("MATRIX_INDEPENDENT_SOURCE_READINESS", raising=False)
    monkeypatch.delenv("MATRIX_API_FOOTBALL_AUTHORIZED", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(SystemExit, match="TELEGRAM_BOT_TOKEN_NOT_CONFIGURED"):
        supervisor.main()
    output = capsys.readouterr().out.strip().splitlines()
    assert output, "MISSING_EXPLICIT_PAID_TRANSPORT_BLOCKER"
    route = json.loads(output[0])
    assert route["status"] == "INDEPENDENT_SOURCE_SUPERVISOR_STARTED"
    assert route["paid_api_football_calls_allowed"] is False
    assert route["signal_emission_certified"] is False
    assert route["real_money"] == "BLOCKED"
    assert route["automatic_wagering"] is False
