import pytest

from app.research.football.validation import (
    BinaryPrediction,
    ModelPromotionPolicy,
    evaluate_binary_predictions,
)


def pred(i, p, outcome, partition="test", market="over_2_5"):
    return BinaryPrediction(str(i), market, partition, p, outcome)


def test_evaluation_computes_brier_logloss_and_calibration():
    report = evaluate_binary_predictions([
        pred(1, 0.8, True), pred(2, 0.7, True), pred(3, 0.2, False), pred(4, 0.3, False)
    ], bin_count=5)
    assert report.sample_size == 4
    assert report.brier_score == pytest.approx(0.065)
    assert report.log_loss > 0
    assert 0 <= report.calibration_error <= 1
    assert report.positive_rate == 0.5


def test_evaluation_rejects_mixing_markets_or_partitions():
    with pytest.raises(ValueError, match="single market|solo market|market"):
        evaluate_binary_predictions([pred(1, 0.5, True), pred(2, 0.5, False, market="btts")])
    with pytest.raises(ValueError, match="partition"):
        evaluate_binary_predictions([pred(1, 0.5, True), pred(2, 0.5, False, partition="validation")])


def test_evaluation_rejects_duplicate_fixture_to_avoid_weighting_leakage():
    with pytest.raises(ValueError, match="mismo fixture"):
        evaluate_binary_predictions([pred(1, 0.6, True), pred(1, 0.7, True)])


def test_promotion_policy_fails_closed_on_insufficient_sample():
    report = evaluate_binary_predictions([pred(i, 0.5, i % 2 == 0) for i in range(20)])
    policy = ModelPromotionPolicy(min_test_samples=500)
    assert not policy.is_promotable(report)
    assert "insufficient_test_sample" in policy.reasons_not_promotable(report)


def test_promotion_policy_never_accepts_validation_as_live_evidence():
    report = evaluate_binary_predictions([pred(i, 0.5, i % 2 == 0, partition="validation") for i in range(20)])
    policy = ModelPromotionPolicy(min_test_samples=10, max_brier_score=1, max_calibration_error=1, max_log_loss=2)
    assert "evaluation_not_test_partition" in policy.reasons_not_promotable(report)
