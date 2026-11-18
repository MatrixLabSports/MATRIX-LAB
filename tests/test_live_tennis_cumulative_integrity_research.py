"""Independent source-integrity regression: synthetic data never authorizes bets."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from tools.live_tennis_cumulative_integrity_research import audit, parse_utc

BASE=Path("evidence/live_tennis_lab")
DAY="2026-11-18"

def row(mid=123, *, lane="itf|women|hard", label=1,
        captured="2026-11-18T01:30:00+00:00", quality=True):
    tour,gender,surface=lane.split("|")
    return {
        "provider":"live_tennis_api","match_id":mid,"tour":tour,
        "gender":gender,"surface":surface,
        "quality_state_valid":quality,
        "label_opened":True,"settlement_status":"FINAL_STANDARD",
        "p1_match_win":label, "captured_at_utc":captured,
    }

def write_fixture(root, *rows, count_override=None, sha_drift=False):
    folder=root/BASE/DAY
    folder.mkdir(parents=True,exist_ok=True)
    lfile=folder/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json"
    ldoc={
        "schema":"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1",
        "operational_date_bogota":DAY,
        "protections":{"real_money":"BLOCKED","automatic_wagering":False,
                       "odds_to_probability":False,"outcomes_read_during_live_capture":0},
        "states":list(rows),
    }
    lfile.write_text(json.dumps(ldoc))
    keys=set()
    lanes={}
    for x in rows:
        key=f"{x['provider']}:{x['match_id']}"
        lane="|".join(x[k] for k in ("tour","gender","surface"))
        keys.add(key)
        lanes.setdefault(lane,{})[key]={
            "valid":x["quality_state_valid"],
            "final":x["label_opened"] and x["settlement_status"]=="FINAL_STANDARD"
                     and x["p1_match_win"] in [0,1],
        }
    canonical={}
    for k,v in lanes.items():
        v=list(v.values())
        canonical[k]={
            "unique_match_count":len(v),
            "quality_valid_unique_match_count":sum(x["valid"] for x in v),
            "settled_final_standard_unique_match_count":sum(x["final"] for x in v),
            "settled_quality_valid_unique_match_count":sum(x["valid"] and x["final"] for x in v),
        }
    manifest_path=lfile.relative_to(root).as_posix()
    digest=hashlib.sha256(lfile.read_bytes()).hexdigest()
    cumulative={
        "schema":"MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1",
        "probability_output_status":"SEALED","metrics_status":"SEALED",
        "protections":{"real_money":"BLOCKED","automatic_wagering":False},
        "source_ledgers":[{"path":manifest_path,"sha256":"a"*64 if sha_drift else digest}],
        "lanes":canonical,
        "global_unique_match_count":len(keys) if count_override is None else count_override,
    }
    (root/BASE/"MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1.json").write_text(json.dumps(cumulative))
    return root

def test_complete_one_match_has_exact_source_sha_but_no_production_admission(tmp_path):
    r=audit(write_fixture(tmp_path,row()))
    assert r["source_integrity_passed"]
    assert r["source_daily_ledgers"]==1
    assert r["states_scanned"]==1
    assert r["physical_unique_matches"]==1
    assert r["multi_lane_same_physical_match_count"]==0
    assert r["contradictory_final_result_count"]==0
    assert r["research_threshold_30_met_lanes"]==0
    assert r["production_model_training_authorized"] is False
    assert r["production_p_live_authorized"] is False
    assert r["real_money"]=="BLOCKED"

def test_30_distinct_match_ids_meets_old_research_threshold_not_training(tmp_path):
    r=audit(write_fixture(tmp_path,*[row(mid=100+i) for i in range(30)]))
    assert r["research_threshold_30_met_lanes"]==1
    assert r["source_integrity_passed"] is True
    assert r["production_model_training_authorized"] is False
    assert r["grouped_chronological_oos_validation_complete"] is False

def test_cross_lane_same_match_is_detected_and_not_promoted(tmp_path):
    a=row(mid=42,lane="itf|women|hard")
    b=row(mid=42,lane="itf|women|clay")
    r=audit(write_fixture(tmp_path,a,b))
    assert r["physical_unique_matches"]==1
    assert r["multi_lane_same_physical_match_count"]==1
    assert r["source_integrity_passed"] is False
    assert r["production_p_live_authorized"] is False

def test_conflicting_final_winners_are_quarantined(tmp_path):
    a=row(mid=43,label=1)
    b=row(mid=43,label=0)
    r=audit(write_fixture(tmp_path,a,b))
    assert r["contradictory_final_result_count"]==1
    assert r["source_integrity_passed"] is False

def test_wrong_global_counts_are_reported_not_silently_reconciled(tmp_path):
    r=audit(write_fixture(tmp_path,row(),count_override=2))
    assert not r["source_integrity_passed"]
    assert any(x.get("reason")=="GLOBAL_PHYSICAL_MATCH_COUNT_DISAGREES"
               for x in r["reported_count_discrepancies"])

def test_bad_sha_refuses_to_reinterpret_evidence(tmp_path):
    with pytest.raises(ValueError,match="LEDGER_SOURCE_SHA_DRIFT"):
        audit(write_fixture(tmp_path,row(),sha_drift=True))

def test_naive_timestamp_is_not_repaired_or_assumed_utc(tmp_path):
    r=audit(write_fixture(tmp_path,row(captured="2026-11-18T01:30:00")))
    assert r["matches_with_missing_or_bad_capture_timestamp"]==1
    assert r["source_integrity_passed"] is False
    with pytest.raises(ValueError,match="UTC_TIMESTAMP_WITHOUT_ZONE"):
        parse_utc("2026-11-18T01:30:00")

def test_missing_daily_ledger_in_manifest_fails_closed(tmp_path):
    write_fixture(tmp_path,row())
    (tmp_path/BASE/DAY/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json").unlink()
    with pytest.raises(ValueError,match="CUMULATIVE_MANIFEST_DOES_NOT_COVER_ALL_DAILY_LEDGERS"):
        audit(tmp_path)
