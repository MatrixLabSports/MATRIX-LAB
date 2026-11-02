from datetime import datetime, timezone
import json

from tools.matrix_football_independent_fixture_pipeline import capture, normalize

NOW = datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc)

class Reply:
    status = 200
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def read(self, _maxsize):
        return json.dumps(self.payload).encode()

def fixtures_payload():
    return {"matches": [
        {"id": 51, "utcDate": "2026-11-02T15:00:00Z", "status": "SCHEDULED",
         "homeTeam": {"id": 1, "name": "Club A"}, "awayTeam": {"id": 2, "name": "Club B"},
         "competition": {"name": "League"}},
        {"id": 52, "utcDate": "2026-11-03T06:00:00Z", "status": "TIMED",
         "homeTeam": {"id": 3, "name": "Club C"}, "awayTeam": {"id": 4, "name": "Club D"}},
        {"id": 53, "utcDate": "2026-11-02T13:00:00Z", "status": "FINISHED",
         "homeTeam": {"id": 5, "name": "Club E"}, "awayTeam": {"id": 6, "name": "Club F"}},
    ]}

def test_real_provider_format_captures_bogota_day_without_crossing_dates():
    def open_fake(req, timeout):
        assert req.get_header("X-auth-token") == "test-secret"
        assert "dateFrom=2026-11-02" in req.full_url
        assert "dateTo=2026-11-03" in req.full_url
        assert timeout == 25
        return Reply(fixtures_payload())
    result = capture("2026-11-02", "test-secret", opener=open_fake, now_utc=NOW)
    assert result["provider_calls"] == 1
    assert result["fixture_count"] == 1
    assert result["fixtures"][0]["source_fixture_id"] == "51"
    assert result["fixtures"][0]["home"] == "Club A"
    assert result["fixtures"][0]["api_football_fixture_id"] is None
    assert result["signal_generation_authorized"] is False
    assert result["governed_feature_equivalence_verified"] is False
    assert result["real_money"] == "BLOCKED"
    assert "test-secret" not in json.dumps(result)

def test_missing_secret_never_networks():
    def never(*_args, **_kw):
        raise AssertionError("NETWORK_SHOULD_NOT_RUN")
    result = capture("2026-11-02", "", opener=never, now_utc=NOW)
    assert result["provider_status"] == "MISSING_FOOTBALL_DATA_ORG_TOKEN"
    assert result["provider_calls"] == 0
    assert result["fixtures"] == []

def test_duplicate_source_identity_fails_closed():
    items = fixtures_payload()
    items["matches"].append(dict(items["matches"][0]))
    try:
        normalize(items, "2026-11-02", NOW)
    except ValueError as exc:
        assert "DUPLICATE" in str(exc)
    else:
        raise AssertionError("DUPLICATES_MUST_FAIL")

def test_http_failure_never_promotes():
    from urllib.error import HTTPError
    def reject(req, timeout):
        raise HTTPError(req.full_url, 403, "Forbidden", {}, None)
    result = capture("2026-11-02", "secret", opener=reject, now_utc=NOW)
    assert result["provider_status"] == "PROVIDER_HTTP_ERROR"
    assert result["http_status"] == 403
    assert result["fixture_count"] == 0
    assert result["signal_generation_authorized"] is False

def test_invalid_payload_fails_closed():
    result = capture("2026-11-02", "secret", opener=lambda *_a, **_kw: Reply({"matches": "unexpected"}), now_utc=NOW)
    assert result["provider_status"] == "INVALID_PROVIDER_RESPONSE"
    assert result["fixtures"] == []
