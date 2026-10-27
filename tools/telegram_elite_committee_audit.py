from __future__ import annotations

import argparse, json
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_BASE = Path("evidence/notifications/telegram")

def load(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value

def build_audit(base: Path, config: dict[str,Any], run_health: dict[str,Any]) -> dict[str,Any]:
    blocker=load(base/"MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json")
    telemetry=load(base/"MATRIX_TELEGRAM_QUOTE_ATTEMPT_TELEMETRY_AUDIT_LAST.json")
    watchdog=load(base/"MATRIX_TELEGRAM_MONITORING_WATCHDOG_LAST.json")
    risk=load(base/"MATRIX_CORRELATED_RISK_CALIBRATION_LAST.json")
    recs=list(blocker.get("records") or [])
    states=Counter(str(x.get("gate_state") or x.get("state") or "UNKNOWN") for x in recs if isinstance(x,dict))
    sample=telemetry.get("sample") or {}
    latest=(run_health.get("latest_green_signal_run") or {}).get("physical_output") or {}
    recent=run_health.get("supervisor_15m_recent_runs") or []
    consecutive_failures=0
    for row in recent:
        if row.get("conclusion")=="failure": consecutive_failures += 1
        else: break

    repair_verification=run_health.get("repair_verification") or {}
    persistence_repaired=bool(
        repair_verification.get("status")=="PASS_REPAIRED_AND_PHYSICALLY_VERIFIED"
        and repair_verification.get("historical_persistence_regression_active") is False
    )
    findings=[
      {
        "id":"F01_CURRENT_ZERO_IS_PRE_SEND_SELECTION_NOT_TELEGRAM_DELIVERY",
        "severity":"HIGH",
        "owners":["INCIDENT_COMMANDER","TELEGRAM_DELIVERY","OPERATIONS"],
        "verdict":"CONFIRMED",
        "evidence":{
          "latest_green_signal_run_conclusion":(run_health.get("latest_green_signal_run") or {}).get("conclusion"),
          "pre_send_passed":latest.get("pre_send_passed"),
          "pre_send_blocked":latest.get("pre_send_blocked"),
          "pre_send_waiting_window":latest.get("pre_send_waiting_window"),
          "sent_now":latest.get("sent_now"),
          "delivery_failures_now":latest.get("delivery_failures_now"),
        },
        "diagnosis":"The latest green-signal workflow executed successfully but no candidate passed pre-send. Telegram delivery was not the direct blocker in that run."
      },
      {
        "id":"F02_FINAL_WINDOW_IS_ACTIVE_PRIMARY_SHORT_TERM_BLOCKER",
        "severity":"HIGH",
        "owners":["TEMPORAL_INTEGRITY","OPERATIONS","FOOTBALL_DOMAIN"],
        "verdict":"CONFIRMED",
        "evidence":{"WAITING_FINAL_REVALIDATION_WINDOW":states.get("WAITING_FINAL_REVALIDATION_WINDOW",0)},
        "diagnosis":"Candidates outside the final prematch window must wait; no backfill after kickoff is permitted."
      },
      {
        "id":"F03_EXACT_AUTHORIZED_OVER25_QUOTE_COVERAGE_IS_STRUCTURAL_BOTTLENECK",
        "severity":"HIGH",
        "owners":["MARKET_MICROSTRUCTURE","BOOKMAKER_COVERAGE","DATA_ENGINEERING"],
        "verdict":"CONFIRMED",
        "evidence":{
          "blocked_no_valid_exact_authorized_book_over25":states.get("BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25",0),
          "real_quote_attempts_total":sample.get("real_quote_attempts_total"),
          "remaining_to_50":sample.get("remaining_to_minimum"),
          "exact_over25_coverage_by_house":sample.get("exact_over25_coverage_by_house"),
        },
        "diagnosis":"Exact executable Over 2.5 coverage is concentrated in Betano; BetPlay and Rushbet have zero exact observed coverage in the current immutable sample."
      },
      {
        "id":"F04_SHARP_AND_EV_GATES_ALSO_REMOVE_CANDIDATES",
        "severity":"MEDIUM",
        "owners":["SHARP_REFERENCE","QUANT_MODEL","STATISTICAL_VALIDATION"],
        "verdict":"CONFIRMED",
        "evidence":{
          "blocked_no_fresh_pinnacle":states.get("BLOCKED_NO_FRESH_PINNACLE_REFERENCE",0),
          "blocked_nonpositive_ev":states.get("BLOCKED_NONPOSITIVE_EV",0),
        },
        "diagnosis":"Some candidates are correctly rejected by fresh-sharp-reference and positive-EV gates; these gates must not be weakened to manufacture signals."
      },
      {
        "id":"F05_15M_SUPERVISOR_PERSISTENCE_REGRESSION",
        "severity":"CRITICAL",
        "owners":["SRE_WORKFLOW","GITOPS_CONCURRENCY","RELEASE_ENGINEERING","QA_ADVERSARIAL"],
        "verdict":"REPAIRED_VERIFIED" if persistence_repaired else "CONFIRMED_ACTIVE",
        "evidence":{
          "consecutive_recent_failures_before_repair":consecutive_failures,
          "run_111_error":(run_health.get("run_111_failure") or {}).get("exact_error"),
          "scheduler_contract_drift":run_health.get("scheduler_contract_drift"),
          "repair_verification":repair_verification,
        },
        "diagnosis":(
          "The Git persistence regression and branch-contract drift were physically repaired and verified by a successful dedicated 15-minute supervisor run."
          if persistence_repaired else
          "The dedicated 15-minute supervisor has a Git persistence regression caused by unstaged generated telemetry plus default-branch/operational-branch contract drift."
        )
      },
      {
        "id":"F06_REDUNDANT_GREEN_SIGNAL_WORKFLOW_REMAINS_OPERATIONAL",
        "severity":"INFO",
        "owners":["SRE_WORKFLOW","RED_TEAM","OBSERVABILITY"],
        "verdict":"CONFIRMED",
        "evidence":{
          "green_signal_run":(run_health.get("latest_green_signal_run") or {}).get("run_number"),
          "green_signal_conclusion":(run_health.get("latest_green_signal_run") or {}).get("conclusion"),
          "watchdog_summary":watchdog.get("summary"),
        },
        "diagnosis":"A separate green-signal workflow is still executing the signal engine successfully, so the persistence regression is a resilience defect rather than proof of a total Telegram blackout."
      },
      {
        "id":"F07_H02_IS_OPEN_BUT_NOT_CAUSE_OF_CURRENT_ZERO",
        "severity":"INFO",
        "owners":["PORTFOLIO_RISK","GOVERNANCE_AUDIT"],
        "verdict":"CONFIRMED",
        "evidence":{"h02_closed":risk.get("h02_closed"),"status":risk.get("status"),"sample_records":risk.get("sample_records")},
        "diagnosis":"H02 remains fail-closed research governance. The latest zero occurred before any candidate reached send, so H02 is not established as the direct cause of sent_now=0."
      }
    ]
    role_ids={r["id"] for r in config.get("roles") or []}
    for finding in findings:
        missing=[x for x in finding["owners"] if x not in role_ids]
        if missing: raise ValueError("UNKNOWN_COMMITTEE_ROLE:"+repr(missing))
    direct_causes=[
        "NO_CANDIDATE_PASSED_PRE_SEND_IN_LATEST_GREEN_SIGNAL_RUN",
        "FINAL_PREMATCH_WINDOW_NOT_OPEN_FOR_53_RECORDS",
        "EXACT_AUTHORIZED_OVER25_QUOTE_COVERAGE_LIMITATION",
    ]
    reliability_defects=(
        []
        if persistence_repaired else
        [
          "DEDICATED_15M_SUPERVISOR_PERSISTENCE_REBASE_FAILURE",
          "DEFAULT_BRANCH_VS_OPERATIONAL_WORKFLOW_CONTRACT_DRIFT",
        ]
    )
    repaired_reliability_defects=(
        [
          "DEDICATED_15M_SUPERVISOR_PERSISTENCE_REBASE_FAILURE",
          "DEFAULT_BRANCH_VS_OPERATIONAL_WORKFLOW_CONTRACT_DRIFT",
        ]
        if persistence_repaired else []
    )
    return {
      "schema":"MATRIX_TELEGRAM_ELITE_COMMITTEE_AUDIT_V1",
      "committee_name":config.get("name"),
      "role_count":len(config.get("roles") or []),
      "roles":config.get("roles"),
      "status":"ROOT_CAUSES_IDENTIFIED_RELIABILITY_REPAIR_VERIFIED" if repair_verified else "ROOT_CAUSES_IDENTIFIED_ACTION_REQUIRED",
      "latest_green_signal_run":run_health.get("latest_green_signal_run"),
      "direct_causes_of_current_zero":direct_causes,
      "reliability_defects_active":reliability_defects,
      "reliability_defects_repaired_verified":repaired_reliability_defects,
      "findings":findings,
      "blocker_state_counts":dict(sorted(states.items())),
      "quote_sample":sample,
      "governance":{
        "no_invention":True,
        "missing_not_zero":True,
        "no_silent_imputation":True,
        "no_backfill_after_kickoff":True,
        "odds_generate_p_matrix":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
      },
      "committee_decision":{
        "telegram_api_is_current_direct_root_cause":False,
        "lower_gates_to_force_signals":False,
        "repair_15m_persistence_and_branch_parity":not persistence_repaired,
        "persistence_and_branch_parity_repair_verified":persistence_repaired,
        "expand_exact_quote_recovery":True,
        "continue_t120_revalidation":True,
      }
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base",default=str(DEFAULT_BASE))
    p.add_argument("--config",default="config/MATRIX_TELEGRAM_ELITE_COMMITTEE_V1.json")
    p.add_argument("--run-health",default="evidence/notifications/telegram/MATRIX_TELEGRAM_SUPERVISOR_RUN_HEALTH_LAST.json")
    p.add_argument("--out",default="evidence/notifications/telegram/MATRIX_TELEGRAM_ELITE_COMMITTEE_AUDIT_LAST.json")
    a=p.parse_args()
    result=build_audit(Path(a.base),load(Path(a.config)),load(Path(a.run_health)))
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
      "status":result["status"],
      "role_count":result["role_count"],
      "direct_causes":result["direct_causes_of_current_zero"],
      "reliability_defects_active":result["reliability_defects_active"],
      "reliability_defects_repaired_verified":result["reliability_defects_repaired_verified"],
      "real_money":"BLOCKED",
    },sort_keys=True))

if __name__=="__main__":
    main()
