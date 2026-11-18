"""Retrospective, group-held-out Live Tennis research from authentic captured states.

This is NOT prospectively frozen validation and NEVER yields production P_LIVE,
Telegram selections, weights for the original models or wagering authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tools.live_tennis_model_gate import FEATURES_V0_1
from tools.live_tennis_presettlement_builder import fold_for_match
from tools.live_tennis_cumulative_integrity_research import parse_utc

ROOT = Path("evidence/live_tennis_lab")
INTEGRITY = "MATRIX_LIVE_TENNIS_CUMULATIVE_INTEGRITY_RESEARCH_LAST.json"
CUMULATIVE = "MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1.json"
SCHEMA = "MATRIX_LIVE_TENNIS_HISTORICAL_GROUPED_RESEARCH_V1"
MIN_RESEARCH_MATCHES = 30  # Existing Live Tennis gate-30, never a new production threshold.
BOOL_FIELDS = {"server_is_p1","is_tiebreak","corroborated"}
FLOAT_FIELDS = [k for k in FEATURES_V0_1 if k not in BOOL_FIELDS]
PROVIDER = "live_tennis_api"

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read(path: Path) -> tuple[dict,str]:
    raw=path.read_bytes()
    if len(raw)>15_000_000:
        raise ValueError("RESEARCH_SOURCE_OVERSIZED")
    doc=json.loads(raw)
    if not isinstance(doc,dict):
        raise ValueError("RESEARCH_SOURCE_NOT_JSON_OBJECT")
    return doc,sha(raw)

def score_state(row: dict) -> list[float] | None:
    """Do not replace missing, null, malformed or nonfinite values."""
    if (row.get("quality_state_valid") is not True
        or row.get("origin") != "observed"
        or row.get("stale") is not False
        or row.get("corroborated") is not True
        or type(row.get("sources_count")) is not int
        or row["sources_count"] < 2):
        return None
    # A final score in the live feature vector might trivially reveal the label.
    for key in ("sets_p1","sets_p2"):
        if type(row.get(key)) is not int or not 0 <= row[key] < 2:
            return None
    result=[]
    for name in FEATURES_V0_1:
        value=row.get(name)
        if name in BOOL_FIELDS:
            if type(value) is not bool:
                return None
            result.append(float(value))
        elif type(value) in (float,int) and math.isfinite(float(value)):
            result.append(float(value))
        else:
            return None
    return result

def sigmoid(x: float) -> float:
    return 1.0/(1.0+math.exp(-max(-40.0,min(40.0,x))))

def fit_research(train: list[tuple[list[float],int]]) -> dict:
    """Fixed single logistic baseline: train-only standardization and ridge."""
    if not train:
        raise ValueError("EMPTY_DEVELOPMENT_SET")
    if set(y for _,y in train) != {0,1}:
        raise ValueError("DEVELOPMENT_REQUIRES_BOTH_OUTCOMES")
    width=len(FEATURES_V0_1)
    if any(len(x)!=width for x,_ in train):
        raise ValueError("FEATURE_WIDTH_INCONSISTENT")
    n=len(train)
    means=[sum(x[j] for x,_ in train)/n for j in range(width)]
    stds=[]
    for j in range(width):
        sd=math.sqrt(sum((x[j]-means[j])**2 for x,_ in train)/n)
        # This is scale-only, NOT a missing-value default or sample imputation.
        stds.append(sd if sd>1e-12 else 1.0)
    xs=[[max(-10.0,min(10.0,(v-m)/sd))
         for v,m,sd in zip(x,means,stds)] for x,_ in train]
    ys=[y for _,y in train]
    positive=sum(ys)
    intercept=math.log((positive+0.5)/(n-positive+0.5))
    weights=[0.0]*width
    for _ in range(450):
        predictions=[sigmoid(intercept+sum(w*v for w,v in zip(weights,x))) for x in xs]
        errors=[pred-y for pred,y in zip(predictions,ys)]
        bgrad=sum(errors)/n
        gradients=[
            sum(err*x[j] for err,x in zip(errors,xs))/n + 0.05*weights[j]
            for j in range(width)
        ]
        intercept-=0.12*bgrad
        weights=[w-0.12*g for w,g in zip(weights,gradients)]
    return {"intercept":intercept,"weights":weights,"means":means,"scales":stds,
            "train_prevalence":positive/n}

def predict(model: dict,x: list[float]) -> float:
    standardized=[max(-10.0,min(10.0,(v-m)/sd))
                  for v,m,sd in zip(x,model["means"],model["scales"])]
    return sigmoid(model["intercept"]+
                   sum(w*v for w,v in zip(model["weights"],standardized)))

def metrics(y: list[int],p: list[float]) -> dict:
    if not y or len(y)!=len(p):
        raise ValueError("INVALID_METRICS_INPUT")
    n=len(y)
    brier=sum((a-b)**2 for a,b in zip(y,p))/n
    logloss=-sum(a*math.log(max(1e-12,b))+(1-a)*math.log(max(1e-12,1-b))
                 for a,b in zip(y,p))/n
    ece=0.0
    for i in range(10):
        bucket=[(a,b) for a,b in zip(y,p)
                if i/10 <= b < (i+1)/10 or (i==9 and b==1.0)]
        if bucket:
            ece+=(len(bucket)/n)*abs(sum(b for a,b in bucket)/len(bucket)
                                  -sum(a for a,b in bucket)/len(bucket))
    positives=[b for a,b in zip(y,p) if a==1]
    negatives=[b for a,b in zip(y,p) if a==0]
    auc=None
    if positives and negatives:
        auc=sum(1.0 if x>z else 0.5 if x==z else 0.0
                for x in positives for z in negatives)/(len(positives)*len(negatives))
    return {"brier":round(brier,6),"log_loss":round(logloss,6),
            "ece_10_bins":round(ece,6),"auc":None if auc is None else round(auc,6),
            "holdout_outcome_prevalence":round(sum(y)/n,6)}

def evidence(root: Path) -> dict:
    base=root/ROOT
    audit,audit_hash=read(base/INTEGRITY)
    cumulative,canonical_hash=read(base/CUMULATIVE)
    if (audit.get("schema")!="MATRIX_LIVE_TENNIS_CUMULATIVE_INTEGRITY_RESEARCH_V1"
        or audit.get("source_cumulative_sha256")!=canonical_hash
        or audit.get("production_p_live_authorized") is not False
        or audit.get("real_money")!="BLOCKED"
        or cumulative.get("probability_output_status")!="SEALED"
        or cumulative.get("multi_lane_ambiguity_quarantined_from_all_gate_counts") is not True):
        raise ValueError("RESEARCH_SOURCES_NOT_FROZEN_OR_INTEGRITY_GATE_NOT_SEALED")
    accepted_lanes={
        x["lane"] for x in audit.get("lane_research_counts") or []
        if x.get("research_integrity_clear") is True
        and x.get("research_count_threshold_30_met") is True
    }
    bad_keys=set(audit.get("quarantined_physical_match_keys") or [])
    bymatch=defaultdict(list)
    skipped=Counter()
    manifest=cumulative.get("source_ledgers") or []
    if len(manifest)!=audit.get("source_daily_ledgers"):
        raise ValueError("RESEARCH_DAILY_MANIFEST_COUNT_DRIFT")
    for source in manifest:
        name=str(source.get("path") or "")
        path=root/name
        doc,digest=read(path)
        if (digest!=source.get("sha256")
            or digest!=(audit.get("source_daily_ledger_hashes") or {}).get(name)):
            raise ValueError("RESEARCH_LEDGER_SOURCE_SHA_CHANGED")
        if doc.get("schema")!="MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1":
            raise ValueError("UNVERIFIED_LIVE_LEDGER_SCHEMA")
        for row in doc.get("states") or []:
            if not isinstance(row,dict):
                skipped["ROW_NOT_OBJECT"]+=1;continue
            mid=row.get("match_id")
            if type(mid) is not int or mid<=0:
                skipped["MATCH_ID_INVALID"]+=1;continue
            if row.get("provider")!=PROVIDER:
                skipped["PROVIDER_NOT_EQUIVALENCE_CERTIFIED"]+=1;continue
            key=PROVIDER+":"+str(mid)
            if key in bad_keys:
                skipped["CROSS_LANE_IDENTITY_QUARANTINED"]+=1;continue
            lane="|".join(str(row.get(n) or "unknown").lower().strip()
                          for n in ("tour","gender","surface"))
            if lane not in accepted_lanes:
                continue
            bymatch[(lane,key)].append(row)
    grouped=defaultdict(list)
    for (lane,key),rows in bymatch.items():
        labels={
            r.get("p1_match_win") for r in rows
            if r.get("label_opened") is True
            and r.get("settlement_status")=="FINAL_STANDARD"
            and type(r.get("p1_match_win")) is int
            and r["p1_match_win"] in (0,1)
        }
        if len(labels)!=1:
            skipped["NOT_EXACTLY_ONE_VALID_FINAL_OUTCOME"]+=1
            continue
        candidates=[]
        for row in rows:
            x=score_state(row)
            if x is None:
                continue
            try:
                captured=parse_utc(row.get("captured_at_utc"))
            except (ValueError,TypeError):
                continue
            # Only a genuine previously observed quality-valid state; never
            # use final-result fields as features or a post-settlement state.
            candidates.append((captured,x))
        if not candidates:
            skipped["NO_COMPLETE_EARLY_LIVE_STATE"]+=1
            continue
        candidates.sort(key=lambda z:z[0])
        mid=int(key.split(":")[-1])
        grouped[lane].append((key,mid,candidates[0][1],next(iter(labels)),candidates[0][0]))
    lane_results=[]
    for lane in sorted(accepted_lanes):
        cases=grouped.get(lane,[])
        dev=[(x,y) for _,mid,x,y,_ in cases if fold_for_match(mid)!=4]
        hold=[(x,y) for _,mid,x,y,_ in cases if fold_for_match(mid)==4]
        record={"lane":lane,"historical_earliest_complete_quality_valid_matches":len(cases),
                "development_unique_matches":len(dev),
                "holdout_unique_matches":len(hold),
                "retrospective_grouped_research_training_executed":False,
                "prospective_out_of_sample_certified":False,
                "production_p_live_authorized":False,"probability_output_authorized":False,
                "holdout_metrics":None,"development_only_baseline_metrics":None}
        if len(cases)<MIN_RESEARCH_MATCHES:
            record["status"]="INCOMPLETE_LIVE_FEATURES_LESS_THAN_ORIGINAL_GATE30"
        elif len(dev)<20 or len(hold)<5:
            record["status"]="DEVELOPMENT_OR_HOLDOUT_INSUFFICIENT_FOR_RESEARCH"
        elif set(y for x,y in dev)!={0,1}:
            record["status"]="DEVELOPMENT_SINGLE_OUTCOME_CLASS"
        else:
            model=fit_research(dev)
            labels=[y for _,y in hold]
            predictions=[predict(model,x) for x,y in hold]
            reference=[model["train_prevalence"]]*len(hold)
            record["status"]="HISTORICAL_GROUP_HELDOUT_RESEARCH_ONLY"
            record["retrospective_grouped_research_training_executed"]=True
            record["holdout_metrics"]=metrics(labels,predictions)
            record["development_only_baseline_metrics"]=metrics(labels,reference)
            record["fixed_research_model_sha256"]=sha(
                json.dumps(model,sort_keys=True,separators=(",",":")).encode())
            record["untouched_holdout_unique_matches"]=len(hold)
        lane_results.append(record)
    return {
        "schema":SCHEMA,
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status":"HISTORICAL_RESEARCH_ONLY_NOT_PROSPECTIVE_CERTIFICATION",
        "source_integrity_sha256":audit_hash,
        "source_cumulative_sha256":canonical_hash,
        "source_daily_ledgers_verified":len(manifest),
        "source_quarantined_physical_match_count":len(bad_keys),
        "source_research_clear_lanes":len(accepted_lanes),
        "fixed_feature_set":list(FEATURES_V0_1),
        "split_policy":"EXISTING_SHA256_MATRIX_LIVE_TENNIS_V0_1_MATCH_ID_FOLD_4_HOLDOUT",
        "model":"SINGLE_FIXED_RIDGE_LOGISTIC_EXPLORATORY_NOT_ORIGINAL_MODEL",
        "missing_features_are_dropped_not_replaced":True,
        "no_result_field_used_as_a_model_feature":True,
        "no_match_in_both_groups":True,
        "historical_labeled_observations_not_prospective_holdout":True,
        "per_lane":lane_results,
        "rejected_research_matches_by_reason":dict(sorted(skipped.items())),
        "retrospective_research_lanes_with_metrics":sum(
            x["retrospective_grouped_research_training_executed"] for x in lane_results),
        "independently_pre_registered_prospective_holdout_complete":False,
        "prospective_model_certified":False,
        "production_p_live_authorized":False,
        "telegram_signal_authorized":False,
        "original_hard_clay_calibrations_unchanged":True,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=Path("."))
    ap.add_argument("--out",type=Path,default=Path(
        "evidence/live_tennis_lab/MATRIX_LIVE_TENNIS_HISTORICAL_GROUPED_RESEARCH_LAST.json"))
    args=ap.parse_args()
    result=evidence(args.root)
    dest=args.root/args.out
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],
        "research_clear_lanes":result["source_research_clear_lanes"],
        "historical_lanes_with_metrics":result["retrospective_research_lanes_with_metrics"],
        "production_probability_authorized":False},sort_keys=True))

if __name__=="__main__":
    main()
