from pathlib import Path

ROLLING = Path(".github/workflows/tennis-world-rolling-horizon.yml")
BATCH = Path(".github/workflows/cor0203-batch-freeze.yml")
CYCLE = Path("scripts/cor0203_production_cycle.sh")


def test_hard_rolling_horizon_is_d0_d7_two_tier_every_two_hours_and_rapidapi_only():
    raw = ROLLING.read_text(encoding="utf-8")
    assert 'cron: "17 */2 * * *"' in raw
    assert "for OFFSET in 0 1 2 3 4 5 6 7" in raw
    assert 'if [ "$OFFSET" -le 2 ]; then' in raw
    assert '"shadow_scout_offsets":[3,4,5,6,7]' in raw
    assert '"d3_d7_admitted_to_holdout":False' in raw
    assert '"browser_first_required_before_holdout_admission":True' in raw
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


def test_d3_d7_shadow_scout_is_non_admitting_and_separate_from_d0_d2_production():
    raw = ROLLING.read_text(encoding="utf-8")
    production_guard = raw.index('if [ "$OFFSET" -le 2 ]; then')
    production_call = raw.index('bash scripts/cor0203_production_cycle.sh', production_guard)
    else_pos = raw.index("else", production_call)
    shadow_inventory = raw.index("python -m tools.tennis_world_inventory_rapidapi", else_pos)
    shadow_end = raw.index("fi", shadow_inventory)
    assert production_call < else_pos < shadow_inventory < shadow_end
    assert "bash scripts/cor0203_production_cycle.sh" not in raw[else_pos:shadow_end]
    assert '"admitted_to_holdout":False' in raw
    assert '"metrics_opened":False' in raw
    assert '"real_money":"BLOCKED"' in raw
