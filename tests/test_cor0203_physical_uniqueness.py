from __future__ import annotations

import json
from pathlib import Path

from tools.cor0203_physical_identity import physical_event_key
from tools.cor0203_physical_uniqueness_audit import audit_physical_uniqueness
from tools.cor0203_preregister_discovery import preregister_discovery


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _candidate(match_id: int, round_name: str = "First") -> dict:
    row = {
        "event_id": f"rapidapi-tennis:match:{match_id}",
        "canonical_source_event_id": f"rapidapi-tennis:match:{match_id}",
        "competition_id": "rapidapi-tennis:tournament:22037",
        "competition": "Porto Challenger",
        "round": round_name,
        "surface": "Hard",
        "tour_level": "C",
        "event_start_utc": "2026-10-03T12:00:00+00:00",
        "target_period": 20260921,
        "source_provider": "rapidapi_tennis",
        "source_reference": f"fixtures:matchId={match_id};tournament_info=22037",
        "source_snapshot_sha256": ("a" if match_id == 9001 else "b") * 64,
        "player_identities": [
            {
                "display_name": "Alpha",
                "provider_player_id": "rapidapi-tennis:player:101",
                "provider": "rapidapi_tennis",
            },
            {
                "display_name": "Beta",
                "provider_player_id": "rapidapi-tennis:player:202",
                "provider": "rapidapi_tennis",
            },
        ],
        "players": [
            {
                "name": "Alpha",
                "provider_player_id": "rapidapi-tennis:player:101",
                "provider_ranking": {"place": "100", "points": "600"},
            },
            {
                "name": "Beta",
                "provider_player_id": "rapidapi-tennis:player:202",
                "provider_ranking": {"place": "120", "points": "500"},
            },
        ],
    }
    row["physical_event_key"] = physical_event_key(row)
    return row


def _discovery(match_id: int, round_name: str = "First") -> dict:
    return {
        "provider": "rapidapi_tennis",
        "status": "DISCOVERY_COMPLETED",
        "eligible_candidates": [_candidate(match_id, round_name)],
    }


def test_changed_match_id_same_physical_match_is_not_preregistered_twice(tmp_path):
    cor = tmp_path / "cor0203"
    runtime = cor / "runtime"
    holdout = cor / "holdout"
    runtime.mkdir(parents=True)
    holdout.mkdir(parents=True)

    first = preregister_discovery(
        discovery=_discovery(9001),
        cor_root=cor,
        runtime_dir=runtime,
        holdout_dir=holdout,
    )
    assert first["status"] == "PREREGISTERED"

    second = preregister_discovery(
        discovery=_discovery(9002),
        cor_root=cor,
        runtime_dir=runtime,
        holdout_dir=holdout,
    )
    assert second["status"] == "NO_NEW_EVENTS"
    assert (
        "ALREADY_PREREGISTERED_OR_FROZEN_PHYSICAL_EVENT"
        in second["skipped"][0]["blockers"]
    )


def test_same_players_different_round_has_different_physical_identity(tmp_path):
    assert physical_event_key(_candidate(9001, "First")) != physical_event_key(
        _candidate(9002, "Second")
    )


def test_uniqueness_audit_quarantines_later_alias_without_reading_outcome(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    runtime.mkdir()
    holdout.mkdir()

    first = _candidate(9001)
    second = _candidate(9002)
    _write(
        runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R1.json",
        {
            "events": [
                {
                    **first,
                    "event_id": "E1",
                    "players": ["Alpha", "Beta"],
                },
                {
                    **second,
                    "event_id": "E2",
                    "players": ["Alpha", "Beta"],
                },
            ]
        },
    )
    _write(
        holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R1.json",
        {
            "observations": [
                {
                    "event_id": "E1",
                    "canonical_source_event_id": "rapidapi-tennis:match:9001",
                    "observation_index": 1,
                    "freeze_at_utc": "2026-10-01T10:00:00+00:00",
                    "event_start_utc": "2026-10-03T12:00:00+00:00",
                    "competition": "Porto Challenger",
                    "round": "First",
                    "alphabetical_player_a": "Alpha",
                    "alphabetical_player_b": "Beta",
                    "outcome": None,
                },
                {
                    "event_id": "E2",
                    "canonical_source_event_id": "rapidapi-tennis:match:9002",
                    "observation_index": 2,
                    "freeze_at_utc": "2026-10-01T11:00:00+00:00",
                    "event_start_utc": "2026-10-03T12:00:00+00:00",
                    "competition": "Porto Challenger",
                    "round": "First",
                    "alphabetical_player_a": "Alpha",
                    "alphabetical_player_b": "Beta",
                    "outcome": None,
                },
            ]
        },
    )
    report = audit_physical_uniqueness(
        runtime_dir=runtime,
        holdout_dir=holdout,
        integrity={
            "holdout_id": "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1",
            "result": "PASS",
            "admissible_batch_revisions": [1],
            "admissible_observations": 2,
        },
    )
    assert report["result"] == "PASS"
    assert report["physical_frozen_rows"] == 2
    assert report["unique_calibration_observations"] == 1
    assert report["duplicate_observations_quarantined"] == 1
    assert report["canonical_observations"][0]["event_id"] == "E1"
    assert report["quarantined_duplicates"][0]["event_id"] == "E2"
    assert report["outcomes_read"] == 0
    assert report["metrics_opened"] is False
