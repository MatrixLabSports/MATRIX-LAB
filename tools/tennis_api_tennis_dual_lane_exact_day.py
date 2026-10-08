from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from tools.cor0203_api_tennis_discovery import (
    ApiTennisDiscoveryClient,
    ApiTennisDiscoveryError,
    CHALLENGER_MEN_SINGLES_KEY,
    CHALLENGER_MEN_SINGLES_NAME,
    _result_list,
    _draw_surface,
)

BOGOTA=ZoneInfo("America/Bogota")

def _norm(v: object) -> str:
    s=unicodedata.normalize("NFKD",str(v or ""))
    s="".join(ch for ch in s if not unicodedata.combining(ch)).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+"," ",s).split())

def _sha(v: Any) -> str:
    return hashlib.sha256(
        json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    ).hexdigest()

def _parse_start(row: Mapping[str,Any]) -> datetime:
    day=str(row.get("event_date") or "").strip()
    clock=str(row.get("event_time") or "").strip()
    if not day or not clock:
        raise ValueError("START_MISSING")
    return datetime.fromisoformat(f"{day}T{clock}:00+00:00").astimezone(timezone.utc)

def _player_key(v: object) -> str | None:
    s=str(v or "").strip()
    return s if s.isdigit() and int(s)>0 else None

def fetch(target: date, out: Path) -> dict[str,Any]:
    key=os.environ.get("API_TENNIS_KEY","").strip()
    if not key:
        raise ValueError("API_TENNIS_KEY_NOT_CONFIGURED")
    client=ApiTennisDiscoveryClient(key)

    rows=[]
    for qday in (target,target+timedelta(days=1)):
        payload=client._post("get_fixtures",{
            "date_start":qday.isoformat(),
            "date_stop":qday.isoformat(),
            "event_type_key":CHALLENGER_MEN_SINGLES_KEY,
            "timezone":"UTC",
        })
        rows.extend(_result_list(payload))

    selected=[]
    tournaments={}
    malformed=[]
    for row in rows:
        if str(row.get("event_type_type") or "").strip()!=CHALLENGER_MEN_SINGLES_NAME:
            continue
        try:
            start=_parse_start(row)
        except Exception as e:
            malformed.append({"event_key":row.get("event_key"),"reason":type(e).__name__})
            continue
        local=start.astimezone(BOGOTA)
        if local.date()!=target:
            continue
        tk=str(row.get("tournament_key") or "").strip()
        season=str(row.get("tournament_season") or "").strip()
        if tk and re.fullmatch(r"\d{4}",season):
            tournaments[tk]=season
        selected.append((row,start,local))

    draw={}
    for tk,season in sorted(tournaments.items()):
        try:
            draw[tk]=client.draw(tk,season)
        except ApiTennisDiscoveryError as e:
            draw[tk]={"_error":type(e).__name__+":"+str(e)[:200]}

    events=[]
    for row,start,local in selected:
        tk=str(row.get("tournament_key") or "").strip()
        surface,draw_source=_draw_surface(draw.get(tk) or {})
        p1=str(row.get("event_first_player") or "").strip()
        p2=str(row.get("event_second_player") or "").strip()
        p1k=_player_key(row.get("first_player_key"))
        p2k=_player_key(row.get("second_player_key"))
        ek=str(row.get("event_key") or "").strip() or None
        blockers=[]
        if not ek: blockers.append("EVENT_KEY_INVALID")
        if not p1 or not p2 or not p1k or not p2k or p1k==p2k:
            blockers.append("PLAYER_IDENTITY_NOT_FIXED")
        if not surface:
            blockers.append("DRAW_SURFACE_MISSING")
        family=None
        st=str(surface or "").strip().upper()
        if st in {"HARD","I.HARD","INDOOR HARD","INDOOR_HARD"}:
            family="HARD"
        elif st=="CLAY":
            family="CLAY"
        elif st=="GRASS":
            family="GRASS"
        elif surface:
            family="OTHER"
        events.append({
            "source_provider":"api_tennis",
            "source_event_id":f"api-tennis:event:{ek}" if ek else None,
            "event_key":ek,
            "tournament_key":tk or None,
            "tournament_name":str(row.get("tournament_name") or "").strip(),
            "round":str(row.get("tournament_round") or "").strip(),
            "event_start_utc":start.isoformat(),
            "event_start_bogota":local.isoformat(),
            "player1":{"id":f"api-tennis:player:{p1k}" if p1k else None,"name":p1},
            "player2":{"id":f"api-tennis:player:{p2k}" if p2k else None,"name":p2},
            "event_format":"SINGLES",
            "surface_raw":surface,
            "surface_family":family,
            "draw_source":draw_source,
            "status":str(row.get("event_status") or "").strip(),
            "blockers":blockers,
            "source_snapshot_sha256":_sha(row),
        })

    payload={
        "schema":"MATRIX_API_TENNIS_CHALLENGER_MEN_SINGLES_EXACT_DAY_V1",
        "target_date_bogota":target.isoformat(),
        "provider":"api_tennis",
        "event_type_key":CHALLENGER_MEN_SINGLES_KEY,
        "event_type_name":CHALLENGER_MEN_SINGLES_NAME,
        "network_calls":client.request_count,
        "fixture_rows_queried":len(rows),
        "selected_exact_bogota_day":len(events),
        "tournaments_seen":len(tournaments),
        "surface_counts":{
            k:sum(1 for e in events if e["surface_family"]==k)
            for k in ("HARD","CLAY","GRASS","OTHER",None)
        },
        "events":events,
        "malformed":malformed,
        "automatic_model_feed":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS"
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":"PASS",
        "selected":len(events),
        "surface_counts":payload["surface_counts"],
        "network_calls":client.request_count
    },sort_keys=True))
    return payload

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--target-date-bogota",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    fetch(date.fromisoformat(a.target_date_bogota),Path(a.out))

if __name__=="__main__":
    main()
