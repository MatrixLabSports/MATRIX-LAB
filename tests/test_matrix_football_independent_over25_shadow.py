import json
from datetime import datetime, timedelta, timezone

from tools.matrix_football_independent_over25_shadow import historic_rows, score_intake

def intake():
    return {
        "schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
        "source":"FOOTBALL_DATA_ORG","real_money":"BLOCKED",
        "signal_generation_authorized":False,
        "target_date_bogota":"2026-11-02",
        "fixtures":[{
            "source_fixture_id":"301","source_competition_id":2019,
            "home_source_team_id":"1","away_source_team_id":"2",
            "home":"Home","away":"Away","kickoff_utc":"2030-11-02T18:00:00+00:00",
        }],
    }

def history(n=30):
    rows=[]
    for i in range(n):
        moment=datetime(2026,9,1,tzinfo=timezone.utc)+timedelta(days=i)
        rows.append({
            "id":str(1000+i), "status":"FINISHED","utcDate":moment.isoformat(),
            "competition":{"id":2019},
            "homeTeam":{"id":1}, "awayTeam":{"id":2},
            "score":{"fullTime":{"home":i%4,"away":(i+1)%3}},
        })
    return {"competition":{"id":2019},"matches":rows}

class Response:
    status=200
    def __init__(self,payload):self.payload=payload
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def read(self,_):return json.dumps(self.payload).encode()

def test_histories_reuse_frozen_model_without_authorizing_signal():
    def opener(req,timeout):
        assert req.full_url.endswith("/2019/matches")
        assert req.get_header("X-auth-token")=="fake-key"
        assert timeout==25
        return Response(history())
    r=score_intake(intake(),"fake-key",opener=opener)
    assert r["network_calls"]==1
    assert r["scored_count"]==1
    assert r["blocked_count"]==0
    assert 0 < r["scored"][0]["p_over25_research"] < 1
    assert r["frozen_parameters"]=={"a":0.6,"b":0.0,"c":0.4}
    assert r["parameter_refit"] is False
    assert r["market_signal_authorized"] is False
    assert r["real_money"]=="BLOCKED"

def test_short_history_cannot_create_probability():
    r=score_intake(intake(),"fake-key",opener=lambda *_a,**_kw:Response(history(5)))
    assert r["scored_count"]==0
    assert "HISTORY_BELOW_20" in r["blocked"][0]["reason"]
    assert r["market_signal_authorized"] is False

def test_competition_mismatch_fails_closed():
    h=history()
    h["matches"][0]["competition"]["id"]=123
    r=score_intake(intake(),"fake-key",opener=lambda *_a,**_kw:Response(h))
    assert r["scored_count"]==0
    assert r["group_status"]["2019"]["status"]=="HISTORY_PROVIDER_BLOCKED"

def test_no_token_does_not_call_provider():
    def never(*a,**kw):raise AssertionError("UNEXPECTED_NETWORK")
    r=score_intake(intake(),"",opener=never)
    assert r["network_calls"]==0
    assert r["market_signal_authorized"] is False

def test_provider_scoring_does_not_accept_wrong_discovery():
    x=intake()
    x["signal_generation_authorized"]=True
    try:
        score_intake(x,"fake-key",opener=lambda *_a,**_kw:Response(history()))
    except ValueError as exc:
        assert "MUST_NOT_AUTHORIZE" in str(exc)
    else:
        raise AssertionError("DISCOVERY_PROMOTION_FORBIDDEN")
