import json
from pathlib import Path

from app.market.matrix_market_portfolio import (
    EXPECTED_FOOTBALL_KEYS,
    EXPECTED_TENNIS_KEYS,
    FOOTBALL_MARKETS,
    TENNIS_MARKETS,
)

MANDATE = Path("evidence/audit/MATRIX_MARKET_PORTFOLIO_PERMANENT_MANDATE_V1.json")


def test_market_portfolio_is_permanent_and_cannot_silently_narrow():
    m=json.loads(MANDATE.read_text(encoding="utf-8"))
    assert m["status"]=="PERMANENT_ACTIVE"
    assert m["change_control"]=="USER_EXPLICIT_REPLACE_MODIFY_SUSPEND_REVOKE_ONLY"
    assert set(m["football_markets"])==set(EXPECTED_FOOTBALL_KEYS)
    assert set(m["tennis_markets"])==set(EXPECTED_TENNIS_KEYS)


def test_tennis_aces_is_mandatory_and_cannot_be_forgotten():
    m=json.loads(MANDATE.read_text(encoding="utf-8"))
    assert "ACES" in EXPECTED_TENNIS_KEYS
    assert "ACES" in m["tennis_markets"]
    assert m["explicit_user_correction_2026_10_24"]["aces_required"] is True


def test_over25_is_not_allowed_to_become_single_market_scope():
    m=json.loads(MANDATE.read_text(encoding="utf-8"))
    assert m["invariants"]["over_2_5_is_not_the_only_market"] is True
    assert len(FOOTBALL_MARKETS) >= 20
    assert len(TENNIS_MARKETS) >= 12


def test_no_go_does_not_stop_research_collection():
    m=json.loads(MANDATE.read_text(encoding="utf-8"))
    assert m["invariants"]["no_go_for_production_does_not_mean_stop_collecting_research"] is True
    assert m["invariants"]["laboratory_collection_runs_in_parallel"] is True


def test_subscription_expiry_urgency_is_physically_coded():
    m=json.loads(MANDATE.read_text(encoding="utf-8"))
    u=m["subscription_urgency"]
    assert u["paid_through_bogota_date"]=="2026-10-28"
    assert u["mandate"]=="MAXIMIZE_PHYSICAL_EVIDENCE_BEFORE_EXPIRY"


def test_safety_invariants_remain_blocked():
    m=json.loads(MANDATE.read_text(encoding="utf-8"))
    assert m["invariants"]["odds_do_not_generate_p_matrix"] is True
    assert m["invariants"]["automatic_wagering"] is False
    assert m["invariants"]["real_money"]=="BLOCKED"



def test_first_and_second_half_goal_markets_are_mandatory():
    required = {
        "TEAM_TOTAL_GOALS_HOME",
        "TEAM_TOTAL_GOALS_AWAY",
        "FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
        "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
        "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
        "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
        "SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
        "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
    }
    assert required.issubset(EXPECTED_FOOTBALL_KEYS)
    m=json.loads(MANDATE.read_text(encoding="utf-8"))
    assert required.issubset(set(m["football_markets"]))
    corr=m["explicit_user_correction_2026_10_24_goals_by_period"]
    assert corr["first_half_goals_required"] is True
    assert corr["second_half_goals_required"] is True
    assert corr["team_total_goals_full_match_required"] is True
    assert corr["team_total_goals_by_half_required"] is True
