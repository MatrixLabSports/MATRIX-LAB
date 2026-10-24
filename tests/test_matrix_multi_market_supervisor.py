import json
from pathlib import Path

from app.market.matrix_market_portfolio import FOOTBALL_MARKETS, TENNIS_MARKETS
from tools.matrix_multi_market_supervisor import build


def test_supervisor_emits_every_mandated_lane_without_silent_drop():
    r=build()
    assert r["status"]=="PASS"
    assert r["football_required_lanes"]==30
    assert r["tennis_required_lanes"]==12
    assert r["total_required_lanes"]==42
    keys=[x["market_key"] for x in r["rows"]]
    assert len(keys)==len(set(keys))==42
    assert set(keys)=={x.key for x in (*FOOTBALL_MARKETS,*TENNIS_MARKETS)}


def test_supervisor_locks_explicitly_forgotten_markets():
    r=build()
    keys={x["market_key"] for x in r["rows"]}
    assert "ACES" in keys
    assert "FIRST_HALF_TOTAL_GOALS_OVER_UNDER" in keys
    assert "SECOND_HALF_TOTAL_GOALS_OVER_UNDER" in keys
    assert "TEAM_TOTAL_GOALS_HOME" in keys
    assert "TEAM_TOTAL_GOALS_AWAY" in keys


def test_every_lane_continues_collecting_even_if_not_production_ready():
    r=build()
    assert all(x["must_continue_collecting"] is True for x in r["rows"])
    assert all(
        x["operational_state"] in {"ACTIVE", "LAB"}
        or x["operational_state"].startswith("BLOCKED")
        for x in r["rows"]
    )


def test_supervisor_preserves_safety_invariants():
    r=build()
    inv=r["invariants"]
    assert inv["every_mandated_lane_emitted_each_cycle"] is True
    assert inv["no_go_does_not_stop_research_collection"] is True
    assert inv["over_2_5_not_single_market_scope"] is True
    assert inv["odds_do_not_generate_p_matrix"] is True
    assert inv["automatic_wagering"] is False
    assert inv["real_money"]=="BLOCKED"


def test_aces_is_visible_and_has_physical_source_lab():
    r=build()
    row=next(x for x in r["rows"] if x["market_key"]=="ACES")
    assert row["required"] is True
    assert row["must_continue_collecting"] is True
    assert row["operational_state"]=="LAB"
    assert row["implementation_present"] is True
    assert row["implementation_paths"]==["tools/rapidapi_tennis_serve_stats_lab.py"]
    assert "BLOCKED_TENNIS_STAT_MARKET_IMPLEMENTATION" not in row["blockers"]


def test_six_period_goal_markets_are_real_labs_not_blocked_models():
    r=build()
    required={
        "FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
        "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
        "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
        "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
        "SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
        "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
    }
    rows={x["market_key"]:x for x in r["rows"]}
    assert required.issubset(rows)
    for key in required:
        row=rows[key]
        assert row["operational_state"]=="LAB"
        assert row["implementation_present"] is True
        assert row["implementation_paths"]==["tools/api_football_period_goals_lab.py"]
        assert "BLOCKED_MODEL" not in row["blockers"]
        assert row["production_authorized"] is False


def test_three_tennis_serve_stat_markets_are_real_labs():
    r=build()
    rows={x["market_key"]:x for x in r["rows"]}
    for key in {"ACES","DOUBLE_FAULTS","BREAKS_OF_SERVE"}:
        row=rows[key]
        assert row["operational_state"]=="LAB"
        assert row["implementation_present"] is True
        assert row["implementation_paths"]==["tools/rapidapi_tennis_serve_stats_lab.py"]
        assert row["production_authorized"] is False
