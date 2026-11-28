"""Independent prospective Brier benchmark on immutable ESPN SHA/PIT forecasts.

This is a research scoreboard, never a production model-selection or betting
authorisation. A pending or wrongly identified match cannot count as a loss.
"""
from __future__ import annotations
import argparse,json,math,random
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

SCHEMA="MATRIX_SHA_PIT_OOS_POISSON_BENCHMARK_V1"
SOURCE_FREEZE="MATRIX_ESPN_SHA_PROVEN_TWO_MONTH_OVER25_RESEARCH_FREEZE_V1"
SOURCE_OOS="MATRIX_ESPN_SHA_PIT_PROSPECTIVE_OVER25_OOS_SETTLEMENT_V1"


def timestamp(value):
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("UNZONED_TIMESTAMP")
    return dt.astimezone(timezone.utc)


def benchmark(frozen:dict,score:dict,*,resamples:int=5000,seed:int=20261122)->dict:
    if (frozen.get("schema")!=SOURCE_FREEZE or score.get("schema")!=SOURCE_OOS
        or frozen.get("source_sha256_and_point_in_time_receipts_verified") is not True
        or score.get("source_raw_sha_and_pit_receipts_verified") is not True
        or frozen.get("telegram_signal_authorized") is not False
        or score.get("telegram_signal_authorized") is not False
        or frozen.get("production_p_matrix_authorized") is not False
        or score.get("production_p_matrix_authorized") is not False
        or frozen.get("real_money")!="BLOCKED" or score.get("real_money")!="BLOCKED"):
        raise ValueError("RESEARCH_EVIDENCE_GOVERNANCE_NOT_TRUSTED")
    freeze_time=timestamp(frozen["research_frozen_at_utc"])
    if timestamp(score["preregistered_frozen_at_utc"])!=freeze_time:
        raise ValueError("OOS_SCORECARD_FROZEN_TIME_CONFLICT")
    indexed={}
    for row in frozen["research_rows"]:
        key=(str(row["original_league_id_research_only"]),str(row["provider_fixture_id"]))
        if key in indexed:
            raise ValueError("DUPLICATE_FROZEN_FORECAST_ID")
        indexed[key]=row
    seen=set();joined=[]
    for s in score["settled"]:
        key=(str(s["league_id"]),str(s["provider_event_id"]))
        if key in seen or key not in indexed:
            raise ValueError("SETTLEMENT_ID_DUPLICATED_OR_NOT_PRE_FROZEN")
        seen.add(key)
        f=indexed[key]
        k=timestamp(f["kickoff_utc"])
        if (not freeze_time<k<timestamp(s["final_observed_at_utc"])
            or timestamp(s["frozen_at_utc"])!=freeze_time
            or str(f["research_frozen_at_utc"])!=str(frozen["research_frozen_at_utc"])):
            raise ValueError("FROZEN_PREDICTION_AFTER_KICKOFF_OR_POSTGAME_INVALID")
        y=s["outcome_over25"]
        if y not in (0,1) or type(y) is not int:
            raise ValueError("SETTLEMENT_OUTCOME_NOT_BINARY")
        if (int(s["observed_home_goals"])+int(s["observed_away_goals"])>=3)!=bool(y):
            raise ValueError("SETTLEMENT_GOALS_DO_NOT_MATCH_OUTCOME")
        p=f["research_probability_over25"]
        if (type(p) not in (int,float) or not math.isfinite(p) or not 0<p<1
            or abs(s["frozen_probability_over25"]-p)>2e-10):
            raise ValueError("SOURCE_PREGAME_PROBABILITY_CHANGED")
        tr=f.get("source_history_feature_trace") or {}
        po=tr.get("poisson_over25")
        base=tr.get("group_baseline_over25")
        if any(type(q) not in (float,int) or not math.isfinite(q) or not 0<=q<=1
               for q in (po,base)):
            raise ValueError("SOURCE_BASELINE_NOT_PREREGISTERED")
        joined.append({"league":key[0],"id":key[1],"y":y,"p":p,"po":po,"base":base,
                       "model_error":(p-y)**2,"poisson_error":(po-y)**2,
                       "baseline_error":(base-y)**2})
    if len(joined)!=score["verified_prospective_settlements"]:
        raise ValueError("SCORECARD_SETTLEMENT_COUNT_CONFLICT")
    n=len(joined)
    mean=lambda values:(sum(values)/len(values) if values else None)
    differences=[r["model_error"]-r["poisson_error"] for r in joined]
    ci=None
    if n>=2 and resamples>=100:
        rng=random.Random(seed)
        boot=sorted(mean([differences[rng.randrange(n)] for _ in range(n)])
                    for _ in range(resamples))
        ci=[round(boot[int(.025*resamples)],10),round(boot[min(resamples-1,int(.975*resamples))],10)]
    per_league={}
    for league in ("39","61","78","135","140","239"):
        group=[r for r in joined if r["league"]==league]
        per_league[league]={"settled":len(group),"minimum_30_met":len(group)>=30,
                            "model_brier":mean([r["model_error"] for r in group]),
                            "poisson_brier":mean([r["poisson_error"] for r in group])}
    return {"schema":SCHEMA,"status":"NOT_CERTIFIED_COMPARISON_ONLY",
            "freeze_utc":freeze_time.isoformat(),
            "prospective_settled":n,"pending_final":score["awaiting_authentic_final"],
            "rejected_provenance":score["rejected_wrong_identity_or_provenance"],
            "model_brier":mean([r["model_error"] for r in joined]),
            "poisson_brier":mean([r["poisson_error"] for r in joined]),
            "historical_group_brier":mean([r["baseline_error"] for r in joined]),
            "model_minus_poisson_brier":mean(differences),
            "model_better_than_poisson_event_count":sum(d<0 for d in differences),
            "poisson_better_than_model_event_count":sum(d>0 for d in differences),
            "paired_bootstrap_seed":seed,"paired_bootstrap_resamples":resamples,
            "paired_brier_difference_ci95_exploratory":ci,
            "per_league":per_league,
            "all_six_leagues_30_research_events_met":all(v["minimum_30_met"] for v in per_league.values()),
            "producer_parameters_unchanged":True,
            "scientific_independent_model_certified":False,
            "official_p_matrix_authorized":False,"telegram_signal_authorized":False,
            "automatic_wagering":False,"real_money":"BLOCKED"}


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--freeze",type=Path,required=True)
    parser.add_argument("--scorecard",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if set(args.out.parts)&{"telegram","notifications","daily_prematch_reports","market_portfolio"}:
        raise SystemExit("RESEARCH_BENCHMARK_CANNOT_WRITE_PRODUCTION")
    frozen=json.loads(args.freeze.read_text(encoding="utf-8"))
    score=json.loads(args.scorecard.read_text(encoding="utf-8"))
    audit=benchmark(frozen,score)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(audit,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"settled":audit["prospective_settled"],
                      "model_brier":audit["model_brier"],
                      "poisson_brier":audit["poisson_brier"],
                      "official_promoted":False},sort_keys=True))


if __name__=="__main__":
    main()
