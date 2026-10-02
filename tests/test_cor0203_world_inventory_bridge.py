from tools.cor0203_world_inventory_bridge import build_bridge


def _world():
    return {
        "status": "PASS",
        "world_inventory_complete": True,
        "target_date_bogota": "2026-10-02",
        "world_calendar_inventory_count": 100,
        "derived_lanes": {
            "COR02_COR03_ATP_CHALLENGER_HARD": {
                "source_event_ids": [
                    "rapidapi-tennis:atp:match:100",
                    "rapidapi-tennis:atp:match:200",
                    "rapidapi-tennis:atp:match:300",
                ]
            }
        },
    }


def test_bridge_traces_world_candidates_to_prereg_and_rejections():
    report = build_bridge(
        world_inventory=_world(),
        cor_discovery={
            "eligible_candidates": [
                {
                    "event_id": "rapidapi-tennis:match:100",
                    "canonical_source_event_id": "rapidapi-tennis:match:100",
                },
                {
                    "event_id": "rapidapi-tennis:match:400",
                    "canonical_source_event_id": "rapidapi-tennis:match:400",
                },
            ],
            "provider_rejected": [
                {
                    "match_id": "200",
                    "blockers": ["EVENT_NOT_FUTURE"],
                },
            ],
        },
        prereg={
            "event_ids": ["COR0203-RAPIDAPI-TENNIS-100"],
            "skipped": [],
        },
    )
    assert report["world_domain_candidates"] == 3
    by_id = {row["match_id"]: row for row in report["rows"]}
    assert by_id["100"]["status"] == "PREREGISTERED"
    assert by_id["200"]["status"] == "COR_DISCOVERY_REJECTED"
    assert by_id["200"]["blockers"] == ["EVENT_NOT_FUTURE"]
    assert by_id["300"]["status"] == "NOT_PRESENT_IN_CURRENT_COR_DISCOVERY"
    assert report["cor_candidates_outside_today_world_lane"][0]["match_id"] == "400"
    assert report["automatic_model_feed"] is False
    assert report["metrics_opened"] is False
    assert report["outcomes_read"] == 0
    assert report["real_money"] == "BLOCKED"


def test_bridge_preserves_preregistration_skip_blockers():
    report = build_bridge(
        world_inventory=_world(),
        cor_discovery={
            "eligible_candidates": [
                {
                    "event_id": "rapidapi-tennis:match:100",
                    "canonical_source_event_id": "rapidapi-tennis:match:100",
                }
            ],
            "provider_rejected": [],
        },
        prereg={
            "event_ids": [],
            "skipped": [
                {
                    "source_event_id": "rapidapi-tennis:match:100",
                    "blockers": [
                        "ALREADY_PREREGISTERED_OR_FROZEN_PHYSICAL_EVENT"
                    ],
                }
            ],
        },
    )
    row = next(x for x in report["rows"] if x["match_id"] == "100")
    assert row["status"] == "PREREGISTRATION_SKIPPED"
    assert row["blockers"] == [
        "ALREADY_PREREGISTERED_OR_FROZEN_PHYSICAL_EVENT"
    ]
