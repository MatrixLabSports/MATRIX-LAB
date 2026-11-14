"""Bounded TheSportsDB public football fixture probe: source research only.

One explicitly authorized public HTTP call; never models, odds or bookmaker
markets. Redacted evidence remains on failure, including HTTP 401/403/429.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import date,datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError

def classify(data: dict, day: str) -> dict:
    events=data.get("events") if isinstance(data,dict) else None
    if not isinstance(events,list):
        return {"status":"NO_USABLE_EVENT_LIST_FAIL_CLOSED","returned_count":0,"events":[]}
    rows=[]
    for e in events[:3]:
        if not isinstance(e,dict):continue
        rows.append({"provider_event_id":str(e.get("idEvent") or ""),
            "date":str(e.get("dateEvent") or ""),
            "home":str(e.get("strHomeTeam") or ""),
            "away":str(e.get("strAwayTeam") or ""),
            "league":str(e.get("strLeague") or "")})
    return {"status":"PARTIAL_SAMPLE_ONLY_NOT_WORLD_INVENTORY",
        "returned_count":len(rows),"events":rows}

def strict_daily_fixture_rows(data:dict,day:str)->list[dict]:
    """Source identification only; do not promote unnamed/incomplete matches."""
    rows=data.get("events") if isinstance(data,dict) else None
    valid=[]
    for item in rows if isinstance(rows,list) else []:
        if not isinstance(item,dict):continue
        sid=str(item.get("idEvent") or "")
        league=str(item.get("strLeague") or "").strip()
        home=str(item.get("strHomeTeam") or "").strip()
        away=str(item.get("strAwayTeam") or "").strip()
        if (sid.isdigit() and item.get("dateEvent")==day and league
                and home and away and home.casefold()!=away.casefold()):
            valid.append({"id":sid,"date":day,"league":league})
    return valid

def one_call(day:str,opener=urlopen,clock=None)->dict:
    date.fromisoformat(day)
    endpoint="https://www.thesportsdb.com/api/v1/json/123/eventsday.php?"+urlencode(
        {"d":day,"s":"Soccer"})
    result={"schema":"MATRIX_FOOTBALL_PUBLIC_FREE_PROBE_V2",
        "provider":"thesportsdb","date":day,
        "checked_at_utc":(clock or datetime.now(timezone.utc)).isoformat(),
        "network_calls":1,"provider_free_event_cap":3,
        "http_status":None,"response_bytes":None,"response_sha256":None,
        "current_day_fixture_ids_verified":0,"current_day_sample_ids":[],
        "worldwide_inventory_complete":False,
        "canonical_candidate_generation_authorized":False,
        "signal_generation_authorized":False,
        "production_feature_equivalence_certified":False,
        "real_money":"BLOCKED","automatic_wagering":False}
    try:
        with opener(Request(endpoint,headers={
            "User-Agent":"MATRIX-Research-ReadOnly/1.0"}),timeout=15) as response:
            result["http_status"]=int(response.status)
            body=response.read(250001)
        if len(body)>250000:
            raise ValueError("OVERSIZE_PROVIDER_RESPONSE")
        result["response_bytes"]=len(body)
        result["response_sha256"]=hashlib.sha256(body).hexdigest()
        data=json.loads(body)
        if result["http_status"]!=200:
            result["status"]="PROVIDER_HTTP_"+str(result["http_status"])
        else:
            visible=strict_daily_fixture_rows(data,day)
            result["current_day_fixture_ids_verified"]=len(visible)
            result["current_day_sample_ids"]=[x["id"] for x in visible[:3]]
            result["status"]=("PUBLIC_DAILY_FIXTURE_IDENTITIES_VERIFIED"
                              if visible else "NO_VERIFIABLE_CURRENT_DAY_FIXTURES")
    except HTTPError as exc:
        result["http_status"]=exc.code
        result["status"]="PROVIDER_HTTP_"+str(exc.code)
    except (URLError,TimeoutError,ValueError,UnicodeError) as exc:
        result["status"]="PUBLIC_PROBE_BLOCK_"+type(exc).__name__
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--date",required=True)
    parser.add_argument("--allow-one-public-call",action="store_true")
    parser.add_argument("--out",type=Path,default=Path(
        "evidence/governance/MATRIX_FOOTBALL_PUBLIC_FREE_PROBE_LAST.json"))
    args=parser.parse_args()
    date.fromisoformat(args.date)
    if not args.allow_one_public_call:
        raise SystemExit("EXPLICIT_PUBLIC_PROBE_OPT_IN_REQUIRED")
    result=one_call(args.date)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,
        sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))

if __name__=="__main__":
    main()
