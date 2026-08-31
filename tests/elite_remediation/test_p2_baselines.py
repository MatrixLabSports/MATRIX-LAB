import pytest

from matrix_elite.baselines import (
    BaselineInputEvidence,
    binary_baseline_benchmark,
    fit_binary_empirical_baseline,
    fit_multiclass_empirical_baseline,
    multiclass_baseline_benchmark,
    multiclass_brier_score,
    multiclass_log_loss,
    require_registered_market,
    sample_size_gate,
    segment_stability_gate,
)
from matrix_elite.baseline_governance import MarketBaselinePolicy, default_baseline_policies, validate_baseline_evidence


def evidence(sport="football", market="BTTS", train_n=200, validation_n=50):
    return BaselineInputEvidence(sport, market, "a"*64, "b"*64, True, train_n, validation_n)


def test_market_registry_is_separated_by_sport():
    require_registered_market("football", "BTTS")
    require_registered_market("tennis", "MATCH_WINNER")
    with pytest.raises(ValueError, match="MARKET_NOT_REGISTERED_FOR_SPORT"):
        require_registered_market("football", "MATCH_WINNER")


def test_baseline_evidence_requires_pit_identity_and_rights():
    with pytest.raises(ValueError, match="RIGHTS_GATE_REQUIRED"):
        BaselineInputEvidence("football","BTTS","a"*64,"b"*64,False,200,50)
    with pytest.raises(ValueError, match="PIT_SNAPSHOT_SHA256_REQUIRED"):
        BaselineInputEvidence("football","BTTS","bad","b"*64,True,200,50)


def test_binary_empirical_baseline_uses_training_only():
    train=[1]*8+[0]*2
    p=fit_binary_empirical_baseline(train)
    a=binary_baseline_benchmark(train_outcomes=train,validation_outcomes=[1,1,1,1],validation_market_probabilities=[.7]*4)
    b=binary_baseline_benchmark(train_outcomes=train,validation_outcomes=[0,0,0,0],validation_market_probabilities=[.3]*4)
    assert a.empirical_probability == b.empirical_probability == p


def test_binary_benchmark_reports_empirical_and_market_baselines():
    out=binary_baseline_benchmark(train_outcomes=[1,0]*20,validation_outcomes=[1,0]*10,validation_market_probabilities=[.6,.4]*10)
    assert out.n==20 and out.market_brier < out.empirical_brier


def test_multiclass_empirical_probabilities_are_smoothed_and_sum_to_one():
    p=fit_multiclass_empirical_baseline(["H","D","A","H"],labels=["H","D","A"])
    assert len(p)==3 and abs(sum(p)-1)<1e-12 and all(x>0 for x in p)


def test_multiclass_metrics_validate_probability_simplex():
    with pytest.raises(ValueError, match="SUM_TO_ONE"):
        multiclass_brier_score([[.5,.5,.2]],["H"],labels=["H","D","A"])
    with pytest.raises(ValueError, match="SUM_TO_ONE"):
        multiclass_log_loss([[.5,.5,.2]],["H"],labels=["H","D","A"])


def test_1x2_multiclass_market_benchmark_is_supported():
    train=["H","D","A"]*20
    val=["H","D","A"]*10
    market=[[.5,.25,.25],[.25,.5,.25],[.25,.25,.5]]*10
    out=multiclass_baseline_benchmark(train_outcomes=train,validation_outcomes=val,validation_market_probabilities=market,labels=["H","D","A"])
    assert out.n==30 and out.market_brier < out.empirical_brier and out.market_log_loss < out.empirical_log_loss


def test_sample_size_gate_is_explicit():
    assert sample_size_gate(train_n=200,validation_n=50,minimum_train=200,minimum_validation=50)
    assert not sample_size_gate(train_n=199,validation_n=50,minimum_train=200,minimum_validation=50)


def test_segment_stability_requires_positive_improvement_in_most_eligible_segments():
    r=segment_stability_gate({"home":(100,.01,.02),"away":(100,.02,.01),"rare":(10,-.1,-.1)},minimum_segment_n=50,minimum_positive_segment_fraction=.75)
    assert r["pass"] and r["segments_underpowered"]==1
    r2=segment_stability_gate({"a":(100,.01,.01),"b":(100,-.01,-.01)},minimum_segment_n=50,minimum_positive_segment_fraction=.75)
    assert not r2["pass"]


def test_default_policy_has_one_distinct_entry_per_registered_market():
    p=default_baseline_policies()
    assert ("football","1X2") in p and p[("football","1X2")].task_type=="MULTICLASS"
    assert ("tennis","MATCH_WINNER") in p and p[("tennis","MATCH_WINNER")].task_type=="BINARY"
    assert all(not x.shared_cross_market_model_allowed for x in p.values())


def test_shared_cross_market_model_is_forbidden_by_policy():
    with pytest.raises(ValueError, match="SHARED_CROSS_MARKET_MODEL_FORBIDDEN"):
        MarketBaselinePolicy("football","BTTS","BINARY",200,50,shared_cross_market_model_allowed=True)


def test_policy_validation_blocks_underpowered_market_segment():
    assert validate_baseline_evidence(evidence())
    with pytest.raises(ValueError, match="SAMPLE_SIZE_GATE_FAILED"):
        validate_baseline_evidence(evidence(train_n=199))
