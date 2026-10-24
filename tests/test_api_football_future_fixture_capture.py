from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from tools.api_football_future_fixture_capture import (
    default_target_date,
    run_capture,
)


def _response(rows):
    response = Mock()
    response.status_code = 200
    payload = {
        "get": "fixtures",
        "parameters": {"date": "2026-09-28", "timezone": "America/Bogota"},
        "errors": [],
        "results": len(rows),
        "paging": {"current": 1, "total": 1},
        "response": rows,
    }
    raw = __import__("json").dumps(payload, separators=(",", ":")).encode()
    response.content = raw
    response.json.return_value = payload
    response.headers = {
        "content-type": "application/json",
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": "98",
        "X-RateLimit-Limit": "10",
        "X-RateLimit-Remaining": "8",
    }
    return response


def fixture(*, fixture_id=100, when="2026-09-28T12:00:00+00:00", status="NS"):
    return {
        "fixture": {
            "id": fixture_id,
            "date": when,
            "timezone": "UTC",
            "status": {"short": status},
            "venue": {"id": 1, "name": "Stadium"},
        },
        "league": {
            "id": 39,
            "name": "Premier League",
            "country": "England",
            "season": 2026,
            "round": "Regular Season - 7",
        },
        "teams": {
            "home": {"id": 40, "name": "Home FC"},
            "away": {"id": 41, "name": "Away FC"},
        },
    }


def test_capture_persists_raw_and_future_registry(tmp_path):
    session = Mock()
    session.get.return_value = _response([
        fixture(fixture_id=100, when="2026-09-28T12:00:00+00:00"),
        fixture(fixture_id=101, when="2026-09-28T01:00:00+00:00"),
        fixture(fixture_id=102, when="2026-09-28T13:00:00+00:00", status="FT"),
    ])

    result = run_capture(
        api_key="test-key",
        out_dir=tmp_path,
        target_date="2026-09-28",
        session=session,
        captured_at_utc="2026-09-28T04:00:00+00:00",
    )

    session.get.assert_called_once_with(
        "https://v3.football.api-sports.io/fixtures",
        headers={"x-apisports-key": "test-key"},
        params={"date": "2026-09-28", "timezone": "America/Bogota"},
        timeout=20.0,
    )
    assert result["status"] == "PASS"
    assert result["fixtures_received"] == 3
    assert result["eligible_future_fixtures"] == 1
    assert result["rate_limit"]["daily_remaining"] == "98"

    registry = __import__("json").loads((tmp_path / "future_fixture_registry.json").read_text())
    assert len(registry["events"]) == 1
    event = registry["events"][0]
    assert event["provider_fixture_id"] == "100"
    assert event["provider_league_id"] == "39"
    assert event["provider_home_team_id"] == "40"
    assert event["provider_away_team_id"] == "41"
    assert registry["protections"]["outcomes_used"] is False
    assert registry["protections"]["odds_used"] is False
    assert registry["protections"]["real_money"] == "BLOCKED"

    request_text = (tmp_path / "request.json").read_text()
    assert "test-key" not in request_text
    assert "REDACTED" in request_text
    assert (tmp_path / "response_body.bin").exists()
    assert (tmp_path / "capture_manifest.json").exists()


def test_capture_rejects_missing_key_before_network(tmp_path):
    session = Mock()
    with pytest.raises(ValueError, match="API_FOOTBALL_KEY_NOT_CONFIGURED"):
        run_capture(
            api_key="",
            out_dir=tmp_path,
            target_date="2026-09-28",
            session=session,
        )
    session.get.assert_not_called()


def test_capture_rejects_provider_errors(tmp_path):
    response = Mock()
    response.status_code = 200
    payload = {"errors": {"token": "bad"}, "results": 0, "response": []}
    response.content = __import__("json").dumps(payload).encode()
    response.json.return_value = payload
    response.headers = {}
    session = Mock()
    session.get.return_value = response

    with pytest.raises(ValueError, match="API_FOOTBALL_PROVIDER_ERRORS"):
        run_capture(
            api_key="test-key",
            out_dir=tmp_path,
            target_date="2026-09-28",
            session=session,
            captured_at_utc="2026-09-28T04:00:00+00:00",
        )


def test_capture_deduplicates_provider_fixture_ids(tmp_path):
    session = Mock()
    session.get.return_value = _response([
        fixture(fixture_id=100, when="2026-09-28T12:00:00+00:00"),
        fixture(fixture_id=100, when="2026-09-28T12:00:00+00:00"),
    ])

    result = run_capture(
        api_key="test-key",
        out_dir=tmp_path,
        target_date="2026-09-28",
        session=session,
        captured_at_utc="2026-09-28T04:00:00+00:00",
    )

    assert result["eligible_future_fixtures"] == 1
    assert result["duplicate_fixture_ids"] == ["100"]


def test_default_target_date_is_next_bogota_day():
    now = datetime(2026, 9, 28, 4, 30, tzinfo=timezone.utc)
    assert default_target_date(now) == "2026-09-28"
