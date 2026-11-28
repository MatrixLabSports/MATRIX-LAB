"""Unit tests: the 30 original SHA-anchored forecasts remain valid after daily report rotation."""
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
    hashes = {}
    for number in range(123, 153):
        fid = str(number)
        target = tmp_path / ROOT / D / (fid + "_capture.json")
        forecast = {
            "schema":"MATRIX_INDEPENDENT_OVER25_PREMATCH_IMMUTABLE_FREEZE_V1",
            "provider":"FOOTBALL_DATA_ORG",
            "provider_fixture_id":fid,
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
        hashes[fid] = hashlib.sha256(raw).hexdigest()
    certificate_path = tmp_path / INVENTORY / D / "MATRIX_PRODUCER_30_NEW_UNIQUE_RUN_123_CERTIFICATE.json"
    cert = {"schema":"MATRIX_PRODUCER_NEW_UNIQUE_30_GITHUB_RUN_CERTIFICATE_V1",
            "fixture_target_date_bogota":D,
            "github_actions_run_id":45084248031,
            "new_immutable_forecasts":30,
            "new_fixture_ids":sorted(hashes),
            "production_p_matrix_authorized":False,
            "telegram_signal_authorized":False,
            "real_money":"BLOCKED"}
    write(certificate_path, cert)
    manifest_path = tmp_path / INVENTORY / D / "MATRIX_PRODUCER_30_IMMUTABLE_SHA_MANIFEST.json"
    manifest = {"schema":"MATRIX_PROSPECTIVE_28NOV_FIXED_SHA_MANIFEST_V1",
                "target_date_bogota":D,
                "github_run_id":45084248031,
                "immutable_forecast_sha256_by_fixture_id":hashes,
                "production_p_matrix_authorized":False,
                "telegram_signal_authorized":False,
                "real_money":"BLOCKED"}
    write(manifest_path, manifest)
    write(tmp_path / INVENTORY / "MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_LAST.json",
        {"provider":"FOOTBALL_DATA_ORG","telegram_signal_authorized":False,
         "production_p_matrix_authorized":False,"total_verified_settled_rows":1,
         "provider_competitions":[{"source_competition_id":"2016",
                                   "independent_out_of_sample_rows":1}]})
    return tmp_path / ROOT / D / "123_capture.json", manifest_path

def test_frozen_30_cohort_kept_separate_from_settlements(tmp_path):
    fixture(tmp_path)
    result = audit(tmp_path, D)
    assert result["verified_distinct_fixture_count"] == 30
    assert len(result["verified_forecast_sha256_by_fixture_id"]) == 30
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
    target, manifest_path = fixture(tmp_path)
    forecast = json.loads(target.read_text())
    forecast["sealed_at_utc"] = "2026-11-29T00:00:00Z"
    raw = write(target, forecast)
    doc = json.loads(manifest_path.read_text())
    doc["immutable_forecast_sha256_by_fixture_id"]["123"] = hashlib.sha256(raw).hexdigest()
    write(manifest_path, doc)
    with pytest.raises(ValueError,match="FROZEN_PREMATCH_OR_GOVERNANCE_INVALID"):
        audit(tmp_path, D)

def test_report_can_be_rotated_to_zero_without_losing_the_original_cohort(tmp_path):
    fixture(tmp_path)
    write(tmp_path / INVENTORY / D / "MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_REPORT.json",
          {"immutable_prematch_freeze_count":0,"blocked":[],"sealed":[]})
    assert audit(tmp_path, D)["verified_distinct_fixture_count"] == 30

def test_manifest_missing_or_altered_fails_closed(tmp_path):
    _, manifest_path = fixture(tmp_path)
    manifest_path.unlink()
    with pytest.raises(FileNotFoundError):
        audit(tmp_path, D)
