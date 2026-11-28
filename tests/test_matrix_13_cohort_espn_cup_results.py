import json
from tools.matrix_13_cohort_espn_cup_results import run

def freeze():
    return {"fixture_id":"123","competition_name":"DFB Pokal",
      "kickoff_utc":"2026-10-28T19:30:00Z",
      "freeze_at_utc":"2026-10-25T12:30:00Z",
      "home_team_name":"Bayern München","away_team_name":"1. FC Magdeburg"}

def data():
    return {"events":[{"id":"334","date":"2026-10-28T19:30Z",
        "competitions":[{
        "status":{"period":2,"type":{"name":"STATUS_FULL_TIME","completed":True}},
        "competitors":[
          {"homeAway":"home","score":"3","team":{"displayName":"Bayern München"}},
          {"homeAway":"away","score":"0","team":{"displayName":"1. FC Magdeburg"}},
        ]}]}]}

def test_one_cup_scoreboard_call_never_changes_original_ledger():
    body=json.dumps(data()).encode()
    class Resp:
        status=200
        def __enter__(self):return self
        def __exit__(self,*exc):return None
        def read(self,n):return body
    urls=[]
    def opener(req,timeout):
        urls.append(req.full_url)
        return Resp()
    r,files=run([freeze()],opener=opener)
    assert r["target_count"]==1
    assert r["exact_final_matches"]==1
    assert r["network_calls"]==1
    assert "ger.dfb_pokal" in urls[0]
    assert r["canonical_ledger_appends"]==0
    assert r["real_money"]=="BLOCKED"
    assert r["matched"][0]["espn_fixture_id"]=="334"
    assert len(files)==1

def test_cup_scoreboard_rejects_mismatched_home_team():
    j=data()
    j["events"][0]["competitions"][0]["competitors"][0]["team"]["displayName"]="Bayer Leverkusen"
    body=json.dumps(j).encode()
    class Resp:
        status=200
        def __enter__(self):return self
        def __exit__(self,*exc):return None
        def read(self,n):return body
    report,_=run([freeze()],opener=lambda req,timeout:Resp())
    assert report["exact_final_matches"]==0

def test_no_cups_no_calls():
    r,raw=run([])
    assert r["network_calls"]==0
    assert not raw
