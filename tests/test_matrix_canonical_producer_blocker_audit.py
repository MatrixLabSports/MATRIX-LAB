from pathlib import Path
from tools.matrix_canonical_producer_blocker_audit import audit, WORKFLOWS, GATES


def test_workflow_gates_detected_without_claiming_runtime_success(tmp_path):
    for lane, relative in WORKFLOWS.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(GATES[lane].values()), encoding="utf-8")
    result = audit(tmp_path)
    assert all(x["status"] == "STATIC_GATES_PRESENT" for x in result["workflows"].values())
    assert result["runtime_failure_cause_confirmed"] is False
    assert result["canonical_generation_verified"] is False
    assert result["telegram_delivery_verified"] is False
    assert result["automatic_wagering"] is False


def test_missing_workflows_are_not_marked_healthy(tmp_path):
    result = audit(tmp_path)
    assert all(x["status"] == "WORKFLOW_MISSING" for x in result["workflows"].values())
    assert result["workflow_runs_inspected"] is False


def test_missing_gate_is_reported(tmp_path):
    for lane, relative in WORKFLOWS.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")
    result = audit(tmp_path)
    assert all(x["status"] == "STATIC_GATE_MISSING" for x in result["workflows"].values())
