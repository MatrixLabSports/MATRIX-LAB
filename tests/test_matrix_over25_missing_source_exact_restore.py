"""Actual SHA binding is required to repair research source archives."""
import hashlib
import json
from pathlib import Path

from tools.matrix_over25_missing_source_exact_restore import recover
from tools.matrix_independent_over25_prematch_freeze import SCHEMA


DAY = "2026-11-05"

def prepare(tmp_path, *, candidate=b'{"verified":true}', corrupt=False):
    archive = tmp_path / "evidence/football_research_freezes" / DAY
    archive.mkdir(parents=True)
    expected = hashlib.sha256(b'{"verified":true}').hexdigest()
    frozen = {
      "schema": SCHEMA, "provider": "FOOTBALL_DATA_ORG",
      "real_money": "BLOCKED",
      "telegram_signal_authorized": False,
      "production_p_matrix_authorized": False,
      "source_intake_file_sha256": expected,
      "source_shadow_file_sha256": expected,
    }
    forecast = archive / "555_first.json"
    forecast.write_text(json.dumps(frozen), encoding="utf-8")
    if candidate is not None:
        source = tmp_path / "evidence/football_world_inventory" / DAY / "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json"
        source.parent.mkdir(parents=True)
        source.write_bytes(candidate)
    target = archive / "sources" / (expected + ".json")
    if corrupt:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'{"corrupted":true}')
    return forecast, target, expected

def test_restore_exact_source_without_mutating_frozen_forecast(tmp_path):
    forecast, target, expected = prepare(tmp_path)
    old = forecast.read_bytes()
    report = recover(tmp_path, write=True)
    assert report["unrecoverable_source_count"] == 0
    assert report["exact_sha_restored_count"] == 1
    assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
    assert forecast.read_bytes() == old
    assert report["production_p_matrix_authorized"] is False

def test_unverified_candidate_must_not_be_restored(tmp_path):
    forecast, target, expected = prepare(tmp_path, candidate=b'{"different":true}')
    report = recover(tmp_path, write=True)
    assert report["exact_sha_restored_count"] == 0
    assert report["unrecoverable_source_count"] == 1
    assert not target.exists()
    assert report["telegram_signal_authorized"] is False

def test_existing_corruption_is_preserved_as_forensic_sidecar(tmp_path):
    _, target, expected = prepare(tmp_path, corrupt=True)
    original = target.read_bytes()
    report = recover(tmp_path, write=True)
    forensic = target.parent / "corrupted_originals" / (hashlib.sha256(original).hexdigest() + ".json")
    assert report["exact_sha_restored_count"] == 1
    assert forensic.read_bytes() == original
    assert hashlib.sha256(target.read_bytes()).hexdigest() == expected

def test_dry_run_never_writes_even_if_exact_source_exists(tmp_path):
    _, target, _ = prepare(tmp_path)
    report = recover(tmp_path, write=False)
    assert report["exact_sha_restored_count"] == 1
    assert report["exact_sha_restored"][0]["action"] == "EXACT_SHA_AVAILABLE_NOT_WRITTEN"
    assert not target.exists()

def test_original_sha_can_be_recovered_from_reformatted_same_content(tmp_path):
    _, target, expected = prepare(tmp_path, candidate=None, corrupt=True)
    altered = b'{\\n  "verified": true\\n}\\n'.decode("unicode_escape").encode("utf-8")
    target.write_bytes(altered)
    report = recover(tmp_path, write=True)
    assert report["exact_sha_restored_count"] == 1
    assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
    forensic = target.parent / "corrupted_originals" / (hashlib.sha256(altered).hexdigest() + ".json")
    assert forensic.read_bytes() == altered
