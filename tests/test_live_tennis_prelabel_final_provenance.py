"""Strict forward-link only: final response timestamp != independent match end time."""
import json
from datetime import datetime,timezone
from pathlib import Path

import pytest

from tools.live_tennis_prelabel_final_provenance import (
    archive_current_final,git_blob_sha,link
)
from tools.live_tennis_prospective_prelabel_freeze import collect

DAY="2026-11-18"
NOW=datetime(2026,11,18,12,tzinfo=timezone.utc)
BASE=Path("evidence/live_tennis_lab")/DAY

def source(root):
    folder=root/BASE
    folder.mkdir(parents=True,exist_ok=True)
    d={
        "schema":"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1",
        "operational_date_bogota":DAY,
        "protections":{"real_money":"BLOCKED","odds_to_probability":False,
            "automatic_wagering":False,"outcomes_read_during_live_capture":0,
            "secrets_persisted":False},
        "states":[
            {"provider":"live_tennis_api","match_id":100,"label_opened":True,
             "p1_match_win":1,"settlement_status":"FINAL_STANDARD",
             "captured_at_utc":"2026-11-18T10:00:00+00:00",
             "quality_state_valid":False,"origin":"observed","stale":True,
             "sets_p1":2,"sets_p2":0},
            *[
                {"provider":"live_tennis_api","match_id":mid,"label_opened":False,
                 "p1_match_win":None,"settlement_status":"PENDING_FINAL",
                 "captured_at_utc":"2026-11-18T11:54:00+00:00",
                 "quality_state_valid":True,"origin":"observed","stale":False,
                 "sets_p1":1,"sets_p2":0,
                 "state_key":f"live_tennis_api:{mid}:sequence:10"}
                for mid in (900001,900002)
            ],
        ],
    }
    (folder/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json").write_text(json.dumps(d))
    freeze=collect(root,DAY,now=NOW)
    assert freeze["newly_frozen_unique_match_keys"]==2
    return folder

def record(mid=900001,winner=1,when="2026-11-18T12:15:00+00:00"):
    return {"match_id":mid,"status":"completed","outcome":"completed",
        "winner":winner,"result_version":1,"result_restated_at":None,
        "settled_at_utc":when}

def report(folder,records):
    doc={
        "schema":"MATRIX_LIVE_TENNIS_SETTLEMENT_SYNC_V0_1",
        "generated_at_utc":"2026-11-18T12:20:00+00:00",
        "source_ledger":(BASE/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json").as_posix(),
        "standard_final_settlements":records,
        "protections":{"real_money":"BLOCKED","final_only":True,
            "odds_to_probability":False},
    }
    path=folder/"MATRIX_LIVE_TENNIS_SETTLEMENT_SYNC_V0_1.json"
    path.write_text(json.dumps(doc))
    return path

def test_real_scenario_one_result_after_freeze_does_not_open_model(tmp_path):
    folder=source(tmp_path)
    report(folder,[record(),record(999999)])
    d=link(tmp_path,DAY)
    assert d["frozen_physical_matches"]==2
    assert d["verified_immutable_final_report_count"]==1
    assert d["status_counts"]["FINAL_OBSERVED_AFTER_FREEZE_ACTUAL_END_TIME_UNVERIFIED"]==1
    assert d["status_counts"]["FINAL_RESULT_NOT_YET_PRESERVED"]==1
    row=next(x for x in d["rows"] if x["physical_match_key"]=="live_tennis_api:900001")
    assert row["final_winner"]==1
    assert row["actual_event_completion_time_independently_verified"] is False
    assert row["prospective_holdout_admitted"] is False
    assert d["model_probability_authorized"] is False
    assert d["telegram_signal_authorized"] is False
    assert d["real_money"]=="BLOCKED"
    assert len(list((folder/"settlement_immutable").glob("MATRIX_LIVE_FINAL_SYNC_SHA256_*.json")))==1

def test_unsettled_matches_are_pending_not_zero_or_lost(tmp_path):
    source(tmp_path)
    d=link(tmp_path,DAY)
    assert d["verified_immutable_final_report_count"]==0
    assert d["status_counts"]=={"FINAL_RESULT_NOT_YET_PRESERVED":2}
    assert all(x["final_winner"] is None for x in d["rows"])

def test_final_report_observed_before_freeze_is_quarantined(tmp_path):
    folder=source(tmp_path)
    report(folder,[record(when="2026-11-18T11:59:00+00:00")])
    d=link(tmp_path,DAY)
    assert d["status_counts"]["FINAL_ALREADY_OBSERVED_BEFORE_OR_AT_FREEZE_QUARANTINED"]==1
    row=next(x for x in d["rows"] if x["physical_match_key"]=="live_tennis_api:900001")
    assert row["final_winner"] is None

def test_newer_reversing_final_is_conflict_not_overwrite(tmp_path):
    folder=source(tmp_path)
    report(folder,[record(winner=1)])
    d=link(tmp_path,DAY)
    assert d["status_counts"]["FINAL_OBSERVED_AFTER_FREEZE_ACTUAL_END_TIME_UNVERIFIED"]==1
    report(folder,[record(winner=2,when="2026-11-18T12:18:00+00:00")])
    d=link(tmp_path,DAY)
    assert d["verified_immutable_final_report_count"]==2
    assert d["status_counts"]["FINAL_WINNER_CONFLICT_QUARANTINED"]==1
    assert next(x for x in d["rows"] if x["physical_match_key"]=="live_tennis_api:900001")["final_winner"] is None

def test_genuine_historic_git_blob_receipt_can_be_verified_without_new_live_query(tmp_path):
    folder=source(tmp_path)
    src=report(folder,[record()])
    raw=src.read_bytes()
    (folder/"settlement_immutable").mkdir()
    archived=folder/"settlement_immutable"/("MATRIX_LIVE_FINAL_SYNC_GITBLOB_"+git_blob_sha(raw)+".json")
    archived.write_bytes(raw)
    src.unlink()
    d=link(tmp_path,DAY,archive_current=False)
    assert d["status_counts"]["FINAL_OBSERVED_AFTER_FREEZE_ACTUAL_END_TIME_UNVERIFIED"]==1
    archived.write_bytes(raw+b" ")
    with pytest.raises(ValueError,match="FINAL_ARCHIVE_GIT_BLOB_IMMUTABILITY_VIOLATION"):
        link(tmp_path,DAY,archive_current=False)

def test_new_immutable_sha256_archive_detects_mutation(tmp_path):
    folder=source(tmp_path)
    report(folder,[record()])
    p=archive_current_final(folder,DAY)
    a=folder/"settlement_immutable"/p
    a.write_bytes(a.read_bytes()+b" ")
    with pytest.raises(ValueError,match="FINAL_REPORT_ARCHIVE_SHA_COLLISION_OR_MUTATION"):
        link(tmp_path,DAY)

def test_tampered_prelabel_snapshot_cannot_backfill_final(tmp_path):
    folder=source(tmp_path)
    report(folder,[record()])
    p=next((folder/"prelabel_immutable").glob("MATRIX_LIVE_PRELABEL_STATES_*.json"))
    p.write_bytes(p.read_bytes()+b" ")
    with pytest.raises(ValueError,match="PRELABEL_FROZEN_STATE_SNAPSHOT_HASH_INVALID"):
        link(tmp_path,DAY)

def test_nonstandard_walkover_or_boolean_winner_is_rejected(tmp_path):
    folder=source(tmp_path)
    report(folder,[{**record(), "outcome":"walkover"}])
    with pytest.raises(ValueError,match="FINAL_PROVIDER_ROW_NOT_STANDARD_COMPLETED"):
        link(tmp_path,DAY)
    report(folder,[record(winner=True)])
    with pytest.raises(ValueError,match="FINAL_PROVIDER_ROW_NOT_STANDARD_COMPLETED"):
        link(tmp_path,DAY)

def test_source_report_must_be_from_the_same_operational_day(tmp_path):
    folder=source(tmp_path)
    r=report(folder,[record()])
    doc=json.loads(r.read_text())
    doc["source_ledger"]="evidence/live_tennis_lab/2026-11-17/MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json"
    r.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match="FINAL_PROVIDER_REPORT_NOT_GOVERNED"):
        link(tmp_path,DAY)
