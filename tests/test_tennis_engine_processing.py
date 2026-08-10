from app.sports.tennis.contract import TennisMatchContract
from app.sports.tennis.engine import TennisEngine
from app.sports.tennis.match_model import TennisMatchModel
from app.sports.tennis.processing_result import TennisProcessingResult
from app.sports.tennis.data_coverage import TennisDataCoverage
from app.sports.tennis.coverage_policy import TennisCoveragePolicy

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

def test_tennis_engine_invalid_analysis_has_zero_confidence():
    engine = TennisEngine()

    result = engine.analyze_match(None)

    assert isinstance(result, TennisProcessingResult)
    assert result.accepted is False
    assert result.reason == "invalid_match"
    assert result.confidence == 0.0

def test_tennis_engine_valid_analysis_uses_data_confidence():
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

    coverage = TennisDataCoverage(
    recent_form=True,
    surface_history=True,
    serve_stats=True,
    return_stats=False,
    fatigue_context=False,
    market_data=False,
)

    result = engine.analyze_match(
        match,
        coverage=coverage,
    )

    assert result.accepted is True
    assert result.reason == "valid_match"
    assert result.confidence == 0.5

def test_tennis_engine_calculates_confidence_from_data_coverage():
    engine = TennisEngine()

    coverage = TennisDataCoverage(
        recent_form=True,
        surface_history=True,
        serve_stats=True,
        return_stats=False,
        fatigue_context=False,
        market_data=False,
    )

    confidence = engine.calculate_data_confidence(coverage)

    assert confidence == 0.5

def test_tennis_engine_valid_analysis_without_coverage_has_zero_confidence():
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

    assert result.accepted is True
    assert result.reason == "valid_match"
    assert result.confidence == 0.0

def test_tennis_engine_rejects_analysis_below_coverage_policy():
    engine = TennisEngine()
    policy = TennisCoveragePolicy(minimum_score=0.5)

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

    coverage = TennisDataCoverage(
        recent_form=True,
        surface_history=True,
        serve_stats=False,
        return_stats=False,
        fatigue_context=False,
        market_data=False,
    )

    result = engine.analyze_match(
        match,
        coverage=coverage,
        policy=policy,
    )

    assert result.accepted is False
    assert result.reason == "insufficient_data_coverage"
    assert result.confidence == 0.0

def test_tennis_engine_accepts_analysis_at_coverage_threshold():
    engine = TennisEngine()
    policy = TennisCoveragePolicy(minimum_score=0.5)

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

    coverage = TennisDataCoverage(
        recent_form=True,
        surface_history=True,
        serve_stats=True,
        return_stats=False,
        fatigue_context=False,
        market_data=False,
    )

    result = engine.analyze_match(
        match,
        coverage=coverage,
        policy=policy,
    )

    assert result.accepted is True
    assert result.reason == "valid_match"
    assert result.confidence == 0.5

def test_tennis_engine_rejects_analysis_when_policy_requires_missing_coverage():
    engine = TennisEngine()
    policy = TennisCoveragePolicy(minimum_score=0.5)

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

    result = engine.analyze_match(
        match,
        policy=policy,
    )

    assert result.accepted is False
    assert result.reason == "insufficient_data_coverage"
    assert result.confidence == 0.0