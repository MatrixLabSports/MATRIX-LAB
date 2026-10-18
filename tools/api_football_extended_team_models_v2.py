from __future__ import annotations

import hashlib
import json
from math import exp, log
from pathlib import Path
from typing import Any

from tools.api_football_extended_team_models import (
    EPS,
    _choose_line,
    _metrics,
)

TARGET_LANES=(
    "CORNERS",
    "TEAM_SHOTS_ON_TARGET",
    "TEAM_GOALKEEPER_SAVES",
    "TEAM_YELLOW_CARDS",
    "TEAM_FOULS",
)
MIN_TRAIN=200
MIN_VALIDATION=50


def _load_jsonl(path:Path)->list[dict[str,Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _sigmoid(x:float)->float:
    if x>=0:
        z=exp(-x)
        return 1/(1+z)
    z=exp(x)
    return z/(1+z)


def _raw_features(row:dict[str,Any],mode:str)->list[float]:
    expected_total=float(row["expected_total"])
    expected_home=float(row["expected_home"])
    expected_away=float(row["expected_away"])
    base=[
        expected_total,
        expected_home,
        expected_away,
        float(row["home_for_mean"]),
        float(row["home_against_mean"]),
        float(row["away_for_mean"]),
        float(row["away_against_mean"]),
    ]
    if mode=="EXPECTED_ONLY":
        return [expected_total]
    if mode=="TEAM_STRENGTH":
        return base
    if mode=="TEAM_STRENGTH_LEAGUE":
        league_flag=1.0 if str(row.get("league_id"))=="252" else 0.0
        return base+[league_flag,expected_total*expected_total]
    raise ValueError("UNKNOWN_FEATURE_MODE")


def _fit_scaler(rows:list[dict[str,Any]],mode:str):
    matrix=[_raw_features(r,mode) for r in rows]
    d=len(matrix[0])
    means=[sum(x[j] for x in matrix)/len(matrix) for j in range(d)]
    stds=[]
    for j in range(d):
        var=sum((x[j]-means[j])**2 for x in matrix)/len(matrix)
        stds.append(max(var**0.5,1e-6))
    return means,stds


def _features(row:dict[str,Any],mode:str,means:list[float],stds:list[float])->list[float]:
    raw=_raw_features(row,mode)
    return [1.0]+[(x-m)/s for x,m,s in zip(raw,means,stds)]


def _fit(rows:list[dict[str,Any]],line:float,mode:str,l2:float,lr:float=0.03,epochs:int=250):
    means,stds=_fit_scaler(rows,mode)
    d=1+len(means)
    w=[0.0]*d
    n=len(rows)
    for _ in range(epochs):
        g=[0.0]*d
        for r in rows:
            x=_features(r,mode,means,stds)
            y=1.0 if float(r["target_total"])>line else 0.0
            p=_sigmoid(sum(a*b for a,b in zip(w,x)))
            err=p-y
            for j in range(d):
                g[j]+=err*x[j]
        for j in range(d):
            reg=0.0 if j==0 else l2*w[j]
            w[j]-=lr*(g[j]/n+reg)
    return {"mode":mode,"means":means,"stds":stds,"weights":w,"l2":l2,"learning_rate":lr,"epochs":epochs}


def _predict(row:dict[str,Any],model:dict[str,Any])->float:
    x=_features(row,model["mode"],model["means"],model["stds"])
    return _sigmoid(sum(float(a)*float(b) for a,b in zip(model["weights"],x)))


def _folds(rows:list[dict[str,Any]]):
    n=len(rows)
    initial=max(120,int(n*0.60))
    remaining=n-initial
    if remaining<30:
        raise ValueError("INSUFFICIENT_INTERNAL_OOS")
    widths=[remaining//3,remaining//3]
    widths.append(remaining-sum(widths))
    out=[]
    pos=initial
    for width in widths:
        test=rows[pos:pos+width]
        out.append((rows[:pos],test))
        pos+=width
    return out


def _sha(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def build_lane(lane:str,path:Path)->dict[str,Any]:
    rows=_load_jsonl(path)
    train=[r for r in rows if r.get("split")=="TRAIN"]
    validation=[r for r in rows if r.get("split")=="VALIDATION"]
    if len(train)<MIN_TRAIN or len(validation)<MIN_VALIDATION:
        return {
            "schema":"MATRIX_FOOTBALL_EXTENDED_TEAM_MODEL_V2",
            "lane":lane,
            "status":"SEALED_INSUFFICIENT_HISTORICAL_OOS",
            "train_count":len(train),"validation_count":len(validation),
            "prospective_eligible":False,"metrics_opened":False,
            "automatic_wagering":False,"real_money":"BLOCKED",
        }

    line=_choose_line(train)
    trials=[]
    for mode in ("EXPECTED_ONLY","TEAM_STRENGTH","TEAM_STRENGTH_LEAGUE"):
        for l2 in (0.001,0.01,0.1):
            fold_records=[]
            all_y=[]; all_p=[]; all_base=[]
            for fold_no,(fit_rows,test_rows) in enumerate(_folds(train),1):
                model=_fit(fit_rows,line,mode,l2)
                probs=[_predict(r,model) for r in test_rows]
                ys=[int(float(r["target_total"])>line) for r in test_rows]
                base_p=sum(int(float(r["target_total"])>line) for r in fit_rows)/len(fit_rows)
                bases=[base_p]*len(test_rows)
                cm=_metrics(ys,probs); bm=_metrics(ys,bases)
                fold_records.append({
                    "fold":fold_no,"train_count":len(fit_rows),"validation_count":len(test_rows),
                    "challenger":cm,"baseline":bm,
                    "beats_brier":cm["brier_score"]<bm["brier_score"],
                    "beats_log_loss":cm["log_loss"]<bm["log_loss"],
                })
                all_y.extend(ys); all_p.extend(probs); all_base.extend(bases)
            cm_all=_metrics(all_y,all_p); bm_all=_metrics(all_y,all_base)
            trials.append({
                "mode":mode,"l2":l2,
                "internal_challenger":cm_all,"internal_baseline":bm_all,
                "delta_brier":cm_all["brier_score"]-bm_all["brier_score"],
                "delta_log_loss":cm_all["log_loss"]-bm_all["log_loss"],
                "folds":fold_records,
            })

    trials.sort(key=lambda t:(t["internal_challenger"]["log_loss"],t["internal_challenger"]["brier_score"]))
    selected=trials[0]
    model=_fit(train,line,selected["mode"],float(selected["l2"]))
    ys=[int(float(r["target_total"])>line) for r in validation]
    probs=[_predict(r,model) for r in validation]
    base_p=sum(int(float(r["target_total"])>line) for r in train)/len(train)
    bases=[base_p]*len(validation)
    cm=_metrics(ys,probs); bm=_metrics(ys,bases)
    db=cm["brier_score"]-bm["brier_score"]
    dl=cm["log_loss"]-bm["log_loss"]
    pass_gate=(
        db<0 and dl<0
        and cm["ece_5bin"]<=0.08
        and cm["max_calibration_error_5bin"]<=0.15
    )
    frozen={
        "evaluation_line":line,
        "mode":model["mode"],
        "means":model["means"],
        "stds":model["stds"],
        "weights":model["weights"],
        "l2":model["l2"],
        "learning_rate":model["learning_rate"],
        "epochs":model["epochs"],
    }
    result={
        "schema":"MATRIX_FOOTBALL_EXTENDED_TEAM_MODEL_V2",
        "lane":lane,
        "source_dataset":str(path),
        "source_dataset_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "row_count":len(rows),"train_count":len(train),"validation_count":len(validation),
        "line":line,
        "internal_selection":{
            "trial_count":len(trials),
            "selected":selected,
            "validation_set_used_for_selection":False,
        },
        "model_parameters":frozen,
        "model_parameters_sha256":_sha(frozen),
        "validation":{
            "baseline":bm,"challenger":cm,
            "delta_brier_challenger_minus_baseline":db,
            "delta_log_loss_challenger_minus_baseline":dl,
            "gate_passed":pass_gate,
        },
        "status":"FROZEN_FOR_NEW_PROSPECTIVE_VALIDATION" if pass_gate else "REJECTED_HISTORICAL_OOS_V2",
        "prospective_eligible":pass_gate,
        "prospective_gates":[30,50,100,200] if pass_gate else [],
        "validation_used_for_parameter_tuning":False,
        "odds_used_to_generate_probability":False,
        "p_matrix_generated":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    if lane=="TEAM_YELLOW_CARDS":
        result["semantic_gate"]="YELLOW_CARDS_ONLY_FOUNDATION_NOT_FULL_CARD_SETTLEMENT"
    if lane=="TEAM_GOALKEEPER_SAVES":
        result["semantic_gate"]="TEAM_AGGREGATE_FOUNDATION_NOT_INDIVIDUAL_GOALKEEPER_PROP"
    if lane=="TEAM_FOULS":
        result["semantic_gate"]="FOUNDATION_LANE_REQUIRES_BOOKMAKER_SCOPE_BINDING"
    return result


def main():
    root=Path("evidence/api_football/market_expansion/team_pit")
    out=Path("evidence/api_football/market_expansion/team_models_v2")
    out.mkdir(parents=True,exist_ok=True)
    paths={
        "CORNERS":root/"corners_pit.jsonl",
        "TEAM_SHOTS_ON_TARGET":root/"team_shots_on_target_pit.jsonl",
        "TEAM_GOALKEEPER_SAVES":root/"team_goalkeeper_saves_pit.jsonl",
        "TEAM_YELLOW_CARDS":root/"team_yellow_cards_pit.jsonl",
        "TEAM_FOULS":root/"team_fouls_pit.jsonl",
    }
    results={}
    for lane,path in paths.items():
        result=build_lane(lane,path)
        results[lane]=result
        (out/f"{lane.casefold()}_model_v2.json").write_text(
            json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8"
        )
    summary={
        "schema":"MATRIX_FOOTBALL_EXTENDED_TEAM_MODELS_V2_SUMMARY",
        "lanes":{k:{
            "status":v["status"],
            "train_count":v["train_count"],
            "validation_count":v["validation_count"],
            "prospective_eligible":v["prospective_eligible"],
        } for k,v in results.items()},
        "selection_policy":"TEMPORAL_INTERNAL_FOLDS_ON_TRAIN_ONLY; FINAL_50_UNTOUCHED_UNTIL_FINAL_EVALUATION",
        "prospective_gates":[30,50,100,200],
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    (out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,sort_keys=True))


if __name__=="__main__":
    main()
