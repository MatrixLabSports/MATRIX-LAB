from app.core.pipeline_engine import MatrixPipelineEngine
from app.core.engine_registry import EngineRegistry
from app.core.interfaces.sport_engine import SportEngine
from app.sports.tennis.engine import TennisEngine

def test_pipeline_valid_match():
    """
    Verifica que el Pipeline procese correctamente un partido válido.
    """

    pipeline = MatrixPipelineEngine()

    match = {
        "sport": "TENNIS",
        "player1": "Carlos Alcaraz",
        "player2": "Jannik Sinner",
        "tournament": "US Open",
        "tour": "ATP",
        "surface": "Hard",
        "round": "R32",
        "datetime": "2026-08-06",
        "status": "scheduled",
    }

    result = pipeline.process_match(match)

    assert result.passed is True
    assert result.status == "APROBADO"
    assert result.data is not None
    assert result.sport is not None
    assert result.sport.code == "TENNIS"

def test_pipeline_blocks_invalid_match_before_engine_processing():
    pipeline = MatrixPipelineEngine()

    match = {
        "sport": "TENNIS",
        "player1": "Carlos Alcaraz",
        "player2": "Carlos Alcaraz",
        "tournament": "US Open",
        "tour": "ATP",
        "surface": "Hard",
        "round": "R32",
        "datetime": "2026-08-06",
        "status": "scheduled",
    }

    result = pipeline.process_match(match)

    assert result.passed is False
    assert result.stage == "DATA_QUALITY"
    assert result.status == "BLOQUEADO"
    assert result.data is not None

    from app.core.engine_registry import EngineRegistry
from app.core.interfaces.sport_engine import SportEngine


class FakePipelineTennisEngine(SportEngine):
    def __init__(self):
        self.processed_match = None

    @property
    def sport_code(self) -> str:
        return "TENNIS"

    def validate_match(self, match) -> bool:
        return True

    def process_match(self, match):
        self.processed_match = match
        return match


def test_pipeline_uses_registered_engine_after_data_quality():
    registry = EngineRegistry()
    engine = FakePipelineTennisEngine()
    registry.register(engine)

    pipeline = MatrixPipelineEngine(engine_registry=registry)

    match = {
        "sport": "TENNIS",
        "player1": "Carlos Alcaraz",
        "player2": "Jannik Sinner",
        "tournament": "US Open",
        "tour": "ATP",
        "surface": "Hard",
        "round": "R32",
        "datetime": "2026-08-06",
        "status": "scheduled",
    }

    result = pipeline.process_match(match)

    assert result.passed is True
    assert engine.processed_match is not None

    from app.sports.tennis.engine import TennisEngine


def test_pipeline_with_real_tennis_engine_requires_model_conversion():
    registry = EngineRegistry()
    registry.register(TennisEngine())

    pipeline = MatrixPipelineEngine(engine_registry=registry)

    match = {
        "sport": "TENNIS",
        "player1": "Carlos Alcaraz",
        "player2": "Jannik Sinner",
        "tournament": "US Open",
        "tour": "ATP",
        "surface": "Hard",
        "round": "R32",
        "datetime": "2026-08-06",
        "status": "scheduled",
    }

    pipeline.process_match(match)

class FakePipelineFootballEngine(SportEngine):
    def __init__(self):
        self.processed_match = None

    @property
    def sport_code(self) -> str:
        return "FOOTBALL"

    def validate_match(self, match) -> bool:
        return True

    def process_match(self, match):
        self.processed_match = match
        return match


def test_pipeline_core_does_not_require_tennis_fields_for_football():
    registry = EngineRegistry()
    engine = FakePipelineFootballEngine()
    registry.register(engine)

    pipeline = MatrixPipelineEngine(engine_registry=registry)

    match = {
        "sport": "FOOTBALL",
        "home_team": "Team A",
        "away_team": "Team B",
        "competition": "Test League",
        "datetime": "2026-08-12T20:00:00Z",
        "status": "scheduled",
    }

    result = pipeline.process_match(match)

    assert result.passed is True
    assert result.sport is not None
    assert result.sport.code == "FOOTBALL"
    assert engine.processed_match is match