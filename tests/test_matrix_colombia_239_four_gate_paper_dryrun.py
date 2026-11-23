"""No-send integration and prospective settlement governance (real retained evidence)."""
from pathlib import Path
import json,copy
import pytest
from tools.matrix_colombia_239_four_gate_paper_dryrun import decide

R=Path("evidence/football_world_inventory")
def docs():
    files=[
      "2026-11-24/MATRIX_COLOMBIA_THREE_SOURCE_READINESS_RUN_45090559298.json",
      "2026-11-22/MATRIX_COLOMBIA_239_ORIGINAL_FORMULA_SHADOW_RUN_45089678156.json",
      "2026-11-24/MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT.json",
      "2026-11-22/MATRIX_COLOMBIA_239_FULLSEASON_GOAL_PARITY_RUN_45089678156.json",
      "2026-11-22/MATRIX_COLOMBIA_239_TWO_KICKOFF_CONFLICTS_QUARANTINED.json",
    ]
    return [json.loads((R/p).read_bytes()) for p in files]
def test_authentic_sources_generate_no_signal_and_no_network():
    result=decide(*docs())
    assert result["candidate_fixture_identity_count"]==2
    assert result["research_prematch_forecasts_count"]==2
    assert result["historical_matched_results"]==356
    assert result["historical_kickoff_conflicts_quarantined"]==2
    assert result["prospective_oos_gate_passed"] is False
    assert result["telegram_api_calls"]==0
    assert result["telegram_messages_sent"]==0
    assert result["official_green_signals"]==0
    assert result["production_p_matrix_authorized"] is False
    assert result["real_money"]=="BLOCKED"
def test_fake_bookmaker_sharp_quotes_cannot_promote_research_probability():
    d=docs()
    d[2]["bookmaker_quote_verified_count"]=1
    d[2]["sharp_120s_verified_count"]=1
    result=decide(*d)
    assert result["price_gate_reason"]=="RESEARCH_QUOTE_REQUIRES_SEPARATE_OFFICIAL_SOURCE_CERTIFICATION"
    assert result["telegram_messages_sent"]==0
    assert result["official_green_signals"]==0
def test_malicious_telegram_promotion_in_model_is_rejected():
    d=docs();d[1]["telegram_signal_authorized"]=True
    with pytest.raises(ValueError,match="SOURCE_OR_CALIBRATION_GOVERNANCE_INVALID"):
        decide(*d)
def test_target_scored_after_kickoff_fails_closed():
    d=docs();d[1]["research_scores"][0]["scored_at_utc"]="2026-11-25T23:20:00Z"
    with pytest.raises(ValueError,match="FORECAST_NOT_GENUINELY_PREMATCH"):
        decide(*d)
def test_unreconciled_source_fixture_id_fails():
    d=docs();d[0]["three_source_matches"][0]["espn_event_id"]="99999999"
    with pytest.raises(ValueError,match="DUPLICATE_OR_MISSING_PROSPECTIVE_FROZEN_RECORD"):
        decide(*d)
def test_real_money_unblocked_fails():
    d=docs();d[2]["real_money"]="UNBLOCKED"
    with pytest.raises(ValueError,match="REAL_MONEY_PROTECTION_VIOLATED"):
        decide(*d)
def test_fake_feature_parity_promoted_to_complete_is_rejected():
    d=docs()
    feature={"schema":"MATRIX_COL_239_356_PAIR_ORIGINAL_FEATURE_MATH_PARITY_V1",
      "real_money":"BLOCKED","verified_exact_common_finished_fixtures":356,
      "raw_goals_input_parity_within_exact_common_subset":True,
      "all_enriched_source_features_certified":True}
    with pytest.raises(ValueError,match="FEATURE_PARITY_EVIDENCE_UNTRUSTED"):
        decide(*d,feature=feature)
