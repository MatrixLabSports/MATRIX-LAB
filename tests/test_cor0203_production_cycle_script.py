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


def test_cycle_requires_primary_rapidapi_mode_and_never_auto_switches():
    text = _text()
    assert 'TENNIS_MODE="${MATRIX_TENNIS_MODE:-rapidapi_primary_open_reconciliation}"' in text
    assert 'if [[ "$TENNIS_MODE" != "rapidapi_primary_open_reconciliation" ]]' in text
    assert "RAPIDAPI_PRIMARY_OPEN_RECONCILIATION_MODE_REQUIRED" in text
    assert "RAPIDAPI_TENNIS_KEY_REQUIRED" in text
    assert "python -m tools.cor0203_rapidapi_durable_discovery" in text
    assert "python -m tools.cor0203_eight_day_rapidapi_discovery" in text
    assert "python -m tools.cor0203_primary_source_readiness" in text
    assert "python -m tools.cor0203_api_tennis_discovery" not in text
    assert "python -m tools.cor0203_dual_provider_reconcile" not in text
    assert "automatic_provider_switch" not in text


def test_primary_paid_discovery_uses_governed_four_day_seed_then_eight_day_horizon():
    text = _text()
    rapid_start = text.index("python -m tools.cor0203_rapidapi_durable_discovery")
    horizon_start = text.index("python -m tools.cor0203_eight_day_rapidapi_discovery")
    readiness_start = text.index("python -m tools.cor0203_primary_source_readiness")
    rapid_block = text[rapid_start:horizon_start]
    assert "--days 4" in rapid_block
    assert rapid_start < horizon_start < readiness_start


def test_cycle_runs_identity_restage_delta_before_staging():
    script = Path("scripts/cor0203_production_cycle.sh").read_text(encoding="utf-8")
    first_crosswalk = script.index("python -m tools.cor0203_build_identity_crosswalk")
    delta = script.index("python -m tools.cor0203_identity_restage_delta")
    second_crosswalk = script.index("python -m tools.cor0203_build_identity_crosswalk", first_crosswalk + 1)
    stage = script.index("python -m tools.cor0203_stage_from_registry")
    assert first_crosswalk < delta < second_crosswalk < stage
    assert "MATRIX_COR0203_IDENTITY_RESTAGE_DELTA_LAST.json" in script
