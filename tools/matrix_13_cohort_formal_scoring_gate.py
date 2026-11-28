"""Formal prospective proper-scoring comparison, exact 600+ settled only.

Never refits, retunes, or promotes. Pre-existing 4000 retrospective sample and
period-goals laboratory are NOT used in this independent settlement cohort.
"""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
from tools.api_football_prospective_api_settlement import _load_ledger
from tools.matrix_13_cohort_independent_settlement import validated_ledger
from tools.matrix_gate600_post_audit import _metrics_for_rows,_binary_metrics

ROOT=Path(__file__).resolve().parents[1]
FREEZE=ROOT/"evidence/api_football/prospective_market_freeze/freeze.json"
PORTFOLIO=ROOT/"evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl"
API=ROOT/"evidence/api_football/prospective_market_freeze/settlement_ledger.jsonl"
ALT=ROOT/"evidence/football_cohort_recovery/MATRIX_INDEPENDENT_VERIFIED_FT_LEDGER.jsonl"
EXACT=ROOT/"evidence/governance/MATRIX_13_MARKET_EXACT_COHORT_CALIBRATION_LAST.json"
OUT=ROOT/"evidence/governance/MATRIX_13_MARKET_FORMAL_SCORING_GATE_LAST.json"
CORE={"MATCH_RESULT_1X2","DOUBLE_CHANCE_1X","DOUBLE_CHANCE_X2",
      "DOUBLE_CHANCE_12","TOTAL_GOALS_OVER_UNDER"}


def assess(cohort,freeze,portfolio,settlements):
    if cohort.get("summary",{}).get("markets_targeted")!=13:
        raise ValueError("REQUIRES_EXACTLY_13_COHORTS")
    src={str(r["fixture_id"]):r for r in freeze["rows"]}
    actual={}
    for x in settlements:
        fid=str(x.get("fixture_id") or "")
        if fid in actual or not fid or x.get("terminal_status")!="FT":
            raise ValueError("SETTLEMENT_CONFLICT_OR_NONFINAL")
        actual[fid]=x
    eligibility={}
    for r in portfolio:
        k=r.get("market_lane")
        if k in CORE and r.get("prospective_admitted") is True:
            eligibility.setdefault(k,set()).add(str(r.get("fixture_id") or r.get("event_id") or ""))
    rows=[]
    for r in cohort["lanes"]:
        lane=r["market_key"]
        n=r["exact_cohort_final_verified"]
        report={"market_key":lane,"exact_verified_ft_count":n,"required_600":600,
                "eligible_to_test":n>=600,"promoted":False,"automatic_wagering":False}
        if n<600:
            report["verdict"]="HOLD_BELOW_600_PROSPECTIVE_EXACT_FT"
            report["remaining"]=600-n
        elif lane not in CORE:
            report["verdict"]="HOLD_DEDICATED_REFERENCE_AND_FORMAL_GATE_REQUIRED"
            report["remaining"]=0
        else:
            sample=[]
            for fid in eligibility.get(lane,set()):
                result=actual.get(fid)
                base=src.get(fid)
                if result is None or base is None:
                    continue
                if str(base.get("kickoff_utc"))[:19]!=str(result.get("kickoff_utc"))[:19]:
                    raise ValueError("KICKOFF_IDENTITY_MISMATCH")
                c=base.get("frozen_research_probabilities")
                p=base.get("poisson_reference")
                if not c or not p:
                    continue
                home,away=result["fulltime_home_goals"],result["fulltime_away_goals"]
                sample.append({
                    "fixture_id":fid,
                    "kickoff_utc":base["kickoff_utc"],
                    "frozen_challenger_probabilities":c,
                    "frozen_poisson_reference":p,
                    "outcomes":{"1x2":"H" if home>away else "D" if home==away else "A",
                                "over_2_5":home+away>=3},
                })
            if len(sample)!=n:
                report["verdict"]="HOLD_FROZEN_REFERENCE_COHORT_NOT_EQUAL_TO_SETTLED_COUNT"
                report["reference_evaluable_count"]=len(sample)
            else:
                if lane=="TOTAL_GOALS_OVER_UNDER":
                    outcomes=[int(x["outcomes"]["over_2_5"]) for x in sample]
                    model=_binary_metrics([float(x["frozen_challenger_probabilities"]["over_2_5"]) for x in sample],outcomes)
                    baseline=_binary_metrics([float(x["frozen_poisson_reference"]["over_2_5"]) for x in sample],outcomes)
                    metrics={"challenger":model,"poisson":baseline,
                             "delta_brier_challenger_minus_poisson":model["brier_score"]-baseline["brier_score"],
                             "delta_log_loss_challenger_minus_poisson":model["log_loss"]-baseline["log_loss"]}
                else:
                    metrics=_metrics_for_rows(sample,lane)
                report["proper_scoring"]=metrics
                beat=(metrics["delta_brier_challenger_minus_poisson"]<0 and
                      metrics["delta_log_loss_challenger_minus_poisson"]<0)
                if lane=="DOUBLE_CHANCE_12":
                    report["verdict"]="NO_GO_RETAIN_EXISTING_DIAGNOSTIC_BLOCK"
                else:
                    report["verdict"]="PASS_SCORING_COMPARISON_NO_PROMOTION" if beat else "NO_GO_PROPER_SCORING_VS_POISSON"
                report["reference_evaluable_count"]=len(sample)
                report["remaining"]=0
        rows.append(report)
    return {
        "schema":"MATRIX_13_MARKET_FORMAL_SCORING_GATE_V1",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":"PASS_READ_ONLY_NO_PROMOTION",
        "lanes":rows,
        "summary":{
            "gate600_final_count":sum(x["eligible_to_test"] for x in rows),
            "formal_core_scoring_comparisons_completed":sum("proper_scoring" in x for x in rows),
            "newly_promoted":0,
        },
        "protections":{
            "frozen_probabilities_only":True,"no_parameter_refit":True,
            "strict_600_exact_final_threshold":True,
            "proper_scoring_vs_original_frozen_poisson":True,
            "no_new_unsupported_ece_threshold":True,
            "retrospective_holdout_not_mixed":True,
            "no_automatic_market_promotion":True,
            "no_telegram_messages":True,"automatic_wagering":False,"real_money":"BLOCKED",
        },
    }


def main():
    cohort=json.loads(EXACT.read_text(encoding="utf-8"))
    frozen=json.loads(FREEZE.read_text(encoding="utf-8"))
    portfolio=[json.loads(line) for line in PORTFOLIO.read_text(encoding="utf-8").splitlines() if line.strip()]
    settlements=_load_ledger(API)+validated_ledger(ALT)
    result=assess(cohort,frozen,portfolio,settlements)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"summary":result["summary"],
        "decisions":[{"market":x["market_key"],"n":x["exact_verified_ft_count"],
                     "verdict":x["verdict"]} for x in result["lanes"]]},sort_keys=True))


if __name__=="__main__":
    main()
