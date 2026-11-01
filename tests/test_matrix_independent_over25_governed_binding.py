from tools.matrix_independent_over25_governed_binding import bind


def test_governed_score_binding_never_authorizes_signal():
    discovery = {"schema": "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1", "fixtures": [
        {"home": "A", "away": "B", "kickoff_utc": "2026-11-01T20:00:00+00:00"}
    ]}
    scores = {"schema": "MATRIX_GOVERNED_OVER25_SCORE_EXPORT_V1", "rows": [
        {"home": "A", "away": "B", "kickoff_utc": "2026-11-01T20:00:00+00:00",
         "market": "OVER_2_5", "p_matrix": 0.64,
         "governance_status": "FROZEN_GOVERNED_MARKET_SCOPED_SIGNAL_ONLY",
         "fixture_binding_verified": True, "model_evidence_path": "evidence/model/real.json"}
    ]}
    promotion = {"market": "OVER_2_5", "promotion_status": "PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY",
                 "engine_executable_for_p_matrix": True,
                 "promotion_scope": "MARKET_SCOPED_SIGNAL_GENERATION_NOT_REAL_MONEY",
                 "protections": {"real_money": "BLOCKED", "automatic_wagering": False}}
    result = bind(discovery, scores, promotion)
    assert len(result["rows"]) == 1
    assert result["rows"][0]["p_matrix"] == 0.64
    assert result["rows"][0]["decimal_odds"] is None
    assert result["rows"][0]["ev"] is None
    assert result["signal_generation_authorized"] is False
    assert result["telegram_messages_sent"] == 0


def test_missing_governed_score_fails_closed():
    discovery = {"schema": "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1", "fixtures": [
        {"home": "A", "away": "B", "kickoff_utc": "2026-11-01T20:00:00+00:00"}
    ]}
    scores = {"schema": "MATRIX_GOVERNED_OVER25_SCORE_EXPORT_V1", "rows": []}
    result = bind(discovery, scores, {})
    assert result["rows"] == []
    assert result["rejected"][0]["reason"] == "MARKET_PROMOTION_INVALID"
