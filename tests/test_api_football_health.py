from unittest.mock import Mock

import requests

from app.providers.api_football.health import check_api_football_health


def test_api_football_health_reports_available_provider():
    client = Mock()
    client.get.return_value = {
        "response": {
            "account": {
                "firstname": "Test",
            },
        },
    }
    client.daily_limit = 100
    client.daily_remaining = 99

    result = check_api_football_health(client)

    client.get.assert_called_once_with("/status")
    assert result.available is True
    assert result.daily_limit == 100
    assert result.daily_remaining == 99

def test_api_football_health_reports_unavailable_provider_on_request_error():
    client = Mock()
    client.get.side_effect = requests.RequestException(
        "provider unavailable"
    )
    client.daily_limit = None
    client.daily_remaining = None

    result = check_api_football_health(client)

    assert result.available is False
    assert result.daily_limit is None
    assert result.daily_remaining is None