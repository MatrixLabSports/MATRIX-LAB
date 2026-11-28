from tools.matrix_dixon_coles_over25_relevance_audit import audit_row, build

def _row(lam=1.4,mu=1.1):
    return {"expected_home_goals":lam,"expected_away_goals":mu}

def test_low_score_tau_preserves_over25_with_fixed_lambdas():
    for rho in (-0.2,-0.1,0.0,0.1,0.2):
        a=audit_row(_row(),rho)
        assert abs(a["mass_delta"]) < 1e-12
        assert abs(a["over25_delta"]) < 1e-12

def test_audit_is_research_only_and_fail_closed():
    out=build([_row(),_row(0.8,0.7)])
    assert out["finding"]=="LOW_SCORE_TAU_WITH_FIXED_LAMBDAS_DOES_NOT_CHANGE_OVER25"
    assert out["production_engine_modified"] is False
    assert out["parameter_tuning_allowed"] is False
    assert out["odds_used_to_generate_probability"] is False
    assert out["real_money"]=="BLOCKED"
