from datetime import date

from tools.cor0203_historical_identity_reconcile import reconcile_historical_identity
from tools.cor0203_api_tennis_discovery import CHALLENGER_MEN_SINGLES_NAME


class FakeClient:
    def __init__(self, payload_by_date):
        self.payload_by_date = payload_by_date
        self.request_count = 0

    def fixtures(self, start: date, stop: date):
        assert start == stop
        self.request_count += 1
        return self.payload_by_date[start.isoformat()]


def queue():
    return {
        "items": [{
            "event_id": "E1",
            "status": "IDENTITY_MAPPING_REQUIRED",
            "alphabetical_player_a": "Harold Mayot",
            "alphabetical_player_b": "Murphy Cassone",
            "event_start_utc": "2026-09-26T12:00:00+00:00",
        }]
    }


def fixture(event_key="55", p1="Harold Mayot", p2="Murphy Cassone"):
    return {
        "event_key": event_key,
        "event_date": "2026-09-26",
        "event_type_type": CHALLENGER_MEN_SINGLES_NAME,
        "event_first_player": p1,
        "event_second_player": p2,
        "first_player_key": "10",
        "second_player_key": "20",
    }


def test_exact_unique_pair_reconciles_without_fuzzy_matching():
    client = FakeClient({"2026-09-26": {"result": [fixture(p1="Murphy Cassone", p2="Harold Mayot")]}})
    result = reconcile_historical_identity(queue=queue(), client=client)
    assert result["reconciled_count"] == 1
    assert result["blocked_count"] == 0
    row = result["reconciled"][0]
    assert row["provider_match_key"] == "55"
    assert row["canonical_source_event_id"] == "api-tennis:event:55"
    assert row["match_rule"] == "EXACT_DATE_EXACT_UNORDERED_PLAYER_PAIR_UNIQUE"
    assert result["automatic_fuzzy_matching"] is False
    assert client.request_count == 1


def test_zero_exact_matches_stays_blocked():
    client = FakeClient({"2026-09-26": {"result": [fixture(p1="Other", p2="Players")]}})
    result = reconcile_historical_identity(queue=queue(), client=client)
    assert result["reconciled_count"] == 0
    assert result["blocked"][0]["reason"] == "HISTORICAL_IDENTITY_NO_EXACT_UNIQUE_MATCH"


def test_multiple_exact_matches_stay_blocked_as_ambiguous():
    rows = [fixture(event_key="55"), fixture(event_key="56")]
    client = FakeClient({"2026-09-26": {"result": rows}})
    result = reconcile_historical_identity(queue=queue(), client=client)
    assert result["reconciled_count"] == 0
    assert result["blocked"][0]["reason"] == "HISTORICAL_IDENTITY_AMBIGUOUS_EXACT_MATCH"
    assert result["blocked"][0]["exact_candidate_count"] == 2


def test_one_provider_call_per_date_for_multiple_events():
    q = queue()
    q["items"].append({
        "event_id": "E2",
        "status": "IDENTITY_MAPPING_REQUIRED",
        "alphabetical_player_a": "Alpha",
        "alphabetical_player_b": "Beta",
        "event_start_utc": "2026-09-26T18:00:00+00:00",
    })
    rows = [
        fixture(),
        {
            "event_key": "57",
            "event_date": "2026-09-26",
            "event_type_type": CHALLENGER_MEN_SINGLES_NAME,
            "event_first_player": "Beta",
            "event_second_player": "Alpha",
            "first_player_key": "30",
            "second_player_key": "40",
        },
    ]
    client = FakeClient({"2026-09-26": {"result": rows}})
    result = reconcile_historical_identity(queue=q, client=client)
    assert result["reconciled_count"] == 2
    assert client.request_count == 1
