import copy
import pytest
from tools.matrix_colombia_239_source_route import evaluate

def sample():
    registry={"scope_approved":True,"leagues":[{"id":"239","name":"Primera A (Colombia)"}],
              "production_p_matrix_authorized":False,"telegram_signal_authorized":False,"real_money":"BLOCKED"}
    espn={"schema":"MATRIX_ESPN_PUBLIC_SIX_LEAGUE_DISCOVERY_RESEARCH_ONLY_V1",
          "source":"ESPN_PUBLIC_SCOREBOARD_JSON","provider_raw_bytes_preserved":False,
          "source_snapshots":[{"original_league_id":"239","espn_league_slug":"col.1",
          "response_event_count":1,"events":[{"espn_event_id":"123","p_matrix_authorized":False,
          "original_enriched_pit_verified":False,"sofascore_flashscore_crossmatch_verified":False}]}]}
    return registry,espn

def test_colombia_route_not_certified():
    out=evaluate(*sample())
    assert out["research_source_route_exists"] is True
    assert len(out["source_candidates"])==2
    assert not out["production_p_matrix_authorized"]
    assert not out["telegram_signal_authorized"]

def test_reject_wrong_league():
    a,b=sample();a["leagues"][0]["name"]="Portugal"
    with pytest.raises(ValueError,match="ORIGINAL_COLOMBIAN"):evaluate(a,b)

def test_reject_forged_provider_raw():
    a,b=sample();b["provider_raw_bytes_preserved"]=True
    with pytest.raises(ValueError,match="ESPN_RESEARCH"):evaluate(a,b)

def test_reject_premature_event_promotion():
    a,b=sample();b["source_snapshots"][0]["events"][0]["p_matrix_authorized"]=True
    with pytest.raises(ValueError,match="ESPN_EVENT_RESEARCH"):evaluate(a,b)

def test_reject_duplicate_event():
    a,b=sample();r=b["source_snapshots"][0];r["events"].append(copy.deepcopy(r["events"][0]));r["response_event_count"]=2
    with pytest.raises(ValueError,match="ESPN_EVENT_IDS_NOT_UNIQUE"):evaluate(a,b)
