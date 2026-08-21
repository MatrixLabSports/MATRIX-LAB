import pytest

from app.core.pinned_https_transport import (
    PinnedHttpProtocolError,
    PinnedHttpResponse,
    PinnedHttpStatusError,
)
from app.providers.api_football.response_validation import (
    ApiFootballProviderResponseError,
    request_and_validate_api_football_response,
    validate_api_football_response_envelope,
)


class _Client:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def get(self, *args, **kwargs):
        if self.error is not None:
            raise self.error
        return self.result


def test_strict_pinned_response_requires_json_content_type():
    response = PinnedHttpResponse(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body=b"{}",
        strict_protocol=True,
    )
    with pytest.raises(
        PinnedHttpProtocolError,
        match="PINNED_HTTP_CONTENT_TYPE_INVALID",
    ):
        response.json()


def test_strict_pinned_response_rejects_invalid_json():
    response = PinnedHttpResponse(
        status_code=200,
        headers={"Content-Type": "application/json; charset=utf-8"},
        body=b"{",
        strict_protocol=True,
    )
    with pytest.raises(
        PinnedHttpProtocolError,
        match="PINNED_HTTP_JSON_INVALID",
    ):
        response.json()


def test_strict_pinned_response_rejects_http_error_before_json():
    response = PinnedHttpResponse(
        status_code=500,
        headers={"Content-Type": "application/json"},
        body=b"{}",
        strict_protocol=True,
    )
    with pytest.raises(PinnedHttpStatusError, match="HTTP_STATUS_500"):
        response.json()


def test_envelope_rejects_primitive_response_item():
    with pytest.raises(ApiFootballProviderResponseError) as captured:
        validate_api_football_response_envelope(
            {"response": [7]},
            endpoint="/fixtures",
        )

    assert captured.value.code == "API_FOOTBALL_RESPONSE_ITEM_NOT_MAPPING"
    assert captured.value.category == "SCHEMA"


def test_protocol_error_maps_to_canonical_provider_taxonomy():
    client = _Client(
        error=PinnedHttpProtocolError(
            "PINNED_HTTP_JSON_INVALID",
            "JSON_DECODE",
        )
    )
    with pytest.raises(ApiFootballProviderResponseError) as captured:
        request_and_validate_api_football_response(
            client,
            endpoint="/fixtures",
            params={"date": "2026-08-21"},
        )

    assert captured.value.category == "JSON_DECODE"
    assert captured.value.code == "API_FOOTBALL_JSON_DECODE_ERROR"


def test_provider_error_taxonomy_does_not_echo_raw_error():
    secret = "provider-raw-secret-detail"
    client = _Client(
        result={
            "response": [],
            "errors": {"detail": secret},
        }
    )
    with pytest.raises(ApiFootballProviderResponseError) as captured:
        request_and_validate_api_football_response(
            client,
            endpoint="/fixtures",
            params={"date": "2026-08-21"},
        )

    assert secret not in str(captured.value)
