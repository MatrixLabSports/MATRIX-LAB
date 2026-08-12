import pytest

from app.sports.tennis.match_factory import TennisMatchFactory
from app.sports.tennis.match_model import TennisMatchModel


def test_factory_builds_tennis_match_model_from_valid_data():
    data = {
        "player1": "Carlos Alcaraz",
        "player2": "Jannik Sinner",
        "tournament": "US Open",
        "surface": "Hard",
        "tour": "ATP",
        "round": "R32",
        "datetime": "2026-08-07T19:00:00Z",
        "status": "scheduled",
    }

    match = TennisMatchFactory.from_dict(data)

    assert isinstance(match, TennisMatchModel)
    assert match.contract.player1 == "Carlos Alcaraz"
    assert match.contract.player2 == "Jannik Sinner"
    assert match.contract.tournament == "US Open"
    assert match.contract.surface == "Hard"
    assert match.tour == "ATP"
    assert match.round == "R32"
    assert match.datetime == "2026-08-07T19:00:00Z"
    assert match.status == "scheduled"


def test_factory_rejects_equal_players():
    data = {
        "player1": "Carlos Alcaraz",
        "player2": "Carlos Alcaraz",
        "tournament": "US Open",
        "surface": "Hard",
        "tour": "ATP",
        "round": "R32",
        "datetime": "2026-08-07T19:00:00Z",
        "status": "scheduled",
    }

    with pytest.raises(ValueError):
        TennisMatchFactory.from_dict(data)

def test_factory_rejects_missing_required_field():
    data = {
        "player1": "Carlos Alcaraz",
        "player2": "Jannik Sinner",
        "tournament": "US Open",
        "surface": "Hard",
        "tour": "ATP",
        "round": "R32",
        "datetime": "2026-08-07T19:00:00Z",
    }

    with pytest.raises(KeyError):
        TennisMatchFactory.from_dict(data)