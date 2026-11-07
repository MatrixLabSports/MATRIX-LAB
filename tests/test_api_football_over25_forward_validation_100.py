from __future__ import annotations

import importlib.util

import pytest
from pathlib import Path

MODULE_PATH = Path("tools/api_football_over25_forward_validation_100.py")
SPEC = importlib.util.spec_from_file_location("over25_forward_100", MODULE_PATH)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


def _row(pc: float, pp: float, y: bool):
    return {
        "frozen_challenger_probabilities": {"over_2_5": pc},
        "frozen_poisson_reference": {"over_2_5": pp},
        "outcomes": {"over_2_5": y},
    }


def test_binary_metrics_reports_calibration_and_outcome_rate():
    rows = [
        _row(0.8, 0.7, True),
        _row(0.6, 0.55, True),
        _row(0.4, 0.45, False),
        _row(0.2, 0.3, False),
    ]
    result = MOD._binary_metrics(rows, "challenger")
    assert result["sample_size"] == 4
    assert result["observed_over_2_5_rate"] == 0.5
    assert result["mean_predicted_probability"] == pytest.approx(0.5, abs=1e-12)
    assert result["accuracy_at_0_5_diagnostic_only"] == 1.0
    assert result["calibration"]["method"] == "EQUAL_WIDTH_10_BINS"
    assert len(result["probability_band_reliability"]) == 4


def test_paired_comparison_directional_pass_when_both_scores_improve():
    rows = [
        _row(0.8, 0.6, True),
        _row(0.2, 0.4, False),
        _row(0.75, 0.55, True),
        _row(0.25, 0.45, False),
    ]
    result = MOD._paired_comparison(rows)
    assert result["delta_brier_challenger_minus_poisson"] < 0
    assert result["delta_log_loss_challenger_minus_poisson"] < 0
    assert result["proper_scoring_directional_pass"] is True


def test_paired_comparison_exposes_uncertainty_intervals():
    rows = [
        _row(0.99, 0.8, True),
        _row(0.49, 0.3, False),
    ]
    result = MOD._paired_comparison(rows)
    assert isinstance(result["proper_scoring_directional_pass"], bool)
    assert len(result["brier_ci95"]) == 2
    assert len(result["log_loss_ci95"]) == 2
