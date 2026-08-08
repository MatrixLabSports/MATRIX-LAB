from app.sports.tennis.contract import TennisMatchContract
from app.sports.tennis.engine import TennisEngine
from app.sports.tennis.match_model import TennisMatchModel
from app.sports.tennis.processing_result import TennisProcessingResult

def test_tennis_engine_returns_processing_result():
    engine = TennisEngine()

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

    result = engine.analyze_match(match)

    assert isinstance(result, TennisProcessingResult)
    assert result.accepted is True
    assert result.reason == "valid_match"

def test_tennis_engine_processes_valid_match():
    engine = TennisEngine()

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

    result = engine.process_match(match)

    assert result is match


def test_tennis_engine_does_not_process_invalid_match():
    engine = TennisEngine()

    try:
        engine.process_match(None)
        processed = True
    except (ValueError, TypeError):
        processed = False

    assert processed is False