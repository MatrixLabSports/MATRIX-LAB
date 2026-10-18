from __future__ import annotations

import json
from datetime import date

import pytest

from tools.cor0203_rapidapi_tennis_discovery import (
    RAPIDAPI_HOST,
    RapidApiTennisClient,
    RapidApiTennisDiscoveryError,
    build_discovery_registry,
    fetch_discovery,
    recover_exact_rankings_via_profile_alias,
)


class FakeResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RecordingOpener:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []

    def __call__(self, request, timeout=20.0):
        self.requests.append(request)
        return FakeResponse(self.payloads.pop(0))


def fixture(
    *,
    match_id=1001,
    tournament_id=500,
    p1=11,
    p2=22,
    start="2026-09-27T12:00:00.000Z",
):
    return {
        "id": match_id,
        "matchId": match_id,
        "date": start,
        "startTime": start,
        "player1Id": p1,
        "player2Id": p2,
        "player1": {"id": p1, "name": "Player A", "countryAcr": "USA"},
        "player2": {"id": p2, "name": "Player B", "countryAcr": "FRA"},
        "tournamentId": tournament_id,
        "roundId": 4,
        "round": {"name": "Quarter-Final"},
    }


def tournament(*, tier="Challenger 75", surface="Hard", rank_id=1):
    return {
        "id": 500,
        "name": "Test Challenger",
        "tier": tier,
        "rankId": rank_id,
        "court": {"id": 1, "name": surface},
    }


def rankings():
    return {
        "11": {
            "place": "100",
            "points": "600",
            "player": "Player A",
            "country": "USA",
            "snapshot_date": "2026-09-21",
        },
        "22": {
            "place": "120",
            "points": "500",
            "player": "Player B",
            "country": "FRA",
            "snapshot_date": "2026-09-21",
        },
    }


def test_client_keeps_secret_in_header_not_url():
    opener = RecordingOpener([
        {"data": [], "pageNo": 1, "pageSize": 0, "hasNextPage": False}
    ])
    client = RapidApiTennisClient("secret-rapid-key", opener=opener)

    client.fixtures(date(2026, 9, 27), date(2026, 9, 27))

    request = opener.requests[0]
    assert "secret-rapid-key" not in request.full_url
    headers = {k.lower(): v for k, v in request.header_items()}
    assert headers["x-rapidapi-key"] == "secret-rapid-key"
    assert headers["x-rapidapi-host"] == RAPIDAPI_HOST
    assert "PlayerGroup%3Asingles%3BTourRank%3A1" in request.full_url


def test_hard_challenger_future_match_with_dated_ranking_is_eligible():
    result = build_discovery_registry(
        fixture_payload={"data": [fixture()]},
        tournament_info={"500": tournament()},
        ranking_by_player=rankings(),
        as_of_utc="2026-09-27T00:00:00+00:00",
    )

    assert result["world_registry"]["cor0203_eligible_events"] == 1
    row = result["world_registry"]["rows"][0]
    assert row["event_id"] == "rapidapi-tennis:match:1001"
    assert row["player1_id"] == "rapidapi-tennis:player:11"
    assert row["player2_id"] == "rapidapi-tennis:player:22"
    assert row["surface"] == "Hard"
    assert row["cor0203_eligible"] is True
    assert len(row["source_snapshot_sha256"]) == 64
    candidate = result["eligible_candidates"][0]
    assert candidate["players"][0]["provider_ranking"]["place"] == "100"


def test_rank_one_itf_is_not_silently_treated_as_challenger():
    result = build_discovery_registry(
        fixture_payload={"data": [fixture()]},
        tournament_info={"500": tournament(tier="ITF M25")},
        ranking_by_player=rankings(),
        as_of_utc="2026-09-27T00:00:00+00:00",
    )

    assert result["world_registry"]["cor0203_eligible_events"] == 0
    assert (
        "TOURNAMENT_NOT_PROVEN_CHALLENGER"
        in result["provider_rejected"][0]["blockers"]
    )


