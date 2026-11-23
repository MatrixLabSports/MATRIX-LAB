"""Real ESPN payload admitted only through original MATRIX structural input contract."""
import copy,gzip,json
from pathlib import Path
import pytest
from tools.matrix_colombia_239_espn_canonical_experimental_bridge import build
ROOT=Path("evidence/football_world_inventory")
def inputs():
    raw=gzip.decompress((ROOT/"2026-11-22/sources/ESPN_COL_239_FULLSEASON_RAW_RUN_45089678156.json.gz").read_bytes())
    parity=json.loads((ROOT/"2026-11-22/MATRIX_COLOMBIA_239_FULLSEASON_GOAL_PARITY_RUN_45089678156.json").read_bytes())
    triple=json.loads((ROOT/"2026-11-24/MATRIX_COLOMBIA_THREE_SOURCE_READINESS_RUN_45090559298.json").read_bytes())
    shadow=json.loads((ROOT/"2026-11-22/MATRIX_COLOMBIA_239_ORIGINAL_FORMULA_SHADOW_RUN_45089678156.json").read_bytes())
    return raw,parity,triple,shadow
def test_actual_espn_native_provider_history_maps_into_original_structural_contract():
    j=build(*inputs())
    assert j["input_count"]==2
    assert j["original_october_strict_matched_history"]==356
    assert j["historical_kickoff_conflicts_still_quarantined"]==2
    assert all(x["home_history_count"]==20 and x["away_history_count"]==20 for x in j["inputs"])
    assert all(x["structural_readiness"]=="READY_FOR_EXPERIMENTAL_EVALUATION" for x in j["inputs"])
    assert all(x["canonical_source_namespace"]=="ESPN_COL_1" for x in j["inputs"])
    assert all(x["source_native_competition_id"]=="col.1" for x in j["inputs"])
    assert all(x["original_api_football_fixture_id"] is None for x in j["inputs"])
    assert j["original_enriched_feature_equivalence_certified"] is False
    assert j["production_p_matrix_authorized"] is False
    assert j["telegram_signal_authorized"] is False
def test_tampered_raw_body_rejected_not_zero_filled():
    r=list(inputs());r[0]+=b" "
    with pytest.raises(ValueError,match="EXPERIMENTAL_CANONICAL_INPUT_SOURCE_UNTRUSTED"):
        build(*r)
def test_missing_original_matched_espn_event_blocks_canonical_inputs():
    r=list(inputs());r[1]=copy.deepcopy(r[1])
    r[1]["historical_matched_fixture_ids"].pop()
    with pytest.raises(ValueError,match="SOURCE_HISTORICAL_PAIR_SET_INCOMPLETE"):
        build(*r)
def test_unfrozen_target_timestamp_rejected():
    r=list(inputs());r[2]=copy.deepcopy(r[2])
    r[2]["three_source_matches"][0]["kickoff_utc"]="2026-11-22T23:00:00+00:00"
    with pytest.raises(ValueError,match="EXPERIMENTAL_CANONICAL_POINT_IN_TIME_FAIL"):
        build(*r)
def test_original_model_weights_never_changed():
    r=list(inputs());r[3]=copy.deepcopy(r[3]);r[3]["original_parameters"]["a"]=0.7
    with pytest.raises(ValueError,match="EXPERIMENTAL_CANONICAL_INPUT_SOURCE_UNTRUSTED"):
        build(*r)
