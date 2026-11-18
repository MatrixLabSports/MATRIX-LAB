"""FINAL detail-query rotation remains quota-bound and changes no match result."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest

from tools.live_tennis_settlement_sync import (
    fair_departed_queue, historical_query_attempts, frozen_match_ids
)

def receipt(*ids):
    return {"schema":"MATRIX_LIVE_TENNIS_SETTLEMENT_SYNC_V0_1",
            "queried_match_ids":list(ids),"standard_final_settlements":[],
            "protections":{"real_money":"BLOCKED"}}

def test_unqueried_matches_win_before_repeated_old_ids():
    ordered=fair_departed_queue([101,102,103],{101:3,102:1},{101,103})
    assert ordered==[103,102,101]
    assert ordered[:2]==[103,102]

def test_frozen_match_priority_breaks_only_equal_query_history():
    assert fair_departed_queue([101,103,102],{101:1,102:1,103:1},{103})==[103,101,102]
    assert fair_departed_queue([101,102],{101:2,102:1},{101})==[102,101]

def test_exact_receipt_dedup_prevents_duplicate_attempts(tmp_path):
    current=tmp_path/"MATRIX_LIVE_TENNIS_SETTLEMENT_SYNC_V0_1.json"
    body=json.dumps(receipt(101,102))
    current.write_text(body)
    archive=tmp_path/"settlement_immutable"
    archive.mkdir()
    (archive/("MATRIX_LIVE_FINAL_SYNC_SHA256_"+hashlib.sha256(body.encode()).hexdigest()+".json")).write_text(body)
    (archive/"MATRIX_LIVE_FINAL_SYNC_SHA256_synthetic_second.json").write_text(json.dumps(receipt(101,103)))
    attempts=historical_query_attempts(current)
    assert attempts=={101:2,102:1,103:1}

def test_invalid_or_fabricated_receipts_fail_closed(tmp_path):
    current=tmp_path/"MATRIX_LIVE_TENNIS_SETTLEMENT_SYNC_V0_1.json"
    current.write_text(json.dumps({"schema":"OTHER","queried_match_ids":[1]}))
    with pytest.raises(ValueError,match="SETTLEMENT_QUERY_RECEIPT_SCHEMA_INVALID"):
        historical_query_attempts(current)
    current.write_text(json.dumps(receipt(True)))
    with pytest.raises(ValueError,match="SETTLEMENT_QUERY_RECEIPT_IDS_INVALID"):
        historical_query_attempts(current)

def test_frozen_manifest_is_identity_only_not_final(tmp_path):
    lp=tmp_path/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json"
    a=tmp_path/"prelabel_immutable"
    a.mkdir()
    (a/"MATRIX_LIVE_PRELABEL_BATCH_abc.json").write_text(json.dumps({
        "schema":"MATRIX_LIVE_TENNIS_PRELABEL_CAPTURE_BATCH_V1",
        "real_money":"BLOCKED","model_probability_authorized":False,
        "matches":[
          {"match_id":101,"physical_match_key":"live_tennis_api:101"},
          {"match_id":103,"physical_match_key":"live_tennis_api:103"},
        ]}))
    assert frozen_match_ids(lp)=={101,103}

def test_fake_batch_and_bad_match_id_not_used_to_prioritize(tmp_path):
    lp=tmp_path/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json"
    arc=tmp_path/"prelabel_immutable"
    arc.mkdir()
    p=arc/"MATRIX_LIVE_PRELABEL_BATCH_abc.json"
    p.write_text(json.dumps({
        "schema":"MATRIX_LIVE_TENNIS_PRELABEL_CAPTURE_BATCH_V1",
        "real_money":"BLOCKED","model_probability_authorized":False,
        "matches":[{"match_id":True,"physical_match_key":"live_tennis_api:True"}]}))
    with pytest.raises(ValueError,match="PRELABEL_MATCH_ID_AMBIGUOUS"):
        frozen_match_ids(lp)
    p.write_text(json.dumps({"schema":"NOT_A_FREEZE","matches":[]}))
    with pytest.raises(ValueError,match="PRELABEL_BATCH_NOT_SAFE_FOR_SETTLEMENT_PRIORITY"):
        frozen_match_ids(lp)
