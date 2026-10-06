from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE="https://api.livetennisapi.com/api/public/v1"
OUT=Path("evidence/live_tennis_lab/2026-10-06/MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json")
POINT_CODE={"0":0,"15":1,"30":2,"40":3,"AD":4,"A":4}


def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def get_json(path:str,key:str,params:dict[str,Any]|None=None):
    r=requests.get(BASE+path,headers={"X-API-Key":key},params=params or {},timeout=20)
    body=bytes(r.content)
    try: payload=r.json()
    except Exception: payload={"_non_json":True}
    return payload,{
      "path":path,"params":params or {},"http_status":r.status_code,
      "response_bytes":len(body),"response_sha256":sha(body)
    }


def pcode(v:Any)->int|None:
    return POINT_CODE.get(str(v or "").strip().upper())


def names(row:dict[str,Any]):
    players=row.get("players") if isinstance(row.get("players"),dict) else {}
    p1=players.get("p1") if isinstance(players.get("p1"),dict) else {}
    p2=players.get("p2") if isinstance(players.get("p2"),dict) else {}
    return (
      str(p1.get("name") or row.get("p1_name") or "").strip(),
      str(p2.get("name") or row.get("p2_name") or "").strip(),
      p1,p2
    )


def state_from_row(row:dict[str,Any],captured_at:str,response_sha:str)->dict[str,Any]|None:
    if row.get("is_doubles") is True:
        return None
    p1_name,p2_name,p1,p2=names(row)
    if not p1_name or not p2_name:
        return None
    score=row.get("score") if isinstance(row.get("score"),dict) else {}
    seq=score.get("sequence")
    sets=score.get("sets")
    games=score.get("games")
    points=score.get("points")
    server=score.get("server")
    if not isinstance(seq,int):
        return None
    if not (isinstance(sets,list) and len(sets)==2):
        return None
    if not (isinstance(games,list) and len(games)==2 and isinstance(games[0],list) and isinstance(games[1],list)):
        return None
    if not (isinstance(points,list) and len(points)==2):
        return None
    g1=[int(x) for x in games[0]]
    g2=[int(x) for x in games[1]]
    idx=min(len(g1),len(g2))-1
    r1=p1.get("ranking") if isinstance(p1,dict) else row.get("p1_ranking")
    r2=p2.get("ranking") if isinstance(p2,dict) else row.get("p2_ranking")
    rank_adv=(int(r2)-int(r1)) if isinstance(r1,int) and isinstance(r2,int) else None
    pc1,pc2=pcode(points[0]),pcode(points[1])
    mid=row.get("id")
    if not isinstance(mid,int):
        return None
    return {
      "state_key":f"live_tennis_api:{mid}:sequence:{seq}",
      "provider":"live_tennis_api",
      "match_id":mid,
      "sequence":seq,
      "captured_at_utc":captured_at,
      "response_sha256":response_sha,
      "tour":row.get("tour"),
      "gender":row.get("gender"),
      "tournament":row.get("tournament"),
      "round":row.get("round"),
      "round_code":row.get("round_code"),
      "surface":row.get("surface"),
      "p1_name":p1_name,"p2_name":p2_name,
      "p1_ranking":r1,"p2_ranking":r2,
      "ranking_advantage_p1":rank_adv,
      "sets_p1":int(sets[0]),"sets_p2":int(sets[1]),
      "set_diff_p1":int(sets[0])-int(sets[1]),
      "games_by_set_p1":g1,"games_by_set_p2":g2,
      "total_game_diff_p1":sum(g1)-sum(g2),
      "current_set_index_zero_based":idx,
      "current_set_game_diff_p1":g1[idx]-g2[idx] if idx>=0 else None,
      "point_p1_raw":str(points[0]),"point_p2_raw":str(points[1]),
      "point_p1_code":pc1,"point_p2_code":pc2,
      "point_diff_p1":pc1-pc2 if pc1 is not None and pc2 is not None else None,
      "server":server,
      "server_is_p1":True if server==1 else False if server==2 else None,
      "is_tiebreak":score.get("is_tiebreak"),
      "age_seconds":score.get("age_seconds"),
      "observed_age_seconds":score.get("observed_age_seconds"),
      "corroborated":score.get("corroborated"),
      "sources_count":score.get("sources_count"),
      "stale":score.get("stale"),
      "origin":score.get("origin"),
      "quality_state_valid":(
        row.get("status")=="live" and server in {1,2}
        and score.get("stale") is False and score.get("origin")=="observed"
      ),
      "p1_match_win":None,
      "settlement_status":"PENDING_FINAL",
      "label_opened":False
    }


