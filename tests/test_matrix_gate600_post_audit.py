from tools.matrix_gate600_post_audit import build


def test_post600_audit_targets_only_lab_lanes_at_or_above_600():
    r=build()
    assert r["status"]=="PASS"
    assert r["gate600_lab_lane_count"]==4
    assert {x["market_lane"] for x in r["lanes"]}=={
        "MATCH_RESULT_1X2",
        "DOUBLE_CHANCE_1X",
        "DOUBLE_CHANCE_X2",
        "DOUBLE_CHANCE_12",
    }


def test_post600_audit_never_auto_promotes_and_requires_settled_600():
    r=build()
    p=r["adjudication_policy"]
    assert p["freeze_gate_threshold"]==600
    assert p["settled_gate_threshold"]==600
    assert p["pass_requires_exact_settled_600"] is True
    assert p["pass_requires_brier_better_than_poisson"] is True
    assert p["pass_requires_logloss_better_than_poisson"] is True
    assert p["no_automatic_promotion"] is True
    assert all(x["automatic_promotion"] is False for x in r["lanes"])


def test_post600_audit_preserves_safety_contract():
    r=build()
    p=r["protections"]
    assert p["exact_fixture_intersection_between_42_lane_ledger_and_final_calibration_ledger"] is True
    assert p["final_ft_only"] is True
    assert p["parameter_tuning_allowed"] is False
    assert p["refit_allowed"] is False
    assert p["historical_backfill"] is False
    assert p["post_start_backfill"] is False
    assert p["missing_not_zero"] is True
    assert p["silent_imputation"] is False
    assert p["odds_used_to_generate_probability"] is False
    assert p["automatic_wagering"] is False
    assert p["real_money"]=="BLOCKED"


def test_post600_audit_verdict_is_grounded_in_exact_settled_count():
    r=build()
    for lane in r["lanes"]:
        n=lane["exact_settled_count"]
        if n<600:
            assert lane["verdict"]=="HOLD"
            assert lane["remaining_settled_to_600"]==600-n
            assert lane["verdict_reason"]=="AWAITING_600_EXACT_SETTLED_OBSERVATIONS"
        else:
            assert lane["metrics"] is not None
            expected="PASS" if lane["metrics"]["proper_scoring_gate_passed"] else "NO_GO"
            assert lane["verdict"]==expected


def test_diagnostics_do_not_invent_new_gating_thresholds():
    r=build()
    p=r["adjudication_policy"]
    assert p["ece_is_diagnostic_not_a_new_invented_threshold"] is True
    assert p["temporal_stability_is_diagnostic_not_a_new_invented_threshold"] is True
    assert p["competition_concentration_is_diagnostic_not_a_new_invented_threshold"] is True
