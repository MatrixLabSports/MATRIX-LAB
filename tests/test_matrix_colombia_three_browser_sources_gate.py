"""Real persisted three-source browser evidence and fail-closed mutation contracts."""
import copy,json
from pathlib import Path
import pytest
from tools.matrix_colombia_three_browser_sources_gate import audit

P=Path("evidence/football_world_inventory")
def data():
    obs=json.loads((P/"2026-11-24/MATRIX_COLOMBIA_BROWSER_THREE_SOURCE_DIRECT_OBSERVATIONS.json").read_bytes())
    shadow=json.loads((P/"2026-11-22/MATRIX_COLOMBIA_239_ORIGINAL_FORMULA_SHADOW_RUN_45089678156.json").read_bytes())
    bridge=json.loads((P/"2026-11-22/MATRIX_COLOMBIA_239_FUTURE_BRIDGE_RUN_45089031372.json").read_bytes())
    parity=json.loads((P/"2026-11-22/MATRIX_COLOMBIA_239_FULLSEASON_GOAL_PARITY_RUN_45089678156.json").read_bytes())
    quotes=json.loads((P/"2026-11-24/MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT.json").read_bytes())
    return [obs,shadow,bridge,parity,quotes]
def test_two_real_observed_three_provider_event_identities_keep_research_guard():
    j=audit(*data())
    assert j["three_calendar_matches"]==2
    assert {x["sofascore_event_id"] for x in j["three_source_matches"]}=={"17575405","17575404"}
    assert {x["flashscore_mid"] for x in j["three_source_matches"]}=={"dzkRA7eB","lAoJCTQb"}
    assert j["true_official_p_matrix_candidates"]==0
    assert j["last_quote_audit_bookmaker_verified"]==0
    assert j["telegram_green_signals_authorized"]==0
    assert j["real_money"]=="BLOCKED"
def test_swapped_teams_rejected():
    d=data();d[0]["fixtures"][0]["flashscore"]["home"]="Atl. Bucaramanga"
    with pytest.raises(ValueError,match="BROWSER_TEAM_ORIENTATION_MISMATCH"):audit(*d)
def test_browser_wrong_kickoff_rejected():
    d=data();d[0]["fixtures"][0]["sofascore"]["calendar_display"]="24/11/26 20:20"
    with pytest.raises(ValueError,match="BROWSER_DATE_AND_TIME_MISMATCH"):audit(*d)
def test_flashscore_fake_mid_is_rejected():
    d=data();d[0]["fixtures"][0]["flashscore"]["url"]=d[0]["fixtures"][0]["flashscore"]["url"].replace("dzkRA7eB","AAAAAAAA")
    with pytest.raises(ValueError,match="PROVIDER_EVENT_LINK_NOT_AUTHENTICATED"):audit(*d)
def test_original_model_coefficients_cannot_change():
    d=data();d[1]["original_parameters"]["a"]=0.7
    with pytest.raises(ValueError,match="ORIGINAL_CALIBRATION_MUTATED"):audit(*d)
def test_historical_team_ids_not_in_prospective_source():
    d=data();d[2]["historically_joined_research_only_fixtures"][0]["home"]["espn_team_id"]="8888"
    with pytest.raises(ValueError,match="ESPN_TEAM_ID_CONTRADICTION"):audit(*d)
def test_no_post_kickoff_browser_admission():
    d=data();d[0]["observed_at_utc"]="2026-11-25T01:00:00Z"
    with pytest.raises(ValueError,match="MULTI_SOURCE_KICKOFF_OR_LOOKAHEAD"):audit(*d)
