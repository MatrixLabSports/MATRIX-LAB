"""Repository-derived six-league inventory contract tests; synthetic paths are not evidence."""
import json
from pathlib import Path
import pytest
from tools.matrix_six_league_existing_evidence_recovery import evaluate, relative_paths, OUTPUT

IDS=["39","61","78","135","140","239"]
REG="evidence/api_football/governance/alternative_producer_original_six_league_registry.json"
DISC="evidence/football_world_inventory/2026-11-04/MATRIX_ORIGINAL_ARCHIVE_LEAGUE_DISCOVERY.json"

def files(tmp_path):
    a=tmp_path/REG
    a.parent.mkdir(parents=True)
    a.write_text(json.dumps({"schema":"MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1",
        "scope_approved":True,"real_money":"BLOCKED","telegram_signal_authorized":False,
        "original_six_league_ids":IDS}),encoding="utf-8")
    b=tmp_path/DISC
    b.parent.mkdir(parents=True)
    b.write_text(json.dumps({"reference_groups":[{
        "original_league_id":int(i),"season":2026,
        "archive_files":[f"evidence/api_football/prospective_daily/2026-10-10/c/history/raw/league_{i}_season_2026.bin"]
        } for i in IDS]}),encoding="utf-8")

def test_original_archives_are_not_prospective_predictions(tmp_path):
    files(tmp_path)
    sample=[f"evidence/api_football/prospective_daily/2026-10-10/c/history/raw/league_{i}_season_2026.bin" for i in IDS]
    doc=evaluate(tmp_path,sample)
    assert all(r["original_archived_raw_group_files_in_discovery"]==1 for r in doc["leagues"])
    assert all(r["certified_prospective_rows_from_strict_manifest"]==0 for r in doc["leagues"])
    assert all(r["remaining_verified_rows_to_minimum"]==30 for r in doc["leagues"])
    assert doc["strict_oos_manifest_paths"]==[]
    assert doc["production_p_matrix_authorized"] is False
    assert doc["telegram_signal_authorized"] is False

def test_research_shadow_does_not_become_an_oos_snapshot(tmp_path):
    files(tmp_path)
    doc=evaluate(tmp_path,["evidence/football_world_inventory/2026-11-04/MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"])
    assert doc["category_counts_all_leagues"]["research_shadow_json_files"]==1
    assert doc["prospective_filename_candidate_count"]==0
    assert all(x["certified_prospective_rows_from_strict_manifest"]==0 for x in doc["leagues"])

def test_forged_manifest_name_cannot_certify(tmp_path):
    files(tmp_path)
    path="evidence/football_world_inventory/2026-11-04/MATRIX_ALTERNATIVE_PRODUCER_PROSPECTIVE_EVIDENCE.json"
    p=tmp_path/path
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps({"schema":"MATRIX_ALTERNATIVE_PRODUCER_PROSPECTIVE_EVIDENCE_V1",
        "original_six_league_ids":IDS,"rows":[{"source_verified":True}],
        "real_money":"BLOCKED","signal_generation_authorized":False}),encoding="utf-8")
    doc=evaluate(tmp_path,[path])
    assert doc["strict_oos_manifest_paths"]==[path]
    assert doc["strict_oos_manifest_results"][0]["status"]!="PASS_SIX_LEAGUE_ENRICHED_PROSPECTIVE_OOS"
    assert all(x["certified_prospective_rows_from_strict_manifest"]==0 for x in doc["leagues"])

def test_not_approved_fails_closed(tmp_path):
    files(tmp_path)
    p=tmp_path/REG
    d=json.loads(p.read_text(encoding="utf-8"));d["scope_approved"]=False
    p.write_text(json.dumps(d),encoding="utf-8")
    with pytest.raises(ValueError,match="SIX_LEAGUES_UNGOVERNED"):
        evaluate(tmp_path,[])

def test_only_git_tracked_files_scan(tmp_path):
    import subprocess
    subprocess.run(["git","init","-q",str(tmp_path)],check=True)
    a=tmp_path/"evidence"/"demo.json";a.parent.mkdir();a.write_text("{}")
    b=tmp_path/"evidence"/"secret.json";b.write_text("{}")
    subprocess.run(["git","-C",str(tmp_path),"add","--","evidence/demo.json"],check=True)
    result=relative_paths(tmp_path)
    assert result==["evidence/demo.json"]
