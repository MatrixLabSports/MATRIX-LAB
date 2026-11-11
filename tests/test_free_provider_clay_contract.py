"""Offline regression for Hard/Clay free provider coverage without false admission."""
from __future__ import annotations

import json
import sys

from tools import free_provider_daily_coverage as coverage


class FakeResponse:
    def __init__(self, data):
        self._data = data
        self.content = json.dumps(data).encode("utf-8")
        self.headers = {"content-type": "application/json"}
        self.status_code = 200

    def json(self):
        return self._data


def test_clay_and_hard_from_same_free_request(monkeypatch, tmp_path):
    calls = []

    def fake_get(url, *, headers, params, timeout):
        calls.append(url)
        if "football-data.org" in url:
            assert "X-Auth-Token" in headers
            return FakeResponse({"matches": []})
        assert "livetennisapi.com" in url
        assert "X-API-Key" in headers
        assert params["tour"] == "challenger"
        return FakeResponse({"data": [
            {"id": 101, "start_time": "2026-11-11T18:00:00Z",
             "event_date": "2026-11-11", "tour": "challenger",
             "surface": "clay", "player1_name": "A",
             "player2_name": "B", "status": "scheduled"},
            {"id": 102, "start_time": "2026-11-12T20:00:00Z",
             "event_date": "2026-11-12", "tour": "challenger",
             "surface": "HARD", "player1_name": "C",
             "player2_name": "D", "status": "scheduled"},
            {"id": 103, "start_time": "2026-11-11T22:00:00Z",
             "event_date": "2026-11-11", "tour": "challenger",
             "surface": "grass", "status": "scheduled"},
        ]})

    monkeypatch.setattr(coverage.requests, "get", fake_get)
    monkeypatch.setenv("FOOTBALL_DATA_ORG_KEY", "synthetic_offline_test")
    monkeypatch.setenv("LIVE_TENNIS_API_KEY", "synthetic_offline_test")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["coverage", "--date", "2026-11-11"])
    assert coverage.main() == 0

    output = tmp_path / "evidence/free_providers/2026-11-11/MATRIX_FREE_PROVIDER_COVERAGE_SNAPSHOT.json"
    data = json.loads(output.read_text(encoding="utf-8"))
    tennis = data["providers"]["live_tennis_api"]
    assert len(calls) == 2
    assert tennis["d0_clay_rows"] == 1
    assert tennis["d0_d2_clay_rows"] == 1
    assert [r["provider_match_id"] for r in tennis["d0_d2_clay_candidates"]] == [101]
    assert tennis["d0_hard_rows"] == 0
    assert tennis["d0_d2_hard_rows"] == 1
    assert [r["provider_match_id"] for r in tennis["d0_d2_hard_candidates"]] == [102]
    assert data["promotion"]["automatic_model_feed"] is False
    assert data["promotion"]["automatic_counter_increment"] is False
    assert data["protections"]["real_money"] == "BLOCKED"
    assert data["protections"]["metrics_opened"] is False
    assert data["protections"]["secrets_persisted"] is False
