from app.research.football.comparison import PairedModelComparison
from app.research.football.governance import ResearchPromotionEvidence, ResearchPromotionGate
from app.research.football.quality import DatasetQualityReport
from app.research.football.validation import BinaryModelEvaluation, ModelPromotionPolicy


def quality(passed=True):
    return DatasetQualityReport(
        row_count=1000, fixture_count=1000, partition_counts={"train": 700, "validation": 100, "test": 200},
        market_label="over_2_5", positive_rate=0.5, feature_schema_count=1,
        feature_quality=(), suspicious_features=(), reasons=() if passed else ("bad_data",),
    )


def evaluation():
    return BinaryModelEvaluation(
        market="over_2_5", partition="test", sample_size=600, brier_score=0.18,
        log_loss=0.58, calibration_error=0.03, positive_rate=0.5, mean_probability=0.5, bins=(),
    )


def comparison(confident=True):
    upper = -0.01 if confident else 0.01
    return PairedModelComparison(
        sample_size=600, block_count=20,
        candidate_brier=0.18, baseline_brier=0.21, brier_delta=-0.03,
        brier_delta_ci_low=-0.05, brier_delta_ci_high=upper,
        candidate_log_loss=0.58, baseline_log_loss=0.62, log_loss_delta=-0.04,
        log_loss_delta_ci_low=-0.08, log_loss_delta_ci_high=-0.01,
    )


def test_governance_remains_fail_closed_without_paper_odds_reproducibility():
    evidence = ResearchPromotionEvidence(quality(), evaluation(), comparison())
    gate = ResearchPromotionGate(model_policy=ModelPromotionPolicy(min_test_samples=500))
    reasons = gate.reasons_blocked(evidence)
    assert "insufficient_paper_trading" in reasons
    assert "odds_ev_validation_missing" in reasons
    assert "reproducibility_not_verified" in reasons
    assert not gate.live_money_eligible(evidence)


def test_governance_can_pass_only_when_every_gate_is_satisfied():
    evidence = ResearchPromotionEvidence(
        quality(), evaluation(), comparison(),
        paper_trading_samples=700, odds_validation_complete=True, reproducibility_verified=True,
    )
    gate = ResearchPromotionGate(model_policy=ModelPromotionPolicy(min_test_samples=500))
    assert gate.reasons_blocked(evidence) == ()
    assert gate.live_money_eligible(evidence)


def test_governance_blocks_candidate_that_does_not_confidently_beat_baseline():
    evidence = ResearchPromotionEvidence(
        quality(), evaluation(), comparison(False),
        paper_trading_samples=700, odds_validation_complete=True, reproducibility_verified=True,
    )
    assert "candidate_does_not_beat_baseline_on_brier_with_confidence" in ResearchPromotionGate().reasons_blocked(evidence)
