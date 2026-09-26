from pathlib import Path

CYCLE = Path("scripts/cor0203_production_cycle.sh")


def test_empty_cycle_exits_before_mutable_last_files_are_staged():
    text = CYCLE.read_text(encoding="utf-8-sig")
    material_check = text.index('if git diff --cached --quiet; then')
    last_stage = text.index('git add "$RUNNER_LAST"')
    assert material_check < last_stage


def test_append_only_artifacts_define_material_cycle():
    text = CYCLE.read_text(encoding="utf-8-sig")
    material_check = text.index('if git diff --cached --quiet; then')
    for token in (
        "MATRIX_COR0203_PREFEATURE_REGISTRY_R*.json",
        "MATRIX_COR0203_IDENTITY_CROSSWALK_R*.json",
        "MATRIX_COR0203_BATCH_PREFLIGHT_R*.json",
        "MATRIX_COR0203_HOLDOUT_BATCH_R*.json",
    ):
        assert text.index(token) < material_check
