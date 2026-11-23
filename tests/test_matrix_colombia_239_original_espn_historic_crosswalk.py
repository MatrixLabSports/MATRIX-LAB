"""Strict retrospective crosswalk tests: fixture ID, score, kickoff, team orientation."""
import json
from datetime import datetime,timezone
from tools.matrix_colombia_239_original_espn_historic_crosswalk import compare,original_rows,espn_rows

def originals():
    return {"parameters":{"league":"239","season":"2026"},"response":[
      {"league":{"id":239},"fixture":{"id":1490001,"status":{"short":"FT"},"date":"2026-10-27T23:00:00Z"},
       "teams":{"home":{"id":1470,"name":"Cucuta"},"away":{"id":1144,"name":"Águilas Doradas"}},
       "goals":{"home":0,"away":2}},
      {"league":{"id":239},"fixture":{"id":1490002,"status":{"short":"FT"},"date":"2026-10-28T01:05:00Z"},
       "teams":{"home":{"id":1132,"name":"Chico"},"away":{"id":1135,"name":"Junior"}},
       "goals":{"home":1,"away":1}}
    ]}
def espn():
    def event(eid,kickoff,home,hid,hs,away,aid,ascore):
        return {"id":str(eid),"date":kickoff,"competitions":[{
           "status":{"type":{"name":"STATUS_FULL_TIME","completed":True}},
           "competitors":[
             {"homeAway":"home","team":{"id":str(hid),"displayName":home},"score":str(hs)},
             {"homeAway":"away","team":{"id":str(aid),"displayName":away},"score":str(ascore)}]}]}
    return {"leagues":[{"slug":"col.1"}],"events":[
        event(401877953,"2026-10-27T23:00Z","Cúcuta Deportivo",6101,0,"Águilas Doradas",9762,2),
        event(401877861,"2026-10-28T01:05Z","Boyacá Chicó FC",5480,1,"Atlético Junior",4815,1)
    ]}
def audit(o=None,e=None):
    return compare(json.dumps(o or originals()).encode(),json.dumps(e or espn()).encode(),
                   "2026-11-23T01:00:00Z")
def test_two_genuine_historical_fixture_ids_and_four_unique_team_ids():
    out=audit()
    assert out["exact_historical_fixture_pairs"]==2
    assert out["distinct_original_team_ids_crosswalked"]==4
    a,b=out["historical_matches"]
    assert a["espn_event_id"]=="401877953" and a["api_home_id"]=="1470" and a["espn_home_id"]=="6101"
    assert b["espn_event_id"]=="401877861" and b["api_home_id"]=="1132" and b["espn_home_id"]=="5480"
    assert out["prospective_cross_provider_fixture_identity_certified"] is False
    assert out["production_p_matrix_authorized"] is False
    assert out["telegram_signal_authorized"] is False
    assert out["real_money"]=="BLOCKED"
def test_wrong_league_rejected_without_fuzzy_reassignment():
    import pytest
    x=espn();x["leagues"][0]["slug"]="eng.1"
    with pytest.raises(ValueError,match="ESPN_WRONG_COLOMBIA_COMPETITION"):
        audit(e=x)
def test_mismatched_score_does_not_produce_team_crosswalk():
    e=espn();e["events"][0]["competitions"][0]["competitors"][0]["score"]="1"
    out=audit(e=e)
    assert out["exact_historical_fixture_pairs"]==1
    assert out["distinct_original_team_ids_crosswalked"]==2
def test_wrong_kickoff_and_reversed_teams_are_rejected():
    e=espn();e["events"][0]["date"]="2026-10-27T23:20:00Z"
    # Swapping list order does not change homeAway semantics; swap labels.
    sides=e["events"][1]["competitions"][0]["competitors"]
    sides[0]["homeAway"]="away"
    sides[1]["homeAway"]="home"
    out=audit(e=e)
    assert out["exact_historical_fixture_pairs"]==0
def test_wrong_original_league_rejected():
    import pytest
    o=originals();o["parameters"]["league"]="39"
    with pytest.raises(ValueError,match="ORIGINAL_COLOMBIA_ARCHIVE_HEADER_INVALID"):
        audit(o=o)
def test_contradictory_source_team_id_fails_closed():
    import pytest
    x=espn()
    x["events"][1]["competitions"][0]["competitors"][0]["team"]["id"]="6101"
    # Different original teams mapping to the same ESPN ID must fail closed.
    with pytest.raises(ValueError,match="CROSSWALK_TEAM_ID_CONTRADICTION"):
        audit(e=x)
def test_repeated_espn_id_rejected():
    import pytest
    x=espn();x["events"][1]["id"]=x["events"][0]["id"]
    with pytest.raises(ValueError,match="ESPN_DUPLICATE_OR_INVALID_EVENT"):
        audit(e=x)
def test_no_forecast_from_posthoc_outcome_data():
    out=audit()
    assert out["status"]=="HISTORIC_IDENTITY_AUDIT_ONLY_NOT_PROSPECTIVE_MODEL_PARITY"
    assert out["source_feature_parity_certified"] is False
    assert out["scientific_oos_certified"] is False
