import io
import json
from datetime import datetime, timezone
from tools.matrix_colombia_239_public_raw_capture import capture, persist, sha
import pytest

ESPN={"events":[{"id":"100","date":"2026-11-23T01:15:00Z","status":{"type":{"name":"STATUS_SCHEDULED"}},
                 "competitions":[{"competitors":[{"homeAway":"home","team":{"displayName":"Local"}},
                                                {"homeAway":"away","team":{"displayName":"Visitante"}}]}]}]}
TSDB={"events":[{"idEvent":"200","idLeague":"4497","strSport":"Soccer",
                 "dateEvent":"2026-11-22","strTimestamp":"2026-11-23T01:15:00+00:00",
                 "strHomeTeam":"Local","strAwayTeam":"Visitante","strStatus":"NS","idAPIfootball":"1650176"}]}

class Reply:
    status=200
    def __init__(self,data):self.raw=json.dumps(data).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.raw[:n]

def opener(req,timeout=20):
    return Reply(ESPN if "espn.com" in req.full_url else TSDB)

def test_raw_observation_not_certification(tmp_path):
    r,blobs=capture("2026-11-22",opener=opener,observed_at_utc=datetime(2026,11,22,tzinfo=timezone.utc))
    assert r["raw_verified_source_count"]==2
    assert not r["production_p_matrix_authorized"]
    assert not r["telegram_signal_authorized"]
    persist(tmp_path,r,blobs)
    for provider,body in blobs.items():
        assert (tmp_path/r["sources"][provider]["raw_archive_path"]).read_bytes()==body
        assert r["sources"][provider]["raw_sha256"]==sha(body)

def test_duplicate_espn_rejected():
    def bad(req,timeout=20):
        return Reply({"events":[ESPN["events"][0],ESPN["events"][0]]} if "espn.com" in req.full_url else TSDB)
    r,_=capture("2026-11-22",opener=bad)
    assert r["sources"]["ESPN"]["status"]=="SOURCE_UNAVAILABLE_OR_INVALID"
    assert r["raw_verified_source_count"]==1

def test_cross_league_tsdb_rejected():
    def bad(req,timeout=20):
        doc=json.loads(json.dumps(TSDB));doc["events"][0]["idLeague"]="999"
        return Reply(ESPN if "espn.com" in req.full_url else doc)
    r,_=capture("2026-11-22",opener=bad)
    assert r["sources"]["THESPORTSDB"]["status"]=="SOURCE_UNAVAILABLE_OR_INVALID"

def test_no_production_writes(tmp_path):
    with pytest.raises(ValueError,match="CAPTURE_CANNOT_WRITE_PRODUCTION"):
        persist(tmp_path/"telegram",{},{})

def test_bad_date_rejected():
    with pytest.raises(ValueError):capture("2026-99-99",opener=opener)

def test_missing_tsdb_time_is_not_invented():
    doc=json.loads(json.dumps(TSDB));doc["events"][0]["strTimestamp"]=None
    def opener2(req,timeout=20):
        return Reply(ESPN if "espn.com" in req.full_url else doc)
    r,_=capture("2026-11-22",opener=opener2)
    assert r["sources"]["THESPORTSDB"]["provider_native_events"][0]["kickoff_utc"] is None

def test_unzoned_provider_api_football_id_is_hint_only():
    doc=json.loads(json.dumps(TSDB))
    doc["events"][0]["strTimestamp"]="2026-11-22T01:15:00"
    def opener3(req,timeout=20):
        return Reply(ESPN if "espn.com" in req.full_url else doc)
    report,_=capture("2026-11-22",opener=opener3)
    row=report["sources"]["THESPORTSDB"]["provider_native_events"][0]
    assert row["api_football_fixture_id_unverified_hint"]=="1650176"
    assert row["timestamp_quality"]=="UNZONED_PROVIDER_TIMESTAMP_NOT_CERTIFIED"
    assert row["kickoff_utc"] is None
    assert row["cross_provider_identity_certified"] is False

def test_utc_bogota_boundary_requires_explicit_espn_day():
    report,_=capture("2026-11-22",espn_day="2026-11-21",opener=opener)
    assert report["espn_calendar_date_requested"]=="2026-11-21"
    assert report["cross_date_source_query"] is True
    assert report["coverage_is_not_complete_for_both_calendar_days"] is True
    assert "dates=20261121" in report["sources"]["ESPN"]["url"]

def test_reject_non_adjacent_espn_day():
    with pytest.raises(ValueError,match="ESPN_DATE_MUST_BE_TARGET_OR_PRIOR_LOCAL_DAY"):
        capture("2026-11-22",espn_day="2026-11-01",opener=opener)
