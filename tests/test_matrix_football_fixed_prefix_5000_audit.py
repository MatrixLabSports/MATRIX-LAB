from tools.matrix_football_fixed_prefix_5000_audit import TARGET, build


def test_current_state_is_sealed_below_5000_or_open_exactly_when_ready():
    r=build()
    assert r["status"]=="PASS"
    assert r["target_settled_count"]==TARGET==5000
    assert r["current_settled_count"]>=0
    assert r["automatic_promotion"] is False
    if r["current_settled_count"]<5000:
        assert r["audit_state"]=="SEALED_BELOW_5000"
        assert r["metrics_opened"] is False
        assert r["metrics"] is None
        assert r["remaining_to_5000"]==5000-r["current_settled_count"]
        assert r["audit_verdict"]=="HOLD"
    else:
        assert r["audit_state"]=="OPEN_FIXED_PREFIX_5000"
        assert r["metrics_opened"] is True
        assert r["prefix"]["observation_count"]==5000
        assert r["remaining_to_5000"]==0


def test_5000_audit_preserves_no_tuning_and_no_wagering_contract():
    r=build()
    p=r["protections"]
    assert p["fixed_prefix_only"] is True
    assert p["final_ft_only"] is True
    assert p["append_only_source"] is True
    assert p["parameter_tuning_allowed"] is False
    assert p["refit_allowed"] is False
    assert p["historical_backfill"] is False
    assert p["post_start_backfill"] is False
    assert p["odds_used_to_generate_probability"] is False
    assert p["automatic_wagering"] is False
    assert p["real_money"]=="BLOCKED"


def test_metrics_never_open_before_target():
    r=build()
    if r["current_settled_count"]<5000:
        assert r["metrics"] is None
        assert r["temporal_stability"] is None
        assert r["competition_concentration"] is None
        assert r["next_required_action"]=="CONTINUE_FINAL_ONLY_SETTLEMENT_UNTIL_5000"