def test_non_hard_challenger_is_rejected():
    result = build_discovery_registry(
        fixture_payload={"data": [fixture()]},
        tournament_info={"500": tournament(surface="Clay")},
        ranking_by_player=rankings(),
        as_of_utc="2026-09-27T00:00:00+00:00",
    )

    assert result["world_registry"]["cor0203_eligible_events"] == 0
    assert "SURFACE_OUT_OF_DOMAIN" in result["provider_rejected"][0]["blockers"]


def test_indoor_hard_challenger_is_normalized_into_hard_model_domain():
    result = build_discovery_registry(
        fixture_payload={"data": [fixture()]},
        tournament_info={"500": tournament(surface="I.hard")},
        ranking_by_player=rankings(),
        as_of_utc="2026-09-27T00:00:00+00:00",
    )

    assert result["world_registry"]["cor0203_eligible_events"] == 1
    assert result["eligible_candidates"][0]["surface"] == "Hard"


def test_missing_ranking_cut_blocks_event():
    values = rankings()
    del values["22"]
    result = build_discovery_registry(
        fixture_payload={"data": [fixture()]},
        tournament_info={"500": tournament()},
        ranking_by_player=values,
        as_of_utc="2026-09-27T00:00:00+00:00",
    )

    assert result["world_registry"]["cor0203_eligible_events"] == 0
    assert (
        "RANKING_CUT_MISSING_PLAYER2"
        in result["provider_rejected"][0]["blockers"]
    )


def test_started_event_is_rejected():
    result = build_discovery_registry(
        fixture_payload={
            "data": [fixture(start="2026-09-26T12:00:00.000Z")]
        },
        tournament_info={"500": tournament()},
        ranking_by_player=rankings(),
        as_of_utc="2026-09-27T00:00:00+00:00",
    )

    assert result["world_registry"]["cor0203_eligible_events"] == 0
    assert "EVENT_NOT_FUTURE" in result["provider_rejected"][0]["blockers"]


def test_fixture_range_is_bounded():
    client = RapidApiTennisClient("k", opener=RecordingOpener([]))
    with pytest.raises(ValueError, match="DISCOVERY_RANGE_EXCEEDS_4_DAYS"):
        client.fixtures(date(2026, 9, 1), date(2026, 9, 6))


def test_client_rejects_non_ascii_masked_secret_before_network():
    with pytest.raises(
        RapidApiTennisDiscoveryError,
        match="RAPIDAPI_TENNIS_KEY_MUST_BE_ASCII",
    ):
        RapidApiTennisClient("•" * 50, opener=RecordingOpener([]))


def test_successful_provider_response_counts_verified_response():
    opener = RecordingOpener([
        {"data": [], "pageNo": 1, "pageSize": 0, "hasNextPage": False}
    ])
    client = RapidApiTennisClient("ascii-key", opener=opener)

    client.fixtures(date(2026, 9, 27), date(2026, 9, 27))

    assert client.request_attempt_count == 1
    assert client.request_count == 1



def test_profile_verified_alias_can_recover_exact_cut_ranking_for_changed_provider_id():
    class AliasClient:
        def __init__(self):
            self.request_count = 0

        def ranking_snapshot_rows(self, *, ranking_date):
            self.request_count += 1
            return [{
                "position": 120,
                "pts": 500,
                "player": {
                    "id": 999,
                    "name": "Player B",
                    "countryAcr": "FRA",
                },
            }]

        def player_profile(self, *, player_id):
            self.request_count += 1
            if str(player_id) == "22":
                return {"data": {
                    "id": 22,
                    "name": "Player B",
                    "birthday": "2001-02-03T00:00:00Z",
                    "countryAcr": "FRA",
                    "information": {"plays": "Right-Handed"},
                    "currentRank": 111,
                }}
            return {"data": {
                "id": 999,
                "name": "Player B",
                "birthday": "2001-02-03T00:00:00Z",
                "countryAcr": "FRA",
                "information": {"plays": "Right-Handed"},
                "currentRank": 120,
            }}

    merged, audit = recover_exact_rankings_via_profile_alias(
        client=AliasClient(),
        ranking_date=date(2026, 9, 21),
        wanted_player_ids={"22"},
        existing_rankings={},
        fixture_identity_by_player={
            "22": {"name": "Player B", "country": "FRA"},
        },
    )

    assert audit["recovered_count"] == 1
    assert audit["join_by_name_only"] is False
    assert audit["current_rank_used"] is False
    row = merged["22"]
    assert row["place"] == "120"
    assert row["points"] == "500"
    assert row["snapshot_date"] == "2026-09-21"
    assert row["ranking_source"] == "EXACT_CUT_RANKING_PROFILE_ALIAS"
    assert row["ranking_identity_alias"]["ranking_player_id"] == "999"


