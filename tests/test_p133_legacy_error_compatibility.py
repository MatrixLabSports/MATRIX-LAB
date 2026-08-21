
import pytest

from app.providers.api_football.fixture_service import (
    get_fixture_records_by_date,
)
from app.providers.api_football.odds_service import (
    get_fixture_odds_raw,
)
from app.providers.api_football.response_validation import (
    ApiFootballProviderResponseError,
    validate_api_football_response_envelope,
)


class _Client:
    def __init__(self, payload):
        self.payload = payload

    def get(self, *args, **kwargs):
        return self.payload


def test_fixture_service_preserves_legacy_malformed_response_message():
    client = _Client(
        {
            "response": {},
        }
    )

    with pytest.raises(
        ValueError,
        match=(
            "respuesta de fixtures de API-Football inválida"
        ),
    ):
        get_fixture_records_by_date(
            client,
            "2026-08-21",
        )


def test_odds_service_preserves_legacy_malformed_response_message():
    client = _Client(
        {
            "response": {},
        }
    )

    with pytest.raises(
        ValueError,
        match=(
            "respuesta de odds de API-Football inválida"
        ),
    ):
        get_fixture_odds_raw(
            client,
            123,
        )


def test_provider_declared_error_still_exposes_canonical_taxonomy():
    with pytest.raises(
        ApiFootballProviderResponseError,
        match=(
            "API_FOOTBALL_PROVIDER_ERROR_PRESENT"
        ),
    ):
        validate_api_football_response_envelope(
            {
                "response": [],
                "errors": {
                    "provider": "blocked",
                },
            },
            endpoint="/fixtures",
        )
