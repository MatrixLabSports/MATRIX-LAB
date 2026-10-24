from __future__ import annotations

import hashlib
import json
from math import exp, log, floor
from pathlib import Path
from statistics import median
from typing import Any

EPS=1e-15
MIN_TRAIN=200
MIN_VALIDATION=50
LANES=(
    "CORNERS",
    "TEAM_SHOTS_ON_TARGET",
    "TEAM_TOTAL_SHOTS",
    "TEAM_FOULS",
    "TEAM_GOALKEEPER_SAVES",
    "TEAM_YELLOW_CARDS",
)


def _load_jsonl(path:Path)->list[dict[str,Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)


def _poisson_over(mu:float,line:float)->float:
    mu=max(0.05,float(mu))
    cut=int(floor(line))
    term=exp(-mu)
    cdf=term
    for k in range(1,cut+1):
        term*=mu/k
        cdf+=term
    return _clip(1.0-cdf)


def _metrics(ys:list[int],ps:list[float])->dict[str,float]:
    if len(ys)!=len(ps) or not ys:
        raise ValueError("METRIC_INPUT_INVALID")
    brier=ll=0.0
    bins=[[] for _ in range(5)]
    for y,p0 in zip(ys,ps):
        p=_clip(p0)
        brier+=(p-y)**2
        ll+=-(y*log(p)+(1-y)*log(1-p))
        idx=min(4,int(p*5))
        bins[idx].append((y,p))
    ece=0.0
    max_err=0.0
    n=len(ys)
    for bucket in bins:
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
    vals=sorted(float(r["target_total"]) for r in train)
    m=float(median(vals))
    return floor(m)+0.5


def _fit_count_model(train:list[dict[str,Any]])->dict[str,float]:
    targets=[float(r["target_total"]) for r in train]
    expects=[max(0.05,float(r["expected_total"])) for r in train]
    target_mean=sum(targets)/len(targets)
    expected_sum=sum(expects)
    scale=(sum(targets)/expected_sum) if expected_sum>0 else 1.0

    best=None
    for alpha in (0.25,0.50,0.75,1.0):
        nll=0.0
        for y,x in zip(targets,expects):
            mu=max(0.05,alpha*(scale*x)+(1-alpha)*target_mean)
            # Poisson NLL without log(y!), which is constant across candidates.
            nll+=mu-y*log(mu)
        candidate=(nll,alpha)
        if best is None or candidate<best:
            best=candidate
    assert best is not None
    return {
        "scale":scale,
        "shrinkage_alpha":best[1],
        "training_target_mean":target_mean,
        "training_poisson_nll_without_constant":best[0]/len(train),
    }


def _candidate_prob(row:dict[str,Any],params:dict[str,float],line:float)->float:
    x=max(0.05,float(row["expected_total"]))
    mu=max(
        0.05,
        params["shrinkage_alpha"]*(params["scale"]*x)
        +(1-params["shrinkage_alpha"])*params["training_target_mean"],
    )
    return _poisson_over(mu,line)


def _sha(value:Any)->str:
    return hashlib.sha256(
        json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    ).hexdigest()


def build_lane(lane:str,path:Path)->dict[str,Any]:
    rows=_load_jsonl(path)
    train=[r for r in rows if r.get("split")=="TRAIN"]
    val=[r for r in rows if r.get("split")=="VALIDATION"]
    base={
        "schema":"MATRIX_FOOTBALL_EXTENDED_TEAM_MODEL_V1",
        "lane":lane,
        "source_dataset":str(path),
        "source_dataset_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "row_count":len(rows),
        "train_count":len(train),
        "validation_count":len(val),
        "minimum_train_required":MIN_TRAIN,
        "minimum_validation_required":MIN_VALIDATION,
        "validation_used_for_parameter_tuning":False,
        "odds_used_to_generate_probability":False,
        "p_matrix_generated":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    if len(train)<MIN_TRAIN or len(val)<MIN_VALIDATION:
        return {
            **base,
            "status":"SEALED_INSUFFICIENT_HISTORICAL_OOS",
            "metrics_opened":False,
            "line":None,
            "model_parameters":None,
            "validation":None,
            "prospective_eligible":False,
        }

    line=_choose_line(train)
    ys_train=[int(float(r["target_total"])>line) for r in train]
    baseline_p=sum(ys_train)/len(ys_train)
    params=_fit_count_model(train)

    ys=[int(float(r["target_total"])>line) for r in val]
    baseline_probs=[baseline_p]*len(val)
    challenger_probs=[_candidate_prob(r,params,line) for r in val]
    bm=_metrics(ys,baseline_probs)
    cm=_metrics(ys,challenger_probs)
    db=cm["brier_score"]-bm["brier_score"]
    dl=cm["log_loss"]-bm["log_loss"]
    pass_gate=(
        db<0 and dl<0
        and cm["ece_5bin"]<=0.08
        and cm["max_calibration_error_5bin"]<=0.15
    )
    frozen={
        "evaluation_line":line,
        "baseline_probability":baseline_p,
        "count_model":params,
    }
    return {
        **base,
        "status":"FROZEN_FOR_NEW_PROSPECTIVE_VALIDATION" if pass_gate else "REJECTED_HISTORICAL_OOS",
        "metrics_opened":True,
        "line":line,
        "model_parameters":frozen,
        "model_parameters_sha256":_sha(frozen),
        "validation":{
            "baseline":bm,
            "challenger":cm,
            "delta_brier_challenger_minus_baseline":db,
            "delta_log_loss_challenger_minus_baseline":dl,
            "gate_passed":pass_gate,
        },
        "prospective_eligible":pass_gate,
        "prospective_gates":[30,50,100,200] if pass_gate else [],
    }


def main()->None:
    root=Path("evidence/api_football/market_expansion/team_pit")
    out=Path("evidence/api_football/market_expansion/team_models")
    out.mkdir(parents=True,exist_ok=True)
    lane_paths={
        "CORNERS":root/"corners_pit.jsonl",
        "TEAM_SHOTS_ON_TARGET":root/"team_shots_on_target_pit.jsonl",
        "TEAM_TOTAL_SHOTS":root/"team_total_shots_pit.jsonl",
        "TEAM_FOULS":root/"team_fouls_pit.jsonl",
        "TEAM_GOALKEEPER_SAVES":root/"team_goalkeeper_saves_pit.jsonl",
        "TEAM_YELLOW_CARDS":root/"team_yellow_cards_pit.jsonl",
    }
    results={}
    for lane,path in lane_paths.items():
        result=build_lane(lane,path)
        if lane=="TEAM_YELLOW_CARDS":
            result["semantic_gate"]="YELLOW_CARDS_ONLY_FOUNDATION_NOT_FULL_CARD_SETTLEMENT"
        if lane=="TEAM_GOALKEEPER_SAVES":
            result["semantic_gate"]="TEAM_AGGREGATE_FOUNDATION_NOT_INDIVIDUAL_GOALKEEPER_PROP"
        if lane in {"TEAM_TOTAL_SHOTS","TEAM_FOULS"}:
            result["semantic_gate"]="FOUNDATION_LANE_REQUIRES_BOOKMAKER_SCOPE_BINDING"
        results[lane]=result
        (out/f"{lane.casefold()}_model.json").write_text(
            json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",
            encoding="utf-8",
        )

    summary={
        "schema":"MATRIX_FOOTBALL_EXTENDED_TEAM_MODELS_SUMMARY_V1",
        "lanes":{k:{
            "status":v["status"],
            "row_count":v["row_count"],
            "train_count":v["train_count"],
            "validation_count":v["validation_count"],
            "prospective_eligible":v["prospective_eligible"],
        } for k,v in results.items()},
        "policy":{
            "minimum_train":MIN_TRAIN,
            "minimum_validation":MIN_VALIDATION,
            "line_selected_from_train_only":True,
            "validation_tuning":False,
            "odds_to_probability":False,
            "prospective_gates":[30,50,100,200],
        },
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
