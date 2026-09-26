from pathlib import Path

WORKFLOW = Path(".github/workflows/cor0203-batch-freeze.yml")


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8-sig")


def test_identity_crosswalk_is_in_production_path():
    text = _text()
    assert "tools/cor0203_build_identity_crosswalk.py" in text
    assert "python -m tools.cor0203_build_identity_crosswalk" in text
    assert "MATRIX_COR0203_IDENTITY_CROSSWALK_LAST.json" in text
    assert "MATRIX_COR0203_IDENTITY_CROSSWALK_R" in text


def test_preregister_crosswalk_stage_order_is_fail_closed():
    text = _text()
    prereg = text.index("Preregister newly discovered eligible events before features")
    crosswalk = text.index("Build strong provider-to-canonical identity crosswalks")
    stage = text.index("Auto-stage preregistered events from sealed player registry")
    assert prereg < crosswalk < stage
