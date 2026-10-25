import json
from pathlib import Path

from app.market.matrix_market_portfolio import ALL_MARKETS
from tools.matrix_42_lane_action_board import build


def test_action_board_has_exactly_all_42_lanes_once():
    r=build()
    assert r["status"]=="PASS"
    assert r["counts"]["total_lanes"]==42
    assert r["counts"]["football_lanes"]==30
    assert r["counts"]["tennis_lanes"]==12
    keys=[x["market_lane"] for x in r["rows"]]
    assert len(keys)==len(set(keys))==42
    assert set(keys)=={m.key for m in ALL_MARKETS}
    assert r["invariants"]["all_42_present_exactly_once"] is True


def test_every_lane_has_physical_next_action_and_continues_collecting():
    r=build()
    assert all(x["next_required_action"] for x in r["rows"])
    assert all(x["must_continue_collecting"] is True for x in r["rows"])
    assert r["invariants"]["every_lane_has_next_action"] is True
    assert r["invariants"]["every_lane_must_continue_collecting"] is True


def test_action_board_preserves_safety_contract():
    r=build()
    inv=r["invariants"]
    assert inv["missing_not_zero"] is True
    assert inv["no_silent_imputation"] is True
    assert inv["odds_do_not_generate_p_matrix"] is True
    assert inv["automatic_wagering"] is False
    assert inv["real_money"]=="BLOCKED"


def test_gate600_lab_lanes_leave_acceleration_queue_and_require_audit():
    r=build()
    rows={x["market_lane"]:x for x in r["rows"]}
    for key in {
        "MATCH_RESULT_1X2",
        "DOUBLE_CHANCE_1X",
        "DOUBLE_CHANCE_X2",
        "DOUBLE_CHANCE_12",
    }:
        assert rows[key]["prospective_unique_count"]>=600
        assert rows[key]["priority"]=="P0_GATE600_REACHED_AWAIT_AUDIT"
        assert rows[key]["next_required_action"]=="RUN_GATE600_CALIBRATION_STABILITY_AUDIT_NO_AUTO_PROMOTION"


def test_sub600_advanced_lanes_remain_in_300_to_600_queue():
    r=build()
    rows={x["market_lane"]:x for x in r["rows"]}
    for key in {
        "TEAM_TOTAL_GOALS_HOME",
        "TEAM_TOTAL_GOALS_AWAY",
        "FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
        "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
        "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
        "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
        "SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
        "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
    }:
        assert 300<=rows[key]["prospective_unique_count"]<600
        assert rows[key]["priority"]=="P1_ADVANCE_300_TO_600"


def test_zero_lanes_are_never_silently_marked_complete():
    r=build()
    zero=[x for x in r["rows"] if x["prospective_unique_count"]==0]
    assert zero
    assert all(x["priority"]=="P4_OPEN_VALID_PROSPECTIVE_FREEZE" for x in zero)
    assert all(x["remaining_to_600"]==600 for x in zero)


def test_active_lane_post_gate_is_maintained_not_demoted_to_audit_queue():
    r=build()
    rows={x["market_lane"]:x for x in r["rows"]}
    total=rows["TOTAL_GOALS_OVER_UNDER"]
    assert total["operational_state"]=="ACTIVE"
    assert total["prospective_unique_count"]>=600
    assert total["priority"]=="P0_MAINTAIN_ACTIVE_POST_GATE"
    assert total["next_required_action"]=="KEEP_ACTIVE_PAPER_MONITORING_AND_CONTINUE_POST_GATE_VALIDATION"


def test_gate600_never_auto_promotes():
    r=build()
    assert r["invariants"]["gate600_never_auto_promotes"] is True
    assert r["invariants"]["lab_lane_at_600_routes_to_audit"] is True
