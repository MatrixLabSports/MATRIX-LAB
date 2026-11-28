from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


GATES=(30,50,100,200)


def lane_key(row):
    return "|".join([
        str(row.get("tour") or "unknown"),
        str(row.get("gender") or "unknown"),
        str(row.get("surface") or "unknown"),
    ])


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ledger",required=True)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()

    ledger=json.loads(Path(args.ledger).read_text(encoding="utf-8"))
    states=[x for x in ledger.get("states",[]) if isinstance(x,dict)]

    lanes=defaultdict(lambda:{
        "state_count":0,
        "quality_valid_state_count":0,
        "match_ids":set(),
        "quality_valid_match_ids":set(),
        "settled_match_ids":set(),
        "labeled_state_count":0,
    })

    for row in states:
        key=lane_key(row)
        d=lanes[key]
        d["state_count"]+=1
        mid=row.get("match_id")
        if isinstance(mid,int):
            d["match_ids"].add(mid)
        if row.get("quality_state_valid") is True:
            d["quality_valid_state_count"]+=1
            if isinstance(mid,int):
                d["quality_valid_match_ids"].add(mid)
        if row.get("label_opened") is True and row.get("settlement_status")=="FINAL_STANDARD" and row.get("p1_match_win") in {0,1}:
            d["labeled_state_count"]+=1
            if isinstance(mid,int):
                d["settled_match_ids"].add(mid)

    out_lanes={}
    for key,d in sorted(lanes.items()):
        settled=len(d["settled_match_ids"])
        out_lanes[key]={
            "state_count":d["state_count"],
            "quality_valid_state_count":d["quality_valid_state_count"],
            "unique_match_count":len(d["match_ids"]),
            "quality_valid_unique_match_count":len(d["quality_valid_match_ids"]),
            "settled_unique_match_count":settled,
            "labeled_state_count":d["labeled_state_count"],
            "gates":{
                str(g):{
                    "minimum_unique_settled_matches":g,
                    "status":"OPEN" if settled>=g else "SEALED",
                    "remaining":max(0,g-settled)
                } for g in GATES
            }
        }

    settled_all={
        x.get("match_id") for x in states
        if x.get("label_opened") is True
        and x.get("settlement_status")=="FINAL_STANDARD"
        and x.get("p1_match_win") in {0,1}
        and isinstance(x.get("match_id"),int)
    }

    payload={
        "schema":"MATRIX_LIVE_TENNIS_READINESS_AUDIT_V0_1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_ledger":args.ledger,
        "model_status":"RESEARCH_ONLY",
        "probability_output_status":"SEALED",
        "metrics_status":"SEALED" if len(settled_all)<30 else "ELIGIBLE_FOR_LANE_SPECIFIC_REVIEW_ONLY",
        "global_counts":{
            "unique_state_count":len(states),
            "quality_valid_state_count":sum(1 for x in states if x.get("quality_state_valid") is True),
            "quality_invalid_state_count":sum(1 for x in states if x.get("quality_state_valid") is not True),
            "unique_match_count":len({x.get("match_id") for x in states if isinstance(x.get("match_id"),int)}),
            "settled_standard_unique_match_count":len(settled_all),
            "labeled_state_count":sum(1 for x in states if x.get("label_opened") is True)
        },
        "lanes":out_lanes,
        "rules":{
            "gate_unit":"UNIQUE_SETTLED_MATCHES_PER_LANE",
            "states_do_not_substitute_for_matches":True,
            "same_match_train_test_forbidden":True,
            "unknown_lane_not_promotable_without_metadata_reconciliation":True,
            "no_metrics_before_lane_gate_30":True
        },
        "protections":{
            "odds_to_probability":False,
            "prematch_freeze_mutated":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED"
        }
    }

    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(payload["global_counts"],sort_keys=True))


if __name__=="__main__":
    main()
