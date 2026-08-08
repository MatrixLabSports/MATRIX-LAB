import pytest

from app.sports.tennis.contract import TennisMatchContract


def test_valid_tennis_contract_can_be_created():
    match = TennisMatchContract(
        player1="Carlos Alcaraz",
        player2="Jannik Sinner",
        tournament="US Open",
        surface="Hard",
    )

    assert match.player1 == "Carlos Alcaraz"
    assert match.player2 == "Jannik Sinner"
    assert match.tournament == "US Open"
    assert match.surface == "Hard"

    import pytest


def test_tennis_contract_rejects_same_player():
    with pytest.raises(ValueError):
        TennisMatchContract(
        player1="Carlos Alcaraz",
        player2="Carlos Alcaraz",
        tournament="US Open",
        surface="Hard",
    )

def test_tennis_contract_rejects_empty_player():
    with pytest.raises(ValueError):
        TennisMatchContract(
        player1="   ",
        player2="Jannik Sinner",
        tournament="US Open",
        surface="Hard",
    )

def test_tennis_contract_rejects_empty_tournament():
    with pytest.raises(ValueError):
        TennisMatchContract(
        player1="Carlos Alcaraz",
        player2="Jannik Sinner",
        tournament="   ",
        surface="Hard",
    )

def test_tennis_contract_rejects_empty_surface():
    with pytest.raises(ValueError):
        TennisMatchContract(
        player1="Carlos Alcaraz",
        player2="Jannik Sinner",
        tournament="US Open",
        surface="   ",
    )