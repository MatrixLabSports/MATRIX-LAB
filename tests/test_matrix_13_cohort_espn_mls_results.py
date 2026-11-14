import json
from tools.matrix_13_cohort_espn_mls_results import club, compare, run


def frozen():
    return {"fixture_id":"1490574","competition_name":"Major League Soccer",
       "kickoff_utc":"2026-10-28T23:30:00+00:00",
       "freeze_at_utc":"2026-10-25T03:50:08+00:00",
       "home_team_name":"Charlotte","away_team_name":"CF Montreal"}


def event():
    return {"events":[{
      "id":"761907","date":"2026-10-28T23:30Z",
      "competitions":[{
        "status":{"period":2,"type":{"name":"STATUS_FULL_TIME","completed":True}},
        "competitors":[
          {"homeAway":"home","score":"4","team":{"displayName":"Charlotte FC"}},
          {"homeAway":"away","score":"0","team":{"displayName":"CF Montréal"}}
        ]
      }]
    }]}


def test_exact_mls_result_with_safe_suffix_normalization():
    matches,rejected=compare([frozen()],event(),"0"*64)
    assert not rejected
    assert len(matches)==1
    r=matches[0]
    assert r["api_football_fixture_id"]=="1490574"
    assert r["espn_fixture_id"]=="761907"
    assert r["fulltime_home"]==4 and r["fulltime_away"]==0
    assert r["canonical_ledger_appends"]==0
    assert not r["telegram_authorized"]
    assert r["half_time_certified"] is False


def test_reject_wrong_date_and_nonfinal():
    r=frozen()
    r["kickoff_utc"]="2026-10-28T23:31:00Z"
    assert not compare([r],event(),"0"*64)[0]
    p=event()
    p["events"][0]["competitions"][0]["status"]["type"]["completed"]=False
    assert not compare([frozen()],p,"0"*64)[0]
    p=event()
    p["events"][0]["competitions"][0]["status"]["period"]=3
    assert not compare([frozen()],p,"0"*64)[0]


def test_reject_ambiguous_duplicate_result():
    p=event()
    p["events"].append(p["events"][0].copy())
    assert not compare([frozen()],p,"0"*64)[0]


def test_mls_historical_public_response_is_one_call():
    data=json.dumps(event()).encode()
    calls=[]
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*a): return None
        def read(self,maxlen): return data
    def opener(req,timeout):
        calls.append(req.full_url)
        return Response()
    report,raw=run([frozen()],opener=opener)
    assert report["exact_final_matches"]==1
    assert report["network_calls"]==1
    assert len(raw)==1
    assert report["provider_events_seen"]["20261028"]==1
    assert report["real_money"]=="BLOCKED"
    assert report["canonical_ledger_appends"]==0
    assert calls[0].endswith("dates=20261028")



def test_only_explicitly_verified_mls_team_aliases_are_allowed():
    assert club("D.C. United")==club("DC United")
    assert club("Red Bull New York")==club("New York Red Bulls")
    assert club("DC Liverpool")!=club("D.C. United")
    assert club("New York City FC")!=club("New York Red Bulls")
