import json
from pathlib import Path

import pytest

from tools.matrix_independent_feature_parity_audit import evaluate


def fixture(tmp_path: Path):
    folder=tmp_path/"evidence"/"football_world_inventory"/"2026-11-03"
    folder.mkdir(parents=True)
    src={"source_fixture_id":"100","kickoff_utc":"2026-11-03T19:45:00+00:00"}
    files={
      "MATRIX_TRIPLE_SOURCE_CALENDAR_IDENTITY_CERTIFICATE.json":{
        "target_date_bogota":"2026-11-03","canonical_model_input_authorized":False,
        "triple_source_calendar_identities":1,
        "rows":[{"independent_fixture_id":"100","kickoff_utc":src["kickoff_utc"],"calendar_identity_verified":True}]},
      "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json":{
        "historical_source_equivalence_verified":False,"market_signal_authorized":False,
        "scored":[{"source_fixture_id":"100","p_over25_research":0.92,
          "feature_counts":{"home_history_count":13,"away_history_count":13}}]},
      "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json":{
        "governed_feature_equivalence_verified":False,"signal_generation_authorized":False,
        "fixture_count":1,"fixtures":[src]},
      "MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT.json":{
        "signal_generation_authorized":False,"bookmaker_quote_verified_count":0}
    }
    for name,data in files.items():
        (folder/name).write_text(json.dumps(data),encoding="utf-8")
    return folder,files


def test_research_counts_cannot_certify_provider_native_history(tmp_path):
    folder,_=fixture(tmp_path)
    j=evaluate(folder,"2026-11-03")
    assert j["calendar_certified_fixture_count"]==1
    assert j["research_minimum_history_fixture_count"]==1
    assert j["provider_native_history_certified_count"]==0
    assert j["model_feature_parity_certified_count"]==0
    assert j["telegram_signal_authorized"] is False
    assert j["canonical_inputs_generated"] is False
    assert j["calibration_parameters_untouched"] is True
    assert "p_matrix" not in j["rows"][0]


def test_missing_research_not_converted_to_zero_history(tmp_path):
    folder,files=fixture(tmp_path)
    files["MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"]["scored"]=[]
    (folder/"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json").write_text(
        json.dumps(files["MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"]),encoding="utf-8")
    j=evaluate(folder,"2026-11-03")
    assert j["rows"][0]["research_rows_available"] is False
    assert j["rows"][0]["research_home_history_count"] is None
    assert j["research_minimum_history_fixture_count"]==0


def test_mismatched_fixture_kickoff_fails_closed(tmp_path):
    folder,files=fixture(tmp_path)
    files["MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json"]["fixtures"][0]["kickoff_utc"]="2026-11-03T21:45:00+00:00"
    (folder/"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").write_text(
      json.dumps(files["MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json"]),encoding="utf-8")
    with pytest.raises(ValueError,match="PARITY_FIXTURE_SOURCE_MISMATCH"):
        evaluate(folder,"2026-11-03")


def test_unverified_research_governance_fails_closed(tmp_path):
    folder,files=fixture(tmp_path)
    files["MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"]["historical_source_equivalence_verified"]=True
    (folder/"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json").write_text(
      json.dumps(files["MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"]),encoding="utf-8")
    with pytest.raises(ValueError,match="PARITY_RESEARCH_GOVERNANCE_INVALID"):
        evaluate(folder,"2026-11-03")


def test_duplicate_research_ids_are_blocked(tmp_path):
    folder,files=fixture(tmp_path)
    row=files["MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"]["scored"][0]
    files["MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"]["scored"].append(dict(row))
    (folder/"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json").write_text(
      json.dumps(files["MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"]),encoding="utf-8")
    with pytest.raises(ValueError,match="DUPLICATE"):
        evaluate(folder,"2026-11-03")
