from __future__ import annotations

import json
from pathlib import Path

from tools.cor0203_preregister_discovery import preregister_discovery


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _discovery():
    return {
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
