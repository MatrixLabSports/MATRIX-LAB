from __future__ import annotations

from tools.cor0203_world_inventory_discovery import (
    apply_certified_exact_cut_rank_overrides,
    derive_world_cor_discovery,
)


def _world_event(
    match_id,
    *,
    tournament_id,
    start,
    surface="Hard",
    p1=11,
    p2=22,
):
    return {
        "source_event_id": f"rapidapi-tennis:atp:match:{match_id}",
        "provider_channel": "ATP",
        "circuit_family": "ATP",
        "circuit_detail": "ATP_CHALLENGER",
        "match_id": str(match_id),
        "tournament_id": str(tournament_id),
        "tournament_name": "Example Challenger",
        "tier": "",
        "surface": surface,
        "round": "Quarter-Final",
        "event_format": "SINGLES",
        "player1": {"id": str(p1), "name": f"P{p1}", "country": "COL"},
        "player2": {"id": str(p2), "name": f"P{p2}", "country": "ESP"},
        "event_start_utc": start,
        "model_derivation": {
            "lane": "COR02_COR03_ATP_CHALLENGER_HARD",
            "domain_candidate": True,
            "blockers": [],
        },
    }


class FakeClient:
    def __init__(self):
        self.request_count = 0
        self.tournament_calls = []
        self.ranking_calls = []

    def tournament_info(self, tournament_id):
        self.request_count += 1
        self.tournament_calls.append(str(tournament_id))
        surface = "I.hard" if str(tournament_id) == "501" else "Hard"
        return {
            "id": int(tournament_id),
            "name": "Example Challenger",
            "tier": "Challenger 75",
            "rankId": 1,
            "court": {"name": surface},
        }

    def ranking_snapshot(self, *, ranking_date, wanted_player_ids):
        self.request_count += 1
        self.ranking_calls.append(
            (ranking_date.isoformat(), sorted(wanted_player_ids))
        )
        return {
            str(pid): {
                "place": str(100 + i),
                "points": str(500 - i),
                "player": f"P{pid}",
                "country": "COL",
                "snapshot_date": ranking_date.isoformat(),
            }
            for i, pid in enumerate(sorted(wanted_player_ids))
        }


def _world():
    return {
        "schema": "MATRIX_TENNIS_WORLD_INVENTORY_V2",
        "status": "PASS",
        "provider_inventory_complete": True,
        "world_inventory_complete": False,
        "world_complete_gate": "REQUIRES_MULTI_SOURCE_RECONCILIATION",
        "target_date_bogota": "2026-10-02",
        "world_calendar_inventory_count": 5,
        "events": [
            _world_event(
                1001,
                tournament_id=500,
                start="2026-10-02T15:00:00+00:00",
                p1=11,
                p2=22,
            ),
            _world_event(
                1002,
                tournament_id=500,
                start="2026-10-02T06:00:00+00:00",
                p1=33,
                p2=44,
            ),
            _world_event(
                1003,
                tournament_id=501,
                start="2026-10-02T17:00:00+00:00",
                surface="I.hard",
                p1=55,
                p2=66,
            ),
            {
                "source_event_id": "rapidapi-tennis:wta:match:2001",
                "circuit_detail": "WTA_MAIN_OR_OTHER",
                "event_format": "SINGLES",
                "model_derivation": {
                    "lane": "COR02_COR03_ATP_CHALLENGER_HARD",
                    "domain_candidate": False,
                },
            },
            {
                "source_event_id": "rapidapi-tennis:atp:match:3001",
                "circuit_detail": "ITF_MEN",
                "event_format": "SINGLES",
                "model_derivation": {
                    "lane": "COR02_COR03_ATP_CHALLENGER_HARD",
                    "domain_candidate": False,
                },
            },
        ],
    }


def test_world_derived_discovery_enriches_only_cor_domain_candidates():
    client = FakeClient()
    result = derive_world_cor_discovery(
        world_inventory=_world(),
        client=client,
        as_of_utc="2026-10-02T07:00:00+00:00",
    )

    assert result["status"] == "DISCOVERY_COMPLETED"
    assert result["source_mode"] == "WORLD_INVENTORY_DERIVED"
    assert result["world_domain_candidates_input"] == 3
    assert result["eligible_input_events"] == 2
    assert {x["event_id"] for x in result["eligible_candidates"]} == {
        "rapidapi-tennis:atp:match:1001",
        "rapidapi-tennis:atp:match:1003",
    }
    rejected = {str(x["match_id"]): x for x in result["provider_rejected"]}
    assert "EVENT_NOT_FUTURE" in rejected["1002"]["blockers"]
    assert result["tournaments_requested"] == 2
    assert result["tournaments_enriched"] == 2
    assert result["ranking_players_requested"] == 6
    assert result["ranking_players_found"] == 6
    assert result["automatic_model_feed"] is False
    assert result["governed_preregistration_required"] is True
    assert result["metrics_opened"] is False
    assert result["outcomes_read"] == 0
    assert result["real_money"] == "BLOCKED"


