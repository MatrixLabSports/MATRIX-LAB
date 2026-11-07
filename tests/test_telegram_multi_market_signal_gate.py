from tools.telegram_multi_market_signal_gate import build

def test_multi_market_gate_is_fail_closed_and_truthful():
    out=build()
    assert out["status"]=="PASS"
    rows={x["market"]:x for x in out["markets"]}
    assert rows["OVER_2_5"]["signal_status"]=="SIGNAL_AUTHORIZED"
    assert rows["OVER_2_5"]["quote_extraction_path_present"] is True
    assert rows["OVER_2_5"]["telegram_signal_engine_present"] is True
    for key in ["UNDER_2_5","1X2","DOUBLE_CHANCE_1X","DOUBLE_CHANCE_X2"]:
        assert rows[key]["signal_status"]=="RESEARCH_ONLY"
        assert rows[key]["explicit_signal_promotion"] is False
    assert rows["BTTS"]["signal_status"]=="NO_GO"
    assert rows["DOUBLE_CHANCE_12"]["signal_status"]=="NO_GO"
    for key in ["CORNERS","TEAM_SHOTS_ON_TARGET","TEAM_GOALKEEPER_SAVES","TEAM_YELLOW_CARDS"]:
        assert rows[key]["signal_status"]=="NO_GO"
    for key in ["FIRST_HALF_TOTAL_GOALS_OVER_UNDER","SECOND_HALF_TOTAL_GOALS_OVER_UNDER"]:
        assert rows[key]["signal_status"]=="LAB_ONLY"
    assert out["policy"]["silent_market_omission_forbidden"] is True
    assert out["policy"]["automatic_wagering"] is False
    assert out["policy"]["real_money"]=="BLOCKED"
