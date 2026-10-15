from __future__ import annotations

from datetime import date
from pathlib import Path

from tools.cor0203_api_tennis_discovery import ApiTennisDiscoveryError
import tools.tennis_world_exact_day_dual_audit as mod


class FakeRapidClient:
    def __init__(self, api_key):
        self.request_count = 1


class FakeApiClient:
    def __init__(self, api_key):
        self.request_count = 2


def test_secondary_provider_failure_preserves_primary_capture_and_fails_closed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "RapidApiTennisClient", FakeRapidClient)
    monkeypatch.setattr(mod, "ApiTennisDiscoveryClient", FakeApiClient)
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
                    "circuit_detail": "CHALLENGER",
                    "tournament_name": "Example Challenger",
                    "event_format": "SINGLES",
                    "event_start_bogota": "2026-10-15T12:00:00-05:00",
                    "player1": {"name": "Player A"},
                    "player2": {"name": "Player B"},
                }
            ],
        },
    )

    def blocked_secondary(client, target):
        raise ApiTennisDiscoveryError("API_TENNIS_PROVIDER_FAILURE")

    monkeypatch.setattr(mod, "_fetch_api_rows_for_bogota_day", blocked_secondary)

    out_path = tmp_path / "audit.json"
    result = mod.run(date(2026, 10, 15), out_path)

    assert result["primary_world_inventory"]["provider"] == "rapidapi_tennis"
    assert result["primary_world_inventory"]["unique_match_count"] == 1
    assert result["secondary_crosscheck"]["provider"] == "api_tennis"
    assert result["secondary_crosscheck"]["status"] == "BLOCKED"
    assert result["secondary_crosscheck"]["blocker"] == "API_TENNIS_PROVIDER_FAILURE"
    assert result["secondary_crosscheck"]["attempted"] is True
    assert result["secondary_crosscheck"]["network_calls"] == 2
    assert result["status"] == "PASS_PRIMARY_PROVIDER_CAPTURE_SECONDARY_BLOCKED_WORLD_UNSEALED"
    assert result["world_inventory_complete"] is False
    assert result["automatic_model_feed"] is False
    assert result["metrics_opened"] is False
    assert result["automatic_wagering"] is False
    assert result["real_money"] == "BLOCKED"
    assert out_path.is_file()
