import json
from pathlib import Path
import tools.telegram_market_signal_eligibility as m


def test_market_signal_eligibility_is_fail_closed_and_truthful(tmp_path, monkeypatch):
    root=Path(".")
    out=m.build()
    assert out["status"]=="PASS"
    by={x["market_key"]:x for x in out["rows"]}
    assert by["OVER_2_5"]["telegram_signal_state"]=="SIGNAL_ACTIVE"
    for key in ["MATCH_RESULT_1X2","UNDER_2_5","DOUBLE_CHANCE_1X","DOUBLE_CHANCE_X2"]:
        assert by[key]["telegram_signal_state"]=="PROMOTION_REQUIRED"
        assert by[key]["production_authorized"] is False
        assert by[key]["settlement_evidence"] >= 3900
    assert by["BTTS"]["telegram_signal_state"]=="BLOCKED"
    assert by["DOUBLE_CHANCE_12"]["telegram_signal_state"]=="BLOCKED"
    for key in m.PERIOD_KEYS:
        assert by[key]["telegram_signal_state"]=="BLOCKED_LAB"
        assert by[key]["production_authorized"] is False
    assert out["governance"]["calibration_does_not_equal_signal_authorization"] is True
    assert out["governance"]["automatic_wagering"] is False
    assert out["governance"]["real_money"]=="BLOCKED"
