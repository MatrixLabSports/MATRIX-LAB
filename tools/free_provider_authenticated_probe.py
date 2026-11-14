from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

OUT = Path("evidence/governance/MATRIX_FREE_API_AUTHENTICATED_PROBE_LAST.json")
TIMEOUT = 15

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def get_json(url: str, headers: dict[str, str],
             params: dict[str, Any] | None = None,
             session=None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Never persist or log tokens, response bodies, or sensitive URLs."""
    get=(session or requests).get
    response=get(url,headers=headers,params=params or {},timeout=TIMEOUT)
    body=bytes(response.content[:250001])
    if len(body)>250000:
        raise ValueError("PROVIDER_RESPONSE_OVERSIZE")
    meta={"http_status":int(response.status_code),
          "response_bytes":len(body),
          "response_sha256":sha256_bytes(body),
          "content_type":response.headers.get("content-type")}
    try: parsed=response.json()
    except (ValueError,TypeError): parsed={"_non_json":True}
    if not isinstance(parsed,dict):parsed={"_invalid_shape":True}
    return parsed,meta

def single_provider(provider_id:str,key:str,url:str,header:str,expected_list:str,
                    params=None,session=None)->dict:
    if not key:
        return {"status":"KEY_NOT_CONFIGURED","authenticated":False,
                "data_verified":False,"calls":0,"token_redacted":True}
    try:
        data,meta=get_json(url,{header:key},params,session)
        rows=data.get(expected_list)
        ok=meta["http_status"]==200 and isinstance(rows,list) and len(rows)>0
        reason=("HTTP_200_WITH_NONEMPTY_VERIFIED_LIST" if ok else
                "HTTP_"+str(meta["http_status"]) if meta["http_status"]!=200 else
                "EMPTY_OR_INVALID_PROVIDER_LIST")
        return {"status":reason,"authenticated":ok,
                "data_verified":ok,"calls":1,"response":meta,
                "returned_count":len(rows) if isinstance(rows,list) else None,
                "token_redacted":True}
    except (requests.RequestException,ValueError,TimeoutError) as exc:
        return {"status":"NETWORK_OR_RESPONSE_BLOCK_"+type(exc).__name__,
                "authenticated":False,"data_verified":False,"calls":1,
                "token_redacted":True}

def football_daily_fixture_probe(key:str,day:str,session=None)->dict:
    """One current-day read-only request; no model, odds or score ingestion."""
    if not key:
        return {"status":"KEY_NOT_CONFIGURED","verified":False,"calls":0}
    try:
        data,meta=get_json("https://api.football-data.org/v4/matches",
            {"X-Auth-Token":key},params={"dateFrom":day,"dateTo":day},
            session=session)
        matches=data.get("matches")
        verified=[]
        for row in matches if isinstance(matches,list) else []:
            if not isinstance(row,dict):continue
            utc=row.get("utcDate")
            competition=row.get("competition")
            fixture_id=row.get("id")
            home=row.get("homeTeam");away=row.get("awayTeam")
            if (type(fixture_id) is int and isinstance(utc,str)
                and utc[:10]==day and utc.endswith("Z")
                and isinstance(competition,dict) and type(competition.get("id")) is int
                and isinstance(home,dict) and isinstance(away,dict)
                and (home.get("name") or home.get("shortName"))
                and (away.get("name") or away.get("shortName"))):
                verified.append({"id":fixture_id,"utcDate":utc,
                                 "competition_id":competition["id"]})
        good=meta["http_status"]==200 and len(verified)>0
        return {"status":"CURRENT_DAY_FIXTURE_IDENTITIES_VERIFIED" if good
                   else "CURRENT_DAY_FIXTURES_EMPTY_OR_UNVERIFIED",
                "verified":good,"calls":1,"day":day,
                "candidate_count":len(verified),"response":meta,
                "sample_ids":[x["id"] for x in verified[:5]],
                "no_predictions_or_results_imported":True}
    except (requests.RequestException,ValueError,TimeoutError) as exc:
        return {"status":"FIXTURE_QUERY_BLOCK_"+type(exc).__name__,
                "verified":False,"calls":1,"day":day}

def football_competition_window_probe(key:str,start:str,end:str,session=None)->dict:
    """At most one PL current-week source query; provider scope may deny it."""
    try:
        data,meta=get_json("https://api.football-data.org/v4/competitions/PL/matches",
            {"X-Auth-Token":key},
            params={"dateFrom":start,"dateTo":end},session=session)
        rows=data.get("matches")
        valid=[]
        seen=set()
        for row in rows if isinstance(rows,list) else []:
            if not isinstance(row,dict):continue
            mid=row.get("id");kickoff=row.get("utcDate")
            comp=row.get("competition") or {}
            home=row.get("homeTeam") or {};away=row.get("awayTeam") or {}
            name_home=str(home.get("name") or home.get("shortName") or "").strip() if isinstance(home,dict) else ""
            name_away=str(away.get("name") or away.get("shortName") or "").strip() if isinstance(away,dict) else ""
            if (type(mid) is int and isinstance(kickoff,str)
                and start<=kickoff[:10]<=end and kickoff.endswith("Z")
                and isinstance(comp,dict) and
                (comp.get("code")=="PL" or comp.get("id")==2021)
                and name_home and name_away and name_home.casefold()!=name_away.casefold()
                and mid not in seen):
                seen.add(mid)
                valid.append({"provider_fixture_id":mid,"kickoff_utc":kickoff,
                              "competition_id":comp.get("id"),
                              "competition_code":comp.get("code"),
                              "home":name_home[:120],"away":name_away[:120]})
        good=meta["http_status"]==200 and bool(valid)
        return {"status":"CURRENT_WEEK_PL_FIXTURES_VERIFIED" if good
                else "PL_WEEK_ENDPOINT_NO_VERIFIABLE_FIXTURES",
                "verified":good,"calls":1,"start":start,"end":end,
                "match_count":len(valid),
                "sample_ids":[x["provider_fixture_id"] for x in valid[:5]],
                "source_fixtures_research_only":valid[:25],
                "response":meta,"model_admission_authorized":False,
                "source_name_crossmatch_certified":False,
                "historic_provider_id_equivalence_certified":False}
    except (requests.RequestException,ValueError,TimeoutError) as exc:
        return {"status":"PL_WEEK_QUERY_BLOCK_"+type(exc).__name__,
                "verified":False,"calls":1,"start":start,"end":end}

def probe(football_key:str,tennis_key:str, *, tennis_opt_in:bool=False,
          session=None, now=None)->dict:
    football=single_provider("football_data_org",football_key,
        "https://api.football-data.org/v4/competitions","X-Auth-Token",
        "competitions",session=session)
    clock=now or datetime.now(timezone.utc)
    day=clock.astimezone(timezone.utc).date().isoformat()
    fixtures=(football_daily_fixture_probe(football_key,day,session=session)
              if football["data_verified"] else
              {"status":"FOOTBALL_CATALOG_NOT_VERIFIED_NO_QUERY",
               "verified":False,"calls":0,"day":day})
    # A single matchless day can coincide with an international break.
    # One more bounded, explicitly named competition query verifies whether
    # current fixtures are available; it never grants model admission.
    horizon={"status":"NOT_NEEDED_OR_CATALOG_NOT_VERIFIED",
             "verified":False,"calls":0}
    if football["data_verified"] and not fixtures["verified"]:
        next_week=(clock.astimezone(timezone.utc).date()+timedelta(days=7)).isoformat()
        horizon=football_competition_window_probe(football_key,day,next_week,
                                                   session=session)
    # LiveTennisAPI's free entitlement has NOT been established. No speculative
    # consumption of a plan, including usage endpoint, without explicit opt-in.
    tennis=(single_provider("live_tennis_api",tennis_key,
        "https://api.livetennisapi.com/api/public/v1/matches",
        "X-API-Key","data",params={"status":"upcoming","limit":5},
        session=session) if tennis_opt_in else
        {"status":"ENTITLEMENT_NOT_ATTESTED_NO_REQUEST",
         "authenticated":False,"data_verified":False,
         "calls":0,"token_redacted":True})
    result={"schema":"MATRIX_FREE_API_INDEPENDENT_PROBE_V2",
        "generated_at_utc":(now or datetime.now(timezone.utc)).isoformat(),
        "providers":{"football_data_org":football,"live_tennis_api":tennis},
        "football_current_day_fixture_proof":fixtures,
        "football_named_competition_week_proof":horizon,
        "network_calls":football["calls"]+fixtures["calls"]+horizon["calls"]+tennis["calls"],
        "live_tennis_opt_in":tennis_opt_in,
        "status":"PARTIAL_VERIFIED" if any(p["data_verified"]
                      for p in (football,tennis)) else "NO_VERIFIED_LIVE_PROVIDER",
        "promotion_gate":{"automatic_model_feed":False,
                          "requires_independent_coverage_identity_and_pit_certification":True,
                          "production_feed_authorized":False},
        "protections":{"secrets_persisted":False,"secrets_echoed":False,
                       "paid_api_subscription_authorized":False,
                       "real_money":"BLOCKED","automatic_wagering":False}}
    return result

def main():
    report=probe(os.getenv("FOOTBALL_DATA_ORG_KEY","").strip(),
                 os.getenv("LIVE_TENNIS_API_KEY","").strip(),
                 tennis_opt_in=os.getenv("MATRIX_LIVE_TENNIS_PROBE_OPT_IN")=="true")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"network_calls":report["network_calls"],
      "providers":{k:v["status"] for k,v in report["providers"].items()},
      "real_money":"BLOCKED","production_feed_authorized":False},sort_keys=True))

if __name__=="__main__":main()
