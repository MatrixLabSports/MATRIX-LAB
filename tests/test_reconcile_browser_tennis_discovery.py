from tools.reconcile_browser_tennis_discovery import flash_identity, reconcile


def test_flash_variants_deduplicate_by_player_pair():
    a = "https://www.flashscore.co/partido/tenis/player-a-ID1/player-b-ID2/"
    b = a + "?mid=abc"
    assert flash_identity(a) == flash_identity(b)


def test_reconciliation_does_not_claim_unverified_cross_provider_match():
    sofa = {"schema": "MATRIX_BROWSER_TENNIS_CALENDAR_DISCOVERY_V1", "calendar_date": "2026-10-31", "events": [{"event_id": "123", "source_url": "https://www.sofascore.com/es/tennis/match/a-b/slug#id:123"}]}
    flash = {"schema": "MATRIX_BROWSER_FLASHSCORE_TENNIS_LINK_DISCOVERY_V1", "links": [{"name": "A - B", "url": "https://www.flashscore.co/partido/tenis/a-123/b-456/"}, {"name": "A - B", "url": "https://www.flashscore.co/partido/tenis/a-123/b-456/?mid=abc"}]}
    result = reconcile(sofa, flash)
    assert result["sofascore_unique_events"] == 1
    assert result["flashscore_unique_player_pair_urls"] == 1
    assert result["cross_provider_confirmed_matches"] == 0
    assert result["candidate_eligible"] is False
    assert result["telegram_send_authorized"] is False
