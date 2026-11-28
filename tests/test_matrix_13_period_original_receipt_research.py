"""Defensive synthetic tests: no fake halftime scores, no cohort promotion."""
import hashlib
import json
from datetime import datetime, timezone

import pytest
from tools import matrix_13_period_original_receipt_research as lab


def receipt(halftime, final=(2, 1)):
    return {
        "errors": [], "results": 1,
        "response": [{
            "fixture": {"id": "123", "date": "2026-10-25T20:00:00+00:00",
                        "status": {"short": "FT"}},
            "score": {
                "halftime": {"home": halftime[0], "away": halftime[1]},
                "fulltime": {"home": final[0], "away": final[1]},
            },
            "goals": {"home": final[0], "away": final[1]},
        }],
    }


def write_receipt(folder, halftime):
    raw = json.dumps(receipt(halftime)).encode()
    (folder / "fixture_123.bin").write_bytes(raw)
    return {"result_payload_sha256": hashlib.sha256(raw).hexdigest()}


def test_source_null_halftime_stays_blocked(tmp_path):
    token = write_receipt(tmp_path, [None, None])
    item = lab.quality_detail("123", token, tmp_path)
    assert item["classification"] == "PROVIDER_HALFTIME_NULL_OR_MISSING"
    assert item["source_sha256_matches"] is True
    assert item["not_a_usable_halftime_label"] is True


def test_receipt_with_wrong_sha_never_certified(tmp_path):
    write_receipt(tmp_path, [1, 0])
    result = lab.quality_detail("123", {"result_payload_sha256": "a"*64}, tmp_path)
    assert result["classification"] == "ORIGINAL_MATCH_RECEIPT_SHA256_MISMATCH"
    assert result["source_sha256_matches"] is False


def test_wrong_half_score_type_is_not_zero(tmp_path):
    token = write_receipt(tmp_path, ["1", 0])
    result = lab.quality_detail("123", token, tmp_path)
    assert result["classification"] == "PROVIDER_HALFTIME_WRONG_TYPE_OR_NEGATIVE"
    assert result["not_a_usable_halftime_label"] is True


def test_missing_original_match_receipt_is_not_a_goal_label(tmp_path):
    result = lab.quality_detail("123", {"result_payload_sha256": "a"*64}, tmp_path)
    assert result["classification"] == "MISSING_ORIGINAL_MATCH_RECEIPT"
    assert result["source_sha256_matches"] is False


def test_readonly_triage_six_independent_lanes(monkeypatch, tmp_path):
    rows = []
    for lane in lab.PERIOD_LANES:
        rows.append({
            "market_lane": lane, "fixture_id": "123",
            "event_start_utc": "2026-10-25T20:00:00+00:00",
            "freeze_timestamp_utc": "2026-10-25T19:00:00+00:00",
        })
    def fake_build(*args, **kwargs):
        return {"lanes": [{"market_key": k, "blockers": {}}
                          for k in lab.PERIOD_LANES]}
    monkeypatch.setattr(lab, "build", fake_build)
    token = write_receipt(tmp_path, [None, None])
    original = {
        "fixture_id": "123", "result_source_provider": "api_football",
        "kickoff_utc": "2026-10-25T20:00:00+00:00",
        "freeze_at_utc": "2026-10-25T19:00:00+00:00",
        "fulltime_home_goals": 2, "fulltime_away_goals": 1,
        **token,
    }
    result = lab.inspect({}, rows, [original], [], rawdir=tmp_path)
    assert result["unique_fixture_issue_counts"]["INVALID_RAW_HALF_OR_FINAL_SCORE"] == 1
    assert result["source_problem_details"][0]["raw_field_diagnostic"]["classification"] == "PROVIDER_HALFTIME_NULL_OR_MISSING"
    assert result["new_halftime_labels_written"] == 0
    assert result["model_parameters_changed"] is False
    assert result["telegram_authorized"] is False
    assert result["real_money"] == "BLOCKED"


def test_no_final_does_not_trigger_halftime_guess(monkeypatch, tmp_path):
    monkeypatch.setattr(lab, "build", lambda *args,**kwargs: {
        "lanes": [{"market_key": k, "blockers": {}} for k in lab.PERIOD_LANES]
    })
    rows = [
        {"fixture_id": "456", "market_lane": lane,
         "event_start_utc": "2026-10-25T20:00:00+00:00",
         "freeze_timestamp_utc": "2026-10-25T19:00:00+00:00"}
        for lane in lab.PERIOD_LANES
    ]
    result = lab.inspect({}, rows, [], [], rawdir=tmp_path)
    assert result["unique_fixture_issue_counts"]["NO_STANDARD_FT"] == 1
    assert result["new_halftime_labels_written"] == 0
    assert result["source_problem_details"] == []


def test_archived_kickoff_drift_is_measured_not_auto_corrected(tmp_path):
    token = write_receipt(tmp_path, [1, 0])
    token["kickoff_utc"] = "2026-10-25T19:30:00+00:00"
    result = lab.quality_detail("123", token, tmp_path)
    assert result["source_sha256_matches"] is True
    assert result["raw_kickoff_minus_frozen_kickoff_minutes"] == 30
    assert result["raw_fixture_id_equals_frozen_id"] is True
    assert result["raw_status_is_standard_ft"] is True
    assert result["not_a_usable_halftime_label"] is True


def test_no_drift_guess_when_original_kickoff_absent(tmp_path):
    token = write_receipt(tmp_path, [1, 0])
    result = lab.quality_detail("123", token, tmp_path)
    assert result["raw_kickoff_minus_frozen_kickoff_minutes"] is None
    assert result["not_a_usable_halftime_label"] is True
