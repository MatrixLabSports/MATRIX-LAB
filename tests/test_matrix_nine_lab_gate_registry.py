import json
from datetime import datetime, timezone
from pathlib import Path

from tools.matrix_nine_lab_gate_registry import ALL_LANES, build_registry


def test_registry_preserves_baselines_without_false_prospective_admission(tmp_path: Path):
    football = tmp_path / "football.json"
    tennis = tmp_path / "tennis.json"
    ledger = tmp_path / "ledger.jsonl"

    football.write_text(json.dumps({
        "status": "PASS_LAB",
        "payload_sha256": "football-sha",
        "eligible_walk_forward_rows": 3177,
    }), encoding="utf-8")
    tennis.write_text(json.dumps({
        "status": "PASS_SOURCE_LAB",
        "payload_sha256": "tennis-sha",
        "events_probed": 2,
        "captures": [
            {"event_id": "1", "status": "InPlay"},
            {"event_id": "2", "status": "InPlay"},
        ],
    }), encoding="utf-8")

    result = build_registry(
        football_path=football,
        tennis_path=tennis,
        ledger_path=ledger,
        generated_at=datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "PASS"
    assert result["lane_count"] == 9
    assert set(result["lanes"]) == set(ALL_LANES)
    assert result["baseline"]["football_historical_walk_forward_rows"] == 3177
    assert result["baseline"]["football_baseline_counts_as_prospective"] is False
    assert result["baseline"]["tennis_live_source_events"] == 2
    assert result["baseline"]["tennis_inplay_counts_as_prospective"] is False
    assert all(v["prospective_unique_count"] == 0 for v in result["lanes"].values())
    assert all(v["gates"]["100"]["status"] == "SEALED" for v in result["lanes"].values())
    assert result["protections"]["real_money"] == "BLOCKED"


def test_registry_is_append_only_and_deduplicates_same_physical_baseline(tmp_path: Path):
    football = tmp_path / "football.json"
    tennis = tmp_path / "tennis.json"
    ledger = tmp_path / "ledger.jsonl"

    football.write_text(json.dumps({
        "status": "PASS_LAB",
        "payload_sha256": "football-sha",
        "eligible_walk_forward_rows": 10,
    }), encoding="utf-8")
    tennis.write_text(json.dumps({
        "status": "PASS_SOURCE_LAB",
        "payload_sha256": "tennis-sha",
        "events_probed": 1,
        "captures": [{"event_id": "evt", "status": "InPlay"}],
    }), encoding="utf-8")

    first = build_registry(
        football_path=football,
        tennis_path=tennis,
        ledger_path=ledger,
        generated_at=datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc),
    )
    second = build_registry(
        football_path=football,
        tennis_path=tennis,
        ledger_path=ledger,
        generated_at=datetime(2026, 10, 24, 18, 15, tzinfo=timezone.utc),
    )

    assert first["ledger_rows_appended_this_run"] == 9
    assert second["ledger_rows_appended_this_run"] == 0
    assert second["ledger_rows_total"] == first["ledger_rows_total"]


def test_invalid_prospective_row_does_not_count(tmp_path):
    import json
    from datetime import datetime, timezone
    from tools.matrix_nine_lab_gate_registry import build_registry

    football = tmp_path / "football.json"
    tennis = tmp_path / "tennis.json"
    ledger = tmp_path / "ledger.jsonl"

    football.write_text(json.dumps({
        "status": "PASS_LAB",
        "payload_sha256": "f" * 64,
        "eligible_walk_forward_rows": 3177,
    }), encoding="utf-8")
    tennis.write_text(json.dumps({
        "status": "PASS_SOURCE_LAB",
        "payload_sha256": "t" * 64,
        "events_probed": 0,
        "captures": [],
    }), encoding="utf-8")

    invalid = {
        "observation_key": "bad-prospective",
        "record_type": "PROSPECTIVE_PREMATCH_FREEZE",
        "market_lane": "FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
        "fixture_id": "1",
        "event_start_utc": "2026-10-25T15:00:00+00:00",
        "freeze_timestamp_utc": "2026-10-25T15:01:00+00:00",
        "prediction_snapshot_sha256": "a" * 64,
        "prospective_admitted": True,
        "counts_toward_100_300_600": True,
        "odds_used_to_generate_probability": False,
        "missing_not_zero": True,
        "silent_imputation": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    ledger.write_text(json.dumps(invalid) + "\n", encoding="utf-8")

    result = build_registry(
        football_path=football,
        tennis_path=tennis,
        ledger_path=ledger,
        generated_at=datetime(2026, 10, 24, 20, 0, tzinfo=timezone.utc),
    )
    assert result["lanes"]["FIRST_HALF_TOTAL_GOALS_OVER_UNDER"]["prospective_unique_count"] == 0
