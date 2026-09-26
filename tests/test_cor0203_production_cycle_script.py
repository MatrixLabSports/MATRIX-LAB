import subprocess
from pathlib import Path

SCRIPT = Path("scripts/cor0203_production_cycle.sh")


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8-sig")


def test_cycle_shell_is_syntactically_valid():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_cycle_preserves_governed_ordering():
    text = _text()
    prereg = text.index("python -m tools.cor0203_preregister_discovery")
    crosswalk = text.index("python -m tools.cor0203_build_identity_crosswalk")
    stage = text.index("python -m tools.cor0203_stage_from_registry")
    runner = text.index("python -m tools.cor0203_batch_runner")
    assert prereg < crosswalk < stage < runner


def test_cycle_keeps_holdout_sealed_and_persists_all_outputs():
    text = _text()
    assert 'assert payload.get("metrics") == "SEALED_UNTIL_600"' in text
    assert 'assert payload.get("outcomes_read") == 0' in text
    assert "MATRIX_COR0203_IDENTITY_CROSSWALK_R*.json" in text
    assert "MATRIX_COR0203_HOLDOUT_BATCH_R*.json" in text
    assert 'git rebase "origin/$TARGET_BRANCH"' in text
