from datetime import datetime, timezone, timedelta
import pytest
from matrix_elite.pit import audit_point_in_time, valid_history_windows
from matrix_elite.identity import IdentityBinding, CanonicalIdentityRegistry
from matrix_elite.metrics import brier_score, log_loss, expected_calibration_error, devig_multiplicative, expected_value, clv_probability
from matrix_elite.walk_forward import expanding_walk_forward, assert_final_holdout_untouched
from matrix_elite.paper_ledger import FrozenDecision, HashChainedPaperLedger
from matrix_elite.live_slo import LiveTiming, live_slo_report
from matrix_elite.risk import Position, fractional_kelly, exposure_audit, deterministic_bankroll_stress
from matrix_elite.failover import ProviderHealth, governed_failover
from matrix_elite.rights import RightsProfile
from matrix_elite.sre import ContinuityEvidence, production_continuity_gate
from matrix_elite.postmortem import classify_outcome

UTC=timezone.utc
BASE=datetime(2026,1,1,tzinfo=UTC)

def test_pit_rejects_future_available_data():
    rows=[{"observed_at":BASE,"available_at":BASE+timedelta(minutes=2)}]
    assert audit_point_in_time(rows,as_of=BASE+timedelta(minutes=1))[0].code=="NOT_AVAILABLE_AS_OF"
    assert valid_history_windows(21)[20] is True and valid_history_windows(21)[30] is False

def test_identity_forbids_silent_name_join_and_rebind():
    r=CanonicalIdentityRegistry(); b=IdentityBinding("p","1","c1",.99,"a"*64); r.bind(b)
    assert r.resolve("p","1")=="c1"
    with pytest.raises(ValueError): r.resolve_by_name("John")
    with pytest.raises(ValueError): r.bind(IdentityBinding("p","1","c2",.99,"b"*64))

def test_metrics_and_devig():
    assert 0 <= brier_score([.8,.2],[1,0]) < .1
    assert log_loss([.8,.2],[1,0]) > 0
    assert expected_calibration_error([.8,.2],[1,0],bins=5) >= 0
    fair=devig_multiplicative([1.91,1.91]); assert abs(sum(fair)-1)<1e-12
    assert expected_value(2.1,.5) > 0
    assert clv_probability(2.0,.55) > 0

def test_walk_forward_is_temporal_and_holdout_separate():
    ts=[BASE+timedelta(days=i) for i in range(12)]
    folds=expanding_walk_forward(ts,min_train=6,validation_size=2)
    assert len(folds)==3
    assert max(folds[0].train_indices) < min(folds[0].validation_indices)
    with pytest.raises(ValueError): assert_final_holdout_untouched(tuning_indices=[1,2],holdout_indices=[2,3])

def test_hash_chained_paper_ledger_freezes_pre_event_decisions():
    led=HashChainedPaperLedger()
    a=FrozenDecision("d1","football","e","m","s",BASE,BASE+timedelta(hours=1),2.0,.55,"PAPER_BET","m1","f1","c"*64,None)
    h=led.append(a)
    b=FrozenDecision("d2","football","e2","m","s",BASE,BASE+timedelta(hours=2),None,None,"NO_BET","m1","f1",None,h)
    led.append(b); assert led.size==2

def test_live_slo_reports_missed_and_stale():
    s=LiveTiming(10,10,10,10,10,10,10,10,100)
    r=live_slo_report([s],stale_threshold_ms=50)
    assert r["p50_ms"]==80 and r["stale_signal_rate"]==1 and r["missed_window_rate"]==0

def test_risk_caps_and_stress():
    assert fractional_kelly(2.0,.55,.25) > 0
    r=exposure_audit([Position("football","e","m",.03,"g"),Position("football","e","m2",.03,"g")],max_event=.05,max_day=.1,max_group=.05)
    assert r["event_cap_breached"] and r["correlation_cap_breached"]
    assert deterministic_bankroll_stress(100,[.1,.1])["ending_bankroll"]==81

def test_governed_failover_never_switches_automatically():
    a=ProviderHealth("a",1,False,True,True); b=ProviderHealth("b",1,True,True,True)
    with pytest.raises(ValueError): governed_failover(a,b,human_approved=False)
    assert governed_failover(a,b,human_approved=True)=="b"

def test_rights_and_continuity():
    r=RightsProfile("p",True,True,True,True,False,False,False,None,"d"*64)
    assert r.admissible_for("research") and not r.admissible_for("commercial_use")
    e=ContinuityEvidence(True,True,50,10,True,True,True)
    assert production_continuity_gate(e,max_rto_s=60,max_rpo_s=30)

def test_variance_cannot_be_used_without_evidence():
    with pytest.raises(ValueError): classify_outcome(primary_cause="LEGITIMATE_VARIANCE",evidence=())
    assert classify_outcome(primary_cause="MODEL_ERROR",evidence=("audit:1",))["review_required"] is False
from matrix_elite.sports_policies import (
    FOOTBALL_ANALYSIS_ORDER, SimpleBetAdmission, CombinationAdmission,
    combination_frequency_ok, validate_live_state, validate_tennis_feature_context,
)

def test_sport_policies_preserve_matrix_parameters():
    assert FOOTBALL_ANALYSIS_ORDER[0]=="INDIVIDUAL_PLAYER" and FOOTBALL_ANALYSIS_ORDER[-1]=="ODDS_EV"
    assert SimpleBetAdmission(1.69,.05,True,True,True).admissible() is False
    assert SimpleBetAdmission(1.69,.05,True,True,True,"documented exception").admissible() is True
    assert SimpleBetAdmission(2.0,-.01,True,True,True).admissible() is False
    assert CombinationAdmission(3,.2,False,.1).admissible() is False
    assert CombinationAdmission(3,.2,True,.1).admissible() is True
    assert combination_frequency_ok(simple_bets=9,combination_bets=1)
    assert not combination_frequency_ok(simple_bets=8,combination_bets=2)
    assert validate_live_state("WATCH")=="WATCH"
    validate_tennis_feature_context(history_windows=(5,10,20,30,50),injury_claim=False,injury_verified=False)
    with pytest.raises(ValueError):
        validate_tennis_feature_context(history_windows=(5,10,20,30,50),injury_claim=True,injury_verified=False)
from matrix_elite.evaluation import compare_model_to_market, backtested_promotion_gate
from matrix_elite.odds import OddsSnapshot, reject_stale, fair_market_probabilities, closing_line_value

def test_oos_model_comparison_requires_real_improvement():
    y=[1,0]*20
    model=[.9 if v else .1 for v in y]
    market=[.6 if v else .4 for v in y]
    c=compare_model_to_market(model,market,y,bootstrap_samples=100,seed=1)
    assert c.brier_improvement>0 and c.log_loss_improvement>0
    assert backtested_promotion_gate(c,max_model_ece=.15)

def test_odds_binding_devig_staleness_and_clv():
    t=BASE
    a=OddsSnapshot('e','m','A','book',t,1.91,False)
    b=OddsSnapshot('e','m','B','book',t,1.91,False)
    fair=fair_market_probabilities([a,b]); assert abs(sum(fair.values())-1)<1e-12
    reject_stale(a,now=t+timedelta(seconds=30),max_age=timedelta(minutes=1))
    with pytest.raises(ValueError): reject_stale(a,now=t+timedelta(minutes=2),max_age=timedelta(minutes=1))
    assert closing_line_value(taken_decimal_odds=2.0,closing_fair_probability=.55)>0
