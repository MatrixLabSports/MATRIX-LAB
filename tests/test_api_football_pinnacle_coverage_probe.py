import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from tools.api_football_pinnacle_coverage_probe import run


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {
            "x-ratelimit-requests-limit": "7500",
            "x-ratelimit-requests-remaining": "7300",
            "X-RateLimit-Limit": "300",
            "X-RateLimit-Remaining": "299",
        }
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return self._payload


def _registry(path: Path):
    payload = {
        "events": [
            {
                "provider_fixture_id": "100",
                "event_start_utc": "2026-09-29T12:00:00+00:00",
                "home_team": "A",
                "away_team": "B",
                "competition": "League",
                "country": "X",
            },
            {
                "provider_fixture_id": "101",
                "event_start_utc": "2026-09-28T00:00:00+00:00",
                "home_team": "C",
                "away_team": "D",
                "competition": "League",
                "country": "X",
            },
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_future_only_and_pinnacle_markets(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _registry(registry)
    session = Mock()
    session.get.return_value = FakeResponse({
        "errors": {},
        "response": [{
            "bookmakers": [{
                "id": 4,
                "name": "Pinnacle",
                "bets": [{
                    "id": 1,
                    "name": "Match Winner",
                    "values": [
                        {"value": "Home", "odd": "1.80"},
                        {"value": "Draw", "odd": "3.40"},
                        {"value": "Away", "odd": "4.10"},
                    ],
                }],
            }],
        }],
    })
    result = run(
        "secret",
        registry,
        tmp_path / "out",
        session=session,
        now=datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc),
        capture_clock=lambda: datetime(2026, 9, 28, 7, 0, 5, tzinfo=timezone.utc),
    )
    assert result["target_fixture_count"] == 1
    assert result["network_calls_performed"] == 1
    assert result["fixtures_with_pinnacle_odds"] == 1
    assert result["coverage_rate"] == 1.0
    assert result["unique_markets"] == ["Match Winner"]
    assert result["capture_timestamp_scope"] == "PER_FIXTURE_RESPONSE"
    assert result["fixtures"][0]["captured_at_utc"] == "2026-09-28T07:00:05+00:00"
    assert result["real_money"] == "BLOCKED"


def test_empty_odds_is_valid_zero_coverage(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _registry(registry)
    session = Mock()
    session.get.return_value = FakeResponse({"errors": {}, "response": []})
    result = run(
        "secret",
        registry,
        tmp_path / "out",
        session=session,
        now=datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc),
    )
    assert result["status"] == "PASS"
    assert result["fixtures_with_pinnacle_odds"] == 0
    assert result["fixtures_without_pinnacle_odds"] == 1


def test_provider_error_blocks(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _registry(registry)
    session = Mock()
    session.get.return_value = FakeResponse({"errors": {"access": "blocked"}, "response": []})
    result = run(
        "secret",
        registry,
        tmp_path / "out",
        session=session,
        now=datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc),
    )
    assert result["status"] == "BLOCKED"
    assert result["provider_error_count"] == 1
