from __future__ import annotations

import io
import json
from datetime import date
from urllib.parse import parse_qs

import pytest

from tools.cor0203_api_tennis_discovery import (
    ApiTennisDiscoveryClient,
    ApiTennisDiscoveryError,
    build_discovery_registry,
)


class FakeResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RecordingOpener:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []

    def __call__(self, request, timeout=20.0):
        self.requests.append(request)
        return FakeResponse(self.payloads.pop(0))


def fixture(
    *,
    event_key="1001",
    p1="11",
    p2="22",
    date_value="2026-09-26",
    time_value="12:00",
    tournament_key="500",
    surface_event_type="Challenger Men Singles",
    status="",
):
    return {
        "event_key": event_key,
        "event_date": date_value,
        "event_time": time_value,
        "event_first_player": "Player A",
        "first_player_key": p1,
        "event_second_player": "Player B",
        "second_player_key": p2,
        "event_status": status,
        "event_type_type": surface_event_type,
        "tournament_name": "Test Challenger",
        "tournament_key": tournament_key,
        "tournament_round": "Quarter-finals",
        "tournament_season": "2026",
        "event_live": "0",
    }


def draw(surface="Hard", source="draw_feed"):
    return {
        "success": 1,
        "result": {
            "tournament": {
                "tournament_key": "500",
                "tournament_name": "Test Challenger",
                "tournament_surface": surface,
                "tournament_season": "2026",
            },
            "source": source,
            "brackets": [],
        },
    }


def test_client_uses_post_body_not_secret_bearing_url():
    opener = RecordingOpener([{"success": 1, "result": []}])
    key = "secret-key-123"
    client = ApiTennisDiscoveryClient(key, opener=opener)

    client.fixtures(date(2026, 9, 26), date(2026, 9, 27))

    request = opener.requests[0]
    assert request.full_url == "https://api.api-tennis.com/tennis/"
    assert key not in request.full_url
    form = parse_qs(request.data.decode("utf-8"))
    assert form["APIkey"] == [key]
    assert form["method"] == ["get_fixtures"]
    assert form["event_type_key"] == ["281"]
    assert form["timezone"] == ["UTC"]


def test_secret_echo_is_rejected():
    key = "do-not-persist-me"
    opener = RecordingOpener([{"success": 1, "result": [{"echo": key}]}])
    client = ApiTennisDiscoveryClient(key, opener=opener)
    with pytest.raises(ApiTennisDiscoveryError, match="SECRET_ECHO"):
        client.fixtures(date(2026, 9, 26), date(2026, 9, 26))


def test_hard_future_challenger_with_strong_ids_is_eligible():
    fixtures = {"success": 1, "result": [fixture()]}
    result = build_discovery_registry(
        fixture_payload=fixtures,
        draw_payloads={"500": draw("Hard")},
        as_of_utc="2026-09-25T23:00:00+00:00",
    )

    registry = result["world_registry"]
    assert registry["cor0203_eligible_events"] == 1
    row = registry["rows"][0]
    assert row["event_id"] == "api-tennis:event:1001"
    assert row["player1_id"] == "api-tennis:player:11"
    assert row["player2_id"] == "api-tennis:player:22"
    assert row["surface"] == "Hard"
    assert len(row["source_snapshot_sha256"]) == 64
    assert row["cor0203_eligible"] is True


def test_missing_player_id_is_rejected_not_replaced_by_name():
    fixtures = {"success": 1, "result": [fixture(p2="")]}
    result = build_discovery_registry(
        fixture_payload=fixtures,
        draw_payloads={"500": draw("Hard")},
        as_of_utc="2026-09-25T23:00:00+00:00",
    )
    assert result["world_registry"]["cor0203_eligible_events"] == 0
    assert "PLAYER_KEYS_NOT_FIXED" in result["provider_rejected"][0]["blockers"]


def test_non_hard_surface_is_rejected():
    fixtures = {"success": 1, "result": [fixture()]}
    result = build_discovery_registry(
        fixture_payload=fixtures,
        draw_payloads={"500": draw("Clay")},
        as_of_utc="2026-09-25T23:00:00+00:00",
    )
    assert result["world_registry"]["cor0203_eligible_events"] == 0
    assert "SURFACE_OUT_OF_DOMAIN" in result["provider_rejected"][0]["blockers"]


def test_missing_draw_surface_is_rejected():
    fixtures = {"success": 1, "result": [fixture()]}
    result = build_discovery_registry(
        fixture_payload=fixtures,
        draw_payloads={},
        as_of_utc="2026-09-25T23:00:00+00:00",
    )
    assert result["world_registry"]["cor0203_eligible_events"] == 0
    assert "DRAW_SURFACE_MISSING" in result["provider_rejected"][0]["blockers"]


def test_started_event_is_rejected():
    fixtures = {
        "success": 1,
        "result": [fixture(date_value="2026-09-25", time_value="20:00")],
    }
    result = build_discovery_registry(
        fixture_payload=fixtures,
        draw_payloads={"500": draw("Hard")},
        as_of_utc="2026-09-25T23:00:00+00:00",
    )
    assert result["world_registry"]["cor0203_eligible_events"] == 0
    assert "EVENT_NOT_FUTURE" in result["provider_rejected"][0]["blockers"]


def test_terminal_event_is_rejected_even_if_future_timestamp_is_bad_source_data():
    fixtures = {"success": 1, "result": [fixture(status="Finished")]}
    result = build_discovery_registry(
        fixture_payload=fixtures,
        draw_payloads={"500": draw("Hard")},
        as_of_utc="2026-09-25T23:00:00+00:00",
    )
    assert result["world_registry"]["cor0203_eligible_events"] == 0
    assert "TERMINAL_EVENT" in result["provider_rejected"][0]["blockers"]


def test_fixture_range_is_bounded():
    client = ApiTennisDiscoveryClient("k", opener=RecordingOpener([]))
    with pytest.raises(ValueError, match="DISCOVERY_RANGE_EXCEEDS_4_DAYS"):
        client.fixtures(date(2026, 9, 1), date(2026, 9, 6))
