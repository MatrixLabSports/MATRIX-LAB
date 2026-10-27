import json
from pathlib import Path
from tools.telegram_elite_committee_audit import build_audit

def dump(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj),encoding="utf-8")

def test_committee_separates_delivery_from_pre_send_and_detects_persistence_regression(tmp_path: Path):
    base=tmp_path/"evidence/notifications/telegram"
    dump(base/"MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json",{"records":[
      {"gate_state":"WAITING_FINAL_REVALIDATION_WINDOW"},
      {"gate_state":"BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25"},
      {"gate_state":"BLOCKED_NO_FRESH_PINNACLE_REFERENCE"},
      {"gate_state":"BLOCKED_NONPOSITIVE_EV"},
    ]})
    dump(base/"MATRIX_TELEGRAM_QUOTE_ATTEMPT_TELEMETRY_AUDIT_LAST.json",{"sample":{
      "real_quote_attempts_total":18,"remaining_to_minimum":32,
      "exact_over25_coverage_by_house":{"betano":15,"betplay":0,"rushbet":0}
    }})
    dump(base/"MATRIX_TELEGRAM_MONITORING_WATCHDOG_LAST.json",{"summary":{"status":"PASS"}})
    dump(base/"MATRIX_CORRELATED_RISK_CALIBRATION_LAST.json",{"h02_closed":False,"status":"READY_FAIL_CLOSED","sample_records":56})
    roles=["INCIDENT_COMMANDER","SRE_WORKFLOW","GITOPS_CONCURRENCY","TELEGRAM_DELIVERY","QUANT_MODEL","MARKET_MICROSTRUCTURE","SHARP_REFERENCE","BOOKMAKER_COVERAGE","TEMPORAL_INTEGRITY","DATA_ENGINEERING","IDENTITY_RESOLUTION","OBSERVABILITY","QA_ADVERSARIAL","SECURITY_SECRETS","PORTFOLIO_RISK","STATISTICAL_VALIDATION","FOOTBALL_DOMAIN","TENNIS_DOMAIN","GOVERNANCE_AUDIT","RED_TEAM","RELEASE_ENGINEERING","OPERATIONS"]
    cfg={"name":"test","roles":[{"id":x} for x in roles]}
    health={"latest_green_signal_run":{"conclusion":"success","run_number":1250,"physical_output":{
      "pre_send_passed":0,"pre_send_blocked":75,"pre_send_waiting_window":53,"sent_now":0,"delivery_failures_now":0}},
      "supervisor_15m_recent_runs":[{"conclusion":"failure"},{"conclusion":"failure"},{"conclusion":"failure"}],
      "run_111_failure":{"exact_error":"error: cannot rebase: You have unstaged changes."},
      "scheduler_contract_drift":{"main_and_operational_workflow_equal":False}}
    out=build_audit(base,cfg,health)
    assert out["role_count"]==22
    assert out["committee_decision"]["telegram_api_is_current_direct_root_cause"] is False
    assert out["committee_decision"]["lower_gates_to_force_signals"] is False
    assert "DEDICATED_15M_SUPERVISOR_PERSISTENCE_REBASE_FAILURE" in out["reliability_defects_active"]
    ids={x["id"] for x in out["findings"]}
    assert "F01_CURRENT_ZERO_IS_PRE_SEND_SELECTION_NOT_TELEGRAM_DELIVERY" in ids
    assert "F05_15M_SUPERVISOR_PERSISTENCE_REGRESSION" in ids
    assert out["governance"]["real_money"]=="BLOCKED"
