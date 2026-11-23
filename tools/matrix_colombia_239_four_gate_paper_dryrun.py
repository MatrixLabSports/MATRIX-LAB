"""Four-gate MATRIX Colombia paper-signal admission and OOS readiness (NO SEND).

Real artifacts only. Synthetic price or claim injection cannot unlock green
signals. This module does not import Telegram clients, use network, or access
any token. It prints an auditable NO-BET, never a fabricated green tip.
"""
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path

MIN_PROSPECTIVE_SETTLED=30
def decide(three,shadow,quotes,parity,conflicts,feature=None):
    if (three.get("schema")!="MATRIX_COLOMBIA_239_THREE_SOURCE_RESEARCH_TO_TELEGRAM_GUARD_V1"
        or shadow.get("schema")!="MATRIX_COLOMBIA_239_ORIGINAL_ENGINE_FREE_SOURCE_PIT_SHADOW_V1"
        or parity.get("schema")!="MATRIX_COLOMBIA_239_COMPLETE_SEASON_FT_GOALS_AND_FUTURE_IDENTITY_AUDIT_V1"
        or conflicts.get("schema")!="MATRIX_COLOMBIA_239_TWO_HISTORICAL_KICKOFF_CONTRADICTIONS_V1"
        or quotes.get("schema")!="MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT_V1"):
        raise ValueError("MATRIX_PAPER_GATE_SOURCE_SCHEMA_INVALID")
    inputs=[three,shadow,quotes,parity,conflicts]+([feature] if feature is not None else [])
    if any(s.get("real_money")!="BLOCKED" for s in inputs):
        raise ValueError("REAL_MONEY_PROTECTION_VIOLATED")
    if (shadow.get("original_parameters")!={"a":0.6,"b":0,"c":0.4}
        or shadow.get("production_p_matrix_authorized") is not False
        or shadow.get("telegram_signal_authorized") is not False
        or conflicts.get("discrepancy_count")!=2
        or parity.get("original_results_unmatched_count")!=2):
        raise ValueError("SOURCE_OR_CALIBRATION_GOVERNANCE_INVALID")
    if (three.get("three_calendar_matches")!=2 or
        len(three.get("three_source_matches",[]))!=2 or
        shadow.get("research_scores_count")!=4):
        raise ValueError("THREE_SOURCE_OR_RESEARCH_COHORT_CHANGED")
    if feature is not None and (feature.get("schema")!="MATRIX_COL_239_356_PAIR_ORIGINAL_FEATURE_MATH_PARITY_V1"
        or feature.get("verified_exact_common_finished_fixtures")!=356
        or feature.get("raw_goals_input_parity_within_exact_common_subset") is not True
        or feature.get("all_enriched_source_features_certified") is not False):
        raise ValueError("FEATURE_PARITY_EVIDENCE_UNTRUSTED")
    if quotes.get("bookmaker_quote_verified_count")!=0 or quotes.get("sharp_120s_verified_count")!=0:
        # Independent quote audit may evolve; report counters without treating
        # research quotes as official. Never promote any market on this path.
        quote_reason="RESEARCH_QUOTE_REQUIRES_SEPARATE_OFFICIAL_SOURCE_CERTIFICATION"
    else:quote_reason="NO_AUTHENTIC_CURRENT_EXECUTION_AND_SHARP_QUOTES"
    research={str(x["espn_event_id"]):x for x in shadow["research_scores"]}
    seen=set();events=[]
    for f in three["three_source_matches"]:
        fid=str(f["espn_event_id"])
        if fid in seen or fid not in research:raise ValueError("DUPLICATE_OR_MISSING_PROSPECTIVE_FROZEN_RECORD")
        seen.add(fid)
        forecast=research[fid]
        observed=datetime.fromisoformat(forecast["scored_at_utc"].replace("Z","+00:00"))
        start=datetime.fromisoformat(forecast["kickoff_utc"].replace("Z","+00:00"))
        if observed.utcoffset() is None or start.utcoffset() is None or observed>=start:
            raise ValueError("FORECAST_NOT_GENUINELY_PREMATCH")
        if (not 0<float(forecast["p_over25_research_only"])<1
            or forecast.get("telegram_signal_authorized") is not False
            or forecast.get("production_p_matrix_authorized") is not False
            or f.get("source_fixture_identity_on_three_calendars_verified") is not True):
            raise ValueError("SOURCE_FORECAST_NOT_TRUSTED")
        events.append({"espn_event_id":fid,"kickoff_utc":forecast["kickoff_utc"],
          "model_probability_research_only":forecast["p_over25_research_only"],
          "prospective_forecast_frozen_before_kickoff":True,
          "matched_on_three_provider_calendars":True,
          "prospective_verified_final_result":False,
          "prospective_settlement_count":0,
          "min_prospective_settlements":MIN_PROSPECTIVE_SETTLED,
          "oos_eligible":False,
          "feature_level_equivalent_to_original_producer":False,
          "official_p_matrix":False,"authentic_quotes_accepted":False,
          "green_signal_authorized":False,"paper_message_sent":False})
    return {"schema":"MATRIX_COL_239_FOUR_GATE_PAPER_DRYRUN_NO_SEND_V1",
      "status":"BLOCKED_RESEARCH_INPUT_NOT_OFFICIALLY_CERTIFIED",
      "evidence_source":"VERIFIED_GITHUB_HISTORY_AND_CURRENT_THREE_SOURCE_BLOBS",
      "candidate_fixture_identity_count":len(events),
      "research_prematch_forecasts_count":len(events),
      "historical_matched_results":parity["exact_original_goals_time_and_team_parity_count"],
      "historical_kickoff_conflicts_quarantined":conflicts["discrepancy_count"],
      "goal_only_exact_356_mathematical_feature_parity":feature is not None,
      "all_original_enriched_features_certified":False,
      "prospective_settled_before_kickoff":0,
      "minimum_prospective_settled_for_screening":MIN_PROSPECTIVE_SETTLED,
      "prospective_oos_gate_passed":False,
      "execution_book_and_sharp_pair_verified":False,
      "price_gate_reason":quote_reason,
      "telegram_integration_mode":"OFFLINE_NEGATIVE_TEST_NO_NETWORK_NO_SEND",
      "telegram_api_calls":0,"telegram_messages_sent":0,
      "official_green_signals":0,"production_p_matrix_authorized":False,
      "automatic_wagering":False,"real_money":"BLOCKED",
      "events":events}
def main():
    p=argparse.ArgumentParser()
    for name in ("three","shadow","quotes","parity","conflicts","out"):
        p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--feature",type=Path)
    a=p.parse_args()
    if set(a.out.parts)&{"telegram","notifications","governance","daily_prematch_reports"}:
        raise SystemExit("NO_PRODUCTION_PATHS_IN_OFFLINE_DRYRUN")
    load=lambda path:json.loads(path.read_bytes())
    result=decide(load(a.three),load(a.shadow),load(a.quotes),load(a.parity),load(a.conflicts),
        load(a.feature) if a.feature and a.feature.is_file() else None)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"forecast_count":result["research_prematch_forecasts_count"],
      "paper_messages_sent":0,"official_green":0,"real_money":"BLOCKED"}))
if __name__=="__main__":main()
