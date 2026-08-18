import pytest

from app.research.football.comparison import PairedPrediction, compare_candidate_to_baseline


def make_rows(candidate_good=True):
    rows = []
    for block in range(10):
        for i in range(20):
            outcome = i % 2 == 0
            if candidate_good:
                candidate = 0.8 if outcome else 0.2
            else:
                candidate = 0.5
            baseline = 0.55 if outcome else 0.45
            rows.append(PairedPrediction(f"{block}-{i}", f"week-{block}", outcome, candidate, baseline))
    return rows


def test_block_bootstrap_detects_strong_candidate_dominance():
    report = compare_candidate_to_baseline(make_rows(True), bootstrap_iterations=300, random_seed=7)
    assert report.sample_size == 200
    assert report.block_count == 10
    assert report.brier_delta < 0
    assert report.log_loss_delta < 0
    assert report.candidate_beats_baseline_with_brier_confidence
    assert report.candidate_beats_baseline_with_logloss_confidence


def test_comparison_rejects_single_block_and_duplicate_fixture():
    rows = [PairedPrediction(str(i), "same", i % 2 == 0, 0.5, 0.5) for i in range(10)]
    with pytest.raises(ValueError, match="two blocks"):
        compare_candidate_to_baseline(rows, bootstrap_iterations=100)

    duplicate = PairedPrediction("1", "a", True, 0.8, 0.5)
    with pytest.raises(ValueError, match="one prediction per fixture"):
        compare_candidate_to_baseline([duplicate, duplicate, PairedPrediction("2", "b", False, 0.2, 0.5)], bootstrap_iterations=100)
