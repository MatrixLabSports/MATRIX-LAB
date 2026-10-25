from tools.matrix_42_lane_300_to_600_accelerator import build


def test_accelerator_selects_highest_300_to_599_cohort():
    r=build()
    assert r["status"]=="PASS"
    selected=r["selected_cohort"]
    assert selected["prospective_unique_count"]==393
    assert selected["remaining_to_600"]==207
    assert selected["lanes"]==[
        "MATCH_RESULT_1X2",
        "DOUBLE_CHANCE_1X",
        "DOUBLE_CHANCE_X2",
        "DOUBLE_CHANCE_12",
    ]


def test_accelerator_orders_next_cohorts_without_hiding_them():
    r=build()
    counts=[x["prospective_unique_count"] for x in r["ordered_cohorts"]]
    assert counts==sorted(counts,reverse=True)
    assert counts[:3]==[393,384,377]
    assert r["portfolio_visibility"]["all_42_remain_supervised"] is True
    assert r["portfolio_visibility"]["selected_cohort_does_not_suspend_other_lanes"] is True


def test_accelerator_never_refits_or_backfills():
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


def test_period_goal_cohort_keeps_price_family_work_visible():
    r=build()
    period=next(x for x in r["ordered_cohorts"] if x["prospective_unique_count"]==384)
    assert len(period["lanes"])==6
    assert set(period["price_family_not_observed"])==set(period["lanes"])
