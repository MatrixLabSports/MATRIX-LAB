from __future__ import annotations

from tools.cor0203_world_inventory_discovery import derive_world_cor_discovery


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
        "world_inventory_complete": True,
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
