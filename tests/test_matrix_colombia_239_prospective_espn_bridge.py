"""Colombia ESPN current fixture research bridge must fail closed on identity/time."""
import json
from tools.matrix_colombia_239_prospective_espn_bridge import inspect, DAYS
import pytest

NOW="2026-11-22T23:00:00Z"
def crosswalk():
    rows=[{"espn_home_id":"5484","api_home_id":"1125","espn_away_id":"6137",
          "api_away_id":"1131","kickoff_score_orientation_and_name_verified":True},
          {"espn_home_id":"8109","api_home_id":"1138","espn_away_id":"2672",
          "api_away_id":"1127","kickoff_score_orientation_and_name_verified":True}]
    return {"schema":"MATRIX_COLOMBIA_239_API_ESPN_HISTORIC_IDENTITY_CROSSWALK_V1",
      "exact_historical_fixture_pairs":2,"distinct_original_team_ids_crosswalked":4,
      "historical_matches":rows,"real_money":"BLOCKED",
      "prospective_cross_provider_fixture_identity_certified":False,
      "production_p_matrix_authorized":False,"telegram_signal_authorized":False}
def event(event_id,date,homeid,awayid,status="STATUS_SCHEDULED"):
    return {"id":str(event_id),"date":date,"competitions":[{"status":{"type":{
      "name":status,"completed":False}},"competitors":[
      {"homeAway":"home","team":{"id":str(homeid),"displayName":"Home"}},
      {"homeAway":"away","team":{"id":str(awayid),"displayName":"Away"}}]}]}
def days():
    first={"leagues":[{"slug":"col.1"}],"events":[
       event(401934688,"2026-11-24T23:20:00Z",5484,6137),
       event(401934706,"2026-11-25T01:30:00Z",8109,2672)]}
    second={"leagues":[{"slug":"col.1"}],"events":[]}
    return {"20261124":json.dumps(first).encode(),"20261125":json.dumps(second).encode()}
def test_future_mapped_pairs_do_not_authorize_model():
    j=inspect(days(),crosswalk(),observed_at_utc=NOW)
    assert j["future_fixtures_with_historic_team_id_bridge"]==2
    assert j["eligible_for_production"]==0
    assert all(x["sofascore_fixture_match_verified"] is False for x in j["historically_joined_research_only_fixtures"])
    assert j["production_p_matrix_authorized"] is False and j["telegram_signal_authorized"] is False
def test_missing_historical_team_identity_blocks_current_pair():
    d=days();j=json.loads(d["20261124"])
    j["events"][0]["competitions"][0]["competitors"][1]["team"]["id"]="999999"
    d["20261124"]=json.dumps(j).encode()
    x=inspect(d,crosswalk(),observed_at_utc=NOW)
    assert x["future_fixtures_with_historic_team_id_bridge"]==1
    assert x["blocked"][0]["reason"]=="TEAM_NOT_PROVEN_BY_PRIOR_HISTORICAL_CROSSWALK"
def test_wrong_league_rejected():
    d=days();j=json.loads(d["20261124"]);j["leagues"][0]["slug"]="eng.1"
    d["20261124"]=json.dumps(j).encode()
    with pytest.raises(ValueError,match="ESPN_INCORRECT_COMPETITION"):
        inspect(d,crosswalk(),observed_at_utc=NOW)
def test_future_result_cannot_be_admitted_after_kickoff():
    with_time="2026-11-26T12:00:00Z"
    j=inspect(days(),crosswalk(),observed_at_utc=with_time)
    assert j["future_fixtures_with_historic_team_id_bridge"]==0
def test_source_team_mapping_conflict_fails_closed():
    c=crosswalk()
    c["historical_matches"].append({"espn_home_id":"5484","api_home_id":"1138",
                                    "espn_away_id":"2672","api_away_id":"1127",
                                    "kickoff_score_orientation_and_name_verified":True})
    c["exact_historical_fixture_pairs"]=3
    with pytest.raises(ValueError,match="CROSSWALK_TEAM_ID_CONTRADICTION"):
        inspect(days(),c,observed_at_utc=NOW)
def test_duplicate_current_event_ids_fail():
    d=days();j=json.loads(d["20261124"]);j["events"][1]["id"]=j["events"][0]["id"]
    d["20261124"]=json.dumps(j).encode()
    with pytest.raises(ValueError,match="ESPN_DUPLICATE_PROSPECTIVE_EVENT"):
        inspect(d,crosswalk(),observed_at_utc=NOW)
