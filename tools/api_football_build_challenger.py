from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import exp, log
from pathlib import Path
from typing import Any, Mapping

EPS = 1e-12
DEV_FRACTION = 0.70
VALIDATION_FRACTION = 0.15


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _canonical_sha(payload: Any) -> str:
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _clip(p: float) -> float:
    return min(max(float(p), EPS), 1.0 - EPS)


def _logit(p: float) -> float:
    p = _clip(p)
    return log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = exp(-x)
        return 1.0 / (1.0 + z)
    z = exp(x)
    return z / (1.0 + z)


def _binary_metrics(rows: list[dict[str, Any]], probs: list[float], market: str) -> dict[str, float]:
    if len(rows) != len(probs) or not rows:
        raise ValueError("BINARY_METRIC_INPUT_MISMATCH")
    brier = 0.0
    ll = 0.0
    for row, p in zip(rows, probs):
        y = 1.0 if bool(row["outcome"][market]) else 0.0
        p = _clip(p)
        brier += (p - y) ** 2
        ll += -(y * log(p) + (1.0-y) * log(1.0-p))
    return {"sample_size": len(rows), "brier_score": brier/len(rows), "log_loss": ll/len(rows)}


def _multiclass_metrics(rows: list[dict[str, Any]], probs: list[dict[str, float]]) -> dict[str, float]:
    if len(rows) != len(probs) or not rows:
        raise ValueError("MULTICLASS_METRIC_INPUT_MISMATCH")
    brier = 0.0
    ll = 0.0
    accuracy = 0
    for row, p in zip(rows, probs):
        actual = row["outcome"]["1x2"]
        for k in ("H","D","A"):
            y = 1.0 if actual == k else 0.0
            brier += (p[k]-y)**2
        ll += -log(max(p[actual], EPS))
        accuracy += int(max(("H","D","A"), key=lambda k:p[k]) == actual)
    return {"sample_size":len(rows),"brier_score":brier/len(rows),"log_loss":ll/len(rows),"accuracy":accuracy/len(rows)}


def _multiclass_log_pool(row: Mapping[str, Any], a: float, c: float) -> dict[str, float]:
    scores = {}
    for k in ("H","D","A"):
        pp = max(float(row["poisson"]["1x2"][k]), EPS)
        bp = max(float(row["baseline"]["1x2"][k]), EPS)
        scores[k] = exp(a*log(pp) + c*log(bp))
    total = sum(scores.values())
    return {k:scores[k]/total for k in scores}


def _binary_log_pool(row: Mapping[str, Any], market: str, a: float, c: float, b: float) -> float:
    pp = float(row["poisson"][market])
    bp = float(row["baseline"][market])
    return _sigmoid(a*_logit(pp) + c*_logit(bp) + b)


def _candidate_better(candidate: Mapping[str,float], poisson: Mapping[str,float]) -> bool:
    return candidate["brier_score"] < poisson["brier_score"] and candidate["log_loss"] < poisson["log_loss"]


def _gain(candidate: Mapping[str,float], poisson: Mapping[str,float]) -> float:
    return (poisson["brier_score"]-candidate["brier_score"]) + (poisson["log_loss"]-candidate["log_loss"])


def _fit_1x2(dev: list[dict[str,Any]], val: list[dict[str,Any]]) -> dict[str,Any]:
    poisson_val = _multiclass_metrics(val,[r["poisson"]["1x2"] for r in val])
    baseline_val = _multiclass_metrics(val,[r["baseline"]["1x2"] for r in val])
    candidates=[]
    for ai in range(0,21,2):
        a=ai/10
        for ci in range(0,21,2):
            c=ci/10
            if a==0 and c==0:
                continue
            dev_probs=[_multiclass_log_pool(r,a,c) for r in dev]
            dev_m=_multiclass_metrics(dev,dev_probs)
            candidates.append((dev_m["brier_score"],dev_m["log_loss"],a,c))
    candidates.sort()
    shortlist=candidates[:25]
    chosen=None
    for _,_,a,c in shortlist:
        val_probs=[_multiclass_log_pool(r,a,c) for r in val]
        m=_multiclass_metrics(val,val_probs)
        if _candidate_better(m,poisson_val):
            score=_gain(m,poisson_val)
            if chosen is None or score>chosen["gain"]:
                chosen={"a":a,"c":c,"validation":m,"gain":score}
    return {
        "market":"1x2",
        "poisson_validation":poisson_val,
        "baseline_validation":baseline_val,
        "selected":chosen,
        "validation_superiority":chosen is not None,
        "search_family":"log_probability_pool_poisson_plus_baseline",
        "search_grid":{"a":"0.0..2.0 step 0.2","c":"0.0..2.0 step 0.2","shortlist_by_dev_brier":25},
    }


