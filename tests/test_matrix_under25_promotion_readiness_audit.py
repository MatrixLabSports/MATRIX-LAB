from tools.matrix_under25_promotion_readiness_audit import build


def test_under25_fails_closed_until_all_promotion_gates_exist():
    out = build()
    assert out["market"] == "UNDER_2_5"
    assert out["checks"]["checkpoint_4000_complete"] is True
    assert out["checks"]["derived_from_over25_declared"] is True
    assert out["governance"]["minimum_decimal_odds_exclusive"] == 1.50
    assert out["governance"]["positive_ev_required"] is True
    assert out["governance"]["p_matrix_must_exist_before_odds"] is True
    assert out["governance"]["odds_may_not_generate_probability"] is True
    assert out["governance"]["no_backfill"] is True
    assert out["governance"]["automatic_wagering"] is False
    assert out["governance"]["real_money"] == "BLOCKED"
    if out["promotion_allowed"]:
        assert out["status"] == "PASS_PROMOTION_READY"
        assert not out["blockers"]
    else:
        assert out["status"] == "BLOCKED_NOT_PROMOTABLE"
        assert out["signal_status"] == "RESEARCH_ONLY"
        assert out["blockers"]
