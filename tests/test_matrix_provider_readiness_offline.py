from tools.matrix_provider_readiness_offline import audit, PROVIDERS, REQUIRED

def test_missing_evidence_fails_closed():
    result = audit({})
    assert result["network_calls_performed"] == 0
    assert result["provider_authorization_granted_by_this_tool"] is False
    assert result["signal_generation_authorized_by_this_tool"] is False
    assert all(result["providers"][name]["status"] == "UNVERIFIED_FAIL_CLOSED" for name in PROVIDERS)

def test_partial_evidence_does_not_promote_provider():
    result = audit({"rapidapi_tennis": {"account_plan_verified": True}})
    assert result["providers"]["rapidapi_tennis"]["status"] == "UNVERIFIED_FAIL_CLOSED"

def test_complete_record_still_does_not_authorize_network_or_signals():
    row = {key: True for key in REQUIRED}
    row.update(verification_artifact="evidence/example.json", verified_at_utc="2026-11-01T00:00:00Z")
    result = audit({"odds_api_net": row})
    assert result["providers"]["odds_api_net"]["status"] == "EVIDENCE_RECORDED_NOT_RUNTIME_AUTHORIZATION"
    assert result["provider_authorization_granted_by_this_tool"] is False
    assert result["signal_generation_authorized_by_this_tool"] is False
