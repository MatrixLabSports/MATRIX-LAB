import json
from pathlib import Path

import pytest

from tools.matrix_independent_triple_source_calendar_certificate import certify


def fixture(tmp_path: Path):
    folder=tmp_path/"evidence"/"football_world_inventory"/"2026-11-03"
    folder.mkdir(parents=True)
    src={"source":"FOOTBALL_DATA_ORG","source_fixture_id":"123",
         "api_football_fixture_id":None,"home":"Home FC","away":"Away FC",
         "kickoff_utc":"2026-11-03T19:45:00+00:00",
         "signal_generation_authorized":False}
    base={"real_money":"BLOCKED","signal_generation_authorized":False}
    files={
        "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json":
          {**base,"fixture_count":1,"fixtures":[src]},
        "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json":
          {**base,"target_date_bogota":"2026-11-03","matched_count":1,
           "matched":[{"fixture_id":"123","sofascore_event_id":"sofa123",
                       "kickoff_utc":src["kickoff_utc"],"identity_time_and_teams_verified":True,
                       "sofascore_url":"https://www.sofascore.com/test"}]},
        "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json":
          {**base,"target_date_bogota":"2026-11-03","matched_count":1,
           "matched":[{"source_fixture_id":"123","sofascore_event_id":"sofa123",
                       "flashscore_mid":"flash123","kickoff_utc":src["kickoff_utc"],
                       "three_source_calendar_identity_verified":True,
                       "flashscore_url":"https://www.flashscore.co/test"}]},
    }
    for name,data in files.items():
        (folder/name).write_text(json.dumps(data),encoding="utf-8")
    return folder,files


def test_verified_calendar_identity_never_promotes_probabilities_or_signals(tmp_path):
    folder,files=fixture(tmp_path)
    cert=certify(folder,"2026-11-03")
    assert cert["triple_source_calendar_identities"]==1
    assert cert["rows"][0]["independent_fixture_id"]=="123"
    assert cert["canonical_model_input_authorized"] is False
    assert cert["telegram_signal_authorized"] is False
    assert cert["api_football_fixture_id_mapping_present"] is False
    assert cert["real_money"]=="BLOCKED"
    assert all("p_matrix" not in row for row in cert["rows"])


def test_kickoff_mismatch_is_rejected(tmp_path):
    folder,files=fixture(tmp_path)
    files["MATRIX_FLASH_FOOTBALL_CROSSCHECK.json"]["matched"][0]["kickoff_utc"]="2026-11-03T20:45:00+00:00"
    (folder/"MATRIX_FLASH_FOOTBALL_CROSSCHECK.json").write_text(
        json.dumps(files["MATRIX_FLASH_FOOTBALL_CROSSCHECK.json"]),encoding="utf-8")
    with pytest.raises(ValueError,match="KICKOFF_MISMATCH"):
        certify(folder,"2026-11-03")


def test_fixture_id_namespace_cannot_masquerade_as_api_football(tmp_path):
    folder,files=fixture(tmp_path)
    files["MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json"]["fixtures"][0]["api_football_fixture_id"]="123"
    (folder/"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").write_text(
        json.dumps(files["MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json"]),encoding="utf-8")
    with pytest.raises(ValueError,match="NAMESPACE_MISMATCH"):
        certify(folder,"2026-11-03")


def test_duplicate_source_id_is_rejected(tmp_path):
    folder,files=fixture(tmp_path)
    d=files["MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json"]
    d["fixtures"].append(dict(d["fixtures"][0]));d["fixture_count"]=2
    (folder/"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").write_text(
        json.dumps(d),encoding="utf-8")
    with pytest.raises(ValueError,match="DUPLICATE_ID"):
        certify(folder,"2026-11-03")


def test_missing_data_is_never_silently_promoted(tmp_path):
    folder,files=fixture(tmp_path)
    files["MATRIX_FLASH_FOOTBALL_CROSSCHECK.json"]["matched"][0]["three_source_calendar_identity_verified"]=False
    (folder/"MATRIX_FLASH_FOOTBALL_CROSSCHECK.json").write_text(
        json.dumps(files["MATRIX_FLASH_FOOTBALL_CROSSCHECK.json"]),encoding="utf-8")
    with pytest.raises(ValueError,match="IDENTITY_NOT_VERIFIED"):
        certify(folder,"2026-11-03")
