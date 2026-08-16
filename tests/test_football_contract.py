import pytest

from app.sports.football.contract import FootballMatchContract


def test_football_match_contract_can_be_created():
    contract = FootballMatchContract(
        home_team="Millonarios",
        away_team="Atlético Nacional",
        competition="Liga BetPlay",
        country="Colombia",
    )

    assert contract.home_team == "Millonarios"
    assert contract.away_team == "Atlético Nacional"
    assert contract.competition == "Liga BetPlay"
    assert contract.country == "Colombia"


def test_football_match_contract_rejects_same_team():
    with pytest.raises(
        ValueError,
        match="home_team y away_team no pueden ser iguales",
    ):
        FootballMatchContract(
            home_team="Millonarios",
            away_team="Millonarios",
            competition="Liga BetPlay",
            country="Colombia",
        )


def test_football_match_contract_rejects_empty_required_fields():
    with pytest.raises(ValueError):
        FootballMatchContract(
            home_team="",
            away_team="Atlético Nacional",
            competition="Liga BetPlay",
            country="Colombia",
        )


def test_football_match_contract_rejects_whitespace_only_fields():
    with pytest.raises(ValueError):
        FootballMatchContract(
            home_team="   ",
            away_team="Atlético Nacional",
            competition="Liga BetPlay",
            country="Colombia",
        )