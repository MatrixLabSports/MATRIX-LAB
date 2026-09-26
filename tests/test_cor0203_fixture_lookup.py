from urllib.parse import parse_qs

import pytest

from tests.test_cor0203_api_tennis_discovery import RecordingOpener, fixture
from tools.cor0203_api_tennis_discovery import ApiTennisDiscoveryClient


def test_fixture_lookup_uses_match_key_and_hides_secret_from_url():
    opener = RecordingOpener([{"success": 1, "result": [fixture(event_key="123")]}])
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
