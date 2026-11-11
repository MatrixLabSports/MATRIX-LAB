"""Research-only source identity and immutable historical biography contracts."""
from pathlib import Path
import json
from tools.matrix_tennis_free_visible_profile_research import (
    birthdate_from_visible_text,original_biography_match,valid_profile,
)

ROOT=Path(__file__).resolve().parents[1]

def test_sofascore_visible_clay_birth_dates_are_parsed_without_inference():
    for text,yyyymmdd in (
        ("3 de abril de 2004","20040403"),
        ("26 de marzo de 2000","20000326"),
        ("12 de febrero de 2003","20030212")):
        result,status=birthdate_from_visible_text(text)
        assert status=="VISIBLE_BIRTHDATE_EXACT"
        assert result[0]==yyyymmdd

def test_multiple_or_missing_birthdays_fail_closed():
    for text in ("sin fecha", "3 de abril de 2004; 26 de marzo de 2000",
                 "35 de abril de 2004","23 de mayo de 2005 y 31 de diciembre de 2000"):
        value,status=birthdate_from_visible_text(text)
        assert value is None
        assert status=="VISIBLE_BIRTHDATE_ABSENT_OR_AMBIGUOUS"

def test_real_nov12_clay_names_dates_country_match_sealed_originals_research_only():
    details=json.loads((ROOT/"evidence/tennis_calendar_physical/2026-11-12/sofascore_verified_match_details.json").read_bytes())
    records=json.loads((ROOT/"evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/identity/MATRIX_CLAY_IDENTITY_AUTHORITY_LAST.json").read_bytes())["records"]
    event=next(e for e in details["events"] if e["sofascore_event_id"]=="17489785")
    dob={"Gonzalo Bueno":"20040403","Joao Lucas Reis Da Silva":"20000326"}
    for player in event["players"]:
        assert valid_profile(player)
        result=original_biography_match(player,dob[player["name"]],records)
        assert result["status"]=="PRE_CUT_NAME_COUNTRY_BIRTHDATE_HISTORY_MATCH_RESEARCH_ONLY"
        assert result["pre_cut_latest_row_date"]<20261112
        assert result["native_provider_id_mapping_certified"] is False
        assert result["production_feature_equivalence_certified"] is False

def test_forged_dob_and_profile_source_cannot_pass():
    records=json.loads((ROOT/"evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/identity/MATRIX_CLAY_IDENTITY_AUTHORITY_LAST.json").read_bytes())["records"]
    player={"name":"Gonzalo Bueno","country":"Peru"}
    assert original_biography_match(player,"20000326",records)["status"]=="VISIBLE_DOB_CONFLICTS_WITH_ORIGINAL"
    assert not valid_profile(dict(player,sofascore_player_id="299765",
        profile_url="https://evil.example/es/tennis/player/bueno-gonzalo/299765"))

def test_provider_duplicate_unchanged_source_identity_not_proof_of_model():
    records=json.loads((ROOT/"evidence/cor0203/identity/MATRIX_COR0203_IDENTITY_AUTHORITY_LAST.json").read_bytes())["records"]
    player={"name":"Cezar Cretu","country":"Romania"}
    result=original_biography_match(player,"20010424",records)
    assert result["status"]=="PRE_CUT_NAME_COUNTRY_BIRTHDATE_HISTORY_MATCH_RESEARCH_ONLY"
    assert result["native_provider_id_mapping_certified"] is False
