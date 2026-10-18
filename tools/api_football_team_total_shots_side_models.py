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
SIDES=("HOME","AWAY")


def _load_jsonl(path:Path)->list[dict[str,Any]]:
    rows=[json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return sorted(rows,key=lambda r:(str(r["kickoff_utc"]),str(r["fixture_id"])))


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
    if not ys or len(ys)!=len(ps):
        raise ValueError("INVALID_METRIC_INPUT")
    brier=ll=0.0
    bins=[[] for _ in range(5)]
    for y,p0 in zip(ys,ps):
        p=_clip(p0)
        brier+=(p-y)**2
        ll+=-(y*log(p)+(1-y)*log(1-p))
        bins[min(4,int(p*5))].append((y,p))
    n=len(ys); ece=0.0; maxe=0.0
    for b in bins:
        if not b: continue
        obs=sum(y for y,_ in b)/len(b)
        pred=sum(p for _,p in b)/len(b)
        err=abs(obs-pred)
        ece+=len(b)/n*err
        maxe=max(maxe,err)
    return {"sample_size":n,"brier_score":brier/n,"log_loss":ll/n,"ece_5bin":ece,"max_calibration_error_5bin":maxe}


def _folds(rows:list[dict[str,Any]])->list[tuple[list[dict[str,Any]],list[dict[str,Any]]]]:
    n=len(rows)
    initial=max(140,int(n*0.62))
    rem=n-initial
    if rem<30:
        raise ValueError("INSUFFICIENT_INTERNAL_TEMPORAL_OOS")
    widths=[rem//3,rem//3]
    widths.append(rem-sum(widths))
    out=[]; pos=initial
    for width in widths:
        out.append((rows[:pos],rows[pos:pos+width]))
        pos+=width
    return out


def _side_keys(side:str)->dict[str,str]:
    if side=="HOME":
        return {
            "target":"target_home","expected":"expected_home",
            "for_mean":"home_for_mean","against_mean":"away_against_mean",
            "own_hist":"home_history_count","opp_hist":"away_history_count",
        }
    if side=="AWAY":
        return {
            "target":"target_away","expected":"expected_away",
            "for_mean":"away_for_mean","against_mean":"home_against_mean",
            "own_hist":"away_history_count","opp_hist":"home_history_count",
        }
    raise ValueError("UNKNOWN_SIDE")


def _raw_features(row:dict[str,Any],side:str,mode:str)->list[float]:
    k=_side_keys(side)
    expected=max(0.05,float(row[k["expected"]]))
    if mode=="EXPECTED_ONLY":
        return [expected]
    if mode=="SIDE_STRENGTH":
        return [
            expected,
            float(row[k["for_mean"]]),
            float(row[k["against_mean"]]),
            float(row["expected_total"]),
        ]
    if mode=="SIDE_STRENGTH_HISTORY":
        return [
            expected,
            float(row[k["for_mean"]]),
            float(row[k["against_mean"]]),
            float(row["expected_total"]),
            float(row[k["own_hist"]]),
            float(row[k["opp_hist"]]),
            1.0 if str(row.get("league_id"))=="252" else 0.0,
        ]
    raise ValueError("UNKNOWN_MODE")


def _fit_scaler(rows:list[dict[str,Any]],side:str,mode:str)->tuple[list[float],list[float]]:
    matrix=[_raw_features(r,side,mode) for r in rows]
    d=len(matrix[0])
    means=[sum(x[j] for x in matrix)/len(matrix) for j in range(d)]
    stds=[]
    for j in range(d):
        var=sum((x[j]-means[j])**2 for x in matrix)/len(matrix)
        stds.append(max(var**0.5,1e-6))
    return means,stds


def _x(row:dict[str,Any],side:str,mode:str,means:list[float],stds:list[float])->list[float]:
    raw=_raw_features(row,side,mode)
    return [1.0]+[(a-m)/s for a,m,s in zip(raw,means,stds)]


def _fit_poisson_glm(rows:list[dict[str,Any]],side:str,mode:str,l2:float,lr:float=0.01,epochs:int=500)->dict[str,Any]:
    k=_side_keys(side)
    means,stds=_fit_scaler(rows,side,mode)
    w=[log(max(0.05,sum(float(r[k["target"]]) for r in rows)/len(rows)))]+[0.0]*len(means)
    n=len(rows)
    for _ in range(epochs):
        g=[0.0]*len(w)
        for row in rows:
            z=sum(a*b for a,b in zip(w,_x(row,side,mode,means,stds)))
            mu=min(max(exp(min(max(z,-6.0),6.0)),0.05),100.0)
            y=float(row[k["target"]])
            err=mu-y
            xx=_x(row,side,mode,means,stds)
            for j in range(len(w)):
                g[j]+=err*xx[j]
        for j in range(len(w)):
            reg=0.0 if j==0 else l2*w[j]
            w[j]-=lr*(g[j]/n+reg)
    return {"family":"POISSON_GLM","side":side,"mode":mode,"means":means,"stds":stds,"weights":w,"l2":l2,"learning_rate":lr,"epochs":epochs}


def _predict_mu(row:dict[str,Any],model:dict[str,Any])->float:
    z=sum(a*b for a,b in zip(model["weights"],_x(row,model["side"],model["mode"],model["means"],model["stds"])))
    return min(max(exp(min(max(z,-6.0),6.0)),0.05),100.0)


def _raw_expected_reference_mu(row:dict[str,Any],side:str)->float:
    return max(0.05,float(row[_side_keys(side)["expected"]]))


def _sha(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def _evaluation_line(train:list[dict[str,Any]],side:str)->float:
    target=_side_keys(side)["target"]
    return floor(float(median([float(r[target]) for r in train])))+0.5


def _evaluate(rows:list[dict[str,Any]],side:str,line:float,model:dict[str,Any],base_rate:float)->dict[str,Any]:
    k=_side_keys(side)
    ys=[int(float(r[k["target"]])>line) for r in rows]
    challenger=[_poisson_over(_predict_mu(r,model),line) for r in rows]
    raw_reference=[_poisson_over(_raw_expected_reference_mu(r,side),line) for r in rows]
    constant=[base_rate]*len(rows)
    return {
        "challenger":_metrics(ys,challenger),
        "raw_expected_poisson_reference":_metrics(ys,raw_reference),
        "constant_train_base_rate":_metrics(ys,constant),
    }


def build_side(side:str,rows:list[dict[str,Any]])->dict[str,Any]:
    train=[r for r in rows if r.get("split")=="TRAIN"]
    val=[r for r in rows if r.get("split")=="VALIDATION"]
    if len(train)<MIN_TRAIN or len(val)<MIN_VALIDATION:
        raise ValueError("INSUFFICIENT_SIDE_DATA")
    line=_evaluation_line(train,side)
    target=_side_keys(side)["target"]

    trials=[]
    for mode in ("EXPECTED_ONLY","SIDE_STRENGTH","SIDE_STRENGTH_HISTORY"):
        for l2 in (0.001,0.01,0.1):
            ys=[]; ps=[]; refs=[]; consts=[]; fold_records=[]
            for fold_no,(fit_rows,test_rows) in enumerate(_folds(train),1):
                model=_fit_poisson_glm(fit_rows,side,mode,l2)
                base=sum(int(float(r[target])>line) for r in fit_rows)/len(fit_rows)
                ev=_evaluate(test_rows,side,line,model,base)
                k=_side_keys(side)
                y=[int(float(r[k["target"]])>line) for r in test_rows]
                cp=[_poisson_over(_predict_mu(r,model),line) for r in test_rows]
                rp=[_poisson_over(_raw_expected_reference_mu(r,side),line) for r in test_rows]
                bp=[base]*len(test_rows)
                ys.extend(y); ps.extend(cp); refs.extend(rp); consts.extend(bp)
                fold_records.append({"fold":fold_no,"train_count":len(fit_rows),"validation_count":len(test_rows),**ev})
            cm=_metrics(ys,ps); rm=_metrics(ys,refs); bm=_metrics(ys,consts)
            trials.append({
                "mode":mode,"l2":l2,
                "internal_challenger":cm,
                "internal_raw_expected_poisson_reference":rm,
                "internal_constant_base_rate":bm,
                "delta_brier_vs_raw":cm["brier_score"]-rm["brier_score"],
                "delta_log_loss_vs_raw":cm["log_loss"]-rm["log_loss"],
                "folds":fold_records,
            })
    trials.sort(key=lambda x:(x["internal_challenger"]["log_loss"],x["internal_challenger"]["brier_score"]))
    selected=trials[0]
    model=_fit_poisson_glm(train,side,selected["mode"],float(selected["l2"]))
    base=sum(int(float(r[target])>line) for r in train)/len(train)
    ev=_evaluate(val,side,line,model,base)
    cm=ev["challenger"]; rm=ev["raw_expected_poisson_reference"]; bm=ev["constant_train_base_rate"]
    pass_gate=(
        cm["brier_score"]<rm["brier_score"] and cm["log_loss"]<rm["log_loss"]
        and cm["brier_score"]<bm["brier_score"] and cm["log_loss"]<bm["log_loss"]
        and cm["ece_5bin"]<=0.10 and cm["max_calibration_error_5bin"]<=0.20
    )
    market_binding={
        "HOME":{"api_football_bet_id":221,"api_football_bet_name":"Shots. Home Total"},
        "AWAY":{"api_football_bet_id":220,"api_football_bet_name":"Shots. Away Total"},
    }[side]
    frozen={
        **model,
        "historical_evaluation_line":line,
        "train_base_rate_at_evaluation_line":base,
        "arbitrary_half_line_probability_supported":True,
    }
    return {
        "schema":"MATRIX_TEAM_TOTAL_SHOTS_SIDE_MODEL_V1",
        "lane":f"TEAM_TOTAL_SHOTS_{side}",
        "side":side,
        "market_binding":market_binding,
        "bookmaker_scope_alignment_certified":True,
        "source_dataset":"evidence/api_football/market_expansion/team_pit/team_total_shots_pit.jsonl",
        "row_count":len(rows),"train_count":len(train),"validation_count":len(val),
        "historical_evaluation_line":line,
        "internal_selection":{
            "selection_rows":len(train),
            "trial_count":len(trials),
            "selected":{"mode":selected["mode"],"l2":selected["l2"],"internal_challenger":selected["internal_challenger"],"internal_raw_expected_poisson_reference":selected["internal_raw_expected_poisson_reference"]},
            "final_validation_used_for_selection":False,
        },
        "model_parameters":frozen,
        "model_parameters_sha256":_sha(frozen),
        "validation":{
            **ev,
            "delta_brier_challenger_minus_raw":cm["brier_score"]-rm["brier_score"],
            "delta_log_loss_challenger_minus_raw":cm["log_loss"]-rm["log_loss"],
            "delta_brier_challenger_minus_constant":cm["brier_score"]-bm["brier_score"],
            "delta_log_loss_challenger_minus_constant":cm["log_loss"]-bm["log_loss"],
            "gate_passed":pass_gate,
        },
        "status":"FROZEN_FOR_NEW_PROSPECTIVE_VALIDATION" if pass_gate else "REJECTED_HISTORICAL_OOS_SIDE_V1",
        "prospective_eligible":pass_gate,
        "prospective_gates":[30,50,100,200] if pass_gate else [],
        "validation_used_for_parameter_tuning":False,
        "odds_used_to_generate_probability":False,
        "p_matrix_generated":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main()->None:
    src=Path("evidence/api_football/market_expansion/team_pit/team_total_shots_pit.jsonl")
    rows=_load_jsonl(src)
    out=Path("evidence/api_football/market_expansion/team_total_shots_side_models")
    out.mkdir(parents=True,exist_ok=True)
    results={side:build_side(side,rows) for side in SIDES}
    for side,result in results.items():
        (out/f"{side.casefold()}_model.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    summary={
        "schema":"MATRIX_TEAM_TOTAL_SHOTS_SIDE_MODELS_SUMMARY_V1",
        "source_dataset_sha256":hashlib.sha256(src.read_bytes()).hexdigest(),
        "lanes":{side:{
            "status":r["status"],"line":r["historical_evaluation_line"],
            "prospective_eligible":r["prospective_eligible"],
            "binding":r["market_binding"],
            "validation":r["validation"],
        } for side,r in results.items()},
        "selection_policy":"TEMPORAL_INTERNAL_FOLDS_ON_TRAIN_ONLY; FINAL_50_UNTOUCHED_UNTIL_FINAL_EVALUATION",
        "arbitrary_half_line_probability_supported":True,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    (out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,sort_keys=True))


if __name__=="__main__":
    main()
