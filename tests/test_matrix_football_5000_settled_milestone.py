from tools.matrix_football_5000_settled_milestone import TARGET, _state, build


def test_current_physical_milestone_is_consistent_and_safe():
    r=build()
    assert r["status"]=="PASS"
    assert r["target_settled_count"]==5000
    assert r["current_settled_count"]>=0
    assert r["remaining_to_5000"]==max(0,5000-r["current_settled_count"])
    assert r["fixed_prefix_5000"]["automatic_promotion"] is False
    c=r["settlement_contract"]
    assert c["final_ft_only"] is True
    assert c["append_only"] is True
    assert c["duplicate_fixture_ids_forbidden"] is True
    assert c["hash_chain_verified"] is True
    assert c["historical_backfill"] is False
    assert c["post_start_backfill"] is False
    assert c["parameter_tuning_allowed"] is False
    assert c["refit_allowed"] is False
    assert c["automatic_promotion"] is False
    assert c["automatic_wagering"] is False
    assert c["real_money"]=="BLOCKED"


def test_state_before_5000_is_tracking_only():
    state,action=_state(TARGET-1)
    assert state=="TRACKING_TO_5000"
    assert action=="CONTINUE_FINAL_ONLY_SETTLEMENT_UNTIL_5000"


def test_state_at_5000_is_ready_for_fixed_prefix_audit_not_promotion():
    state,action=_state(TARGET)
    assert state=="READY_FOR_5000_AUDIT"
    assert action=="RUN_FIXED_PREFIX_5000_CALIBRATION_AUDIT_NO_AUTO_PROMOTION"


def test_state_above_5000_remains_ready_for_same_fixed_prefix_audit():
    state,action=_state(TARGET+250)
    assert state=="READY_FOR_5000_AUDIT"
    assert action=="RUN_FIXED_PREFIX_5000_CALIBRATION_AUDIT_NO_AUTO_PROMOTION"
