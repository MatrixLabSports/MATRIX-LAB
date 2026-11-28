import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "matrix_42_market_elite_calibration_closure.py"
spec = importlib.util.spec_from_file_location("elite_cal", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_elite_calibration_closure_fail_closed_and_no_false_promotion():
    report = mod.build_report()
    assert report["portfolio"]["total_lanes"] == 42
    assert report["portfolio"]["football_lanes"] == 30
    assert report["portfolio"]["tennis_lanes"] == 12
    assert report["governance"]["real_money"] == "BLOCKED"
    assert report["governance"]["automatic_wagering"] is False
    assert report["governance"]["parameter_refit"] is False
    assert report["governance"]["parameter_search"] is False
    assert report["adjudication"]["signal_authorized_markets"] == ["OVER_2_5"]
    assert report["checkpoint_4000"]["over_2_5"]["promotion_authorized"] is True
    for key in ("1x2", "under_2_5", "double_chance_1x", "double_chance_x2"):
        assert report["checkpoint_4000"][key]["eligible_rows"] == 4000
        assert report["checkpoint_4000"][key]["promotion_authorized"] is False
    assert report["period_goals_walk_forward"]["observations"] == 3177
    assert report["period_goals_walk_forward"]["production_authorized"] is False
    assert report["double_chance_12"]["status"] == "NOT_PROMOTED_DIAGNOSTIC_ONLY"
    assert report["oos"]["metrics_opened"] is False
