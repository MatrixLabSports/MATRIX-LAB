import pytest

from app.core.engine_registry import EngineRegistry
from app.core.interfaces.sport_engine import SportEngine


class FakeTennisEngine(SportEngine):
    @property
    def sport_code(self) -> str:
        return "TENNIS"

    def validate_match(self, match) -> bool:
        return True

    def process_match(self, match):
        return match


def test_register_and_get_engine():
    registry = EngineRegistry()
    engine = FakeTennisEngine()

    registry.register(engine)

    assert registry.get("TENNIS") is engine


def test_sport_code_is_normalized():
    registry = EngineRegistry()
    engine = FakeTennisEngine()

    registry.register(engine)

    assert registry.get(" tennis ") is engine


def test_unknown_engine_is_rejected():
    registry = EngineRegistry()

    with pytest.raises(ValueError):
        registry.get("FOOTBALL")


def test_duplicate_engine_registration_is_rejected():
    registry = EngineRegistry()
    engine = FakeTennisEngine()

    registry.register(engine)

    with pytest.raises(ValueError):
        registry.register(engine)