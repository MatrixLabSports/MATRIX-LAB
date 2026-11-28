"""Run against physical frozen research snapshots. Never modify calibration.

Some assertions intentionally use the known 2026-11-21 prospective cohort.
Only fixtures from actual saved GitHub evidence count as production evidence.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from tools import matrix_hybrid_elite_research_pair_bridge as gate

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc)
DAY = "2026-11-21"
F = "560643"


def sample_tree(tmp: Path):
    home = ROOT / "evidence/football_world_inventory" / DAY / "MATRIX_FREE_POISSON_V1_IMMUTABLE" / (F + ".json")
    archived = ROOT / "evidence/football_research_freezes" / DAY / "560643_fe3c7660d1604deff4b2.json"
    old = json.loads(archived.read_text(encoding="utf-8"))
    files = [home, archived,
             ROOT / old["source_intake_file_path"],
             ROOT / old["source_shadow_file_path"]]
    for src in files:
        dest = tmp / src.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return (tmp / home.relative_to(ROOT)), (tmp / archived.relative_to(ROOT)), old


def test_verified_physical_cohort_37_exact_same_event_prelabeled_pairs():
    result = gate.prepare(ROOT, now=NOW, day=DAY)
    assert result["recovered_research_pair_count"] == 37, result["rejected"]
    assert result["rejected_research_pair_count"] == 0
    assert len({x["physical_event_id"] for x in result["prelabel_research_pairs"]}) == 37
    assert all(x["same_authenticated_input_evidence"] is True for x in result["prelabel_research_pairs"])
    assert all(x["postmatch_outcome_included"] is False for x in result["prelabel_research_pairs"])
    assert all(x["formal_hybrid_lab_admission_authorized"] is False for x in result["prelabel_research_pairs"])
    assert result["formal_hybrid_elite_lab_rows_admitted"] == 0
    assert result["real_money"] == "BLOCKED"
    assert result["telegram_signal_authorized"] is False


def test_subset_recoverable_from_original_sha_bound_evidence(tmp_path):
    sample_tree(tmp_path)
    result = gate.prepare(tmp_path, now=NOW, day=DAY)
    assert result["recovered_research_pair_count"] == 1, result["rejected"]
    assert not result["rejected"]
    assert result["prelabel_research_pairs"][0]["physical_event_id"] == F
    assert result["prelabel_research_pairs"][0]["original_official_p_matrix_certified"] is False


def test_source_shadow_bytes_tamper_fails_closed(tmp_path):
    _, _, old = sample_tree(tmp_path)
    path = tmp_path / old["source_shadow_file_path"]
    path.write_bytes(path.read_bytes() + b" ")
    result = gate.prepare(tmp_path, now=NOW, day=DAY)
    assert result["recovered_research_pair_count"] == 0
    assert "SOURCE_BYTES_SHA_MISMATCH" in result["rejected"][0]["reason"]


def test_silent_source_fixture_identity_change_fails_closed(tmp_path):
    po, _, _ = sample_tree(tmp_path)
    row = json.loads(po.read_text(encoding="utf-8"))
    row["away"] = "Another Team"
    po.write_text(json.dumps(row), encoding="utf-8")
    result = gate.prepare(tmp_path, now=NOW, day=DAY)
    assert result["recovered_research_pair_count"] == 0
    assert "RESEARCH_PROVIDER_IDENTITIES_NOT_EQUAL" in result["rejected"][0]["reason"]


def test_forecast_postkickoff_is_never_admitted(tmp_path):
    po, _, _ = sample_tree(tmp_path)
    row = json.loads(po.read_text(encoding="utf-8"))
    row["forecast_frozen_at_utc"] = "2026-11-21T13:30:00+00:00"
    po.write_text(json.dumps(row), encoding="utf-8")
    result = gate.prepare(tmp_path, now=datetime(2026,11,22,tzinfo=timezone.utc), day=DAY)
    assert result["recovered_research_pair_count"] == 0
    assert "FREE_POISSON_NOT_PROSPECTIVE" in result["rejected"][0]["reason"]


def test_original_research_probability_invalid_fails_closed(tmp_path):
    _, original_file, _ = sample_tree(tmp_path)
    original = json.loads(original_file.read_text(encoding="utf-8"))
    original["research_probability_over25"] = 1.2
    original_file.write_text(json.dumps(original), encoding="utf-8")
    result = gate.prepare(tmp_path, now=NOW, day=DAY)
    assert result["recovered_research_pair_count"] == 0
    assert "ORIGINAL_RESEARCH_PROBABILITY_INVALID" in result["rejected"][0]["reason"]


def test_absent_real_history_does_not_claim_predictions(tmp_path):
    result = gate.prepare(tmp_path, now=NOW, day=DAY)
    assert result["recovered_research_pair_count"] == 0
    assert result["formal_hybrid_elite_lab_rows_admitted"] == 0
    assert result["prelabel_research_pairs"] == []
