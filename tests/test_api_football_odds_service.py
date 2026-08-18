from unittest.mock import Mock

import pytest

from app.providers.api_football.odds_service import get_fixture_odds_raw


def test_prematch_odds_endpoint_and_counts():
    client = Mock()
    client.get.return_value = {"response": [{"fixture": {"id": 1}}, "bad", {"fixture": {"id": 2}}]}
    result = get_fixture_odds_raw(client, 123)
    client.get.assert_called_once_with("/odds", {"fixture": 123})
    assert result.received_count == 3
    assert result.rejected_count == 1
    assert len(result.response) == 2


def test_live_odds_endpoint():
    client = Mock()
    client.get.return_value = {"response": []}
    result = get_fixture_odds_raw(client, "123", live=True)
    client.get.assert_called_once_with("/odds/live", {"fixture": "123"})
    assert result.endpoint == "/odds/live"


def test_invalid_odds_response_fails_closed():
    client = Mock()
    client.get.return_value = {"response": {}}
    with pytest.raises(ValueError, match="inválida"):
        get_fixture_odds_raw(client, 123)
