from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_LEDGER = Path("evidence/api_football/prospective_calibration/ledger.jsonl")
SOURCE_SYNC = Path("evidence/api_football/prospective_calibration/sync_last.json")
OUT = Path("evidence/api_football/calibration_v2/CHECKPOINT_4000_MARKET_CALIBRATION_20261023.json")
TARGET = 4000
EPS = 1e-15

def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def canonical_sha(obj: Any) -> str:
    raw=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def load_rows() -> list[dict[str,Any]]:
    rows=[]
    for line in SOURCE_LEDGER.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows

def clip(p: float) -> float:
    return min(1.0-EPS,max(EPS,float(p)))

def binary_metrics(rows: list[tuple[float,bool]]) -> dict[str,Any]:
    n=len(rows)
    if not n:
        return {"sample_size":0,"status":"NO_VALID_ROWS"}
    brier=sum((p-(1.0 if y else 0.0))**2 for p,y in rows)/n
    ll=-sum((1.0 if y else 0.0)*math.log(clip(p))+(0.0 if y else 1.0)*math.log(clip(1.0-p)) for p,y in rows)/n
    bins=[]
    ece=0.0
    mce=0.0
    for i in range(10):
        lo=i/10
        hi=(i+1)/10
        subset=[(p,y) for p,y in rows if (lo <= p < hi) or (i==9 and p==1.0)]
        if not subset:
            continue
        mp=sum(p for p,_ in subset)/len(subset)
        obs=sum(1.0 if y else 0.0 for _,y in subset)/len(subset)
        gap=abs(mp-obs)
        ece += len(subset)/n*gap
        mce=max(mce,gap)
        bins.append({"bin":i,"lower":lo,"upper":hi,"count":len(subset),"mean_probability":mp,"observed_rate":obs,"absolute_gap":gap})
    return {
        "sample_size":n,
        "brier_score":brier,
        "log_loss":ll,
        "ece":ece,
        "max_calibration_error":mce,
        "mean_predicted_probability":sum(p for p,_ in rows)/n,
        "observed_positive_rate":sum(1.0 if y else 0.0 for _,y in rows)/n,
        "probability_min":min(p for p,_ in rows),
        "probability_max":max(p for p,_ in rows),
        "reliability_bins":bins,
    }

def multiclass_metrics(rows: list[tuple[dict[str,float],str]]) -> dict[str,Any]:
    labels=("H","D","A")
    n=len(rows)
    if not n:
        return {"sample_size":0,"status":"NO_VALID_ROWS"}
    brier=0.0
    ll=0.0
    acc=0
    per={k:[] for k in labels}
    for probs,y in rows:
        brier += sum((float(probs[k])-(1.0 if y==k else 0.0))**2 for k in labels)
        ll += -math.log(clip(float(probs[y])))
        pred=max(labels,key=lambda k:float(probs[k]))
        acc += int(pred==y)
        for k in labels:
            per[k].append((float(probs[k]),y==k))
    class_cal={k:binary_metrics(v) for k,v in per.items()}
    macro_ece=sum(class_cal[k]["ece"] for k in labels)/3
    max_err=max(class_cal[k]["max_calibration_error"] for k in labels)
    return {
        "sample_size":n,
        "brier_score":brier/n,
        "log_loss":ll/n,
        "accuracy":acc/n,
        "calibration":{"method":"ONE_VS_REST_EQUAL_WIDTH_10_BINS","macro_ece":macro_ece,"max_class_calibration_error":max_err,"per_class":class_cal},
    }

