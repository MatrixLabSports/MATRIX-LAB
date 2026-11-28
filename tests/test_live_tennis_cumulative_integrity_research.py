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
    by_match={}
    for lane,matches in lanes.items():
        for key in matches:
            by_match.setdefault(key,set()).add(lane)
    ambiguous=sorted(key for key,ls in by_match.items() if len(ls)>1)
    canonical={}
    for k,observed in lanes.items():
        v=list(observed.values())
        canonical[k]={
            "unique_match_count":len(v),
            "quality_valid_unique_match_count":sum(x["valid"] for x in v),
            "settled_final_standard_unique_match_count":sum(x["final"] for x in v),
            "raw_settled_quality_valid_before_multi_lane_quarantine":sum(x["valid"] and x["final"] for x in v),
            "settled_quality_valid_unique_match_count":sum(
                x["valid"] and x["final"] for key,x in observed.items()
                if key not in ambiguous),
        }
    manifest_path=lfile.relative_to(root).as_posix()
    digest=hashlib.sha256(lfile.read_bytes()).hexdigest()
    cumulative={
        "schema":"MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1",
        "probability_output_status":"SEALED","metrics_status":"SEALED",
        "protections":{"real_money":"BLOCKED","automatic_wagering":False},
        "source_ledgers":[{"path":manifest_path,"sha256":"a"*64 if sha_drift else digest}],
        "lanes":canonical,
        "multi_lane_ambiguous_match_keys":ambiguous,
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


def test_contamination_is_localized_without_globally_promoting_any_model(tmp_path):
    clean=[row(mid=i+1000,lane="itf|women|hard") for i in range(30)]
    bad_a=row(mid=206910,lane="utr|men|unknown")
    bad_b=row(mid=206910,lane="unknown|unknown|unknown")
    r=audit(write_fixture(tmp_path,*clean,bad_a,bad_b))
    assert r["source_integrity_passed"] is False
    assert r["multi_lane_same_physical_match_count"] == 1
    assert r["quarantined_physical_match_count"] == 1
    assert r["multi_lane_match_details"][0]["lanes"] == [
        "unknown|unknown|unknown", "utr|men|unknown"
    ]
    by_lane={x["lane"]:x for x in r["lane_research_counts"]}
    clean_lane=by_lane["itf|women|hard"]
    assert clean_lane["research_integrity_clear"] is True
    assert clean_lane["research_count_threshold_30_met"] is True
    assert clean_lane["settled_quality_valid_research_count_after_quarantine"] == 30
    affected=by_lane["utr|men|unknown"]
    assert affected["research_integrity_clear"] is False
    assert affected["settled_quality_valid_unique_match_count"] == 1
    assert affected["settled_quality_valid_research_count_after_quarantine"] == 0
    assert affected["quarantined_physical_match_count"] == 1
    assert r["production_model_training_authorized"] is False
    assert r["production_p_live_authorized"] is False
    assert r["telegram_signal_authorized"] is False

def test_conflicting_final_winner_is_removed_from_research_count(tmp_path):
    r=audit(write_fixture(tmp_path,row(mid=990,label=0),row(mid=990,label=1)))
    lane=r["lane_research_counts"][0]
    assert lane["settled_quality_valid_unique_match_count"] == 1
    assert lane["settled_quality_valid_research_count_after_quarantine"] == 0
    assert lane["research_integrity_clear"] is False
