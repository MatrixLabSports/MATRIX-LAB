import json
from urllib.parse import parse_qs

import pytest

from tools.cor0203_api_tennis_discovery import ApiTennisDiscoveryClient


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


def fixture(event_key="123"):
    return {
        "event_key": event_key,
        "event_date": "2026-09-27",
        "event_time": "12:00",
        "event_first_player": "Player A",
        "first_player_key": "10",
        "event_second_player": "Player B",
        "second_player_key": "20",
        "event_status": "Finished",
        "event_winner": "First Player",
        "event_final_result": "2 - 0",
        "event_type_type": "Challenger Men Singles",
        "tournament_key": "500",
        "tournament_name": "Test Challenger",
        "tournament_round": "Semi-finals",
        "tournament_season": "2026",
        "event_live": "0",
    }


def test_fixture_lookup_uses_match_key_and_hides_secret_from_url():
    opener = RecordingOpener([{"success": 1, "result": [fixture()]}])
    key = "secret-key-lookup"
    client = ApiTennisDiscoveryClient(key, opener=opener)

    payload = client.fixture_by_match_key("123")

    assert payload["success"] == 1
    request = opener.requests[0]
    assert request.full_url == "https://api.api-tennis.com/tennis/"
    assert key not in request.full_url
    form = parse_qs(request.data.decode("utf-8"))
    assert form["method"] == ["get_fixtures"]
    assert form["match_key"] == ["123"]
    assert form["timezone"] == ["UTC"]


@pytest.mark.parametrize("value", ["", "abc", "0", "-1"])
def test_fixture_lookup_rejects_invalid_match_key(value):
    client = ApiTennisDiscoveryClient("k", opener=RecordingOpener([]))
    with pytest.raises(ValueError, match="MATCH_KEY_INVALID"):
        client.fixture_by_match_key(value)
