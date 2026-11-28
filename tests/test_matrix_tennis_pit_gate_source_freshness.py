"""A cloud report can publish only if its source is the actual latest browser blob."""
import hashlib
import json
from pathlib import Path

from tools.matrix_tennis_pit_gate_source_freshness import verify

DAY="2026-11-18"

def fixture(tmp_path, *, same=True, missing_gate=False, bad_real_money=False):
    folder=tmp_path/"evidence/tennis_calendar_physical"/DAY
    rec=tmp_path/"evidence/tennis_calendar_reconciliation"/DAY
    folder.mkdir(parents=True)
    rec.mkdir(parents=True)
    details={"schema":"MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1",
             "target_date_bogota":DAY,"real_money":"BLOCKED",
             "new_model_observations_admitted":0,"events":[{"sofascore_event_id":"1"}]}
    p=folder/"sofascore_verified_match_details.json"
    p.write_text(json.dumps(details))
    h=hashlib.sha256(p.read_bytes()).hexdigest()
    report={"schema":"MATRIX_TENNIS_BROWSER_CHALLENGER_PIT_GATE_V1",
            "target_date_bogota":DAY,
            "real_money":"ENABLED" if bad_real_money else "BLOCKED",
            "match_detail_sha256":h if same else "f"*64,
            "new_hard_holdout_observations":0,
            "new_clay_holdout_observations":0}
    if not missing_gate:
        (rec/"MATRIX_TENNIS_BROWSER_CHALLENGER_PIT_GATE_LAST.json").write_text(json.dumps(report))
    return h

def test_current_reconciler_matches_exact_browser_source(tmp_path):
    actual=fixture(tmp_path)
    r=verify(tmp_path,DAY)
    assert r["status"]=="SOURCE_SHA256_BOUND_REPORT_CURRENT"
    assert r["publish_safe"] is True
    assert r["current_source_sha256"]==actual
    assert r["same_source"] is True

def test_concurrently_updated_browser_source_disallows_stale_report_publish(tmp_path):
    fixture(tmp_path)
    p=tmp_path/"evidence/tennis_calendar_physical"/DAY/"sofascore_verified_match_details.json"
    doc=json.loads(p.read_text())
    doc["events"][0]["new_source_kickoff"]="2026-11-18T17:10:00Z"
    p.write_text(json.dumps(doc))
    r=verify(tmp_path,DAY)
    assert r["status"]=="PIT_GATE_SOURCE_DRIFT_AFTER_GIT_REBASE"
    assert r["publish_safe"] is False

def test_missing_gate_is_not_empty_calendar_certification(tmp_path):
    fixture(tmp_path,missing_gate=True)
    r=verify(tmp_path,DAY)
    assert r["status"]=="MISSING_GOVERNED_PIT_GATE_OR_VISIBLE_DETAILS"
    assert r["publish_safe"] is False

def test_missing_both_does_not_invent_a_zero_observation(tmp_path):
    r=verify(tmp_path,DAY)
    assert r["status"]=="NO_DETAIL_AND_NO_GATE_NOT_ADMITTED"
    assert r["same_source"] is False
    assert r["publish_safe"] is True

def test_nonblocked_real_money_is_rejected(tmp_path):
    fixture(tmp_path,bad_real_money=True)
    assert verify(tmp_path,DAY)["publish_safe"] is False

def test_real_nov18_current_repo_state_is_reported_truthfully():
    root=Path(__file__).resolve().parents[1]
    r=verify(root,DAY)
    assert r["real_money"]=="BLOCKED" if "real_money" in r else True
    assert not (r["status"]=="SOURCE_SHA256_BOUND_REPORT_CURRENT" and
                r["gate_source_sha256"]!=r["current_source_sha256"])
