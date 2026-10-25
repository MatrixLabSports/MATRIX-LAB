from tools.matrix_42_lane_300_to_600_accelerator import build


def test_accelerator_selects_highest_count_cohort_without_silent_drop():
    r=build()
    assert r["status"]=="PASS"
    sel=r["selected_cohort"]
    assert set(sel["lanes"])=={
        "FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
        "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
        "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
        "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
        "SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
        "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
    }
    assert sel["prospective_unique_count"]==592
    assert sel["remaining_to_600"]==8
    assert r["portfolio_visibility"]["all_42_remain_supervised"] is True
    assert r["portfolio_visibility"]["selected_cohort_does_not_suspend_other_lanes"] is True


def test_accelerator_orders_remaining_300_to_600_cohorts():
    r=build()
    counts=[x["prospective_unique_count"] for x in r["ordered_cohorts"]]
    assert counts==sorted(counts,reverse=True)
    assert counts[:2]==[592,585]


def test_accelerator_preserves_safety_and_no_backfill():
    r=build()
    p=r["selection_policy"]
    assert p["model_refit"] is False
    assert p["parameter_search"] is False
    assert p["historical_backfill"] is False
    assert p["post_start_backfill"] is False
    assert p["outcomes_read_to_create_freeze"] is False
    assert p["odds_used_to_generate_probability"] is False
    assert p["missing_not_zero"] is True
    assert p["silent_imputation"] is False
    assert p["automatic_wagering"] is False
    assert p["real_money"]=="BLOCKED"


def test_accelerator_keeps_price_gap_visible_for_period_goals():
    r=build()
    cohort=next(x for x in r["ordered_cohorts"] if x["prospective_unique_count"]==592)
    assert set(cohort["price_family_not_observed"])=={
        "FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
        "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
        "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
        "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
        "SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
        "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
    }


def test_gate600_lab_lanes_are_removed_from_acceleration_and_listed_for_audit():
    r=build()
    assert set(r["post600_audit_queue"]["lanes"])=={
        "MATCH_RESULT_1X2",
        "DOUBLE_CHANCE_1X",
        "DOUBLE_CHANCE_X2",
        "DOUBLE_CHANCE_12",
    }
    assert r["post600_audit_queue"]["automatic_promotion"] is False
    assert all(x>=600 for x in r["post600_audit_queue"]["counts"])
    accelerated={lane for cohort in r["ordered_cohorts"] for lane in cohort["lanes"]}
    assert accelerated.isdisjoint(set(r["post600_audit_queue"]["lanes"]))
