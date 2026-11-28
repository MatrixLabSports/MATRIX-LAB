import hashlib
import json
from datetime import datetime,timezone
from tools.matrix_13_cohort_independent_results import compare,capture,normalized


def entry():
    return {"fixture_id":"q8","kickoff_utc":"2026-10-30T20:00:00+00:00",
            "freeze_at_utc":"2026-10-30T19:00:00+00:00",
            "home_team_name":"Cádiz CF","away_team_name":"Racing Club de Ferrol"}


def source():
    return {"matches":[{
      "id":87321,"utcDate":"2026-10-30T20:00:00Z",
      "homeTeam":{"id":98,"name":"Cadiz CF"},
      "awayTeam":{"id":99,"name":"Racing Club de Ferrol"},
      "status":"FINISHED",
      "score":{"duration":"REGULAR","fullTime":{"home":2,"away":1},
               "halfTime":{"home":1,"away":0}}
    }]}


def test_same_team_kickoff_authenticated_crossprovider_receipt():
    m,r,n=compare([entry()],source(),source_sha256="a"*64,captured_at_utc="2026-11-02T12:00:00Z")
    assert len(m)==1 and not r and n==0
    assert m[0]["api_football_fixture_id"]=="q8"
    assert m[0]["independent_provider_fixture_id"]=="87321"
    assert m[0]["halftime_certified"] is True
    assert m[0]["fulltime_home"]==2
    assert m[0]["authorized_to_append_canonical_settlement"] is False
    assert m[0]["authorized_to_produce_signals"] is False


def test_no_fuzzy_aliases_and_kickoff_inference():
    row=entry()
    row["home_team_name"]="CD Cádiz"
    m,r,n=compare([row],source(),source_sha256="a"*64,captured_at_utc="now")
    assert not m and r[0]["reason"]=="NO_EXACT_CROSS_PROVIDER_IDENTITY"
    row=entry()
    row["kickoff_utc"]="2026-10-30T20:01:00+00:00"
    m,r,n=compare([row],source(),source_sha256="a"*64,captured_at_utc="now")
    assert not m


def test_duplicates_must_not_double_settle():
    j=source()
    j["matches"].append(j["matches"][0].copy())
    m,r,n=compare([entry()],j,source_sha256="a"*64,captured_at_utc="now")
    assert not m and n==1 and r[0]["reason"]=="AMBIGUOUS_CROSS_PROVIDER_IDENTITY"


def test_nonstandard_and_untrusted_scores_rejected():
    j=source()
    j["matches"][0]["score"]["duration"]="EXTRA_TIME"
    m,r,_=compare([entry()],j,source_sha256="a"*64,captured_at_utc="now")
    assert not m and r[0]["reason"]=="EXTRA_TIME_OR_UNKNOWN_SCORE_DURATION"
    j=source()
    j["matches"][0]["score"]["fullTime"]["home"]=True
    m,r,_=compare([entry()],j,source_sha256="a"*64,captured_at_utc="now")
    assert not m and r[0]["reason"]=="INDEPENDENT_SCORE_INVALID"


def test_late_freeze_rejected_and_no_network_if_no_token():
    row=entry()
    row["freeze_at_utc"]=row["kickoff_utc"]
    m,r,_=compare([row],source(),source_sha256="a"*64,captured_at_utc="now")
    assert not m and r[0]["reason"]=="INVALID_CANONICAL_FROZEN_IDENTITY"
    result,raw=capture({"unsettled_fixture_triage":[entry()]},"",now_utc=datetime(2026,11,2,tzinfo=timezone.utc))
    assert result["quota_bounded_provider_calls"]==0
    assert result["real_money"]=="BLOCKED"
    assert raw is None


class FakeResponse:
    status=200
    def __init__(self,body):
        self.body=body
    def __enter__(self):
        return self
    def __exit__(self,*args):
        pass
    def read(self,n):
        return self.body[:n]


def test_one_realistic_provider_response_is_hashed_and_not_promoted():
    payload=json.dumps(source()).encode("utf-8")
    queries=[]
    def fake(request,timeout):
        queries.append((request.full_url,timeout,request.headers))
        return FakeResponse(payload)
    result,raw=capture(
        {"unsettled_fixture_triage":[entry()]},"fake-token",opener=fake,
        now_utc=datetime(2026,11,2,tzinfo=timezone.utc)
    )
    assert result["quota_bounded_provider_calls"]==1
    assert len(queries)==1
    assert result["source_match_count"]==1
    assert result["identity_matched_standard_final"]==1
    assert result["telegram_signal_authorized"] is False
    assert result["historical_prediction_changes"]==0
    assert result["canonical_ledger_appends"]==0
    assert result["response_sha256"]==hashlib.sha256(raw).hexdigest()
    assert "fake-token" not in json.dumps(result)
