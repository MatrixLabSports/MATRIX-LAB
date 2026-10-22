from pathlib import Path

ROLLING = Path(".github/workflows/tennis-world-rolling-horizon.yml")
BATCH = Path(".github/workflows/cor0203-batch-freeze.yml")
CYCLE = Path("scripts/cor0203_production_cycle.sh")


def test_hard_rolling_horizon_is_d0_d1_d2_every_two_hours_and_rapidapi_only():
    raw = ROLLING.read_text(encoding="utf-8")
    assert 'cron: "17 */2 * * *"' in raw
    assert "for OFFSET in 0 1 2" in raw
    assert "RAPIDAPI_TENNIS_KEY" in raw
    assert "secrets.API_TENNIS_KEY" not in raw
    assert 'MATRIX_COR0203_STATS_RICH_PROBE: "0"' in raw


def test_stats_rich_probe_is_diagnostic_opt_in_not_routine():
    raw = CYCLE.read_text(encoding="utf-8")
    assert 'MATRIX_COR0203_STATS_RICH_PROBE:-0' in raw
    assert 'COR0203_STATS_RICH_PROBE_SKIPPED_ZERO_HIT_DIAGNOSTIC_ONLY' in raw
    assert 'if [[ "${MATRIX_COR0203_STATS_RICH_PROBE:-0}" == "1" ]]' in raw


def test_holdout_protections_remain_explicit():
    raw = CYCLE.read_text(encoding="utf-8")
    assert 'assert uniqueness["metrics_opened"] is False' in raw
    assert 'assert uniqueness["outcomes_read"] == 0' in raw
    assert 'assert source_readiness["required_paid_providers"] == ["rapidapi_tennis"]' in raw
    assert 'assert source_readiness["retired_paid_sources"]["api_tennis"]["required"] is False' in raw


def test_only_rolling_horizon_owns_routine_two_hour_hard_schedule():
    rolling = ROLLING.read_text(encoding="utf-8")
    batch = BATCH.read_text(encoding="utf-8")
    assert 'cron: "17 */2 * * *"' in rolling
    assert "cron: '17 */2 * * *'" not in batch
    assert "workflow_dispatch:" in batch
