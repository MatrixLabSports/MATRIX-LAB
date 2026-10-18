from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from math import exp, log
from pathlib import Path
from typing import Any

from tools.api_football_prediction_store import load_chunked_json

EPS=1e-12
MIN_INITIAL_TRAIN=1200
FOLD_COUNT=3

FEATURE_MODES=("BETA_POISSON","POISSON_BASELINE_BLEND","RICH_LOGISTIC")


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _canonical_sha(value:Any)->str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return sha256(raw).hexdigest()


def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)


def _logit(p:float)->float:
    p=_clip(p)
    return log(p/(1-p))


def _sigmoid(x:float)->float:
    if x>=0:
        z=exp(-x)
        return 1/(1+z)
    z=exp(x)
    return z/(1+z)


def _features(row:dict[str,Any],mode:str)->list[float]:
    pp=_clip(float(row["poisson"]["btts"]))
    bp=_clip(float(row["baseline"]["btts"]))
    eh=float(row.get("expected_home_goals",0.0))
    ea=float(row.get("expected_away_goals",0.0))
    if mode=="BETA_POISSON":
        return [1.0,log(pp),-log(1-pp)]
    if mode=="POISSON_BASELINE_BLEND":
        return [1.0,_logit(pp),_logit(bp)]
    if mode=="RICH_LOGISTIC":
        total=eh+ea
        low=min(eh,ea)
        diff=abs(eh-ea)
        product=eh*ea
        hh=float(row.get("home_history_count",0.0))/20.0
        ah=float(row.get("away_history_count",0.0))/20.0
        return [
            1.0,_logit(pp),_logit(bp),total,low,diff,product,
            total*total,low*low,hh,ah,
        ]
    raise ValueError("UNKNOWN_FEATURE_MODE")


def _predict(weights:list[float],row:dict[str,Any],mode:str)->float:
    x=_features(row,mode)
    return _sigmoid(sum(a*b for a,b in zip(weights,x)))


def _fit(rows:list[dict[str,Any]],mode:str,lr:float,l2:float,epochs:int)->list[float]:
    if not rows:
        raise ValueError("NO_TRAIN_ROWS")
    d=len(_features(rows[0],mode))
    w=[0.0]*d
    n=len(rows)
    for _ in range(epochs):
        grad=[0.0]*d
        for row in rows:
            x=_features(row,mode)
            y=1.0 if bool(row["outcome"]["btts"]) else 0.0
            err=_predict(w,row,mode)-y
            for j in range(d):
                grad[j]+=err*x[j]
        for j in range(d):
            reg=0.0 if j==0 else l2*w[j]
            w[j]-=lr*(grad[j]/n+reg)
    return w


def _metrics(rows:list[dict[str,Any]],probs:list[float])->dict[str,float]:
    if not rows or len(rows)!=len(probs):
        raise ValueError("METRIC_INPUT_INVALID")
    brier=logloss=0.0
    for row,p0 in zip(rows,probs):
        p=_clip(p0)
        y=1.0 if bool(row["outcome"]["btts"]) else 0.0
        brier+=(p-y)**2
        logloss+=-(y*log(p)+(1-y)*log(1-p))
    n=len(rows)
    return {"sample_size":n,"brier_score":brier/n,"log_loss":logloss/n}


def _temporal_folds(rows:list[dict[str,Any]])->list[tuple[list[dict[str,Any]],list[dict[str,Any]]]]:
    n=len(rows)
    if n <= MIN_INITIAL_TRAIN+FOLD_COUNT:
        raise ValueError("INSUFFICIENT_DEVELOPMENT_ROWS")
    remaining=n-MIN_INITIAL_TRAIN
    base=remaining//FOLD_COUNT
    folds=[]
    start=MIN_INITIAL_TRAIN
    for i in range(FOLD_COUNT):
        end=n if i==FOLD_COUNT-1 else start+base
        train=rows[:start]
        test=rows[start:end]
        if not test:
            raise ValueError("EMPTY_TEMPORAL_FOLD")
        folds.append((train,test))
        start=end
    return folds


def _prospective_forbidden_ids(root:Path)->set[str]:
    path=root/"evidence/api_football/prospective_calibration/ledger.jsonl"
    ids=set()
    if not path.exists():
        return ids
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            row=json.loads(raw)
            if row.get("fixture_id") is not None:
                ids.add(str(row["fixture_id"]))
    return ids


