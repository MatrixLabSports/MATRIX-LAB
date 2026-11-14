"""Offline authentic-shape replay; no provider requests or betting actions."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json

import pytest
from tools.matrix_football_independent_over25_shadow import score_intake
from tools.matrix_championship_prospective_pit_attestation import report,source_digest
from tools.matrix_championship_baseline_pit_replay import replay

class Response:
    status=200
    def __init__(self,payload):
        self.body=json.dumps(payload,separators=(",",":")).encode()
    def __enter__(self):return self
    def __exit__(self,*a):return None
    def read(self,maxsize):return self.body[:maxsize]

def documents():
    now=datetime.now(timezone.utc)
    future=now+timedelta(hours=6)
    kickoff=future.isoformat()
    intake={
        "schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
        "target_date_bogota":"2026-11-03",
        "source":"FOOTBALL_DATA_ORG","provider_status":"AUTHENTICATED_FIXTURE_CAPTURE",
        "signal_generation_authorized":False,"real_money":"BLOCKED",
        "generated_at_utc":(now-timedelta(minutes=2)).isoformat(),
        "fixture_count":1,"response_sha256":"b"*64,
        "fixtures":[{"source_fixture_id":"561918","source_competition_id":2016,
            "source_competition_code":"ELC",
            "home_source_team_id":"1","away_source_team_id":"2",
            "home":"Home FC","away":"Away FC","kickoff_utc":kickoff}]}
    matches=[]
    for n in range(30):
        dt=now-timedelta(days=31-n)
        matches.append({"id":1000+n,"status":"FINISHED",
             "utcDate":dt.isoformat(),
             "competition":{"id":2016},
             "homeTeam":{"id":1,"name":"Home FC"},
             "awayTeam":{"id":2,"name":"Away FC"},
             "score":{"fullTime":{"home":n%4,"away":(n+1)%3}}})
    payload={"competition":{"id":2016},"matches":matches}
    def opener(req,timeout):
        assert req.full_url.endswith("/2016/matches")
        return Response(payload)
    shadow=score_intake(intake,"mock-token",opener=opener)
    assert shadow["scored_count"]==1
    sofa={"target_date_bogota":"2026-11-03","real_money":"BLOCKED",
          "signal_generation_authorized":False,
          "matched_count":1,
          "matched":[{"fixture_id":"561918","sofascore_event_id":"fixture-sofa",
                      "identity_time_and_teams_verified":True,
                      "kickoff_utc":kickoff}]}
    flash={"target_date_bogota":"2026-11-03","real_money":"BLOCKED",
           "signal_generation_authorized":False,
           "sofascore_verified":True,"flashscore_verified":True,"matched_count":1,
           "matched":[{"source_fixture_id":"561918","flashscore_mid":"fixture-flash",
                       "sofascore_event_id":"fixture-sofa",
                       "three_source_calendar_identity_verified":True,"kickoff_utc":kickoff}]}
    att=report(intake,sofa,flash,shadow,now=datetime.now(timezone.utc))
    assert att["prospective_research_history_certified_count"]==1
    return intake,shadow,att,sofa,flash

def test_full_authentic_raw_http_baseline_recomputed_by_original_model():
    docs=documents()
    x=replay(*docs,now=datetime.now(timezone.utc))
    assert x["verified_research_baseline_count"]==1
    row=x["rows"][0]
    assert row["status"]=="PASS_AUTHENTIC_RAW_HTTP_BASELINE_AND_POISSON_REPLAY_ONLY"
    assert row["original_group_fixture_count"]==30
    assert row["baseline_over25_recomputed"]==docs[1]["scored"][0]["baseline_over25_research_component"]
    assert row["source_response_sha256"]==docs[1]["group_status"]["2016"]["sha256"]
    assert x["calibrated_model_equivalence_verified"] is False
    assert x["production_p_matrix_authorized"] is False
    assert x["telegram_signal_authorized"] is False

def test_corrupt_http_bytes_fail_closed_even_with_same_summary():
    intake,shadow,att,sofa,flash=documents()
    shadow=deepcopy(shadow)
    raw=shadow["authenticated_raw_group_replay_evidence"]["2016"]
    raw["response_base64"]=raw["response_base64"][:-4]+"AAAA"
    att=deepcopy(att)
    att["source_shadow_sha256"]=source_digest(shadow)
    d=replay(intake,shadow,att,sofa,flash,now=datetime.now(timezone.utc))
    assert d["verified_research_baseline_count"]==0
    assert d["rows"][0]["status"].startswith("BLOCKED_GROUP_HTTP_VERIFICATION_")

def test_missing_authenticated_raw_evidence_denies_baseline():
    intake,shadow,att,sofa,flash=documents()
    shadow=deepcopy(shadow)
    shadow["authenticated_raw_group_replay_evidence"]={}
    att=deepcopy(att)
    att["source_shadow_sha256"]=source_digest(shadow)
    d=replay(intake,shadow,att,sofa,flash,now=datetime.now(timezone.utc))
    assert d["verified_research_baseline_count"]==0
    assert d["rows"][0]["status"]=="BLOCKED_AUTHENTIC_HTTP_RESPONSE_NOT_PERSISTED"

def test_probability_change_without_source_re_attestation_fails():
    intake,shadow,att,sofa,flash=documents()
    shadow=deepcopy(shadow)
    shadow["scored"][0]["baseline_over25_research_component"]=0.99
    with pytest.raises(ValueError,match="BOUND_SOURCE"):
        replay(intake,shadow,att,sofa,flash,now=datetime.now(timezone.utc))

def test_re_attested_malicious_baseline_probability_is_rejected():
    intake,shadow,att,sofa,flash=documents()
    shadow=deepcopy(shadow)
    shadow["scored"][0]["baseline_over25_research_component"]=0.99
    att=deepcopy(att)
    att["source_shadow_sha256"]=source_digest(shadow)
    d=replay(intake,shadow,att,sofa,flash,now=datetime.now(timezone.utc))
    assert d["verified_research_baseline_count"]==0
    assert d["rows"][0]["status"]=="BLOCKED_FROZEN_GROUP_FEATURE_OR_PROBABILITY_MISMATCH"

def test_started_match_never_accepted_even_if_historical_report_was_valid():
    intake,shadow,att,sofa,flash=documents()
    now=datetime.fromisoformat(intake["fixtures"][0]["kickoff_utc"])+timedelta(seconds=1)
    d=replay(intake,shadow,att,sofa,flash,now=now)
    assert d["verified_research_baseline_count"]==0
    assert d["rows"][0]["status"]=="BLOCKED_NOT_PREMATCH"
