import io
import json
from urllib.error import HTTPError

import pytest

from tools.cor0203_api_tennis_discovery import (
    ApiTennisDiscoveryClient,
    ApiTennisDiscoveryError,
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


class SequenceOpener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, request, timeout=20.0):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return FakeResponse(outcome)


def test_transient_network_error_retries_once_then_succeeds():
    opener = SequenceOpener([
        OSError("temporary"),
        {"success": 1, "result": []},
    ])
    sleeps = []
    client = ApiTennisDiscoveryClient(
        "k",
        opener=opener,
        retry_attempts=2,
        retry_base_delay_seconds=0.0,
        sleeper=sleeps.append,
    )
    result = client.fixture_by_match_key("123")
    assert result["success"] == 1
    assert opener.calls == 2
    assert client.request_count == 2
    assert sleeps == [0.0]


def test_nonretryable_http_400_fails_without_second_attempt():
    error = HTTPError(
        "https://api.api-tennis.com/tennis/",
        400,
        "Bad Request",
        hdrs=None,
        fp=io.BytesIO(b""),
    )
    opener = SequenceOpener([error])
    client = ApiTennisDiscoveryClient(
        "k",
        opener=opener,
        retry_attempts=2,
        sleeper=lambda _: None,
    )
    with pytest.raises(ApiTennisDiscoveryError, match="API_TENNIS_HTTP_ERROR"):
        client.fixture_by_match_key("123")
    assert opener.calls == 1
    assert client.request_count == 1


def test_transient_errors_are_bounded_and_fail_closed():
    opener = SequenceOpener([OSError("one"), OSError("two")])
    client = ApiTennisDiscoveryClient(
        "k",
        opener=opener,
        retry_attempts=2,
        retry_base_delay_seconds=0.0,
        sleeper=lambda _: None,
    )
    with pytest.raises(ApiTennisDiscoveryError, match="API_TENNIS_RETRY_EXHAUSTED"):
        client.fixture_by_match_key("123")
    assert opener.calls == 2
    assert client.request_count == 2
