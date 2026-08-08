from app.core.interfaces.sport_engine import SportEngine
from app.sports.tennis.contract import TennisMatchContract
from app.sports.tennis.engine import TennisEngine
from app.sports.tennis.match_model import TennisMatchModel


def test_tennis_engine_implements_sport_engine():
    assert issubclass(TennisEngine, SportEngine)

def test_tennis_engine_rejects_invalid_match():
    engine = TennisEngine()

    assert engine.validate_match(None) is False


def test_tennis_engine_rejects_match_with_invalid_surface():
    engine = TennisEngine()

    contract = TennisMatchContract(
        player1="Carlos Alcaraz",
        player2="Jannik Sinner",
        tournament="US Open",
        surface="ICE",
    )

    match = TennisMatchModel(
        contract=contract,
        tour="ATP",
        round="R32",
        datetime="2026-08-07T19:00:00Z",
        status="scheduled",
    )

    assert engine.validate_match(match) is False