import json
from pathlib import Path

from tools.matrix_42_lane_300_to_600_accelerator import BOARD, build


def _expected_p1():
    board=json.loads(Path(BOARD).read_text(encoding="utf-8"))
    p1=[
        x for x in board["rows"]
        if x["priority"]=="P1_ADVANCE_300_TO_600"
        and 300 <= int(x["prospective_unique_count"]) < 600
    ]
    max_count=max(int(x["prospective_unique_count"]) for x in p1) if p1 else None
    selected=sorted(
        [x for x in p1 if int(x["prospective_unique_count"])==max_count],
        key=lambda x:int(x["portfolio_index"]),
    )
    return p1,max_count,selected


def test_accelerator_selects_highest_300_to_599_cohort():
    r=build()
    p1,max_count,selected=_expected_p1()
    assert r["status"]=="PASS"
    assert r["selected_cohort"]["prospective_unique_count"]==max_count
    assert r["selected_cohort"]["lanes"]==[x["market_lane"] for x in selected]
    if max_count is not None:
        assert r["selected_cohort"]["remaining_to_600"]==600-max_count


def test_accelerator_orders_all_current_cohorts_without_hiding_them():
    r=build()
    p1,_,_=_expected_p1()
    expected_counts=sorted({int(x["prospective_unique_count"]) for x in p1},reverse=True)
    actual=[x["prospective_unique_count"] for x in r["ordered_cohorts"]]
    assert actual==expected_counts
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


def test_price_family_work_remains_visible_for_any_selected_cohort():
    r=build()
    board=json.loads(Path(BOARD).read_text(encoding="utf-8"))
    by_lane={x["market_lane"]:x for x in board["rows"]}
    for cohort in r["ordered_cohorts"]:
        expected={
            lane for lane in cohort["lanes"]
            if by_lane[lane]["price_state"]=="PRICE_FAMILY_NOT_OBSERVED"
        }
        assert set(cohort["price_family_not_observed"])==expected
