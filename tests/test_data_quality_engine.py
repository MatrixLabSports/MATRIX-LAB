from app.data.data_quality_engine import (
    MatrixDataQualityEngine,
)

def test_valid_match():
    """
    Verifica que un partido válido sea aprobado.
    """

    engine = MatrixDataQualityEngine()

    match = {
        "player1": "Carlos Alcaraz",
        "player2": "Jannik Sinner",
        "tournament": "US Open",
        "tour": "ATP",
        "surface": "Hard",
        "round": "R32",
        "datetime": "2026-08-06",
        "status": "scheduled",
    }

    result = engine.validate_match(match)

    assert result.passed is True
    assert result.status == "APROBADO"
    assert result.score == 8


def test_same_players_are_blocked():
    """
    Verifica que un partido con jugadores iguales sea bloqueado.
    """

    engine = MatrixDataQualityEngine()

    match = {
        "player1": "Carlos Alcaraz",
        "player2": "Carlos Alcaraz",
        "tournament": "US Open",
        "tour": "ATP",
        "surface": "Hard",
        "round": "R32",
        "datetime": "2026-08-06",
        "status": "scheduled",
    }

    result = engine.validate_match(match)

    assert result.passed is False
    assert result.status == "BLOQUEADO"
    assert any(
        "no pueden ser iguales" in mensaje
        for mensaje in result.messages
    )

def test_missing_required_fields_are_blocked():
    """
    Verifica que un partido con varios campos faltantes sea bloqueado.
    """

    engine = MatrixDataQualityEngine()

    match = {
        "player1": "Carlos Alcaraz",
        "player2": "Jannik Sinner",
        "tournament": "US Open",
    }

    result = engine.validate_match(match)

    assert result.passed is False
    assert result.status == "BLOQUEADO"
    assert result.score == 3
    assert any(
        "Falta el campo: surface" in mensaje
        for mensaje in result.messages
    )

def test_short_player_name_is_blocked():
    """
    Verifica que un nombre de jugador demasiado corto sea bloqueado.
    """

    engine = MatrixDataQualityEngine()

    match = {
        "player1": "A",
        "player2": "Jannik Sinner",
        "tournament": "US Open",
        "tour": "ATP",
        "surface": "Hard",
        "round": "R32",
        "datetime": "2026-08-06",
        "status": "scheduled",
    }

    result = engine.validate_match(match)

    assert result.passed is False
    assert result.status == "BLOQUEADO"
    assert any(
        "player1 debe contener al menos 2 caracteres" in mensaje
        for mensaje in result.messages
    )