def _fit_binary(dev: list[dict[str,Any]], val: list[dict[str,Any]], market: str) -> dict[str,Any]:
    poisson_val=_binary_metrics(val,[float(r["poisson"][market]) for r in val],market)
    baseline_val=_binary_metrics(val,[float(r["baseline"][market]) for r in val],market)
    candidates=[]
    for ai in range(0,21,2):
        a=ai/10
        for ci in range(0,21,2):
            c=ci/10
            for bi in range(-10,11,2):
                b=bi/10
                if a==0 and c==0:
                    continue
                probs=[_binary_log_pool(r,market,a,c,b) for r in dev]
                m=_binary_metrics(dev,probs,market)
                candidates.append((m["brier_score"],m["log_loss"],a,c,b))
    candidates.sort()
    shortlist=candidates[:40]
    chosen=None
    for _,_,a,c,b in shortlist:
        probs=[_binary_log_pool(r,market,a,c,b) for r in val]
        m=_binary_metrics(val,probs,market)
        if _candidate_better(m,poisson_val):
            score=_gain(m,poisson_val)
            if chosen is None or score>chosen["gain"]:
                chosen={"a":a,"c":c,"b":b,"validation":m,"gain":score}
    return {
        "market":market,
        "poisson_validation":poisson_val,
        "baseline_validation":baseline_val,
        "selected":chosen,
        "validation_superiority":chosen is not None,
        "search_family":"logit_pool_poisson_plus_baseline",
        "search_grid":{"a":"0.0..2.0 step 0.2","c":"0.0..2.0 step 0.2","b":"-1.0..1.0 step 0.2","shortlist_by_dev_brier":40},
    }


def build_challenger(source: Mapping[str,Any]) -> tuple[dict[str,Any],dict[str,Any]]:
    rows=source.get("rows")
    if not isinstance(rows,list) or len(rows)<100:
        raise ValueError("RETROSPECTIVE_ROWS_MISSING")
    rows=sorted(rows,key=lambda r:(r["kickoff_utc"],int(r["fixture_id"])))
    n=len(rows)
    dev_end=int(n*DEV_FRACTION)
    val_end=int(n*(DEV_FRACTION+VALIDATION_FRACTION))
    if not (0<dev_end<val_end<n):
        raise ValueError("INVALID_SPLIT")

    dev=rows[:dev_end]
    val=rows[dev_end:val_end]
    holdout=rows[val_end:]

    one=_fit_1x2(dev,val)
    over=_fit_binary(dev,val,"over_2_5")
    btts=_fit_binary(dev,val,"btts")
    reports=[one,over,btts]
    all_superior=all(r["validation_superiority"] for r in reports)

    frozen_parameters={
        r["market"]:r["selected"]
        for r in reports
        if r["selected"] is not None
    }

    holdout_seal_rows=[]
    for r in holdout:
        holdout_seal_rows.append({
            "fixture_id":r["fixture_id"],
            "kickoff_utc":r["kickoff_utc"],
            "league_id":r["league_id"],
            "season":r["season"],
            "poisson":r["poisson"],
            "baseline":r["baseline"],
        })

    holdout_seal={
        "schema":"MATRIX_FOOTBALL_CHALLENGER_HOLDOUT_SEAL_V1",
        "status":"SEALED_OUTCOMES_NOT_READ_BY_CHALLENGER_BUILDER",
        "row_count":len(holdout_seal_rows),
        "rows":holdout_seal_rows,
    }

    manifest={
        "schema":"MATRIX_FOOTBALL_CHALLENGER_V1",
        "created_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_row_count":n,
        "split_policy":"CHRONOLOGICAL_70_DEV_15_VALIDATION_15_FINAL_HOLDOUT",
        "development_count":len(dev),
        "validation_count":len(val),
        "final_holdout_count":len(holdout),
        "holdout_outcomes_read":False,
        "holdout_metrics_computed":False,
        "holdout_status":"SEALED",
        "challenger_name":"calibrated_log_pool_v1",
        "market_reports":reports,
        "all_three_markets_validation_superiority":all_superior,
        "candidate_status":"FROZEN_CHALLENGER_AWAITING_FINAL_HOLDOUT" if all_superior else "REJECTED_ON_VALIDATION",
        "frozen_parameters":frozen_parameters,
        "governed_engine_promoted":False,
        "p_matrix_generated":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    return manifest,holdout_seal


def main() -> None:
    root=Path(".")
    source=_load(root/"evidence/api_football/model_validation/retrospective_predictions.json")
    manifest,seal=build_challenger(source)
    out=root/"evidence/api_football/challenger"
    out.mkdir(parents=True,exist_ok=True)
    seal_path=out/"final_holdout_seal.json"
    seal_path.write_text(json.dumps(seal,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    manifest["holdout_seal_sha256"]=_canonical_sha(seal)
    manifest["holdout_seal_path"]=seal_path.as_posix()
    (out/"challenger_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "candidate_status":manifest["candidate_status"],
        "development_count":manifest["development_count"],
        "validation_count":manifest["validation_count"],
        "final_holdout_count":manifest["final_holdout_count"],
        "all_three_markets_validation_superiority":manifest["all_three_markets_validation_superiority"],
        "market_reports":manifest["market_reports"],
        "holdout_outcomes_read":manifest["holdout_outcomes_read"],
        "real_money":manifest["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
