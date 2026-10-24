from pathlib import Path
import json

from tools.api_football_final_holdout_adjudication import adjudicate


def test_final_holdout_adjudication_uses_frozen_parameters_and_exact_seal():
    result=adjudicate(Path("."))
    assert result["holdout_row_count"]==357
    assert result["holdout_identity_match"] is True
    assert result["parameter_refit_performed"] is False
    assert result["parameter_search_performed"] is False
    assert result["holdout_open_count"]==1
    assert set(result["metrics"])=={"1x2","over_2_5","btts"}
    assert result["governed_engine_promoted"] is False
    assert result["p_matrix_generated"] is False
    assert result["automatic_wagering"] is False
    assert result["real_money"]=="BLOCKED"


def test_holdout_gate_is_strictly_defined_against_poisson_in_brier_and_log_loss():
    result=adjudicate(Path("."))
    expected=all(
        row["delta_brier_challenger_minus_poisson"]<0 and
        row["delta_log_loss_challenger_minus_poisson"]<0
        for row in result["metrics"].values()
    )
    assert result["all_three_markets_holdout_superiority"] is expected
    assert result["methodological_promotion_gate_passed"] is expected
