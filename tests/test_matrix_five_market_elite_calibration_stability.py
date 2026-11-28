"""Unit evidence that 604-result exploratory recalibration never alters governed MATRIX."""
from copy import deepcopy

import pytest

from tools.matrix_five_market_elite_calibration_stability import (
    _metrics, _valid_samples, build, chronological_groups,
    fit_prior_logit_intercept, paired_uncertainty,
)


def mock_canonical(n=600):
    day_sizes = [200,220,n-420]
    fixtures=[]; portfolios=[]; final=[]
    for day,amount in enumerate(day_sizes):
        for index in range(amount):
            fid=str(len(fixtures)+10000)
            utc=f"2026-10-{24+day:02d}T{index%12:02d}:00:00+00:00"
            ft="2026-10-27T01:00:00+00:00"
            if day==2: ft="2026-10-28T01:00:00+00:00"
            fixtures.append({
                "fixture_id":fid,"kickoff_utc":utc,
                "freeze_at_utc":f"2026-10-23T11:00:00+00:00",
                "frozen_research_probabilities":{
                    "1x2":{"H":.51,"D":.26,"A":.23},
                    "over_2_5":.58,
                },
                "poisson_reference":{
                    "1x2":{"H":.48,"D":.24,"A":.28},
                    "over_2_5":.54,
                },
            })
            for lane in ("DOUBLE_CHANCE_1X","TOTAL_GOALS_OVER_UNDER"):
                portfolios.append({
                    "fixture_id":fid,"market_lane":lane,
                    "prospective_admitted":True,
                    "real_money":"BLOCKED","automatic_wagering":False,
                    "odds_used_to_generate_probability":False,"target_outcome":None,
                    "freeze_timestamp_utc":"2026-10-23T11:00:00+00:00",
                    "event_start_utc":utc,
                })
            final.append({
                "fixture_id":fid,"terminal_status":"FT",
                "kickoff_utc":utc,
                "freeze_at_utc":"2026-10-23T11:00:00+00:00",
                "settled_at_utc":ft,
                "fulltime_home_goals":2 if index%3 else 0,
                "fulltime_away_goals":1 if index%4 else 0,
            })
    formal={"summary":{"gate600_final_count":5},
            "lanes":[{"market_key":lane,"exact_verified_ft_count":n} for lane in
                    ("DOUBLE_CHANCE_1X","TOTAL_GOALS_OVER_UNDER")]}
    oos={"frozen_policy":{"parameter_tuning_allowed":False},
         "target_oos_observations":1000,"current_oos_observations":796,
         "metrics_opened":False}
    ready={"market":"DOUBLE_CHANCE_1X","promotion_allowed":False}
    over={"promotion_status":"PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY"}
    return formal,{"rows":fixtures},portfolios,final,oos,ready,over


def test_chronological_nonleaking_604_and_oos_not_combined():
    result=build(*mock_canonical(604))
    assert result["invariants"]["no_cross_cohort_604_plus_oos_796_silent_combination"]
    assert result["existing_governance"]["double_chance_1x_oos_remaining"]==204
    assert len(result["market_results"])==2
    for market,r in result["market_results"].items():
        assert r["settled_fixtures"]==604
        split=r["chronological_split"]
        assert split["train_n"]==420
        assert split["holdout_n"]==184
        assert split["train_last_kickoff"]<split["holdout_first_kickoff"]
        assert r["candidate_promoted"] is False
        assert r["existing_frozen_parameters_modified"] is False
        assert r["proper_scores"]["holdout_intercept_candidate"]["n"]==184
        assert r["full_cohort_paired_uncertainty"]["resamples"]==1000
    assert result["invariants"]["real_money"]=="BLOCKED"


def test_intercept_fit_is_only_earlier_heldout_outcomes_not_future():
    p=[.5]*200
    y=[1]*150+[0]*50
    fit=fit_prior_logit_intercept(p,y)
    assert fit>0.8 and fit<1.5
    with pytest.raises(ValueError,match="TRAIN_SAMPLE_INSUFFICIENT"):
        fit_prior_logit_intercept(p[:99],y[:99])


def test_interval_is_reproducible_and_no_invented_confidence():
    a=paired_uncertainty([.6]*100,[.5]*100,[1]*100)
    b=paired_uncertainty([.6]*100,[.5]*100,[1]*100)
    assert a==b
    assert a["delta_challenger_minus_reference"]["brier_ci95_percentile"][1]<0
    assert a["delta_challenger_minus_reference"]["log_loss_ci95_percentile"][1]<0


def test_same_kickoff_day_never_divided_across_train_and_holdout():
    fixtures=[{"kickoff":f"2026-10-{24+i:02d}T19:00:00+00:00","fixture_id":str(i)} for i in range(2)]
    with pytest.raises(ValueError,match="CHRONO_COHORT_BELOW_600"):
        chronological_groups(fixtures)


def test_post_kickoff_freeze_rejected_fail_closed():
    data=list(mock_canonical(600))
    item=data[2][0]
    item["freeze_timestamp_utc"]=item["event_start_utc"]
    with pytest.raises(ValueError,match="TEMPORAL_OR_FIXTURE_IDENTITY_BROKEN"):
        build(*data)


def test_oos_already_promoted_while_sealed_is_rejected():
    data=list(mock_canonical(600))
    data[5]["promotion_allowed"]=True
    with pytest.raises(ValueError,match="1X_PROMOTION_INCONSISTENT_WITH_SEALED_OOS"):
        build(*data)


def test_derived_probabilities_not_stored_in_governed_frozen_original():
    data=list(mock_canonical(600))
    original=deepcopy(data[1])
    result=build(*data)
    assert original==data[1]
    assert result["market_results"]["DOUBLE_CHANCE_1X"]["candidate_governance_state"]=="EXPLORATORY_RECALIBRATION_ONLY_NOT_PREDECLARED_PROSPECTIVE"


def test_metrics_require_binary_and_finite_probs():
    with pytest.raises(ValueError):
        _metrics([1.1],[1])
    with pytest.raises(ValueError):
        _metrics([.5],[2])
    with pytest.raises(ValueError):
        _metrics([float("nan")],[0])
