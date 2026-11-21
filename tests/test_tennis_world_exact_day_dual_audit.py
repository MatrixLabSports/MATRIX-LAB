from datetime import date
from pathlib import Path

import tools.tennis_world_exact_day_dual_audit as mod


class FakeRapidClient:
    def __init__(self, api_key):
        assert api_key == "test-rapid"
        self.request_count = 2


def test_exact_day_requires_only_rapidapi_and_marks_api_tennis_retired(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("RAPIDAPI_TENNIS_KEY", "test-rapid")
    monkeypatch.delenv("API_TENNIS_KEY", raising=False)
    monkeypatch.setattr(mod, "RapidApiTennisClient", FakeRapidClient)
    monkeypatch.setattr(
        mod,
        "build_world_inventory",
        lambda client, target_date_bogota: {
            "status": "PASS",
            "provider_inventory_complete": True,
            "world_inventory_complete": False,
            "events": [
                {
                    "circuit_family": "ATP",
                    "circuit_detail": "ATP_CHALLENGER",
                    "tournament_name": "Example Challenger",
                    "event_format": "SINGLES",
                },
                {
                    "circuit_family": "ITF",
                    "circuit_detail": "ITF_WOMEN",
                    "tournament_name": "W35 Example",
                    "event_format": "SINGLES",
                },
            ],
        },
    )
    out=tmp_path/"audit.json"
    result=mod.run(date(2026,10,15),out)
    assert result["primary_world_inventory"]["unique_match_count"] == 2
    assert result["source_architecture"]["paid_primary"] == "rapidapi_tennis"
    assert result["source_architecture"]["required_open_calendar_reconciliation"] == ["SofaScore","Flashscore"]
    assert result["source_architecture"]["api_tennis"]["status"] == "RETIRED_COST_UTILITY_DECISION"
    assert result["source_architecture"]["api_tennis"]["attempted"] is False
    assert result["source_architecture"]["two_paid_sources_required"] is False
    assert result["metrics_opened"] is False
    assert result["automatic_wagering"] is False
    assert result["real_money"] == "BLOCKED"
    assert out.is_file()
