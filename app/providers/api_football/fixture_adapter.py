from typing import Any

from app.sports.football.contract import FootballMatchContract
from app.sports.football.match_model import FootballMatchModel


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
}


def adapt_api_football_fixture(
    raw_fixture: dict[str, Any],
) -> FootballMatchModel:
    fixture = raw_fixture["fixture"]
    league = raw_fixture["league"]
    teams = raw_fixture["teams"]

    status_short = fixture["status"]["short"]
    normalized_status = STATUS_MAP.get(status_short)

    if normalized_status is None:
        raise ValueError(
            f"status de API-Football no soportado: {status_short}"
        )

    contract = FootballMatchContract(
        home_team=teams["home"]["name"],
        away_team=teams["away"]["name"],
        competition=league["name"],
        country=league["country"],
    )

    return FootballMatchModel(
        contract=contract,
        season=league["season"],
        round=league["round"],
        datetime=fixture["date"],
        status=normalized_status,
    )