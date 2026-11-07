from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from tools.cor0203_rapidapi_tennis_discovery import RapidApiTennisClient
from tools.tennis_world_inventory_rapidapi import build_world_inventory

BOGOTA=ZoneInfo("America/Bogota")


def _rapid_tournament_key(e:Mapping[str,Any])->tuple[str,str,str]:
    return (
        str(e.get("circuit_family") or "UNKNOWN"),
        str(e.get("circuit_detail") or "UNKNOWN"),
        str(e.get("tournament_name") or "UNKNOWN"),
    )


def run(target:date,out:Path)->dict[str,Any]:
    rapid_key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    if not rapid_key:
        raise ValueError("RAPIDAPI_TENNIS_KEY_NOT_CONFIGURED")

    client=RapidApiTennisClient(rapid_key)
    rapid=build_world_inventory(client=client,target_date_bogota=target)
    events=list(rapid.get("events") or [])

    tournaments=defaultdict(lambda:{"match_count":0,"singles":0,"doubles":0,"unknown_format":0})
    for e in events:
        rec=tournaments[_rapid_tournament_key(e)]
        rec["match_count"]+=1
        fmt=str(e.get("event_format") or "UNKNOWN")
        if fmt=="SINGLES":
            rec["singles"]+=1
        elif fmt=="DOUBLES":
            rec["doubles"]+=1
        else:
            rec["unknown_format"]+=1

    tournament_rows=[
        {
            "circuit_family":family,
            "circuit_detail":detail,
            "tournament_name":name,
            **rec,
        }
        for (family,detail,name),rec in tournaments.items()
    ]
    tournament_rows.sort(key=lambda r:(r["circuit_family"],r["circuit_detail"],r["tournament_name"]))

    family_counts=Counter(str(e.get("circuit_family") or "UNKNOWN") for e in events)
    detail_counts=Counter(str(e.get("circuit_detail") or "UNKNOWN") for e in events)
    format_counts=Counter(str(e.get("event_format") or "UNKNOWN") for e in events)

    provider_complete=bool(rapid.get("provider_inventory_complete"))
    result={
        "schema":"MATRIX_TENNIS_WORLD_EXACT_DAY_PRIMARY_OPEN_RECONCILIATION_V2",
        "target_date_bogota":target.isoformat(),
        "window_bogota":{
            "start":datetime.combine(target,datetime.min.time(),tzinfo=BOGOTA).isoformat(),
            "end":datetime.combine(target,datetime.max.time().replace(microsecond=0),tzinfo=BOGOTA).isoformat(),
        },
        "source_architecture":{
            "paid_primary":"rapidapi_tennis",
            "required_open_calendar_reconciliation":["SofaScore","Flashscore"],
            "api_tennis":{
                "status":"RETIRED_COST_UTILITY_DECISION",
                "subscription":"EXPIRED_NOT_RENEWED",
                "attempted":False,
                "required":False,
            },
            "two_paid_sources_required":False,
        },
        "primary_world_inventory":{
            "provider":"rapidapi_tennis",
            "status":rapid.get("status"),
            "provider_inventory_complete":provider_complete,
            "world_inventory_complete":False,
            "unique_match_count":len(events),
            "network_calls":client.request_count,
            "events_by_family":dict(family_counts),
            "events_by_detail":dict(detail_counts),
            "events_by_format":dict(format_counts),
            "tournament_count":len(tournament_rows),
            "tournaments":tournament_rows,
        },
        "primary_worldwide_registered_match_count":len(events),
        "authoritative_count_policy":"SOFASCORE_FIRST_FLASHSCORE_SECOND_RAPIDAPI_STRUCTURED; NO_FORCED_COUNT_EQUALITY",
        "open_reconciliation_required":True,
        "automatic_model_feed":False,
        "metrics_opened":False,
        "outcomes_read":0,
        "odds_used":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "world_inventory_complete":False,
        "world_complete_gate":"OPEN_SOURCE_CALENDAR_RECONCILIATION_REQUIRED",
        "status":"PASS_PRIMARY_PAID_CAPTURE_OPEN_RECONCILIATION_REQUIRED" if provider_complete else "PARTIAL",
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result["status"],
        "target_date_bogota":result["target_date_bogota"],
        "primary_worldwide_registered_match_count":len(events),
        "primary_tournament_count":len(tournament_rows),
        "rapidapi_calls":client.request_count,
        "api_tennis_status":"RETIRED_COST_UTILITY_DECISION",
        "real_money":"BLOCKED",
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
