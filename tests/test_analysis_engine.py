from app.analysis.analysis_engine import MatchAnalysis


def test_match_analysis_preserves_legacy_confidence_field():
    analysis = MatchAnalysis(
        player1="Player A",
        player2="Player B",
        tournament="Test Tournament",
        filter_status="APROBADO",
        filter_score=7,
        matrix_score=80.0,
        risk_score=20.0,
        risk_level="BAJO",
        level="A",
        confidence="ALTA",
        decision="CANDIDATO PARA REVISIÓN",
        warnings=[],
    )

    assert analysis.confidence == "ALTA"


def test_match_analysis_current_confidence_represents_score_band_label():
    analysis = MatchAnalysis(
        player1="Player A",
        player2="Player B",
        tournament="Test Tournament",
        filter_status="APROBADO",
        filter_score=7,
        matrix_score=80.0,
        risk_score=20.0,
        risk_level="BAJO",
        level="A",
        confidence="ALTA",
        decision="CANDIDATO PARA REVISIÓN",
        warnings=[],
    )

    assert analysis.confidence == "ALTA"


def test_match_analysis_exposes_score_band_label():
    analysis = MatchAnalysis(
        player1="Player A",
        player2="Player B",
        tournament="Test Tournament",
        filter_status="APROBADO",
        filter_score=7,
        matrix_score=80.0,
        risk_score=20.0,
        risk_level="BAJO",
        level="A",
        confidence="ALTA",
        decision="CANDIDATO PARA REVISIÓN",
        warnings=[],
    )

    assert analysis.score_band_label == "ALTA"