def test_world_derived_discovery_accepts_indoor_hard_as_hard_model_surface():
    result = derive_world_cor_discovery(
        world_inventory=_world(),
        client=FakeClient(),
        as_of_utc="2026-10-02T07:00:00+00:00",
    )
    indoor = next(
        row
        for row in result["eligible_candidates"]
        if row["event_id"] == "rapidapi-tennis:atp:match:1003"
    )
    assert indoor["surface"] == "Hard"


def test_world_derived_discovery_fails_closed_on_incomplete_world_inventory():
    world = _world()
    world["status"] = "PARTIAL"
    world["world_inventory_complete"] = False
    result = derive_world_cor_discovery(
        world_inventory=world,
        client=FakeClient(),
        as_of_utc="2026-10-02T07:00:00+00:00",
    )
    assert result["status"] == "WORLD_INVENTORY_NOT_COMPLETE"
    assert result["eligible_candidates"] == []
    assert result["network_calls"] == 0
    assert result["real_money"] == "BLOCKED"


def test_world_derived_discovery_does_not_promote_wta_or_itf():
    result = derive_world_cor_discovery(
        world_inventory=_world(),
        client=FakeClient(),
        as_of_utc="2026-10-02T07:00:00+00:00",
    )
    assert all(
        row["event_id"].startswith("rapidapi-tennis:atp:match:")
        for row in result["eligible_candidates"]
    )
    assert result["world_domain_candidates_input"] == 3


def test_world_derived_identity_is_not_ambiguous_when_wta_reuses_numeric_match_id():
    world = _world()
    world["events"].append({
        "source_event_id": "rapidapi-tennis:wta:match:1001",
        "provider_channel": "WTA",
        "circuit_family": "ITF",
        "circuit_detail": "ITF_WOMEN",
        "match_id": "1001",
        "tournament_id": "999",
        "tournament_name": "W35 Collision Test",
        "surface": "Hard",
        "round": "Quarter-Final",
        "event_format": "SINGLES",
        "player1": {"id": "901", "name": "Woman A", "country": "ESP"},
        "player2": {"id": "902", "name": "Woman B", "country": "ARG"},
        "event_start_utc": "2026-10-02T16:00:00+00:00",
        "model_derivation": {
            "lane": "COR02_COR03_ATP_CHALLENGER_HARD",
            "domain_candidate": False,
            "blockers": ["CIRCUIT_OUTSIDE_COR0203_ATP_CHALLENGER"],
        },
    })
    world["world_calendar_inventory_count"] += 1

    result = derive_world_cor_discovery(
        world_inventory=world,
        client=FakeClient(),
        as_of_utc="2026-10-02T07:00:00+00:00",
    )

    candidate = next(
        row
        for row in result["eligible_candidates"]
        if row["event_id"] == "rapidapi-tennis:atp:match:1001"
    )
    assert candidate["canonical_source_event_id"] == (
        "rapidapi-tennis:atp:match:1001"
    )
    assert candidate["provider_channel"] == "ATP"
    assert candidate["players"][0]["name"] == "P11"
    assert candidate["players"][1]["name"] == "P22"
    assert all(
        not row["event_id"].startswith("rapidapi-tennis:wta:")
        for row in result["eligible_candidates"]
    )


