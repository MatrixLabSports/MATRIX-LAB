from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

GATES=(1,30,50,100,200)


def _lane(row: Mapping[str,Any]) -> str:
    event_type=str(row.get("event_type") or "unknown").strip().casefold()
    if "challenger men" in event_type and "singles" in event_type:
        return "api_tennis|challenger_men_singles"
    if "challenger women" in event_type and "singles" in event_type:
        return "api_tennis|challenger_women_singles"
    if "atp" in event_type and "singles" in event_type:
        return "api_tennis|atp_singles"
    if "wta" in event_type and "singles" in event_type:
        return "api_tennis|wta_singles"
    if "doubles" in event_type:
        return "api_tennis|doubles"
    return "api_tennis|unknown"


def build(root: Path, out: Path) -> dict[str,Any]:
    paths=sorted(root.glob("*/MATRIX_LIVE_TENNIS_API_TENNIS_FAILOVER_LEDGER_V1.json"))
    lanes=defaultdict(dict)
    source=[]
    for path in paths:
        try:
            ledger=json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        source.append({
            "path":str(path),
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "operational_date_bogota":ledger.get("operational_date_bogota"),
            "unique_match_count":ledger.get("unique_match_count"),
            "unique_state_count":ledger.get("unique_state_count"),
        })
        for row in ledger.get("states",[]) or []:
            if not isinstance(row,Mapping):
                continue
            mid=str(row.get("match_id") or "").strip()
            if not mid:
                continue
            key="api_tennis:"+mid
            lane=_lane(row)
            rec=lanes[lane].setdefault(key,{
                "match_id":mid,
                "quality_valid":False,
                "settled_final_standard":False,
                "state_keys":set(),
            })
            if row.get("quality_state_valid") is True:
                rec["quality_valid"]=True
            if (
                row.get("settlement_status")=="FINAL_STANDARD"
                and row.get("label_opened") is True
                and row.get("p1_match_win") in {0,1}
                and row.get("settlement_identity")=="EXACT_PROVIDER_EVENT_KEY"
            ):
                rec["settled_final_standard"]=True
            sk=str(row.get("state_key") or "")
            if sk:
                rec["state_keys"].add(sk)

    out_lanes={}
    all_matches=set()
    for lane,matches in sorted(lanes.items()):
        all_matches.update(matches)
        usable=sum(1 for x in matches.values() if x["quality_valid"] and x["settled_final_standard"])
        final=sum(1 for x in matches.values() if x["settled_final_standard"])
        quality=sum(1 for x in matches.values() if x["quality_valid"])
        out_lanes[lane]={
            "unique_match_count":len(matches),
            "quality_valid_unique_match_count":quality,
            "settled_final_standard_unique_match_count":final,
            "settled_quality_valid_unique_match_count":usable,
            "gates":{
                str(g):{"threshold":g,"status":"OPEN" if usable>=g else "SEALED","remaining":max(0,g-usable)}
                for g in GATES
            },
            "match_keys_sha256":hashlib.sha256("\n".join(sorted(matches)).encode()).hexdigest(),
        }
    payload={
        "schema":"MATRIX_LIVE_TENNIS_API_TENNIS_NATIVE_GATE_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_ledgers":source,
        "ledger_dates_count":len(source),
        "global_unique_match_count":len(all_matches),
        "sum_lane_settled_quality_valid_unique_matches":sum(x["settled_quality_valid_unique_match_count"] for x in out_lanes.values()),
        "lanes":out_lanes,
        "gate_unit":"UNIQUE_API_TENNIS_FINAL_STANDARD_MATCHES_WITH_QUALITY_VALID_STATE",
        "dedupe_key":"api_tennis+provider_event_id",
        "cross_provider_equivalence_required":False,
        "free_provider_lane_mutated":False,
        "surface_imputed":False,
        "model_status":"RESEARCH_ONLY",
        "probability_output_status":"SEALED",
        "metrics_status":"SEALED",
        "protections":{
            "same_provider_exact_event_key_required":True,
            "states_do_not_substitute_for_matches":True,
            "same_match_train_test_forbidden":True,
            "missing_not_zero":True,
            "silent_imputation":False,
            "odds_to_probability":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    payload["sha256_without_self"]=hashlib.sha256(raw).hexdigest()
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return payload


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--root",default="evidence/live_tennis_lab")
    p.add_argument("--out",default="evidence/live_tennis_lab/MATRIX_LIVE_TENNIS_API_TENNIS_NATIVE_GATE_V1.json")
    a=p.parse_args()
    result=build(Path(a.root),Path(a.out))
    print(json.dumps({
        "dates":result["ledger_dates_count"],
        "unique_matches":result["global_unique_match_count"],
        "settled_quality_valid":result["sum_lane_settled_quality_valid_unique_matches"],
        "lanes":{k:v["settled_quality_valid_unique_match_count"] for k,v in result["lanes"].items()},
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
