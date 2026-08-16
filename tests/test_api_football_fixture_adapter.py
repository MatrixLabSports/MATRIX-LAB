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

def test_api_football_fixture_adapter_rejects_incomplete_fixture():
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
        },
    }

    with pytest.raises(
        ValueError,
        match="fixture de API-Football incompleto",
    ):
        adapt_api_football_fixture(raw_fixture)

def test_api_football_fixture_adapter_rejects_empty_team_name():
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
                "name": "   ",
            },
            "away": {
                "name": "Coritiba",
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="home_team y away_team no pueden estar vacíos",
    ):
        adapt_api_football_fixture(raw_fixture)

def test_api_football_fixture_adapter_rejects_invalid_season():
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
            "season": 0,
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
        match="season debe ser un entero positivo",
    ):
        adapt_api_football_fixture(raw_fixture)

def test_api_football_fixture_adapter_rejects_empty_datetime():
    raw_fixture = {
        "fixture": {
            "date": "   ",
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

    with pytest.raises(
        ValueError,
        match="datetime no puede estar vacío",
    ):
        adapt_api_football_fixture(raw_fixture)


def test_api_football_fixture_adapter_maps_awarded_match():
    raw_fixture = {
        "fixture": {
            "date": "2026-08-16T04:00:00+00:00",
            "status": {
                "short": "AWD",
            },
        },
        "league": {
            "name": "Victoria NPL 2",
            "country": "Australia",
            "season": 2026,
            "round": "Regular Season - 24",
        },
        "teams": {
            "home": {
                "name": "Western United II",
            },
            "away": {
                "name": "Langwarrin",
            },
        },
    }

    match = adapt_api_football_fixture(raw_fixture)

    assert match.status == "awarded"
