import json

import pytest

from tools.api_football_build_prematch_queue import build_prematch_queue


def registry():
    return {
        "provider": "api_football",
        "future_only": True,
        "captured_at_utc": "2026-09-28T04:43:53+00:00",
        "target_date": "2026-09-28",
        "protections": {
            "outcomes_used": False,
            "odds_used": False,
            "real_money": "BLOCKED",
        },
        "events": [
            {
                "provider_fixture_id": "100",
                "provider_league_id": "39",
                "provider_home_team_id": "40",
                "provider_away_team_id": "41",
                "event_start_utc": "2026-09-28T18:00:00+00:00",
                "competition": "Premier League",
                "country": "England",
                "season": 2026,
                "round": "Regular Season - 7",
                "home_team": "Home FC",
                "away_team": "Away FC",
                "venue_id": "1",
                "venue_name": "Stadium",
            },
            {
                "provider_fixture_id": "101",
                "provider_league_id": "39",
                "provider_home_team_id": "40",
                "provider_away_team_id": "42",
                "event_start_utc": "2026-09-28T20:00:00+00:00",
                "competition": "Premier League",
                "country": "England",
                "season": 2026,
                "round": "Regular Season - 7",
                "home_team": "Home FC",
                "away_team": "Third FC",
                "venue_id": "1",
                "venue_name": "Stadium",
            },
        ],
    }


def manifest():
    return {
        "response_sha256": "a" * 64,
    }


def test_builds_world_inventory_benchmark_and_unique_team_queue():
    benchmark, queue, inventory = build_prematch_queue(
        registry=registry(),
        manifest=manifest(),
    )

    assert benchmark["benchmark_status"] == "HISTORY_PENDING"
    assert benchmark["provider"] == "api_football"
    assert len(benchmark["fixtures"]) == 2
    assert len(benchmark["unresolved_targets"]) == 2
    assert benchmark["money_decisions_enabled"] is False
    assert benchmark["real_money"] == "BLOCKED"

    first = benchmark["fixtures"]["api_football:fixture:100"]
    assert first["pre_match_frozen"] is True
    assert first["home"]["id"] == "40"
    assert first["away"]["id"] == "41"
    assert first["source_payload_sha256"] == "a" * 64

    assert queue["unique_teams"] == 3
    assert queue["target_fixtures"] == 2
    assert queue["network_calls_performed"] == 0
    home = next(item for item in queue["items"] if item["provider_team_id"] == "40")
    assert sorted(home["target_fixture_ids"]) == ["100", "101"]
    assert home["minimum_history_matches"] == 5
    assert home["preferred_history_matches"] == 20
    assert queue["protections"]["history_must_precede_target"] is True
    assert queue["protections"]["real_money"] == "BLOCKED"

    assert inventory["future_fixture_count"] == 2
    assert inventory["unique_team_count"] == 3
    assert inventory["competition_count"] == 1
    assert inventory["country_count"] == 1
    assert inventory["competition_counts"] == {"Premier League": 2}
    assert len(inventory["benchmark_sha256"]) == 64
    assert len(inventory["history_queue_sha256"]) == 64


def test_fails_closed_if_outcomes_are_marked_used():
    payload = registry()
    payload["protections"]["outcomes_used"] = True

    with pytest.raises(ValueError, match="OUTCOMES_MUST_BE_FALSE"):
        build_prematch_queue(registry=payload, manifest=manifest())


def test_fails_closed_if_fixture_identity_is_incomplete():
    payload = registry()
    payload["events"][0]["provider_home_team_id"] = ""

    with pytest.raises(ValueError, match="EVENT_IDENTITY_INCOMPLETE"):
        build_prematch_queue(registry=payload, manifest=manifest())


def test_rejects_duplicate_fixture_ids():
    payload = registry()
    duplicate = dict(payload["events"][0])
    duplicate["provider_away_team_id"] = "99"
    payload["events"].append(duplicate)

    with pytest.raises(ValueError, match="DUPLICATE_FIXTURE_ID:100"):
        build_prematch_queue(registry=payload, manifest=manifest())
