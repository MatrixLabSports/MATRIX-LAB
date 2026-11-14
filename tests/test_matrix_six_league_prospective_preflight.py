"""Six-league preflight is research-only, never automatically selects cohorts."""
import json
from pathlib import Path
import pytest
from tools.matrix_six_league_prospective_preflight import assess

D="evidence/football_world_inventory/2026-11-04/MATRIX_ORIGINAL_ARCHIVE_LEAGUE_DISCOVERY.json"
R="evidence/api_football/governance/alternative_producer_original_six_league_registry.json"

def fixture(tmp_path):
    p=tmp_path/D
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({
        "schema":"MATRIX_ORIGINAL_ARCHIVE_LEAGUE_DISCOVERY_V1",
        "archived_reference_group_count":7,
        "reference_groups":[{"original_league_id":x,"season":2026,
             "archive_files":[f"evidence/api_football/example_{x}.bin"]} for x in range(1,8)]
    }),encoding="utf-8")
    return p

def reg(tmp_path,ids,approved=True):
    path=tmp_path/R;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({
        "schema":"MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1",
        "original_six_league_ids":ids,
        "scope_approved":approved,
        "source":"ORIGINAL_FROZEN_MODEL",
        "telegram_signal_authorized":False,
        "real_money":"BLOCKED"
    }),encoding="utf-8")

def test_archive_alone_does_not_choose_six(tmp_path):
    fixture(tmp_path)
    r=assess(tmp_path)
    assert r["original_archive_group_count"]==7
    assert r["original_archived_unique_league_count"]==7
    assert r["six_league_ids"]==[]
    assert "ORIGINAL_SIX_LEAGUE_COHORT_NOT_APPROVED" in r["missing_evidence"]
    assert r["scientific_oos_validation_passed"] is False
    assert r["production_p_matrix_authorized"] is False

def test_explicit_six_archived_scope_still_needs_prospective_proofs(tmp_path):
    fixture(tmp_path);reg(tmp_path,[str(i) for i in range(1,7)])
    r=assess(tmp_path)
    assert r["six_league_registry_approved"] is True
    assert r["selected_six_leagues_present_in_original_archive"] is True
    assert len(r["leagues"])==6
    assert all(x["valid_prospective_rows"]==0 and
               x["unverified_must_not_be_interpreted_as_absent"] for x in r["leagues"])
    assert r["scientific_oos_validation_passed"] is False
    assert r["telegram_signal_authorized"] is False

def test_unapproved_or_duplicated_registry_never_selects_leagues(tmp_path):
    fixture(tmp_path)
    reg(tmp_path,[str(i) for i in range(1,7)],approved=False)
    assert assess(tmp_path)["six_league_ids"]==[]
    reg(tmp_path,["1"]*6)
    assert assess(tmp_path)["six_league_ids"]==[]

def test_missing_original_archive_scope_fails_closed(tmp_path):
    fixture(tmp_path)
    reg(tmp_path,["1","2","3","4","5","99"])
    r=assess(tmp_path)
    assert r["selected_six_leagues_present_in_original_archive"] is False
    assert "SELECTED_SIX_LEAGUES_NOT_ALL_IN_ORIGINAL_ARCHIVE" in r["missing_evidence"]

def test_tampered_discovery_count_is_rejected(tmp_path):
    path=fixture(tmp_path)
    document=json.loads(path.read_text())
    document["archived_reference_group_count"]=476
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError,match="GROUP_COUNT_MISMATCH"):
        assess(tmp_path)
