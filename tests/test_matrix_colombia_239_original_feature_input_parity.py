"""Actual archived original 239 vs ESPN full-season feature matrix checks."""
from pathlib import Path
import gzip,json,copy
import pytest
from tools.matrix_colombia_239_original_feature_input_parity import verify

BASE=Path("evidence/football_world_inventory/2026-11-22")
ORIG=Path("evidence/api_football/prospective_daily/2026-10-28/20261028T054128Z/history/raw/league_239_season_2026.bin")
def inputs():
    original=ORIG.read_bytes()
    parity=json.loads((BASE/"MATRIX_COLOMBIA_239_FULLSEASON_GOAL_PARITY_RUN_45089678156.json").read_bytes())
    cross=json.loads((BASE/"MATRIX_COLOMBIA_239_HISTORIC_CROSSWALK_RUN_45088819586.json").read_bytes())
    shadow=json.loads((BASE/"MATRIX_COLOMBIA_239_ORIGINAL_FORMULA_SHADOW_RUN_45089678156.json").read_bytes())
    espn=gzip.decompress((BASE/"sources/ESPN_COL_239_FULLSEASON_RAW_RUN_45089678156.json.gz").read_bytes())
    return original,espn,parity,cross,shadow
def test_exact_common_356_original_and_espn_inputs_are_mathematically_equal():
    result=verify(*inputs())
    assert result["verified_exact_common_finished_fixtures"]==356
    assert result["identically_mapped_original_team_ids"]==20
    assert result["target_count"]==4
    assert result["quarantined_kickoff_discrepancies"]==2
    assert result["raw_goals_input_parity_within_exact_common_subset"] is True
    assert all(all(x["equal"] for x in r["input_comparisons"].values()) for r in result["targets"])
    assert result["original_parameters_unmodified"]=={"a":0.6,"b":0.0,"c":0.4}
    assert result["all_enriched_source_features_certified"] is False
    assert result["production_p_matrix_authorized"] is False
    assert result["telegram_signal_authorized"] is False
def test_real_archive_tampering_sha_blocks_parity():
    a=list(inputs());a[0]+=b" "
    with pytest.raises(ValueError,match="SOURCE_CONTENT_SHA_MISMATCH"):
        verify(*a)
def test_original_source_changed_team_is_never_auto_mapped():
    a=list(inputs());a[3]=copy.deepcopy(a[3])
    a[3]["historical_matches"][0]["api_home_id"]="999999"
    with pytest.raises(ValueError,match="CROSSWALK_TEAM_ID_CONTRADICTION|PAIRED_FIXTURE_ID_TIME_GOAL_CONTRADICTION"):
        verify(*a)
def test_original_frozen_research_model_weight_change_fails_closed():
    a=list(inputs());a[4]=copy.deepcopy(a[4]);a[4]["original_parameters"]["a"]=0.7
    with pytest.raises(ValueError,match="UNTRUSTED_PARITY_CONTRACT"):
        verify(*a)
def test_missing_matched_history_fails_closed_no_imputation():
    a=list(inputs());a[2]=copy.deepcopy(a[2]);a[2]["historical_matched_fixture_ids"].pop()
    with pytest.raises(ValueError,match="COMMON_HISTORY_ROW_COUNT_MISMATCH"):
        verify(*a)
