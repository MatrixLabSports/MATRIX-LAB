"""Read-only API-Football plan probe. Never certifies fixtures, odds, or signals."""
import argparse
import json
import os
import urllib.request
import urllib.parse
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

def verify_current_fixtures(key, target_date, opener=urllib.request.urlopen):
    """One bounded fixture query, only after a verified free plan; never certifies history or odds."""
    result = {"schema":"MATRIX_FOOTBALL_FREE_FIXTURE_COVERAGE_V1",
              "target_date_bogota":target_date,"fixtures_available":0,
              "fixture_coverage_verified":False,"historical_feature_coverage_verified":False,
              "exact_bookmaker_odds_verified":False,"over25_production_authorized":False,
              "signal_emission_authorized":False,"real_money":"BLOCKED"}
    plan=probe(key,opener)
    result["plan_probe_status"]=plan["status"]
    result["plan_name"]=plan.get("plan_name")
    if not plan["plan_verified"]:
        result["status"]="BLOCKED_UNVERIFIED_PLAN"
        return result
    if "free" not in str(plan.get("plan_name","")).lower():
        result["status"]="BLOCKED_NOT_VERIFIED_FREE_PLAN"
        return result
    try:
        url="https://v3.football.api-sports.io/fixtures?"+urllib.parse.urlencode(
            {"date":target_date,"timezone":"America/Bogota"})
        req=urllib.request.Request(url,headers={"x-apisports-key":key})
        with opener(req,timeout=20) as response:
            payload=json.loads(response.read(2000000).decode("utf-8"))
            result["http_status"]=response.status
        if response.status!=200 or payload.get("errors"):
            result["status"]="BLOCKED_PROVIDER_ERROR"
            return result
        fixtures=payload.get("response") or []
        result["fixtures_available"]=len(fixtures)
        result["fixture_coverage_verified"]=bool(fixtures)
        result["status"]="FIXTURES_PRESENT_HISTORY_AND_ODDS_UNVERIFIED" if fixtures else "NO_CURRENT_FIXTURES"
    except Exception as exc:
        result["status"]="BLOCKED_NETWORK_ERROR"
        result["error_type"]=type(exc).__name__
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    p.add_argument("--target-date",default=None)
    a=p.parse_args()
    key=os.environ.get("API_FOOTBALL_KEY","")
    result=verify_current_fixtures(key,a.target_date) if a.target_date else probe(key)
    target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":
    main()
