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


def test_round_aliases_share_one_physical_identity():
    assert physical_event_key(_candidate(9001, "Quarter-Final")) == physical_event_key(
        _candidate(9002, "1/4")
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



def test_uniqueness_audit_reconciles_same_match_across_providers_without_name_only_join(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    runtime.mkdir()
    holdout.mkdir()

    rapid = {
        "event_id": "RAPID",
        "canonical_source_event_id": "rapidapi-tennis:match:3129",
        "competition_id": "rapidapi-tennis:tournament:22097",
        "competition": "Wuning 3 Challenger",
        "round": "Q3",
        "event_start_utc": "2026-10-05T03:30:00+00:00",
        "source_provider": "rapidapi_tennis",
        "player_identities": [
            {"display_name": "Maxim Zhukov", "provider_player_id": "rapidapi-tennis:player:56577"},
            {"display_name": "Ryan Seggerman", "provider_player_id": "rapidapi-tennis:player:90178"},
        ],
        "players": ["Maxim Zhukov", "Ryan Seggerman"],
    }
    api_tennis = {
        "event_id": "API",
        "canonical_source_event_id": "api-tennis:event:12168175",
        "competition_id": "api-tennis:tournament:14335",
        "competition": "Wuning 3 (China) - Qualification",
        "round": "UNKNOWN_ROUND",
        "event_start_utc": "2026-10-05T03:30:00+00:00",
        "source_provider": "api_tennis",
        "player_identities": [
            {"display_name": "Maxim Zhukov", "provider_player_id": "api-tennis:player:2209"},
            {"display_name": "Ryan Seggerman", "provider_player_id": "api-tennis:player:37911"},
        ],
        "players": ["Maxim Zhukov", "Ryan Seggerman"],
    }
    _write(
        runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R1.json",
        {"events": [rapid, api_tennis]},
    )
    _write(
        holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R1.json",
        {
            "observations": [
                {
                    "event_id": "RAPID",
                    "canonical_source_event_id": "rapidapi-tennis:match:3129",
                    "observation_index": 1,
                    "freeze_at_utc": "2026-10-04T11:11:42+00:00",
                    "event_start_utc": "2026-10-05T03:30:00+00:00",
                    "competition": "Wuning 3 Challenger",
                    "round": "Q3",
                    "alphabetical_player_a": "Maxim Zhukov",
                    "alphabetical_player_b": "Ryan Seggerman",
                    "outcome": None,
                },
                {
                    "event_id": "API",
                    "canonical_source_event_id": "api-tennis:event:12168175",
                    "observation_index": 2,
                    "freeze_at_utc": "2026-10-04T11:11:43+00:00",
                    "event_start_utc": "2026-10-05T03:30:00+00:00",
                    "competition": "Wuning 3 (China) - Qualification",
                    "round": "UNKNOWN_ROUND",
                    "alphabetical_player_a": "Maxim Zhukov",
                    "alphabetical_player_b": "Ryan Seggerman",
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
    assert report["quarantined_duplicates"][0]["quarantine_reason"] == (
        "DUPLICATE_PHYSICAL_MATCH_CROSS_PROVIDER"
    )
    assert report["outcomes_read"] == 0
    assert report["metrics_opened"] is False

def test_uniqueness_audit_reconciles_r2_with_round_of_16_across_providers(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    runtime.mkdir()
    holdout.mkdir()

    rapid = {
        "event_id": "RAPID-R2",
        "canonical_source_event_id": "rapidapi-tennis:match:1684",
        "competition_id": "rapidapi-tennis:tournament:22097",
        "competition": "Wuning 3 Challenger",
        "round": "R2",
        "event_start_utc": "2026-10-07T02:00:00+00:00",
        "source_provider": "rapidapi_tennis",
        "player_identities": [
            {"display_name": "Akira Santillan", "provider_player_id": "rapidapi-tennis:player:27531"},
            {"display_name": "Yaroslav Demin", "provider_player_id": "rapidapi-tennis:player:85075"},
        ],
        "players": ["Akira Santillan", "Yaroslav Demin"],
    }
    api_tennis = {
        "event_id": "API-R16",
        "canonical_source_event_id": "api-tennis:event:12168331",
        "competition_id": "api-tennis:tournament:14335",
        "competition": "Wuning 3 (China) - Qualification",
        "round": "WUNING 3 1/8 FINALS",
        "event_start_utc": "2026-10-07T02:00:00+00:00",
        "source_provider": "api_tennis",
        "player_identities": [
            {"display_name": "Akira Santillan", "provider_player_id": "api-tennis:player:7395"},
            {"display_name": "Yaroslav Demin", "provider_player_id": "api-tennis:player:868"},
        ],
        "players": ["Akira Santillan", "Yaroslav Demin"],
    }
    _write(
        runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R1.json",
        {"events": [rapid, api_tennis]},
    )
    _write(
        holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R1.json",
        {
            "observations": [
                {
                    "event_id": "RAPID-R2",
                    "canonical_source_event_id": "rapidapi-tennis:match:1684",
                    "observation_index": 1,
                    "freeze_at_utc": "2026-10-05T14:03:41+00:00",
                    "event_start_utc": "2026-10-07T02:00:00+00:00",
                    "competition": "Wuning 3 Challenger",
                    "round": "Second",
                    "alphabetical_player_a": "Akira Santillan",
                    "alphabetical_player_b": "Yaroslav Demin",
                    "outcome": None,
                },
                {
                    "event_id": "API-R16",
                    "canonical_source_event_id": "api-tennis:event:12168331",
                    "observation_index": 2,
                    "freeze_at_utc": "2026-10-05T14:03:42+00:00",
                    "event_start_utc": "2026-10-07T02:00:00+00:00",
                    "competition": "Wuning 3 (China) - Qualification",
                    "round": "Wuning 3 - 1/8-finals",
                    "alphabetical_player_a": "Akira Santillan",
                    "alphabetical_player_b": "Yaroslav Demin",
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
    assert report["canonical_observations"][0]["event_id"] == "RAPID-R2"
    assert report["quarantined_duplicates"][0]["event_id"] == "API-R16"
    assert report["quarantined_duplicates"][0]["quarantine_reason"] == (
        "DUPLICATE_PHYSICAL_MATCH_CROSS_PROVIDER"
    )
    assert report["outcomes_read"] == 0
    assert report["metrics_opened"] is False

def test_uniqueness_audit_reconciles_first_round_with_round_of_32_after_schedule_drift(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    runtime.mkdir()
    holdout.mkdir()

    rapid = {
        "event_id": "RAPID-FIRST",
        "canonical_source_event_id": "rapidapi-tennis:match:1686",
        "competition_id": "rapidapi-tennis:tournament:22097",
        "competition": "Wuning 3 Challenger",
        "round": "R1",
        "event_start_utc": "2026-10-06T06:00:00+00:00",
        "source_provider": "rapidapi_tennis",
        "player_identities": [
            {"display_name": "Hikaru Shiraishi", "provider_player_id": "rapidapi-tennis:player:53207"},
            {"display_name": "Ryan Seggerman", "provider_player_id": "rapidapi-tennis:player:56577"},
        ],
        "players": ["Hikaru Shiraishi", "Ryan Seggerman"],
    }
    api_tennis = {
        "event_id": "API-R32",
        "canonical_source_event_id": "api-tennis:event:12168338",
        "competition_id": "api-tennis:tournament:14335",
        "competition": "Wuning 3 (China) - Qualification",
        "round": "WUNING 3 1/16 FINALS",
        "event_start_utc": "2026-10-06T05:00:00+00:00",
        "source_provider": "api_tennis",
        "player_identities": [
            {"display_name": "Hikaru Shiraishi", "provider_player_id": "api-tennis:player:10276"},
            {"display_name": "Ryan Seggerman", "provider_player_id": "api-tennis:player:37911"},
        ],
        "players": ["Hikaru Shiraishi", "Ryan Seggerman"],
    }
    _write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R1.json", {"events": [rapid, api_tennis]})
    _write(
        holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R1.json",
        {
            "observations": [
                {
                    "event_id": "RAPID-FIRST",
                    "canonical_source_event_id": "rapidapi-tennis:match:1686",
                    "observation_index": 1,
                    "freeze_at_utc": "2026-10-06T04:22:42+00:00",
                    "event_start_utc": "2026-10-06T06:00:00+00:00",
                    "competition": "Wuning 3 Challenger",
                    "round": "First",
                    "alphabetical_player_a": "Hikaru Shiraishi",
                    "alphabetical_player_b": "Ryan Seggerman",
                    "outcome": None,
                },
                {
                    "event_id": "API-R32",
                    "canonical_source_event_id": "api-tennis:event:12168338",
                    "observation_index": 2,
                    "freeze_at_utc": "2026-10-05T14:03:42+00:00",
                    "event_start_utc": "2026-10-06T05:00:00+00:00",
                    "competition": "Wuning 3 (China) - Qualification",
                    "round": "Wuning 3 - 1/16-finals",
                    "alphabetical_player_a": "Hikaru Shiraishi",
                    "alphabetical_player_b": "Ryan Seggerman",
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
    assert report["unique_calibration_observations"] == 1
    assert report["duplicate_observations_quarantined"] == 1
    assert report["quarantined_duplicates"][0]["quarantine_reason"] == (
        "DUPLICATE_PHYSICAL_MATCH_CROSS_PROVIDER"
    )


def test_uniqueness_audit_reconciles_prefixed_final_label_across_providers(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    runtime.mkdir()
    holdout.mkdir()

    rapid = {
        "event_id": "RAPID-FINAL",
        "canonical_source_event_id": "rapidapi-tennis:match:1348",
        "competition_id": "rapidapi-tennis:tournament:22037",
        "competition": "Porto Challenger",
        "round": "Final",
        "event_start_utc": "2026-10-04T10:00:00+00:00",
        "source_provider": "rapidapi_tennis",
        "player_identities": [
            {"display_name": "Henrique Rocha", "provider_player_id": "rapidapi-tennis:player:1"},
            {"display_name": "Inaki Montes-De La Torre", "provider_player_id": "rapidapi-tennis:player:2"},
        ],
        "players": ["Henrique Rocha", "Inaki Montes-De La Torre"],
    }
    api_tennis = {
        "event_id": "API-FINAL",
        "canonical_source_event_id": "api-tennis:event:12167961",
        "competition_id": "api-tennis:tournament:999",
        "competition": "Porto",
        "round": "PORTO FINAL",
        "event_start_utc": "2026-10-04T10:00:00+00:00",
        "source_provider": "api_tennis",
        "player_identities": [
            {"display_name": "Henrique Rocha", "provider_player_id": "api-tennis:player:3"},
            {"display_name": "Inaki Montes-De La Torre", "provider_player_id": "api-tennis:player:4"},
        ],
        "players": ["Henrique Rocha", "Inaki Montes-De La Torre"],
    }
    _write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R1.json", {"events": [rapid, api_tennis]})
    _write(
        holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R1.json",
        {
            "observations": [
                {
                    "event_id": "RAPID-FINAL",
                    "canonical_source_event_id": "rapidapi-tennis:match:1348",
                    "observation_index": 1,
                    "freeze_at_utc": "2026-10-03T12:00:00+00:00",
                    "event_start_utc": "2026-10-04T10:00:00+00:00",
                    "competition": "Porto Challenger",
                    "round": "Final",
                    "alphabetical_player_a": "Henrique Rocha",
                    "alphabetical_player_b": "Inaki Montes-De La Torre",
                    "outcome": None,
                },
                {
                    "event_id": "API-FINAL",
                    "canonical_source_event_id": "api-tennis:event:12167961",
                    "observation_index": 2,
                    "freeze_at_utc": "2026-10-03T12:00:01+00:00",
                    "event_start_utc": "2026-10-04T10:00:00+00:00",
                    "competition": "Porto",
                    "round": "Porto - Final",
                    "alphabetical_player_a": "Henrique Rocha",
                    "alphabetical_player_b": "Inaki Montes-De La Torre",
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
    assert report["unique_calibration_observations"] == 1
    assert report["duplicate_observations_quarantined"] == 1


def test_uniqueness_audit_does_not_merge_cross_provider_rows_beyond_time_tolerance(tmp_path):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    runtime.mkdir()
    holdout.mkdir()

    rapid = {
        "event_id": "RAPID-LATE",
        "canonical_source_event_id": "rapidapi-tennis:match:1",
        "competition_id": "rapidapi-tennis:tournament:22097",
        "competition": "Wuning 3 Challenger",
        "round": "R1",
        "event_start_utc": "2026-10-06T09:30:00+00:00",
        "source_provider": "rapidapi_tennis",
        "player_identities": [
            {"display_name": "Alpha", "provider_player_id": "rapidapi-tennis:player:1"},
            {"display_name": "Beta", "provider_player_id": "rapidapi-tennis:player:2"},
        ],
        "players": ["Alpha", "Beta"],
    }
    api_tennis = {
        "event_id": "API-EARLY",
        "canonical_source_event_id": "api-tennis:event:2",
        "competition_id": "api-tennis:tournament:14335",
        "competition": "Wuning 3 (China) - Qualification",
        "round": "WUNING 3 1/16 FINALS",
        "event_start_utc": "2026-10-06T06:00:00+00:00",
        "source_provider": "api_tennis",
        "player_identities": [
            {"display_name": "Alpha", "provider_player_id": "api-tennis:player:3"},
            {"display_name": "Beta", "provider_player_id": "api-tennis:player:4"},
        ],
        "players": ["Alpha", "Beta"],
    }
    _write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R1.json", {"events": [rapid, api_tennis]})
    _write(
        holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R1.json",
        {
            "observations": [
                {
                    "event_id": "RAPID-LATE",
                    "canonical_source_event_id": "rapidapi-tennis:match:1",
                    "observation_index": 1,
                    "freeze_at_utc": "2026-10-05T00:00:00+00:00",
                    "event_start_utc": "2026-10-06T09:30:00+00:00",
                    "competition": "Wuning 3 Challenger",
                    "round": "First",
                    "alphabetical_player_a": "Alpha",
                    "alphabetical_player_b": "Beta",
                    "outcome": None,
                },
                {
                    "event_id": "API-EARLY",
                    "canonical_source_event_id": "api-tennis:event:2",
                    "observation_index": 2,
                    "freeze_at_utc": "2026-10-05T00:00:01+00:00",
                    "event_start_utc": "2026-10-06T06:00:00+00:00",
                    "competition": "Wuning 3 (China) - Qualification",
                    "round": "Wuning 3 - 1/16-finals",
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
    assert report["unique_calibration_observations"] == 2
    assert report["duplicate_observations_quarantined"] == 0



def test_current_canonical_window_accounting_uses_unique_matches_not_raw_rows():
    root = Path(__file__).resolve().parents[1]
    report = json.loads(
        (root / "evidence/cor0203/runtime/MATRIX_COR0203_PHYSICAL_UNIQUENESS_LAST.json").read_text()
    )

    assert report["result"] == "PASS"
    physical = report["physical_frozen_rows"]
    unique = report["unique_calibration_observations"]
    duplicates = report["duplicate_observations_quarantined"]
    unresolved = report["unresolved_identity_rows"]

    assert physical == unique + duplicates + unresolved
    assert report["metrics_opened"] is False
    assert report["outcomes_read"] == 0
    assert report["metrics"] == "SEALED_UNTIL_600_UNIQUE"

    canonical = report["canonical_observations"]
    assert len(canonical) == unique
    for row in canonical:
        index = row["canonical_unique_index"]
        expected_window = 1 + (index - 1) // 200
        assert row["window"] == expected_window

    # Raw physical rows can exceed a calibration-window boundary because
    # cross-provider aliases are quarantined after freeze. Window transitions
    # therefore use canonical unique matches, never raw frozen-row count.
    if unique < 200:
        assert all(row["window"] == 1 for row in canonical)
