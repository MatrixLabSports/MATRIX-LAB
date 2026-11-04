"""Only actual frozen probability flags count as produced forecasts."""
import json
from pathlib import Path
from tools.matrix_original_canonical_probability_manifest_audit import analyse

def setup(tmp_path,generated=False,status="NOT_GENERATED"):
    p=tmp_path/"evidence/api_football/prospective_daily/2026-10-24/canonical/canonical_analysis/manifest.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"provider":"api_football","real_money":"BLOCKED",
       "model_probability_generated":generated,"p_matrix_status":status,
       "ready_input_count":344}),encoding="utf-8")
    return str(p.relative_to(tmp_path))

def test_archived_inputs_never_count_as_p_matrix(tmp_path):
    name=setup(tmp_path)
    r=analyse(tmp_path,[name])
    assert r["verified_manifest_count"]==1
    assert r["manifest_files_with_generated_probability_false"]==1
    assert r["sum_ready_input_counts_across_snapshots_not_unique_fixtures"]==344
    assert r["potential_probability_manifest_count"]==0
    assert r["production_p_matrix_authorized"] is False

def test_generated_probability_is_candidate_for_manual_verification_only(tmp_path):
    name=setup(tmp_path,True,"GENERATED")
    r=analyse(tmp_path,[name])
    assert r["manifest_files_with_generated_probability_true"]==1
    assert r["potential_probability_manifest_count"]==1
    assert r["telegram_signal_authorized"] is False
    assert r["six_league_prospective_parity_certified"] is False

def test_untrusted_missing_status_fails_closed(tmp_path):
    name=setup(tmp_path)
    p=tmp_path/name
    d=json.loads(p.read_text());d.pop("p_matrix_status")
    p.write_text(json.dumps(d))
    r=analyse(tmp_path,[name])
    assert r["verified_manifest_count"]==0
    assert r["rejected_manifest_count"]==1

def test_only_original_producer_considered(tmp_path):
    name=setup(tmp_path)
    p=tmp_path/name
    d=json.loads(p.read_text());d["provider"]="independent"
    p.write_text(json.dumps(d))
    r=analyse(tmp_path,[name])
    assert r["potential_probability_manifest_count"]==0
    assert r["rejected_manifest_count"]==1
