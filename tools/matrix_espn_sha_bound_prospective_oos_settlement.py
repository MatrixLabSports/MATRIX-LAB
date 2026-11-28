"""Strict post-kickoff ESPN OOS scorecard for SHA-verified prospective Over2.5.

Never settle from an unauthenticated score, bookmaker information, or an
unbound provider fixture. Research results cannot promote P_MATRIX/Telegram.
"""
from __future__ import annotations
import argparse,json,math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from tools.matrix_football_espn_enriched_pit_research import LEAGUES,dt
from tools.matrix_espn_sha_bound_two_month_over25_research import read_archive,SCHEMA as FREEZE_SCHEMA

SCHEMA="MATRIX_ESPN_SHA_PIT_PROSPECTIVE_OVER25_OOS_SETTLEMENT_V1"


def evaluate(frozen:dict, results_dir:Path, *,now:datetime|None=None)->dict:
    asof=now or datetime.now(timezone.utc)
    if asof.tzinfo is None or asof.utcoffset() is None:
        raise ValueError("SETTLEMENT_CLOCK_MUST_HAVE_TIMEZONE")
    asof=asof.astimezone(timezone.utc)
    if (frozen.get("schema")!=FREEZE_SCHEMA
        or frozen.get("source_sha256_and_point_in_time_receipts_verified") is not True
        or frozen.get("production_p_matrix_authorized") is not False
        or frozen.get("telegram_signal_authorized") is not False
        or frozen.get("real_money")!="BLOCKED"):
        raise ValueError("UNTRUSTED_PREMATCH_FREEZE")
    frozen_at=dt(frozen["research_frozen_at_utc"])
    if frozen_at>asof:
        raise ValueError("PREMATCH_FREEZE_POSTDATES_SETTLEMENT_CHECK")
    index={}
    for lid in LEAGUES:
        for e in read_archive(results_dir,"2026-11",lid,asof):
            if e["id"] in index:
                raise ValueError("SOURCE_RESULT_EVENT_ID_COLLISION")
            index[e["id"]]=e
    outcomes=[];pending=[];rejected=[];keys=set()
    for row in frozen["research_rows"]:
        eid=str(row["provider_fixture_id"])
        league=str(row["original_league_id_research_only"])
        key=(league,eid)
        if key in keys:
            raise ValueError("DUPLICATE_FROZEN_OOS_PREDICTION")
        keys.add(key)
        kickoff=dt(row["kickoff_utc"])
        if dt(row["research_frozen_at_utc"])!=frozen_at or not frozen_at<kickoff:
            rejected.append({"provider_event_id":eid,"reason":"FREEZE_NOT_STRICTLY_PREMATCH"})
            continue
        p=row["research_probability_over25"]
        if type(p) not in (float,int) or not math.isfinite(p) or not 0<p<1:
            rejected.append({"provider_event_id":eid,"reason":"FROZEN_PROBABILITY_INVALID"})
            continue
        if kickoff>=asof:
            pending.append({"provider_event_id":eid,"reason":"FUTURE_FIXTURE"})
            continue
        match=index.get(eid)
        if match is None or match["goals"] is None:
            pending.append({"provider_event_id":eid,"reason":"NO_AUTHENTIC_FINAL_RESULT"})
            continue
        if (match["league"]!=league
            or match["kickoff"]!=kickoff
            or match["home"]!=str(row["home_provider_team_id"])
            or match["away"]!=str(row["away_provider_team_id"])):
            rejected.append({"provider_event_id":eid,"reason":"SOURCE_FINAL_IDENTITY_MISMATCH"})
            continue
        if not (kickoff<match["received"]<=asof and frozen_at<match["received"]):
            rejected.append({"provider_event_id":eid,"reason":"FINAL_SOURCE_RECEIPT_TEMPORAL_INVALID"})
            continue
        outcome=int(sum(match["goals"])>=3)
        brier=(p-outcome)**2
        logloss=-(outcome*math.log(p)+(1-outcome)*math.log1p(-p))
        outcomes.append({"provider_event_id":eid,"league_id":league,
                         "observed_home_goals":match["goals"][0],
                         "observed_away_goals":match["goals"][1],
                         "outcome_over25":outcome,
                         "frozen_probability_over25":p,
                         "frozen_at_utc":frozen_at.isoformat(),
                         "final_observed_at_utc":match["received"].isoformat(),
                         "final_result_source_sha256":match["raw_sha256"],
                         "brier":round(brier,10),"logloss":round(logloss,10),
                         "original_model_equivalence_certified":False,
                         "telegram_signal_authorized":False})
    by_league=defaultdict(list)
    for x in outcomes:
        by_league[x["league_id"]].append(x)
    leagues={}
    for lid in LEAGUES:
        group=by_league[lid]
        n=len(group)
        leagues[lid]={"verified_prospective_results":n,
                      "brier":round(sum(x["brier"] for x in group)/n,9) if n else None,
                      "logloss":round(sum(x["logloss"] for x in group)/n,9) if n else None,
                      "minimum_30_reached":n>=30,
                      "production_certification":False}
    n=len(outcomes)
    return {"schema":SCHEMA,"status":"PROSPECTIVE_OOS_SCORECARD_RESEARCH_ONLY_NO_AUTOPROMOTION",
            "evaluated_at_utc":asof.isoformat(),
            "preregistered_frozen_at_utc":frozen_at.isoformat(),
            "verified_prospective_settlements":n,
            "awaiting_authentic_final":len(pending),
            "rejected_wrong_identity_or_provenance":len(rejected),
            "pending":pending,"rejected":rejected,
            "per_league":leagues,"settled":outcomes,
            "overall_brier":round(sum(x["brier"] for x in outcomes)/n,9) if n else None,
            "overall_logloss":round(sum(x["logloss"] for x in outcomes)/n,9) if n else None,
            "source_order":["SOFASCORE","FLASHSCORE","ESPN"],
            "source_raw_sha_and_pit_receipts_verified":True,
            "original_api_football_feature_equivalence_certified":False,
            "scientific_independent_model_certified":False,
            "production_p_matrix_authorized":False,
            "telegram_signal_authorized":False,
            "automatic_wagering":False,"real_money":"BLOCKED"}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--freeze",type=Path,required=True)
    p.add_argument("--results",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if set(args.out.parts)&{"telegram","notifications","daily_prematch_reports","market_portfolio"}:
        raise SystemExit("OOS_RESEARCH_CANNOT_WRITE_PRODUCTION")
    result=evaluate(json.loads(args.freeze.read_text(encoding="utf-8")),args.results)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"prospective_settlements":result["verified_prospective_settlements"],
                      "pending":result["awaiting_authentic_final"],
                      "official_signals":False},sort_keys=True))


if __name__=="__main__":
    main()
