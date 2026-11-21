"""Fail-closed committee adjudication for 5 markets reaching 604 authentic FT.

Keeps prospective calibration statistics distinct from production readiness.
No action in this module can promote an additional market, rewrite trained
parameters, send Telegram signals or place a wager.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STABILITY=ROOT/"evidence/governance/MATRIX_FIVE_MARKET_ELITE_CALIBRATION_STABILITY_LAST.json"
FORMAL=ROOT/"evidence/governance/MATRIX_13_MARKET_FORMAL_SCORING_GATE_LAST.json"
SUPERVISOR=ROOT/"evidence/market_portfolio/MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json"
ONE_X=ROOT/"evidence/api_football/governance/MATRIX_DOUBLE_CHANCE_1X_PROMOTION_READINESS_LAST.json"
OVER=ROOT/"evidence/api_football/governance/over_2_5_p_matrix_promotion.json"
OUT=ROOT/"evidence/governance/MATRIX_FIVE_MARKET_ELITE_GOVERNANCE_DECISION_LAST.json"
FIVE=(
    "TOTAL_GOALS_OVER_UNDER","DOUBLE_CHANCE_1X","MATCH_RESULT_1X2",
    "DOUBLE_CHANCE_X2","DOUBLE_CHANCE_12",
)
NO_GO={"MATCH_RESULT_1X2","DOUBLE_CHANCE_X2","DOUBLE_CHANCE_12"}


def _hash(data:dict)->str:
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":"),
                                      ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def adjudicate(stability:dict, formal:dict, supervisor:dict, one_x:dict, over:dict)->dict:
    if stability.get("status")!="RESEARCH_EXPERIMENT_DIAGNOSTIC_NO_PROMOTIONS":
        raise ValueError("STABILITY_CERTIFICATION_MISSING")
    if (stability.get("invariants") or {}).get("real_money")!="BLOCKED":
        raise ValueError("INCONSISTENT_REAL_MONEY_GUARD")
    if (formal.get("summary") or {}).get("gate600_final_count")!=5:
        raise ValueError("EXACT_5_MARKETS_GATE600_REQUIRED")
    if one_x.get("market")!="DOUBLE_CHANCE_1X" or one_x.get("promotion_allowed") is not False:
        raise ValueError("EXPLICIT_1X_PROMOTION_GATE_MUST_STILL_BE_BLOCKED")
    if over.get("promotion_status")!="PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY":
        raise ValueError("PREVIOUS_OVER25_PRODUCTION_AUTHORIZATION_NOT_CERTIFIED")
    formal_map={r["market_key"]:r for r in formal.get("lanes",[]) if r["market_key"] in FIVE}
    if len(formal_map)!=5 or set(formal_map)!=set(FIVE):
        raise ValueError("FIVE_MARKETS_MISSING_OR_DUPLICATED")
    if any(formal_map[k].get("exact_verified_ft_count")!=604 for k in FIVE):
        raise ValueError("604_VERIFIED_FINAL_COHORT_NOT_UNCHANGED")
    sup={r["market_key"]:r for r in supervisor.get("rows",[]) if r.get("market_key") in FIVE}
    if set(sup)!=set(FIVE):
        raise ValueError("FIVE_MARKET_SUPERVISOR_ROWS_MISSING")
    if (sup["DOUBLE_CHANCE_1X"]["production_authorized"] is not False
        or sup["DOUBLE_CHANCE_1X"]["operational_state"]!="LAB"
        or sup["TOTAL_GOALS_OVER_UNDER"]["operational_state"]!="ACTIVE"):
        raise ValueError("SUPERVISOR_PRODUCTION_SCOPE_CHANGED")
    metrics=stability.get("market_results") or {}
    if set(metrics)!={"DOUBLE_CHANCE_1X","TOTAL_GOALS_OVER_UNDER"}:
        raise ValueError("MISSING_TWO_MARKET_STABILITY_PROOF")
    one_x_result=metrics["DOUBLE_CHANCE_1X"]
    over_result=metrics["TOTAL_GOALS_OVER_UNDER"]
    for doc in (one_x_result,over_result):
        if (doc.get("settled_fixtures")!=604
            or doc.get("candidate_promoted") is not False
            or doc.get("existing_frozen_parameters_modified") is not False
            or doc.get("chronological_split",{}).get("no_train_holdout_fixture_overlap") is not True):
            raise ValueError("INVALID_TEMPORAL_OR_FROZEN_CANDIDATE_PROOF")
    # Temporal audit supersedes an apparently favorable pooled proper-score delta.
    # A candidate "improvement" needs new prospective evidence, not a backtest promotion.
    one_x_holdout=one_x_result["proper_scores"]
    over_holdout=over_result["proper_scores"]
    one_x_vs_poisson={
        "original_brier_delta":one_x_holdout["holdout_original"]["brier"]-one_x_holdout["holdout_poisson"]["brier"],
        "original_log_loss_delta":one_x_holdout["holdout_original"]["log_loss"]-one_x_holdout["holdout_poisson"]["log_loss"],
        "recalibrated_brier_delta":one_x_holdout["holdout_intercept_candidate"]["brier"]-one_x_holdout["holdout_poisson"]["brier"],
        "recalibrated_log_loss_delta":one_x_holdout["holdout_intercept_candidate"]["log_loss"]-one_x_holdout["holdout_poisson"]["log_loss"],
    }
    over_candidate_vs_existing={
        "brier_delta":over_holdout["holdout_intercept_candidate"]["brier"]-over_holdout["holdout_original"]["brier"],
        "log_loss_delta":over_holdout["holdout_intercept_candidate"]["log_loss"]-over_holdout["holdout_original"]["log_loss"],
    }
    rows=[]
    for market in FIVE:
        if market=="TOTAL_GOALS_OVER_UNDER":
            decision="MAINTAIN_HISTORICALLY_APPROVED_OVER25_ONLY_NO_EXPERIMENTAL_REFIT"
            blocking=["EXPLORATORY_CALIBRATION_NOT_APPROVED_FOR_PRODUCTION",
                      "EXACT_BOOKMAKER_QUOTE_EV_FRESHNESS_AND_KICKOFF_GATES_STILL_REQUIRED"]
            historical=True
        elif market=="DOUBLE_CHANCE_1X":
            decision="NO_GO_NEW_1X_PROMOTION_HOLD_SEPARATE_OOS_AND_PRICE_ENGINE"
            blocking=list(one_x.get("blockers") or [])
            blocking.append("CHRONOLOGICAL_1X_EXPERIMENT_HAS_NO_PROVEN_POISSON_SUPERIORITY")
            historical=False
        else:
            decision="NO_GO_CHALLENGER_PROPER_SCORING"
            blocking=["PROPER_SCORING_VS_POISSON_NOT_SUPERIOR"]
            if market=="DOUBLE_CHANCE_12":
                decision="NO_GO_EXISTING_DIAGNOSTIC_REJECTION_REMAINS"
            historical=False
        rows.append({
            "market_key":market,
            "exact_prospectively_frozen_final_count":604,
            "original_formal_verdict":formal_map[market]["verdict"],
            "governance_decision":decision,
            "blockers":blocking,
            "historical_over25_scope_retained":historical,
            "newly_authorized_for_telegram":False,
            "parameter_changes":False,
            "automatic_wagering":False,
        })
    return {
        "schema":"MATRIX_FIVE_MARKET_ELITE_GOVERNANCE_DECISION_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status":"PASS_FAIL_CLOSED_ELITE_ADJUDICATION",
        "source_hashes_sha256":{"stability":_hash(stability),"formal":_hash(formal),
            "supervisor":_hash(supervisor),"1x_readiness":_hash(one_x),
            "over25_historical_promotion":_hash(over)},
        "markets":rows,
        "diagnostic_findings":{
            "one_x_strictly_later_holdout_vs_poisson":one_x_vs_poisson,
            "over25_experimental_intercept_vs_frozen_existing":over_candidate_vs_existing,
            "pooled_comparison_not_sufficient_for_new_promotion":True,
            "new_calibration_candidate_chosen_for_production":False,
            "one_x_extra_gov_oos_remaining":stability["existing_governance"]["double_chance_1x_oos_remaining"],
            "one_x_oos_sealed":stability["existing_governance"]["double_chance_1x_oos_metrics_opened"] is False,
        },
        "summary":{
            "markets_with_at_least_600_authentic_ft":5,
            "historically_governed_over25_scope_maintained":1,
            "new_market_promotions":0,
            "experimental_recalibrations_promoted":0,
            "markets_blocked_for_new_promotion":4,
        },
        "protections":{
            "revalidate_real_time_exact_odds_before_any_existing_over25_signal":True,
            "new_green_signals_authorized_by_audit":False,
            "preregistered_1000_oos_not_overridden_by_604":True,
            "no_original_parameter_change":True,
            "no_automatic_wagering":True,
            "real_money":"BLOCKED",
        }
    }


def main():
    load=lambda p:json.loads(p.read_text(encoding="utf-8"))
    report=adjudicate(load(STABILITY),load(FORMAL),load(SUPERVISOR),load(ONE_X),load(OVER))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"summary":report["summary"],
        "one_x_future_vs_poisson":report["diagnostic_findings"]["one_x_strictly_later_holdout_vs_poisson"],
        "over25_experiment_vs_original":report["diagnostic_findings"]["over25_experimental_intercept_vs_frozen_existing"]},
        sort_keys=True))


if __name__=="__main__":
    main()
