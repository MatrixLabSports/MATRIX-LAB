"""The 8/11 refers to eleven archived fixtures, not eleven model features."""
from pathlib import Path
import json
from tools.matrix_championship_eight_of_eleven_identity_gap_diagnostic import diagnose

ROOT=Path(__file__).resolve().parents[1]
SHADOW=ROOT/"evidence/football_world_inventory/2026-11-03/MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"

def test_three_real_championship_gap_fixtures_and_names():
    x=diagnose(json.loads(SHADOW.read_text(encoding="utf-8")))
    assert x["interpretation"]=="EIGHT_OF_ELEVEN_HISTORICAL_FIXTURES_NOT_FEATURE_DIMENSIONS"
    assert x["historical_fixture_count"]==11
    assert x["historical_paired_count"]==8
    assert x["blocked_ids"]==["1563221","1563222","1563226"]
    assert len(x["blocked"])==3
    assert all(r["original_status"]=="BLOCKED_HISTORICAL_TEAM_CROSSWALK_MISSING" for r in x["blocked"])
    assert all(r["original_home_name"] and r["original_away_name"] for r in x["blocked"])
    assert x["source_game_outcomes_used_for_identity_candidates"] is False
    assert x["unmatched_three_repaired"] is True
    assert x["replayed_historical_paired_count"]==11
    assert x["production_p_matrix_authorized"] is False
    assert x["telegram_signal_authorized"] is False

def test_diagnostic_never_promotes_research_matches():
    x=diagnose(json.loads(SHADOW.read_text(encoding="utf-8")))
    assert x["source_calendar_observed_after_cutoff_not_prospective"] is True
    assert x["real_money"]=="BLOCKED"
    assert x["automatic_wagering"] is False
    assert all(r["historical_crosswalk_recovered"] is True for r in x["blocked"])
    assert all(r["prospective_crosswalk_verified"] is False for r in x["blocked"])