def main() -> None:
    if not SOURCE_LEDGER.exists() or not SOURCE_SYNC.exists():
        raise SystemExit("CHECKPOINT_4000_SOURCE_MISSING")
    sync=json.loads(SOURCE_SYNC.read_text(encoding="utf-8"))
    rows=load_rows()
    if len(rows) < TARGET:
        raise SystemExit(f"CHECKPOINT_4000_NOT_MATURE:{len(rows)}/{TARGET}")
    if int(sync.get("calibration_observation_count") or 0) < TARGET:
        raise SystemExit("SYNC_NOT_MATURE_4000")
    if sync.get("ledger_hash_chain_verified") is not True:
        raise SystemExit("LEDGER_HASH_CHAIN_NOT_VERIFIED")
    if sync.get("parameters_mutated") is not False:
        raise SystemExit("PARAMETERS_MUTATED")
    if sync.get("real_money") != "BLOCKED":
        raise SystemExit("REAL_MONEY_NOT_BLOCKED")

    prefix=rows[:TARGET]
    prefix_fixture_ids=[str(r.get("fixture_id") or "") for r in prefix]
    if any(not x for x in prefix_fixture_ids) or len(set(prefix_fixture_ids)) != TARGET:
        raise SystemExit("CHECKPOINT_4000_FIXTURE_ID_UNIQUENESS_FAILED")

    one=[]
    over=[]
    lane_missing={"1x2":0,"over_2_5":0}
    parameter_violations=0
    for r in prefix:
        if r.get("parameters_mutated_after_freeze") is not False or r.get("used_for_parameter_tuning") is not False:
            parameter_violations += 1
        probs=r.get("frozen_challenger_probabilities") or {}
        outcomes=r.get("outcomes") or {}
        p1=probs.get("1x2")
        y1=outcomes.get("1x2")
        if isinstance(p1,dict) and y1 in {"H","D","A"} and all(isinstance(p1.get(k),(int,float)) for k in ("H","D","A")):
            one.append(({k:float(p1[k]) for k in ("H","D","A")},str(y1)))
        else:
            lane_missing["1x2"] += 1
        po=probs.get("over_2_5")
        yo=outcomes.get("over_2_5")
        if isinstance(po,(int,float)) and isinstance(yo,bool):
            over.append((float(po),yo))
        else:
            lane_missing["over_2_5"] += 1
    if parameter_violations:
        raise SystemExit(f"CHECKPOINT_4000_PARAMETER_VIOLATIONS:{parameter_violations}")

    under=[(1.0-p,not y) for p,y in over]
    dc1x=[(float(p["H"])+float(p["D"]),y!="A") for p,y in one]
    dcx2=[(float(p["A"])+float(p["D"]),y!="H") for p,y in one]

    markets={
        "1x2":{"market":"1X2","metrics":multiclass_metrics(one),"eligible_rows":len(one),"missing_rows":lane_missing["1x2"]},
        "over_2_5":{"market":"OVER_2_5","metrics":binary_metrics(over),"eligible_rows":len(over),"missing_rows":lane_missing["over_2_5"]},
        "under_2_5":{"market":"UNDER_2_5","metrics":binary_metrics(under),"eligible_rows":len(under),"missing_rows":lane_missing["over_2_5"],"derived_from":"OVER_2_5"},
        "double_chance_1x":{"market":"DOUBLE_CHANCE_1X","metrics":binary_metrics(dc1x),"eligible_rows":len(dc1x),"missing_rows":lane_missing["1x2"],"derived_from":"1X2"},
        "double_chance_x2":{"market":"DOUBLE_CHANCE_X2","metrics":binary_metrics(dcx2),"eligible_rows":len(dcx2),"missing_rows":lane_missing["1x2"],"derived_from":"1X2"},
    }

    payload={
        "schema":"MATRIX_FOOTBALL_CHECKPOINT_4000_MARKET_CALIBRATION_V1",
        "generated_at_utc":now_utc(),
        "checkpoint":4000,
        "checkpoint_role":"CLOSED_FIXED_PREFIX_4000_DIAGNOSTIC_CALIBRATION_NOT_AUTOMATIC_PROMOTION",
        "source":{
            "ledger_path":str(SOURCE_LEDGER),
            "sync_path":str(SOURCE_SYNC),
            "source_rows_available":len(rows),
            "source_sync_observation_count":sync.get("calibration_observation_count"),
            "ledger_hash_chain_verified":True,
            "prefix_fixture_ids_sha256":hashlib.sha256("\n".join(prefix_fixture_ids).encode()).hexdigest(),
            "first_fixture_id":prefix_fixture_ids[0],
            "last_fixture_id":prefix_fixture_ids[-1],
            "unique_fixture_ids":len(set(prefix_fixture_ids)),
        },
        "governance":{
            "metrics_opened":True,
            "outcomes_read_for_checkpoint_metrics":TARGET,
            "parameter_tuning_allowed":False,
            "parameters_mutated":False,
            "refit_allowed":False,
            "model_files_modified":False,
            "odds_used_to_generate_probability":False,
            "no_silent_imputation":True,
            "missing_is_not_zero":True,
            "real_money":"BLOCKED",
            "automatic_wagering":False,
        },
        "markets":markets,
        "adjudication":{
            "calibration_checkpoint_status":"OPENED_AND_MEASURED",
            "market_promotion":"NOT_AUTOMATICALLY_AUTHORIZED",
            "real_money_decision":"NO_GO_KEEP_BLOCKED",
            "reason":"FULL_GO_NO_GO_REQUIRES_PREREGISTERED_MARKET_RULES_PLUS_CLV_RISK_AND_EXECUTION_EVIDENCE",
            "next_oos_block":{"size":1000,"policy":"NEW_PROSPECTIVE_OOS_NO_PARAMETER_CHANGES"},
        },
    }
    payload["checkpoint_sha256"]=canonical_sha(payload)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if OUT.exists():
        old=json.loads(OUT.read_text(encoding="utf-8"))
        immutable_keys=("checkpoint","checkpoint_role")
        for k in immutable_keys:
            if old.get(k)!=payload.get(k):
                raise SystemExit(f"CHECKPOINT_4000_IMMUTABILITY_VIOLATION:{k}")
        if old.get("source",{}).get("prefix_fixture_ids_sha256") != payload["source"]["prefix_fixture_ids_sha256"]:
            raise SystemExit("CHECKPOINT_4000_PREFIX_MUTATED")
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "checkpoint":4000,
        "available":len(rows),
        "prefix_unique":len(set(prefix_fixture_ids)),
        "one_x_two_n":len(one),
        "over25_n":len(over),
        "metrics_opened":True,
        "real_money":"BLOCKED",
        "output":str(OUT),
        "checkpoint_sha256":payload["checkpoint_sha256"],
    },sort_keys=True))

if __name__ == "__main__":
    main()
