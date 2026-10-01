import pytest
from tools.api_football_calibration_diagnostics_v2 import (
    _brier_skill,
    _bin_rows,
    build_diagnostics,
)


def _rows(n: int):
    rows = []
    for i in range(n):
        rows.append({
            "frozen_challenger_probabilities": {
                "1x2": {"H": 0.75, "D": 0.15, "A": 0.10},
                "over_2_5": 0.75,
                "btts_v2": 0.75,
            },
            "frozen_poisson_reference": {
                "1x2": {"H": 0.65, "D": 0.20, "A": 0.15},
                "over_2_5": 0.65,
                "btts": 0.65,
            },
            "outcomes": {
                "1x2": "H" if i % 4 else "A",
                "over_2_5": False if i % 4 == 0 else True,
                "btts": False if i % 4 == 0 else True,
            },
        })
    return rows


def test_bin_rows_tracks_high_confidence_band():
    table = _bin_rows([(0.75, 1), (0.77, 1), (0.79, 0)])
    target = [r for r in table if r["lower"] == 0.75][0]
    assert target["n"] == 3
    assert 0.75 <= target["mean_probability"] < 0.80
    assert target["observed_rate"] == 2 / 3


def test_brier_skill_positive_when_challenger_lower():
    assert _brier_skill(0.20, 0.25) == pytest.approx(0.2)


def test_diagnostics_uses_gate100_only_and_never_allows_tuning():
    d = build_diagnostics(_rows(129))
    assert d["observations_used"] == 100
    assert d["evaluation_sample"] == "DECLARED_GATE100_PREFIX_ONLY"
    assert d["parameter_tuning_allowed"] is False
    assert d["governance"]["gate100_used_for_tuning"] is False
    assert d["governance"]["original_357_holdout_reuse_allowed"] is False
    assert d["governance"]["p_matrix_status"] == "NOT_GENERATED"
    assert d["governance"]["real_money"] == "BLOCKED"
