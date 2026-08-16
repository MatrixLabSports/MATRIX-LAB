import pytest

from app.providers.api_football.fixture_adapter import (
    adapt_api_football_fixture,
)


def test_api_football_fixture_adapter_builds_canonical_match():
    raw_fixture = {
        "fixture": {
            "date": "2026-08-16T00:00:00+00:00",
            "status": {
                "short": "FT",
            },
        },
        "league": {
            "name": "Serie A",
            "country": "Brazil",
            "season": 2026,
            "round": "Regular Season - 23",
        },
        "teams": {
            "home": {
                "name": "Sao Paulo",
            },
            "away": {
                "name": "Coritiba",
            },
        },
    }

    match = adapt_api_football_fixture(raw_fixture)

    assert match.contract.home_team == "Sao Paulo"
    assert match.contract.away_team == "Coritiba"
    assert match.contract.competition == "Serie A"
    assert match.contract.country == "Brazil"
    assert match.season == 2026
    assert match.round == "Regular Season - 23"
    assert match.datetime == "2026-08-16T00:00:00+00:00"
    assert match.status == "finished"

def test_api_football_fixture_adapter_rejects_unknown_status():
    raw_fixture = {
        "fixture": {
            "date": "2026-08-16T00:00:00+00:00",
            "status": {
                "short": "XYZ",
            },
        },
        "league": {
            "name": "Serie A",
            "country": "Brazil",
            "season": 2026,
            "round": "Regular Season - 23",
        },
        "teams": {
            "home": {
                "name": "Sao Paulo",
            },
            "away": {
                "name": "Coritiba",
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="status de API-Football no soportado: XYZ",
    ):
        adapt_api_football_fixture(raw_fixture)