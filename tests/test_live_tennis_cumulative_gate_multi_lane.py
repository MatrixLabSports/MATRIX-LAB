"""Original Live Tennis gate: no source imputation or multi-lane double counting."""
import json
from pathlib import Path

import pytest

from tools.live_tennis_cumulative_gate import build, physical_match_key

def make_row(mid, lane, *, quality=True, label=1):
    tour,gender,surface=lane.split("|")
    return {"match_id":mid, "provider":"live_tennis_api",
            "tour":tour, "gender":gender, "surface":surface,
            "quality_state_valid":quality,"settlement_status":"FINAL_STANDARD",
            "label_opened":True,"p1_match_win":label}

def prepare(tmp_path, rows):
    root=tmp_path/"evidence/live_tennis_lab"
    day=root/"2026-11-18"
    day.mkdir(parents=True)
    (day/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json").write_text(
        json.dumps({"operational_date_bogota":"2026-11-18","states":rows}),
        encoding="utf-8")
    return root

def test_original_gate_quarantines_same_physical_match_between_unknown_lanes(tmp_path):
    same_id=206910
    rows=[
        make_row(same_id,"utr|men|unknown",quality=True,label=1),
        make_row(same_id,"unknown|unknown|unknown",quality=False,label=1),
        make_row(700001,"itf|women|hard",quality=True,label=0),
    ]
    root=prepare(tmp_path,rows)
    d=build(root,tmp_path/"out.json")
    assert d["global_unique_match_count"]==2
    assert d["multi_lane_ambiguous_match_count"]==1
    assert d["multi_lane_ambiguous_match_keys"]==["live_tennis_api:206910"]
    assert d["multi_lane_ambiguity_quarantined_from_all_gate_counts"] is True
    utr=d["lanes"]["utr|men|unknown"]
    assert utr["raw_settled_quality_valid_before_multi_lane_quarantine"]==1
    assert utr["settled_quality_valid_unique_match_count"]==0
    assert utr["excluded_multi_lane_ambiguous_settled_matches"]==1
    assert utr["excluded_settled_without_quality_valid_state"]==0
    assert utr["gates"]["1"]["status"]=="SEALED"
    itf=d["lanes"]["itf|women|hard"]
    assert itf["settled_quality_valid_unique_match_count"]==1
    assert itf["gates"]["1"]["status"]=="OPEN"
    assert d["protections"]["real_money"]=="BLOCKED"
    assert d["probability_output_status"]=="SEALED"

def test_clean_lane_30_keeps_unchanged_gate_30(tmp_path):
    rows=[make_row(10000+i,"itf|women|hard") for i in range(30)]
    rows.extend([make_row(206910,"utr|men|unknown"),
                 make_row(206910,"unknown|unknown|unknown",quality=False)])
    d=build(prepare(tmp_path,rows),tmp_path/"out.json")
    assert d["lanes"]["itf|women|hard"]["gates"]["30"]["status"]=="OPEN"
    assert d["lanes"]["itf|women|hard"]["settled_quality_valid_unique_match_count"]==30
    assert d["sum_lane_settled_unique_matches"]==30
    assert d["multi_lane_ambiguous_match_count"]==1
    assert d["probability_output_status"]=="SEALED"

def test_missing_provider_or_boolean_id_cannot_be_silently_defaulted(tmp_path):
    assert physical_match_key({"match_id":1}) is None
    assert physical_match_key({"provider":"live_tennis_api","match_id":True}) is None
    assert physical_match_key({"provider":"live_tennis_api","match_id":-1}) is None
    assert physical_match_key({"provider":"live_tennis_api","match_id":1})=="live_tennis_api:1"

def test_boolean_final_winner_is_not_valid_result(tmp_path):
    d=build(prepare(tmp_path,[make_row(13,"itf|women|hard",label=True)]),tmp_path/"out.json")
    assert d["lanes"]["itf|women|hard"]["settled_final_standard_unique_match_count"]==0
    assert d["lanes"]["itf|women|hard"]["gates"]["1"]["status"]=="SEALED"

def test_malformed_source_ledger_fails_closed_not_skipped(tmp_path):
    root=tmp_path/"evidence/live_tennis_lab"
    day=root/"2026-11-18"
    day.mkdir(parents=True)
    (day/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json").write_text("{broken")
    with pytest.raises(ValueError,match="LIVE_SOURCE_LEDGER_UNREADABLE"):
        build(root,tmp_path/"out.json")
