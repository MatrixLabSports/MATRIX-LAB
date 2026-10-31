"""Independent candidate inventory must not use expired paid transport."""
import json
from tools import telegram_green_signal_alerts as supervisor

def test_inventory_uses_governed_artifacts_without_network(monkeypatch, capsys):
    monkeypatch.delenv("MATRIX_SUPERVISOR_OFFLINE_PREFLIGHT", raising=False)
    monkeypatch.delenv("MATRIX_INDEPENDENT_SOURCE_READINESS", raising=False)
    monkeypatch.delenv("MATRIX_API_FOOTBALL_AUTHORIZED", raising=False)
    monkeypatch.setenv("MATRIX_INDEPENDENT_CANDIDATE_INVENTORY", "1")
    monkeypatch.setattr(supervisor, "discover_football", lambda dates: {"a": {}})
    monkeypatch.setattr(supervisor, "discover_tennis", lambda dates: {"b": {}})
    def forbidden(*args, **kwargs):
        raise AssertionError("NETWORK_NOT_ALLOWED")
    monkeypatch.setattr(supervisor.requests, "Session", forbidden)
    supervisor.main()
    output=json.loads(capsys.readouterr().out)
    assert output["status"] == "INVENTORY_ONLY_NO_LIVE_QUOTES"
    assert output["football_candidates"] == 1
    assert output["tennis_candidates"] == 1
    assert output["telegram_messages_sent"] == 0
    assert output["api_calls_made"] == 0
    assert output["independent_operational_path_certified"] is False
    assert output["real_money"] == "BLOCKED"
