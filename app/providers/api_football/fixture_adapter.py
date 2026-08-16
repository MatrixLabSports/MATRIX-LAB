from typing import Any

from app.sports.football.contract import FootballMatchContract
from app.sports.football.match_model import FootballMatchModel
from app.sports.football.external_identity import ExternalMatchIdentity


STATUS_MAP = {
    "NS": "scheduled",
    "TBD": "scheduled",
    "1H": "live",
    "2H": "live",
    "ET": "live",
    "BT": "live",
    "P": "live",
    "HT": "halftime",
    "FT": "finished",
    "AET": "finished",
    "PEN": "finished",
    "PST": "postponed",
    "CANC": "cancelled",
    "ABD": "abandoned",
    "AWD": "awarded",
}


def adapt_api_football_fixture(
    raw_fixture: dict[str, Any],
) -> FootballMatchModel:
    try:
        fixture = raw_fixture["fixture"]
        league = raw_fixture["league"]
        teams = raw_fixture["teams"]

        status_short = fixture["status"]["short"]

        home_team = teams["home"]["name"]
        away_team = teams["away"]["name"]
        competition = league["name"]
        country = league["country"]
        season = league["season"]
        round_name = league["round"]
        fixture_date = fixture["date"]
    except (KeyError, TypeError) as error:
        raise ValueError(
            "fixture de API-Football incompleto"
        ) from error

    normalized_status = STATUS_MAP.get(status_short)

    if normalized_status is None:
        raise ValueError(
            f"status de API-Football no soportado: {status_short}"
        )

    contract = FootballMatchContract(
        home_team=home_team,
        away_team=away_team,
        competition=competition,
        country=country,
    )

    return FootballMatchModel(
        contract=contract,
        season=season,
        round=round_name,
        datetime=fixture_date,
        status=normalized_status,
    )


def adapt_api_football_identity(
    raw_fixture: dict[str, Any],
) -> ExternalMatchIdentity:
    try:
        fixture_id = raw_fixture["fixture"]["id"]
    except (KeyError, TypeError) as error:
        raise ValueError(
            "fixture de API-Football sin identidad externa"
        ) from error

    if fixture_id is None:
        raise ValueError(
            "fixture de API-Football sin identidad externa"
        )

    return ExternalMatchIdentity(
        provider="api_football",
        external_id=str(fixture_id),
    )
