from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

LANE_ID = "ATP_CHALLENGER_MEN_SINGLES_CLAY"
DATASET = Path("evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/bootstrap/historical_pit_dataset.csv")
ELO_CANDIDATE = Path("evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/bootstrap/elo_candidate_v1.json")

Q = math.log(10.0) / 400.0
PI2 = math.pi * math.pi

POLICY = {
    "policy_id": "ATP_CHALLENGER_CLAY_ADJUDICATION_POLICY_V1",
    "fixed_before_final_oos_comparison": True,
    "baseline_probability": 0.5,
    "minimum_brier_improvement_absolute": 0.005,
    "minimum_log_loss_improvement_absolute": 0.005,
    "maximum_ece_10bin": 0.08,
    "maximum_mce_10bin": 0.20,
    "winner_rule": "MUST_BE_ELIGIBLE_AND_STRICTLY_LOWER_BRIER_AND_LOG_LOSS_THAN_OTHER_ELIGIBLE_CANDIDATE; SPLIT_DECISION_IS_NO_GO",
    "accuracy_role": "REPORT_ONLY_NOT_PRIMARY_SELECTION_METRIC",
    "prospective_holdout_if_pass": {
        "holdout_id": "ATP_CHALLENGER_CLAY_PROSPECTIVE_V1",
        "windows": 3,
        "n_each": 200,
        "total": 600,
        "metrics": "SEALED_UNTIL_600",
        "historical_backfill": "FORBIDDEN",
        "tuning_after_first_freeze": "FORBIDDEN",
    },
}


