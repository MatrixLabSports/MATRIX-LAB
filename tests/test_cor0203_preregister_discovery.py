from __future__ import annotations

import json
from pathlib import Path

from tools.cor0203_preregister_discovery import preregister_discovery


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _discovery():
    return {
        "provider": "api_tennis",
        "status": "DISCOVERY_COMPLETED",
        "eligible_candidates": [
            {
                "event_id": "api-tennis:event:12345",
                "canonical_source_event_id": "api-tennis:event:12345",
                "competition_id": "api-tennis:tournament:500",
                "competition": "Example Challenger",
                "round": "Quarter-finals",
                "surface": "Hard",
                "tour_level": "C",
                "event_start_utc": "2026-09-27T12:00:00+00:00",
                "target_period": 20260921,
                "source_reference": "fixture+draw",
                "source_snapshot_sha256": "a" * 64,
                "players": [
                    {"name": "Player A", "provider_player_id": "api-tennis:player:11"},
                    {"name": "Player B", "provider_player_id": "api-tennis:player:22"},
                ],
                "historical_identity_crosswalk_status": "PENDING",
            }
        ],
    }


def test_discovery_creates_prefeature_with_strong_provider_ids_and_pending_crosswalk(tmp_path):
    cor = tmp_path / "cor0203"
    runtime = cor / "runtime"
    holdout = cor / "holdout"
    runtime.mkdir(parents=True)
    holdout.mkdir(parents=True)
    _write(
        holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R722.json",
        {"ending_observation_count": 10, "observations": [{"event_id": "old"}]},
    )

    result = preregister_discovery(
        discovery=_discovery(),
        cor_root=cor,
        runtime_dir=runtime,
        holdout_dir=holdout,
    )

    assert result["status"] == "PREREGISTERED"
    assert result["starting_observation_count"] == 10
    assert result["events_registered"] == 1
    path = runtime / f"MATRIX_COR0203_PREFEATURE_REGISTRY_R{result['revision']}.json"
    payload = json.loads(path.read_text())
    event = payload["events"][0]
    assert event["features_loaded"] is False
    assert event["outcome"] is None
    assert event["metrics_opened"] is False
    assert event["identity_crosswalk_required"] is True
    assert event["historical_identity_crosswalk_status"] == "PENDING"
    assert event["player_identities"][0]["provider_player_id"] == "api-tennis:player:11"
    assert event["player_identities"][1]["provider_player_id"] == "api-tennis:player:22"
    assert event["source_snapshot_sha256"] == "a" * 64


def test_duplicate_provider_event_is_not_preregistered_twice(tmp_path):
    cor = tmp_path / "cor0203"
    runtime = cor / "runtime"
    holdout = cor / "holdout"
    runtime.mkdir(parents=True)
    holdout.mkdir(parents=True)
    _write(
        runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R723.json",
        {
            "events": [
                {
                    "event_id": "COR0203-API-TENNIS-12345",
                    "canonical_source_event_id": "api-tennis:event:12345",
                }
            ]
        },
    )

    result = preregister_discovery(
        discovery=_discovery(),
        cor_root=cor,
        runtime_dir=runtime,
        holdout_dir=holdout,
    )

    assert result["status"] == "NO_NEW_EVENTS"
    assert result["events_registered"] == 0
    assert "ALREADY_PREREGISTERED_OR_FROZEN" in result["skipped"][0]["blockers"]


def test_invalid_provider_player_id_is_rejected(tmp_path):
    discovery = _discovery()
    discovery["eligible_candidates"][0]["players"][1]["provider_player_id"] = ""

    cor = tmp_path / "cor0203"
    runtime = cor / "runtime"
    holdout = cor / "holdout"
    runtime.mkdir(parents=True)
    holdout.mkdir(parents=True)

    result = preregister_discovery(
        discovery=discovery,
        cor_root=cor,
        runtime_dir=runtime,
        holdout_dir=holdout,
    )

    assert result["status"] == "NO_NEW_EVENTS"
    assert "PROVIDER_PLAYER_ID_INVALID" in result["skipped"][0]["blockers"]


def test_missing_provider_key_status_does_not_create_prefeature(tmp_path):
    cor = tmp_path / "cor0203"
    runtime = cor / "runtime"
    holdout = cor / "holdout"
    runtime.mkdir(parents=True)
    holdout.mkdir(parents=True)

    result = preregister_discovery(
        discovery={"status": "API_TENNIS_KEY_NOT_CONFIGURED"},
        cor_root=cor,
        runtime_dir=runtime,
        holdout_dir=holdout,
    )

    assert result["status"] == "NO_DISCOVERY_INPUT"
    assert result["created"] is False
    assert list(runtime.iterdir()) == []


