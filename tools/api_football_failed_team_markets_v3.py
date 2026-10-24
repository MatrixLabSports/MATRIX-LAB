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
LANES={
    "CORNERS":"corners_pit.jsonl",
    "TEAM_SHOTS_ON_TARGET":"team_shots_on_target_pit.jsonl",
    "TEAM_GOALKEEPER_SAVES":"team_goalkeeper_saves_pit.jsonl",
    "TEAM_YELLOW_CARDS":"team_yellow_cards_pit.jsonl",
    "TEAM_FOULS":"team_fouls_pit.jsonl",
}


def _load_jsonl(path:Path)->list[dict[str,Any]]:
    rows=[json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return sorted(rows,key=lambda r:(str(r["kickoff_utc"]),str(r["fixture_id"])))


def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)


def _poisson_over(mu:float,line:float)->float:
    mu=max(0.05,float(mu)); cut=int(floor(line))
    term=exp(-mu); cdf=term
    for k in range(1,cut+1):
        term*=mu/k; cdf+=term
    return _clip(1-cdf)


def _nb_over(mu:float,r:float,line:float)->float:
    mu=max(0.05,float(mu)); r=max(0.05,float(r)); cut=int(floor(line))
    q=mu/(r+mu)
    term=(r/(r+mu))**r
    cdf=term
    for k in range(1,cut+1):
        term*=((k-1+r)/k)*q
        cdf+=term
    return _clip(1-cdf)


def _metrics(ys:list[int],ps:list[float])->dict[str,float]:
    if not ys or len(ys)!=len(ps):
        raise ValueError("INVALID_METRICS")
    brier=ll=0.0; bins=[[] for _ in range(5)]
    for y,p0 in zip(ys,ps):
        p=_clip(p0); brier+=(p-y)**2
        ll+=-(y*log(p)+(1-y)*log(1-p))
        bins[min(4,int(p*5))].append((y,p))
    n=len(ys); ece=0.0; mx=0.0
    for b in bins:
        if not b: continue
        obs=sum(y for y,_ in b)/len(b)
        pred=sum(p for _,p in b)/len(b)
        err=abs(obs-pred)
        ece+=len(b)/n*err; mx=max(mx,err)
    return {"sample_size":n,"brier_score":brier/n,"log_loss":ll/n,"ece_5bin":ece,"max_calibration_error_5bin":mx}


