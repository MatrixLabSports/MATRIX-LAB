"""Exploratory chronological stability + intercept-only calibration audit (NO promotions).

Existing frozen P_MATRIX is never fitted/altered. Candidate correction is trained on
EARLIER settled kickoff days, evaluated on STRICTLY LATER kickoff days. It is
research-only and cannot override the separately sealed OOS 4001-5000 policy.
Bootstrap intervals describe uncertainty, not predeclared production gates.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tools.api_football_prospective_api_settlement import _load_ledger
from tools.matrix_13_cohort_independent_settlement import validated_ledger
from tools.matrix_13_market_exact_cohort_calibration import utc

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "evidence/api_football/prospective_market_freeze/freeze.json"
PORTFOLIO = ROOT / "evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl"
API = ROOT / "evidence/api_football/prospective_market_freeze/settlement_ledger.jsonl"
ALT = ROOT / "evidence/football_cohort_recovery/MATRIX_INDEPENDENT_VERIFIED_FT_LEDGER.jsonl"
GATE = ROOT / "evidence/governance/MATRIX_13_MARKET_FORMAL_SCORING_GATE_LAST.json"
OOS = ROOT / "evidence/api_football/calibration_v2/OOS_4001_5000_STATE.json"
ONE_X = ROOT / "evidence/api_football/governance/MATRIX_DOUBLE_CHANCE_1X_PROMOTION_READINESS_LAST.json"
OVER = ROOT / "evidence/api_football/governance/over_2_5_p_matrix_promotion.json"
OUT = ROOT / "evidence/governance/MATRIX_FIVE_MARKET_ELITE_CALIBRATION_STABILITY_LAST.json"

MARKETS = ("DOUBLE_CHANCE_1X", "TOTAL_GOALS_OVER_UNDER")
EPS = 1e-12


def _prob(value: object) -> float:
    if type(value) not in (float, int):
        raise ValueError("INVALID_PROBABILITY_TYPE")
    p = float(value)
    if not math.isfinite(p) or not 0 < p < 1:
        raise ValueError("INVALID_PROBABILITY_RANGE")
    return p


def _logit(p: float) -> float:
    x = min(max(p, EPS), 1-EPS)
    return math.log(x/(1-x))


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1/(1+math.exp(-x))
    e = math.exp(x)
    return e/(1+e)


def _metrics(p: list[float], y: list[int]) -> dict:
    if not p or len(p) != len(y):
        raise ValueError("EMPTY_OR_MISMATCHED_METRICS")
    if any(type(t) is not int or t not in (0, 1) for t in y):
        raise ValueError("INVALID_BINARY_TARGET")
    p = [_prob(v) for v in p]
    n = len(y)
    bs = sum((v-t)**2 for v,t in zip(p,y))/n
    ll = -sum(t*math.log(max(v,EPS))+(1-t)*math.log(max(1-v,EPS)) for v,t in zip(p,y))/n
    ece = 0.0
    for binid in range(10):
        ids = [i for i,v in enumerate(p) if
               binid/10 <= v < (binid+1)/10 or (binid == 9 and v == 1)]
        if ids:
            ece += len(ids)/n * abs(
                sum(p[i] for i in ids)/len(ids)-sum(y[i] for i in ids)/len(ids)
            )
    return {"n": n, "brier": bs, "log_loss": ll, "ece_10_bins": ece,
            "observed_rate": sum(y)/n, "mean_forecast":sum(p)/n}


def fit_prior_logit_intercept(p: list[float], y: list[int]) -> float:
    """One degree of freedom, trained only on earlier games (no holdout peeking)."""
    if len(p) < 100 or len(p) != len(y):
        raise ValueError("TRAIN_SAMPLE_INSUFFICIENT")
    logs = [_logit(_prob(x)) for x in p]
    if any(type(t) is not int or t not in (0, 1) for t in y):
        raise ValueError("INVALID_TRAIN_TARGET")
    if not (0 < sum(y) < len(y)):
        raise ValueError("DEGENERATE_TRAIN_OUTCOMES")
    target = sum(y)/len(y)
    low,high = -6.0,6.0
    for _ in range(65):
        mid=(low+high)/2
        mean=sum(_sigmoid(z+mid) for z in logs)/len(logs)
        if mean < target: low=mid
        else: high=mid
    return (low+high)/2


def paired_uncertainty(model: list[float], baseline: list[float], y: list[int],
                       *, seed: int=20261102, draws: int=1000) -> dict:
    if len(model) != len(baseline) or len(y) != len(model) or len(y) < 30:
        raise ValueError("PAIRED_BOOTSTRAP_INVALID_COHORT")
    if draws < 200 or draws > 5000:
        raise ValueError("BAD_BOOTSTRAP_DRAW_COUNT")
    rng=random.Random(seed)
    score_delta = [(m-t)**2-(p-t)**2 for m,p,t in zip(model,baseline,y)]
    log_delta = [
        -(t*math.log(m)+(1-t)*math.log(1-m))
        +(t*math.log(p)+(1-t)*math.log(1-p))
        for m,p,t in zip(model,baseline,y)
    ]
    n=len(y)
    mean_b=sum(score_delta)/n
    mean_l=sum(log_delta)/n
    bs=[];ls=[]
    for _ in range(draws):
        idx = [rng.randrange(n) for _ in range(n)]
        bs.append(sum(score_delta[i] for i in idx)/n)
        ls.append(sum(log_delta[i] for i in idx)/n)
    bs.sort();ls.sort()
    lo=int(draws*0.025);hi=min(draws-1,int(draws*0.975))
    return {
        "n":n,"seed":seed,"resamples":draws,
        "delta_challenger_minus_reference":{
            "brier":mean_b,"log_loss":mean_l,
            "brier_ci95_percentile":[bs[lo],bs[hi]],
            "log_loss_ci95_percentile":[ls[lo],ls[hi]],
        },
        "uncertainty_note":"EXPLORATORY_PAIRED_FIXTURE_BOOTSTRAP_NOT_GOVERNED_PROMOTION_GATE",
    }


def _valid_samples(market: str, frozen: dict, portfolio: list[dict], results: list[dict]) -> list[dict]:
    base={}
    for r in frozen["rows"]:
        key=str(r["fixture_id"])
        if key in base:
            raise ValueError("DUPLICATED_CANONICAL_FROZEN_FIXTURE")
        base[key]=r
    final={}
    for r in results:
        key=str(r["fixture_id"])
        if key in final or r.get("terminal_status")!="FT":
            raise ValueError("UNTRUSTED_OR_DUPLICATE_FINAL")
        final[key]=r
    same_lane={}
    for r in portfolio:
        if r.get("market_lane")!=market:
            continue
        fid=str(r.get("fixture_id") or r.get("event_id") or "")
        if not fid or fid in same_lane:
            raise ValueError("DUPLICATE_PROSPECTIVE_LANE_FIXTURE")
        same_lane[fid]=r
    output=[]
    for fid,row in same_lane.items():
        ft=final.get(fid)
        if ft is None:
            continue
        src=base.get(fid)
        if src is None or row.get("prospective_admitted") is not True:
            raise ValueError("SETTLED_LANE_FREEZE_NOT_AUTHENTIC")
        if (row.get("real_money")!="BLOCKED"
            or row.get("automatic_wagering") is not False
            or row.get("odds_used_to_generate_probability") is not False
            or row.get("target_outcome") is not None):
            raise ValueError("INVALID_PREMATCH_FREEZE_SAFETY")
        if (utc(src["kickoff_utc"])!=utc(row["event_start_utc"])
            or utc(src["freeze_at_utc"])!=utc(row["freeze_timestamp_utc"])
            or utc(ft["kickoff_utc"])!=utc(row["event_start_utc"])
            or utc(ft["freeze_at_utc"])!=utc(row["freeze_timestamp_utc"])
            or utc(row["freeze_timestamp_utc"])>=utc(row["event_start_utc"])
            or utc(ft["settled_at_utc"])<utc(ft["kickoff_utc"])):
            raise ValueError("TEMPORAL_OR_FIXTURE_IDENTITY_BROKEN")
        hg,ag=ft["fulltime_home_goals"],ft["fulltime_away_goals"]
        if type(hg) is not int or type(ag) is not int or hg<0 or ag<0:
            raise ValueError("INVALID_FINAL_GOALS")
        c=src["frozen_research_probabilities"]
        b=src["poisson_reference"]
        if market=="DOUBLE_CHANCE_1X":
            p=_prob(float(c["1x2"]["H"])+float(c["1x2"]["D"]))
            ref=_prob(float(b["1x2"]["H"])+float(b["1x2"]["D"]))
            y=int(hg>=ag)
        else:
            p=_prob(c["over_2_5"])
            ref=_prob(b["over_2_5"])
            y=int(hg+ag>=3)
        output.append({"fixture_id":fid,"kickoff":utc(src["kickoff_utc"]).isoformat(),
                       "prediction":p,"poisson":ref,"target":y})
    return sorted(output,key=lambda r:(r["kickoff"],r["fixture_id"]))


def chronological_groups(records: list[dict]) -> tuple[list[dict],list[dict],str]:
    if len(records)<600:
        raise ValueError("CHRONO_COHORT_BELOW_600")
    days=sorted(set(r["kickoff"][:10] for r in records))
    if len(days)<3:
        raise ValueError("AT_LEAST_THREE_DISTINCT_KICKOFF_DAYS_REQUIRED")
    # Split rule fixed in code, not chosen by looking at held-out scores:
    # first complete kickoff day yielding train share 60-80%.
    for day in days[:-1]:
        train=[r for r in records if r["kickoff"][:10]<=day]
        if .60 <=len(train)/len(records)<=.80 and len(records)-len(train)>=100:
            later=[r for r in records if r["kickoff"][:10]>day]
            assert max(x["kickoff"] for x in train) < min(x["kickoff"] for x in later)
            return train,later,day
    raise ValueError("NO_VALID_CHRONOLOGICAL_SPLIT_WITHOUT_TIMESTAMP_LEAKAGE")


def build(formal: dict, frozen: dict, portfolio: list[dict], results: list[dict],
          oos: dict, readiness: dict, over_promotion: dict) -> dict:
    bymarket={r["market_key"]:r for r in formal.get("lanes") or []}
    if formal.get("summary",{}).get("gate600_final_count")!=5:
        raise ValueError("NOT_FIVE_EXACT_SETTLED_GATE600_MARKETS")
    if oos.get("frozen_policy",{}).get("parameter_tuning_allowed") is not False:
        raise ValueError("FROZEN_OOS_POLICY_CHANGED")
    if readiness.get("market")!="DOUBLE_CHANCE_1X":
        raise ValueError("INCOMPATIBLE_1X_PROMOTION_READINESS")
    if over_promotion.get("promotion_status")!="PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY":
        raise ValueError("HISTORICAL_OVER25_PROMOTION_MISSING")
    details={}
    for market in MARKETS:
        gate=bymarket[market]
        if gate.get("exact_verified_ft_count",0)<600:
            raise ValueError("NOT_ENOUGH_VERIFIED_FT")
        samples=_valid_samples(market,frozen,portfolio,results)
        if len(samples)!=gate["exact_verified_ft_count"]:
            raise ValueError("SAMPLE_NOT_SAME_AS_VERIFIED_CANONICAL_COHORT")
        train,test,cutoff=chronological_groups(samples)
        pred=[r["prediction"] for r in samples]
        ref=[r["poisson"] for r in samples]
        y=[r["target"] for r in samples]
        bias=fit_prior_logit_intercept([r["prediction"] for r in train],[r["target"] for r in train])
        raw_test=[r["prediction"] for r in test]
        ref_test=[r["poisson"] for r in test]
        ys=[r["target"] for r in test]
        candidate=[_sigmoid(_logit(p)+bias) for p in raw_test]
        metrics={
            "full_cohort_challenger":_metrics(pred,y),
            "full_cohort_poisson":_metrics(ref,y),
            "train_original":_metrics([r["prediction"] for r in train],[r["target"] for r in train]),
            "holdout_original":_metrics(raw_test,ys),
            "holdout_poisson":_metrics(ref_test,ys),
            "holdout_intercept_candidate":_metrics(candidate,ys),
        }
        details[market]={
            "settled_fixtures":len(samples),
            "full_cohort_paired_uncertainty":paired_uncertainty(pred,ref,y),
            "chronological_split":{
                "train_end_utc_date":cutoff,
                "train_n":len(train),"holdout_n":len(test),
                "train_last_kickoff":train[-1]["kickoff"],
                "holdout_first_kickoff":test[0]["kickoff"],
                "training_fixture_ids_sha256":hashlib.sha256(
                    json.dumps([x["fixture_id"] for x in train],separators=(",",":")).encode()
                ).hexdigest(),
                "holdout_fixture_ids_sha256":hashlib.sha256(
                    json.dumps([x["fixture_id"] for x in test],separators=(",",":")).encode()
                ).hexdigest(),
                "no_train_holdout_fixture_overlap":True,
            },
            "experimental_intercept_only_logit_bias":bias,
            "proper_scores":metrics,
            "holdout_candidate_vs_original":paired_uncertainty(candidate,raw_test,ys),
            "holdout_candidate_vs_poisson":paired_uncertainty(candidate,ref_test,ys,seed=20261103),
            "holdout_original_vs_poisson":paired_uncertainty(raw_test,ref_test,ys,seed=20261104),
            "candidate_governance_state":"EXPLORATORY_RECALIBRATION_ONLY_NOT_PREDECLARED_PROSPECTIVE",
            "candidate_promoted":False,
            "existing_frozen_parameters_modified":False,
        }
    outstanding=max(0,int(oos["target_oos_observations"])-int(oos["current_oos_observations"]))
    allow_1x=bool(readiness.get("promotion_allowed"))
    if oos.get("metrics_opened") is False and allow_1x:
        raise ValueError("1X_PROMOTION_INCONSISTENT_WITH_SEALED_OOS")
    return {
        "schema":"MATRIX_FIVE_MARKET_ELITE_CALIBRATION_STABILITY_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status":"RESEARCH_EXPERIMENT_DIAGNOSTIC_NO_PROMOTIONS",
        "committee_roles":["QUANT_PROPER_SCORING","PIT_TEMPORAL_DATA","EXPLORATORY_RECALIBRATION",
            "STATISTICAL_UNCERTAINTY","OOS_COHORT_GOVERNANCE","MLOPS_REPRODUCIBILITY",
            "MODEL_RISK","TELEGRAM_SIGNAL_SAFETY"],
        "market_results":details,
        "existing_governance":{
            "double_chance_1x_promotion_allowed_before_audit":allow_1x,
            "double_chance_1x_promotion_allowed_by_this_audit":False,
            "double_chance_1x_oos_current":int(oos["current_oos_observations"]),
            "double_chance_1x_oos_target":int(oos["target_oos_observations"]),
            "double_chance_1x_oos_remaining":outstanding,
            "double_chance_1x_oos_metrics_opened":bool(oos["metrics_opened"]),
            "historical_over25_market_promotion_status":over_promotion["promotion_status"],
            "over25_promoted_model_unchanged":True,
        },
        "invariants":{
            "full_cohort_metrics_not_confused_with_new_chronological_holdout":True,
            "holdout_scores_not_used_to_fit_candidate":True,
            "recalibration_candidate_is_exploratory_not_pre_registered":True,
            "no_cross_cohort_604_plus_oos_796_silent_combination":True,
            "no_odds_as_prediction_input":True,
            "no_parameter_overwrite":True,"no_automatic_market_promotion":True,
            "no_new_telegram_signals":True,"automatic_wagering":False,"real_money":"BLOCKED",
        }
    }


def main():
    formal=json.loads(GATE.read_text(encoding="utf-8"))
    frozen=json.loads(FREEZE.read_text(encoding="utf-8"))
    portfolio=[json.loads(s) for s in PORTFOLIO.read_text(encoding="utf-8").splitlines() if s.strip()]
    results=_load_ledger(API)+validated_ledger(ALT)
    result=build(formal,frozen,portfolio,results,
                 json.loads(OOS.read_text(encoding="utf-8")),
                 json.loads(ONE_X.read_text(encoding="utf-8")),
                 json.loads(OVER.read_text(encoding="utf-8")))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"market_results":[{
        "market":market,"n":v["settled_fixtures"],
        "train":v["chronological_split"]["train_n"],"holdout":v["chronological_split"]["holdout_n"],
        "fitted_bias_research_only":v["experimental_intercept_only_logit_bias"],
        "holdout_candidate_brier":v["proper_scores"]["holdout_intercept_candidate"]["brier"],
        "holdout_original_brier":v["proper_scores"]["holdout_original"]["brier"],
        "holdout_poisson_brier":v["proper_scores"]["holdout_poisson"]["brier"],
    } for market,v in result["market_results"].items()],
        "one_x_oos_remaining":result["existing_governance"]["double_chance_1x_oos_remaining"]},
        sort_keys=True))


if __name__=="__main__":
    main()
