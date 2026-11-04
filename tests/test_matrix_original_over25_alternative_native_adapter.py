"""Permanent frozen original Over2.5 engine bridge must reject counterfeit sources."""
import base64,hashlib,json
from pathlib import Path
from unittest.mock import patch
from tools.matrix_original_over25_alternative_native_adapter import evaluate,verify,ROOT,PROMOTION
from tools.matrix_independent_over25_prematch_freeze import canonical,digest,SCHEMA
from tools.api_football_market_shadow_p_matrix import PARAMS_OVER25,_pool_over25

def file(root,path,data):
    p=root/path;p.parent.mkdir(parents=True,exist_ok=True)
    content=canonical(data) if isinstance(data,dict) else data
    p.write_bytes(content)
    return p

def setup(tmp_path,*,wrong_source=False,late=False):
    file(tmp_path,PROMOTION,{
      "market":"OVER_2_5",
      "promotion_status":"PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY",
      "engine_executable_for_p_matrix":True,
      "frozen_parameters":{"a":0.6,"b":0.0,"c":0.4},
      "parameter_refit_performed":False,
      "promotion_scope":"MARKET_SCOPED_SIGNAL_GENERATION_NOT_REAL_MONEY"})
    folder=ROOT/"2026-11-04"
    intake={"schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
      "source":"FOOTBALL_DATA_ORG","signal_generation_authorized":False,
      "generated_at_utc":"2026-11-04T08:00:00Z",
      "fixtures":[{"source_fixture_id":"555","source_competition_id":2019,
        "home_source_team_id":"10","away_source_team_id":"20",
        "kickoff_utc":"2026-11-04T20:00:00Z","source_status":"TIMED"}]}
    raw=canonical({"competition":{"id":2019},"matches":[]})
    sha=digest(raw)
    shadow={"schema":"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
      "source":"FOOTBALL_DATA_ORG","parameter_refit":False,
      "market_signal_authorized":False,
      "generated_at_utc":"2026-11-04T08:01:00Z",
      "completed_at_utc":"2026-11-04T08:02:00Z",
      "authenticated_raw_group_replay_evidence":{"2019":{
         "response_base64":base64.b64encode(raw).decode("ascii"),
         "source_payload_sha256":"a"*64 if wrong_source else sha,
         "observed_at_utc":"2026-11-04T20:30:00Z" if late else "2026-11-04T08:01:30Z"}}}
    inpbytes=canonical(intake);shbytes=canonical(shadow)
    ih=digest(inpbytes);sh=digest(shbytes)
    file(tmp_path,folder/"sources"/(ih+".json"),inpbytes)
    file(tmp_path,folder/"sources"/(sh+".json"),shbytes)
    probability=round(_pool_over25(.60,.55),10)
    forecast={"schema":SCHEMA,"provider":"FOOTBALL_DATA_ORG",
      "provider_fixture_id":"555","provider_competition_id":"2019",
      "source_intake_file_sha256":ih,"source_shadow_file_sha256":sh,
      "source_snapshot_sha256":sha,"kickoff_utc":"2026-11-04T20:00:00+00:00",
      "sealed_at_utc":"2026-11-04T09:00:00Z",
      "model_calculated_at_utc":"2026-11-04T08:02:00Z",
      "source_history_home_count":5,"source_history_away_count":5,
      "research_probability_over25":probability,
      "production_p_matrix_authorized":False,
      "telegram_signal_authorized":False,"real_money":"BLOCKED"}
    p=file(tmp_path,folder/"555_first.json",forecast)
    return p

def features():
    return {"prior_group_fixture_count":30,"home_history_count":5,
      "away_history_count":5,"home_history_source":"RAW_GROUP_PIT",
      "away_history_source":"RAW_GROUP_PIT",
      "poisson":{"over_2_5":.60},"baseline":{"over_2_5":.55}}

def test_original_frozen_engine_reused_with_same_weights(tmp_path):
    p=setup(tmp_path)
    with patch("tools.matrix_original_over25_alternative_native_adapter._inputs_for_target",
         return_value=(features(),None)):
        r=evaluate(tmp_path)
    assert r["original_engine_verified_rows"]==1
    assert r["verified"][0]["frozen_probability"]==round(_pool_over25(.60,.55),10)
    assert r["frozen_original_parameters"]==dict(PARAMS_OVER25)
    assert r["official_original_p_matrix_reinstated"] is False
    assert r["telegram_signal_authorized"] is False

def test_tampered_raw_history_fails_closed(tmp_path):
    setup(tmp_path,wrong_source=True)
    with patch("tools.matrix_original_over25_alternative_native_adapter._inputs_for_target",
         return_value=(features(),None)):
        r=evaluate(tmp_path)
    assert r["original_engine_verified_rows"]==0
    assert "AUTHENTIC_HISTORY_SHA_MISMATCH" in r["blocked"][0]["reason"]

def test_history_captured_after_kickoff_fails_closed(tmp_path):
    setup(tmp_path,late=True)
    with patch("tools.matrix_original_over25_alternative_native_adapter._inputs_for_target",
         return_value=(features(),None)):
        r=evaluate(tmp_path)
    assert r["original_engine_verified_rows"]==0
    assert "HISTORY_AVAILABILITY_TIMELINE_INVALID" in r["blocked"][0]["reason"]

def test_cannot_refit_promoted_parameters(tmp_path):
    setup(tmp_path)
    p=tmp_path/PROMOTION
    x=json.loads(p.read_text())
    x["frozen_parameters"]["a"]=0.8
    p.write_bytes(canonical(x))
    try:evaluate(tmp_path)
    except ValueError as e:assert "PROMOTION_OR_PARAMETERS_CHANGED" in str(e)
    else:raise AssertionError("original parameter refit not blocked")

def test_research_probability_mismatch_is_not_promoted(tmp_path):
    p=setup(tmp_path)
    x=json.loads(p.read_text());x["research_probability_over25"]=0.99
    p.write_bytes(canonical(x))
    with patch("tools.matrix_original_over25_alternative_native_adapter._inputs_for_target",
         return_value=(features(),None)):
        r=evaluate(tmp_path)
    assert r["original_engine_verified_rows"]==0
    assert "PROBABILITY_MISMATCH" in r["blocked"][0]["reason"]
