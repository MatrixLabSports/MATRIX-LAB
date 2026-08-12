from app.sports.tennis.contract import TennisMatchContract
from app.sports.tennis.match_model import TennisMatchModel
import pytest


def test_tennis_match_model_can_be_created():
    contract = TennisMatchContract(
        player1="Carlos Alcaraz",
        player2="Jannik Sinner",
        tournament="US Open",
        surface="Hard",
    )

    match = TennisMatchModel(
        contract=contract,
        tour="ATP",
        round="R32",
        datetime="2026-08-07T19:00:00Z",
        status="scheduled",
    )

    assert match.contract.player1 == "Carlos Alcaraz"
    assert match.contract.player2 == "Jannik Sinner"
    assert match.contract.tournament == "US Open"
    assert match.contract.surface == "Hard"
    assert match.tour == "ATP"
    assert match.round == "R32"
    assert match.status == "scheduled"

    import pytest


def test_tennis_match_model_rejects_invalid_round():
    contract = TennisMatchContract(
        player1="Carlos Alcaraz",
        player2="Jannik Sinner",
        tournament="US Open",
        surface="Hard",
    )

    with pytest.raises(ValueError):
        TennisMatchModel(
            contract=contract,
            tour="ATP",
            round="INVALID",
            datetime="2026-08-07T19:00:00Z",
            status="scheduled",
        )