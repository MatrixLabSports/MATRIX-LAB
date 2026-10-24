from datetime import datetime, timezone
from pathlib import Path
import json

from tools.matrix_canonical_truth_guard import evaluate_source

NOW=datetime(2026,10,20,7,30,tzinfo=timezone.utc)


def write(tmp_path,payload):
    p=tmp_path/"x.json"
    p.write_text(json.dumps(payload),encoding="utf-8")
    return p


def test_stale_source_fails_closed(tmp_path):
    p=write(tmp_path,{"schema":"X","generated_at_utc":"2026-10-20T05:00:00Z","value":1})
    r=evaluate_source("x",{"canonical_path":str(p),"required_schema":"X","timestamp_field":"generated_at_utc","max_age_minutes":45,"metric_path":"value"},NOW)
    assert r["status"]=="FAIL_CLOSED"
    assert "CANONICAL_SOURCE_STALE" in r["failures"]


def test_missing_metric_fails_closed(tmp_path):
    p=write(tmp_path,{"schema":"X","generated_at_utc":"2026-10-20T07:20:00Z"})
    r=evaluate_source("x",{"canonical_path":str(p),"required_schema":"X","timestamp_field":"generated_at_utc","max_age_minutes":45,"metric_path":"missing"},NOW)
    assert r["status"]=="FAIL_CLOSED"


def test_fresh_source_passes(tmp_path):
    p=write(tmp_path,{"schema":"X","generated_at_utc":"2026-10-20T07:20:00Z","value":7})
    r=evaluate_source("x",{"canonical_path":str(p),"required_schema":"X","timestamp_field":"generated_at_utc","max_age_minutes":45,"metric_path":"value"},NOW)
    assert r["status"]=="PASS"
    assert r["metrics"]["value"]==7


def test_current_football_canonical_counter_reconciles():
    root=Path("evidence/api_football/governance/MATRIX_FOOTBALL_4000_CANONICAL_TRACKER_LAST.json")
    j=json.loads(root.read_text())
    g=j["global"]
    assert g["valid_final_settlement_count"]+g["pending_count"]+g["blocked_count"]==g["frozen_event_count"]
    assert g["valid_final_settlement_count"]==g["calibration_observation_count"]
    assert j["counter_precedence"]["target_4000"]=="global.valid_final_settlement_count"


def test_all_registered_sources_fail_closed_after_30_minutes():
    registry=json.loads(Path("evidence/governance/MATRIX_CANONICAL_SOURCE_REGISTRY.json").read_text())
    assert registry["sources"]
    assert all(int(spec["max_age_minutes"])==30 for spec in registry["sources"].values())
