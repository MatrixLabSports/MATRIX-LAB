from dataclasses import FrozenInstanceError, fields
import pytest

from app.sports.tennis.coverage_policy import TennisCoveragePolicy
from app.sports.tennis.data_coverage import TennisDataCoverage


def make_coverage(available_count: int) -> TennisDataCoverage:
    evidence_fields = fields(TennisDataCoverage)
    evidence = {
        field.name: index < available_count
        for index, field in enumerate(evidence_fields)
    }
    return TennisDataCoverage(**evidence)


def test_policy_accepts_coverage_at_threshold():
    coverage = make_coverage(3)
    policy = TennisCoveragePolicy(minimum_score=coverage.score())

    assert policy.accepts(coverage) is True


def test_policy_rejects_coverage_below_threshold():
    policy = TennisCoveragePolicy(minimum_score=0.5)

    coverage = make_coverage(2)

    assert policy.accepts(coverage) is False


def test_policy_accepts_complete_coverage():
    policy = TennisCoveragePolicy(minimum_score=0.5)

    coverage = make_coverage(len(fields(TennisDataCoverage)))

    assert policy.accepts(coverage) is True


def test_policy_rejects_zero_coverage():
    policy = TennisCoveragePolicy(minimum_score=0.5)

    coverage = make_coverage(0)

    assert policy.accepts(coverage) is False


@pytest.mark.parametrize(
    "minimum_score",
    [-0.01, 1.01, float("nan"), float("inf"), float("-inf")],
)
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

    coverage = make_coverage(0)

    assert policy.accepts(coverage) is True

def test_policy_accepts_minimum_score_one_with_complete_coverage():
    policy = TennisCoveragePolicy(minimum_score=1.0)

    coverage = make_coverage(len(fields(TennisDataCoverage)))

    assert policy.accepts(coverage) is True

def test_policy_rejects_minimum_score_one_with_incomplete_coverage():
    policy = TennisCoveragePolicy(minimum_score=1.0)

    coverage = make_coverage(len(fields(TennisDataCoverage)) - 1)

    assert policy.accepts(coverage) is False

def test_policy_is_immutable():
    policy = TennisCoveragePolicy()

    with pytest.raises(FrozenInstanceError):
        policy.minimum_score = 0.75