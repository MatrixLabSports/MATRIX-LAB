"""Colombia full-season archived score parity and current fixture isolation."""
import json
from tools.matrix_colombia_239_fullseason_espn_audit import inspect
import pytest

STAMP="2026-11-22T23:10:00Z"
def api():
    return {"parameters":{"league":"239","season":"2026"},"response":[{
       "league":{"id":239},"fixture":{"id":1498269,"status":{"short":"FT"},"date":"2026-10-01T23:20:00Z"},
       "teams":{"home":{"id":1125,"name":"Millonarios"},"away":{"id":1131,"name":"Bucaramanga"}},
       "goals":{"home":2,"away":1}}]}
def espn():
    def e(eid,date,status,home,away,hs=None,ascore=None):
        sides=[{"homeAway":"home","team":{"id":str(home),"displayName":"Home"},"score":str(hs) if hs is not None else None},
               {"homeAway":"away","team":{"id":str(away),"displayName":"Away"},"score":str(ascore) if ascore is not None else None}]
        return {"id":str(eid),"date":date,"competitions":[{
          "status":{"type":{"name":status,"completed":status=="STATUS_FULL_TIME"}},
          "competitors":sides}]}
    return {"leagues":[{"slug":"col.1"}],"events":[
      e(401843152,"2026-10-01T23:20:00Z","STATUS_FULL_TIME",5484,6137,2,1),
      e(401934688,"2026-11-24T23:20:00Z","STATUS_SCHEDULED",5484,6137)]}
def proof():
    row={"kickoff_score_orientation_and_name_verified":True,
         "api_home_id":"1125","espn_home_id":"5484","api_away_id":"1131","espn_away_id":"6137"}
    return {"schema":"MATRIX_COLOMBIA_239_API_ESPN_HISTORIC_IDENTITY_CROSSWALK_V1",
      "exact_historical_fixture_pairs":2,"historical_matches":[row,row],
      "distinct_original_team_ids_crosswalked":2,
      "production_p_matrix_authorized":False,"telegram_signal_authorized":False}
def check(a=None,e=None,p=None):
    return inspect(json.dumps(a or api()).encode(),json.dumps(e or espn()).encode(),
        p or proof(),STAMP)
def test_verified_goals_and_future_team_crosswalk_never_promote_production():
    j=check()
    assert j["exact_original_goals_time_and_team_parity_count"]==1
    assert j["original_results_unmatched_count"]==0
    assert j["future_research_discovery_count"]==1
    assert j["future_native_team_identity_bridged_rows"][0]["original_api_football_current_fixture_id"] is None
    assert j["production_p_matrix_authorized"] is False
    assert j["telegram_signal_authorized"] is False
def test_disagreeing_goal_quarantines_original_outcome():
    e=espn()
    e["events"][0]["competitions"][0]["competitors"][0]["score"]="0"
    j=check(e=e)
    assert j["original_results_unmatched_count"]==1
    assert j["all_source_historical_rows_equivalent"] is False
    assert j["original_enriched_feature_equivalence_certified"] is False
def test_wrong_competition_rejected():
    e=espn();e["leagues"][0]["slug"]="eng.1"
    with pytest.raises(ValueError,match="ESPN_WRONG_COLOMBIA_COMPETITION"):
        check(e=e)
def test_unknown_team_prevents_future_fixture_admission():
    e=espn();e["events"][1]["competitions"][0]["competitors"][0]["team"]["id"]="9999"
    j=check(e=e)
    assert j["future_research_discovery_count"]==0
    assert len(j["future_missing_team_identity_rows"])==1
def test_future_fulltime_is_not_prematch_candidate():
    e=espn();e["events"][1]["competitions"][0]["status"]["type"]={"name":"STATUS_FULL_TIME","completed":True}
    e["events"][1]["competitions"][0]["competitors"][0]["score"]="1"
    e["events"][1]["competitions"][0]["competitors"][1]["score"]="0"
    j=check(e=e)
    assert j["future_research_discovery_count"]==0
def test_no_research_history_backdated_as_forecast():
    j=check()
    assert j["historical_matches_not_backfilled_as_prospective_predictions"] is True
    assert j["point_in_time_source_receipt_not_backdated"] is True
    assert j["real_money"]=="BLOCKED"
