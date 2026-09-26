from __future__ import annotations

import json
from pathlib import Path

from tools.cor0203_stage_from_registry import build_sealed_player_registry, stage_all_pending


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def player(name, source_id, hand, age, rank, points):
    return {
        "name": name,
        "source_id": source_id,
        "hand": hand,
        "age": age,
        "rank": rank,
        "rank_points": points,
    }


def frozen_manifest(event_id="old-a"):
    return {
        "holdout_id": "H",
        "starting_observation_count": 0,
        "events": [
            {
                "event_id": event_id,
                "target_period": 20260921,
                "players": [
                    player("Titouan Droguet", "D0DW", "R", 25.268, 84, 690),
                    player("Dino Prizmic", "P0HW", "R", 21.128, 101, 603),
                ],
            }
        ],
    }


def prereg():
    return {
        "schema": "MATRIX_COR0203_TRUE_PREFEATURE_REGISTRY_R722_V1",
        "holdout_id": "H",
        "starting_observation_count": 9,
        "created_before_feature_acquisition": True,
        "events": [
            {
                "event_id": "COR0203-R722-STT-DROGUET-PRIZMIC",
                "canonical_source_event_id": "STT-2026-SF-DROGUET-PRIZMIC",
                "competition": "ATP Challenger Saint-Tropez",
                "round": "SF",
                "surface": "Hard",
                "tour_level": "C",
                "target_period": 20260921,
                "event_start_utc": "2026-09-26T17:00:00+00:00",
                "identity_source": "current semifinal preview",
                "schedule_source": "26-SEP 19:00 local",
                "players": ["Titouan Droguet", "Dino Prizmic"],
                "features_loaded": False,
                "outcome": None,
                "metrics_opened": False,
            }
        ],
    }