def test_profile_alias_fails_closed_when_dob_does_not_match():
    class AliasClient:
        def ranking_snapshot_rows(self, *, ranking_date):
            return [{
                "position": 120,
                "pts": 500,
                "player": {
                    "id": 999,
                    "name": "Player B",
                    "countryAcr": "FRA",
                },
            }]

        def player_profile(self, *, player_id):
            if str(player_id) == "22":
                birthday = "2001-02-03T00:00:00Z"
            else:
                birthday = "2002-02-03T00:00:00Z"
            return {"data": {
                "id": int(player_id),
                "name": "Player B",
                "birthday": birthday,
                "countryAcr": "FRA",
                "information": {"plays": "Right-Handed"},
            }}

    merged, audit = recover_exact_rankings_via_profile_alias(
        client=AliasClient(),
        ranking_date=date(2026, 9, 21),
        wanted_player_ids={"22"},
        existing_rankings={},
        fixture_identity_by_player={
            "22": {"name": "Player B", "country": "FRA"},
        },
    )

    assert "22" not in merged
    assert audit["recovered_count"] == 0
    assert audit["blocked"][0]["reason"] == "RANKING_PROFILE_ALIAS_NOT_FOUND"


def test_fetch_discovery_recovers_missing_snapshot_rank_from_exact_player_history():
    class HistoryFallbackClient:
        def __init__(self):
            self.request_count = 0
            self.history_calls = []

        def fixtures(self, start, stop):
            return {
                "data": [fixture(start="2026-09-28T12:00:00.000Z")],
                "pageNo": 1,
                "pageSize": 1,
                "hasNextPage": False,
            }

        def tournament_info(self, tournament_id):
            return tournament()

        def ranking_snapshot(self, *, ranking_date, wanted_player_ids):
            values = rankings()
            del values["22"]
            return values

        def ranking_history(self, *, player_id, months=3):
            self.request_count += 1
            self.history_calls.append((str(player_id), int(months)))
            return {
                "history": [
                    {"date": "2026-09-14", "position": 130, "pts": 450},
                    {"date": "2026-09-21", "position": 120, "pts": 500},
                ]
            }

    client = HistoryFallbackClient()
    result = fetch_discovery(
        client=client,
        start=date(2026, 9, 28),
        stop=date(2026, 9, 28),
        as_of_utc="2026-09-28T03:00:00+00:00",
    )

    assert result["eligible_input_events"] == 1
    assert result["ranking_history_recovered_count"] == 1
    assert result["ranking_history_recovery"]["current_rank_used"] is False
    assert result["ranking_history_recovery"]["post_cut_competitive_data_used"] is False
    assert client.history_calls == [("22", 3)]
    recovered = result["eligible_candidates"][0]["players"][1]["provider_ranking"]
    assert recovered["place"] == "120"
    assert recovered["points"] == "500"
    assert recovered["snapshot_date"] == "2026-09-21"
    assert recovered["ranking_source"] == "PLAYER_RANKING_HISTORY_EXACT_CUT"


