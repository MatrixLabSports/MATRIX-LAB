from app.sports.tennis.processing_result import TennisProcessingResult


def test_tennis_processing_result_can_be_created():
    result = TennisProcessingResult(
        accepted=True,
        reason="valid_match",
    )

    assert result.accepted is True
    assert result.reason == "valid_match"