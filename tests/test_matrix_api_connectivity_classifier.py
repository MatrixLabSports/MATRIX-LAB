"""Tests for the credential-safe API connectivity evidence classifier."""
from tools.matrix_api_connectivity_classifier import classify

def test_not_tested_is_not_connected():
    result = classify("api_tennis")
    assert result["status"] == "NOT_TESTED"
    assert result["real_money"] == "BLOCKED"

def test_reject_authentication_failures():
    for status in (401, 403):
        assert classify("api_football", http_status=status)["status"] == "AUTHENTICATION_OR_ENTITLEMENT_FAILED"

def test_quota_limit_not_success():
    assert classify("rapidapi_tennis", http_status=429)["status"] == "QUOTA_OR_RATE_LIMIT"

def test_success_requires_authenticated_valid_payload():
    assert classify("api_tennis", http_status=200)["status"] == "UNVERIFIED_RESPONSE"
    assert classify("api_tennis", http_status=200, authenticated=True)["status"] == "UNVERIFIED_RESPONSE"
    result = classify("api_tennis", http_status=200, authenticated=True, payload_valid=True)
    assert result["status"] == "VERIFIED_RESPONSE"
    assert result["automatic_wagering"] is False
