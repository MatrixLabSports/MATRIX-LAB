from __future__ import annotations

import json
from pathlib import Path

from tools.cor0203_world_funnel_audit import build_world_funnel


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _world():
    return {
        "status": "PASS",
        "world_inventory_complete": True,
        "target_date_bogota": "2026-10-02",
        "world_calendar_inventory_count": 10,
        "derived_lanes": {
            "COR02_COR03_ATP_CHALLENGER_HARD": {
                "source_event_ids": [
                    "rapidapi-tennis:atp:match:100",
                    "rapidapi-tennis:atp:match:200",
                    "rapidapi-tennis:atp:match:300",
                ]
            }
        },
        "events": [
            {
                "source_event_id": "rapidapi-tennis:atp:match:100",
                "tournament_name": "Porto Challenger",
                "round": "1/4",
                "event_start_bogota": "2026-10-02T05:00:00-05:00",
                "player1": {"name": "A"},
                "player2": {"name": "B"},
            },
            {
                "source_event_id": "rapidapi-tennis:atp:match:200",
                "tournament_name": "Columbus Challenger",
                "round": "1/4",
                "event_start_bogota": "2026-10-02T10:00:00-05:00",
                "player1": {"name": "C"},
                "player2": {"name": "D"},
            },
            {
                "source_event_id": "rapidapi-tennis:atp:match:300",
                "tournament_name": "Jingshan Challenger",
                "round": "1/4",
                "event_start_bogota": "2026-10-02T02:00:00-05:00",
                "player1": {"name": "E"},
                "player2": {"name": "F"},
            },
        ],
    }


def test_world_funnel_distinguishes_frozen_blocked_and_rejected(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    _write(
        runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R10.json",
        {
            "events": [
                {
                    "event_id": "COR0203-RAPIDAPI-TENNIS-100-aaaaaaaaaaaa",
                    "physical_event_key": "p100",
                },
                {
                    "event_id": "COR0203-RAPIDAPI-TENNIS-200-bbbbbbbbbbbb",
                    "physical_event_key": "p200",
                },
            ]
        },
    )
    _write(
        runtime / "MATRIX_COR0203_STAGE_BLOCKERS_R10.json",
        {
            "staged_event_ids": [
                "COR0203-RAPIDAPI-TENNIS-100-aaaaaaaaaaaa"
            ],
            "blocked": [
                {
                    "event_id": "COR0203-RAPIDAPI-TENNIS-200-bbbbbbbbbbbb",
                    "blockers": ["IDENTITY_CROSSWALK_MISSING:x"],
                }
            ],
        },
    )

    report = build_world_funnel(
        world_inventory=_world(),
        world_discovery={
            "eligible_candidates": [
                {
                    "event_id": "rapidapi-tennis:match:100",
                    "canonical_source_event_id": "rapidapi-tennis:match:100",
                    "physical_event_key": "p100",
                },
                {
                    "event_id": "rapidapi-tennis:match:200",
                    "canonical_source_event_id": "rapidapi-tennis:match:200",
                    "physical_event_key": "p200",
                },
            ],
            "provider_rejected": [
                {
                    "match_id": "300",
                    "blockers": ["EVENT_NOT_FUTURE"],
                }
            ],
        },
        uniqueness={
            "unique_calibration_observations": 51,
            "canonical_observations": [
                {
                    "event_id": "COR0203-RAPIDAPI-TENNIS-100-aaaaaaaaaaaa",
                    "physical_event_key": "p100",
                    "observation_index": 103,
                }
            ],
        },
        runtime_dir=runtime,
    )

    by_id = {row["match_id"]: row for row in report["rows"]}
    assert by_id["100"]["status"] == "FROZEN_UNIQUE"
    assert by_id["100"]["frozen_observation_index"] == 103
    assert by_id["200"]["status"] == "PREREGISTERED_BLOCKED"
    assert by_id["200"]["blockers"] == ["IDENTITY_CROSSWALK_MISSING:x"]
    assert by_id["300"]["status"] == "DISCOVERY_REJECTED"
    assert by_id["300"]["blockers"] == ["EVENT_NOT_FUTURE"]
    assert report["status_counts"] == {
        "DISCOVERY_REJECTED": 1,
        "FROZEN_UNIQUE": 1,
        "PREREGISTERED_BLOCKED": 1,
    }
    assert report["metrics_opened"] is False
    assert report["outcomes_read"] == 0
    assert report["real_money"] == "BLOCKED"
