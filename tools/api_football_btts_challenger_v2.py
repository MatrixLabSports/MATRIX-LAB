from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import exp, log
from pathlib import Path
from typing import Any

EPS=1e-12

def _load(p:Path)->dict[str,Any]:
    d=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(d,dict): raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return d

def _sha(x:Any)->str:
    return sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def _clip(p:float)->float: return min(max(float(p),EPS),1-EPS)
def _logit(p:float)->float:
    p=_clip(p); return log(p/(1-p))
def _sigmoid(x:float)->float:
    if x>=0:
        z=exp(-x); return 1/(1+z)
    z=exp(x); return z/(1+z)

def _features(r:dict[str,Any])->list[float]:
    return [
        1.0,
        _logit(float(r["poisson"]["btts"])),
        _logit(float(r["baseline"]["btts"])),
        float(r.get("expected_home_goals",0.0)),
        float(r.get("expected_away_goals",0.0)),
        abs(float(r.get("expected_home_goals",0.0))-float(r.get("expected_away_goals",0.0))),
        min(float(r.get("expected_home_goals",0.0)),float(r.get("expected_away_goals",0.0))),
        float(r.get("home_history_count",0.0))/20.0,
        float(r.get("away_history_count",0.0))/20.0,
    ]

def _predict(w:list[float], r:dict[str,Any])->float:
    x=_features(r)
    return _sigmoid(sum(a*b for a,b in zip(w,x)))

def _metrics(rows:list[dict[str,Any]], probs:list[float])->dict[str,float]:
    b=ll=0.0
    for r,p in zip(rows,probs):
        p=_clip(p); y=1.0 if bool(r["outcome"]["btts"]) else 0.0
        b+=(p-y)**2; ll+=-(y*log(p)+(1-y)*log(1-p))
    n=len(rows)
    return {"sample_size":n,"brier_score":b/n,"log_loss":ll/n}

def _fit(dev:list[dict[str,Any]], lr:float, l2:float, epochs:int)->list[float]:
    d=len(_features(dev[0])); w=[0.0]*d
    n=len(dev)
    for _ in range(epochs):
        g=[0.0]*d
        for r in dev:
            x=_features(r); y=1.0 if bool(r["outcome"]["btts"]) else 0.0
            e=_predict(w,r)-y
            for j in range(d): g[j]+=e*x[j]
        for j in range(d):
            reg=0.0 if j==0 else l2*w[j]
            w[j]-=lr*(g[j]/n+reg)
    return w

def build(root:Path)->dict[str,Any]:
    source=_load(root/"evidence/api_football/model_validation/retrospective_predictions.json")
    seal=_load(root/"evidence/api_football/challenger/final_holdout_seal.json")
    gov_path=root/"evidence/api_football/market_governance/market_governance.json"
    if gov_path.exists():
        gov=_load(gov_path)
    else:
        from tools.api_football_market_governance import build as build_market_governance
        gov=build_market_governance(root)
    rows=sorted(source["rows"],key=lambda r:(r["kickoff_utc"],int(r["fixture_id"])))
    if len(rows)!=2379: raise ValueError("SOURCE_ROW_COUNT_CHANGED")
    dev=rows[:1665]; val=rows[1665:2022]
    forbidden_ids={str(r["fixture_id"]) for r in seal["rows"]}
    train_ids={str(r["fixture_id"]) for r in dev+val}
    overlap=sorted(forbidden_ids & train_ids)
    if overlap: raise ValueError("FINAL_HOLDOUT_CONTAMINATION")
    if len(forbidden_ids)!=357: raise ValueError("FORBIDDEN_HOLDOUT_COUNT_CHANGED")
    if "btts" not in gov["rejected_markets"]: raise ValueError("BTTS_NOT_REJECTED_IN_GOVERNANCE")

    poisson=_metrics(val,[float(r["poisson"]["btts"]) for r in val])
    baseline=_metrics(val,[float(r["baseline"]["btts"]) for r in val])

    trials=[]
    for lr in (0.01,0.03):
        for l2 in (0.001,0.01):
            for epochs in (100,200):
                w=_fit(dev,lr,l2,epochs)
                dm=_metrics(dev,[_predict(w,r) for r in dev])
                trials.append((dm["log_loss"],dm["brier_score"],lr,l2,epochs,w))
    trials.sort(key=lambda x:(x[0],x[1]))
    shortlist=trials[:4]
    selected=None
    for _,_,lr,l2,epochs,w in shortlist:
        vm=_metrics(val,[_predict(w,r) for r in val])
        superiority=vm["brier_score"]<poisson["brier_score"] and vm["log_loss"]<poisson["log_loss"]
        gain=(poisson["brier_score"]-vm["brier_score"])+(poisson["log_loss"]-vm["log_loss"])
        cand={"learning_rate":lr,"l2":l2,"epochs":epochs,"weights":w,"validation":vm,"gain_vs_poisson":gain}
        if superiority and (selected is None or gain>selected["gain_vs_poisson"]):
            selected=cand

    exclusion={
        "schema":"MATRIX_BTTS_FINAL_HOLDOUT_EXCLUSION_V1",
        "source_holdout_seal_sha256":gov["holdout_seal_sha256"],
        "forbidden_fixture_count":len(forbidden_ids),
        "forbidden_fixture_ids":sorted(forbidden_ids,key=int),
        "training_validation_overlap_count":len(overlap),
        "policy":"NEVER_USE_THESE_357_FINAL_HOLDOUT_OUTCOMES_FOR_BTTS_V2_DEVELOPMENT_VALIDATION_OR_TUNING",
    }
    return {
        "schema":"MATRIX_FOOTBALL_BTTS_CHALLENGER_V2",
        "created_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "candidate_name":"btts_logistic_challenger_v2",
        "development_count":len(dev),
        "validation_count":len(val),
        "forbidden_final_holdout_count":len(forbidden_ids),
        "forbidden_final_holdout_outcomes_read":False,
        "forbidden_final_holdout_used_for_training":False,
        "forbidden_final_holdout_used_for_validation":False,
        "exclusion_registry":exclusion,
        "exclusion_registry_sha256":_sha(exclusion),
        "poisson_validation":poisson,
        "baseline_validation":baseline,
        "selected":selected,
        "validation_superiority":selected is not None,
        "candidate_status":"FROZEN_BTTS_V2_AWAITING_NEW_PROSPECTIVE_HOLDOUT" if selected is not None else "REJECTED_ON_VALIDATION",
        "next_holdout_policy":"NEW_PROSPECTIVE_UNSEEN_EVENTS_ONLY; ORIGINAL_357_FINAL_HOLDOUT_PERMANENTLY_EXCLUDED",
        "governed_engine_promoted":False,
        "p_matrix_generated":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }

def main()->None:
    root=Path(".")
    d=build(root)
    out=root/"evidence/api_football/btts_challenger_v2"
    out.mkdir(parents=True,exist_ok=True)
    (out/"exclusion_registry.json").write_text(json.dumps(d["exclusion_registry"],ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    d2=dict(d); d2.pop("exclusion_registry")
    (out/"manifest.json").write_text(json.dumps(d2,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"candidate_status":d["candidate_status"],"validation_superiority":d["validation_superiority"],"poisson_validation":d["poisson_validation"],"selected":d["selected"],"forbidden_final_holdout_count":d["forbidden_final_holdout_count"],"real_money":d["real_money"]},sort_keys=True))
if __name__=="__main__": main()
