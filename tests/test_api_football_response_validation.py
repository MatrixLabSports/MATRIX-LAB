from dataclasses import replace

import pytest

from app.providers.api_football.response_validation import (
    ApiFootballProviderResponseError,
    validate_api_football_response_envelope,
)


def test_response_validator_accepts_minimal_fixture_envelope():
    envelope = validate_api_football_response_envelope(
        {
            "response": [],
        },
        endpoint="/fixtures",
    )

    assert envelope.endpoint == "/fixtures"
    assert envelope.response == ()
    assert len(envelope.payload_fingerprint) == 64


def test_response_validator_accepts_canonical_provider_metadata():
    envelope = validate_api_football_response_envelope(
        {
            "get": "fixtures",
            "parameters": {"date": "2026-08-21"},
            "errors": [],
            "results": 0,
            "paging": {
                "current": 1,
                "total": 1,
            },
            "response": [],
        },
        endpoint="/fixtures",
    )

    assert envelope.request_name == "fixtures"
    assert envelope.results == 0
    assert envelope.paging_current == 1
    assert envelope.paging_total == 1


@pytest.mark.parametrize(
    ("payload", "code"),
    (
        (
            [],
            "API_FOOTBALL_RESPONSE_NOT_MAPPING",
        ),
        (
            {},
            "API_FOOTBALL_RESPONSE_FIELD_REQUIRED",
        ),
        (
            {"response": {}},
            "API_FOOTBALL_RESPONSE_FIELD_INVALID",
        ),
        (
            {
                "response": [],
                "errors": {
                    "limit": "exceeded",
                },
            },
            "API_FOOTBALL_PROVIDER_ERROR_PRESENT",
        ),
        (
            {
                "response": [],
                "results": 1,
            },
            "API_FOOTBALL_RESULTS_COUNT_MISMATCH",
        ),
        (
            {
                "get": "odds",
                "response": [],
            },
            "API_FOOTBALL_ENDPOINT_MISMATCH",
        ),
    ),
)
def test_response_validator_fails_closed(
    payload,
    code,
):
    with pytest.raises(
        ApiFootballProviderResponseError
    ) as captured:
        validate_api_football_response_envelope(
            payload,
            endpoint="/fixtures",
        )

    assert captured.value.code == code
    assert str(captured.value) == code


def test_provider_error_does_not_echo_raw_payload():
    secret = "do-not-persist-or-echo-this"

    with pytest.raises(
        ApiFootballProviderResponseError
    ) as captured:
        validate_api_football_response_envelope(
            {
                "response": [],
                "errors": {
                    "detail": secret,
                },
            },
            endpoint="/fixtures",
        )

    assert secret not in str(
        captured.value
    )
