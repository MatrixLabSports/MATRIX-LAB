from __future__ import annotations

from tools.cor0203_build_identity_crosswalk import build_crosswalk


def static_cut():
    return {
        "ranking_cut": "20260921",
        "source_sha256": "a" * 64,
        "silent_imputation": False,
        "post_cut_data_used": False,
        "players": {
            "D0DW": {
                "canonical_name": "Titouan Droguet",
                "hand": "R",
                "age": 25.268,
                "rank": 84,
                "rank_points": 690,
                "ioc": "FRA",
            },
            "P0HW": {
                "canonical_name": "Dino Prizmic",
                "hand": "R",
                "age": 21.128,
                "rank": 101,
                "rank_points": 603,
                "ioc": "CRO",
            },
        },
    }


def prefeature():
    return {
        "revision": "R800",
        "holdout_id": "H",
        "events": [
            {
                "event_id": "e1",
                "identity_crosswalk_required": True,
                "player_identities": [
                    {
                        "display_name": "Titouan Droguet",
                        "provider_player_id": "api-tennis:player:11",
                        "provider_ranking": {
                            "place": "84",
                            "points": "690",
                            "player": "Titouan Droguet",
                            "country": "France",
                        },
                    },
                    {
                        "display_name": "Dino Prizmic",
                        "provider_player_id": "api-tennis:player:22",
                        "provider_ranking": {
                            "place": "101",
                            "points": "603",
                            "player": "Dino Prizmic",
                            "country": "Croatia",
                        },
                    },
                ],
            }
        ],
    }


def test_exact_rank_points_plus_name_confirmation_passes():
    result = build_crosswalk(prefeature=prefeature(), static_cut=static_cut())

    assert result["status"] == "PASS"
    assert result["passed_events"] == 1
    assert result["blocked_events"] == 0
    assert result["join_by_name_only"] is False
    mappings = {m["provider_player_id"]: m for m in result["mappings"]}
    assert mappings["api-tennis:player:11"]["canonical_source_id"] == "D0DW"
    assert mappings["api-tennis:player:22"]["canonical_source_id"] == "P0HW"
    assert mappings["api-tennis:player:11"]["match_basis"] == "EXACT_RANK_AND_POINTS_PLUS_NAME_CONFIRMATION"


def test_name_match_alone_cannot_pass_wrong_rank_points():
    pre = prefeature()
    pre["events"][0]["player_identities"][0]["provider_ranking"]["place"] = "999"

    result = build_crosswalk(prefeature=pre, static_cut=static_cut())

    assert result["status"] == "ALL_BLOCKED"
    event = result["events"][0]
    assert "STATIC_IDENTITY_NO_MATCH:api-tennis:player:11" in event["blockers"]


def test_exact_rank_points_cannot_override_name_mismatch():
    pre = prefeature()
    pre["events"][0]["player_identities"][0]["display_name"] = "Wrong Person"
    pre["events"][0]["player_identities"][0]["provider_ranking"]["player"] = "Wrong Person"

    result = build_crosswalk(prefeature=pre, static_cut=static_cut())

    assert result["status"] == "ALL_BLOCKED"
    assert "IDENTITY_NAME_CONFIRMATION_FAIL:api-tennis:player:11" in result["events"][0]["blockers"]


def test_nonunique_rank_points_are_blocked():
    cut = static_cut()
    cut["players"]["OTHER"] = {
        "canonical_name": "Other Player",
        "hand": "R",
        "age": 30.0,
        "rank": 84,
        "rank_points": 690,
        "ioc": "USA",
    }

    result = build_crosswalk(prefeature=prefeature(), static_cut=cut)

    assert result["status"] == "ALL_BLOCKED"
    assert "STATIC_IDENTITY_NONUNIQUE:api-tennis:player:11" in result["events"][0]["blockers"]


def test_missing_provider_ranking_blocks_without_name_fallback():
    pre = prefeature()
    pre["events"][0]["player_identities"][0]["provider_ranking"] = None

    result = build_crosswalk(prefeature=pre, static_cut=static_cut())

    assert result["status"] == "ALL_BLOCKED"
    assert "PROVIDER_RANKING_MISSING:api-tennis:player:11" in result["events"][0]["blockers"]


def test_events_are_isolated_when_one_crosswalk_fails():
    pre = prefeature()
    second = {
        "event_id": "e2",
        "identity_crosswalk_required": True,
        "player_identities": [
            {
                "display_name": "Titouan Droguet",
                "provider_player_id": "api-tennis:player:11",
                "provider_ranking": {
                    "place": "84",
                    "points": "690",
                    "player": "Titouan Droguet",
                },
            },
            {
                "display_name": "Unknown Player",
                "provider_player_id": "api-tennis:player:33",
                "provider_ranking": {
                    "place": "777",
                    "points": "10",
                    "player": "Unknown Player",
                },
            },
        ],
    }
    pre["events"].append(second)

    result = build_crosswalk(prefeature=pre, static_cut=static_cut())

    assert result["status"] == "PASS_WITH_BLOCKERS"
    by_event = {row["event_id"]: row for row in result["events"]}
    assert by_event["e1"]["status"] == "PASS"
    assert by_event["e2"]["status"] == "BLOCKED"
