from __future__ import annotations

import json
from pathlib import Path

from tools.tennis_clay_glicko_adjudication import build


def test_clay_glicko_and_elo_use_same_sealed_434_oos(tmp_path):
    result = build(tmp_path / "adjudication")
    adjudication = result["adjudication"]
    assert adjudication["oos_physical_event_count"] == 434
    assert adjudication["historical_oos_used_for_parameter_selection"] is False
    assert adjudication["accuracy_used_for_selection"] is False
    assert adjudication["policy"]["fixed_before_final_oos_comparison"] is True

    elo = adjudication["candidates"]["ATP_CHALLENGER_CLAY_ELO_V1"]["metrics"]
    glicko = adjudication["candidates"]["ATP_CHALLENGER_CLAY_GLICKO_V1"]["metrics"]
    assert elo["n"] == 434
    assert glicko["n"] == 434
    for metrics in (elo, glicko):
        assert 0 <= metrics["brier"] <= 1
        assert metrics["log_loss"] > 0
        assert 0 <= metrics["accuracy"] <= 1
        assert 0 <= metrics["ece_10bin"] <= 1
        assert 0 <= metrics["mce_10bin"] <= 1
        assert sum(x["n"] for x in metrics["bins"]) == 434


def test_glicko_parameters_selected_only_on_validation(tmp_path):
    result = build(tmp_path / "adjudication")
    g = result["glicko"]
    assert g["parameter_selection"]["selection_split"] == "VALIDATION"
    assert g["parameter_selection"]["final_historical_oos_not_used_for_selection"] is True
    assert g["parameter_selection"]["initial_rd_grid"] == [200.0, 250.0, 300.0, 350.0]
    assert all(x["validation"]["n"] == 358 for x in g["parameter_selection"]["candidates"])


def test_holdout_is_independent_and_starts_zero_if_adjudication_passes(tmp_path):
    result = build(tmp_path / "adjudication")
    winner = result["adjudication"]["winner"]
    holdout = result["holdout"]
    if winner is None:
        assert holdout is None
        assert result["adjudication"]["promotion_status"] == "NO_GO_BUILD_NEXT_CHALLENGER"
    else:
        assert holdout is not None
        assert holdout["holdout_id"] == "ATP_CHALLENGER_CLAY_PROSPECTIVE_V1"
        assert holdout["holdout_id"] != "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1"
        assert holdout["current_observations"] == 0
        assert holdout["metrics_opened"] is False
        assert holdout["outcomes_read"] == 0
        assert holdout["historical_backfill"] == "FORBIDDEN"
        assert holdout["dual_paid_provider_requirement"] == ["RAPIDAPI_TENNIS", "API_TENNIS"]
        assert holdout["real_money"] == "BLOCKED"