def _folds(rows:list[dict[str,Any]]):
    n=len(rows); initial=max(140,int(n*0.62)); rem=n-initial
    widths=[rem//3,rem//3]; widths.append(rem-sum(widths))
    out=[]; pos=initial
    for width in widths:
        out.append((rows[:pos],rows[pos:pos+width])); pos+=width
    return out


def _line(train:list[dict[str,Any]])->float:
    return floor(float(median([float(r["target_total"]) for r in train])))+0.5


def _fit_mean(train:list[dict[str,Any]],alpha:float)->dict[str,float]:
    targets=[float(r["target_total"]) for r in train]
    expected=[max(0.05,float(r["expected_total"])) for r in train]
    target_mean=sum(targets)/len(targets)
    scale=sum(targets)/sum(expected)
    return {"alpha":alpha,"scale":scale,"target_mean":target_mean}


def _mu(row:dict[str,Any],m:dict[str,float])->float:
    raw=max(0.05,float(row["expected_total"]))
    return max(0.05,m["alpha"]*(m["scale"]*raw)+(1-m["alpha"])*m["target_mean"])


def _evaluate(rows:list[dict[str,Any]],line:float,m:dict[str,float],dispersion:float,base:float):
    ys=[int(float(r["target_total"])>line) for r in rows]
    nb=[_nb_over(_mu(r,m),dispersion,line) for r in rows]
    raw=[_poisson_over(max(0.05,float(r["expected_total"])),line) for r in rows]
    const=[base]*len(rows)
    return {"challenger":_metrics(ys,nb),"raw_expected_poisson_reference":_metrics(ys,raw),"constant_train_base_rate":_metrics(ys,const)}


def _sha(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def build_lane(lane:str,path:Path)->dict[str,Any]:
    rows=_load_jsonl(path)
    train=[r for r in rows if r.get("split")=="TRAIN"]
    val=[r for r in rows if r.get("split")=="VALIDATION"]
    if len(train)<MIN_TRAIN or len(val)<MIN_VALIDATION:
        return {"schema":"MATRIX_FAILED_TEAM_MARKET_CHALLENGER_V3","lane":lane,"status":"SEALED_INSUFFICIENT_OOS","prospective_eligible":False,"real_money":"BLOCKED"}
    line=_line(train)
    trials=[]
    for alpha in (0.25,0.50,0.75,1.0):
        for dispersion in (1.5,2.5,5.0,10.0,25.0,100.0):
            ys=[]; cps=[]; rps=[]; bps=[]; fold_records=[]
            for fold_no,(fit_rows,test_rows) in enumerate(_folds(train),1):
                m=_fit_mean(fit_rows,alpha)
                base=sum(int(float(r["target_total"])>line) for r in fit_rows)/len(fit_rows)
                ev=_evaluate(test_rows,line,m,dispersion,base)
                yy=[int(float(r["target_total"])>line) for r in test_rows]
                cp=[_nb_over(_mu(r,m),dispersion,line) for r in test_rows]
                rp=[_poisson_over(max(0.05,float(r["expected_total"])),line) for r in test_rows]
                ys.extend(yy); cps.extend(cp); rps.extend(rp); bps.extend([base]*len(test_rows))
                fold_records.append({"fold":fold_no,"train_count":len(fit_rows),"validation_count":len(test_rows),**ev})
            cm=_metrics(ys,cps); rm=_metrics(ys,rps); bm=_metrics(ys,bps)
            trials.append({
                "alpha":alpha,"dispersion_r":dispersion,
                "internal_challenger":cm,"internal_raw_expected_poisson_reference":rm,"internal_constant_base_rate":bm,
                "delta_brier_vs_raw":cm["brier_score"]-rm["brier_score"],
                "delta_log_loss_vs_raw":cm["log_loss"]-rm["log_loss"],
                "folds":fold_records,
            })
    trials.sort(key=lambda x:(x["internal_challenger"]["log_loss"],x["internal_challenger"]["brier_score"]))
    selected=trials[0]
    m=_fit_mean(train,float(selected["alpha"]))
    base=sum(int(float(r["target_total"])>line) for r in train)/len(train)
    ev=_evaluate(val,line,m,float(selected["dispersion_r"]),base)
    cm=ev["challenger"]; rm=ev["raw_expected_poisson_reference"]; bm=ev["constant_train_base_rate"]
    pass_gate=(
        cm["brier_score"]<rm["brier_score"] and cm["log_loss"]<rm["log_loss"]
        and cm["brier_score"]<bm["brier_score"] and cm["log_loss"]<bm["log_loss"]
        and cm["ece_5bin"]<=0.10 and cm["max_calibration_error_5bin"]<=0.20
    )
    frozen={"family":"NEGATIVE_BINOMIAL_SHRUNK_EXPECTED","evaluation_line":line,"alpha":selected["alpha"],"dispersion_r":selected["dispersion_r"],**m}
    result={
        "schema":"MATRIX_FAILED_TEAM_MARKET_CHALLENGER_V3",
        "lane":lane,"source_dataset":str(path),"source_dataset_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "row_count":len(rows),"train_count":len(train),"validation_count":len(val),"evaluation_line":line,
        "internal_selection":{
            "trial_count":len(trials),
            "selected":{"alpha":selected["alpha"],"dispersion_r":selected["dispersion_r"],"internal_challenger":selected["internal_challenger"],"internal_raw_expected_poisson_reference":selected["internal_raw_expected_poisson_reference"]},
            "final_validation_used_for_selection":False,
        },
        "model_parameters":frozen,"model_parameters_sha256":_sha(frozen),
        "validation":{
            **ev,
            "delta_brier_challenger_minus_raw":cm["brier_score"]-rm["brier_score"],
            "delta_log_loss_challenger_minus_raw":cm["log_loss"]-rm["log_loss"],
            "delta_brier_challenger_minus_constant":cm["brier_score"]-bm["brier_score"],
            "delta_log_loss_challenger_minus_constant":cm["log_loss"]-bm["log_loss"],
            "gate_passed":pass_gate,
        },
        "status":"FROZEN_FOR_NEW_PROSPECTIVE_VALIDATION_V3" if pass_gate else "REJECTED_HISTORICAL_OOS_V3",
        "prospective_eligible":pass_gate,
        "prospective_gates":[30,50,100,200] if pass_gate else [],
        "validation_used_for_parameter_tuning":False,
        "odds_used_to_generate_probability":False,
        "p_matrix_generated":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    if lane=="TEAM_YELLOW_CARDS":
        result["semantic_gate"]="YELLOW_CARDS_ONLY_NOT_FULL_CARD_MARKET"
    if lane=="TEAM_GOALKEEPER_SAVES":
        result["semantic_gate"]="TEAM_AGGREGATE_NOT_INDIVIDUAL_KEEPER_PROP"
    return result


def main()->None:
    root=Path("evidence/api_football/market_expansion/team_pit")
    out=Path("evidence/api_football/market_expansion/failed_team_markets_v3")
    out.mkdir(parents=True,exist_ok=True)
    results={}
    for lane,filename in LANES.items():
        r=build_lane(lane,root/filename); results[lane]=r
        (out/f"{lane.casefold()}_model_v3.json").write_text(json.dumps(r,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    summary={
        "schema":"MATRIX_FAILED_TEAM_MARKETS_V3_SUMMARY",
        "lanes":{k:{"status":v["status"],"prospective_eligible":v["prospective_eligible"],"validation":v.get("validation")} for k,v in results.items()},
        "challenger_family":"NEGATIVE_BINOMIAL_SHRUNK_EXPECTED",
        "selection_policy":"TEMPORAL_INTERNAL_FOLDS_ON_TRAIN_ONLY; FINAL_50_UNTOUCHED_UNTIL_FINAL_EVALUATION",
        "automatic_wagering":False,"real_money":"BLOCKED"
    }
    (out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,sort_keys=True))


if __name__=="__main__":
    main()