def test_rapidapi_discovery_uses_separate_governed_identity_namespace(tmp_path):
    discovery = {
        "provider": "rapidapi_tennis",
        "status": "DISCOVERY_COMPLETED",
        "eligible_candidates": [
            {
                "event_id": "rapidapi-tennis:match:9001",
                "canonical_source_event_id": "rapidapi-tennis:match:9001",
                "competition_id": "rapidapi-tennis:tournament:77",
                "competition": "Example Challenger",
                "round": "Quarter-Final",
                "surface": "Hard",
                "tour_level": "C",
                "event_start_utc": "2026-09-27T16:00:00+00:00",
                "target_period": 20260921,
                "source_reference": "fixtures+ranking+tournament",
                "source_snapshot_sha256": "b" * 64,
                "players": [
                    {
                        "name": "Player A",
                        "provider_player_id": "rapidapi-tennis:player:101",
                        "provider_ranking": {
                            "place": "100",
                            "points": "600",
                            "player": "Player A",
                        },
                    },
                    {
                        "name": "Player B",
                        "provider_player_id": "rapidapi-tennis:player:202",
                        "provider_ranking": {
                            "place": "120",
                            "points": "500",
                            "player": "Player B",
                        },
                    },
                ],
            }
        ],
    }
    cor = tmp_path / "cor0203"
    runtime = cor / "runtime"
    holdout = cor / "holdout"
    runtime.mkdir(parents=True)
    holdout.mkdir(parents=True)

    result = preregister_discovery(
        discovery=discovery,
        cor_root=cor,
        runtime_dir=runtime,
        holdout_dir=holdout,
    )

    assert result["status"] == "PREREGISTERED"
    path = runtime / f"MATRIX_COR0203_PREFEATURE_REGISTRY_R{result['revision']}.json"
    payload = json.loads(path.read_text())
    assert payload["discovery_provider"] == "rapidapi_tennis"
    event = payload["events"][0]
    assert event["event_id"] == (
        "COR0203-RAPIDAPI-TENNIS-9001-"
        + event["physical_event_key"][:12]
    )
    assert event["source_provider"] == "rapidapi_tennis"
    assert event["provider_source_id_reused"] is False
    assert event["player_identities"][0]["provider"] == "rapidapi_tennis"
    assert (
        event["player_identities"][0]["provider_player_id"]
        == "rapidapi-tennis:player:101"
    )


def test_rapidapi_reused_match_id_with_new_physical_match_is_allowed(tmp_path):
    discovery = {
        "provider": "rapidapi_tennis",
        "status": "DISCOVERY_COMPLETED",
        "eligible_candidates": [
            {
                "event_id": "rapidapi-tennis:match:9001",
                "canonical_source_event_id": "rapidapi-tennis:match:9001",
                "competition_id": "rapidapi-tennis:tournament:77",
                "competition": "Example Challenger",
                "round": "Quarter-Final",
                "surface": "Hard",
                "tour_level": "C",
                "event_start_utc": "2026-10-02T16:00:00+00:00",
                "target_period": 20260921,
                "source_reference": "world-inventory-derived",
                "source_snapshot_sha256": "c" * 64,
                "players": [
                    {
                        "name": "New Player A",
                        "provider_player_id": "rapidapi-tennis:player:101",
                        "provider_ranking": {"place": "100", "points": "600"},
                    },
                    {
                        "name": "New Player B",
                        "provider_player_id": "rapidapi-tennis:player:202",
                        "provider_ranking": {"place": "120", "points": "500"},
                    },
                ],
            }
        ],
    }
    cor = tmp_path / "cor0203"
    runtime = cor / "runtime"
    holdout = cor / "holdout"
    runtime.mkdir(parents=True)
    holdout.mkdir(parents=True)
    _write(
        runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R750.json",
        {
            "events": [
                {
                    "event_id": "COR0203-RAPIDAPI-TENNIS-9001",
                    "canonical_source_event_id": "rapidapi-tennis:match:9001",
                    "competition_id": "rapidapi-tennis:tournament:77",
                    "competition": "Example Challenger",
                    "round": "First",
                    "players": ["Old Player A", "Old Player B"],
                    "player_identities": [
                        {
                            "display_name": "Old Player A",
                            "provider_player_id": "rapidapi-tennis:player:303",
                        },
                        {
                            "display_name": "Old Player B",
                            "provider_player_id": "rapidapi-tennis:player:404",
                        },
                    ],
                }
            ]
        },
    )

    result = preregister_discovery(
        discovery=discovery,
        cor_root=cor,
        runtime_dir=runtime,
        holdout_dir=holdout,
    )

    assert result["status"] == "PREREGISTERED"
    payload = json.loads(
        (
            runtime
            / f"MATRIX_COR0203_PREFEATURE_REGISTRY_R{result['revision']}.json"
        ).read_text()
    )
    event = payload["events"][0]
    assert event["provider_source_id_reused"] is True
    assert event["canonical_source_event_id"] == "rapidapi-tennis:match:9001"
    assert event["event_id"].startswith("COR0203-RAPIDAPI-TENNIS-9001-")


