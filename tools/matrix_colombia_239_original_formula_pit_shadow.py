"""Freeze isolated Colombian Over2.5 RESEARCH probabilities via actual original MATRIX math.

The source is the single captured complete ESPN 2026 season, its SHA verified
against the immutable compressed payload. No parameter tuning, official P_MATRIX,
EV evaluation, bookmaker quote inference, Telegram, or money transactions.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from tools.matrix_colombia_239_original_espn_historic_crosswalk import espn_rows,utc
from tools.api_football_market_shadow_p_matrix import PARAMS_OVER25,_inputs_for_target,_pool_over25

SCHEMA="MATRIX_COLOMBIA_239_ORIGINAL_ENGINE_FREE_SOURCE_PIT_SHADOW_V1"

def score(report,espn_raw,*,now=None):
    clock=now or datetime.now(timezone.utc)
    if clock.utcoffset() is None:raise ValueError("SCORING_CLOCK_NOT_TIMEZONE_AWARE")
    clock=clock.astimezone(timezone.utc)
    received=utc(report["espn_received_at_utc"])
    if (report.get("schema")!="MATRIX_COLOMBIA_239_COMPLETE_SEASON_FT_GOALS_AND_FUTURE_IDENTITY_AUDIT_V1"
        or report.get("original_october_asof_finished_fixture_count")!=358
        or report.get("historical_team_ids_one_to_one_crosswalked")!=20
        or report.get("production_p_matrix_authorized") is not False
        or report.get("telegram_signal_authorized") is not False
        or report.get("real_money")!="BLOCKED"
        or hashlib.sha256(espn_raw).hexdigest()!=report.get("espn_fullseason_raw_sha256")):
        raise ValueError("UNTRUSTED_FREE_SOURCE_OR_SHA")
    if clock<received:raise ValueError("SCORING_CLOCK_PRECEDES_RECEIPT")
    history=[]
    for e in espn_rows(espn_raw):
        if e["kickoff"]>=received:continue
        history.append({"fixture_id":e["id"],"kickoff_utc":e["kickoff"],
          "home_team_id":e["home_id"],"away_team_id":e["away_id"],
          "home_goals":e["home_goals"],"away_goals":e["away_goals"]})
    history.sort(key=lambda x:(x["kickoff_utc"],x["fixture_id"]))
    forecasts=[];blocked=[];seen=set()
    for f in report.get("future_native_team_identity_bridged_rows",[]):
        event_id=str(f["espn_current_fixture_id"])
        kickoff=utc(f["kickoff_utc"])
        if event_id in seen:raise ValueError("REPEATED_TARGET_EVENT_ID")
        seen.add(event_id)
        if kickoff<=clock or kickoff<=received:
            blocked.append({"event_id":event_id,"reason":"TARGET_NOT_FUTURE_AT_SCORING"});continue
        if (f.get("sofascore_current_identity_verified") is not False
            or f.get("flashscore_current_identity_verified") is not False
            or f.get("original_api_football_current_fixture_id") is not None):
            raise ValueError("DO_NOT_IMPERSONATE_CANONICAL_CROSSWALK")
        target={"kickoff_utc":kickoff.isoformat(),
          "home_team_id":str(f["home"]["espn_team_id"]),
          "away_team_id":str(f["away"]["espn_team_id"])}
        features,reason=_inputs_for_target(history,target)
        if features is None:
            blocked.append({"event_id":event_id,"reason":reason});continue
        p=_pool_over25(float(features["poisson"]["over_2_5"]),
                       float(features["baseline"]["over_2_5"]))
        if not 0<p<1:raise ValueError("RESEARCH_PROBABILITY_OUT_OF_RANGE")
        forecasts.append({"espn_event_id":event_id,"kickoff_utc":kickoff.isoformat(),
          "original_api_football_239_home_team_id_from_history":f["home"]["original_api_football_team_id_from_history"],
          "original_api_football_239_away_team_id_from_history":f["away"]["original_api_football_team_id_from_history"],
          "p_over25_research_only":round(p,10),
          "original_frozen_model_parameters":dict(PARAMS_OVER25),
          "poisson_over25":round(float(features["poisson"]["over_2_5"]),10),
          "goal_history_baseline_over25":round(float(features["baseline"]["over_2_5"]),10),
          "home_history_count":features["home_history_count"],
          "away_history_count":features["away_history_count"],
          "history_source":features["home_history_source"],
          "scored_at_utc":clock.isoformat(),
          "source_observed_at_utc":received.isoformat(),
          "prematch_source_sha256":report["espn_fullseason_raw_sha256"],
          "original_goal_parity_is_partial":not report.get("all_source_historical_rows_equivalent",False),
          "source_feature_equivalence_certified":False,
          "production_p_matrix_authorized":False,
          "telegram_signal_authorized":False})
    return {"schema":SCHEMA,
      "source":"ESPN_PUBLIC_COL_1_COMPLETE_2026_SEASON",
      "source_raw_sha256":report["espn_fullseason_raw_sha256"],
      "source_receipt_utc":received.isoformat(),
      "scored_at_utc":clock.isoformat(),
      "original_model_imported_unmodified":True,
      "original_parameters":dict(PARAMS_OVER25),
      "parameter_refit":False,
      "target_results_used":False,
      "history_source_goal_parity_all_rows_certified":False,
      "original_six_league_enriched_feature_parity_certified":False,
      "research_scores_count":len(forecasts),
      "research_scores":forecasts,
      "blocked":blocked,
      "production_p_matrix_authorized":False,
      "exact_bookmaker_quotes_verified":False,
      "sharp_reference_verified":False,
      "telegram_signal_authorized":False,
      "automatic_wagering":False,
      "real_money":"BLOCKED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fullseason-report",type=Path,required=True)
    p.add_argument("--compressed-source",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if set(args.out.parts)&{"governance","telegram","notifications","daily_prematch_reports"}:
        raise SystemExit("RESEARCH_FORECAST_CANNOT_ENTER_PRODUCTION")
    report=json.loads(args.fullseason_report.read_bytes())
    compressed=args.compressed_source.read_bytes()
    if hashlib.sha256(compressed).hexdigest()!=report.get("gzip_archive_sha256"):
        raise SystemExit("GZIP_SHA_CONFLICT")
    out=score(report,gzip.decompress(compressed))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(out,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"research_scores":out["research_scores_count"],"official_scores":0,
       "model_parameters_modified":False,"telegram":False}))
if __name__=="__main__":main()
