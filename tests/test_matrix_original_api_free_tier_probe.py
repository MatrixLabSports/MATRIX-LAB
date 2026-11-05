"""No invented API-Football access; no account/secret leakage or betting."""
import json
from datetime import datetime, timezone
from urllib.error import HTTPError
from io import BytesIO

from tools.matrix_original_api_free_tier_probe import probe

class Response:
    status=200
    def __init__(self,payload):
        self.body=json.dumps(payload).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.body[:n]

STATUS={"response":{"account":{"email":"private@example.com",
      "firstname":"SECRET_FIRST","lastname":"SECRET_LAST"},
   "subscription":{"plan":"Free","active":True},
   "requests":{"current":5,"limit_day":100}},
   "errors":[]}
def league(lid):
    return {"errors":[],"response":[{"league":{"id":int(lid)},
        "seasons":[{"year":2026,"coverage":{"fixtures":{"events":True,
             "lineups":False,"statistics_fixtures":True},"standings":True}}]}]}

def opener_success(url,timeout):
    if url.endswith("/status"):return Response(STATUS)
    if "id=39" in url:return Response(league("39"))
    if "id=239" in url:return Response(league("239"))
    raise AssertionError("Unexpected third quota-consuming call")

def test_no_key_skips_all_network_and_never_promotes():
    def fail(*args,**kwargs):raise AssertionError("Must not call")
    d=probe("",opener=fail)
    assert d["status"]=="BLOCKED_NO_DIRECT_CREDENTIAL_CONFIGURED"
    assert d["quota_consuming_calls"]==0
    assert d["telegram_signal_authorized"] is False
    assert d["all_six_leagues_verified"] is False

def test_direct_free_account_probes_exact_two_and_redacts_personal_info():
    calls=[]
    def opener(req,timeout):
        assert req.get_header("X-apisports-key")=="safe-test-key"
        calls.append(req.full_url)
        return opener_success(req.full_url,timeout)
    d=probe("safe-test-key",opener=opener,
            checked_at=datetime(2026,11,5,tzinfo=timezone.utc))
    assert d["status"].startswith("PASS_TWO_LEAGUE_ACCESS_ONLY")
    assert len(calls)==3 and calls[0].endswith("/status")
    assert d["quota_consuming_calls"]==2 and d["http_status_calls"]==1
    assert d["account_status"]["daily_remaining"]==95
    assert d["two_league_coverage"]["239"]["access_verified"] is True
    assert d["all_six_leagues_verified"] is False
    assert d["original_feature_PIT_captured"] is False
    assert "safe-test-key" not in str(d)
    assert "private@example.com" not in str(d)
    assert "SECRET_FIRST" not in str(d)
    assert d["real_money"]=="BLOCKED"

def test_inactive_account_never_consumes_quota():
    payload=json.loads(json.dumps(STATUS))
    payload["response"]["subscription"]["active"]=False
    calls=[]
    def open_(*a,**kw):
        calls.append(1)
        return Response(payload)
    d=probe("key",opener=open_)
    assert len(calls)==1
    assert d["status"]=="BLOCKED_DIRECT_SUBSCRIPTION_NOT_ACTIVE"
    assert d["quota_consuming_calls"]==0

def test_quota_too_low_blocks_extra_calls():
    payload=json.loads(json.dumps(STATUS))
    payload["response"]["requests"]={"current":99,"limit_day":100}
    d=probe("key",opener=lambda *a,**k:Response(payload))
    assert d["status"]=="BLOCKED_INSUFFICIENT_QUOTA_FOR_TWO_LEAGUES"
    assert d["quota_consuming_calls"]==0

def test_http_429_fails_closed():
    def opener(req,timeout):
        raise HTTPError(req.full_url,429,"Too many",{},BytesIO(b"ignored"))
    d=probe("key",opener=opener)
    assert d["status"]=="BLOCKED_HTTP_429"
    assert d["quota_consuming_calls"]==0
    assert d["telegram_signal_authorized"] is False

def test_wrong_league_id_fails_closed():
    def opener(req,timeout):
        if req.full_url.endswith("/status"):return Response(STATUS)
        return Response(league("999"))
    d=probe("key",opener=opener)
    assert d["status"]=="BLOCKED_LEAGUE_ACCESS_OR_COVERAGE_INCOMPLETE"
    assert d["quota_consuming_calls"]==1
    assert d["all_six_leagues_verified"] is False
