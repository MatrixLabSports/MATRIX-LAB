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


def persist_blocked_state(*, ledger_path:Path, out_path:Path, ledger:dict[str,Any], match_ids:list[int], already_settled_ids:set[int], status:str, reason:str, remaining:int|None=None)->None:
    payload={
      "schema":"MATRIX_LIVE_TENNIS_SETTLEMENT_SYNC_V0_1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "source_ledger":str(ledger_path),
      "status":status,
      "blocking_reason":reason,
      "quota_remaining":remaining,
      "match_ids_seen":len(match_ids),
      "currently_live_match_ids":[],
      "already_settled_match_ids":sorted(already_settled_ids),
      "departed_match_ids":[],
      "queried_match_ids":[],
      "standard_final_settlements":[],
      "blocked_or_pending":[],
      "labeled_state_rows":0,
      "protections":{
        "final_only":True,
        "retired_walkover_abandoned_not_silently_labeled":True,
        "prematch_freeze_mutated":False,
        "odds_to_probability":False,
        "reserve_not_bypassed":True,
        "real_money":"BLOCKED"
      }
    }
    out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    ledger_path.write_text(json.dumps(ledger,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":status,"reason":reason,"quota_remaining":remaining,"settled_matches":0,"labeled_state_rows":0},sort_keys=True))



def historical_query_attempts(out_path:Path)->dict[int,int]:
    """Count previous genuine detail queries, never interpret them as a result."""
    import hashlib
    counts:dict[int,int]={}
    prior=[out_path]
    archive=out_path.parent/"settlement_immutable"
    if archive.is_dir():
        prior.extend(sorted(archive.glob("MATRIX_LIVE_FINAL_SYNC_*.json")))
    seen_digests=set()
    for path in prior:
        if not path.is_file():
            continue
        raw=path.read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
        if digest in seen_digests:
            continue
        seen_digests.add(digest)
        try:
            data=json.loads(raw)
        except (ValueError,UnicodeError):
            raise ValueError("SETTLEMENT_QUERY_RECEIPT_UNREADABLE:"+str(path))
        if not isinstance(data,dict) or data.get("schema")!="MATRIX_LIVE_TENNIS_SETTLEMENT_SYNC_V0_1":
            raise ValueError("SETTLEMENT_QUERY_RECEIPT_SCHEMA_INVALID:"+str(path))
        ids=data.get("queried_match_ids")
        if not isinstance(ids,list) or any(type(mid) is not int or mid<=0 for mid in ids):
            raise ValueError("SETTLEMENT_QUERY_RECEIPT_IDS_INVALID:"+str(path))
        for mid in set(ids):
            counts[mid]=counts.get(mid,0)+1
    return counts


def frozen_match_ids(ledger_path:Path)->set[int]:
    """Read immutable prelabel manifests only; never infer an outcome."""
    archive=ledger_path.parent/"prelabel_immutable"
    matches=set()
    if not archive.is_dir():
        return matches
    for path in sorted(archive.glob("MATRIX_LIVE_PRELABEL_BATCH_*.json")):
        data=json.loads(path.read_bytes())
        if (data.get("schema")!="MATRIX_LIVE_TENNIS_PRELABEL_CAPTURE_BATCH_V1"
            or data.get("real_money")!="BLOCKED"
            or data.get("model_probability_authorized") is not False):
            raise ValueError("PRELABEL_BATCH_NOT_SAFE_FOR_SETTLEMENT_PRIORITY")
        for row in data.get("matches") or []:
            mid=row.get("match_id")
            if (type(mid) is not int or mid<=0 or
                row.get("physical_match_key")!="live_tennis_api:"+str(mid)):
                raise ValueError("PRELABEL_MATCH_ID_AMBIGUOUS")
            matches.add(mid)
    return matches


def fair_departed_queue(departed:list[int],query_attempts:dict[int,int],
                        frozen:set[int])->list[int]:
    """Least queried first; frozen priority only breaks ties."""
    if any(type(mid) is not int or mid<=0 for mid in departed):
        raise ValueError("DEPARTED_MATCH_ID_INVALID")
    return sorted(set(departed),key=lambda mid:(
        query_attempts.get(mid,0),
        0 if mid in frozen else 1,
        mid
    ))

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

    out_path=Path(args.out)
    usage,code=get_json("/usage",key)
    if code==429:
        persist_blocked_state(
            ledger_path=ledger_path,out_path=out_path,ledger=ledger,
            match_ids=match_ids,already_settled_ids=already_settled_ids,
            status="BLOCKED_HTTP_429",reason="USAGE_HTTP_429",remaining=None,
        )
        return
    if code!=200:
        raise SystemExit(f"USAGE_HTTP_{code}")
    remaining=((usage.get("today") or {}).get("remaining_day") if isinstance(usage,dict) else None)
    if not isinstance(remaining,int):
        raise SystemExit("USAGE_REMAINING_UNKNOWN")
    if remaining<=args.reserve_calls:
        persist_blocked_state(
            ledger_path=ledger_path,out_path=out_path,ledger=ledger,
            match_ids=match_ids,already_settled_ids=already_settled_ids,
            status="BLOCKED_BY_RESERVE",reason="QUOTA_RESERVE_PROTECTED",remaining=remaining,
        )
        return

    live,code=get_json("/matches",key,{"status":"live","limit":50})
    if code==429:
        persist_blocked_state(
            ledger_path=ledger_path,out_path=out_path,ledger=ledger,
            match_ids=match_ids,already_settled_ids=already_settled_ids,
            status="BLOCKED_HTTP_429",reason="LIVE_HTTP_429",remaining=remaining,
        )
        return
    if code!=200:
        raise SystemExit(f"LIVE_HTTP_{code}")
    live_rows=live.get("data") if isinstance(live,dict) and isinstance(live.get("data"),list) else []
    live_ids={x.get("id") for x in live_rows if isinstance(x,dict) and isinstance(x.get("id"),int)}
    departed=[mid for mid in match_ids if mid not in live_ids and mid not in already_settled_ids]

    budget=max(0,remaining-args.reserve_calls-1)
    query_attempts=historical_query_attempts(out_path)
    frozen_priority=frozen_match_ids(ledger_path)
    ordered_departed=fair_departed_queue(departed,query_attempts,frozen_priority)
    query_ids=ordered_departed[:min(args.max_detail_queries,budget)]
    settlements=[]
    blocked=[]
    for mid in query_ids:
        detail,code=get_json(f"/matches/{mid}",key)
        if code==429:
            blocked.append({"match_id":mid,"reason":"DETAIL_HTTP_429_RATE_LIMIT_STOP"})
            break
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
      "selection_policy":"LEAST_AUTHENTIC_PAST_QUERIES_THEN_FROZEN_PRIORITY_THEN_MATCH_ID",
      "previous_query_attempts_for_selected":{str(mid):query_attempts.get(mid,0) for mid in query_ids},
      "selected_with_immutable_prelabel_freeze":sum(mid in frozen_priority for mid in query_ids),
      "eligible_departed_not_queried_this_cycle":len(ordered_departed)-len(query_ids),
      "api_detail_query_budget_unchanged":True,
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
