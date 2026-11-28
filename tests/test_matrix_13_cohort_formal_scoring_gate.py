import pytest
from tools.matrix_13_cohort_formal_scoring_gate import assess


def inputs(n=600):
    keys=["MATCH_RESULT_1X2","DOUBLE_CHANCE_1X","DOUBLE_CHANCE_X2",
          "DOUBLE_CHANCE_12","TOTAL_GOALS_OVER_UNDER","TEAM_TOTAL_GOALS_HOME",
          "TEAM_TOTAL_GOALS_AWAY","FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
          "SECOND_HALF_TOTAL_GOALS_OVER_UNDER","FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
          "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY","SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
          "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY"]
    report={"summary":{"markets_targeted":13},
            "lanes":[{"market_key":k,"exact_cohort_final_verified":n if k=="TOTAL_GOALS_OVER_UNDER" else 0} for k in keys]}
    frozen={"rows":[]};portfolio=[];settled=[]
    for i in range(n):
        fid=str(1000+i)
        kickoff="2026-10-28T20:00:00+00:00"
        frozen["rows"].append({"fixture_id":fid,"kickoff_utc":kickoff,
            "frozen_research_probabilities":{"over_2_5":.8,"1x2":{"H":.6,"D":.2,"A":.2}},
            "poisson_reference":{"over_2_5":.5,"1x2":{"H":.4,"D":.3,"A":.3}}})
        portfolio.append({"fixture_id":fid,"market_lane":"TOTAL_GOALS_OVER_UNDER","prospective_admitted":True})
        settled.append({"fixture_id":fid,"kickoff_utc":kickoff,"terminal_status":"FT",
                        "fulltime_home_goals":2,"fulltime_away_goals":1})
    return report,frozen,portfolio,settled


def test_real_threshold_requires_600_and_never_promotes():
    result=assess(*inputs(599))
    row=next(x for x in result["lanes"] if x["market_key"]=="TOTAL_GOALS_OVER_UNDER")
    assert row["verdict"]=="HOLD_BELOW_600_PROSPECTIVE_EXACT_FT"
    assert row["remaining"]==1
    assert result["summary"]["newly_promoted"]==0
    r=assess(*inputs(600))
    target=next(x for x in r["lanes"] if x["market_key"]=="TOTAL_GOALS_OVER_UNDER")
    assert target["verdict"]=="PASS_SCORING_COMPARISON_NO_PROMOTION"
    assert target["proper_scoring"]["delta_brier_challenger_minus_poisson"]<0
    assert target["proper_scoring"]["delta_log_loss_challenger_minus_poisson"]<0
    assert target["promoted"] is False
    assert r["summary"]["formal_core_scoring_comparisons_completed"]==1
    assert r["protections"]["real_money"]=="BLOCKED"


def test_duplicate_or_nonfinal_never_enters_600_sample():
    data=list(inputs(600))
    data[3].append(data[3][0].copy())
    with pytest.raises(ValueError,match="SETTLEMENT_CONFLICT_OR_NONFINAL"):
        assess(*data)
    data=list(inputs(600))
    data[3][0]["terminal_status"]="AET"
    with pytest.raises(ValueError,match="SETTLEMENT_CONFLICT_OR_NONFINAL"):
        assess(*data)


def test_pre_frozen_reference_incomplete_holds_even_above_600():
    data=list(inputs(600))
    data[1]["rows"][0].pop("poisson_reference")
    r=assess(*data)
    market=next(x for x in r["lanes"] if x["market_key"]=="TOTAL_GOALS_OVER_UNDER")
    assert market["verdict"]=="HOLD_FROZEN_REFERENCE_COHORT_NOT_EQUAL_TO_SETTLED_COUNT"
    assert market["reference_evaluable_count"]==599
