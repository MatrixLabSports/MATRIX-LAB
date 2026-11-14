"""Offline regression for authenticated primary + public free secondary crosscheck."""
import json
from datetime import datetime, timezone
from urllib.error import HTTPError

import pytest

from tools.matrix_football_free_secondary_crosscheck import (
    capture, crosscheck, stamp, norm, MAX_CALLS,
)


def primary():
    return {
        "schema": "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
        "target_date_bogota": "2026-11-05",
        "source": "FOOTBALL_DATA_ORG",
        "real_money": "BLOCKED",
        "signal_generation_authorized": False,
        "fixtures": [
            {"source_fixture_id": "555077", "home": "SE Palmeiras",
             "away": "Clube do Remo",
             "kickoff_utc": "2026-11-05T22:30:00+00:00"}
        ],
    }


def response(rows):
    return [{"query_day_utc": "2026-11-05", "http_status": 200,
             "provider_status": "PUBLIC_EVENTS_RESPONSE", "events": rows}]


def event(event_id="9009", home="SE Palmeiras", away="Clube do Remo",
          timestamp="2026-11-05T22:30:00Z"):
    return {"idEvent": event_id, "strSport": "Soccer",
            "strHomeTeam": home, "strAwayTeam": away, "strTimestamp": timestamp}


def test_valid_three_source_hint_cannot_promote_research_to_telegram():
    doc = crosscheck(primary(), response([event()]), target_day="2026-11-05",
                     observed_at="2026-11-05T14:00:00Z")
    assert doc["verified_identity_hint_count"] == 1
    assert doc["matched"][0]["secondary_event_id"] == "9009"
    assert doc["production_p_matrix_authorized"] is False
    assert doc["historical_feature_equivalence_verified"] is False
    assert doc["telegram_signal_authorized"] is False
    assert doc["real_money"] == "BLOCKED"


def test_unknown_provider_clock_and_mismatched_kickoff_rejected():
    rows = [event(timestamp="2026-11-05T22:30:00"),  # naive time never becomes UTC
            event(event_id="9010", timestamp="2026-11-05T22:31:00Z")]
    doc = crosscheck(primary(), response(rows), target_day="2026-11-05",
                     observed_at="2026-11-05T14:00:00Z")
    assert doc["verified_identity_hint_count"] == 0
    assert doc["rejected"][0]["reason"] == "NO_EXACT_SECONDARY_EVENT"


def test_home_away_reversal_not_treated_as_equivalent():
    doc = crosscheck(primary(), response([event(home="Clube do Remo", away="SE Palmeiras")]),
                     target_day="2026-11-05", observed_at="2026-11-05T14:00:00Z")
    assert doc["verified_identity_hint_count"] == 0


def test_duplicate_primary_identity_fails_closed():
    p = primary()
    p["fixtures"].append(p["fixtures"][0].copy())
    with pytest.raises(ValueError, match="DUPLICATE_PRIMARY_ID"):
        crosscheck(p, response([event()]), target_day="2026-11-05",
                   observed_at="2026-11-05T14:00:00Z")


def test_invalid_primary_signal_authorization_rejected():
    p = primary()
    p["signal_generation_authorized"] = True
    with pytest.raises(ValueError, match="UNTRUSTED_PRIMARY_INTAKE"):
        crosscheck(p, response([event()]), target_day="2026-11-05",
                   observed_at="2026-11-05T14:00:00Z")


def test_free_source_two_calls_never_retries_http_429():
    calls = []
    def denied(req, timeout):
        calls.append(req.full_url)
        raise HTTPError(req.full_url, 429, "rate limited", {}, None)
    rows = capture("2026-11-05", opener=denied)
    assert len(rows) == MAX_CALLS == len(calls) == 2
    assert all(row["provider_status"] == "RATE_LIMITED_NO_RETRY" for row in rows)
    assert all("/123/eventsday.php" in url and "s=Soccer" in url for url in calls)


def test_free_source_counts_only_responses_really_received():
    class Fake:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, n):
            return json.dumps({"events": [event()]}).encode()
    calls = []
    def open_fake(req, timeout):
        calls.append(req.full_url)
        return Fake()
    rows = capture("2026-11-05", opener=open_fake)
    assert len(calls) == 2
    assert all(row["event_count"] == 1 for row in rows)
    assert all(len(row["response_sha256"]) == 64 for row in rows)
    assert all(row["provider_status"] == "PUBLIC_EVENTS_RESPONSE" for row in rows)


def test_unicode_normalization_no_fuzzy_identity():
    assert norm("Atlético Nácional") == "atletico nacional"
    assert norm("Manchester United") != norm("Manchester City")
    assert stamp("2026-11-05T22:30:00") is None
