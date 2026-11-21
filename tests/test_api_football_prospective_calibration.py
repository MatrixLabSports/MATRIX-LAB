import copy
import hashlib
import json
from pathlib import Path

from tools.api_football_prospective_calibration import (
    _record_sha,
    audit_calibration_ledger,
    build_gate_state,
    sync_calibration_ledger,
)


def _rows(n:int):
    rows=[]
    previous=None
    for i in range(n):
        row={
            "schema":"MATRIX_FOOTBALL_PROSPECTIVE_CALIBRATION_OBSERVATION_V1",
            "fixture_id":str(100000+i),
            "target_key":f"api_football:fixture:{100000+i}",
            "kickoff_utc":"2026-09-28T18:00:00+00:00",
            "freeze_at_utc":"2026-09-28T12:00:00+00:00",
            "settled_at_utc":"2026-09-28T22:00:00+00:00",
            "input_sha256":"a"*64,
            "frozen_challenger_probabilities":{"1x2":{"H":0.60,"D":0.20,"A":0.20},"over_2_5":0.60,"btts_v2":0.60},
            "frozen_poisson_reference":{"1x2":{"H":0.50,"D":0.25,"A":0.25},"over_2_5":0.55,"btts":0.55},
            "outcomes":{"1x2":"H","over_2_5":True,"btts":True},
            "source_terminal_status":"FT",
            "source_settlement_record_sha256":"b"*64,
            "used_for_parameter_tuning":False,
            "parameters_mutated_after_freeze":False,
            "p_matrix_status":"NOT_GENERATED",
            "automatic_wagering":False,
            "real_money":"BLOCKED",
            "previous_record_sha256":previous,
        }
        row["record_sha256"]=_record_sha(row)
        previous=row["record_sha256"]
        rows.append(row)
    return rows


def test_gate_29_keeps_all_metrics_sealed():
    d=build_gate_state(_rows(29))
    assert all(g["status"]=="SEALED" for g in d["gates"].values())
    assert all(g["metrics"] is None for g in d["gates"].values())
    assert all(g["metrics_opened"] is False for g in d["gates"].values())


def test_gate_30_opens_only_30():
    d=build_gate_state(_rows(30))
    assert d["gates"]["30"]["status"]=="OPENED_AT_THRESHOLD"
    assert d["gates"]["30"]["metrics_opened"] is True
    assert d["gates"]["50"]["status"]=="SEALED"
    assert d["gates"]["100"]["status"]=="SEALED"


def test_gate_50_opens_30_and_50_only():
    d=build_gate_state(_rows(50))
    assert d["gates"]["30"]["metrics_opened"] is True
    assert d["gates"]["50"]["metrics_opened"] is True
    assert d["gates"]["100"]["metrics_opened"] is False


def test_gate_100_opens_all_with_fixed_prefix_samples():
    rows=_rows(100)
    d=build_gate_state(rows)
    assert all(g["metrics_opened"] is True for g in d["gates"].values())
    assert d["gates"]["30"]["observations_used"]==30
    assert d["gates"]["50"]["observations_used"]==50
    assert d["gates"]["100"]["observations_used"]==100
    assert d["gates"]["100"]["metrics"]["all_three_markets_pass"] is True


def test_hash_chain_tamper_is_detected():
    rows=_rows(3)
    rows[1]["fixture_id"]="999999"
    try:
        audit_calibration_ledger(rows)
    except ValueError as exc:
        assert "SHA_MISMATCH" in str(exc)
    else:
        raise AssertionError("tamper must be detected")


def test_live_repository_state_keeps_metrics_sealed_before_threshold():
    root=Path("evidence/api_football")
    sync=sync_calibration_ledger(root)
    ledger_path=root/"prospective_calibration/ledger.jsonl"
    rows=[]
    if ledger_path.exists():
        rows=[json.loads(x) for x in ledger_path.read_text().splitlines() if x.strip()]
    gates=build_gate_state(rows)
    assert sync["ledger_hash_chain_verified"] is True
    if len(rows)<30:
        assert gates["gates"]["30"]["metrics_opened"] is False
        assert gates["gates"]["30"]["metrics"] is None
