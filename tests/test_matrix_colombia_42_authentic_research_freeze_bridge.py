"""Physical authentic pre-kickoff source-backed goals lane intake with zero fabrication."""
import json,copy
from datetime import datetime,timezone
from pathlib import Path
import pytest
from tools.matrix_colombia_42_authentic_research_freeze_bridge import (
    make_rows,TRIPLE,SHADOW,PARITY,CANON,LANES)
from tools.matrix_42_lane_prospective_registry import validate_freeze
NOW=datetime(2026,11,23,5,0,0,tzinfo=timezone.utc)
def real():
    docs=[json.loads(x.read_bytes()) for x in (TRIPLE,SHADOW,PARITY,CANON)]
    return docs
def build(doc=None,now=NOW,seen=None):
    docs=doc or real()
    return make_rows(*docs,now=now,source_shas={"test":"sha-of-authentic-files"},
        existing_events=seen or set())
def test_six_authentic_research_market_rows_from_two_triple_verified_futures():
    rows,blocked=build()
    assert len(rows)==8 and blocked==[]
    assert len({r["event_id"] for r in rows})==2
    assert set(r["market_lane"] for r in rows)==set(LANES)
    assert all(validate_freeze(r)[0] for r in rows)
    assert all(r["official_p_matrix_authorized"] is False for r in rows)
    assert all(r["telegram_signal_authorized"] is False for r in rows)
    assert all(r["experimental_only"] is True for r in rows)
    assert all(r["target_outcome"] is None and r["settlement"] is None for r in rows)
    assert all(r["real_money"]=="BLOCKED" for r in rows)
def test_rerun_same_games_not_recounted_even_with_different_freeze_clock():
    rows,_=build()
    dedup={(r["market_lane"],r["event_id"]) for r in rows}
    again,_=build(now=datetime(2026,11,23,6,tzinfo=timezone.utc),seen=dedup)
    assert len(again)==0
def test_no_post_kickoff_backfill_into_market_ledger():
    rows,blocked=build(now=datetime(2026,11,25,3,tzinfo=timezone.utc))
    assert rows==[]
    assert len(blocked)==2
    assert all(q["reason"]=="TARGET_KICKOFF_PASSED_NO_RETROACTIVE_FREEZE" for q in blocked)
def test_espn_source_mismatch_rejects_research_row():
    j=real()
    j[0]["three_source_matches"][0]["source_fixture_identity_on_three_calendars_verified"]=False
    with pytest.raises(ValueError,match="TARGET_IDENTITY_OR_HISTORY_NOT_VALID"):build(j)
def test_356_source_expected_goal_disagreement_blocks_team_totals():
    j=real()
    j[2]["targets"][0]["input_comparisons"]["expected_home_goals"]["espn_exact356"]=999
    with pytest.raises(ValueError,match="STRICT_356_SOURCE_FEATURE_NOT_EQUAL"):build(j)
def test_cannot_promote_original_p_matrix_or_money():
    j=real();j[1]["production_p_matrix_authorized"]=True
    with pytest.raises(ValueError,match="PIT_RESEARCH_SOURCE_NOT_INDEPENDENTLY_VERIFIED"):build(j)
    j=real();j[3]["real_money"]="UNBLOCKED"
    with pytest.raises(ValueError,match="PIT_RESEARCH_SOURCE_NOT_INDEPENDENTLY_VERIFIED"):build(j)
def test_never_impersonate_api_football_fixture_identity():
    rows,_=build()
    assert all(r["event_id"].startswith("ESPN_COL_1:") for r in rows)
    assert all(r["source_competition_id"]=="col.1" for r in rows)
    assert all(r["model_enriched_feature_equivalence_certified"] is False for r in rows)

def test_btts_poisson_research_baseline_is_preregistered_not_existing_model_promotion():
    import math
    rows,_=build()
    yes=[r for r in rows if r["market_lane"]=="BTTS"]
    assert len(yes)==2
    assert all(r["btts_existing_no_go_model_unchanged"] is True for r in yes)
    assert all("BASELINE_CHALLENGER" in r["model_basis"] for r in yes)
    assert all(r["official_p_matrix_authorized"] is False for r in yes)
    assert all(r["telegram_signal_authorized"] is False for r in yes)
    assert all(0<r["prediction"]["yes"]<1 for r in yes)
    assert all(abs(r["prediction"]["yes"]+r["prediction"]["no"]-1)<1e-12 for r in yes)