def _load_rows(path: Path = DATASET) -> list[dict[str, Any]]:
    out=[]
    with path.open(newline="",encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.append({
                **row,
                "tourney_date": int(row["tourney_date"]),
                "match_num": int(row["match_num"]),
                "label_a_win": int(row["label_a_win"]),
            })
    return out


def _calibration(predictions: list[tuple[float,int]], bins: int = 10) -> dict[str, Any]:
    groups=[[] for _ in range(bins)]
    for p,y in predictions:
        idx=min(bins-1,max(0,int(p*bins)))
        groups[idx].append((p,y))
    details=[]
    ece=0.0
    mce=0.0
    n=len(predictions)
    for i,g in enumerate(groups):
        if not g:
            details.append({"bin":i,"n":0,"mean_p":None,"empirical_rate":None,"abs_error":None})
            continue
        mean_p=sum(p for p,_ in g)/len(g)
        empirical=sum(y for _,y in g)/len(g)
        err=abs(mean_p-empirical)
        ece += len(g)/n*err
        mce=max(mce,err)
        details.append({"bin":i,"n":len(g),"mean_p":mean_p,"empirical_rate":empirical,"abs_error":err})
    return {"ece_10bin":ece,"mce_10bin":mce,"bins":details}


def _metrics(predictions: list[tuple[float,int]]) -> dict[str, Any]:
    eps=1e-15
    n=len(predictions)
    brier=sum((p-y)**2 for p,y in predictions)/n
    log_loss=-sum(y*math.log(max(eps,min(1-eps,p)))+(1-y)*math.log(max(eps,min(1-eps,1-p))) for p,y in predictions)/n
    accuracy=sum(((p>=0.5) == bool(y)) for p,y in predictions)/n
    return {"n":n,"brier":brier,"log_loss":log_loss,"accuracy":accuracy,**_calibration(predictions)}


def _elo_p(ra: float, rb: float) -> float:
    return 1/(1+10**((rb-ra)/400.0))


def elo_predictions(rows: list[dict[str,Any]], k: float) -> list[tuple[float,int,str]]:
    ratings=defaultdict(lambda:1500.0)
    by_date=defaultdict(list)
    for row in rows:
        by_date[row["tourney_date"]].append(row)
    scored=[]
    for date in sorted(by_date):
        pending=[]
        for row in sorted(by_date[date],key=lambda r:(r["tourney_id"],r["match_num"],r["physical_event_key"])):
            ra=ratings[row["player_a_id"]]; rb=ratings[row["player_b_id"]]
            p=_elo_p(ra,rb); y=int(row["label_a_win"])
            if row["development_split"]=="FINAL_HISTORICAL_OOS":
                scored.append((p,y,row["physical_event_key"]))
            pending.append((row,p,y))
        delta=defaultdict(float)
        for row,p,y in pending:
            d=k*(y-p)
            delta[row["player_a_id"]]+=d
            delta[row["player_b_id"]]-=d
        for player,d in delta.items():
            ratings[player]+=d
    return scored


def _gfun(rd: float) -> float:
    return 1.0/math.sqrt(1.0+3.0*Q*Q*rd*rd/PI2)


def _glicko_expected(r: float, opp_r: float, opp_rd: float) -> float:
    return 1.0/(1.0+10.0**(-_gfun(opp_rd)*(r-opp_r)/400.0))


def _glicko_batch_update(
    table: dict[str,dict[str,float]],
    games: list[tuple[str,str,float]],
    initial_rd: float,
) -> dict[str,dict[str,float]]:
    pre={p:{"r":float(v["r"]),"rd":float(v["rd"])} for p,v in table.items()}
    grouped=defaultdict(list)
    for p,opp,score in games:
        grouped[p].append((opp,score))
    out={p:dict(v) for p,v in table.items()}
    for p,gs in grouped.items():
        pr=pre.get(p,{"r":1500.0,"rd":initial_rd})
        r0,rd0=pr["r"],pr["rd"]
        variance_terms=[]
        sum_term=0.0
        for opp,score in gs:
            op=pre.get(opp,{"r":1500.0,"rd":initial_rd})
            g=_gfun(op["rd"])
            e=_glicko_expected(r0,op["r"],op["rd"])
            variance_terms.append(g*g*e*(1-e))
            sum_term += g*(score-e)
        if not variance_terms:
            continue
        d2=1.0/(Q*Q*sum(variance_terms))
        denom=1.0/(rd0*rd0)+1.0/d2
        new_rd=math.sqrt(1.0/denom)
        new_r=r0+Q/denom*sum_term
        out[p]={"r":new_r,"rd":new_rd}
    return out


def glicko_predictions(
    rows: list[dict[str,Any]],
    *,
    initial_rd: float,
    score_split: str,
) -> list[tuple[float,int,str]]:
    table: dict[str,dict[str,float]]={}
    by_date=defaultdict(list)
    for row in rows:
        by_date[row["tourney_date"]].append(row)
    scored=[]
    for date in sorted(by_date):
        day=sorted(by_date[date],key=lambda r:(r["tourney_id"],r["match_num"],r["physical_event_key"]))
        games=[]
        for row in day:
            a=row["player_a_id"]; b=row["player_b_id"]
            ar=table.get(a,{"r":1500.0,"rd":initial_rd})
            br=table.get(b,{"r":1500.0,"rd":initial_rd})
            p=_glicko_expected(ar["r"],br["r"],br["rd"])
            y=int(row["label_a_win"])
            if row["development_split"]==score_split:
                scored.append((p,y,row["physical_event_key"]))
            games.append((a,b,float(y)))
            games.append((b,a,float(1-y)))
        table=_glicko_batch_update(table,games,initial_rd)
    return scored


def _plain(scored: list[tuple[float,int,str]]) -> list[tuple[float,int]]:
    return [(p,y) for p,y,_ in scored]


def _eligible(metrics: dict[str,Any], baseline: dict[str,Any]) -> tuple[bool,list[str]]:
    blockers=[]
    if baseline["brier"]-metrics["brier"] < POLICY["minimum_brier_improvement_absolute"]:
        blockers.append("BRIER_IMPROVEMENT_BELOW_POLICY")
    if baseline["log_loss"]-metrics["log_loss"] < POLICY["minimum_log_loss_improvement_absolute"]:
        blockers.append("LOG_LOSS_IMPROVEMENT_BELOW_POLICY")
    if metrics["ece_10bin"] > POLICY["maximum_ece_10bin"]:
        blockers.append("ECE_ABOVE_POLICY")
    if metrics["mce_10bin"] > POLICY["maximum_mce_10bin"]:
        blockers.append("MCE_ABOVE_POLICY")
    return (not blockers),blockers


def build(out_root: Path) -> dict[str,Any]:
    rows=_load_rows()
    elo=json.loads(ELO_CANDIDATE.read_text(encoding="utf-8"))
    assert elo["parameter_selection"]["final_historical_oos_not_used_for_selection"] is True
    chosen_k=float(elo["parameter_selection"]["chosen_k"])

    development=[r for r in rows if r["development_split"] in {"TRAIN","VALIDATION"}]
    rd_grid=[200.0,250.0,300.0,350.0]
    g_candidates=[]
    for rd in rd_grid:
        pred=glicko_predictions(development,initial_rd=rd,score_split="VALIDATION")
        m=_metrics(_plain(pred))
        g_candidates.append({"initial_rd":rd,"validation":m})
    chosen=min(g_candidates,key=lambda x:(x["validation"]["brier"],x["validation"]["log_loss"],x["initial_rd"]))
    chosen_rd=float(chosen["initial_rd"])

    # Only now, after parameter selection, evaluate the sealed final OOS.
    elo_scored=elo_predictions(rows,chosen_k)
    g_scored=glicko_predictions(rows,initial_rd=chosen_rd,score_split="FINAL_HISTORICAL_OOS")
    elo_keys=[k for _,_,k in elo_scored]
    g_keys=[k for _,_,k in g_scored]
    if elo_keys != g_keys:
        raise ValueError("CLAY_OOS_PHYSICAL_EVENT_SET_MISMATCH")
    if len(elo_keys)!=434 or len(set(elo_keys))!=434:
        raise ValueError("CLAY_OOS_CARDINALITY_OR_UNIQUENESS_INVALID")

    elo_m=_metrics(_plain(elo_scored))
    g_m=_metrics(_plain(g_scored))
    baseline=_metrics([(0.5,y) for _,y,_ in elo_scored])

    elo_ok,elo_blockers=_eligible(elo_m,baseline)
    g_ok,g_blockers=_eligible(g_m,baseline)

    winner=None
    reason=None
    if elo_ok and g_ok:
        if elo_m["brier"] < g_m["brier"] and elo_m["log_loss"] < g_m["log_loss"]:
            winner="ATP_CHALLENGER_CLAY_ELO_V1"
            reason="ELO_ELIGIBLE_AND_STRICTLY_BETTER_BRIER_AND_LOG_LOSS"
        elif g_m["brier"] < elo_m["brier"] and g_m["log_loss"] < elo_m["log_loss"]:
            winner="ATP_CHALLENGER_CLAY_GLICKO_V1"
            reason="GLICKO_ELIGIBLE_AND_STRICTLY_BETTER_BRIER_AND_LOG_LOSS"
        else:
            reason="NO_GO_SPLIT_HEAD_TO_HEAD_METRICS"
    elif elo_ok:
        winner="ATP_CHALLENGER_CLAY_ELO_V1"; reason="ELO_ONLY_ELIGIBLE"
    elif g_ok:
        winner="ATP_CHALLENGER_CLAY_GLICKO_V1"; reason="GLICKO_ONLY_ELIGIBLE"
    else:
        reason="NO_GO_NO_ELIGIBLE_CANDIDATE"

    glicko={
        "schema":"MATRIX_TENNIS_CLAY_GLICKO_CANDIDATE_V1",
        "lane_id":LANE_ID,
        "candidate_identity":"ATP_CHALLENGER_CLAY_GLICKO_V1",
        "rating_initial":1500.0,
        "rating_period":"TOURNEY_DATE_BATCH",
        "same_day_update_policy":"BATCH_AFTER_ALL_MATCHES_ON_TOURNEY_DATE",
        "parameter_selection":{
            "selection_split":"VALIDATION",
            "initial_rd_grid":rd_grid,
            "candidates":g_candidates,
            "chosen_initial_rd":chosen_rd,
            "final_historical_oos_not_used_for_selection":True,
        },
        "final_historical_oos":g_m,
        "baseline_0_5":baseline,
        "status":"PASS_HISTORICAL_OOS_CANDIDATE_NOT_PROMOTED" if g_ok else "FAIL_HISTORICAL_OOS_NO_PROMOTION",
        "eligibility_blockers":g_blockers,
        "prospective_holdout_created":False,
        "prospective_observations":0,
        "automatic_promotion":False,
        "real_money":"BLOCKED",
    }

    adjudication={
        "schema":"MATRIX_TENNIS_CLAY_MODEL_ADJUDICATION_V1",
        "lane_id":LANE_ID,
        "policy":POLICY,
        "oos_physical_event_count":434,
        "oos_physical_event_set_sha256":hashlib.sha256("\n".join(elo_keys).encode()).hexdigest(),
        "baseline_0_5":baseline,
        "candidates":{
            "ATP_CHALLENGER_CLAY_ELO_V1":{"metrics":elo_m,"eligible":elo_ok,"blockers":elo_blockers,"chosen_k":chosen_k},
            "ATP_CHALLENGER_CLAY_GLICKO_V1":{"metrics":g_m,"eligible":g_ok,"blockers":g_blockers,"chosen_initial_rd":chosen_rd},
        },
        "winner":winner,
        "decision_reason":reason,
        "promotion_status":"PASS_CREATE_INDEPENDENT_PROSPECTIVE_HOLDOUT" if winner else "NO_GO_BUILD_NEXT_CHALLENGER",
        "accuracy_used_for_selection":False,
        "odds_used":False,
        "historical_oos_used_for_parameter_selection":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }

    out_root.mkdir(parents=True,exist_ok=True)
    gp=out_root/"glicko_candidate_v1.json"
    ap=out_root/"model_adjudication_v1.json"
    gp.write_text(json.dumps(glicko,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    adjudication["candidate_artifact_sha256"]={
        "elo":hashlib.sha256(ELO_CANDIDATE.read_bytes()).hexdigest(),
        "glicko":hashlib.sha256(gp.read_bytes()).hexdigest(),
    }
    ap.write_text(json.dumps(adjudication,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    holdout=None
    if winner:
        winner_path=ELO_CANDIDATE if winner.endswith("ELO_V1") else gp
        holdout={
            "schema":"MATRIX_TENNIS_CLAY_PROSPECTIVE_HOLDOUT_CONTRACT_V1",
            "holdout_id":"ATP_CHALLENGER_CLAY_PROSPECTIVE_V1",
            "lane_id":LANE_ID,
            "market":"MATCH_WINNER",
            "domain":{"circuit":"ATP_CHALLENGER","gender":"MEN","format":"SINGLES","surface":"CLAY"},
            "frozen_model_identity":winner,
            "frozen_model_sha256":hashlib.sha256(winner_path.read_bytes()).hexdigest(),
            "adjudication_sha256":hashlib.sha256(ap.read_bytes()).hexdigest(),
            "windows":[{"window":1,"start":1,"end":200},{"window":2,"start":201,"end":400},{"window":3,"start":401,"end":600}],
            "total_required":600,
            "current_observations":0,
            "metrics":"SEALED_UNTIL_600",
            "metrics_opened":False,
            "outcomes_read":0,
            "historical_backfill":"FORBIDDEN",
            "first_freeze_tuning_lock":"NO_PARAMETER_CHANGE_AFTER_FIRST_VALID_PROSPECTIVE_FREEZE",
            "event_admission":"FUTURE_PREMATCH_ONLY_IDENTITY_PASS_PIT_HISTORY_COMPLETE_UNIQUE_PHYSICAL_EVENT",
            "dual_paid_provider_requirement":["RAPIDAPI_TENNIS","API_TENNIS"],
            "odds_to_probability":False,
            "missing_not_zero":True,
            "silent_imputation":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }
        hp=out_root.parent/"prospective"/"holdout_contract.json"
        hp.parent.mkdir(parents=True,exist_ok=True)
        hp.write_text(json.dumps(holdout,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        state={
            "schema":"MATRIX_TENNIS_CLAY_PROSPECTIVE_STATE_V1",
            "holdout_id":holdout["holdout_id"],
            "lane_id":LANE_ID,
            "frozen_model_identity":winner,
            "frozen_model_sha256":holdout["frozen_model_sha256"],
            "observation_count":0,
            "unique_physical_event_count":0,
            "metrics_opened":False,
            "outcomes_read":0,
            "status":"ACTIVE_WAITING_FUTURE_ELIGIBLE_EVENTS",
            "real_money":"BLOCKED",
        }
        (hp.parent/"state.json").write_text(json.dumps(state,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    return {"glicko":glicko,"adjudication":adjudication,"holdout":holdout}


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--out-root",default="evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/adjudication")
    args=parser.parse_args()
    r=build(Path(args.out_root))
    print(json.dumps({
        "glicko_status":r["glicko"]["status"],
        "chosen_initial_rd":r["glicko"]["parameter_selection"]["chosen_initial_rd"],
        "winner":r["adjudication"]["winner"],
        "decision_reason":r["adjudication"]["decision_reason"],
        "promotion_status":r["adjudication"]["promotion_status"],
        "holdout_created":r["holdout"] is not None,
        "holdout_observations":0 if r["holdout"] else None,
    },sort_keys=True))


if __name__=="__main__":
    main()
