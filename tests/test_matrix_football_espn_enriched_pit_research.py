import hashlib
import json
import pytest
from tools.matrix_football_espn_enriched_pit_research import extract,eligible_history

FIXTURE={
  "leagues":[{"slug":"col.1"}],
  "events":[{"id":"401934689","date":"2026-11-22T01:15Z",
             "competitions":[{"status":{"type":{"name":"STATUS_FULL_TIME","completed":True}},
             "competitors":[
               {"homeAway":"home","score":"0","team":{"id":"2919","displayName":"Once Caldas"},
                "statistics":[{"name":k,"displayValue":v} for k,v in
                              [("totalShots","12"),("shotsOnTarget","1"),("wonCorners","7"),
                               ("foulsCommitted","10"),("possessionPct","48.9")]]},
               {"homeAway":"away","score":"0","team":{"id":"5264","displayName":"Atlético Nacional"},
                "statistics":[{"name":k,"displayValue":v} for k,v in
                              [("totalShots","7"),("shotsOnTarget","1"),("wonCorners","3"),
                               ("foulsCommitted","12"),("possessionPct","51.1")]]}
             ]}]}]}
def make(payload=FIXTURE, observed="2026-11-22T04:20:00+00:00", league="239"):
    raw=json.dumps(payload).encode("utf-8")
    return extract(raw,raw_sha256=hashlib.sha256(raw).hexdigest(),
                   observed_at_utc=observed,original_league_id=league)

def test_verified_genuine_shape_statistics_are_research_only():
    out=make()
    assert out["verified_source_event_count"]==1
    assert out["fully_enriched_event_count"]==1
    assert out["rows"][0]["home"]["stats"]["wonCorners"]==7
    assert out["rows"][0]["away"]["stats"]["totalShots"]==7
    assert out["production_p_matrix_authorized"] is False

def test_history_was_not_available_before_observation():
    out=make()
    assert eligible_history(out,forecast_frozen_at_utc="2026-11-22T02:00Z")==[]
    assert len(eligible_history(out,forecast_frozen_at_utc="2026-11-22T05:00Z"))==1

def test_no_future_outcome_accepted():
    out=make(observed="2026-11-21T23:00:00Z")
    assert out["verified_source_event_count"]==0
    assert len(out["rejected_or_not_final_events"])==1

def test_nonfinite_or_missing_stats_never_become_zero():
    p=json.loads(json.dumps(FIXTURE))
    p["events"][0]["competitions"][0]["competitors"][0]["statistics"]=[]
    out=make(p)
    assert out["verified_source_event_count"]==1
    assert out["fully_enriched_event_count"]==0
    assert out["rows"][0]["home"]["stats"]["wonCorners"] is None

def test_stat_duplicate_rejected():
    p=json.loads(json.dumps(FIXTURE))
    c=p["events"][0]["competitions"][0]["competitors"][0]
    c["statistics"].append({"name":"wonCorners","displayValue":"7"})
    out=make(p)
    assert out["verified_source_event_count"]==0
    assert out["rejected_or_not_final_events"][0]["reason"]=="ESPN_DUPLICATE_STAT_FIELD"

def test_wrong_league_cannot_be_mixed():
    with pytest.raises(ValueError,match="ESPN_COMPETITION_NAMESPACE_MISMATCH"):
        make(league="39")

def test_modified_raw_digest_rejected():
    raw=json.dumps(FIXTURE).encode()
    with pytest.raises(ValueError,match="RAW_SOURCE_SHA256_MISMATCH"):
        extract(raw+b" ",raw_sha256=hashlib.sha256(raw).hexdigest(),
                observed_at_utc="2026-11-22T04:20Z",original_league_id="239")

def test_not_full_time_not_settled():
    p=json.loads(json.dumps(FIXTURE))
    p["events"][0]["competitions"][0]["status"]["type"]["name"]="STATUS_IN_PROGRESS"
    out=make(p)
    assert out["verified_source_event_count"]==0
