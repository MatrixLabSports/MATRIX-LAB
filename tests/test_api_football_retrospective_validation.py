from pathlib import Path

from tools.api_football_retrospective_validation import build_retrospective_walk_forward


def test_retrospective_validation_is_temporal_and_fail_closed_on_promotion():
    result=build_retrospective_walk_forward(Path("evidence/api_football/history/raw"))
    assert result["evaluation_kind"]=="RETROSPECTIVE_TEMPORAL_WALK_FORWARD_NOT_PROSPECTIVE"
    assert result["eligible_prediction_count"]>0
    assert result["parsed_final_fixture_count"]>=result["eligible_prediction_count"]
    assert result["promotion_screen"]["governed_engine_promoted"] is False
    assert result["promotion_screen"]["p_matrix_generated"] is False
    assert result["promotion_screen"]["paper_trading_satisfied"] is False
    assert result["promotion_screen"]["odds_ev_validation_satisfied"] is False
    assert result["promotion_screen"]["external_audit_closed"] is False
    assert result["automatic_wagering"] is False
    assert result["real_money"]=="BLOCKED"


def test_each_evaluated_market_has_poisson_and_naive_metrics():
    result=build_retrospective_walk_forward(Path("evidence/api_football/history/raw"))
    for market in ("1x2","over_2_5","btts"):
        row=result["metrics"][market]
        assert row["poisson"]["sample_size"]==result["eligible_prediction_count"]
        assert row["baseline"]["sample_size"]==result["eligible_prediction_count"]
        assert isinstance(row["delta_brier_poisson_minus_baseline"],float)
        assert isinstance(row["delta_log_loss_poisson_minus_baseline"],float)
