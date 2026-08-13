from app.analysis.score_engine import MatrixScoreEngine


def test_score_engine_classifies_a_plus():
    engine = MatrixScoreEngine()

    result = engine.calculate_score(
        data_quality=100,
        recent_form=100,
        surface_performance=100,
        market_value=100,
        risk_control=100,
    )

    assert result.total_score == 100.0
    assert result.level == "A+"
    assert result.confidence == "MUY ALTA"


def test_score_engine_classifies_a():
    engine = MatrixScoreEngine()

    result = engine.calculate_score(
        data_quality=80,
        recent_form=80,
        surface_performance=80,
        market_value=80,
        risk_control=80,
    )

    assert result.total_score == 80.0
    assert result.level == "A"
    assert result.confidence == "ALTA"


def test_score_engine_classifies_b():
    engine = MatrixScoreEngine()

    result = engine.calculate_score(
        data_quality=70,
        recent_form=70,
        surface_performance=70,
        market_value=70,
        risk_control=70,
    )

    assert result.total_score == 70.0
    assert result.level == "B"
    assert result.confidence == "MEDIA"


def test_score_engine_classifies_c():
    engine = MatrixScoreEngine()

    result = engine.calculate_score(
        data_quality=60,
        recent_form=60,
        surface_performance=60,
        market_value=60,
        risk_control=60,
    )

    assert result.total_score == 60.0
    assert result.level == "C"
    assert result.confidence == "BAJA"


def test_score_engine_classifies_d():
    engine = MatrixScoreEngine()

    result = engine.calculate_score(
        data_quality=59,
        recent_form=59,
        surface_performance=59,
        market_value=59,
        risk_control=59,
    )

    assert result.total_score == 59.0
    assert result.level == "D"
    assert result.confidence == "NO APROBADA"

def test_score_result_exposes_score_band_label():
    engine = MatrixScoreEngine()

    result = engine.calculate_score(
        data_quality=80,
        recent_form=80,
        surface_performance=80,
        market_value=80,
        risk_control=80,
    )

    assert result.score_band_label == "ALTA"