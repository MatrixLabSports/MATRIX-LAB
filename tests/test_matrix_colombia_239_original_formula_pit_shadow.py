"""The real frozen MATRIX mathematical functions score only before current kickoff."""
import hashlib,json
from datetime import datetime,timezone,timedelta
import pytest
from tools.matrix_colombia_239_original_formula_pit_shadow import score

RECEIPT="2026-11-22T23:00:00Z"
SCORING=datetime(2026,11,22,23,10,tzinfo=timezone.utc)
def fixture_payload():
    events=[]
    for i in range(30):
        date=datetime(2026,9,1,tzinfo=timezone.utc)+timedelta(days=i)
        events.append({
          "id":str(40000+i),"date":date.isoformat(),
          "competitions":[{"status":{"type":{"name":"STATUS_FULL_TIME","completed":True}},
          "competitors":[
             {"homeAway":"home","team":{"id":"5484","displayName":"Millonarios"},"score":"2"},
             {"homeAway":"away","team":{"id":"6137","displayName":"Atlético Bucaramanga"},"score":"1"}]}]})
    events.append({"id":"401934688","date":"2026-11-24T23:20:00Z",
       "competitions":[{"status":{"type":{"name":"STATUS_SCHEDULED","completed":False}},
          "competitors":[
             {"homeAway":"home","team":{"id":"5484","displayName":"Millonarios"}},
             {"homeAway":"away","team":{"id":"6137","displayName":"Bucaramanga"}}]}]})
    return json.dumps({"leagues":[{"slug":"col.1"}],"events":events}).encode()
def report(raw):
    return {"schema":"MATRIX_COLOMBIA_239_COMPLETE_SEASON_FT_GOALS_AND_FUTURE_IDENTITY_AUDIT_V1",
      "espn_received_at_utc":RECEIPT,
      "espn_fullseason_raw_sha256":hashlib.sha256(raw).hexdigest(),
      "original_october_asof_finished_fixture_count":358,
      "historical_team_ids_one_to_one_crosswalked":20,
      "production_p_matrix_authorized":False,
      "telegram_signal_authorized":False,
      "real_money":"BLOCKED",
      "all_source_historical_rows_equivalent":False,
      "future_native_team_identity_bridged_rows":[{
         "espn_current_fixture_id":"401934688","kickoff_utc":"2026-11-24T23:20:00Z",
         "home":{"espn_team_id":"5484","original_api_football_team_id_from_history":"1125"},
         "away":{"espn_team_id":"6137","original_api_football_team_id_from_history":"1131"},
         "sofascore_current_identity_verified":False,
         "flashscore_current_identity_verified":False,
         "original_api_football_current_fixture_id":None,
      }]}
def test_actual_frozen_model_functions_generate_only_research_probabilities():
    raw=fixture_payload()
    out=score(report(raw),raw,now=SCORING)
    assert out["research_scores_count"]==1
    x=out["research_scores"][0]
    assert 0<x["p_over25_research_only"]<1
    assert out["original_parameters"]=={"a":0.6,"b":0.0,"c":0.4}
    assert x["home_history_count"]>=5 and x["away_history_count"]>=5
    assert out["parameter_refit"] is False
    assert out["target_results_used"] is False
    assert out["production_p_matrix_authorized"] is False
    assert out["telegram_signal_authorized"] is False
    assert out["real_money"]=="BLOCKED"
def test_source_sha_fails_closed():
    raw=fixture_payload()
    with pytest.raises(ValueError,match="UNTRUSTED_FREE_SOURCE_OR_SHA"):
        score(report(raw),raw+b" ",now=SCORING)
def test_game_at_or_before_scoring_is_not_retrospective_forecast():
    raw=fixture_payload()
    out=score(report(raw),raw,now=datetime(2026,11,25,1,tzinfo=timezone.utc))
    assert out["research_scores_count"]==0
    assert out["blocked"][0]["reason"]=="TARGET_NOT_FUTURE_AT_SCORING"
def test_untrusted_fake_canonical_identity_fails_closed():
    raw=fixture_payload()
    j=report(raw)
    j["future_native_team_identity_bridged_rows"][0]["sofascore_current_identity_verified"]=True
    with pytest.raises(ValueError,match="DO_NOT_IMPERSONATE_CANONICAL_CROSSWALK"):
        score(j,raw,now=SCORING)
def test_missing_team_history_blocks_without_zero_imputation():
    raw=fixture_payload()
    j=report(raw)
    j["future_native_team_identity_bridged_rows"][0]["home"]["espn_team_id"]="9999"
    out=score(j,raw,now=SCORING)
    assert out["research_scores_count"]==0
    assert "BLOCKED_HOME_TEAM_HISTORY" in out["blocked"][0]["reason"]
