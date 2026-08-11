from dataclasses import dataclass

import pytest

from app.sports.tennis.data_coverage import TennisDataCoverage


def test_tennis_data_coverage_with_no_evidence_is_zero():
    coverage = TennisDataCoverage(
        recent_form=False,
        surface_history=False,
        serve_stats=False,
        return_stats=False,
        fatigue_context=False,
        market_data=False,
    )

    assert coverage.score() == 0.0

def test_tennis_data_coverage_with_all_evidence_is_one():
    coverage = TennisDataCoverage(
        recent_form=True,
        surface_history=True,
        serve_stats=True,
        return_stats=True,
        fatigue_context=True,
        market_data=True,
    )

    assert coverage.score() == 1.0

def test_tennis_data_coverage_with_half_evidence_is_half():
    coverage = TennisDataCoverage(
        recent_form=True,
        surface_history=True,
        serve_stats=True,
        return_stats=False,
        fatigue_context=False,
        market_data=False,
    )

    assert coverage.score() == 0.5

def test_tennis_data_coverage_with_one_evidence_is_one_sixth():
    coverage = TennisDataCoverage(
        recent_form=True,
        surface_history=False,
        serve_stats=False,
        return_stats=False,
        fatigue_context=False,
        market_data=False,
    )

    assert coverage.score() == 1 / 6

def test_tennis_data_coverage_rejects_non_boolean_evidence():
    with pytest.raises(TypeError):
        TennisDataCoverage(
            recent_form=2,
            surface_history=False,
            serve_stats=False,
            return_stats=False,
            fatigue_context=False,
            market_data=False,
        )

@pytest.mark.parametrize(
    "field_name",
    [
        "surface_history",
        "serve_stats",
        "return_stats",
        "fatigue_context",
        "market_data",
    ],
)
def test_tennis_data_coverage_rejects_non_boolean_in_other_fields(field_name):
    evidence = {
        "recent_form": False,
        "surface_history": False,
        "serve_stats": False,
        "return_stats": False,
        "fatigue_context": False,
        "market_data": False,
    }
    evidence[field_name] = 1

    with pytest.raises(TypeError):
        TennisDataCoverage(**evidence)

def test_tennis_data_coverage_score_adapts_to_new_evidence_field():
    @dataclass(frozen=True)
    class ExpandedTennisDataCoverage(TennisDataCoverage):
        weather_context: bool

    coverage = ExpandedTennisDataCoverage(
        recent_form=False,
        surface_history=False,
        serve_stats=False,
        return_stats=False,
        fatigue_context=False,
        market_data=False,
        weather_context=True,
    )

    assert coverage.score() == 1 / 7