"""Physical duplicate snapshot provenance; synthetic edits remain in tmp_path."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools import matrix_hybrid_original_dual_freeze_lineage as lineage

ROOT = Path(__file__).resolve().parents[1]


def sample_root(tmp_path):
    original_manifest = json.loads((ROOT / lineage.SOURCE).read_bytes())
    first_pair = original_manifest["prelabel_research_pairs"][0]
    fid = first_pair["physical_event_id"]
    scoped = {**original_manifest,
              "prelabel_research_pairs": [first_pair],
              "recovered_research_pair_count": 1}
    p = tmp_path / lineage.SOURCE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(scoped, sort_keys=True) + "\n", encoding="utf-8")
    pairpath = Path(first_pair["original_freeze_path"])
    sources = list((ROOT / pairpath.parent).glob(fid + "_*.json"))
    assert len(sources) == 2
    for src in sources:
        dest = tmp_path / src.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return first_pair, sources


def test_all_37_real_original_pairs_have_two_individually_verified_freezes():
    result = lineage.run(ROOT)
    assert result["physical_fixture_count"] == 37
    assert result["lineage_matched_fixture_count"] == 37, result["rejected"]
    assert result["lineage_rejected_fixture_count"] == 0
    assert result["two_snapshot_fixture_count"] == 37
    assert len({r["fixture_id"] for r in result["matched"]}) == 37
    assert all(r["same_authenticated_source_history"] for r in result["matched"])
    assert all(r["same_formula_probability"] for r in result["matched"])
    assert all(r["distinct_files"] for r in result["matched"])
    assert all(r["one_physical_fixture_count"] == 1 for r in result["matched"])
    assert result["first_frozen_forecast_wins_settlement"] is True
    assert result["telegram_signal_authorized"] is False


def test_subsample_lineage_can_be_recovered_from_physical_sources(tmp_path):
    first, files = sample_root(tmp_path)
    report = lineage.run(tmp_path)
    assert report["physical_fixture_count"] == 1
    assert report["lineage_matched_fixture_count"] == 1
    assert report["lineage_rejected_fixture_count"] == 0
    assert report["matched"][0]["fixture_id"] == first["physical_event_id"]


def test_modified_earliest_source_sha_rejects_without_new_observation(tmp_path):
    _, files = sample_root(tmp_path)
    earliest = min(files, key=lambda p: json.loads(p.read_bytes())["sealed_at_utc"])
    dest = tmp_path / earliest.relative_to(ROOT)
    obj = json.loads(dest.read_bytes())
    obj["source_snapshot_sha256"] = "0"*64
    dest.write_text(json.dumps(obj), encoding="utf-8")
    r = lineage.run(tmp_path)
    assert r["lineage_matched_fixture_count"] == 0
    assert "FIRST_AND_RESEARCH_HISTORY_SHA_MISMATCH" in r["rejected"][0]["reason"]


def test_modified_earliest_probability_fails_closed(tmp_path):
    _, files = sample_root(tmp_path)
    earliest = min(files, key=lambda p: json.loads(p.read_bytes())["sealed_at_utc"])
    dest = tmp_path / earliest.relative_to(ROOT)
    obj = json.loads(dest.read_bytes())
    obj["research_probability_over25"] = 0.2
    dest.write_text(json.dumps(obj), encoding="utf-8")
    r = lineage.run(tmp_path)
    assert r["lineage_matched_fixture_count"] == 0
    assert "FIRST_AND_RESEARCH_PROBABILITY_MISMATCH" in r["rejected"][0]["reason"]


def test_promoted_snapshot_is_always_rejected(tmp_path):
    _, files = sample_root(tmp_path)
    dest = tmp_path / files[0].relative_to(ROOT)
    obj = json.loads(dest.read_bytes())
    obj["production_p_matrix_authorized"] = True
    dest.write_text(json.dumps(obj), encoding="utf-8")
    r = lineage.run(tmp_path)
    assert r["lineage_matched_fixture_count"] == 0
    assert "UNTRUSTED_FORECAST_GOVERNANCE" in r["rejected"][0]["reason"]
