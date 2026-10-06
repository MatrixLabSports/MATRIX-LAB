from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from tools.cor0203_rapidapi_tennis_discovery import RapidApiTennisClient
from tools.tennis_world_inventory_rapidapi import build_world_inventory
from tools.cor0203_api_tennis_discovery import ApiTennisDiscoveryClient, ApiTennisDiscoveryError

BOGOTA=ZoneInfo("America/Bogota")


def _norm(v:object)->str:
    s=unicodedata.normalize("NFKD",str(v or ""))
    s="".join(ch for ch in s if not unicodedata.combining(ch)).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+"," ",s).split())


def _sha(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def _api_rows(payload:Mapping[str,Any])->list[Mapping[str,Any]]:
    r=payload.get("result")
    if not isinstance(r,list):
        raise ValueError("API_TENNIS_RESULT_NOT_LIST")
    return [x for x in r if isinstance(x,Mapping)]


def _api_start_utc(row:Mapping[str,Any])->datetime:
    day=str(row.get("event_date") or "").strip()
    clock=str(row.get("event_time") or "").strip()
    if not day or not clock:
        raise ValueError("API_TENNIS_START_MISSING")
    # Query is explicitly UTC, so provider date/time is UTC.
    return datetime.fromisoformat(f"{day}T{clock}:00+00:00").astimezone(timezone.utc)


def _format_api(row:Mapping[str,Any])->str:
    typ=_norm(row.get("event_type_type"))
    if "double" in typ:
        return "DOUBLES"
    p1=str(row.get("event_first_player") or "")
    p2=str(row.get("event_second_player") or "")
    if "/" in p1 and "/" in p2:
        return "DOUBLES"
    if p1 and p2:
        return "SINGLES"
    return "UNKNOWN"


def _api_event(row:Mapping[str,Any],target:date)->dict[str,Any]|None:
    try:
        start=_api_start_utc(row)
    except Exception:
        return None
    local=start.astimezone(BOGOTA)
    if local.date()!=target:
        return None
    ek=str(row.get("event_key") or "").strip()
    p1=str(row.get("event_first_player") or "").strip()
    p2=str(row.get("event_second_player") or "").strip()
    t=str(row.get("tournament_name") or "").strip()
    typ=str(row.get("event_type_type") or "").strip()
    fmt=_format_api(row)
    return {
        "source_provider":"api_tennis",
        "source_event_id":f"api-tennis:event:{ek}" if ek else None,
        "event_key":ek or None,
        "event_start_utc":start.isoformat(),
        "event_start_bogota":local.isoformat(),
        "tournament_key":str(row.get("tournament_key") or "").strip() or None,
        "tournament_name":t or "UNKNOWN",
        "event_type":typ or "UNKNOWN",
        "event_format":fmt,
        "round":str(row.get("tournament_round") or "").strip() or "UNKNOWN",
        "player1_name":p1,
        "player2_name":p2,
        "status":str(row.get("event_status") or "").strip(),
    }


def _neutral_key(event:Mapping[str,Any])->str|None:
    p1=_norm(event.get("player1_name") or (event.get("player1") or {}).get("name"))
    p2=_norm(event.get("player2_name") or (event.get("player2") or {}).get("name"))
    if not p1 or not p2:
        return None
    try:
        local=datetime.fromisoformat(str(event["event_start_bogota"])).astimezone(BOGOTA)
    except Exception:
        return None
    return _sha({
        "date_bogota":local.date().isoformat(),
        "players":sorted([p1,p2]),
        "format":str(event.get("event_format") or "UNKNOWN").upper(),
    })


def _rapid_tournament_key(e:Mapping[str,Any])->tuple[str,str,str]:
    return (
        str(e.get("circuit_family") or "UNKNOWN"),
        str(e.get("circuit_detail") or "UNKNOWN"),
        str(e.get("tournament_name") or "UNKNOWN"),
    )


def _api_tournament_key(e:Mapping[str,Any])->tuple[str,str]:
    return (str(e.get("event_type") or "UNKNOWN"),str(e.get("tournament_name") or "UNKNOWN"))


def _fetch_api_rows_for_bogota_day(
    api_client: ApiTennisDiscoveryClient,
    target: date,
) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    # A Bogotá calendar day spans portions of two UTC dates. Query each UTC
    # date separately so API-Tennis cannot return one oversized two-day blob.
    for query_day in (target, target + timedelta(days=1)):
        payload = api_client._post(
            "get_fixtures",
            {
                "date_start": query_day.isoformat(),
                "date_stop": query_day.isoformat(),
                "timezone": "UTC",
            },
        )
        rows.extend(_api_rows(payload))
    return rows


def run(target:date,out:Path)->dict[str,Any]:
    rapid_key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    api_key=os.environ.get("API_TENNIS_KEY","").strip()
    if not rapid_key:
        raise ValueError("RAPIDAPI_TENNIS_KEY_NOT_CONFIGURED")
    if not api_key:
        raise ValueError("API_TENNIS_KEY_NOT_CONFIGURED")

    rapid_client=RapidApiTennisClient(rapid_key)
    rapid=build_world_inventory(client=rapid_client,target_date_bogota=target)
    rapid["provider_network_calls"]=rapid_client.request_count
    rapid_events=list(rapid.get("events") or [])

    api_client=ApiTennisDiscoveryClient(api_key)
    # Query the two UTC dates spanning the full Bogotá day in bounded chunks.
    api_all=_fetch_api_rows_for_bogota_day(api_client,target)
    api_events=[]
    seen_api=set()
    malformed=0
    for row in api_all:
        e=_api_event(row,target)
        if e is None:
            try:
                _api_start_utc(row)
            except Exception:
                malformed+=1
            continue
        key=e.get("event_key") or _neutral_key(e) or _sha(e)
        if key in seen_api:
            continue
        seen_api.add(key)
        api_events.append(e)
    api_events.sort(key=lambda x:(x["event_start_utc"],x.get("event_key") or ""))

    rapid_by={}
    for e in rapid_events:
        k=_neutral_key(e)
        if k: rapid_by.setdefault(k,[]).append(e)
    api_by={}
    for e in api_events:
        k=_neutral_key(e)
        if k: api_by.setdefault(k,[]).append(e)

    overlap=sorted(set(rapid_by)&set(api_by))
    rapid_only_keys=sorted(set(rapid_by)-set(api_by))
    api_only_keys=sorted(set(api_by)-set(rapid_by))

    rapid_tournaments=defaultdict(lambda:{"match_count":0,"singles":0,"doubles":0,"unknown_format":0})
    for e in rapid_events:
        key=_rapid_tournament_key(e)
        rec=rapid_tournaments[key]
        rec["match_count"]+=1
        fmt=str(e.get("event_format") or "UNKNOWN")
        if fmt=="SINGLES": rec["singles"]+=1
        elif fmt=="DOUBLES": rec["doubles"]+=1
        else: rec["unknown_format"]+=1

    tournament_rows=[]
    for (family,detail,name),rec in rapid_tournaments.items():
        tournament_rows.append({
            "circuit_family":family,
            "circuit_detail":detail,
            "tournament_name":name,
            **rec,
        })
    tournament_rows.sort(key=lambda r:(r["circuit_family"],r["circuit_detail"],r["tournament_name"]))

    family_counts=Counter(str(e.get("circuit_family") or "UNKNOWN") for e in rapid_events)
    detail_counts=Counter(str(e.get("circuit_detail") or "UNKNOWN") for e in rapid_events)
    format_counts=Counter(str(e.get("event_format") or "UNKNOWN") for e in rapid_events)

    api_tournaments=Counter(_api_tournament_key(e) for e in api_events)

    result={
        "schema":"MATRIX_TENNIS_WORLD_EXACT_DAY_DUAL_AUDIT_V1",
        "target_date_bogota":target.isoformat(),
        "window_bogota":{
            "start":datetime.combine(target,datetime.min.time(),tzinfo=BOGOTA).isoformat(),
            "end":datetime.combine(target,datetime.max.time().replace(microsecond=0),tzinfo=BOGOTA).isoformat(),
        },
        "primary_world_inventory":{
            "provider":"rapidapi_tennis",
            "status":rapid.get("status"),
            "provider_inventory_complete":rapid.get("provider_inventory_complete"),
            "world_inventory_complete":rapid.get("world_inventory_complete"),
            "unique_match_count":len(rapid_events),
            "network_calls":rapid_client.request_count,
            "events_by_family":dict(family_counts),
            "events_by_detail":dict(detail_counts),
            "events_by_format":dict(format_counts),
            "tournament_count":len(tournament_rows),
            "tournaments":tournament_rows,
        },
        "secondary_crosscheck":{
            "provider":"api_tennis",
            "status":"PASS",
            "unique_match_count":len(api_events),
            "network_calls":api_client.request_count,
            "malformed_unplaced_rows":malformed,
            "tournament_count":len(api_tournaments),
            "tournaments":[
                {"event_type":k[0],"tournament_name":k[1],"match_count":v}
                for k,v in sorted(api_tournaments.items())
            ],
        },
        "cross_provider_reconciliation":{
            "neutral_exact_overlap_count":len(overlap),
            "rapidapi_only_neutral_count":len(rapid_only_keys),
            "api_tennis_only_neutral_count":len(api_only_keys),
            "exact_union_count":len(set(rapid_by)|set(api_by)),
            "note":"Exact-neutral reconciliation uses Bogota date + normalized player pair + singles/doubles format. Provider-specific aliases can remain unmatched. No single provider is authorized to define the worldwide denominator.",
        },
        "primary_worldwide_registered_match_count":len(rapid_events),
        "authoritative_count_policy":"MULTI_SOURCE_RECONCILIATION_REQUIRED; PROVIDER_COUNTS_ARE_NOT_WORLD_TRUTH",
        "automatic_model_feed":False,
        "metrics_opened":False,
        "odds_used":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "world_inventory_complete":False,
        "world_complete_gate":"REQUIRES_MULTI_SOURCE_RECONCILIATION",
        "status":"PASS_PROVIDER_CAPTURE_WORLD_UNSEALED" if rapid.get("provider_inventory_complete") else "PARTIAL",
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result["status"],
        "target_date_bogota":result["target_date_bogota"],
        "primary_worldwide_registered_match_count":result["primary_worldwide_registered_match_count"],
        "primary_tournament_count":result["primary_world_inventory"]["tournament_count"],
        "rapidapi_calls":rapid_client.request_count,
        "api_tennis_matches":len(api_events),
        "api_tennis_calls":api_client.request_count,
        "exact_overlap":len(overlap),
        "exact_union":result["cross_provider_reconciliation"]["exact_union_count"],
    },sort_keys=True))
    return result


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--target-date-bogota",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    run(date.fromisoformat(a.target_date_bogota),Path(a.out))


if __name__=="__main__":
    main()
