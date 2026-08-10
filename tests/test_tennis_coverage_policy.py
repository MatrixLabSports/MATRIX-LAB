import pytest

from app.sports.tennis.coverage_policy import TennisCoveragePolicy
from app.sports.tennis.data_coverage import TennisDataCoverage


def make_coverage(
    recent_form: bool,
    surface_history: bool,
    serve_stats: bool,
    return_stats: bool,
    fatigue_context: bool,
    market_data: bool,
) -> TennisDataCoverage:
    return TennisDataCoverage(
        recent_form=recent_form,
        surface_history=surface_history,
        serve_stats=serve_stats,
        return_stats=return_stats,
        fatigue_context=fatigue_context,
        market_data=market_data,
    )


def test_policy_accepts_coverage_at_threshold():
    policy = TennisCoveragePolicy(minimum_score=0.5)

    coverage = make_coverage(
        True,
        True,
        True,
        False,
        False,
        False,
    )

    assert policy.accepts(coverage) is True


def test_policy_rejects_coverage_below_threshold():
    policy = TennisCoveragePolicy(minimum_score=0.5)

    coverage = make_coverage(
        True,
        True,
        False,
        False,
        False,
        False,
    )

    assert policy.accepts(coverage) is False


def test_policy_accepts_complete_coverage():
    policy = TennisCoveragePolicy(minimum_score=0.5)

    coverage = make_coverage(
        True,
        True,
        True,
        True,
        True,
        True,
    )

    assert policy.accepts(coverage) is True


def test_policy_rejects_zero_coverage():
    policy = TennisCoveragePolicy(minimum_score=0.5)

    coverage = make_coverage(
        False,
        False,
        False,
        False,
        False,
        False,
    )

    assert policy.accepts(coverage) is False


@pytest.mark.parametrize("minimum_score", [-0.01, 1.01])
def test_policy_rejects_threshold_outside_valid_range(minimum_score):
    with pytest.raises(ValueError):
        TennisCoveragePolicy(minimum_score=minimum_score)


@pytest.mark.parametrize("minimum_score", [True, False, "0.5", None])
def test_policy_rejects_invalid_threshold_type(minimum_score):
    with pytest.raises(TypeError):
        TennisCoveragePolicy(minimum_score=minimum_score)


def test_policy_rejects_invalid_coverage_object():
    policy = TennisCoveragePolicy()

    with pytest.raises(TypeError):
        policy.accepts(object())

def test_policy_accepts_minimum_score_zero():
    policy = TennisCoveragePolicy(minimum_score=0.0)

    coverage = make_coverage(
        False,
        False,
        False,
        False,
        False,
        False,
    )

    assert policy.accepts(coverage) is True

def test_policy_accepts_minimum_score_one_with_complete_coverage():
    policy = TennisCoveragePolicy(minimum_score=1.0)

    coverage = make_coverage(
        True,
        True,
        True,
        True,
        True,
        True,
    )

    assert policy.accepts(coverage) is True

def test_policy_rejects_minimum_score_one_with_incomplete_coverage():
    policy = TennisCoveragePolicy(minimum_score=1.0)

    coverage = make_coverage(
        True,
        True,
        True,
        True,
        True,
        False,
    )

    assert policy.accepts(coverage) is False