def setup_frozen_source(runtime: Path, holdout: Path, *, event_id="old-a") -> None:
    write(runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R707.json", frozen_manifest(event_id))
    write(
        holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R707.json",
        {
            "ending_observation_count": 2,
            "observations": [{"event_id": event_id}],
        },
    )


def test_r722_is_auto_staged_from_only_frozen_sealed_player_values(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    setup_frozen_source(runtime, holdout)
    write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R722.json", prereg())

    result = stage_all_pending(runtime_dir=runtime, holdout_dir=holdout)

    assert result["registry_pass"] == 2
    staged = next(row for row in result["revisions"] if row["revision"] == 722)
    assert staged["status"] == "PASS"
    assert staged["staged_events"] == 1

    static4 = json.loads((runtime / "MATRIX_COR0203_STATIC4_R722.json").read_text())
    events = json.loads((runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R722.json").read_text())
    blockers = json.loads((runtime / "MATRIX_COR0203_STAGE_BLOCKERS_R722.json").read_text())

    assert static4["players"]["Titouan Droguet"]["rank"] == 84
    assert static4["players"]["Dino Prizmic"]["rank"] == 101
    assert static4["players"]["Titouan Droguet"]["source_id"] == "D0DW"
    assert static4["players"]["Dino Prizmic"]["source_id"] == "P0HW"
    assert static4["provenance"]["silent_imputation"] is False
    assert static4["provenance"]["registry_source_only_frozen_events"] is True

    assert events["starting_observation_count"] == 9
    assert events["events"][0]["players"][0]["name"] == "Titouan Droguet"
    assert events["events"][0]["players"][1]["name"] == "Dino Prizmic"
    assert events["automatic_wagering"] is False
    assert events["real_money"] == "BLOCKED"
    assert blockers["result"] == "PASS"
    assert blockers["blocked_events"] == 0


def test_unfrozen_manifest_cannot_populate_sealed_player_registry(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    runtime.mkdir()
    holdout.mkdir()
    write(runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R707.json", frozen_manifest("not-frozen"))

    registry = build_sealed_player_registry(runtime_dir=runtime, holdout_dir=holdout)

    assert "Titouan Droguet" not in registry
    assert "Dino Prizmic" not in registry


def test_unknown_player_is_blocked_without_invention(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    setup_frozen_source(runtime, holdout)

    p = prereg()
    p["events"][0]["players"] = ["Titouan Droguet", "Unknown Player"]
    write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R722.json", p)

    result = stage_all_pending(runtime_dir=runtime, holdout_dir=holdout)

    staged = next(row for row in result["revisions"] if row["revision"] == 722)
    assert staged["status"] == "ALL_BLOCKED"
    assert not (runtime / "MATRIX_COR0203_STATIC4_R722.json").exists()
    assert not (runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R722.json").exists()
    blockers = json.loads((runtime / "MATRIX_COR0203_STAGE_BLOCKERS_R722.json").read_text())
    assert "SEALED_STATIC4_PLAYER_NOT_FOUND:Unknown Player" in blockers["blocked"][0]["blockers"]


def test_conflicting_sealed_static_values_block_player(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    setup_frozen_source(runtime, holdout, event_id="old-a")

    conflicting = frozen_manifest("old-b")
    conflicting["events"][0]["players"][0]["rank"] = 999
    write(runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R708.json", conflicting)
    write(
        holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R708.json",
        {"ending_observation_count": 3, "observations": [{"event_id": "old-b"}]},
    )
    write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R722.json", prereg())

    result = stage_all_pending(runtime_dir=runtime, holdout_dir=holdout)

    assert result["registry_conflicts"] >= 1
    blockers = json.loads((runtime / "MATRIX_COR0203_STAGE_BLOCKERS_R722.json").read_text())
    assert "SEALED_STATIC4_CONFLICT:Titouan Droguet" in blockers["blocked"][0]["blockers"]


def test_existing_static_and_event_manifests_are_never_rewritten(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    setup_frozen_source(runtime, holdout)
    write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R722.json", prereg())
    write(runtime / "MATRIX_COR0203_STATIC4_R722.json", {"sentinel": "static"})
    write(runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R722.json", {"sentinel": "events"})

    result = stage_all_pending(runtime_dir=runtime, holdout_dir=holdout)

    staged = next(row for row in result["revisions"] if row["revision"] == 722)
    assert staged["status"] == "ALREADY_STAGED"
    assert json.loads((runtime / "MATRIX_COR0203_STATIC4_R722.json").read_text()) == {"sentinel": "static"}
    assert json.loads((runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R722.json").read_text()) == {"sentinel": "events"}


def test_already_frozen_prefeature_is_immutable_even_if_static4_missing(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    setup_frozen_source(runtime, holdout)

    p = prereg()
    event_id = p["events"][0]["event_id"]
    write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R722.json", p)
    write(
        holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R722.json",
        {"ending_observation_count": 10, "observations": [{"event_id": event_id}]},
    )

    result = stage_all_pending(runtime_dir=runtime, holdout_dir=holdout)

    staged = next(row for row in result["revisions"] if row["revision"] == 722)
    assert staged["status"] == "ALREADY_FROZEN"
    assert not (runtime / "MATRIX_COR0203_STATIC4_R722.json").exists()
    assert not (runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R722.json").exists()


def test_existing_event_manifest_without_static4_is_not_rewritten(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    setup_frozen_source(runtime, holdout)
    write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R722.json", prereg())

    original = {"sentinel": "immutable-existing-manifest"}
    write(runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R722.json", original)

    result = stage_all_pending(runtime_dir=runtime, holdout_dir=holdout)

    staged = next(row for row in result["revisions"] if row["revision"] == 722)
    assert staged["status"] == "INCOMPLETE_EXISTING_STAGE"
    assert json.loads((runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R722.json").read_text()) == original
    assert not (runtime / "MATRIX_COR0203_STATIC4_R722.json").exists()

    blocker = json.loads((runtime / "MATRIX_COR0203_STAGE_BLOCKERS_R722.json").read_text())
    assert blocker["result"] == "INCOMPLETE_EXISTING_STAGE"
    assert "EVENT_MANIFEST_EXISTS_STATIC4_MISSING" in blocker["blocked"][0]["blockers"]


def test_provider_discovery_event_cannot_stage_without_identity_crosswalk(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    setup_frozen_source(runtime, holdout)

    p = prereg()
    p["schema"] = "MATRIX_COR0203_API_TENNIS_PREFEATURE_REGISTRY_R722_V1"
    p["events"][0]["identity_crosswalk_required"] = True
    p["events"][0]["historical_identity_crosswalk_status"] = "PENDING"
    p["events"][0]["source_provider"] = "api_tennis"
    p["events"][0]["source_snapshot_sha256"] = "a" * 64
    p["events"][0]["player_identities"] = [
        {"display_name": "T. Droguet", "provider_player_id": "api-tennis:player:11", "provider": "api_tennis"},
        {"display_name": "D. Prizmic", "provider_player_id": "api-tennis:player:22", "provider": "api_tennis"},
    ]
    p["events"][0]["players"] = ["T. Droguet", "D. Prizmic"]
    write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R722.json", p)

    result = stage_all_pending(runtime_dir=runtime, holdout_dir=holdout)

    staged = next(row for row in result["revisions"] if row["revision"] == 722)
    assert staged["status"] == "ALL_BLOCKED"
    blockers = json.loads((runtime / "MATRIX_COR0203_STAGE_BLOCKERS_R722.json").read_text())
    assert "HISTORICAL_IDENTITY_CROSSWALK_REQUIRED" in blockers["blocked"][0]["blockers"]
    assert not (runtime / "MATRIX_COR0203_STATIC4_R722.json").exists()
    assert not (runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R722.json").exists()


def test_crosswalk_pass_uses_canonical_history_identity_not_provider_display_name(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    setup_frozen_source(runtime, holdout)

    p = prereg()
    p["schema"] = "MATRIX_COR0203_API_TENNIS_PREFEATURE_REGISTRY_R722_V1"
    p["events"][0]["identity_crosswalk_required"] = True
    p["events"][0]["historical_identity_crosswalk_status"] = "PENDING"
    p["events"][0]["player_identities"] = [
        {"display_name": "T. Droguet", "provider_player_id": "api-tennis:player:11", "provider": "api_tennis"},
        {"display_name": "D. Prizmic", "provider_player_id": "api-tennis:player:22", "provider": "api_tennis"},
    ]
    p["events"][0]["players"] = ["T. Droguet", "D. Prizmic"]
    write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R722.json", p)
    write(
        runtime / "MATRIX_COR0203_IDENTITY_CROSSWALK_R722.json",
        {
            "status": "PASS",
            "mappings": [
                {
                    "provider_player_id": "api-tennis:player:11",
                    "canonical_name": "Titouan Droguet",
                    "canonical_source_id": "D0DW",
                    "status": "PASS",
                },
                {
                    "provider_player_id": "api-tennis:player:22",
                    "canonical_name": "Dino Prizmic",
                    "canonical_source_id": "P0HW",
                    "status": "PASS",
                },
            ],
        },
    )

    result = stage_all_pending(runtime_dir=runtime, holdout_dir=holdout)

    staged = next(row for row in result["revisions"] if row["revision"] == 722)
    assert staged["status"] == "PASS"
    events = json.loads((runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R722.json").read_text())
    row = events["events"][0]
    names = [player["name"] for player in row["players"]]
    assert names == ["Titouan Droguet", "Dino Prizmic"]
    assert [player["source_id"] for player in row["players"]] == ["D0DW", "P0HW"]
    assert [player["provider_player_id"] for player in row["players"]] == [
        "api-tennis:player:11",
        "api-tennis:player:22",
    ]
    assert all(
        player["identity_binding"] == "API_TENNIS_TO_STATIC_CUT_STRONG_CROSSWALK"
        for player in row["players"]
    )
    assert row["source_provider"] == "api_tennis"
    assert row["source_snapshot_sha256"] == "a" * 64
    assert row["identity_crosswalk_required"] is True
    assert row["identity_crosswalk_reference"] == "MATRIX_COR0203_IDENTITY_CROSSWALK_R722.json"
