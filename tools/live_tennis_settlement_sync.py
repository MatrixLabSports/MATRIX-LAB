from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

BASE="https://api.livetennisapi.com/api/public/v1"


def get_json(path:str,key:str,params:dict[str,Any]|None=None):
    r=requests.get(BASE+path,headers={"X-API-Key":key},params=params or {},timeout=20)
    try: payload=r.json()
    except Exception: payload={"_non_json":True}
    return payload,r.status_code


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ledger",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--max-detail-queries",type=int,default=10)
    ap.add_argument("--reserve-calls",type=int,default=20)
    args=ap.parse_args()

    key=os.environ.get("LIVE_TENNIS_API_KEY","").strip()
    if not key:
        raise SystemExit("LIVE_TENNIS_API_KEY_NOT_CONFIGURED")

    ledger_path=Path(args.ledger)
    ledger=json.loads(ledger_path.read_text(encoding="utf-8"))
    states=ledger.get("states",[]) or []
    match_ids=sorted({x.get("match_id") for x in states if isinstance(x,dict) and isinstance(x.get("match_id"),int)})
    already_settled_ids={
        x.get("match_id") for x in states
        if isinstance(x,dict)
        and isinstance(x.get("match_id"),int)
        and x.get("label_opened") is True
        and x.get("settlement_status")=="FINAL_STANDARD"
        and x.get("p1_match_win") in {0,1}
    }

    usage,code=get_json("/usage",key)
    if code!=200:
        raise SystemExit(f"USAGE_HTTP_{code}")
    remaining=((usage.get("today") or {}).get("remaining_day") if isinstance(usage,dict) else None)
    if not isinstance(remaining,int):
        raise SystemExit("USAGE_REMAINING_UNKNOWN")

    live,code=get_json("/matches",key,{"status":"live","limit":50})
    if code!=200:
        raise SystemExit(f"LIVE_HTTP_{code}")
    live_rows=live.get("data") if isinstance(live,dict) and isinstance(live.get("data"),list) else []
    live_ids={x.get("id") for x in live_rows if isinstance(x,dict) and isinstance(x.get("id"),int)}
    departed=[mid for mid in match_ids if mid not in live_ids and mid not in already_settled_ids]

    budget=max(0,remaining-args.reserve_calls-1)
    query_ids=departed[:min(args.max_detail_queries,budget)]
    settlements=[]
    blocked=[]
    for mid in query_ids:
        detail,code=get_json(f"/matches/{mid}",key)
        if code!=200:
            blocked.append({"match_id":mid,"reason":f"DETAIL_HTTP_{code}"})
            continue
        status=detail.get("status")
        outcome=detail.get("outcome")
        winner=detail.get("winner")
        if status=="completed" and outcome=="completed" and winner in {1,2}:
            settlements.append({
              "match_id":mid,
              "winner":winner,
              "outcome":outcome,
              "status":status,
              "result_version":detail.get("result_version"),
              "result_restated_at":detail.get("result_restated_at"),
              "settled_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            })
        else:
            blocked.append({
              "match_id":mid,
              "reason":"NOT_STANDARD_COMPLETED_RESULT",
              "status":status,
              "outcome":outcome,
              "winner":winner
            })

    settle_index={x["match_id"]:x for x in settlements}
    updated=0
    for row in states:
        if not isinstance(row,dict):
            continue
        s=settle_index.get(row.get("match_id"))
        if not s:
            continue
        row["p1_match_win"]=1 if s["winner"]==1 else 0
        row["settlement_status"]="FINAL_STANDARD"
        row["label_opened"]=True
        row["result_version"]=s.get("result_version")
        updated+=1

    out_payload={
      "schema":"MATRIX_LIVE_TENNIS_SETTLEMENT_SYNC_V0_1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "source_ledger":args.ledger,
      "match_ids_seen":len(match_ids),
      "currently_live_match_ids":sorted(live_ids),
      "already_settled_match_ids":sorted(already_settled_ids),
      "departed_match_ids":departed,
      "queried_match_ids":query_ids,
      "standard_final_settlements":settlements,
      "blocked_or_pending":blocked,
      "labeled_state_rows":updated,
      "protections":{
        "final_only":True,
        "retired_walkover_abandoned_not_silently_labeled":True,
        "prematch_freeze_mutated":False,
        "odds_to_probability":False,
        "real_money":"BLOCKED"
      }
    }
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(out_payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    ledger_path.write_text(json.dumps(ledger,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
      "status":"PASS","departed":len(departed),"queried":len(query_ids),
      "settled_matches":len(settlements),"labeled_state_rows":updated
    },sort_keys=True))

if __name__=="__main__":
    main()