def test_fetch_discovery_does_not_use_non_cut_ranking_history():
    class WrongDateHistoryClient:
        def __init__(self):
            self.request_count = 0

        def fixtures(self, start, stop):
            return {
                "data": [fixture(start="2026-09-28T12:00:00.000Z")],
                "pageNo": 1,
                "pageSize": 1,
                "hasNextPage": False,
            }

        def tournament_info(self, tournament_id):
            return tournament()

        def ranking_snapshot(self, *, ranking_date, wanted_player_ids):
            values = rankings()
            del values["22"]
            return values

        def ranking_history(self, *, player_id, months=3):
            self.request_count += 1
            return {
                "history": [
                    {"date": "2026-09-28", "position": 110, "pts": 550},
                ]
            }

    result = fetch_discovery(
        client=WrongDateHistoryClient(),
        start=date(2026, 9, 28),
        stop=date(2026, 9, 28),
        as_of_utc="2026-09-28T03:00:00+00:00",
    )

    assert result["eligible_input_events"] == 0
    assert result["ranking_history_recovered_count"] == 0
    assert result["ranking_history_recovery"]["blocked"][0]["reason"] == (
        "EXACT_RANKING_CUT_NOT_FOUND"
    )
    assert "RANKING_CUT_MISSING_PLAYER2" in (
        result["provider_rejected"][0]["blockers"]
    )


def test_fetch_discovery_reuses_embedded_tournament_metadata_beyond_fallback_cap():
    class EmbeddedClient:
        def __init__(self):
            self.request_count = 0
            self.tournament_info_calls = []

        def fixtures(self, start, stop):
            rows = []
            for i in range(15):
                tid = 700 + i
                p1 = 1000 + i * 2
                p2 = p1 + 1
                row = fixture(
                    match_id=2000 + i,
                    tournament_id=tid,
                    p1=p1,
                    p2=p2,
                    start="2026-09-28T12:00:00.000Z",
                )
                row["player1"]["name"] = f"Player {p1}"
                row["player2"]["name"] = f"Player {p2}"
                row["tournament"] = {
                    "id": tid,
                    "name": f"Embedded Challenger {i}",
                    "tier": "Challenger 75",
                    "rankId": 1,
                    "court": {"id": 1, "name": "Hard"},
                }
                rows.append(row)
            return {
                "data": rows,
                "pageNo": 1,
                "pageSize": len(rows),
                "hasNextPage": False,
            }

        def tournament_info(self, tournament_id):
            self.tournament_info_calls.append(tournament_id)
            raise AssertionError("embedded tournament metadata should avoid fallback")

        def ranking_snapshot(self, *, ranking_date, wanted_player_ids):
            return {
                str(pid): {
                    "place": str(100 + n),
                    "points": str(1000 - n),
                    "player": f"Player {pid}",
                    "country": "USA",
                    "snapshot_date": ranking_date.isoformat(),
                }
                for n, pid in enumerate(sorted(wanted_player_ids))
            }

    client = EmbeddedClient()
    result = fetch_discovery(
        client=client,
        start=date(2026, 9, 28),
        stop=date(2026, 9, 29),
        as_of_utc="2026-09-28T03:00:00+00:00",
    )

    assert result["eligible_input_events"] == 15
    assert result["tournaments_queried"] == 15
    assert result["tournaments_embedded"] == 15
    assert result["tournaments_network_queried"] == 0
    assert result["tournaments_unresolved"] == 0
    assert client.tournament_info_calls == []


def test_fetch_discovery_uses_bounded_fallback_when_fixture_lacks_tournament_metadata():
    class FallbackClient:
        def __init__(self):
            self.request_count = 0
            self.tournament_info_calls = []

        def fixtures(self, start, stop):
            return {
                "data": [fixture(start="2026-09-28T12:00:00.000Z")],
                "pageNo": 1,
                "pageSize": 1,
                "hasNextPage": False,
            }

        def tournament_info(self, tournament_id):
            self.tournament_info_calls.append(tournament_id)
            return tournament()

        def ranking_snapshot(self, *, ranking_date, wanted_player_ids):
            return rankings()

    client = FallbackClient()
    result = fetch_discovery(
        client=client,
        start=date(2026, 9, 28),
        stop=date(2026, 9, 29),
        as_of_utc="2026-09-28T03:00:00+00:00",
    )

    assert result["eligible_input_events"] == 1
    assert result["tournaments_embedded"] == 0
    assert result["tournaments_network_queried"] == 1
    assert result["tournaments_unresolved"] == 0
    assert client.tournament_info_calls == ["500"]
