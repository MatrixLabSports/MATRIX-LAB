import json
from pathlib import Path

from tools.api_football_prospective_supervisor import MIN_SETTLEMENT_AGE_MINUTES


MANDATE=Path("evidence/audit/MATRIX_FOOTBALL_SCHEDULER_RESILIENCE_MANDATE_V1.json")
INDEX=Path("evidence/audit/MATRIX_PERMANENT_MANDATE_INDEX_V1.json")


def test_scheduler_resilience_mandate_is_permanent_and_active():
    d=json.loads(MANDATE.read_text(encoding="utf-8"))
    assert d["status"]=="ACTIVE"
    assert d["mode"]=="PERMANENT_ADDITIVE"
    assert d["change_control"]=="USER_EXPLICIT_REPLACE_MODIFY_SUSPEND_REVOKE_ONLY"


def test_scheduler_resilience_contract_is_not_weakened():
    d=json.loads(MANDATE.read_text(encoding="utf-8"))
    a=d["architecture"]
    assert a["legacy_settlement_schedule"] is False
    assert a["legacy_calibration_schedule"] is False
    assert a["supervisor_schedule_utc_minutes"]==[7,22,37,52]
    assert a["minimum_settlement_age_minutes"]==45
    assert MIN_SETTLEMENT_AGE_MINUTES==45
    assert a["final_delay_minutes"]==120
    assert a["settlement_and_calibration_same_cycle"] is True
    assert set(a["supervisor_workflow_run_fallbacks"])=={
        "COR02-03 repo-native hourly scheduler",
        "API-Football daily prospective production",
    }


def test_scheduler_resilience_hard_gates_remain_fail_closed():
    d=json.loads(MANDATE.read_text(encoding="utf-8"))
    h=d["hard_invariants"]
    assert h["settlement_final_only"] is True
    assert h["outcomes_do_not_auto_open_metrics"] is True
    assert h["calibration_thresholds"]==[30,50,100]
    assert h["parameter_tuning_allowed"] is False
    assert h["original_357_holdout_reuse_allowed"] is False
    assert h["p_matrix_status"]=="NOT_GENERATED"
    assert h["automatic_wagering"] is False
    assert h["real_money"]=="BLOCKED"
    assert h["physical_workflow_evidence_required"] is True


def test_scheduler_resilience_mandate_is_in_permanent_index():
    d=json.loads(INDEX.read_text(encoding="utf-8"))
    rows={row["id"]:row for row in d["mandates"]}
    assert "FOOTBALL_SCHEDULER_RESILIENCE_MANDATE_V1" in rows
    row=rows["FOOTBALL_SCHEDULER_RESILIENCE_MANDATE_V1"]
    assert row["status"]=="PERMANENT_ACTIVE"
    assert row["path"]=="docs/governance/MATRIX_FOOTBALL_SCHEDULER_RESILIENCE_MANDATE_V1.md"
