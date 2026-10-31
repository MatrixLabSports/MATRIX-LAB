import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "matrix_paid_api_final_day_elite_closure.py"
spec = importlib.util.spec_from_file_location("paid_api_close", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_final_paid_api_closure_is_physical_and_fail_closed():
    r = mod.build_report()
    assert r["governance"]["date_bogota"] == "2026-10-28"
    assert r["governance"]["real_money"] == "BLOCKED"
    assert r["governance"]["automatic_wagering"] is False
    assert r["governance"]["paid_api_renewal_authorized"] is False
    assert r["api_football"]["provider_error_classification"] == "DAILY_REQUEST_LIMIT_REACHED"
    assert r["api_football"]["adjudication"] == "EXTERNAL_DAILY_QUOTA_BLOCK_FAIL_CLOSED"
    assert r["rapidapi_tennis"]["paid_through"] == "2026-10-28"
    assert r["rapidapi_tennis"]["network_calls"] == 2
    assert r["rapidapi_tennis"]["unique_match_count"] == 287
    assert r["rapidapi_tennis"]["provider_inventory_complete"] is True
    assert r["rapidapi_tennis"]["automatic_model_feed"] is False
    assert r["rapidapi_tennis"]["canonical_row_count"] == 306
    assert r["rapidapi_tennis"]["cor0203_preregister_candidate_count"] == 1
    assert r["oos_football"]["current"] == 796
    assert r["oos_football"]["target"] == 1000
    assert r["oos_football"]["metrics_opened"] is False
    assert r["clv"]["closing_odds_count"] == 11
    assert r["clv"]["metrics_opened"] is False
    assert r["signal_authorized"] == ["OVER_2_5"]
