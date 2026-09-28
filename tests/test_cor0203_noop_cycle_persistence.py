from pathlib import Path

CYCLE = Path("scripts/cor0203_production_cycle.sh")


def test_empty_cycle_exits_before_mutable_last_files_are_staged():
    text = CYCLE.read_text(encoding="utf-8-sig")
    material_check = text.index('if git diff --cached --quiet; then')
    for variable in (
        "DURABLE_DISCOVERY_LAST",
        "PREREG_LAST",
        "CROSSWALK_LAST",
        "STAGE_LAST",
        "RUNNER_LAST",
        "INTEGRITY_LAST",
        "OBSERVABILITY_LAST",
        "SETTLEMENT_QUEUE_LAST",
        "HISTORICAL_IDENTITY_LAST",
        "SETTLEMENT_SYNC_LAST",
        "HEARTBEAT",
    ):
        token = 'git add "

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
 + variable + '"'
        assert text.index(token) > material_check


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
