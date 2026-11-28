from tools.matrix_football_source_recovery_audit import inspect

POLICY = {"paid_primary": {"paid_through_bogota_date": "2026-10-28", "renewal_authorized": False}}

def test_expired_provider_and_missing_sources_fail_closed():
    result = inspect(POLICY, None, None, "2026-11-01")
    assert result["paid_api_football_window_active"] is False
    assert result["browser_preregistry_current"] is False
    assert all(value == "UNVERIFIED_FAIL_CLOSED" for value in result["sources"].values())
    assert result["network_calls_performed"] == 0
    assert result["canonical_candidate_generation_verified"] is False
    assert result["telegram_delivery_verified"] is False
    assert result["real_money"] == "BLOCKED"

def test_browser_evidence_does_not_authorize_quotes_or_signals():
    browser = {"status": "PASS_BROWSER_FIRST_PREREGISTRATION",
               "target_date_bogota": "2026-11-01",
               "policy": {"source_order": ["SOFASCORE", "FLASHSCORE", "APIS"]}}
    result = inspect(POLICY, browser, None, "2026-11-01")
    assert result["browser_preregistry_current"] is True
    assert result["canonical_candidate_generation_verified"] is False

def test_old_browser_date_rejected():
    browser = {"status": "PASS_BROWSER_FIRST_PREREGISTRATION",
               "target_date_bogota": "2026-10-31",
               "policy": {"source_order": ["SOFASCORE", "FLASHSCORE", "APIS"]}}
    assert inspect(POLICY, browser, None, "2026-11-01")["browser_preregistry_current"] is False
