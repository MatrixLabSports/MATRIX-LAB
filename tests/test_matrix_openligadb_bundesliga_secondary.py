"""Legitimate secondary provider checks, with no manufactured official P."""
import hashlib
import json
from datetime import datetime, timezone

import pytest

from tools.matrix_openligadb_bundesliga_secondary import match, fetch

ASOF = datetime(2026, 11, 21, 16, 30, tzinfo=timezone.utc)
SHA = hashlib.sha256(b"provider-native-research-test-fixture").hexdigest()

def primary():
    return {
        "schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
        "provider_status":"AUTHENTICATED_FIXTURE_CAPTURE",
        "source":"FOOTBALL_DATA_ORG",
        "real_money":"BLOCKED",
        "signal_generation_authorized":False,
        "target_date_bogota":"2026-11-22",
        "fixtures":[
            {"source_competition_id":2002,"source_fixture_id":"565864",
             "home":"FC Augsburg","away":"1. FSV Mainz 05",
             "kickoff_utc":"2026-11-22T14:30:00Z","signal_generation_authorized":False},
            {"source_competition_id":2002,"source_fixture_id":"565863",
             "home":"SV Werder Bremen","away":"Hamburger SV",
             "kickoff_utc":"2026-11-22T16:30:00Z","signal_generation_authorized":False},
        ],
    }

def league():
    return [
        {"matchID":101,"leagueShortcut":"bl1","leagueSeason":2026,
         "matchDateTimeUTC":"2026-11-22T14:30:00Z",
         "team1":{"teamId":1,"teamName":"FC Augsburg"},
         "team2":{"teamId":2,"teamName":"1. FSV Mainz 05"},
         "matchIsFinished":False},
        {"matchID":102,"leagueShortcut":"bl1","leagueSeason":2026,
         "matchDateTimeUTC":"2026-11-22T16:30:00Z",
         "team1":{"teamId":3,"teamName":"SV Werder Bremen"},
         "team2":{"teamId":4,"teamName":"Hamburger SV"},
         "matchIsFinished":False},
    ]

def test_exact_two_native_fixture_crosschecks_research_only():
    result=match(primary(),league(),captured_at=ASOF,raw_sha256=SHA)
    assert result["primary_bundesliga_candidates"]==2
    assert result["exact_prematch_matches"]==2
    assert result["rejected_candidates"]==0
    assert result["source_priority"][:2]==["SofaScore","Flashscore"]
    assert all(r["team_order_exact"] and r["utc_kickoff_exact"] for r in result["matched"])
    assert result["cross_provider_team_id_equivalence_certified"] is False
    assert result["original_enriched_feature_parity_certified"] is False
    assert result["production_p_matrix_authorized"] is False
    assert result["telegram_signal_authorized"] is False
    assert result["real_money"]=="BLOCKED"

@pytest.mark.parametrize("change", ["kickoff","team_order","duplicate","finished","post_kickoff","wrong_league"])
def test_unsupported_independent_evidence_never_turns_into_a_match(change):
    rows=league()
    now=ASOF
    if change=="kickoff":
        rows[0]["matchDateTimeUTC"]="2026-11-22T14:31:00Z"
    elif change=="team_order":
        rows[0]["team1"],rows[0]["team2"]=rows[0]["team2"],rows[0]["team1"]
    elif change=="duplicate":
        rows.append(dict(rows[0],matchID=333))
    elif change=="finished":
        rows[0]["matchIsFinished"]=True
    elif change=="post_kickoff":
        now=datetime(2026,11,22,14,31,tzinfo=timezone.utc)
    else:
        rows[0]["leagueShortcut"]="bl2"
    result=match(primary(),rows,captured_at=now,raw_sha256=SHA)
    assert result["exact_prematch_matches"] < 2
    assert result["rejected_candidates"]
    assert result["telegram_signal_authorized"] is False
    assert result["production_p_matrix_authorized"] is False

def test_wrong_primary_governance_fails_before_scoring():
    doc=primary()
    doc["signal_generation_authorized"]=True
    with pytest.raises(ValueError,match="SECONDARY_INTAKE_NOT_AUTHENTIC"):
        match(doc,league(),captured_at=ASOF,raw_sha256=SHA)

def test_source_needs_sha_and_explicit_utc_clock():
    with pytest.raises(ValueError,match="SECONDARY_RAW_SOURCE_SHA_MISSING"):
        match(primary(),league(),captured_at=ASOF,raw_sha256="fake")
    rows=league()
    rows[0]["matchDateTimeUTC"]="2026-11-22T14:30:00"
    result=match(primary(),rows,captured_at=ASOF,raw_sha256=SHA)
    assert result["exact_prematch_matches"]==1

def test_provider_is_read_once_and_response_shape_checked():
    payload=json.dumps(league()).encode("utf-8")
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self,n): return payload
    requests=[]
    def opener(request,timeout):
        requests.append((request.full_url,timeout))
        return Response()
    data,raw=fetch(opener=opener)
    assert data==league() and raw==payload
    assert len(requests)==1 and requests[0][0].endswith("/getmatchdata/bl1/2026")