def build(root:Path)->dict[str,Any]:
    source=load_chunked_json(root/"evidence/api_football/model_validation/retrospective_predictions_manifest.json")
    seal=_load(root/"evidence/api_football/challenger/final_holdout_seal.json")
    rows=sorted(source["rows"],key=lambda r:(r["kickoff_utc"],int(r["fixture_id"])))
    if len(rows)!=2379:
        raise ValueError("SOURCE_ROW_COUNT_CHANGED")

    final_holdout_ids={str(r["fixture_id"]) for r in seal["rows"]}
    if len(final_holdout_ids)!=357:
        raise ValueError("FINAL_HOLDOUT_COUNT_CHANGED")

    development=[
        r for r in rows
        if str(r["fixture_id"]) not in final_holdout_ids
    ]
    if len(development)!=2022:
        raise ValueError("DEVELOPMENT_COUNT_CHANGED")

    prospective_ids=_prospective_forbidden_ids(root)
    development_ids={str(r["fixture_id"]) for r in development}
    if development_ids & final_holdout_ids:
        raise ValueError("FINAL_HOLDOUT_CONTAMINATION")
    if development_ids & prospective_ids:
        raise ValueError("PROSPECTIVE_CONTAMINATION")

    folds=_temporal_folds(development)
    candidates=[]
    for mode in FEATURE_MODES:
        for lr in (0.01,0.03):
            for l2 in (0.001,0.01):
                fold_rows=[]
                all_test=[]
                all_candidate_probs=[]
                all_poisson_probs=[]
                for idx,(train,test) in enumerate(folds,1):
                    weights=_fit(train,mode,lr,l2,80)
                    cprobs=[_predict(weights,r,mode) for r in test]
                    pprobs=[float(r["poisson"]["btts"]) for r in test]
                    cm=_metrics(test,cprobs)
                    pm=_metrics(test,pprobs)
                    fold_rows.append({
                        "fold":idx,
                        "train_count":len(train),
                        "validation_count":len(test),
                        "train_last_kickoff_utc":train[-1]["kickoff_utc"],
                        "validation_first_kickoff_utc":test[0]["kickoff_utc"],
                        "validation_last_kickoff_utc":test[-1]["kickoff_utc"],
                        "challenger":cm,
                        "poisson":pm,
                        "beats_poisson_brier":cm["brier_score"]<pm["brier_score"],
                        "beats_poisson_log_loss":cm["log_loss"]<pm["log_loss"],
                    })
                    all_test.extend(test)
                    all_candidate_probs.extend(cprobs)
                    all_poisson_probs.extend(pprobs)
                cm_all=_metrics(all_test,all_candidate_probs)
                pm_all=_metrics(all_test,all_poisson_probs)
                pass_brier=cm_all["brier_score"]<pm_all["brier_score"]
                pass_log=cm_all["log_loss"]<pm_all["log_loss"]
                fold_pass_count=sum(
                    1 for f in fold_rows
                    if f["beats_poisson_brier"] and f["beats_poisson_log_loss"]
                )
                candidates.append({
                    "feature_mode":mode,
                    "learning_rate":lr,
                    "l2":l2,
                    "epochs":80,
                    "folds":fold_rows,
                    "aggregate_challenger":cm_all,
                    "aggregate_poisson":pm_all,
                    "delta_brier":cm_all["brier_score"]-pm_all["brier_score"],
                    "delta_log_loss":cm_all["log_loss"]-pm_all["log_loss"],
                    "aggregate_superiority":pass_brier and pass_log,
                    "fold_superiority_count":fold_pass_count,
                })

    eligible=[
        c for c in candidates
        if c["aggregate_superiority"] and c["fold_superiority_count"]>=2
    ]
    eligible.sort(key=lambda c:(c["delta_log_loss"],c["delta_brier"],-c["fold_superiority_count"]))
    selected=eligible[0] if eligible else None

    frozen=None
    if selected is not None:
        weights=_fit(
            development,
            selected["feature_mode"],
            float(selected["learning_rate"]),
            float(selected["l2"]),
            int(selected["epochs"]),
        )
        frozen={
            "feature_mode":selected["feature_mode"],
            "learning_rate":selected["learning_rate"],
            "l2":selected["l2"],
            "epochs":selected["epochs"],
            "weights":weights,
            "weights_sha256":_canonical_sha(weights),
            "development_count":len(development),
            "development_first_kickoff_utc":development[0]["kickoff_utc"],
            "development_last_kickoff_utc":development[-1]["kickoff_utc"],
        }

    created=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    status=(
        "FROZEN_BTTS_V3_AWAITING_NEW_PROSPECTIVE_UNSEEN_EVENTS"
        if frozen is not None
        else "REJECTED_INTERNAL_TEMPORAL_OOS"
    )
    return {
        "schema":"MATRIX_FOOTBALL_BTTS_CHALLENGER_V3",
        "created_at_utc":created,
        "candidate_name":"btts_temporal_calibration_challenger_v3",
        "development_count":len(development),
        "final_holdout_excluded_count":len(final_holdout_ids),
        "prospective_ledger_excluded_count":len(prospective_ids),
        "final_holdout_used_for_tuning":False,
        "prospective_checkpoint_200_used_for_tuning":False,
        "prospective_ledger_used_for_tuning":False,
        "temporal_fold_count":len(folds),
        "selection_policy":"AGGREGATE_BRIER_AND_LOGLOSS_BETTER_THAN_POISSON_AND_AT_LEAST_2_OF_3_FOLDS_BETTER_ON_BOTH",
        "candidates":candidates,
        "selected_internal_oos":selected,
        "frozen_model":frozen,
        "candidate_status":status,
        "prospective_validation_policy":{
            "eligible_event_rule":"EVENT_KICKOFF_AND_FREEZE_MUST_BOTH_BE_AFTER_V3_FREEZE",
            "outcomes_seen_before_freeze_for_prospective_validation":0,
            "gates":[30,50,100,200],
            "parameter_tuning_after_freeze":False,
            "original_357_holdout_reuse":False,
            "checkpoint_200_reuse":False,
        },
        "p_matrix_generated":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main()->None:
    root=Path(".")
    result=build(root)
    out=root/"evidence/api_football/btts_challenger_v3"
    out.mkdir(parents=True,exist_ok=True)
    (out/"manifest.json").write_text(
        json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "candidate_status":result["candidate_status"],
        "development_count":result["development_count"],
        "final_holdout_excluded_count":result["final_holdout_excluded_count"],
        "prospective_ledger_excluded_count":result["prospective_ledger_excluded_count"],
        "selected_internal_oos":result["selected_internal_oos"],
        "frozen_model":result["frozen_model"],
        "real_money":result["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
