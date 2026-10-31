"""Inspect missing canonical sources without paid network transport."""
import json
from tools import telegram_green_signal_alerts as supervisor

def test_diagnostic_reports_source_paths_without_network(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("MATRIX_SUPERVISOR_OFFLINE_PREFLIGHT", raising=False)
    monkeypatch.delenv("MATRIX_INDEPENDENT_SOURCE_READINESS", raising=False)
    monkeypatch.delenv("MATRIX_INDEPENDENT_CANDIDATE_INVENTORY", raising=False)
    monkeypatch.delenv("MATRIX_API_FOOTBALL_AUTHORIZED", raising=False)
    monkeypatch.setenv("MATRIX_INDEPENDENT_SOURCE_DIAGNOSTIC", "1")
    monkeypatch.setattr(supervisor, "FOOTBALL_ROOT", tmp_path / "football")
    monkeypatch.setattr(supervisor, "TENNIS_ROOT", tmp_path / "tennis")
    monkeypatch.setattr(supervisor, "over25_signal_governance_authorized", lambda: (False, {}))
    def forbidden(*args, **kwargs):
        raise AssertionError("NETWORK_NOT_ALLOWED")
    monkeypatch.setattr(supervisor.requests, "Session", forbidden)
    supervisor.main()
    result=json.loads(capsys.readouterr().out)
    assert result["status"] == "SOURCE_PATH_DIAGNOSTIC_ONLY"
    assert result["over25_governance_authorized"] is False
    assert len(result["inventory"]["football"]) == 2
    assert len(result["inventory"]["tennis"]) == 2
    assert result["api_calls_made"] == 0
    assert result["telegram_messages_sent"] == 0
