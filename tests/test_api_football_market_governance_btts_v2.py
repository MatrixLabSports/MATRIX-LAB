from pathlib import Path
from tools.api_football_market_governance import build as build_governance
from tools.api_football_btts_challenger_v2 import build as build_btts

def test_market_governance_splits_passed_and_failed_markets():
    d=build_governance(Path("."))
    assert set(d["approved_markets"])=={"1x2","over_2_5"}
    assert d["rejected_markets"]==["btts"]
    assert all(x["engine_executable_for_p_matrix"] is False for x in d["markets"])
    assert d["p_matrix_generated"] is False
    assert d["real_money"]=="BLOCKED"

def test_btts_v2_permanently_excludes_original_final_holdout():
    d=build_btts(Path("."))
    assert d["development_count"]==1665
    assert d["validation_count"]==357
    assert d["forbidden_final_holdout_count"]==357
    assert d["forbidden_final_holdout_outcomes_read"] is False
    assert d["forbidden_final_holdout_used_for_training"] is False
    assert d["forbidden_final_holdout_used_for_validation"] is False
    assert d["exclusion_registry"]["training_validation_overlap_count"]==0
    assert "ORIGINAL_357_FINAL_HOLDOUT_PERMANENTLY_EXCLUDED" in d["next_holdout_policy"]
    assert d["governed_engine_promoted"] is False
    assert d["p_matrix_generated"] is False
    assert d["real_money"]=="BLOCKED"
