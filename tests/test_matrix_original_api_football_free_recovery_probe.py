import json
from datetime import datetime,timezone
from tools.matrix_original_api_football_free_recovery_probe import probe

NOW=datetime(2026,11,4,16,tzinfo=timezone.utc)

class Response:
    def __init__(self,league,*,status=200,errors=None,rate=60):
        self.status_code=status
        self.headers={"x-ratelimit-requests-remaining":str(rate)}
        self.content=json.dumps({"errors":errors or {},
            "response":[{"fixture":{"id":100000+int(league),"date":"2026-11-06T20:00:00+00:00"},
                         "league":{"id":int(league)}}] if status==200 and not errors else []}).encode()

class Session:
    def __init__(self,*,bad=False,rate=60):self.calls=[];self.bad=bad;self.rate=rate
    def get(self,url,params,headers,timeout):
        assert url.endswith("/fixtures")
        assert headers.get("x-apisports-key")=="test-key"
        self.calls.append(params["league"])
        return Response(params["league"],status=403 if self.bad else 200,rate=self.rate)

def test_six_original_leagues_verified_without_promoting_model(tmp_path):
    sess=Session()
    r=probe(key="test-key",now=NOW,root=tmp_path,session=sess)
    assert len(sess.calls)==6
    assert r["original_league_id_coverage"]==6
    assert r["original_six_league_coverage_verified"] is True
    assert r["production_p_matrix_authorized"] is False
    assert r["telegram_signal_authorized"] is False

def test_403_stops_without_retrying_any_other_league(tmp_path):
    sess=Session(bad=True)
    r=probe(key="test-key",now=NOW,root=tmp_path,session=sess)
    assert len(sess.calls)==1
    assert r["original_six_league_coverage_verified"] is False
    assert r["real_money"]=="BLOCKED"

def test_provider_remaining_at_reserve_is_not_exhausted(tmp_path):
    sess=Session(rate=20)
    r=probe(key="test-key",now=NOW,root=tmp_path,session=sess)
    assert r["calls"]==1
    assert len(sess.calls)==1

def test_no_key_does_not_call_network(tmp_path):
    r=probe(key="",now=NOW,root=tmp_path,session=Session())
    assert r["status"]=="ORIGINAL_API_FOOTBALL_KEY_MISSING"
    assert r["calls"]==0
