import pytest

from app.sports.tennis.contract import TennisMatchContract
from app.sports.tennis.match_model import TennisMatchModel


def test_tennis_match_accepts_scheduled_status():
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

    assert match.status == "scheduled"


def test_tennis_match_rejects_invalid_status():
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
            round="R32",
            datetime="2026-08-07T19:00:00Z",
            status="flying",
        )

def test_tennis_match_accepts_live_status():
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
            status="live",
        )

        assert match.status == "live"