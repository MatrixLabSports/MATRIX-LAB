from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GATES=(1,30,50,100,200)

def lane_key(row: dict[str,Any]) -> str:
    return "|".join([
        str(row.get("tour") or "unknown").strip().lower(),
        str(row.get("gender") or "unknown").strip().lower(),
        str(row.get("surface") or "unknown").strip().lower(),
    ])

def physical_match_key(row: dict[str,Any]) -> str | None:
    mid=row.get("match_id")
    if not isinstance(mid,int):
        return None
    provider=str(row.get("provider") or "live_tennis_api").strip().lower()
    return f"{provider}:{mid}"

def build(root: Path, out: Path) -> dict[str,Any]:
    ledgers=sorted(root.glob("*/MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json"))
    lane_matches=defaultdict(dict)
    global_matches={}
    source_rows=[]
    for lp in ledgers:
        try:
            j=json.loads(lp.read_text(encoding="utf-8"))
        except Exception:
            continue
        source_rows.append({
            "path":str(lp),
            "sha256":hashlib.sha256(lp.read_bytes()).hexdigest(),
            "operational_date_bogota":j.get("operational_date_bogota"),
            "unique_match_count":j.get("unique_match_count"),
            "unique_state_count":j.get("unique_state_count"),
        })
        for row in j.get("states",[]) or []:
            if not isinstance(row,dict):
                continue
            key=physical_match_key(row)
            if not key:
                continue
            lane=lane_key(row)
            rec=lane_matches[lane].setdefault(key,{
                "provider":row.get("provider"),
                "match_id":row.get("match_id"),
                "quality_valid":False,
                "settled_final_standard":False,
                "labeled_state_count":0,
                "state_keys":set(),
            })
            sk=row.get("state_key")
            if sk:
                rec["state_keys"].add(str(sk))
            if row.get("quality_state_valid") is True:
                rec["quality_valid"]=True
            if (
                row.get("label_opened") is True
                and row.get("settlement_status")=="FINAL_STANDARD"
                and row.get("p1_match_win") in {0,1}
            ):
                rec["settled_final_standard"]=True
                rec["labeled_state_count"]+=1
            global_matches[key]=True

    lanes={}
    for lane,matches in sorted(lane_matches.items()):
        settled=sum(1 for x in matches.values() if x["settled_final_standard"])
        valid=sum(1 for x in matches.values() if x["quality_valid"])
        lanes[lane]={
            "unique_match_count":len(matches),
            "quality_valid_unique_match_count":valid,
            "settled_unique_match_count":settled,
            "gates":{
                str(g):{
                    "threshold":g,
                    "status":"OPEN" if settled>=g else "SEALED",
                    "remaining":max(0,g-settled),
                } for g in GATES
            },
            "match_keys_sha256":hashlib.sha256(
                "\n".join(sorted(matches)).encode()
            ).hexdigest(),
        }

    total_settled=sum(x["settled_unique_match_count"] for x in lanes.values())
    payload={
        "schema":"MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_ledgers":source_rows,
        "ledger_dates_count":len(source_rows),
        "global_unique_match_count":len(global_matches),
        "sum_lane_settled_unique_matches":total_settled,
        "lanes":lanes,
        "gate_unit":"UNIQUE_FINAL_STANDARD_MATCHES_PER_LANE_ACROSS_DAYS",
        "dedupe_key":"provider+match_id",
        "states_do_not_substitute_for_matches":True,
        "same_match_train_test_forbidden":True,
        "model_status":"RESEARCH_ONLY",
        "probability_output_status":"SEALED",
        "metrics_status":"SEALED",
        "protections":{
            "prematch_hard_mutated":False,
            "prematch_clay_mutated":False,
            "odds_to_probability":False,
            "silent_imputation":False,
            "missing_not_zero":True,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }
    }
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    payload["sha256_without_self"]=hashlib.sha256(raw).hexdigest()
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return payload

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="evidence/live_tennis_lab")
    ap.add_argument("--out",default="evidence/live_tennis_lab/MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1.json")
    a=ap.parse_args()
    p=build(Path(a.root),Path(a.out))
    print(json.dumps({
        "dates":p["ledger_dates_count"],
        "global_unique_matches":p["global_unique_match_count"],
        "settled":p["sum_lane_settled_unique_matches"],
        "lanes":{k:v["settled_unique_match_count"] for k,v in p["lanes"].items()}
    },sort_keys=True))

if __name__=="__main__":
    main()
