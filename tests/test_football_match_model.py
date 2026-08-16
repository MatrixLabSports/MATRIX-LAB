import pytest

from app.sports.football.contract import FootballMatchContract
from app.sports.football.match_model import FootballMatchModel


def test_football_match_model_can_be_created():
    contract = FootballMatchContract(
        home_team="Millonarios",
        away_team="Atlético Nacional",
        competition="Liga BetPlay",
        country="Colombia",
    )

    match = FootballMatchModel(
        contract=contract,
        season=2026,
        round="Clausura - 8",
        datetime="2026-08-16T20:00:00-05:00",
        status="scheduled",
    )

    assert match.contract is contract
    assert match.season == 2026
    assert match.round == "Clausura - 8"
    assert match.datetime == "2026-08-16T20:00:00-05:00"
    assert match.status == "scheduled"


def test_football_match_model_rejects_invalid_status():
    contract = FootballMatchContract(
        home_team="Millonarios",
        away_team="Atlético Nacional",
        competition="Liga BetPlay",
        country="Colombia",
    )

    with pytest.raises(
        ValueError,
        match="status no permitido para un partido de fútbol",
    ):
        FootballMatchModel(
            contract=contract,
            season=2026,
            round="Clausura - 8",
            datetime="2026-08-16T20:00:00-05:00",
            status="unknown",
        )


def test_football_match_model_rejects_invalid_season():
    contract = FootballMatchContract(
        home_team="Millonarios",
        away_team="Atlético Nacional",
        competition="Liga BetPlay",
        country="Colombia",
    )

    with pytest.raises(
        ValueError,
        match="season debe ser un entero positivo",
    ):
        FootballMatchModel(
            contract=contract,
            season=0,
            round="Clausura - 8",
            datetime="2026-08-16T20:00:00-05:00",
            status="scheduled",
        )

def test_football_match_model_rejects_empty_round():
    contract = FootballMatchContract(
        home_team="Millonarios",
        away_team="Atlético Nacional",
        competition="Liga BetPlay",
        country="Colombia",
    )

    with pytest.raises(
        ValueError,
        match="round no puede estar vacío",
    ):
        FootballMatchModel(
            contract=contract,
            season=2026,
            round="   ",
            datetime="2026-08-16T20:00:00-05:00",
            status="scheduled",
        )


def test_football_match_model_rejects_empty_datetime():
    contract = FootballMatchContract(
        home_team="Millonarios",
        away_team="Atlético Nacional",
        competition="Liga BetPlay",
        country="Colombia",
    )

    with pytest.raises(
        ValueError,
        match="datetime no puede estar vacío",
    ):
        FootballMatchModel(
            contract=contract,
            season=2026,
            round="Clausura - 8",
            datetime="   ",
            status="scheduled",
        )
