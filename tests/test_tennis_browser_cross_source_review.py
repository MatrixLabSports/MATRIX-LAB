from tools.tennis_browser_cross_source_review import review


def test_review_requires_both_original_links():
    sofa = {"schema": "MATRIX_BROWSER_TENNIS_CALENDAR_DISCOVERY_V1", "events": [{"event_id": "17449699", "source_url": "https://www.sofascore.com/es/tennis/match/a-b/slug#id:17449699"}]}
    flash = {"schema": "MATRIX_BROWSER_FLASHSCORE_TENNIS_LINK_DISCOVERY_V1", "links": [{"url": "https://www.flashscore.co/partido/tenis/faria-jaime-ETojuYQP/hijikata-rinky-f9eT4NTQ/?mid=test"}]}
    result = review(sofa, flash)
    assert result["reviewed_pair_count"] == 1
    assert result["candidate_eligible"] is False
    assert result["telegram_send_authorized"] is False
    assert result["kickoff_verified"] is False
    assert result["confirmed_same_match_count"] == 0
    assert result["reviewed_pairs"][0]["same_match_confirmed"] is False


def test_review_never_invents_missing_source():
    result = review({"schema": "MATRIX_BROWSER_TENNIS_CALENDAR_DISCOVERY_V1", "events": []}, {"schema": "MATRIX_BROWSER_FLASHSCORE_TENNIS_LINK_DISCOVERY_V1", "links": []})
    assert result["reviewed_pair_count"] == 0
    assert len(result["missing_reviewed_ids"]) == 3


def test_review_ignores_nonnumeric_sofa_identifiers():
    result = review({"schema": "MATRIX_BROWSER_TENNIS_CALENDAR_DISCOVERY_V1", "events": [{"event_id": "invalid", "source_url": "example"}]}, {"schema": "MATRIX_BROWSER_FLASHSCORE_TENNIS_LINK_DISCOVERY_V1", "links": []})
    assert result["reviewed_pair_count"] == 0
    assert result["confirmed_same_match_count"] == 0


def test_review_rejects_wrong_source_schema():
    import pytest
    with pytest.raises(ValueError, match="SOFA_SCHEMA"):
        review({"schema": "WRONG", "events": []}, {"schema": "MATRIX_BROWSER_FLASHSCORE_TENNIS_LINK_DISCOVERY_V1", "links": []})
