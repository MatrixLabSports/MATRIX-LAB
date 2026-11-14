from tools.matrix_independent_over25_governed_binding import bind


def test_governed_score_binding_never_authorizes_signal():
    discovery = {"schema": "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
                 "status": "DISCOVERY_ONLY_NO_GOVERNED_PROBABILITY_OR_QUOTES", "fixtures": [
        {"home": "A", "away": "B", "kickoff_utc": "2026-11-01T20:00:00+00:00"}
    ]}
    scores = {"schema": "MATRIX_GOVERNED_OVER25_SCORE_EXPORT_V1", "rows": [
        {"home": "A", "away": "B", "kickoff_utc": "2026-11-01T20:00:00+00:00",
         "market": "OVER_2_5", "p_matrix": 0.64,
         "governance_status": "FROZEN_GOVERNED_MARKET_SCOPED_SIGNAL_ONLY",
         "fixture_binding_verified": True, "source_freeze_verified": True,
         "engine_id": "calibrated_log_pool_v1_over_2_5",
         "frozen_parameters": {"a": 0.6, "b": 0.0, "c": 0.4},
         "odds_used_to_generate_probability": False, "target_outcome_used": False,
         "model_evidence_path": "evidence/model/real.json"}
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
    discovery = {"schema": "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
                 "status": "DISCOVERY_ONLY_NO_GOVERNED_PROBABILITY_OR_QUOTES", "fixtures": [
        {"home": "A", "away": "B", "kickoff_utc": "2026-11-01T20:00:00+00:00"}
    ]}
    scores = {"schema": "MATRIX_GOVERNED_OVER25_SCORE_EXPORT_V1", "rows": []}
    result = bind(discovery, scores, {})
    assert result["rows"] == []
    assert result["rejected"][0]["reason"] == "MARKET_PROMOTION_INVALID"


def test_rejects_unverified_freeze_and_parameter_change():
    discovery = {"schema": "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
                 "status": "DISCOVERY_ONLY_NO_GOVERNED_PROBABILITY_OR_QUOTES", "fixtures": [
        {"home": "A", "away": "B", "kickoff_utc": "2026-11-01T20:00:00+00:00"}]}
    score = {"home": "A", "away": "B", "kickoff_utc": "2026-11-01T20:00:00+00:00",
             "market": "OVER_2_5", "p_matrix": 0.64,
             "governance_status": "FROZEN_GOVERNED_MARKET_SCOPED_SIGNAL_ONLY",
             "engine_id": "calibrated_log_pool_v1_over_2_5",
             "frozen_parameters": {"a": 0.6, "b": 0.0, "c": 0.4},
             "fixture_binding_verified": True, "source_freeze_verified": False,
             "odds_used_to_generate_probability": False, "target_outcome_used": False,
             "model_evidence_path": "evidence/model/real.json"}
    promotion = {"market": "OVER_2_5", "promotion_status": "PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY",
                 "engine_executable_for_p_matrix": True,
                 "promotion_scope": "MARKET_SCOPED_SIGNAL_GENERATION_NOT_REAL_MONEY",
                 "protections": {"real_money": "BLOCKED", "automatic_wagering": False}}
    result = bind(discovery, {"schema": "MATRIX_GOVERNED_OVER25_SCORE_EXPORT_V1", "rows": [score]}, promotion)
    assert result["rows"] == []
    assert result["rejected"][0]["reason"] == "FIXTURE_BINDING_UNVERIFIED"
    score["source_freeze_verified"] = True
    score["frozen_parameters"]["a"] = 0.7
    result = bind(discovery, {"schema": "MATRIX_GOVERNED_OVER25_SCORE_EXPORT_V1", "rows": [score]}, promotion)
    assert result["rows"] == []
    assert result["rejected"][0]["reason"] == "FROZEN_PARAMETERS_MISMATCH"
