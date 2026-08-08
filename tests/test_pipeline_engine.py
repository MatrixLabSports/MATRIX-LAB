from app.core.pipeline_engine import MatrixPipelineEngine


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