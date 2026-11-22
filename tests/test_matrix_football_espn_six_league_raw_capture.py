import hashlib
import json
from datetime import datetime,timezone
import pytest
from tools.matrix_football_espn_six_league_raw_capture import capture,persist

class Reply:
    status=200
    def __init__(self,body): self.body=body
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.body[:n]

def fake(req,timeout=20):
    slug=req.full_url.split("/soccer/",1)[1].split("/scoreboard",1)[0]
    body=json.dumps({"leagues":[{"slug":slug}],"events":[]}).encode()
    return Reply(body)

def test_six_league_raw_capture_no_fake_results(tmp_path):
    report,raws=capture("2026-11-21",opener=fake,
        observed_at=datetime(2026,11,22,tzinfo=timezone.utc))
    assert report["source_captured_leagues"]==6
    assert all(v["fully_enriched_history_count"]==0 for v in report["sources"].values())
    assert not report["production_p_matrix_authorized"]
    persist(tmp_path,report,raws)
    assert len(list(tmp_path.glob("ESPN_*.json")))==6
    for lid,raw in raws.items():
        assert hashlib.sha256(raw).hexdigest()==report["sources"][lid]["raw_sha256"]

def test_one_bad_source_remains_unknown():
    def broken(req,timeout=20):
        if "col.1" in req.full_url:
            raise ValueError("NO_SOURCE")
        return fake(req,timeout)
    report,raws=capture("2026-11-21",opener=broken)
    assert report["source_captured_leagues"]==5
    assert report["sources"]["239"]["fully_enriched_history_count"] is None
    assert report["sources"]["239"]["status"]=="SOURCE_CAPTURE_BLOCKED_NO_ZERO_IMPUTATION"

def test_provider_league_swap_rejected():
    def wrong(req,timeout=20):
        return Reply(json.dumps({"leagues":[{"slug":"bogus"}],"events":[]}).encode())
    report,raws=capture("2026-11-21",opener=wrong)
    assert not raws
    assert report["source_captured_leagues"]==0

def test_forbid_prod_writes(tmp_path):
    with pytest.raises(ValueError,match="RAW_RESEARCH_NOT_PRODUCTION"):
        persist(tmp_path/"notifications",{"sources":{}},{})

def test_monthly_archive_uses_bounded_six_calls(tmp_path):
    seen=[]
    def recorder(req,timeout=20):
        seen.append(req.full_url)
        return fake(req,timeout)
    report,raws=capture("2026-10",opener=recorder,
        observed_at=datetime(2026,11,22,tzinfo=timezone.utc))
    assert len(seen)==6
    assert all("dates=202610&limit=300" in link for link in seen)
    assert report["query_kind"]=="MONTH"
    assert report["backfilled_monthly_results_are_not_prospective_predictions"] is True
    assert report["production_p_matrix_authorized"] is False
    persist(tmp_path,report,raws)
    assert len(list(tmp_path.glob("ESPN_*.json")))==6

def test_monthly_source_does_not_admit_invalid_date():
    with pytest.raises(ValueError):
        capture("2026-13",opener=fake)
    with pytest.raises(ValueError):
        capture("October 2026",opener=fake)
