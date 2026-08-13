import pytest

from app.sports.tennis.processing_result import TennisProcessingResult


def test_tennis_processing_result_can_be_created():
    result = TennisProcessingResult(
        accepted=True,
        reason="valid_match",
    )

    assert result.accepted is True
    assert result.reason == "valid_match"

def test_tennis_processing_result_stores_confidence():
    result = TennisProcessingResult(
        accepted=True,
        reason="valid_match",
        confidence=0.85,
    )

    assert result.confidence == 0.85


def test_tennis_processing_result_rejects_confidence_below_zero():
    with pytest.raises(ValueError):
        TennisProcessingResult(
            accepted=True,
            reason="valid_match",
            confidence=-0.01,
        )


def test_tennis_processing_result_rejects_confidence_above_one():
    with pytest.raises(ValueError):
        TennisProcessingResult(
            accepted=True,
            reason="valid_match",
            confidence=1.01,
        )

def test_tennis_processing_result_exposes_data_coverage_score():
    result = TennisProcessingResult(
        accepted=True,
        reason="valid_match",
        confidence=0.85,
    )

    assert result.data_coverage_score == 0.85
