from unittest.mock import Mock

import pytest
import requests

from app.providers.api_football.client import ApiFootballClient
from app.providers.api_football.config import ApiFootballConfig


def test_api_football_client_sends_authenticated_get_request():
    config = ApiFootballConfig(api_key="test-key")
    session = Mock()

    response = Mock()
    response.json.return_value = {"response": []}
    response.raise_for_status.return_value = None
    session.get.return_value = response

    client = ApiFootballClient(
        config=config,
        session=session,
    )

    result = client.get("/status")

    session.get.assert_called_once_with(
        "https://v3.football.api-sports.io/status",
        headers={"x-apisports-key": "test-key"},
        params=None,
        timeout=10.0,
    )
    assert result == {"response": []}


def test_api_football_client_propagates_timeout():
    config = ApiFootballConfig(api_key="test-key")
    session = Mock()
    session.get.side_effect = requests.Timeout("timeout")

    client = ApiFootballClient(
        config=config,
        session=session,
    )

    with pytest.raises(requests.Timeout):
        client.get("/status")


def test_api_football_client_propagates_http_error():
    config = ApiFootballConfig(api_key="test-key")
    session = Mock()

    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError(
        "API error"
    )
    session.get.return_value = response

    client = ApiFootballClient(
        config=config,
        session=session,
    )

    with pytest.raises(requests.HTTPError):
        client.get("/status")


def test_api_football_client_exposes_rate_limit_headers():
    config = ApiFootballConfig(api_key="test-key")
    session = Mock()

    response = Mock()
    response.json.return_value = {"response": []}
    response.raise_for_status.return_value = None
    response.headers = {
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": "99",
        "X-RateLimit-Limit": "10",
        "X-RateLimit-Remaining": "9",
    }
    session.get.return_value = response

    client = ApiFootballClient(
        config=config,
        session=session,
    )

    client.get("/status")

    assert client.daily_limit == 100
    assert client.daily_remaining == 99
    assert client.minute_limit == 10
    assert client.minute_remaining == 9


def test_api_football_client_tolerates_missing_or_invalid_rate_limit_headers():
    config = ApiFootballConfig(api_key="test-key")
    session = Mock()

    response = Mock()
    response.json.return_value = {"response": []}
    response.raise_for_status.return_value = None
    response.headers = {
        "x-ratelimit-requests-limit": "invalid",
        "X-RateLimit-Remaining": None,
    }
    session.get.return_value = response

    client = ApiFootballClient(
        config=config,
        session=session,
    )

    result = client.get("/status")

    assert result == {"response": []}
    assert client.daily_limit is None
    assert client.daily_remaining is None
    assert client.minute_limit is None
    assert client.minute_remaining is None
