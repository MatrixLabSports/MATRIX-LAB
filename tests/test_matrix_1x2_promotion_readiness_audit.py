from tools.matrix_1x2_promotion_readiness_audit import build


def test_1x2_fails_closed_until_all_promotion_gates_exist():
    out = build()
    assert out["market"] == "1X2"
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
