"""Synthetic, offline receipt integrity tests. No provider calls or signals."""
import hashlib
import json
from pathlib import Path

import pytest

from tools.matrix_football_six_league_receipt_audit import audit
from tools.matrix_football_free_six_league_crosscheck import ROOT

DAY = "2026-11-19"
LEAGUE = "4328"


def write_raw(folder: Path, raw: bytes, *, valid_receipt: bool = True):
    folder.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(raw).hexdigest()
    (folder / f"MATRIX_THESPORTSDB_DAY_LEAGUE_{LEAGUE}_RAW.json").write_bytes(raw)
    receipt_file = folder / (
        f"MATRIX_THESPORTSDB_DAY_LEAGUE_{LEAGUE}_SHA256_{sha}_RECEIPT.json"
    )
    receipt = {
        "schema": "MATRIX_TSDB_LEAGUE_SOURCE_HASH_RECEIPT_V1",
        "target_date_bogota": DAY,
        "thesportsdb_league_id": LEAGUE,
        "raw_sha256": sha,
        "raw_bytes": len(raw),
        "research_only": True,
        "fixture_identity_certified": False,
        "production_p_matrix_authorized": False,
        "real_money": "BLOCKED",
    }
    if valid_receipt:
        receipt_file.write_text(json.dumps(receipt))
    return receipt_file


def test_three_missing_and_one_authentic_null_is_not_world_zero(tmp_path):
    folder = tmp_path / ROOT / DAY
    write_raw(folder, b'{"events":null}')
    result = audit(tmp_path, DAY)
    assert result["verified_league_receipts"] == 1
    assert result["unverified_league_receipts"] == 5
    row = next(x for x in result["leagues"] if x["thesportsdb_league_id"] == LEAGUE)
    assert row["status"] == "AUTHENTIC_NULL_EVENTS_NOT_WORLD_ZERO"
    assert row["events_returned"] is None
    assert result["production_p_matrix_authorized"] is False
    assert result["telegram_signal_authorized"] is False
    assert result["network_calls"] == 0


def test_legacy_raw_is_not_false_coverage(tmp_path):
    folder = tmp_path / ROOT / DAY
    write_raw(folder, b'{"events":[]}', valid_receipt=False)
    result = audit(tmp_path, DAY)
    assert result["verified_league_receipts"] == 0
    assert next(x for x in result["leagues"] if x["thesportsdb_league_id"] == LEAGUE)["status"] == (
        "LEGACY_RAW_WITHOUT_IMMUTABLE_RECEIPT"
    )


def test_tampered_source_sha_cannot_be_counted(tmp_path):
    folder = tmp_path / ROOT / DAY
    write_raw(folder, b'{"events":null}')
    (folder / f"MATRIX_THESPORTSDB_DAY_LEAGUE_{LEAGUE}_RAW.json").write_bytes(
        b'{"events":[]}'
    )
    result = audit(tmp_path, DAY)
    assert result["verified_league_receipts"] == 0


def test_tampered_receipt_fails_closed(tmp_path):
    folder = tmp_path / ROOT / DAY
    receipt_file = write_raw(folder, b'{"events":null}')
    receipt = json.loads(receipt_file.read_text())
    receipt["production_p_matrix_authorized"] = True
    receipt_file.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="SIX_LEAGUE_RECEIPT_INTEGRITY_FAILURE"):
        audit(tmp_path, DAY)


def test_bad_provider_schema_fails_closed(tmp_path):
    folder = tmp_path / ROOT / DAY
    write_raw(folder, b'{"unexpected":1}')
    with pytest.raises(ValueError, match="SIX_LEAGUE_PROVIDER_RAW_SCHEMA_INVALID"):
        audit(tmp_path, DAY)
