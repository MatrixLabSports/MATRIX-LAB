from datetime import datetime, timedelta, timezone
import pytest

from matrix_elite.calibration import calibration_table, maximum_calibration_gap
from matrix_elite.temporal_validation import TemporalObservation, purged_expanding_walk_forward, final_chronological_holdout_indices, assert_no_tuning_on_holdout
from matrix_elite.uncertainty import paired_moving_block_bootstrap_model_vs_market
from matrix_elite.oos_governance import OOSPromotionEvidence, oos_promotion_gate

UTC=timezone.utc
T0=datetime(2025,1,1,tzinfo=UTC)


def test_purged_walk_forward_excludes_targets_unresolved_at_validation_start():
    obs=[]
    for i in range(12):
        d=T0+timedelta(days=i)
        obs.append(TemporalObservation(d,d+timedelta(hours=1)))
    # Force the first configured fold (validation day 5) to be inadmissible,
    # then force index 6 to remain unresolved at the next fold (validation day 7).
    obs[4]=TemporalObservation(T0+timedelta(days=4),T0+timedelta(days=6))
    obs[6]=TemporalObservation(T0+timedelta(days=6),T0+timedelta(days=8))
    folds=purged_expanding_walk_forward(obs,min_train=5,validation_size=2)
    assert folds[0].validation_start == T0+timedelta(days=7)
    assert 6 not in folds[0].train_indices
    assert all(obs[i].target_available_at <= folds[0].purge_cutoff for i in folds[0].train_indices)


def test_purged_walk_forward_embargo_removes_recent_training_labels():
    obs=[TemporalObservation(T0+timedelta(days=i),T0+timedelta(days=i,hours=1)) for i in range(15)]
    folds=purged_expanding_walk_forward(obs,min_train=5,validation_size=2,embargo=timedelta(days=2))
    assert all(obs[i].target_available_at <= folds[0].purge_cutoff for i in folds[0].train_indices)


def test_final_holdout_is_tail_and_cannot_be_tuned():
    tune,hold=final_chronological_holdout_indices(100,holdout_size=20)
    assert tune[-1]==79 and hold[0]==80 and hold[-1]==99
    assert_no_tuning_on_holdout(tuning_indices=tune,holdout_indices=hold)
    with pytest.raises(ValueError,match="TOUCHED"):
        assert_no_tuning_on_holdout(tuning_indices=[79,80],holdout_indices=hold)


def test_calibration_table_marks_underpowered_bins_and_wilson_intervals():
    p=[.1]*10+[.9]*50; y=[0]*8+[1]*2+[1]*45+[0]*5
    table=calibration_table(p,y,bins=10,minimum_bin_n=20)
    assert table[1].underpowered is True and table[9].underpowered is False
    assert table[9].wilson_low is not None and table[9].wilson_high is not None
    assert maximum_calibration_gap(table) >= 0


def test_max_calibration_gap_refuses_all_underpowered_bins():
    table=calibration_table([.1,.9],[0,1],bins=2,minimum_bin_n=10)
    with pytest.raises(ValueError,match="NO_POWERED"):
        maximum_calibration_gap(table)


def test_moving_block_bootstrap_is_deterministic_for_seed():
    y=[1,0]*50; model=[.8,.2]*50; market=[.6,.4]*50
    a=paired_moving_block_bootstrap_model_vs_market(model,market,y,block_length=5,bootstrap_samples=200,seed=7)
    b=paired_moving_block_bootstrap_model_vs_market(model,market,y,block_length=5,bootstrap_samples=200,seed=7)
    assert a==b and a.brier_ci95[0]>0 and a.log_loss_ci95[0]>0


def test_moving_block_bootstrap_rejects_too_few_resamples():
    y=[1,0]*20
    with pytest.raises(ValueError,match="BOOTSTRAP_SAMPLES_TOO_SMALL"):
        paired_moving_block_bootstrap_model_vs_market([.7,.3]*20,[.6,.4]*20,y,block_length=2,bootstrap_samples=50)


def good_evidence():
    y=[1,0]*50; model=[.8,.2]*50; market=[.6,.4]*50
    boot=paired_moving_block_bootstrap_model_vs_market(model,market,y,block_length=5,bootstrap_samples=200,seed=1)
    return OOSPromotionEvidence(
        sport="football",market="BTTS",pit_snapshot_sha256="a"*64,identity_manifest_sha256="b"*64,
        model_version="m1",feature_version="f1",fold_count=4,final_holdout_n=100,final_holdout_untouched=True,
        model_ece=.05,max_calibration_gap=.08,block_bootstrap=boot,segment_positive_fraction=.8,segment_eligible_count=5,
        leakage_audit_passed=True,market_baseline_present=True,empirical_baseline_present=True,
    )


def test_oos_promotion_gate_requires_all_evidence():
    e=good_evidence()
    assert oos_promotion_gate(e,max_ece=.1,max_calibration_gap=.1)
    bad=OOSPromotionEvidence(**{**e.__dict__,"final_holdout_untouched":False})
    assert not oos_promotion_gate(bad,max_ece=.1,max_calibration_gap=.1)
    bad2=OOSPromotionEvidence(**{**e.__dict__,"market_baseline_present":False})
    assert not oos_promotion_gate(bad2,max_ece=.1,max_calibration_gap=.1)


def test_oos_promotion_gate_blocks_calibration_or_segment_instability():
    e=good_evidence()
    bad=OOSPromotionEvidence(**{**e.__dict__,"model_ece":.2})
    assert not oos_promotion_gate(bad,max_ece=.1,max_calibration_gap=.1)
    bad2=OOSPromotionEvidence(**{**e.__dict__,"segment_positive_fraction":.5})
    assert not oos_promotion_gate(bad2,max_ece=.1,max_calibration_gap=.1)
