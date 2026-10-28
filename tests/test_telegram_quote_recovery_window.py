from datetime import datetime, timezone

from tools.telegram_green_signal_alerts import (
    ODDS_API_NET_EVENT_SEARCH_WINDOW_SECONDS,
    build_blocker_recovery_audit,
    physical_open_bookmaker_names,
    odds_api_net_exact_over25_offer,
)


def test_odds_event_search_window_is_two_hours_each_side():
    assert ODDS_API_NET_EVENT_SEARCH_WINDOW_SECONDS == 7200


def test_blocker_audit_never_marks_past_kickoff_quote_gap_recoverable():
    now = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)
    key = "k"
    ledger = {
        "pre_send_gate": {
            key: {
                "state": "BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25",
                "checked_at_utc": "2026-10-23T17:56:32+00:00",
                "odds_api_net_diagnostic": {
                    "status": "BLOCKED_EVENT_NOT_COVERED",
                    "discard_reasons": {},
                },
            }
        }
    }
    candidates = {
        key: {
            "sport": "football",
            "fixture_id": "123",
            "match": "A vs B",
            "league_id": "1",
            "kickoff": "2026-10-23T17:00:00+00:00",
            "p_matrix": 0.64,
            "house": "MULTIBOOK_REVALIDATION",
            "odds": None,
            "ev": None,
        }
    }
    out = build_blocker_recovery_audit(ledger, candidates, set(), now)
    assert out["summary"]["counts_by_recoverability"] == {
        "NOT_RECOVERABLE_NO_BACKFILL": 1
    }
    row = out["records"][0]
    assert row["time_state_at_audit"] == "PAST_KICKOFF"
    assert row["final_disposition"] == "PAST_KICKOFF_NO_BACKFILL"
    assert row["sources_available_for_recovery"] == []



def test_blocker_report_separates_live_quote_checks_from_historical_terminal_states():
    now = datetime(2026, 10, 26, 23, 0, tzinfo=timezone.utc)
    live = "live"
    old = "old"
    ledger = {
        "pre_send_gate": {
            live: {
                "state": "BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25",
                "checked_at_utc": now.isoformat(),
                "live_quote_attempted_this_run": True,
                "quote_attempt_run_token": now.isoformat(),
                "odds_api_net_diagnostic": {},
                "api_football_offer_diagnostic": {},
            },
            old: {
                "state": "BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25",
                "checked_at_utc": "2026-10-25T20:00:00+00:00",
                "odds_api_net_diagnostic": {},
                "api_football_offer_diagnostic": {},
            },
        },
        "candidate_lifecycle": {
            old: {
                "first_terminal_state": "BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25"
            }
        },
    }
    candidates = {
        live: {
            "sport": "football",
            "fixture_id": "1",
            "match": "Live A vs B",
            "league_id": "10",
            "kickoff": "2026-10-27T00:00:00+00:00",
            "p_matrix": 0.64,
        },
        old: {
            "sport": "football",
            "fixture_id": "2",
            "match": "Old A vs B",
            "league_id": "20",
            "kickoff": "2026-10-26T20:00:00+00:00",
            "p_matrix": 0.64,
        },
    }
    out = build_blocker_recovery_audit(ledger, candidates, set(), now)
    s = out["summary"]
    assert s["counts_by_state"]["BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25"] == 2
    assert s["counts_by_state_scope"] == "LEGACY_COMBINED_LIVE_AND_HISTORICAL_DO_NOT_USE_AS_LIVE_COVERAGE"
    assert s["live_quote_attempt_records_this_run"] == 1
    assert s["live_quote_attempts_this_run_by_state"] == {
        "BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25": 1
    }
    assert s["historical_terminal_inherited_records"] == 1
    assert s["historical_terminal_inherited_by_state"] == {
        "BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25": 1
    }
    assert s["legacy_combined_counts_must_not_be_interpreted_as_live_quote_checks"] is True


def test_browser_recovery_count_matches_physical_coverage():
    names = physical_open_bookmaker_names()
    assert len(names) == 12
    assert "YaJuego" not in names
    assert "Zamba" not in names


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload

class _FixtureLookupFailureThenEmptyOdds:
    def get(self, url, **kwargs):
        if "api-sports.io/fixtures" in url:
            return _FakeResponse(429, {"errors": {"rateLimit": "reached"}, "response": []})
        if url.endswith("/events"):
            return _FakeResponse(200, {"items": [], "next_cursor": None})
        raise AssertionError(url)

def test_odds_identity_falls_back_to_preregistered_candidate_when_api_fixture_lookup_fails():
    diagnostic = {}
    offer = odds_api_net_exact_over25_offer(
        _FixtureLookupFailureThenEmptyOdds(),
        "key",
        "1611788",
        "2026-10-28T10:00:00+00:00",
        0.6127141456,
        "api-key",
        diagnostic,
        candidate_match="Shakhtar Donetsk U19 vs Livyi Bereh U19",
    )
    assert offer is None
    assert diagnostic["fixture_identity_source"] == "CANDIDATE_PREREGISTERED_MATCH_FALLBACK"
    assert diagnostic["api_football_fixture_lookup_status"] == "FAILED_FALLBACK_USED"
    assert diagnostic["identity_source"]["home"] == "Shakhtar Donetsk U19"
    assert diagnostic["identity_source"]["away"] == "Livyi Bereh U19"
    assert diagnostic["status"] == "BLOCKED_EVENT_NOT_COVERED"


class _RateLimitResponse:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
    def json(self):
        return self._payload

class _FixtureOkThenRateLimitedEvents:
    def get(self, url, **kwargs):
        if "api-sports.io/fixtures" in url:
            return _RateLimitResponse(200, {
                "response": [{
                    "teams": {
                        "home": {"name": "Shakhtar Donetsk U19"},
                        "away": {"name": "Livyi Bereh U19"}
                    }
                }]
            })
        if url.endswith("/events"):
            return _RateLimitResponse(
                429,
                {"detail": "rate limited", "code": "RATE_LIMITED", "request_id": "req-test"},
                {"Retry-After": "30", "X-RateLimit-Remaining": "0", "X-RateLimit-Bucket": "events"}
            )
        raise AssertionError(url)

def test_odds_event_search_429_is_explicit_and_fail_closed():
    diagnostic = {}
    offer = odds_api_net_exact_over25_offer(
        _FixtureOkThenRateLimitedEvents(),
        "key",
        "1611788",
        "2026-10-28T10:00:00+00:00",
        0.6127141456,
        "api-key",
        diagnostic,
        candidate_match="Shakhtar Donetsk U19 vs Livyi Bereh U19",
    )
    assert offer is None
    assert diagnostic["status"] == "BLOCKED_EVENT_SEARCH_RATE_LIMIT"
    assert diagnostic["event_search_http_status"] == 429
    assert diagnostic["event_search_retry_after_seconds"] == "30"
    assert diagnostic["event_search_rate_limit_remaining"] == "0"
    assert diagnostic["event_search_rate_limit_bucket"] == "events"
    assert diagnostic["event_search_request_id"] == "req-test"
