from typing import Any

from app.providers.api_football.fixture_adapter import (
    adapt_api_football_fixture,
    adapt_api_football_identity,
)
from app.sports.football.match_model import FootballMatchModel
from app.sports.football.match_record import FootballMatchRecord
from dataclasses import dataclass


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

    raw_fixtures = payload.get("response", [])

    if not isinstance(raw_fixtures, list):
        raise ValueError(
            "respuesta de fixtures de API-Football inválida"
        )

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

    raw_fixtures = payload.get("response", [])

    if not isinstance(raw_fixtures, list):
        raise ValueError(
            "respuesta de fixtures de API-Football inválida"
        )

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

    raw_fixtures = payload.get("response", [])

    if not isinstance(raw_fixtures, list):
        raise ValueError(
            "respuesta de fixtures de API-Football inválida"
        )

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
