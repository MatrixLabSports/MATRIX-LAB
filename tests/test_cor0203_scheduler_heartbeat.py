from pathlib import Path

WORKFLOW = Path(".github/workflows/cor0203-batch-freeze.yml")


def test_scheduler_heartbeat_is_a_governed_production_trigger():
    text = WORKFLOW.read_text(encoding="utf-8-sig")
    assert "evidence/cor0203/runtime/MATRIX_COR0203_SCHEDULER_HEARTBEAT.json" in text
    assert "concurrency:" in text
    assert "cancel-in-progress: false" in text
