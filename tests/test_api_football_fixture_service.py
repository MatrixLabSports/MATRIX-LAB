from unittest.mock import Mock

import pytest

from app.providers.api_football.fixture_service import (
    get_fixture_records_by_date,
    get_fixtures_by_date,
)


def test_fixture_service_gets_and_adapts_fixtures_by_date():
    client = Mock()
    client.get.return_value = {
        "response": [
            {
                "fixture": {
                    "date": "2026-08-16T00:00:00+00:00",
                    "status": {"short": "FT"},
                },
                "league": {
                    "name": "Serie A",
                    "country": "Brazil",
                    "season": 2026,
                    "round": "Regular Season - 23",
                },
                "teams": {
                    "home": {"name": "Sao Paulo"},
                    "away": {"name": "Coritiba"},
                },
            },
            {
                "fixture": {
                    "date": "2026-08-16T19:00:00+00:00",
                    "status": {"short": "NS"},
                },
                "league": {
                    "name": "Liga Profesional",
                    "country": "Argentina",
                    "season": 2026,
                    "round": "Regular Season - 10",
                },
                "teams": {
                    "home": {"name": "River Plate"},
                    "away": {"name": "Racing Club"},
                },
            },
        ]
    }

    matches = get_fixtures_by_date(
        client,
        "2026-08-16",
    )

    client.get.assert_called_once_with(
        "/fixtures",
        {"date": "2026-08-16"},
    )

    assert len(matches) == 2

    assert matches[0].contract.home_team == "Sao Paulo"
    assert matches[0].contract.away_team == "Coritiba"
    assert matches[0].status == "finished"

    assert matches[1].contract.home_team == "River Plate"
    assert matches[1].contract.away_team == "Racing Club"
    assert matches[1].status == "scheduled"


def test_fixture_service_returns_empty_list_when_no_fixtures_exist():
    client = Mock()
    client.get.return_value = {
        "response": [],
    }

    matches = get_fixtures_by_date(
        client,
        "2026-08-16",
    )

    client.get.assert_called_once_with(
        "/fixtures",
        {"date": "2026-08-16"},
    )

    assert matches == []


def test_fixture_service_rejects_malformed_response():
    client = Mock()
    client.get.return_value = {
        "response": {},
    }

    with pytest.raises(
        ValueError,
        match="respuesta de fixtures de API-Football inválida",
    ):
        get_fixtures_by_date(
            client,
            "2026-08-16",
        )


def test_fixture_service_builds_records_with_external_identity():
    client = Mock()
    client.get.return_value = {
        "response": [
            {
                "fixture": {
                    "id": 1522161,
                    "date": "2026-08-16T04:00:00+00:00",
                    "status": {"short": "AWD"},
                },
                "league": {
                    "name": "Victoria NPL 2",
                    "country": "Australia",
                    "season": 2026,
                    "round": "Regular Season - 24",
                },
                "teams": {
                    "home": {"name": "Western United II"},
                    "away": {"name": "Langwarrin"},
                },
            },
        ]
    }

    records = get_fixture_records_by_date(
        client,
        "2026-08-16",
    )

    assert len(records) == 1

    record = records[0]

    assert record.identity.provider == "api_football"
    assert record.identity.external_id == "1522161"
    assert record.match.contract.home_team == "Western United II"
    assert record.match.contract.away_team == "Langwarrin"
    assert record.match.status == "awarded"
