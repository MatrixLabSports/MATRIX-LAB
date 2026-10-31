from __future__ import annotations

import importlib.util

import pytest
from pathlib import Path

MODULE_PATH = Path("tools/api_football_over25_forward_validation_1444_1544.py")
SPEC = importlib.util.spec_from_file_location("over25_1444_1544", MODULE_PATH)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


def _row(pc: float, pp: float, y: bool):
    return {
        "frozen_challenger_probabilities": {"over_2_5": pc},
        "frozen_poisson_reference": {"over_2_5": pp},
        "outcomes": {"over_2_5": y},
    }


def test_metrics_expose_required_calibration_fields():
    rows = [
        _row(0.8, 0.7, True),
        _row(0.6, 0.55, True),
        _row(0.4, 0.45, False),
        _row(0.2, 0.3, False),
    ]
    m = MOD._metrics(rows, "challenger")
    assert m["sample_size"] == 4
    assert m["ece"] >= 0
    assert m["max_calibration_error"] >= 0
    assert m["observed_over_2_5_rate"] == 0.5
    assert m["mean_predicted_probability"] == pytest.approx(0.5, abs=1e-12)
    assert m["accuracy_at_0_5_diagnostic_only"] == 1.0
    assert len(m["probability_band_reliability"]) == 4


def test_paired_comparison_requires_both_proper_scores_directionally_better():
    rows = [
        _row(0.8, 0.6, True),
        _row(0.2, 0.4, False),
        _row(0.75, 0.55, True),
        _row(0.25, 0.45, False),
    ]
    p = MOD._paired(rows)
    assert p["delta_brier_challenger_minus_poisson"] < 0
    assert p["delta_log_loss_challenger_minus_poisson"] < 0
    assert p["proper_scoring_directional_pass"] is True
    assert len(p["brier_ci95"]) == 2
    assert len(p["log_loss_ci95"]) == 2