def test_rapidapi_channel_qualified_atp_event_preserves_canonical_source(tmp_path):
    discovery = {
        "provider": "rapidapi_tennis",
        "status": "DISCOVERY_COMPLETED",
        "eligible_candidates": [
            {
                "event_id": "rapidapi-tennis:atp:match:9001",
                "canonical_source_event_id": "rapidapi-tennis:atp:match:9001",
                "competition_id": "rapidapi-tennis:tournament:77",
                "competition": "Example Challenger",
                "round": "Quarter-Final",
                "surface": "Hard",
                "tour_level": "C",
                "event_start_utc": "2026-10-02T16:00:00+00:00",
                "target_period": 20260921,
                "source_reference": "world-inventory-derived;provider_channel=ATP",
                "source_snapshot_sha256": "d" * 64,
                "players": [
                    {
                        "name": "Player A",
                        "provider_player_id": "rapidapi-tennis:player:101",
                        "provider_ranking": {"place": "100", "points": "600"},
                    },
                    {
                        "name": "Player B",
                        "provider_player_id": "rapidapi-tennis:player:202",
                        "provider_ranking": {"place": "120", "points": "500"},
                    },
                ],
            }
        ],
    }
    cor = tmp_path / "cor0203"
    runtime = cor / "runtime"
    holdout = cor / "holdout"
    runtime.mkdir(parents=True)
    holdout.mkdir(parents=True)

    result = preregister_discovery(
        discovery=discovery,
        cor_root=cor,
        runtime_dir=runtime,
        holdout_dir=holdout,
    )

    assert result["status"] == "PREREGISTERED"
    payload = json.loads(
        (
            runtime
            / f"MATRIX_COR0203_PREFEATURE_REGISTRY_R{result['revision']}.json"
        ).read_text()
    )
    event = payload["events"][0]
    assert event["canonical_source_event_id"] == (
        "rapidapi-tennis:atp:match:9001"
    )
    assert event["event_id"].startswith("COR0203-RAPIDAPI-TENNIS-9001-")


def test_preregister_blocks_canonical_physical_key_from_uniqueness_audit(tmp_path):
    discovery = {
        "provider": "rapidapi_tennis",
        "status": "DISCOVERY_COMPLETED",
        "eligible_candidates": [
            {
                "event_id": "rapidapi-tennis:atp:match:1366",
                "canonical_source_event_id": "rapidapi-tennis:atp:match:1366",
                "competition_id": "rapidapi-tennis:tournament:22093",
                "competition": "Villena Challenger",
                "round": "Second",
                "surface": "Hard",
                "tour_level": "C",
                "event_start_utc": "2026-10-08T09:00:00+00:00",
                "target_period": 20260921,
                "source_reference": "fixtures+ranking+tournament",
                "source_snapshot_sha256": "e" * 64,
                "physical_event_key": "a" * 64,
                "players": [
                    {
                        "name": "Moez Echargui",
                        "provider_player_id": "rapidapi-tennis:player:36114",
                        "provider_ranking": {"place": "378", "points": "134"},
                    },
                    {
                        "name": "Daniil Glinka",
                        "provider_player_id": "rapidapi-tennis:player:48825",
                        "provider_ranking": {"place": "173", "points": "333"},
                    },
                ],
            }
        ],
    }
    cor = tmp_path / "cor0203"
    runtime = cor / "runtime"
    holdout = cor / "holdout"
    runtime.mkdir(parents=True)
    holdout.mkdir(parents=True)

    # Historical append-only batch has an older provider-derived key.
    _write(
        holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R843.json",
        {
            "ending_observation_count": 212,
            "observations": [
                {
                    "event_id": "COR0203-RAPIDAPI-TENNIS-1346-old",
                    "canonical_source_event_id": "rapidapi-tennis:match:1346",
                    "physical_event_key": "b" * 64,
                }
            ],
        },
    )
    # The uniqueness audit has already canonicalized the same physical match.
    _write(
        runtime / "MATRIX_COR0203_PHYSICAL_UNIQUENESS_LAST.json",
        {
            "canonical_observations": [
                {
                    "event_id": "COR0203-RAPIDAPI-TENNIS-1346-old",
                    "canonical_source_event_id": "rapidapi-tennis:match:1346",
                    "physical_event_key": "a" * 64,
                }
            ],
            "quarantined_duplicates": [],
        },
    )

    result = preregister_discovery(
        discovery=discovery,
        cor_root=cor,
        runtime_dir=runtime,
        holdout_dir=holdout,
    )

    assert result["status"] == "NO_NEW_EVENTS"
    assert result["events_registered"] == 0
    assert "ALREADY_PREREGISTERED_OR_FROZEN_PHYSICAL_EVENT" in (
        result["skipped"][0]["blockers"]
    )
