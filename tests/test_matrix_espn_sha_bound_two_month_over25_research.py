import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from tools.matrix_football_espn_enriched_pit_research import LEAGUES
from tools.matrix_football_espn_six_league_raw_capture import capture, persist
from tools.matrix_espn_sha_bound_two_month_over25_research import (
    _p_over25, evaluate, read_archive,
)


class Reply:
    status = 200
    def __init__(self, raw):
        self.raw=raw
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def read(self,n):
        return self.raw[:n]


def fake_open(req,timeout=20):
    slug=req.full_url.split("/soccer/",1)[1].split("/scoreboard",1)[0]
    if slug not in LEAGUES.values():
        raise ValueError("INVALID_LEAGUE")
    october="dates=202610" in req.full_url
    rows=[]
    if october:
        for n in range(24):
            kickoff=datetime(2026,10,1,tzinfo=timezone.utc)+timedelta(days=n)
            rows.append({
                "id":str(400000+n+1000*list(LEAGUES.values()).index(slug)),
                "date":kickoff.isoformat(),
                "competitions":[{
                    "status":{"type":{"name":"STATUS_FULL_TIME","completed":True,"state":"post"}},
                    "competitors":[
                        {"homeAway":"home","team":{"id":"1","displayName":"Home"},"score":str(n%3)},
                        {"homeAway":"away","team":{"id":"2","displayName":"Away"},"score":str(n%2)}
                    ]
                }]
            })
    else:
        rows.append({
            "id":str(500000+1000*list(LEAGUES.values()).index(slug)),
            "date":"2026-11-25T15:00:00+00:00",
            "competitions":[{
                "status":{"type":{"name":"STATUS_SCHEDULED","completed":False,"state":"pre"}},
                "competitors":[
                    {"homeAway":"home","team":{"id":"1","displayName":"Home"},"score":None},
                    {"homeAway":"away","team":{"id":"2","displayName":"Away"},"score":None}
                ]
            }]
        })
    return Reply(json.dumps({"leagues":[{"slug":slug}],"events":rows}).encode())


def make_archives(tmp_path):
    t=datetime(2026,11,22,4,0,tzinfo=timezone.utc)
    october=tmp_path/"oct"
    november=tmp_path/"nov"
    for month,dest in [("2026-10",october),("2026-11",november)]:
        report,raw=capture(month,opener=fake_open,observed_at=t)
        assert report["point_in_time_receipts_stamped_after_source_response"] is True
        persist(dest,report,raw)
    return october,november,t


def test_prospective_sha_bound_original_frozen_math(tmp_path):
    octo,nove,t=make_archives(tmp_path)
    report=evaluate(octo,nove,frozen_at=t+timedelta(minutes=1))
    assert report["research_probability_count"]==6
    assert all(v["sha_and_pit_verified_research_probabilities"]==1
               for v in report["six_league_counts"].values())
    assert all(r["observed_outcome"] is None for r in report["research_rows"])
    assert all(0<r["research_probability_over25"]<1 for r in report["research_rows"])
    assert all(r["source_history_feature_trace"]["group_history_count"]==24
               for r in report["research_rows"])
    assert all(r["source_history_feature_trace"]["home_history_count"]==20
               for r in report["research_rows"])
    assert not report["telegram_signal_authorized"]
    assert not report["production_p_matrix_authorized"]


def test_sha_tampering_fails_closed(tmp_path):
    octo,nove,t=make_archives(tmp_path)
    receipt=json.loads((octo/"MATRIX_ESPN_SIX_LEAGUE_RAW_RESEARCH_LAST.json").read_text())
    file=octo/receipt["sources"]["239"]["raw_archive_file"]
    file.write_bytes(file.read_bytes()+b" ")
    with pytest.raises(ValueError,match="AUTHENTIC_PROVIDER_BYTES_SHA_MISMATCH"):
        evaluate(octo,nove,frozen_at=t+timedelta(minutes=1))


def test_prior_receipt_must_precede_freeze(tmp_path):
    octo,nove,t=make_archives(tmp_path)
    with pytest.raises(ValueError,match="SOURCE_RECEIPT_CLOCK_CONFLICT"):
        evaluate(octo,nove,frozen_at=t-timedelta(seconds=1))


def test_no_prediction_after_kickoff(tmp_path):
    octo,nove,t=make_archives(tmp_path)
    report=evaluate(octo,nove,frozen_at=datetime(2026,11,26,tzinfo=timezone.utc))
    assert report["research_probability_count"]==0


def test_wrong_competition_namespace_is_not_accepted(tmp_path):
    octo,nove,t=make_archives(tmp_path)
    receipt=json.loads((nove/"MATRIX_ESPN_SIX_LEAGUE_RAW_RESEARCH_LAST.json").read_text())
    receipt["sources"]["239"]["provider_competition_id"]="eng.1"
    (nove/"MATRIX_ESPN_SIX_LEAGUE_RAW_RESEARCH_LAST.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError,match="MISSING_AUTHENTIC_LEAGUE_SOURCE"):
        evaluate(octo,nove,frozen_at=t+timedelta(minutes=1))


def test_no_fake_probability_with_missing_history():
    assert _p_over25([], "1", "2") is None


def test_retrospective_raw_does_not_backfill_prospective(tmp_path):
    octo,nove,t=make_archives(tmp_path)
    report=json.loads((nove/"MATRIX_ESPN_SIX_LEAGUE_RAW_RESEARCH_LAST.json").read_text())
    original=report["sources"]["239"]["source_received_at_utc"]
    report["sources"]["239"]["source_received_at_utc"]="2026-11-26T04:00:00+00:00"
    (nove/"MATRIX_ESPN_SIX_LEAGUE_RAW_RESEARCH_LAST.json").write_text(json.dumps(report))
    with pytest.raises(ValueError,match="SOURCE_RECEIPT_CLOCK_CONFLICT"):
        evaluate(octo,nove,frozen_at=t+timedelta(minutes=1))

def test_one_day_horizon_filters_without_renaming_history(tmp_path):
    octo,nove,t=make_archives(tmp_path)
    report=evaluate(octo,nove,frozen_at=t+timedelta(minutes=1),
                    max_horizon_hours=24)
    assert report["research_probability_count"]==0
    assert report["maximum_horizon_hours"]==24
    assert report["source_months"]==["2026-10","2026-11"]

def test_previously_frozen_fixture_id_cannot_repeat(tmp_path):
    octo,nove,t=make_archives(tmp_path)
    existing=evaluate(octo,nove,frozen_at=t+timedelta(minutes=1))
    ids={row["provider_fixture_id"] for row in existing["research_rows"]}
    report=evaluate(octo,nove,frozen_at=t+timedelta(minutes=1),
                    exclude_event_ids=ids)
    assert report["research_probability_count"]==0
    assert report["excluded_existing_frozen_provider_ids"]==len(ids)
    assert all(row["reason"]=="ALREADY_PREVIOUSLY_FROZEN" for row in report["blocked"])

def test_skip_nonlinear_month_pair(tmp_path):
    octo,nove,t=make_archives(tmp_path)
    with pytest.raises(ValueError,match="SOURCE_MONTHS_MUST_BE_CONSECUTIVE"):
        evaluate(octo,nove,source_months=("2026-10","2026-12"),frozen_at=t)

def test_skip_invalid_horizon(tmp_path):
    octo,nove,t=make_archives(tmp_path)
    with pytest.raises(ValueError,match="PREMATCH_HORIZON_OUTSIDE_48H"):
        evaluate(octo,nove,max_horizon_hours=100,frozen_at=t)
