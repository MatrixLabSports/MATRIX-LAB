"""Read-only API-Football plan probe. Never certifies fixtures, odds, or signals."""
import argparse
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATUS_URL = "https://v3.football.api-sports.io/status"

def probe(key, opener=urllib.request.urlopen):
    out = {"schema":"MATRIX_FOOTBALL_FREE_PLAN_PROBE_V1",
           "checked_at_utc":datetime.now(timezone.utc).isoformat(),
           "provider":"api_football", "endpoint":"status",
           "plan_verified":False,"current_season_coverage_verified":False,
           "candidate_production_authorized":False,"signal_emission_authorized":False,
           "real_money":"BLOCKED"}
    if not key:
        out["status"]="MISSING_KEY"
        return out
    try:
        req=urllib.request.Request(STATUS_URL,headers={"x-apisports-key":key,"Accept":"application/json"})
        with opener(req,timeout=15) as response:
            out["http_status"]=response.status
            raw=json.loads(response.read(250000).decode("utf-8"))
        errors=raw.get("errors")
        account=(raw.get("response") or {}).get("subscription") or {}
        requests=(raw.get("response") or {}).get("requests") or {}
        out["daily_limit"]=requests.get("limit_day")
        out["daily_current"]=requests.get("current")
        out["plan_name"]=account.get("plan")
        if response.status==200 and not errors and account.get("plan"):
            out["plan_verified"]=True
            out["status"]="PLAN_IDENTIFIED_COVERAGE_UNVERIFIED"
        else:
            out["status"]="PLAN_NOT_VERIFIED"
    except Exception as exc:
        out["status"]="PROBE_FAILED"
        out["error_type"]=type(exc).__name__
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    a=p.parse_args()
    result=probe(os.environ.get("API_FOOTBALL_KEY",""))
    target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":
    main()
