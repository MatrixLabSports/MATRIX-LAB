import copy
import pytest
from tools.matrix_alternative_oos_readiness_gate import evaluate


def sample():
    score = {"schema":"MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_V1",
             "provider_competitions":[{"source_competition_id":str(i),
                "independent_out_of_sample_rows":10,
                "scientific_original_six_league_equivalence_certified":False} for i in range(6)],
             "total_verified_settled_rows":60,"production_p_matrix_authorized":False,
             "telegram_signal_authorized":False,"real_money":"BLOCKED"}
    scope = {"schema":"MATRIX_OVER25_ORIGINAL_SCOPE_RESEARCH_PROGRESS_V1",
             "original_six_league_ids":list(range(6)),
             "provider_competition_map_source_to_original":{str(i):str(i) for i in range(6)},
             "production_p_matrix_authorized":False,
             "telegram_signal_authorized":False,"real_money":"BLOCKED"}
    return score,scope


def test_counts_no_promotion():
    result=evaluate(*sample())
    assert len(result["six_league_research_rows"])==6
    assert result["six_league_research_rows"][0]["remaining_for_30_row_research_screen"]==20
    assert not result["scientific_independent_model_certified"]
    assert not result["production_p_matrix_authorized"]
    assert not result["telegram_signal_authorized"]


def test_duplicate_provider_rejected():
    a,b=sample()
    a["provider_competitions"].append(copy.deepcopy(a["provider_competitions"][0]))
    with pytest.raises(ValueError,match="SCORECARD_ROW_UNTRUSTED"):evaluate(a,b)


def test_total_mismatch_rejected():
    a,b=sample();a["total_verified_settled_rows"]=61
    with pytest.raises(ValueError,match="OOS_TOTAL_RECONCILIATION_FAILED"):evaluate(a,b)


def test_governance_rejects_promoted_input():
    a,b=sample();b["telegram_signal_authorized"]=True
    with pytest.raises(ValueError,match="RESEARCH_GOVERNANCE_NOT_FAIL_CLOSED"):evaluate(a,b)


def test_missing_mapping_cannot_pass():
    a,b=sample();b["provider_competition_map_source_to_original"].pop("0")
    result=evaluate(a,b)
    assert result["six_league_research_rows"][0]["alternative_competitions"]==[]
    assert not result["all_six_research_screens_reached"]
