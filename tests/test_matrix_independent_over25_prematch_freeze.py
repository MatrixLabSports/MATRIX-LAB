"""Test immutable real-source freeze and strict no-backfill boundaries."""
import base64
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from tools.matrix_independent_over25_prematch_freeze import freeze,canonical,SCHEMA
from tools.api_football_market_shadow_p_matrix import _pool_over25

T=lambda s:datetime.fromisoformat(s.replace("Z","+00:00"))
KICK="2026-11-04T20:00:00Z"
AT="2026-11-04T12:00:00Z"
HIST="2026-11-04T12:02:00Z"
CALC="2026-11-04T12:03:00Z"

def sample(kick=KICK,observed=HIST):
    raw=json.dumps({"matches":[]}).encode()
    h=hashlib.sha256(raw).hexdigest()
    inp={"schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
      "source":"FOOTBALL_DATA_ORG","real_money":"BLOCKED",
      "signal_generation_authorized":False,"target_date_bogota":"2026-11-04",
      "generated_at_utc":AT,
      "fixtures":[{"source_fixture_id":"555","source_competition_id":2019,
        "source_status":"TIMED","kickoff_utc":kick,
        "home_source_team_id":"101","away_source_team_id":"102"}]}
    shadow={"schema":"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
      "source":"FOOTBALL_DATA_ORG","real_money":"BLOCKED",
      "market_signal_authorized":False,"parameter_refit":False,
      "target_date_bogota":"2026-11-04","generated_at_utc":CALC,
      "authenticated_raw_group_replay_evidence":{"2019":{
         "response_base64":base64.b64encode(raw).decode(),
         "source_payload_sha256":h,"observed_at_utc":observed}},
      "scored":[{"source_fixture_id":"555","competition_id":2019,
        "kickoff_utc":kick,"p_over25_research":round(_pool_over25(0.6,0.55),10)}]}
    return inp,shadow

def run(tmp_path,now="2026-11-04T12:04:00Z",**kwargs):
    a,b=sample(**kwargs)
    with patch("tools.matrix_independent_over25_prematch_freeze.historic_rows",return_value=[]),\
         patch("tools.matrix_independent_over25_prematch_freeze._inputs_for_target",
             return_value=({"home_history_count":5,"away_history_count":5,
                            "poisson":{"over_2_5":0.6},
                            "baseline":{"over_2_5":0.55}},None)):
        return freeze(a,b,intake_bytes=canonical(a),shadow_bytes=canonical(b),
            now=T(now),folder=tmp_path/"evidence/football_research_freezes/2026-11-04")

def test_immutable_seal_and_replay(tmp_path):
    r=run(tmp_path)
    assert r["immutable_prematch_freeze_count"]==1
    entry=r["sealed"][0]
    x=json.loads(Path(entry["path"]).read_text())
    assert x["schema"]==SCHEMA
    assert x["sealed_at_utc"]<x["kickoff_utc"]
    assert x["source_shadow_file_sha256"]
    for label in ("source_shadow_file_path","source_intake_file_path"):
        src=Path(x[label])
        assert src.is_file()
        assert hashlib.sha256(src.read_bytes()).hexdigest()==x[label.replace("_path","_sha256")]
    assert x["source_snapshot_sha256"]
    assert x["production_p_matrix_authorized"] is False
    assert r["telegram_signal_authorized"] is False
    again=run(tmp_path)
    assert again["sealed"][0]["status"]=="ALREADY_IDENTICAL"

def test_late_capture_cannot_backfill(tmp_path):
    r=run(tmp_path,now="2026-11-04T20:01:00Z")
    assert r["immutable_prematch_freeze_count"]==0
    assert r["blocked"][0]["reason"]=="TARGET_ALREADY_STARTED_OR_FREEZE_TOO_LATE"

def test_group_observed_late_rejected(tmp_path):
    r=run(tmp_path,observed="2026-11-04T20:01:00Z")
    assert r["immutable_prematch_freeze_count"]==0
    assert "RAW_HISTORY_NOT_CAPTURED_BEFORE_KICKOFF" in r["blocked"][0]["reason"]

def test_shadow_history_wrong_hash_rejected(tmp_path):
    a,b=sample()
    b["authenticated_raw_group_replay_evidence"]["2019"]["source_payload_sha256"]="f"*64
    r=freeze(a,b,intake_bytes=canonical(a),shadow_bytes=canonical(b),
             now=T("2026-11-04T12:04:00Z"),folder=tmp_path)
    assert r["immutable_prematch_freeze_count"]==0
    assert "SOURCE_BYTES_OR_HASH_INVALID" in r["blocked"][0]["reason"]

def test_governance_must_be_blocked(tmp_path):
    a,b=sample();b["market_signal_authorized"]=True
    try:
        freeze(a,b,intake_bytes=canonical(a),shadow_bytes=canonical(b),
             now=T("2026-11-04T12:04:00Z"),folder=tmp_path)
    except ValueError as e:
        assert "GOVERNANCE_INVALID" in str(e)
    else:raise AssertionError("Unauthorized freeze allowed")

def test_probabilities_must_match_original_math(tmp_path):
    a,b=sample();b["scored"][0]["p_over25_research"]=0.99
    with patch("tools.matrix_independent_over25_prematch_freeze.historic_rows",return_value=[]),\
         patch("tools.matrix_independent_over25_prematch_freeze._inputs_for_target",
             return_value=({"home_history_count":5,"away_history_count":5,
                            "poisson":{"over_2_5":0.6},
                            "baseline":{"over_2_5":0.55}},None)):
        r=freeze(a,b,intake_bytes=canonical(a),shadow_bytes=canonical(b),
            now=T("2026-11-04T12:04:00Z"),folder=tmp_path)
    assert r["immutable_prematch_freeze_count"]==0
    assert r["blocked"][0]["reason"]=="LIVE_SHADOW_PROBABILITY_MISMATCH"
