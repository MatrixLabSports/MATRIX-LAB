"""Every captured prelabel match must be real, immutable and never a production probability."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

import pytest

from tools.live_tennis_prospective_prelabel_freeze import collect,ARCHIVE
from tools.live_tennis_presettlement_builder import fold_for_match

DAY="2026-11-18"
NOW=datetime(2026,11,18,12,tzinfo=timezone.utc)
ROOT=Path("evidence/live_tennis_lab")/DAY

def state(mid=900001, **update):
    return {"match_id":mid,"provider":"live_tennis_api",
            "captured_at_utc":"2026-11-18T11:30:00+00:00",
            "p1_match_win":None,"label_opened":False,
            "settlement_status":"PENDING_FINAL",
            "quality_state_valid":True,"origin":"observed","stale":False,
            "sets_p1":0,"sets_p2":1,
            **update}

def source(tmp_path, rows):
    folder=tmp_path/ROOT
    folder.mkdir(parents=True,exist_ok=True)
    doc={
        "schema":"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1",
        "operational_date_bogota":DAY,
        "protections":{"real_money":"BLOCKED","odds_to_probability":False,
                       "automatic_wagering":False,
                       "outcomes_read_during_live_capture":0,"secrets_persisted":False},
        "states":rows,
    }
    (folder/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json").write_text(json.dumps(doc))
    return folder

def test_first_prelabel_snapshot_is_exact_original_byte_capture_and_split(tmp_path):
    folder=source(tmp_path,[state(),state(900002)])
    r=collect(tmp_path,DAY,now=NOW)
    assert r["status"]=="FROZEN_NEW_UNLABELED_LIVE_MATCHES_RESEARCH_ONLY"
    assert r["newly_frozen_unique_match_keys"]==2
    assert r["production_model_probability_authorized"] is False
    assert r["prospective_pit_and_oos_authorized"] is False
    archive=folder/ARCHIVE
    raw=(folder/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json").read_bytes()
    src=archive/("MATRIX_LIVE_PRELABEL_RAW_"+hashlib.sha256(raw).hexdigest()+".json")
    assert src.read_bytes()==raw
    frozen=list(archive.glob("MATRIX_LIVE_PRELABEL_BATCH_*.json"))
    assert len(frozen)==1
    doc=json.loads(frozen[0].read_bytes())
    assert doc["source_raw_sha256"]==hashlib.sha256(raw).hexdigest()
    assert doc["outcomes_read"]==0
    assert all(x["final_outcome"] is None for x in doc["matches"])
    assert doc["matches"][0]["fold_5"]==fold_for_match(900001)
    assert doc["same_match_train_test_forbidden"] is True

def test_second_cycle_never_overwrites_first_frozen_source(tmp_path):
    folder=source(tmp_path,[state()])
    r1=collect(tmp_path,DAY,now=NOW)
    first=folder/ARCHIVE/(
        "MATRIX_LIVE_PRELABEL_BATCH_"+r1["source_raw_sha256"]+".json")
    first_bytes=first.read_bytes()
    r2=collect(tmp_path,DAY,now=NOW)
    assert r2["status"]=="NO_NEW_UNLABELED_MATCHES_TO_FREEZE"
    assert r2["newly_frozen_unique_match_keys"]==0
    assert first.read_bytes()==first_bytes
    source(tmp_path,[state(),state(900002)])
    r3=collect(tmp_path,DAY,now=NOW)
    assert r3["status"]=="FROZEN_NEW_UNLABELED_LIVE_MATCHES_RESEARCH_ONLY"
    assert r3["previously_frozen_unique_match_keys"]==1
    assert r3["newly_frozen_unique_match_keys"]==1
    assert len(list((folder/ARCHIVE).glob("MATRIX_LIVE_PRELABEL_BATCH_*.json")))==2
    assert first.read_bytes()==first_bytes

def test_mixed_daily_ledger_freezes_only_a_different_never_labeled_match(tmp_path):
    folder=source(tmp_path,[state(),state(900002,p1_match_win=1,label_opened=True,
                                  settlement_status="FINAL_STANDARD")])
    r=collect(tmp_path,DAY,now=NOW)
    assert r["status"]=="FROZEN_NEW_UNLABELED_LIVE_MATCHES_RESEARCH_ONLY"
    assert r["newly_frozen_unique_match_keys"]==1
    assert r["source_labeled_physical_match_keys_quarantined"]==1
    assert r["source_contains_prior_final_labels"] is True
    assert r["unfrozen_match_keys_in_this_capture"]==1
    batches=list((folder/ARCHIVE).glob("MATRIX_LIVE_PRELABEL_BATCH_*.json"))
    assert len(batches)==1
    doc=json.loads(batches[0].read_bytes())
    assert doc["source_contains_other_prior_final_labels"] is True
    assert doc["no_outcome_values_in_source"] is False
    assert doc["unlabeled_eligible_matches_have_no_final_labels"] is True
    assert {x["match_id"] for x in doc["matches"]}=={900001}
    snapshot=list((folder/ARCHIVE).glob("MATRIX_LIVE_PRELABEL_STATES_*.json"))
    assert len(snapshot)==1
    clean=json.loads(snapshot[0].read_bytes())
    assert {x["match_id"] for x in clean["states"]}=={900001}
    for row in clean["states"]:
        assert "p1_match_win" not in row
        assert "settlement_status" not in row
        assert "label_opened" not in row
        assert "result_version" not in row
    assert doc["frozen_state_snapshot_sha256"]==hashlib.sha256(snapshot[0].read_bytes()).hexdigest()

def test_even_unopened_non_null_outcome_is_rejected(tmp_path):
    source(tmp_path,[state(p1_match_win=0,label_opened=False)])
    r=collect(tmp_path,DAY,now=NOW)
    assert r["status"]=="BLOCKED_NO_SAFE_UNLABELED_NEW_MATCH_IN_MIXED_LEDGER"

def test_missing_timestamps_and_future_captures_are_not_repaired(tmp_path):
    source(tmp_path,[state(captured_at_utc="2026-11-18T11:30:00")])
    with pytest.raises(ValueError,match="UTC_TIMESTAMP_WITHOUT_ZONE"):
        collect(tmp_path,DAY,now=NOW)
    source(tmp_path,[state(captured_at_utc="2026-11-18T15:30:00+00:00")])
    with pytest.raises(ValueError,match="PRELABEL_STATE_CAPTURE_AFTER_FREEZE"):
        collect(tmp_path,DAY,now=NOW)

def test_no_source_is_not_misreported_as_zero_matches(tmp_path):
    r=collect(tmp_path,DAY,now=NOW)
    assert r["status"]=="NO_CURRENT_CAPTURE_LEDGER"
    assert r["source_current_unique_match_keys"] is None
    assert r["prospective_pit_and_oos_authorized"] is False

def test_no_imputed_provider_identity(tmp_path):
    source(tmp_path,[state(provider=None)])
    with pytest.raises(ValueError,match="PRELABEL_MISSING_MATCH_SOURCE_IDENTITY"):
        collect(tmp_path,DAY,now=NOW)

def test_source_not_wagering_safe_cannot_be_frozen(tmp_path):
    f=source(tmp_path,[state()])
    p=f/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json"
    obj=json.loads(p.read_text())
    obj["protections"]["real_money"]="ENABLED"
    p.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match="UNSAFE_CURRENT_LIVE_LEDGER_NOT_FROZEN"):
        collect(tmp_path,DAY,now=NOW)


def test_old_label_free_records_are_not_retroactively_frozen(tmp_path):
    folder=source(tmp_path,[state(captured_at_utc="2026-11-18T10:00:00+00:00")])
    r=collect(tmp_path,DAY,now=NOW)
    assert r["status"]=="BLOCKED_NO_NEW_FRESH_QUALITY_VALID_LIVE_STATE"
    assert r["newly_frozen_unique_match_keys"]==0
    assert r["unfrozen_match_keys_in_this_capture"]==1
    assert list((folder/ARCHIVE).glob("MATRIX_LIVE_PRELABEL_BATCH_*.json"))==[]

def test_fresh_low_quality_is_not_frozen_as_a_model_observation(tmp_path):
    source(tmp_path,[state(quality_state_valid=False)])
    r=collect(tmp_path,DAY,now=NOW)
    assert r["status"]=="BLOCKED_NO_NEW_FRESH_QUALITY_VALID_LIVE_STATE"
    assert r["production_model_probability_authorized"] is False

def test_fresh_subset_never_masks_unfrozen_stale_backlog(tmp_path):
    source(tmp_path,[state(900001),state(900002,captured_at_utc="2026-11-18T09:00:00+00:00")])
    r=collect(tmp_path,DAY,now=NOW)
    assert r["status"]=="FROZEN_NEW_UNLABELED_LIVE_MATCHES_RESEARCH_ONLY"
    assert r["newly_frozen_unique_match_keys"]==1
    assert r["source_unfrozen_stale_or_low_quality_match_keys"]==1
    assert r["unfrozen_match_keys_in_this_capture"]==1


def test_same_physical_match_past_label_quarantines_all_earlier_states(tmp_path):
    folder=source(tmp_path,[
        state(900001),
        state(900001,p1_match_win=0,label_opened=True,
              settlement_status="FINAL_STANDARD"),
        state(900002)])
    r=collect(tmp_path,DAY,now=NOW)
    assert r["newly_frozen_unique_match_keys"]==1
    assert r["source_labeled_physical_match_keys_quarantined"]==1
    doc=json.loads(next((folder/ARCHIVE).glob("MATRIX_LIVE_PRELABEL_BATCH_*.json")).read_bytes())
    assert {x["match_id"] for x in doc["matches"]}=={900002}

def test_match_complete_score_is_not_prelabel_candidate_even_if_provider_omits_label(tmp_path):
    source(tmp_path,[state(sets_p1=2,sets_p2=0)])
    report=collect(tmp_path,DAY,now=NOW)
    assert report["status"]=="BLOCKED_NO_NEW_FRESH_QUALITY_VALID_LIVE_STATE"
    assert report["newly_frozen_unique_match_keys"]==0

def test_immutable_clean_state_snapshot_corruption_blocks_reuse(tmp_path):
    folder=source(tmp_path,[state()])
    first=collect(tmp_path,DAY,now=NOW)
    snap=folder/ARCHIVE/(
        "MATRIX_LIVE_PRELABEL_STATES_"+first["source_raw_sha256"]+".json")
    snap.write_bytes(snap.read_bytes()+b" ")
    with pytest.raises(ValueError,match="PRELABEL_IMMUTABLE_LIVE_STATE_SNAPSHOT_CHANGED"):
        collect(tmp_path,DAY,now=NOW)

def test_unexpected_result_fields_quarantine_entire_physical_match(tmp_path):
    folder=source(tmp_path,[state(winner=2,result_version=7)])
    result=collect(tmp_path,DAY,now=NOW)
    assert result["status"]=="BLOCKED_NO_SAFE_UNLABELED_NEW_MATCH_IN_MIXED_LEDGER"
    assert result["source_labeled_physical_match_keys_quarantined"]==1
    assert result["newly_frozen_unique_match_keys"]==0
    assert not list((folder/ARCHIVE).glob("MATRIX_LIVE_PRELABEL_BATCH_*.json"))

def test_one_labeled_source_row_never_enters_separate_clean_snapshot(tmp_path):
    folder=source(tmp_path,[state(winner=2,result_version=7),state(900002)])
    result=collect(tmp_path,DAY,now=NOW)
    assert result["newly_frozen_unique_match_keys"]==1
    clean=json.loads(next((folder/ARCHIVE).glob("MATRIX_LIVE_PRELABEL_STATES_*.json")).read_bytes())
    assert {x["match_id"] for x in clean["states"]}=={900002}
    assert all("winner" not in x and "result_version" not in x for x in clean["states"])
