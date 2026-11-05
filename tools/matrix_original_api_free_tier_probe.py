"""MATRIX: bounded proof of original API-Football free-tier continuity.

One quota-free /status call and at most two league-coverage requests per
invocation. Never logs credentials, account identity, raw private response,
prices, or betting instructions. Diagnostic only; original p_matrix frozen.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://v3.football.api-sports.io"
SOURCE = "API_FOOTBALL_DIRECT"
MAX_BODY = 1_500_000
LEAGUES = (("39", "PREMIER_LEAGUE"), ("239", "COLOMBIA_PRIMERA_A"))
OUT = Path("evidence/football_world_inventory/MATRIX_ORIGINAL_API_FREE_TIER_CAPABILITY_LAST.json")

def _response(url: str, key: str, *, opener=urlopen) -> tuple[int, dict]:
    req=Request(url,headers={"x-apisports-key":key},method="GET")
    with opener(req,timeout=20) as handle:
        status=int(handle.status)
        body=handle.read(MAX_BODY+1)
    if len(body)>MAX_BODY:
        raise ValueError("PROVIDER_RESPONSE_TOO_LARGE")
    payload=json.loads(body)
    if not isinstance(payload,dict):
        raise ValueError("PROVIDER_RESPONSE_NOT_OBJECT")
    return status,payload

def _provider_errors(payload:dict)->bool:
    errors=payload.get("errors")
    return bool(errors) and errors not in ({},[])

def _active_coverage(payload:dict, league_id:str, year:int)->dict:
    if _provider_errors(payload):
        return {"status":"PROVIDER_APPLICATION_ERROR","season_found":False,
                "access_verified":False}
    rows=payload.get("response")
    if not isinstance(rows,list):
        return {"status":"MALFORMED_RESPONSE","season_found":False,
                "access_verified":False}
    matches=[x for x in rows if isinstance(x,dict) and
             str((x.get("league") or {}).get("id"))==league_id]
    season_rows=[s for x in matches for s in x.get("seasons",[])
                 if isinstance(s,dict) and s.get("year")==year]
    if len(matches)!=1 or len(season_rows)!=1:
        return {"status":"NO_UNIQUE_LEAGUE_AND_SEASON_COVERAGE",
                "season_found":False,"access_verified":False}
    coverage=season_rows[0].get("coverage")
    features=(coverage or {}).get("fixtures") or {}
    return {"status":"AUTHENTIC_LEAGUE_SEASON_RESPONSE",
            "season_found":True,"access_verified":True,
            "coverage_flags":{"fixtures_events":features.get("events"),
                "fixtures_lineups":features.get("lineups"),
                "fixtures_statistics":features.get("statistics_fixtures"),
                "standings":(coverage or {}).get("standings")},
            "feature_flags_do_not_prove_same_PIT_history":True}

def probe(key:str, *, opener=urlopen, checked_at=None)->dict:
    checked_at=checked_at or datetime.now(timezone.utc)
    out={"schema":"MATRIX_ORIGINAL_API_FREE_TIER_CAPABILITY_V1",
         "checked_at_utc":checked_at.astimezone(timezone.utc).isoformat(),
         "provider":SOURCE,"status":"BLOCKED_NO_DIRECT_CREDENTIAL_CONFIGURED",
         "http_status_calls":0,"quota_consuming_calls":0,"max_quota_calls":2,
         "two_league_coverage":{}, "status_probe_quota_free_per_provider_docs":True,
         "all_six_leagues_verified":False,
         "original_historical_parity_verified":False,
         "original_feature_PIT_captured":False,
         "original_p_matrix_promoted":False,
         "telegram_signal_authorized":False,
         "automatic_wagering":False,"real_money":"BLOCKED"}
    if not key.strip():
        return out
    try:
        out["http_status_calls"]=1
        code,payload=_response(BASE+"/status",key,opener=opener)
        if code!=200 or _provider_errors(payload):
            out["status"]="BLOCKED_PROVIDER_STATUS_AUTH_OR_QUOTA_ERROR"
            return out
        response=payload.get("response") or {}
        if not isinstance(response,dict):
            out["status"]="BLOCKED_MALFORMED_ACCOUNT_STATUS"
            return out
        subscription=response.get("subscription") or {}
        requests=response.get("requests") or {}
        if not isinstance(subscription,dict) or not isinstance(requests,dict):
            out["status"]="BLOCKED_MALFORMED_ACCOUNT_STATUS"
            return out
        limit=requests.get("limit_day")
        used=requests.get("current")
        if type(limit) is not int or type(used) is not int or limit<0 or used<0:
            out["status"]="BLOCKED_PROVIDER_QUOTA_NOT_NUMERIC"
            return out
        remaining=max(0,limit-used)
        out["account_status"]={"subscription_plan":str(subscription.get("plan") or "UNKNOWN")[:64],
          "subscription_active":subscription.get("active") is True,
          "daily_limit":limit,"daily_consumed":used,"daily_remaining":remaining}
        if subscription.get("active") is not True:
            out["status"]="BLOCKED_DIRECT_SUBSCRIPTION_NOT_ACTIVE"
            return out
        if remaining<2:
            out["status"]="BLOCKED_INSUFFICIENT_QUOTA_FOR_TWO_LEAGUES"
            return out
        for lid,name in LEAGUES:
            out["quota_consuming_calls"]+=1
            code,body=_response(BASE+"/leagues?id="+lid+"&season=2026",key,opener=opener)
            out["two_league_coverage"][lid]={"league_name":name,
                "http_status":code,**_active_coverage(body,lid,2026)}
            if code!=200 or not out["two_league_coverage"][lid]["access_verified"]:
                out["status"]="BLOCKED_LEAGUE_ACCESS_OR_COVERAGE_INCOMPLETE"
                return out
        out["status"]="PASS_TWO_LEAGUE_ACCESS_ONLY_FULL_SIX_LEAGUE_FEATURE_PARITY_NOT_CERTIFIED"
    except HTTPError as exc:
        out["status"]="BLOCKED_HTTP_"+str(exc.code)
    except (TimeoutError,URLError,OSError,ValueError,TypeError,
            json.JSONDecodeError) as exc:
        out["status"]="BLOCKED_TRANSPORT_OR_RESPONSE_"+type(exc).__name__
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=OUT)
    args=p.parse_args()
    if any(x in args.out.parts for x in ("daily_prematch_reports","tennis_signals","telegram","governance")):
        raise SystemExit("DIAGNOSTIC_CANNOT_WRITE_PRODUCTION")
    # Separate direct API-SPORTS key; RapidAPI credentials use a different
    # subscription/host and are NOT accepted as equivalent.
    key=(os.environ.get("API_FOOTBALL_DIRECT_KEY") or
         os.environ.get("API_FOOTBALL_KEY") or
         os.environ.get("API_FOOTBALL_API_KEY") or "")
    result=probe(key)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+"\n",
                        encoding="utf-8")
    print(json.dumps({"status":result["status"],
      "http_status_calls":result["http_status_calls"],
      "quota_consuming_calls":result["quota_consuming_calls"],
      "two_league_coverage":result["two_league_coverage"],
      "original_p_matrix_promoted":False,
      "telegram_signal_authorized":False},sort_keys=True))

if __name__=="__main__":
    main()
