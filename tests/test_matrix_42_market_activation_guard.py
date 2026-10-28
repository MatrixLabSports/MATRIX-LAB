import json
from pathlib import Path
from tools.matrix_42_market_activation_guard import (
    CANONICAL, FOOTBALL, TENNIS, build, telegram_market_allowed
)

def test_exact_42_contract():
    assert len(CANONICAL)==42
    assert len(set(CANONICAL))==42
    assert len(FOOTBALL)==30
    assert len(TENNIS)==12
    assert "ACES" in TENNIS
    assert "FIRST_HALF_TOTAL_GOALS_OVER_UNDER" in FOOTBALL
    assert "SECOND_HALF_TOTAL_GOALS_OVER_UNDER" in FOOTBALL

def test_current_state_is_fully_represented():
    out=build()
    assert len(out["lanes"])==42
    assert out["governance"]["real_money"]=="BLOCKED"
    assert out["governance"]["automatic_wagering"] is False
    assert out["governance"]["cadence_minutes"]==15

def test_telegram_does_not_auto_promote_600_lanes():
    out=build()
    by={x["market_key"]:x for x in out["lanes"]}
    assert by["DOUBLE_CHANCE_1X"]["gate_600_reached"] is True
    assert by["DOUBLE_CHANCE_1X"]["telegram_market_ready"] is False
    assert by["DOUBLE_CHANCE_12"]["telegram_market_ready"] is False

def test_only_governed_over25_is_allowed_from_goal_family():
    assert telegram_market_allowed("TOTAL_GOALS_OVER_UNDER","OVER_2_5",0.65,1.80,0.08)
    assert not telegram_market_allowed("TOTAL_GOALS_OVER_UNDER","UNDER_2_5",0.65,1.80,0.08)
    assert not telegram_market_allowed("TOTAL_GOALS_OVER_UNDER","OVER_2_5",0.59,1.80,0.08)
    assert not telegram_market_allowed("TOTAL_GOALS_OVER_UNDER","OVER_2_5",0.65,1.50,0.08)
    assert not telegram_market_allowed("TOTAL_GOALS_OVER_UNDER","OVER_2_5",0.65,1.80,0.04)