def test_world_derived_discovery_resolves_same_atp_match_id_by_physical_identity():
    world = _world()
    first = _world_event(
        7777,
        tournament_id=500,
        start="2026-10-02T18:00:00+00:00",
        p1=101,
        p2=102,
    )
    second = _world_event(
        7777,
        tournament_id=500,
        start="2026-10-02T20:00:00+00:00",
        p1=103,
        p2=104,
    )
    first["stable_physical_identity_key"] = "a" * 64
    second["stable_physical_identity_key"] = "b" * 64
    world["events"].extend([first, second])
    world["world_calendar_inventory_count"] += 2

    result = derive_world_cor_discovery(
        world_inventory=world,
        client=FakeClient(),
        as_of_utc="2026-10-02T07:00:00+00:00",
    )

    collision_rows = [
        row for row in result["eligible_candidates"]
        if str(row.get("provider_source_event_id") or "").endswith(":7777")
    ]
    assert len(collision_rows) == 2
    assert len({row["event_id"] for row in collision_rows}) == 2
    assert all(
        row["event_id"].startswith("rapidapi-tennis:physical:")
        for row in collision_rows
    )
    assert {row["world_stable_physical_identity_key"] for row in collision_rows} == {
        "a" * 64,
        "b" * 64,
    }
    assert all(row["source_id_collision_resolved"] is True for row in collision_rows)
    assert result["world_source_event_id_collision_count"] >= 1
    assert result["world_identity_binding_rejection_count"] == 0


def test_certified_atp_exact_cut_override_fills_only_missing_numeric_id(tmp_path):
    import json

    path = tmp_path / "rank_overrides.json"
    path.write_text(json.dumps({
        "schema": "MATRIX_COR0203_CERTIFIED_EXACT_CUT_RANK_OVERRIDES_V1",
        "ranking_cut": "2026-09-21",
        "entries": [{
            "provider_player_id": "rapidapi-tennis:player:60951",
            "provider_numeric_player_id": "60951",
            "player": "Patrick Maloney",
            "country": "USA",
            "place": "999",
            "points": "19",
            "snapshot_date": "2026-09-21",
            "source_authority": "ATP_OFFICIAL_RANKINGS_BROWSER_EXACT_DATE",
            "source_url": "https://www.atptour.com/en/rankings/singles?dateWeek=2026-09-21",
            "verified_date_filter_value": "2026.09.21",
            "protections": {
                "overwrite_existing_provider_rank": False,
                "join_by_name_only": False,
                "post_cut_competitive_data_used": False,
                "outcomes_used": False,
                "odds_used": False
            }
        }]
    }), encoding="utf-8")

    merged, audit = apply_certified_exact_cut_rank_overrides(
        rankings={"40609": {
            "place": "77", "points": "763", "player": "Jenson Brooksby",
            "country": "USA", "snapshot_date": "2026-09-21"
        }},
        wanted_player_ids={"40609", "60951"},
        fixture_identity_by_player={
            "40609": {"name": "Jenson Brooksby", "country": "USA"},
            "60951": {"name": "Patrick Maloney", "country": "USA"},
        },
        path=path,
    )

    assert merged["60951"]["place"] == "999"
    assert merged["60951"]["points"] == "19"
    assert merged["60951"]["ranking_source"] == (
        "ATP_OFFICIAL_BROWSER_EXACT_CUT_CERTIFIED_OVERRIDE"
    )
    assert audit["applied_count"] == 1
    assert audit["overwrote_existing_provider_rank"] is False
    assert audit["join_by_name_only"] is False


def test_certified_exact_cut_override_never_overwrites_provider_rank(tmp_path):
    import json

    path = tmp_path / "rank_overrides.json"
    path.write_text(json.dumps({
        "schema": "MATRIX_COR0203_CERTIFIED_EXACT_CUT_RANK_OVERRIDES_V1",
        "ranking_cut": "2026-09-21",
        "entries": [{
            "provider_numeric_player_id": "60951",
            "player": "Patrick Maloney",
            "country": "USA",
            "place": "999",
            "points": "19",
            "snapshot_date": "2026-09-21",
            "source_authority": "ATP_OFFICIAL_RANKINGS_BROWSER_EXACT_DATE",
            "source_url": "https://www.atptour.com/en/rankings/singles?dateWeek=2026-09-21",
            "verified_date_filter_value": "2026.09.21",
            "protections": {
                "overwrite_existing_provider_rank": False,
                "join_by_name_only": False,
                "post_cut_competitive_data_used": False,
                "outcomes_used": False,
                "odds_used": False
            }
        }]
    }), encoding="utf-8")

    provider = {
        "60951": {
            "place": "998", "points": "20", "player": "Patrick Maloney",
            "country": "USA", "snapshot_date": "2026-09-21"
        }
    }
    merged, audit = apply_certified_exact_cut_rank_overrides(
        rankings=provider,
        wanted_player_ids={"60951"},
        fixture_identity_by_player={
            "60951": {"name": "Patrick Maloney", "country": "USA"},
        },
        path=path,
    )

    assert merged["60951"]["place"] == "998"
    assert audit["applied_count"] == 0
    assert audit["skipped_existing_provider_rank"] == ["60951"]
