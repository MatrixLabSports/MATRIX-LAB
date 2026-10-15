from pathlib import Path


def test_production_cycle_has_no_active_api_tennis_dependency():
    text=Path("scripts/cor0203_production_cycle.sh").read_text(encoding="utf-8")
    assert "TWO_PAID_TENNIS_KEYS_REQUIRED" not in text
    assert "DUAL_PAID_TENNIS_MODE_REQUIRED" not in text
    assert "python -m tools.cor0203_api_tennis_discovery" not in text
    assert "python -m tools.cor0203_eight_day_dual_discovery" not in text
    assert "python -m tools.cor0203_dual_source_readiness" not in text
    assert "python -m tools.cor0203_dual_provider_reconcile" not in text
    assert "python -m tools.cor0203_api_tennis_rank_bridge" not in text
    assert "rapidapi_primary_open_reconciliation" in text
    assert "RAPIDAPI_TENNIS_KEY_REQUIRED" in text