def load_existing():
    if not OUT.exists():
        return {}
    try:
        j=json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {x["state_key"]:x for x in j.get("states",[]) if isinstance(x,dict) and x.get("state_key")}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cycles",type=int,default=6)
    ap.add_argument("--interval-seconds",type=int,default=20)
    ap.add_argument("--reserve-calls",type=int,default=20)
    args=ap.parse_args()
    key=os.environ.get("LIVE_TENNIS_API_KEY","").strip()
    if not key:
        raise SystemExit("LIVE_TENNIS_API_KEY_NOT_CONFIGURED")

    usage,umeta=get_json("/usage",key)
    today=usage.get("today") if isinstance(usage,dict) and isinstance(usage.get("today"),dict) else {}
    remaining=today.get("remaining_day")
    if not isinstance(remaining,int):
        raise SystemExit("USAGE_REMAINING_UNKNOWN")
    allowed=max(0,remaining-args.reserve_calls)
    cycles=min(args.cycles,allowed)
    if cycles<=0:
        raise SystemExit("DAILY_QUOTA_RESERVE_GATE_BLOCKED")

    existing=load_existing()
    initial=len(existing)
    call_meta=[]
    capture_summaries=[]
    for i in range(cycles):
        captured=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        payload,meta=get_json("/matches",key,{"status":"live","limit":50})
        if meta["http_status"]!=200:
            raise SystemExit(f"LIVE_REQUEST_HTTP_{meta['http_status']}")
        rows=payload.get("data") if isinstance(payload,dict) and isinstance(payload.get("data"),list) else []
        added=0
        singles=0
        for row in rows:
            if not isinstance(row,dict) or row.get("is_doubles") is True:
                continue
            singles+=1
            state=state_from_row(row,captured,meta["response_sha256"])
            if state is None:
                continue
            if state["state_key"] not in existing:
                existing[state["state_key"]]=state
                added+=1
        call_meta.append(meta)
        capture_summaries.append({
          "cycle":i+1,"captured_at_utc":captured,
          "live_rows":len(rows),"singles_rows":singles,"new_unique_states":added
        })
        if i<cycles-1:
            time.sleep(max(1,args.interval_seconds))

    states=sorted(existing.values(),key=lambda x:(x["captured_at_utc"],x["match_id"],x["sequence"]))
    match_ids=sorted({x["match_id"] for x in states})
    payload={
      "schema":"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "model_status":"RESEARCH_ONLY",
      "observation_unit":"UNIQUE_MATCH_SEQUENCE_STATE",
      "quota_guard":{
        "tier":usage.get("tier"),"per_day":(usage.get("limits") or {}).get("per_day"),
        "remaining_before_run":remaining,"reserve_calls":args.reserve_calls,
        "requested_cycles":args.cycles,"executed_cycles":cycles
      },
      "capture_summaries":capture_summaries,
      "network_calls":call_meta,
      "unique_match_count":len(match_ids),
      "unique_state_count":len(states),
      "new_states_this_run":len(states)-initial,
      "states":states,
      "split_rule":"GROUP_BY_MATCH_ID_NO_MATCH_MAY_CROSS_TRAIN_TEST",
      "protections":{
        "prematch_freeze_mutated":False,"outcomes_read_during_live_capture":0,
        "odds_to_probability":False,"silent_imputation":False,"missing_not_zero":True,
        "automatic_wagering":False,"real_money":"BLOCKED","secrets_persisted":False
      }
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
      "status":"PASS","executed_cycles":cycles,
      "unique_match_count":len(match_ids),"unique_state_count":len(states),
      "new_states_this_run":len(states)-initial
    },sort_keys=True))

if __name__=="__main__":
    main()
