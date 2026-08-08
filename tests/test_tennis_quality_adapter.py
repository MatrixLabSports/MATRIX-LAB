from app.sports.tennis.contract import TennisMatchContract
from app.sports.tennis.match_model import TennisMatchModel
from app.sports.tennis.quality_adapter import TennisQualityAdapter


def test_tennis_quality_adapter_converts_match_model():
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

    result = TennisQualityAdapter.to_quality_data(match)

    assert result == {
        "player1": "Carlos Alcaraz",
        "player2": "Jannik Sinner",
        "surface": "Hard",
    }