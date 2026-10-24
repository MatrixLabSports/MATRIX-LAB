from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.api_football_extended_team_models import _choose_line, _metrics
from tools.api_football_extended_team_models_v2 import _fit, _folds, _predict

LANE="TEAM_SHOTS_ON_TARGET"
MIN_TRAIN=200
MIN_VALIDATION=50


def _load_jsonl(path:Path)->list[dict[str,Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _clip(p:float)->float:
    return min(max(float(p),1e-9),1-1e-9)


def _calibrate(p:float,base:float,gamma:float)->float:
    return _clip(base+gamma*(float(p)-base))


def _sha(value:Any)->str:
    return hashlib.sha256(
        json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    ).hexdigest()


def build(path:Path)->dict[str,Any]:
    rows=_load_jsonl(path)
    train=[r for r in rows if r.get("split")=="TRAIN"]
    validation=[r for r in rows if r.get("split")=="VALIDATION"]
    if len(train)<MIN_TRAIN or len(validation)<MIN_VALIDATION:
        raise ValueError("INSUFFICIENT_TEAM_SOT_SAMPLE")
    line=_choose_line(train)

    # Reproduce the v2 raw model selection on TRAIN only.
    raw_trials=[]
    for mode in ("EXPECTED_ONLY","TEAM_STRENGTH","TEAM_STRENGTH_LEAGUE"):
        for l2 in (0.001,0.01,0.1):
            all_y=[]; all_p=[]
            for fit_rows,test_rows in _folds(train):
                model=_fit(fit_rows,line,mode,l2)
                all_y.extend(int(float(r["target_total"])>line) for r in test_rows)
                all_p.extend(_predict(r,model) for r in test_rows)
            metric=_metrics(all_y,all_p)
            raw_trials.append({
                "mode":mode,"l2":l2,
                "internal_metric":metric,
                "oof_y":all_y,"oof_p":all_p,
            })
    raw_trials.sort(key=lambda t:(t["internal_metric"]["log_loss"],t["internal_metric"]["brier_score"]))
    selected_raw=raw_trials[0]

    oof_y=selected_raw["oof_y"]
    oof_p=selected_raw["oof_p"]
    base=sum(oof_y)/len(oof_y)
    calibration_trials=[]
    for gamma in (0.25,0.40,0.55,0.70,0.85,1.0,1.15):
        probs=[_calibrate(p,base,gamma) for p in oof_p]
        metric=_metrics(oof_y,probs)
        calibration_trials.append({"gamma":gamma,"metric":metric})
    calibration_trials.sort(
        key=lambda t:(
            t["metric"]["log_loss"],
            t["metric"]["brier_score"],
            t["metric"]["ece_5bin"],
        )
    )
    selected_cal=calibration_trials[0]

    raw_model=_fit(
        train,line,
        selected_raw["mode"],
        float(selected_raw["l2"]),
    )
    raw_val=[_predict(r,raw_model) for r in validation]
    calibrated=[
        _calibrate(p,base,float(selected_cal["gamma"]))
        for p in raw_val
    ]
    ys=[int(float(r["target_total"])>line) for r in validation]
    train_base=sum(int(float(r["target_total"])>line) for r in train)/len(train)
    baseline=_metrics(ys,[train_base]*len(ys))
    challenger=_metrics(ys,calibrated)
    db=challenger["brier_score"]-baseline["brier_score"]
    dl=challenger["log_loss"]-baseline["log_loss"]
    passed=(
        db<0 and dl<0
        and challenger["ece_5bin"]<=0.08
        and challenger["max_calibration_error_5bin"]<=0.15
    )
    frozen={
        "evaluation_line":line,
        "raw_mode":selected_raw["mode"],
        "raw_l2":selected_raw["l2"],
        "raw_model":raw_model,
        "oof_prevalence":base,
        "calibration_gamma":selected_cal["gamma"],
    }
    return {
        "schema":"MATRIX_FOOTBALL_TEAM_SOT_CHALLENGER_V3",
        "lane":LANE,
        "source_dataset":str(path),
        "source_dataset_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "train_count":len(train),
        "validation_count":len(validation),
        "evaluation_line":line,
        "selection":{
            "raw_model_selected_on_train_oof_only":True,
            "calibrator_selected_on_train_oof_only":True,
            "final_validation_used_for_selection":False,
            "selected_raw":{
                "mode":selected_raw["mode"],
                "l2":selected_raw["l2"],
                "internal_metric":selected_raw["internal_metric"],
            },
            "selected_calibration":selected_cal,
        },
        "frozen_parameters":frozen,
        "frozen_parameters_sha256":_sha(frozen),
        "validation":{
            "baseline":baseline,
            "challenger":challenger,
            "delta_brier_challenger_minus_baseline":db,
            "delta_log_loss_challenger_minus_baseline":dl,
            "gate_passed":passed,
        },
        "status":"FROZEN_FOR_NEW_PROSPECTIVE_VALIDATION" if passed else "REJECTED_HISTORICAL_OOS_V3",
        "prospective_eligible":passed,
        "prospective_gates":[30,50,100,200] if passed else [],
        "parameter_tuning_after_freeze":False,
        "odds_used_to_generate_probability":False,
        "p_matrix_generated":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main():
    result=build(Path("evidence/api_football/market_expansion/team_pit/team_shots_on_target_pit.jsonl"))
    out=Path("evidence/api_football/market_expansion/team_sot_v3")
    out.mkdir(parents=True,exist_ok=True)
    (out/"manifest.json").write_text(
        json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status":result["status"],
        "train_count":result["train_count"],
        "validation_count":result["validation_count"],
        "validation":result["validation"],
        "prospective_eligible":result["prospective_eligible"],
        "real_money":result["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
