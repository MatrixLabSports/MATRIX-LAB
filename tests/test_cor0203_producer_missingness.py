import pytest

from tools.cor0203_prospective_producer import feature_snapshot, score_spec


def _player(name, rank):
    return {
        "name": name,
        "source_id": name,
        "hand": "R",
        "age": 24.0,
        "rank": rank,
        "rank_points": 300,
    }


def _state():
    players = ["A", "B"]
    return {
        "history": {
            "matches": {"A": [1, 0, 1], "B": [0, 1, 0]},
            "surface": {
                "A": {"Hard": [2.0, 3.0]},
                "B": {"Hard": [1.0, 3.0]},
            },
            "overall": {"A": [2.0, 3.0], "B": [1.0, 3.0]},
            "serve": {"A": [180.0, 300.0], "B": [170.0, 300.0]},
            "ret": {"A": [120.0, 300.0], "B": [110.0, 300.0]},
            "opp_strength": {"A": [1.8, 3.0], "B": [1.5, 3.0]},
        },
        "elo_overall": {"A": 1550.0, "B": 1500.0},
        "elo_surface": {"Hard": {"A": 1560.0, "B": 1490.0}},
        "glicko_overall": {
            "A": {"r": 1540.0, "rd": 90.0},
            "B": {"r": 1510.0, "rd": 95.0},
        },
        "glicko_surface": {
            "Hard": {
                "A": {"r": 1530.0, "rd": 100.0},
                "B": {"r": 1500.0, "rd": 100.0},
            }
        },
    }


def _event():
    return {"players": [_player("A", 100), _player("B", 120)]}


def test_feature_snapshot_requires_observed_service_history():
    state = _state()
    state["history"]["serve"]["B"] = [0.0, 0.0]
    with pytest.raises(ValueError, match="OBSERVED_FEATURE_MISSING:serve_pts_won:B"):
        feature_snapshot(state, _event())


def test_feature_snapshot_requires_surface_elo_instead_of_1500_fallback():
    state = _state()
    del state["elo_surface"]["Hard"]["B"]
    with pytest.raises(ValueError, match="OBSERVED_FEATURE_MISSING:elo_surface:B"):
        feature_snapshot(state, _event())


def test_score_spec_does_not_impute_missing_feature_with_model_median():
    spec = {
        "features": ["x1", "x2"],
        "median": [0.0, 0.0],
        "scale": [1.0, 1.0],
        "intercept": 0.0,
        "coef": [1.0, 1.0],
    }
    with pytest.raises(ValueError, match="MODEL_FEATURE_MISSING:x2"):
        score_spec(spec, {"x1": 1.0})


def test_complete_observed_snapshot_still_scores():
    _, _, base, eo, es, go, gs = feature_snapshot(_state(), _event())
    values = {**base, "elo_overall_diff": eo, "elo_surface_diff": es}
    spec = {
        "features": ["rank_diff", "elo_overall_diff", "elo_surface_diff"],
        "median": [0.0, 0.0, 0.0],
        "scale": [1.0, 100.0, 100.0],
        "intercept": 0.0,
        "coef": [0.0, 1.0, 1.0],
    }
    p = score_spec(spec, values)
    assert 0.0 < p < 1.0
