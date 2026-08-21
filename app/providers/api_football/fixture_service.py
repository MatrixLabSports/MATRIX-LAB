from typing import Any

from app.providers.api_football.fixture_adapter import (
    adapt_api_football_fixture,
    adapt_api_football_identity,
)
from app.sports.football.match_model import FootballMatchModel
from app.sports.football.match_record import FootballMatchRecord
from dataclasses import dataclass
from app.providers.api_football.response_validation import (
    ApiFootballProviderResponseError,
    validate_api_football_response_envelope,
)


@dataclass(frozen=True)
class FixtureIngestionResult:
    records: list[FootballMatchRecord]
    received_count: int
    accepted_count: int
    rejected_count: int


def get_fixtures_by_date(
    client: Any,
    date: str,
) -> list[FootballMatchModel]:
    payload = client.get(
        "/fixtures",
        {"date": date},
    )

    try:
        envelope = validate_api_football_response_envelope(
            payload,
            endpoint="/fixtures",
        )
    except ApiFootballProviderResponseError as error:
        if error.code == "API_FOOTBALL_RESPONSE_FIELD_INVALID":
            raise ValueError("respuesta de fixtures de API-Football inv\u00e1lida") from error
        raise
    raw_fixtures = list(envelope.response)

    return [
        adapt_api_football_fixture(raw_fixture)
        for raw_fixture in raw_fixtures
    ]


def get_fixture_records_by_date(
    client: Any,
    date: str,
) -> list[FootballMatchRecord]:
    payload = client.get(
        "/fixtures",
        {"date": date},
    )

    try:
        envelope = validate_api_football_response_envelope(
            payload,
            endpoint="/fixtures",
        )
    except ApiFootballProviderResponseError as error:
        if error.code == "API_FOOTBALL_RESPONSE_FIELD_INVALID":
            raise ValueError("respuesta de fixtures de API-Football inv\u00e1lida") from error
        raise
    raw_fixtures = list(envelope.response)

    return [
        FootballMatchRecord(
            identity=adapt_api_football_identity(raw_fixture),
            match=adapt_api_football_fixture(raw_fixture),
        )
        for raw_fixture in raw_fixtures
    ]


def get_fixture_ingestion_by_date(
    client: Any,
    date: str,
) -> FixtureIngestionResult:
    payload = client.get(
        "/fixtures",
        {"date": date},
    )

    try:
        envelope = validate_api_football_response_envelope(
            payload,
            endpoint="/fixtures",
        )
    except ApiFootballProviderResponseError as error:
        if error.code == "API_FOOTBALL_RESPONSE_FIELD_INVALID":
            raise ValueError("respuesta de fixtures de API-Football inv\u00e1lida") from error
        raise
    raw_fixtures = list(envelope.response)

    records: list[FootballMatchRecord] = []
    rejected_count = 0

    for raw_fixture in raw_fixtures:
        try:
            record = FootballMatchRecord(
                identity=adapt_api_football_identity(raw_fixture),
                match=adapt_api_football_fixture(raw_fixture),
            )
        except ValueError:
            rejected_count += 1
            continue

        records.append(record)

    return FixtureIngestionResult(
        records=records,
        received_count=len(raw_fixtures),
        accepted_count=len(records),
        rejected_count=rejected_count,
    )
