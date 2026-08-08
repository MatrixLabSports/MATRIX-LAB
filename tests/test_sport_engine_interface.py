from app.core.interfaces.sport_engine import SportEngine


def test_sport_engine_interface_exists():
    assert SportEngine is not None

def test_incomplete_sport_engine_cannot_be_instantiated():
    class IncompleteSportEngine(SportEngine):
        pass

    import pytest

    with pytest.raises(TypeError):
        IncompleteSportEngine()

def test_sport_engine_requires_sport_code():
    class MissingSportCode(SportEngine):
        def validate_match(self, match):
            return True

        def process_match(self, match):
            return match

    import pytest

    with pytest.raises(TypeError):
        MissingSportCode()


def test_sport_engine_requires_validate_match():
    class MissingValidateMatch(SportEngine):
        @property
        def sport_code(self):
            return "test"

        def process_match(self, match):
            return match

    import pytest

    with pytest.raises(TypeError):
        MissingValidateMatch()


def test_sport_engine_requires_process_match():
    class MissingProcessMatch(SportEngine):
        @property
        def sport_code(self):
            return "test"

        def validate_match(self, match):
            return True

    import pytest

    with pytest.raises(TypeError):
        MissingProcessMatch()