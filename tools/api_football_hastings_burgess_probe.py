from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE="https://v3.football.api-sports.io"
OUT=Path("evidence/daily_source_counts/2026-10-06/MATRIX_API_FOOTBALL_HASTINGS_BURGESS_PROBE.json")

def norm(s:str)->str:
    return " ".join(s.casefold().replace("fc"," ").split())

def req(session,key,endpoint,params):
    r=session.get(BASE+endpoint,headers={"x-apisports-key":key},params=params,timeout=20)
    b=bytes(r.content)
    meta={"endpoint":endpoint,"params":params,"http_status":r.status_code,"response_bytes":len(b),"response_sha256":hashlib.sha256(b).hexdigest()}
    return (r.json() if r.ok else {"response":[]}),meta

def team_id(rows,name):
    wanted=norm(name)
    vals=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get("team"),dict): continue
        team=row["team"]; n=norm(str(team.get("name") or ""))
        if n==wanted or wanted in n or n in wanted:
            if isinstance(team.get("id"),int): vals.append(team["id"])
    return vals[0] if len(set(vals))==1 else None

def main():
    key=os.environ.get("API_FOOTBALL_KEY","").strip()
    if not key: raise SystemExit("API_FOOTBALL_KEY_NOT_CONFIGURED")
    s=requests.Session(); calls=[]
    hp,m=req(s,key,"/teams",{"search":"Hastings United"}); calls.append(m)
    bp,m=req(s,key,"/teams",{"search":"Burgess Hill Town"}); calls.append(m)
    hid=team_id(hp.get("response") or [],"Hastings United")
    bid=team_id(bp.get("response") or [],"Burgess Hill Town")
    fixture=None
    if hid is not None:
        fp,m=req(s,key,"/fixtures",{"team":hid,"date":"2026-10-06","timezone":"America/Bogota"}); calls.append(m)
        for row in fp.get("response") or []:
            teams=row.get("teams") or {}; h=teams.get("home") or {}; a=teams.get("away") or {}
            if bid is not None and {h.get("id"),a.get("id")}=={hid,bid}:
                fixture=row; break
    payload={
      "schema":"MATRIX_API_FOOTBALL_OFFICIAL_CORRECTED_GAP_PROBE_V1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "match":"Hastings United - Burgess Hill Town",
      "official_schedule_source":"https://www.hastingsunited.com/",
      "official_kickoff_local":"2026-10-06 19:45 Europe/London",
      "home_team_id":hid,"away_team_id":bid,
      "fixture_id":((fixture or {}).get("fixture") or {}).get("id"),
      "provider_fixture":fixture,
      "request_evidence":calls,
      "status":"PROVIDER_FIXTURE_BOUND" if fixture else ("TEAM_IDS_BOUND_FIXTURE_NOT_COVERED" if hid and bid else "TEAM_BINDING_INCOMPLETE"),
      "protections":{"automatic_model_feed":False,"automatic_wagering":False,"real_money":"BLOCKED"}
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":payload["status"],"home_team_id":hid,"away_team_id":bid,"fixture_id":payload["fixture_id"]},sort_keys=True))
if __name__=="__main__": main()
