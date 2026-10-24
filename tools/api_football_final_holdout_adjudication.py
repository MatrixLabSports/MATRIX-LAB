from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from math import exp, log
from pathlib import Path

from tools.api_football_prediction_store import load_chunked_json
from typing import Any, Mapping

EPS=1e-12


def _load(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _canonical_sha(payload: Any) -> str:
    return sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()


def _clip(p: float) -> float:
    return min(max(float(p),EPS),1.0-EPS)


def _logit(p: float) -> float:
    p=_clip(p)
    return log(p/(1.0-p))


def _sigmoid(x: float) -> float:
    if x>=0:
        z=exp(-x)
        return 1.0/(1.0+z)
    z=exp(x)
    return z/(1.0+z)


def _mc_pool(row: Mapping[str,Any],a:float,c:float)->dict[str,float]:
    scores={}
    for k in ("H","D","A"):
        pp=max(float(row["poisson"]["1x2"][k]),EPS)
        bp=max(float(row["baseline"]["1x2"][k]),EPS)
        scores[k]=exp(a*log(pp)+c*log(bp))
    s=sum(scores.values())
    return {k:v/s for k,v in scores.items()}


def _bin_pool(row: Mapping[str,Any],market:str,a:float,c:float,b:float)->float:
    return _sigmoid(a*_logit(float(row["poisson"][market]))+c*_logit(float(row["baseline"][market]))+b)


def _mc_metrics(rows:list[dict[str,Any]], probs:list[dict[str,float]])->dict[str,float]:
    brier=ll=0.0
    correct=0
    for row,p in zip(rows,probs):
        actual=row["outcome"]["1x2"]
        for k in ("H","D","A"):
            y=1.0 if actual==k else 0.0
            brier+=(p[k]-y)**2
        ll+=-log(max(p[actual],EPS))
        correct+=int(max(("H","D","A"),key=lambda k:p[k])==actual)
    n=len(rows)
    return {"sample_size":n,"brier_score":brier/n,"log_loss":ll/n,"accuracy":correct/n}


def _bin_metrics(rows:list[dict[str,Any]], probs:list[float], market:str)->dict[str,float]:
    brier=ll=0.0
    for row,p in zip(rows,probs):
        p=_clip(p)
        y=1.0 if bool(row["outcome"][market]) else 0.0
        brier+=(p-y)**2
        ll+=-(y*log(p)+(1.0-y)*log(1.0-p))
    n=len(rows)
    return {"sample_size":n,"brier_score":brier/n,"log_loss":ll/n}


def _sealed_projection(row: Mapping[str,Any])->dict[str,Any]:
    return {
        "fixture_id":row["fixture_id"],
        "kickoff_utc":row["kickoff_utc"],
        "league_id":row["league_id"],
        "season":row["season"],
        "poisson":row["poisson"],
        "baseline":row["baseline"],
    }


def adjudicate(root:Path)->dict[str,Any]:
    manifest=_load(root/"evidence/api_football/challenger/challenger_manifest.json")
    seal=_load(root/"evidence/api_football/challenger/final_holdout_seal.json")
    source=load_chunked_json(root/"evidence/api_football/model_validation/retrospective_predictions_manifest.json")

    if manifest.get("candidate_status")!="FROZEN_CHALLENGER_AWAITING_FINAL_HOLDOUT":
        raise ValueError("CHALLENGER_NOT_FROZEN_FOR_HOLDOUT")
    if manifest.get("holdout_outcomes_read") is not False or manifest.get("holdout_metrics_computed") is not False:
        raise ValueError("HOLDOUT_ALREADY_OPENED_IN_MANIFEST")
    expected_sha=str(manifest.get("holdout_seal_sha256") or "")
    actual_sha=_canonical_sha(seal)
    if actual_sha!=expected_sha:
        raise ValueError("HOLDOUT_SEAL_SHA_MISMATCH")

    rows=source.get("rows")
    if not isinstance(rows,list):
        raise ValueError("SOURCE_ROWS_MISSING")
    rows=sorted(rows,key=lambda r:(r["kickoff_utc"],int(r["fixture_id"])))
    n=int(manifest["final_holdout_count"])
    holdout=rows[-n:]
    sealed_rows=seal.get("rows")
    if not isinstance(sealed_rows,list) or len(sealed_rows)!=n or len(holdout)!=n:
        raise ValueError("HOLDOUT_COUNT_MISMATCH")
    projected=[_sealed_projection(r) for r in holdout]
    if projected!=sealed_rows:
        raise ValueError("HOLDOUT_IDENTITY_OR_INPUT_MISMATCH")

    fp=manifest.get("frozen_parameters")
    if not isinstance(fp,dict) or set(fp)!={"1x2","over_2_5","btts"}:
        raise ValueError("FROZEN_PARAMETERS_INCOMPLETE")

    p1=fp["1x2"]
    ch1=[_mc_pool(r,float(p1["a"]),float(p1["c"])) for r in holdout]
    po1=[r["poisson"]["1x2"] for r in holdout]
    ba1=[r["baseline"]["1x2"] for r in holdout]
    r1={"challenger":_mc_metrics(holdout,ch1),"poisson":_mc_metrics(holdout,po1),"baseline":_mc_metrics(holdout,ba1)}

    reports={"1x2":r1}
    for market in ("over_2_5","btts"):
        p=fp[market]
        cp=[_bin_pool(r,market,float(p["a"]),float(p["c"]),float(p["b"])) for r in holdout]
        pp=[float(r["poisson"][market]) for r in holdout]
        bp=[float(r["baseline"][market]) for r in holdout]
        reports[market]={
            "challenger":_bin_metrics(holdout,cp,market),
            "poisson":_bin_metrics(holdout,pp,market),
            "baseline":_bin_metrics(holdout,bp,market),
        }

    for market,row in reports.items():
        row["delta_brier_challenger_minus_poisson"]=row["challenger"]["brier_score"]-row["poisson"]["brier_score"]
        row["delta_log_loss_challenger_minus_poisson"]=row["challenger"]["log_loss"]-row["poisson"]["log_loss"]
        row["beats_poisson_brier"]=row["delta_brier_challenger_minus_poisson"]<0
        row["beats_poisson_log_loss"]=row["delta_log_loss_challenger_minus_poisson"]<0
        row["market_superiority"]=row["beats_poisson_brier"] and row["beats_poisson_log_loss"]

    all_superior=all(row["market_superiority"] for row in reports.values())
    return {
        "schema":"MATRIX_FOOTBALL_FINAL_HOLDOUT_ADJUDICATION_V1",
        "adjudicated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "challenger_name":manifest["challenger_name"],
        "source_candidate_manifest_created_at_utc":manifest["created_at_utc"],
        "frozen_parameters":fp,
        "holdout_seal_sha256_verified":actual_sha,
        "holdout_row_count":n,
        "holdout_identity_match":True,
        "parameter_refit_performed":False,
        "parameter_search_performed":False,
        "holdout_open_count":1,
        "metrics":reports,
        "all_three_markets_holdout_superiority":all_superior,
        "final_holdout_status":"PASS_SUPERIOR_TO_POISSON_ALL_THREE_MARKETS" if all_superior else "FAIL_NOT_SUPERIOR_TO_POISSON_ALL_THREE_MARKETS",
        "methodological_promotion_gate_passed":all_superior,
        "governed_engine_promoted":False,
        "p_matrix_generated":False,
        "paper_trading_satisfied":False,
        "odds_ev_validation_satisfied":False,
        "external_audit_closed":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main()->None:
    root=Path(".")
    out=root/"evidence/api_football/challenger/final_holdout_adjudication.json"
    if out.exists():
        raise ValueError("FINAL_HOLDOUT_ADJUDICATION_ALREADY_EXISTS_REFUSE_SECOND_OPEN")
    result=adjudicate(root)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "final_holdout_status":result["final_holdout_status"],
        "holdout_row_count":result["holdout_row_count"],
        "all_three_markets_holdout_superiority":result["all_three_markets_holdout_superiority"],
        "metrics":result["metrics"],
        "parameter_refit_performed":result["parameter_refit_performed"],
        "real_money":result["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
