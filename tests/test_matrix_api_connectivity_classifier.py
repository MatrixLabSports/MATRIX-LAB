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


def test_secret_presence_does_not_expose_values():
    from tools.matrix_api_connectivity_classifier import secret_presence
    values = {"API_FOOTBALL_KEY": "private-football-value",
              "RAPIDAPI_TENNIS_KEY": "private-rapid-value",
              "API_TENNIS_KEY": "", "ODDS_API_NET_KEY": "private-odds-value"}
    result = secret_presence(values)
    assert result["api_football"]["configured"] is True
    assert result["rapidapi_tennis"]["configured"] is True
    assert result["api_tennis"]["configured"] is False
    assert result["odds_api_net"]["configured"] is True
    assert all(not row["live_connectivity_verified"] for row in result.values())
    assert not any(secret in str(result) for secret in values.values() if secret)


def test_api_football_probe_success_redacts_key():
    from tools.matrix_api_connectivity_classifier import probe_api_football
    class Response:
        status_code = 200
        def json(self):
            return {"response": {"account": {"firstname": "Test"}}}
    class Session:
        def get(self, url, headers, timeout):
            assert url.endswith("/status")
            assert headers["x-apisports-key"] == "secret-test-key"
            assert timeout == 12
            return Response()
    result = probe_api_football("secret-test-key", session=Session())
    assert result["status"] == "VERIFIED_RESPONSE"
    assert "secret-test-key" not in str(result)


def test_api_football_probe_denied_and_missing():
    from tools.matrix_api_connectivity_classifier import probe_api_football
    class Response:
        status_code = 403
    class Session:
        def get(self, url, headers, timeout):
            return Response()
    assert probe_api_football("key", session=Session())["status"] == "AUTHENTICATION_OR_ENTITLEMENT_FAILED"
    assert probe_api_football("", session=Session())["status"] == "NOT_TESTED"
