"""Real prospective Championship research input: source hashes, individual PIT history.

No API-Football fixture ID invention. Not a canonical generator and NEVER
authorizes execution, Telegram, or real-money wagering.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.research.football.match_analysis_input import (
    FootballHistoryObservation, FootballMatchAnalysisInput, assess_match_analysis_readiness,
)
from tools.api_football_market_shadow_p_matrix import _pool_over25, _score_probs

def utc(s):
    stamp=datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("PROSPECTIVE_TIMESTAMP_NAIVE")
    return stamp.astimezone(timezone.utc)

def source_digest(payload):
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()

def by_id(rows,key):
    if not isinstance(rows,list): raise ValueError("PROSPECTIVE_ROWS_MISSING")
    obj={}
    for row in rows:
        if not isinstance(row,dict): raise ValueError("PROSPECTIVE_ROW_NOT_OBJECT")
        fid=str(row.get(key) or "")
        if not fid or fid in obj: raise ValueError("PROSPECTIVE_DUPLICATE_OR_MISSING_ID")
        obj[fid]=row
    return obj

def report(intake,sofa,flash,shadow,*,now:datetime):
    now=utc(now.isoformat())
    day=intake.get("target_date_bogota")
    if (intake.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
        or intake.get("source")!="FOOTBALL_DATA_ORG"
        or intake.get("provider_status")!="AUTHENTICATED_FIXTURE_CAPTURE"
        or not day or day!=sofa.get("target_date_bogota")
        or day!=flash.get("target_date_bogota")
        or day!=shadow.get("target_date_bogota")):
        raise ValueError("PROSPECTIVE_SOURCE_SCOPE_INVALID")
    for doc in (intake,sofa,flash,shadow):
        if doc.get("real_money")!="BLOCKED": raise ValueError("PROSPECTIVE_REAL_MONEY_INVALID")
    if (intake.get("signal_generation_authorized") is not False
        or sofa.get("signal_generation_authorized") is not False
        or flash.get("signal_generation_authorized") is not False
        or shadow.get("market_signal_authorized") is not False
        or shadow.get("parameter_refit") is not False):
        raise ValueError("PROSPECTIVE_SIGNAL_GOVERNANCE_INVALID")
    if flash.get("sofascore_verified") is not True or flash.get("flashscore_verified") is not True:
        raise ValueError("PROSPECTIVE_CALENDAR_LINK_UNVERIFIED")
    if (shadow.get("model")!="calibrated_log_pool_v1"
        or shadow.get("frozen_parameters")!={"a":0.6,"b":0.0,"c":0.4}):
        raise ValueError("PROSPECTIVE_MODEL_CONTRACT_CHANGED")
    source_at=utc(intake["generated_at_utc"])
    scored_at=utc(shadow["completed_at_utc"])
    source_age=(now-source_at).total_seconds()
    if not (0 <= source_age <= 1800 and source_at <= scored_at <= now):
        raise ValueError("PROSPECTIVE_INTAKE_STALE_OR_TIME_ORDER_INVALID")
    fixture_map=by_id(intake.get("fixtures"),"source_fixture_id")
    sofa_map=by_id(sofa.get("matched"),"fixture_id")
    flash_map=by_id(flash.get("matched"),"source_fixture_id")
    score_map=by_id(shadow.get("scored"),"source_fixture_id")
    if (len(fixture_map)!=intake.get("fixture_count")
        or len(sofa_map)!=sofa.get("matched_count")
        or len(flash_map)!=flash.get("matched_count")
        or len(score_map)!=shadow.get("scored_count")):
        raise ValueError("PROSPECTIVE_SOURCE_COUNT_MISMATCH")
    output=[]
    for fid,f in sorted(fixture_map.items()):
        if f.get("source_competition_code")!="ELC" or str(f.get("source_competition_id"))!="2016":
            continue
        row={"source_fixture_id":fid,"home":f.get("home"),"away":f.get("away"),
             "kickoff_utc":f.get("kickoff_utc"),"status":"BLOCKED",
             "research_history_count_home":None,"research_history_count_away":None,
             "governed_probability_authorized":False,"telegram_signal_authorized":False}
        output.append(row)
        try:
            kickoff=utc(f["kickoff_utc"])
            if not now<kickoff or not scored_at<kickoff:
                row["status"]="BLOCKED_KICKOFF_OR_SCORE_NOT_PREMATCH";continue
            b,c,s=sofa_map.get(fid),flash_map.get(fid),score_map.get(fid)
            if b is None or c is None or s is None:
                row["status"]="BLOCKED_TRIPLE_IDENTITY_OR_SCORE_MISSING";continue
            if (b.get("identity_time_and_teams_verified") is not True
                or c.get("three_source_calendar_identity_verified") is not True
                or b.get("kickoff_utc")!=f["kickoff_utc"]
                or c.get("kickoff_utc")!=f["kickoff_utc"]
                or not b.get("sofascore_event_id")
                or str(b["sofascore_event_id"])!=str(c.get("sofascore_event_id"))
                or not c.get("flashscore_mid")
                or str(s.get("kickoff_utc"))!=f["kickoff_utc"]
                or str(s.get("competition_id"))!="2016"
                or s.get("signal_generation_authorized") is not False):
                row["status"]="BLOCKED_TRIPLE_IDENTITY_CONFLICT";continue
            provenance=s.get("prospective_history_provenance") or {}
            if provenance.get("status")!="PROSPECTIVE_HISTORY_ROWS_OBSERVED":
                row["status"]="BLOCKED_PIT_PROVENANCE_NOT_CAPTURED";continue
            as_of=utc(provenance.get("history_observed_at_utc"))
            if not source_at<=as_of<=scored_at or as_of>=kickoff:
                row["status"]="BLOCKED_PIT_OBSERVED_TIME";continue
            hashval=provenance.get("source_payload_sha256")
            if hashval!=s.get("history_sha256") or not isinstance(hashval,str) or len(hashval)!=64:
                row["status"]="BLOCKED_HISTORICAL_RESPONSE_HASH";continue
            history={}
            for side in ("home","away"):
                expected_id=str(f.get(f"{side}_source_team_id") or "")
                team_name=str(f.get(side) or "")
                if not expected_id or not team_name:
                    raise ValueError("MISSING_TEAM_ID")
                values=[]
                for h in provenance.get(f"{side}_history",[]):
                    if h.get("source_provider")!="FOOTBALL_DATA_ORG":
                        raise ValueError("HISTORY_PROVIDER_MISMATCH")
                    if h.get("source_payload_sha256")!=hashval:
                        raise ValueError("HISTORY_HASH_MISMATCH")
                    if h.get("team_id")!=expected_id:
                        raise ValueError("HISTORY_TEAM_MISMATCH")
                    values.append(FootballHistoryObservation(
                        fixture_id=h["fixture_id"],kickoff_utc=h["kickoff_utc"],
                        team_id=expected_id,team_name=team_name,
                        opponent_id=h.get("opponent_id"),
                        opponent_name=h["opponent_name"],venue_role=h["venue_role"],
                        goals_for=h["goals_for"],goals_against=h["goals_against"],
                        competition="ELC",source_provider="FOOTBALL_DATA_ORG",
                        observed_at_utc=h["observed_at_utc"],
                        source_payload_sha256=hashval,
                        fixture_identity_kind="provider",
                        source_reference="football-data.org/v4/competitions/2016/matches",
                    ))
                history[side]=tuple(values)
            item=FootballMatchAnalysisInput(
                benchmark_id="MATRIX_INDEPENDENT_CHAMPIONSHIP_PROSPECTIVE_SHADOW_V1",
                target_key="FOOTBALL_DATA_ORG:"+fid,
                fixture_id=fid,as_of_utc=as_of.isoformat(),
                kickoff_utc=kickoff.isoformat(),
                home_team_id=str(f["home_source_team_id"]),home_team_name=str(f["home"]),
                away_team_id=str(f["away_source_team_id"]),away_team_name=str(f["away"]),
                competition_id="2016",competition_name=str(f.get("league") or "Championship"),
                season=None,round_name=None,venue_name=None,
                fixture_source_provider="FOOTBALL_DATA_ORG",
                fixture_payload_sha256=intake["response_sha256"],
                fixture_id_namespace="FOOTBALL_DATA_ORG",
                home_team_id_namespace="FOOTBALL_DATA_ORG",
                away_team_id_namespace="FOOTBALL_DATA_ORG",
                home_history=history["home"],away_history=history["away"],
            )
            readiness=assess_match_analysis_readiness(item)
            row["research_history_count_home"]=readiness.home_history_count
            row["research_history_count_away"]=readiness.away_history_count
            if not readiness.ready:
                row["status"]="BLOCKED_HISTORICAL_READINESS";continue
            # Independent Poisson re-computation from the *individual*
            # authenticated observations, not from the already-scored model.
            # The frozen model averages the last 20 team scores, home and
            # away oriented, and clips both expected-goal lambdas.
            home_pairs=history["home"][:20]
            away_pairs=history["away"][:20]
            if len(home_pairs)<5 or len(away_pairs)<5:
                row["status"]="BLOCKED_POISSON_REPLAY_HISTORY_INSUFFICIENT";continue
            hl=min(5.0,max(0.05,(
                sum(h.goals_for for h in home_pairs)/len(home_pairs)
                +sum(h.goals_against for h in away_pairs)/len(away_pairs))/2.0))
            al=min(5.0,max(0.05,(
                sum(h.goals_for for h in away_pairs)/len(away_pairs)
                +sum(h.goals_against for h in home_pairs)/len(home_pairs))/2.0))
            replay_poisson=_score_probs(hl,al)["over_2_5"]
            archived_poisson=float(s["poisson_over25_research_component"])
            if (not math.isfinite(archived_poisson)
                or abs(replay_poisson-archived_poisson)>1e-9):
                row["status"]="BLOCKED_AUTHENTIC_HISTORY_POISSON_MISMATCH"
                continue
            row["research_poisson_recomputed_from_authenticated_history"]=round(replay_poisson,12)
            row["research_expected_home_goals_recomputed"]=round(hl,8)
            row["research_expected_away_goals_recomputed"]=round(al,8)
            raw_prob=float(s["p_over25_research"])
            expected=_pool_over25(
                float(s["poisson_over25_research_component"]),
                float(s["baseline_over25_research_component"]))
            if (not math.isfinite(raw_prob) or not 0<raw_prob<1
                or abs(expected-raw_prob)>1e-9):
                row["status"]="BLOCKED_ORIGINAL_MODEL_RECOMPUTATION_MISMATCH";continue
            row.update({
                "status":"PASS_PROSPECTIVE_RESEARCH_HISTORY_ONLY",
                "research_input_sha256":item.canonical_sha256(),
                "research_as_of_utc":as_of.isoformat(),
                "research_source_history_sha256":hashval,
                "research_model_probability_over25":round(expected,10),
                "research_ready_for_experimental_evaluation":True,
                "reference_fixture_namespace":"FOOTBALL_DATA_ORG",
                "original_api_football_fixture_crosswalk_verified":False,
                "original_enriched_source_parity_proven_for_this_fixture":False,
                "governed_probability_authorized":False,
                "telegram_signal_authorized":False,
            })
        except (KeyError,TypeError,ValueError,OverflowError):
            row["status"]="BLOCKED_INVALID_PROVENANCE_OR_IDENTITY"
    return {
        "schema":"MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION_V1",
        "source_binding_schema":"MATRIX_PROSPECTIVE_PIT_EXACT_FOUR_SOURCE_BINDING_V1",
        "source_intake_sha256":source_digest(intake),
        "source_shadow_sha256":source_digest(shadow),
        "source_sofa_sha256":source_digest(sofa),
        "source_flash_sha256":source_digest(flash),
        "source_intake_generated_at_utc":source_at.isoformat(),
        "source_shadow_completed_at_utc":scored_at.isoformat(),
        "target_date_bogota":day,
        "observed_at_utc":now.isoformat(),
        "status":"RESEARCH_ONLY_NO_PRODUCTION_AUTHORIZATION",
        "championship_fixture_count":len(output),
        "prospective_research_history_certified_count":sum(
            x["status"]=="PASS_PROSPECTIVE_RESEARCH_HISTORY_ONLY" for x in output),
        "production_p_matrix_authorized_count":0,
        "rows":output,
        "historical_archive_replay_is_not_prospective_provider_parity":True,
        "calibration_untouched":True,"no_target_results_used":True,
        "no_real_money":True,"real_money":"BLOCKED",
        "automatic_wagering":False,"telegram_signal_authorized":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",required=True)
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if "daily_prematch_reports" in args.out.parts or "tennis_signals" in args.out.parts:
        raise SystemExit("PROSPECTIVE_RESEARCH_CANNOT_CREATE_PRODUCTION_SIGNAL")
    folder=args.root/"evidence"/"football_world_inventory"/args.date
    fn=lambda filename:json.loads((folder/filename).read_text(encoding="utf-8"))
    result=report(
        fn("MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json"),
        fn("MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json"),
        fn("MATRIX_FLASH_FOOTBALL_CROSSCHECK.json"),
        fn("MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"),
        now=datetime.now(timezone.utc))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in (
      "championship_fixture_count","prospective_research_history_certified_count",
      "production_p_matrix_authorized_count","telegram_signal_authorized")},sort_keys=True))

if __name__=="__main__":
    main()
