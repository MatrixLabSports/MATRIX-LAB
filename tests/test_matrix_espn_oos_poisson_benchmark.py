from copy import deepcopy
from datetime import datetime,timezone
import pytest
from tools.matrix_espn_oos_poisson_benchmark import benchmark


def sample():
    f={"schema":"MATRIX_ESPN_SHA_PROVEN_TWO_MONTH_OVER25_RESEARCH_FREEZE_V1",
       "source_sha256_and_point_in_time_receipts_verified":True,
       "production_p_matrix_authorized":False,"telegram_signal_authorized":False,
       "real_money":"BLOCKED","research_frozen_at_utc":"2026-11-22T04:51:41+00:00",
       "research_rows":[
          {"original_league_id_research_only":"39","provider_fixture_id":"100",
           "kickoff_utc":"2026-11-22T14:00:00+00:00",
           "research_frozen_at_utc":"2026-11-22T04:51:41+00:00",
           "research_probability_over25":0.6,
           "source_history_feature_trace":{"poisson_over25":0.55,"group_baseline_over25":0.52}},
          {"original_league_id_research_only":"39","provider_fixture_id":"101",
           "kickoff_utc":"2026-11-22T16:00:00+00:00",
           "research_frozen_at_utc":"2026-11-22T04:51:41+00:00",
           "research_probability_over25":0.45,
           "source_history_feature_trace":{"poisson_over25":0.4,"group_baseline_over25":0.5}}]}
    s={"schema":"MATRIX_ESPN_SHA_PIT_PROSPECTIVE_OVER25_OOS_SETTLEMENT_V1",
       "source_raw_sha_and_pit_receipts_verified":True,
       "production_p_matrix_authorized":False,"telegram_signal_authorized":False,
       "real_money":"BLOCKED",
       "preregistered_frozen_at_utc":"2026-11-22T04:51:41+00:00",
       "verified_prospective_settlements":2,
       "awaiting_authentic_final":0,"rejected_wrong_identity_or_provenance":0,
       "settled":[
          {"league_id":"39","provider_event_id":"100",
           "frozen_at_utc":"2026-11-22T04:51:41+00:00",
           "final_observed_at_utc":"2026-11-22T22:00:00+00:00",
           "frozen_probability_over25":0.6,"observed_home_goals":2,
           "observed_away_goals":1,"outcome_over25":1},
          {"league_id":"39","provider_event_id":"101",
           "frozen_at_utc":"2026-11-22T04:51:41+00:00",
           "final_observed_at_utc":"2026-11-22T22:00:00+00:00",
           "frozen_probability_over25":0.45,"observed_home_goals":1,
           "observed_away_goals":0,"outcome_over25":0}]}
    return f,s


def test_exact_identity_brier_and_closed_model_gate():
    a,b=sample()
    x=benchmark(a,b,resamples=100,seed=2)
    assert x["prospective_settled"]==2
    assert abs(x["model_brier"]-(0.16+0.2025)/2)<1e-10
    assert abs(x["poisson_brier"]-(0.45**2+0.4**2)/2)<1e-10
    assert len(x["paired_brier_difference_ci95_exploratory"])==2
    assert x["telegram_signal_authorized"] is False
    assert x["scientific_independent_model_certified"] is False


def test_wrong_frozen_probability_fails():
    a,b=sample()
    b["settled"][0]["frozen_probability_over25"]=0.7
    with pytest.raises(ValueError,match="SOURCE_PREGAME_PROBABILITY_CHANGED"):
        benchmark(a,b)


def test_future_score_receipt_fails():
    a,b=sample()
    b["settled"][0]["final_observed_at_utc"]="2026-11-22T12:00:00Z"
    with pytest.raises(ValueError,match="FROZEN_PREDICTION_AFTER_KICKOFF_OR_POSTGAME_INVALID"):
        benchmark(a,b)


def test_future_kickoff_freeze_fails():
    a,b=sample()
    a["research_rows"][0]["kickoff_utc"]="2026-11-22T04:00:00Z"
    with pytest.raises(ValueError,match="FROZEN_PREDICTION_AFTER_KICKOFF_OR_POSTGAME_INVALID"):
        benchmark(a,b)


def test_duplicate_settlement_fails():
    a,b=sample()
    b["settled"][1]=deepcopy(b["settled"][0])
    with pytest.raises(ValueError,match="SETTLEMENT_ID_DUPLICATED_OR_NOT_PRE_FROZEN"):
        benchmark(a,b)


def test_false_promotion_fails():
    a,b=sample()
    a["telegram_signal_authorized"]=True
    with pytest.raises(ValueError,match="RESEARCH_EVIDENCE_GOVERNANCE_NOT_TRUSTED"):
        benchmark(a,b)


def test_missing_preregistered_poisson_fails():
    a,b=sample()
    del a["research_rows"][0]["source_history_feature_trace"]["poisson_over25"]
    with pytest.raises(ValueError,match="SOURCE_BASELINE_NOT_PREREGISTERED"):
        benchmark(a,b)


def test_source_outcome_mismatch_fails():
    a,b=sample()
    b["settled"][0]["outcome_over25"]=0
    with pytest.raises(ValueError,match="SETTLEMENT_GOALS_DO_NOT_MATCH_OUTCOME"):
        benchmark(a,b)
