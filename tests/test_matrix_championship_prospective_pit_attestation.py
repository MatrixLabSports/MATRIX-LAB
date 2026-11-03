"""Contracts are simulated, production requires real authenticated snapshots."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from tools.api_football_market_shadow_p_matrix import _pool_over25
from tools.matrix_championship_prospective_pit_attestation import report

NOW=datetime(2026,11,3,10,10,tzinfo=timezone.utc)
KICKOFF="2026-11-03T19:45:00+00:00"
SOURCE_HASH="a"*64
FIXTURE_HASH="b"*64

def docs():
    fixture={"source_fixture_id":"561918","source_competition_id":2016,
             "source_competition_code":"ELC","home":"Portsmouth FC",
             "away":"Swansea City AFC","home_source_team_id":"31",
             "away_source_team_id":"42","kickoff_utc":KICKOFF}
    intake={"schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1","source":"FOOTBALL_DATA_ORG",
            "provider_status":"AUTHENTICATED_FIXTURE_CAPTURE",
            "signal_generation_authorized":False,"real_money":"BLOCKED",
            "target_date_bogota":"2026-11-03","generated_at_utc":"2026-11-03T10:00:00+00:00",
            "response_sha256":FIXTURE_HASH,"fixture_count":1,"fixtures":[fixture]}
    sofa={"target_date_bogota":"2026-11-03","signal_generation_authorized":False,
          "real_money":"BLOCKED","matched_count":1,
          "matched":[{"fixture_id":"561918","identity_time_and_teams_verified":True,
                      "sofascore_event_id":"16391597","kickoff_utc":KICKOFF}]}
    flash={"target_date_bogota":"2026-11-03","signal_generation_authorized":False,
           "real_money":"BLOCKED","sofascore_verified":True,"flashscore_verified":True,
           "matched_count":1,
           "matched":[{"source_fixture_id":"561918","three_source_calendar_identity_verified":True,
                       "sofascore_event_id":"16391597","flashscore_mid":"4tCThItm",
                       "kickoff_utc":KICKOFF}]}
    def rows(team_id):
        ret=[]
        for n in range(5):
            prior=NOW-timedelta(days=12+n)
            ret.append({"fixture_id":str(1000+n+int(team_id)*100),
                        "kickoff_utc":prior.isoformat(),"team_id":team_id,
                        "opponent_id":str(700+n),"opponent_name":"Real Opponent "+str(n),
                        "venue_role":"home" if n%2==0 else "away",
                        "goals_for":n%3,"goals_against":(n+1)%3,
                        "observed_at_utc":"2026-11-03T10:04:00+00:00",
                        "source_provider":"FOOTBALL_DATA_ORG",
                        "source_payload_sha256":SOURCE_HASH})
        return ret
    probability=_pool_over25(0.55,0.60)
    shadow={"real_money":"BLOCKED","market_signal_authorized":False,"parameter_refit":False,
            "model":"calibrated_log_pool_v1","frozen_parameters":{"a":0.6,"b":0.0,"c":0.4},
            "target_date_bogota":"2026-11-03","completed_at_utc":"2026-11-03T10:05:00+00:00",
            "scored_count":1,"scored":[{
                "source_fixture_id":"561918","kickoff_utc":KICKOFF,"competition_id":2016,
                "signal_generation_authorized":False,"history_sha256":SOURCE_HASH,
                "p_over25_research":round(probability,10),
                "poisson_over25_research_component":0.55,
                "baseline_over25_research_component":0.60,
                "prospective_history_provenance":{
                  "status":"PROSPECTIVE_HISTORY_ROWS_OBSERVED",
                  "history_observed_at_utc":"2026-11-03T10:04:00+00:00",
                  "source_payload_sha256":SOURCE_HASH,
                  "home_history":rows("31"),"away_history":rows("42")}
            }]}
    return intake,sofa,flash,shadow

def test_authentic_shape_prospective_shadow_stays_not_authorized():
    d=report(*docs(),now=NOW)
    assert d["championship_fixture_count"]==1
    assert d["prospective_research_history_certified_count"]==1
    assert d["rows"][0]["research_ready_for_experimental_evaluation"] is True
    assert d["rows"][0]["research_input_sha256"]
    assert d["production_p_matrix_authorized_count"]==0
    assert d["telegram_signal_authorized"] is False
    assert d["calibration_untouched"] is True
    assert "p_matrix" not in d["rows"][0]

def test_started_target_never_certified():
    intake,sofa,flash,shadow=docs()
    d=report(intake,sofa,flash,shadow,now=datetime(2026,11,3,20,0,tzinfo=timezone.utc))
    assert d["prospective_research_history_certified_count"]==0

def test_mismatched_browser_mid_blocks():
    intake,sofa,flash,shadow=docs()
    flash["matched"][0]["sofascore_event_id"]="WRONG"
    d=report(intake,sofa,flash,shadow,now=NOW)
    assert d["rows"][0]["status"]=="BLOCKED_TRIPLE_IDENTITY_CONFLICT"

def test_post_analysis_history_observation_blocks():
    intake,sofa,flash,shadow=docs()
    shadow["scored"][0]["prospective_history_provenance"]["home_history"][0]["observed_at_utc"]="2026-11-03T11:00:00+00:00"
    d=report(intake,sofa,flash,shadow,now=NOW)
    assert d["prospective_research_history_certified_count"]==0
    assert d["rows"][0]["status"]=="BLOCKED_INVALID_PROVENANCE_OR_IDENTITY"

def test_stale_capture_never_accepted():
    intake,sofa,flash,shadow=docs()
    intake["generated_at_utc"]="2026-11-03T08:00:00+00:00"
    try:
        report(intake,sofa,flash,shadow,now=NOW)
    except ValueError as e:
        assert "STALE" in str(e)
    else:
        raise AssertionError("STALE_CAPTURE_MUST_FAIL")

def test_false_probability_blocked():
    intake,sofa,flash,shadow=docs()
    shadow["scored"][0]["p_over25_research"]=0.99
    d=report(intake,sofa,flash,shadow,now=NOW)
    assert d["rows"][0]["status"]=="BLOCKED_ORIGINAL_MODEL_RECOMPUTATION_MISMATCH"
    assert d["prospective_research_history_certified_count"]==0

def test_missing_historical_name_fails_closed():
    intake,sofa,flash,shadow=docs()
    shadow["scored"][0]["prospective_history_provenance"]["away_history"][0]["opponent_name"]=""
    d=report(intake,sofa,flash,shadow,now=NOW)
    assert d["rows"][0]["status"]=="BLOCKED_INVALID_PROVENANCE_OR_IDENTITY"

def test_bad_governance_fails_closed():
    intake,sofa,flash,shadow=docs()
    shadow["market_signal_authorized"]=True
    try:
        report(intake,sofa,flash,shadow,now=NOW)
    except ValueError as e:
        assert "GOVERNANCE" in str(e)
    else:
        raise AssertionError("MUST_DENY_ELEVATED_GOVERNANCE")
