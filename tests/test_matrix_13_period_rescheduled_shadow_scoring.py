"""Synthetic adversarial regression for isolated source-attested half-time shadow scoring."""
from copy import deepcopy

import pytest
from tools.matrix_13_market_exact_cohort_calibration import PERIOD_LANES
from tools.matrix_13_period_rescheduled_shadow_scoring import shadow_score


def samples():
    source={
        "fixture_id":"123",
        "status":"RESEARCH_ATTESTATION_NOT_ADMITTED_TO_CALIBRATION",
        "frozen_scheduled_kickoff_utc":"2026-10-25T20:00:00+00:00",
        "source_final_fixture_kickoff_utc":"2026-10-25T21:00:00+00:00",
        "original_prediction_freeze_utc":"2026-10-25T19:00:00+00:00",
        "original_final_goals":{"home":2,"away":1},
        "original_explicit_halftime_goals":{"home":1,"away":1},
    }
    att={"rows":[source],"original_source_qualified_candidates_not_promoted":1}
    baseline={"lanes":[]}
    portfolio=[]
    for lane in PERIOD_LANES:
        thresholds=("over_0_5",) if "_TEAM_TOTAL_GOALS_" in lane else ("over_0_5","over_1_5")
        baseline["lanes"].append({
            "market_key":lane,
            "exact_cohort_final_verified":501,
            "calibration_metrics_unpromoted":{
                k:{"n":501,"brier":.25,"log_loss":.69,"ece":.05}
                for k in thresholds
            },
        })
        portfolio.append({
            "fixture_id":"123",
            "market_lane":lane,
            "record_type":"PROSPECTIVE_PREMATCH_FREEZE",
            "prospective_admitted":True,
            "real_money":"BLOCKED","automatic_wagering":False,
            "odds_used_to_generate_probability":False,
            "target_outcome":None,"settlement":None,
            "prediction_snapshot_sha256":"a"*64,
            "prediction":{k:.65 for k in thresholds},
            "event_start_utc":"2026-10-25T20:00:00+00:00",
            "freeze_timestamp_utc":"2026-10-25T19:00:00+00:00",
        })
    return baseline, att, portfolio


def test_shadow_all_six_markets_leave_formal_501_unchanged():
    b,a,p=samples()
    report=shadow_score(b,a,p)
    assert report["research_source_candidate_count"]==1
    assert len(report["six_period_markets"])==6
    assert all(x["original_formal_exact_final_count"]==501 for x in report["six_period_markets"])
    assert all(x["research_only_potential_exact_final_count"]==502 for x in report["six_period_markets"])
    assert all(x["promoted"] is False for x in report["six_period_markets"])
    assert report["original_formal_cohort_mutated"] is False
    assert report["real_money"]=="BLOCKED"
    assert report["telegram_signal_authorized"] is False


def test_weighted_brier_logloss_only_ece_never_guessed():
    b,a,p=samples()
    r=shadow_score(b,a,p)
    x=r["six_period_markets"][0]["research_only_proper_scoring"]["over_0_5"]
    assert x["research_combined_n"]==502
    assert x["research_combined_ece"] is None
    assert x["extra_verified_original_source_n_research_only"]==1
    assert x["research_combined_brier"]>=0
    assert x["research_combined_log_loss"]>=0
    assert x["original_metrics_remain_unchanged"] is True


def test_outcome_embedded_in_original_freeze_never_allowed():
    b,a,p=samples()
    p[0]["target_outcome"]=1
    with pytest.raises(ValueError,match="SHADOW_UNTRUSTED_PROSPECTIVE_FORECAST_LINEAGE"):
        shadow_score(b,a,p)


def test_poststart_or_retimed_original_forecast_is_rejected():
    b,a,p=samples()
    p[0]["freeze_timestamp_utc"]="2026-10-25T21:01:00+00:00"
    with pytest.raises(ValueError,match="SHADOW_UNTRUSTED_PROSPECTIVE_FORECAST_LINEAGE"):
        shadow_score(b,a,p)


def test_duplicate_market_fixture_never_counted_twice():
    b,a,p=samples()
    p.append(deepcopy(p[0]))
    with pytest.raises(ValueError,match="SHADOW_DUPLICATE_PROSPECTIVE_FIXTURE"):
        shadow_score(b,a,p)


def test_unattested_fixture_cannot_slip_into_shadow():
    b,a,p=samples()
    a["original_source_qualified_candidates_not_promoted"]=2
    with pytest.raises(ValueError,match="SHADOW_DUPLICATE_SOURCE_ATTESTATION"):
        shadow_score(b,a,p)


def test_missing_original_frozen_market_prediction_fails():
    b,a,p=samples()
    p.pop()
    with pytest.raises(ValueError,match="SHADOW_MISSING_FROZEN_FORECAST"):
        shadow_score(b,a,p)
