from tools.tennis_browser_cross_source_review import review


def test_review_requires_both_original_links():
    sofa = {"events": [{"event_id": "17449699", "source_url": "https://www.sofascore.com/es/tennis/match/a-b/slug#id:17449699"}]}
    flash = {"links": [{"url": "https://www.flashscore.co/partido/tenis/faria-jaime-ETojuYQP/hijikata-rinky-f9eT4NTQ/?mid=test"}]}
    result = review(sofa, flash)
    assert result["reviewed_pair_count"] == 1
    assert result["candidate_eligible"] is False
    assert result["telegram_send_authorized"] is False
    assert result["kickoff_verified"] is False


def test_review_never_invents_missing_source():
    result = review({"events": []}, {"links": []})
    assert result["reviewed_pair_count"] == 0
    assert len(result["missing_reviewed_ids"]) == 3
