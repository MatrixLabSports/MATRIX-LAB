"""Tests for SHA/PIT and duplicate-safe cohort readiness (research-only)."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import pytest
from tools.matrix_over25_cohort_progression import audit, ROOT, INVENTORY

D = "2026-11-28"

def write(path: Path, obj: dict) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj, sort_keys=True).encode()
    path.write_bytes(raw)
    return raw

def fixture(tmp_path):
    target = tmp_path / ROOT / D / "123_capture.json"
    forecast = {
        "schema":"MATRIX_INDEPENDENT_OVER25_PREMATCH_IMMUTABLE_FREEZE_V1",
        "provider":"FOOTBALL_DATA_ORG",
        "provider_fixture_id":"123",
        "provider_competition_id":"2016",
        "intake_captured_at_utc":"2026-11-22T20:00:00Z",
        "history_captured_at_utc":"2026-11-22T20:01:00Z",
        "model_calculated_at_utc":"2026-11-22T20:02:00Z",
        "sealed_at_utc":"2026-11-22T20:03:00Z",
        "kickoff_utc":"2026-11-28T15:00:00Z",
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "real_money":"BLOCKED"}
    raw = write(target, forecast)
    report = {"schema":"MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_REPORT_V1",
        "target_date_bogota":D,"production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,"real_money":"BLOCKED",
        "immutable_prematch_freeze_count":1,
        "sealed":[{"fixture_id":"123",
                   "path":str(target.relative_to(tmp_path)).replace("\\","/"),
                   "snapshot_sha256":hashlib.sha256(raw).hexdigest(),
                   "status":"FROZEN"}]}
    report_path = tmp_path / INVENTORY / D / "MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_REPORT.json"
    write(report_path, report)
    write(tmp_path / INVENTORY / "MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_LAST.json",
        {"provider":"FOOTBALL_DATA_ORG","telegram_signal_authorized":False,
         "production_p_matrix_authorized":False,"total_verified_settled_rows":1,
         "provider_competitions":[{"source_competition_id":"2016",
                                   "independent_out_of_sample_rows":1}]})
    return target, report_path

def test_prospective_frozen_cohort_kept_separate_from_settlements(tmp_path):
    fixture(tmp_path)
    result = audit(tmp_path, D)
    assert result["verified_distinct_fixture_count"] == 1
    assert result["settled_research_total_across_provider_competitions"] == 1
    assert result["provider_competitions"][0]["additional_settled_rows_needed_for_30"] == 29
    assert result["production_p_matrix_authorized"] is False

def test_previously_frozen_id_in_other_day_fails_closed(tmp_path):
    target, _ = fixture(tmp_path)
    earlier = tmp_path / ROOT / "2026-11-23" / "123_old.json"
    earlier.parent.mkdir(parents=True, exist_ok=True)
    earlier.write_bytes(target.read_bytes())
    with pytest.raises(ValueError,match="DUPLICATE_OR_UNTRUSTED_PROSPECTIVE_FIXTURE"):
        audit(tmp_path, D)

def test_modified_sha_or_post_kickoff_fails_closed(tmp_path):
    target, _ = fixture(tmp_path)
    target.write_text(target.read_text()+" ",encoding="utf-8")
    with pytest.raises(ValueError,match="FROZEN_SHA256_MISMATCH"):
        audit(tmp_path, D)
    target, report = fixture(tmp_path)
    forecast = json.loads(target.read_text())
    forecast["sealed_at_utc"] = "2026-11-29T00:00:00Z"
    raw = write(target, forecast)
    doc = json.loads(report.read_text())
    doc["sealed"][0]["snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
    write(report, doc)
    with pytest.raises(ValueError,match="FROZEN_PREMATCH_OR_GOVERNANCE_INVALID"):
        audit(tmp_path, D)
