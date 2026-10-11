from pathlib import Path

CYCLE = Path("scripts/cor0203_production_cycle.sh")
WORKFLOW = Path(".github/workflows/cor0203-batch-freeze.yml")


def test_source_readiness_runs_immediately_after_discovery():
    text = CYCLE.read_text(encoding="utf-8-sig")
    discovery = text.index("python -m tools.cor0203_durable_discovery")
    readiness = text.index("python -m tools.cor0203_source_readiness")
    prereg = text.index("python -m tools.cor0203_preregister_discovery")
    assert discovery < readiness < prereg


def test_disconnected_source_cannot_finish_green_as_no_events():
    text = CYCLE.read_text(encoding="utf-8-sig")
    assert "SOURCE_NOT_READY:" in text
    assert 'if not x["ready"]' in text
    assert "MATRIX_COR0203_SOURCE_READINESS_*.json" in text


def test_source_readiness_code_change_triggers_cycle():
    text = WORKFLOW.read_text(encoding="utf-8-sig")
    assert "tools/cor0203_source_readiness.py" in text
    assert "tools/cor0203_durable_discovery.py" in text
