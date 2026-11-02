from copy import deepcopy

import pytest

from tools.matrix_five_market_elite_governance_decision import adjudicate,FIVE


def sample():
    markets={
        "DOUBLE_CHANCE_1X":{
            "settled_fixtures":604,"candidate_promoted":False,
            "existing_frozen_parameters_modified":False,
            "chronological_split":{"no_train_holdout_fixture_overlap":True},
            "proper_scores":{
                "holdout_original":{"brier":.2113,"log_loss":.6155},
                "holdout_poisson":{"brier":.2074,"log_loss":.6040},
                "holdout_intercept_candidate":{"brier":.2092,"log_loss":.6103}},
        },
        "TOTAL_GOALS_OVER_UNDER":{
            "settled_fixtures":604,"candidate_promoted":False,
            "existing_frozen_parameters_modified":False,
            "chronological_split":{"no_train_holdout_fixture_overlap":True},
            "proper_scores":{
                "holdout_original":{"brier":.2266,"log_loss":.6453},
                "holdout_poisson":{"brier":.2268,"log_loss":.6447},
                "holdout_intercept_candidate":{"brier":.2270,"log_loss":.6457}},
        },
    }
    stability={
        "status":"RESEARCH_EXPERIMENT_DIAGNOSTIC_NO_PROMOTIONS",
        "invariants":{"real_money":"BLOCKED"},
        "market_results":markets,
        "existing_governance":{"double_chance_1x_oos_remaining":204,
                               "double_chance_1x_oos_metrics_opened":False}
    }
    verdict={
        "summary":{"gate600_final_count":5},
        "lanes":[{"market_key":key,"exact_verified_ft_count":604,
                  "verdict":"PASS_SCORING_COMPARISON_NO_PROMOTION"} for key in FIVE],
    }
    supervisor={"rows":[{
        "market_key":key,
        "operational_state":"ACTIVE" if key=="TOTAL_GOALS_OVER_UNDER" else "LAB",
        "production_authorized":key=="TOTAL_GOALS_OVER_UNDER",
    } for key in FIVE]}
    one_x={"market":"DOUBLE_CHANCE_1X","promotion_allowed":False,
           "blockers":["OOS_4001_5000_NOT_COMPLETE","NO_EXPLICIT_SIGNAL_P_MATRIX"]}
    over={"promotion_status":"PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY"}
    return stability,verdict,supervisor,one_x,over


def test_no_new_telegram_market_is_granted_from_604_finals():
    result=adjudicate(*sample())
    assert result["status"]=="PASS_FAIL_CLOSED_ELITE_ADJUDICATION"
    assert result["summary"]["markets_with_at_least_600_authentic_ft"]==5
    assert result["summary"]["historically_governed_over25_scope_maintained"]==1
    assert result["summary"]["new_market_promotions"]==0
    assert result["summary"]["markets_blocked_for_new_promotion"]==4
    assert len(result["markets"])==5
    assert not any(m["newly_authorized_for_telegram"] for m in result["markets"])
    assert result["protections"]["real_money"]=="BLOCKED"
    one=next(x for x in result["markets"] if x["market_key"]=="DOUBLE_CHANCE_1X")
    assert "NO_GO_NEW_1X_PROMOTION" in one["governance_decision"]
    assert one["exact_prospectively_frozen_final_count"]==604
    assert result["diagnostic_findings"]["one_x_extra_gov_oos_remaining"]==204


def test_prior_over25_p_matrix_scope_cannot_be_silently_replaced():
    data=list(sample())
    data[4]["promotion_status"]="UNAPPROVED"
    with pytest.raises(ValueError,match="PREVIOUS_OVER25_PRODUCTION_AUTHORIZATION_NOT_CERTIFIED"):
        adjudicate(*data)


def test_supervisor_1x_lab_state_must_remain_unpromoted():
    data=list(sample())
    one=next(x for x in data[2]["rows"] if x["market_key"]=="DOUBLE_CHANCE_1X")
    one["production_authorized"]=True
    with pytest.raises(ValueError,match="SUPERVISOR_PRODUCTION_SCOPE_CHANGED"):
        adjudicate(*data)


def test_recalibration_already_promoted_is_rejected():
    data=list(sample())
    data[0]["market_results"]["DOUBLE_CHANCE_1X"]["candidate_promoted"]=True
    with pytest.raises(ValueError,match="INVALID_TEMPORAL_OR_FROZEN_CANDIDATE_PROOF"):
        adjudicate(*data)


def test_missing_second_holdout_or_604_row_rejected():
    data=list(sample())
    data[0]["market_results"].pop("DOUBLE_CHANCE_1X")
    with pytest.raises(ValueError,match="MISSING_TWO_MARKET_STABILITY_PROOF"):
        adjudicate(*data)
    data=list(sample())
    data[1]["lanes"][0]["exact_verified_ft_count"]=603
    with pytest.raises(ValueError,match="604_VERIFIED_FINAL_COHORT_NOT_UNCHANGED"):
        adjudicate(*data)


def test_decisions_never_modify_inputs():
    args=sample()
    original=deepcopy(args)
    adjudicate(*args)
    assert args==original
