from datetime import datetime, timezone
import json
from pathlib import Path

from tools.matrix_42_lane_prospective_registry import build, validate_freeze


def _row():
    return {
        "observation_key": "football|TOTAL_GOALS_OVER_UNDER|fixture:1",
        "record_type": "PROSPECTIVE_PREMATCH_FREEZE",
        "sport": "football",
        "market_lane": "TOTAL_GOALS_OVER_UNDER",
        "fixture_id": "1",
        "event_start_utc": "2026-10-25T15:00:00+00:00",
        "freeze_timestamp_utc": "2026-10-25T14:45:00+00:00",
        "prediction_snapshot_sha256": "a" * 64,
        "feature_snapshot_sha256": "b" * 64,
        "target_outcome": None,
        "settlement": None,
        "odds_used_to_generate_probability": False,
        "missing_not_zero": True,
        "silent_imputation": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "prospective_admitted": True,
        "counts_toward_100_300_600": True,
    }


def test_rejects_post_start_freeze():
    row = _row()
    row["freeze_timestamp_utc"] = row["event_start_utc"]
    ok, errors = validate_freeze(row)
    assert ok is False
    assert "FREEZE_NOT_BEFORE_EVENT_START" in errors


def test_rejects_outcome_at_freeze():
    row = _row()
    row["target_outcome"] = 1
    ok, errors = validate_freeze(row)
    assert ok is False
    assert "OUTCOME_PRESENT_AT_FREEZE" in errors


def test_counts_only_valid_unique_rows(tmp_path: Path):
    supervisor = tmp_path / "supervisor.json"
    inbox = tmp_path / "inbox.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    rows = []
    from app.market.matrix_market_portfolio import ALL_MARKETS
    for market in ALL_MARKETS:
        rows.append({
            "market_key": market.key,
            "operational_state": "LAB",
            "implementation_present": True,
            "must_continue_collecting": True,
        })
    supervisor.write_text(json.dumps({
        "status": "PASS",
        "total_required_lanes": 42,
        "rows": rows,
    }), encoding="utf-8")
    good = _row()
    bad = _row()
    bad["observation_key"] = "bad"
    bad["freeze_timestamp_utc"] = "2026-10-25T15:01:00+00:00"
    inbox.write_text(json.dumps(good) + "\n" + json.dumps(good) + "\n" + json.dumps(bad) + "\n", encoding="utf-8")
    result = build(
        supervisor_path=supervisor,
        inbox_path=inbox,
        ledger_path=ledger,
        generated_at=datetime(2026, 10, 24, 20, 0, tzinfo=timezone.utc),
    )
    assert result["total_lanes"] == 42
    assert result["counts"]["ledger_rows_total"] == 1
    assert result["lanes"]["TOTAL_GOALS_OVER_UNDER"]["prospective_unique_count"] == 1
    assert result["append_result"]["admitted_this_run"] == 1
    assert result["append_result"]["rejected_this_run"] == 2
    assert result["protections"]["real_money"] == "BLOCKED"
