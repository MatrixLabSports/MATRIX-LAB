from __future__ import annotations

import hashlib
import json
from math import exp, floor, log
from pathlib import Path
from statistics import median
from typing import Any

EPS=1e-15
MIN_TRAIN=200
MIN_VALIDATION=50

LANES=(
    "PLAYER_SHOTS",
    "PLAYER_SHOTS_ON_TARGET",
    "GOALKEEPER_SAVES",
    "PLAYER_ASSISTS",
    "PLAYER_PASSES",
    "PLAYER_TACKLES",
    "PLAYER_FOULS",
)


def _load_jsonl(path:Path)->list[dict[str,Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)


def _poisson_over(mu:float,line:float)->float:
    mu=max(0.01,float(mu))
    cut=int(floor(line))
    term=exp(-mu)
    cdf=term
    for k in range(1,cut+1):
        term*=mu/k
        cdf+=term
    return _clip(1-cdf)


def _metrics(ys:list[int],ps:list[float])->dict[str,float]:
    if not ys or len(ys)!=len(ps):
        raise ValueError("INVALID_METRIC_INPUT")
    brier=ll=0.0
    buckets=[[] for _ in range(5)]
    for y,p0 in zip(ys,ps):
        p=_clip(p0)
        brier+=(p-y)**2
        ll+=-(y*log(p)+(1-y)*log(1-p))
        buckets[min(4,int(p*5))].append((y,p))
    n=len(ys)
    ece=0.0
    max_err=0.0
    for bucket in buckets:
        if not bucket:
            continue
        obs=sum(y for y,_ in bucket)/len(bucket)
        pred=sum(p for _,p in bucket)/len(bucket)
        err=abs(obs-pred)
        ece+=len(bucket)/n*err
        max_err=max(max_err,err)
    return {
        "sample_size":n,
        "brier_score":brier/n,
        "log_loss":ll/n,
        "ece_5bin":ece,
        "max_calibration_error_5bin":max_err,
    }


def _choose_line(train:list[dict[str,Any]])->float:
    values=sorted(float(r["target_count"]) for r in train)
    return floor(float(median(values)))+0.5


def _lambda(row:dict[str,Any],alpha:float,beta:float)->float:
    long=max(0.0,float(row["prior_mean_count"]))
    recent=max(0.0,float(row["last5_mean_count"]))
    prior_minutes=max(1.0,float(row["prior_mean_minutes"]))
    recent_minutes=max(1.0,float(row["last5_mean_minutes"]))
    count=(1-alpha)*long+alpha*recent
    # Only PRIOR minutes are allowed. This mildly normalizes recent-count drift
    # without using current-match minutes or post-start information.
    minute_ratio=min(1.5,max(0.5,recent_minutes/prior_minutes))
    return max(0.01,count*(minute_ratio**beta))


def _internal_split(train:list[dict[str,Any]])->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    cut=max(150,int(len(train)*0.80))
    cut=min(cut,len(train)-25)
    if cut<100 or len(train)-cut<25:
        raise ValueError("INSUFFICIENT_INTERNAL_TEMPORAL_VALIDATION")
    return train[:cut],train[cut:]


def _sha(value:Any)->str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def build_lane(lane:str,path:Path)->dict[str,Any]:
    rows=_load_jsonl(path)
    train=[r for r in rows if r.get("split")=="TRAIN"]
    validation=[r for r in rows if r.get("split")=="VALIDATION"]
    base={
        "schema":"MATRIX_FOOTBALL_EXTENDED_PLAYER_MODEL_V1",
        "lane":lane,
        "source_dataset":str(path),
        "source_dataset_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "row_count":len(rows),
        "train_count":len(train),
        "validation_count":len(validation),
        "minimum_train_required":MIN_TRAIN,
        "minimum_validation_required":MIN_VALIDATION,
        "sample_scope":"CONDITIONAL_ON_APPEARANCE_RESEARCH_ONLY",
        "current_match_minutes_used_as_feature":False,
        "lineup_or_expected_minutes_certified":False,
        "prospective_freeze_allowed":False,
        "prospective_blocker":"PIT_LINEUP_AND_EXPECTED_MINUTES_SOURCE_NOT_YET_CERTIFIED",
        "validation_used_for_parameter_tuning":False,
        "odds_used_to_generate_probability":False,
        "p_matrix_generated":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    if len(train)<MIN_TRAIN or len(validation)<MIN_VALIDATION:
        return {
            **base,
            "status":"SEALED_INSUFFICIENT_HISTORICAL_OOS",
            "metrics_opened":False,
            "historical_candidate_passed":False,
        }

    line=_choose_line(train)
    inner_train,inner_val=_internal_split(train)
    trials=[]
    for alpha in (0.0,0.25,0.50,0.75,1.0):
        for beta in (0.0,0.5,1.0):
            ys=[int(float(r["target_count"])>line) for r in inner_val]
            probs=[_poisson_over(_lambda(r,alpha,beta),line) for r in inner_val]
            metric=_metrics(ys,probs)
            trials.append({
                "alpha_recent":alpha,
                "beta_prior_minutes_ratio":beta,
                "internal_validation":metric,
            })
    trials.sort(key=lambda t:(t["internal_validation"]["log_loss"],t["internal_validation"]["brier_score"]))
    selected=trials[0]

    ys_train=[int(float(r["target_count"])>line) for r in train]
    baseline_probability=sum(ys_train)/len(ys_train)
    ys=[int(float(r["target_count"])>line) for r in validation]
    challenger_probs=[
        _poisson_over(
            _lambda(
                r,
                float(selected["alpha_recent"]),
                float(selected["beta_prior_minutes_ratio"]),
            ),
            line,
        )
        for r in validation
    ]
    baseline_probs=[baseline_probability]*len(validation)
    cm=_metrics(ys,challenger_probs)
    bm=_metrics(ys,baseline_probs)
    db=cm["brier_score"]-bm["brier_score"]
    dl=cm["log_loss"]-bm["log_loss"]
    passed=(
        db<0
        and dl<0
        and cm["ece_5bin"]<=0.10
        and cm["max_calibration_error_5bin"]<=0.20
    )
    params={
        "evaluation_line":line,
        "alpha_recent":selected["alpha_recent"],
        "beta_prior_minutes_ratio":selected["beta_prior_minutes_ratio"],
        "baseline_probability":baseline_probability,
    }
    return {
        **base,
        "status":"HISTORICAL_OOS_PASS_PROSPECTIVE_BLOCKED_BY_LINEUP"
        if passed else "REJECTED_HISTORICAL_OOS",
        "metrics_opened":True,
        "evaluation_line":line,
        "internal_selection":{
            "selection_rows":len(inner_val),
            "trial_count":len(trials),
            "selected":selected,
            "final_validation_used_for_selection":False,
        },
        "model_parameters":params,
        "model_parameters_sha256":_sha(params),
        "validation":{
            "baseline":bm,
            "challenger":cm,
            "delta_brier_challenger_minus_baseline":db,
            "delta_log_loss_challenger_minus_baseline":dl,
            "gate_passed":passed,
        },
        "historical_candidate_passed":passed,
    }


def main()->None:
    root=Path("evidence/api_football/market_expansion/player_pit")
    out=Path("evidence/api_football/market_expansion/player_models")
    out.mkdir(parents=True,exist_ok=True)
    paths={
        lane:root/f"{lane.casefold()}_pit.jsonl"
        for lane in LANES
    }
    results={}
    for lane,path in paths.items():
        result=build_lane(lane,path)
        results[lane]=result
        (out/f"{lane.casefold()}_model.json").write_text(
            json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",
            encoding="utf-8",
        )
    summary={
        "schema":"MATRIX_FOOTBALL_EXTENDED_PLAYER_MODELS_SUMMARY_V1",
        "lanes":{
            lane:{
                "status":r["status"],
                "row_count":r["row_count"],
                "train_count":r["train_count"],
                "validation_count":r["validation_count"],
                "historical_candidate_passed":r["historical_candidate_passed"],
                "prospective_freeze_allowed":r["prospective_freeze_allowed"],
                "prospective_blocker":r["prospective_blocker"],
            }
            for lane,r in results.items()
        },
        "policy":{
            "minimum_train":MIN_TRAIN,
            "minimum_validation":MIN_VALIDATION,
            "conditional_on_appearance_only":True,
            "current_match_minutes_feature":False,
            "validation_tuning":False,
            "odds_to_probability":False,
        },
        "prospective_freeze_allowed":False,
        "global_prospective_blocker":"PIT_LINEUP_AND_EXPECTED_MINUTES_SOURCE_NOT_YET_CERTIFIED",
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    (out/"summary.json").write_text(
        json.dumps(summary,indent=2,sort_keys=True,ensure_ascii=False)+"\n",
        encoding="utf-8",
    )
    print(json.dumps(summary,sort_keys=True))


if __name__=="__main__":
    main()
