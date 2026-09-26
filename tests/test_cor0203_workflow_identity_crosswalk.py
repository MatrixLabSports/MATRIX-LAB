from pathlib import Path

WORKFLOW = Path(".github/workflows/cor0203-batch-freeze.yml")
CYCLE = Path("scripts/cor0203_production_cycle.sh")


def _text() -> str:
    return CYCLE.read_text(encoding="utf-8-sig")


def test_identity_crosswalk_is_in_production_path():
    text = _text()
    assert "tools.cor0203_build_identity_crosswalk" in text
    assert "python -m tools.cor0203_build_identity_crosswalk" in text
    assert "MATRIX_COR0203_IDENTITY_CROSSWALK_LAST.json" in text
    assert "MATRIX_COR0203_IDENTITY_CROSSWALK_R" in text


def test_preregister_crosswalk_stage_order_is_fail_closed():
    text = _text()
    prereg = text.index("python -m tools.cor0203_preregister_discovery")
    crosswalk = text.index("python -m tools.cor0203_build_identity_crosswalk")
    stage = text.index("python -m tools.cor0203_stage_from_registry")
    assert prereg < crosswalk < stage
