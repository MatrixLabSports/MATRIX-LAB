import pytest
from app.sports.tennis.data_quality import TennisDataQualityEngine


def test_tennis_data_quality_engine_can_be_created():
    engine = TennisDataQualityEngine()

    assert engine is not None

def test_tennis_rejects_same_player():
    engine = TennisDataQualityEngine()

    match = {
        "player1": "Carlos Alcaraz",
        "player2": "Carlos Alcaraz",
    }

    result = engine.validate_match(match)

    assert result.passed is False

def test_tennis_rejects_invalid_surface():
    engine = TennisDataQualityEngine()

    match = {
    "player1": "Carlos Alcaraz",
    "player2": "Jannik Sinner",
    "surface": "ICE",
    }

    result = engine.validate_match(match)

    assert result.passed is False

def test_tennis_rejects_non_dictionary_match():
    engine = TennisDataQualityEngine()

    with pytest.raises(TypeError):
        engine.validate_match(None)

@pytest.mark.parametrize("field_name", ["player1", "player2"])
def test_tennis_rejects_missing_player(field_name):
    engine = TennisDataQualityEngine()
    match = {
        "player1": "Carlos Alcaraz",
        "player2": "Jannik Sinner",
    }
    del match[field_name]

    result = engine.validate_match(match)

    assert result.passed is False
    assert f"{field_name} es obligatorio." in result.messages