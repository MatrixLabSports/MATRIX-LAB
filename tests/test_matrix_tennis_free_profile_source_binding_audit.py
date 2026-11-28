"""Synthetic no-network regression tests of tennis biographical SHA binding."""
import hashlib
import json
from datetime import datetime
import pytest

from tools.matrix_tennis_free_profile_source_binding_audit import audit, BASE

DAY="2026-11-19"

def build(tmp_path):
    folder=tmp_path/BASE/DAY
    folder.mkdir(parents=True)
    detail={
        "schema":"MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1",
        "target_date_bogota":DAY,"real_money":"BLOCKED",
        "new_model_observations_admitted":0,
        "provider_identity_equivalence_certified":False,
        "events":[{
            "sofascore_event_id":"17537333","surface":"Hard",
            "kickoff_utc":"2026-11-19T16:00:00Z",
            "players":[{
                "sofascore_player_id":"386501","name":"Bor Artnak",
                "country":"Slovenia","profile_url":"https://www.sofascore.com/tennis/player/artnak-bor/386501",
            }],
        }],
    }
    dp=folder/"sofascore_verified_match_details.json"
    dp.write_text(json.dumps(detail))
    profile={
        "schema":"MATRIX_TENNIS_FREE_VISIBLE_PROFILE_BIRTHDATES_RESEARCH_V1",
        "target_date_bogota":DAY,"source_detail_sha256":hashlib.sha256(dp.read_bytes()).hexdigest(),
        "real_money":"BLOCKED","official_holdout_admitted":0,
        "provider_identity_equivalence_certified":False,
        "profiles":[{
            "sofascore_player_id":"386501","name":"Bor Artnak",
            "country":"Slovenia","profile_url":"https://www.sofascore.com/tennis/player/artnak-bor/386501",
            "surface":"Hard","kickoff_utc":"2026-11-19T16:00:00Z",
            "observed_at_utc":"2026-11-18T09:00:00Z",
            "visible_birth_date_yyyymmdd":"20040604",
            "approved_model_player_id":False,
            "original_match_research":{"pre_cut_latest_row_date":20260504,"pre_cut_rows":5,
                                       "pre_cut_source_id":"A0I1"}
        }]
    }
    pp=folder/"MATRIX_TENNIS_FREE_VISIBLE_PROFILE_BIRTHDATES_RESEARCH.json"
    pp.write_text(json.dumps(profile))
    return dp,pp

def test_precut_profile_and_exact_matching_page_remain_research_only(tmp_path):
    build(tmp_path)
    r=audit(tmp_path,DAY)
    assert r["profiles_verified_against_match_details"]==1
    assert r["matches_with_verified_profiles"]==1
    assert r["new_hard_holdout_observations"]==r["new_clay_holdout_observations"]==0
    assert r["original_model_pit_equivalence_certified"] is False
    assert r["telegram_signal_authorized"] is False
    assert r["real_money"]=="BLOCKED"

def test_tampered_authentic_match_detail_rejected_by_sha(tmp_path):
    dp,_=build(tmp_path)
    dp.write_bytes(dp.read_bytes()+b" ")
    with pytest.raises(ValueError,match="PROFILE_AUDIT_ORIGINAL_DETAIL_SHA_SNAPSHOT_UNAVAILABLE"):
        audit(tmp_path,DAY)

def test_wrong_player_identity_is_rejected(tmp_path):
    _,pp=build(tmp_path)
    p=json.loads(pp.read_text())
    p["profiles"][0]["sofascore_player_id"]="12345"
    pp.write_text(json.dumps(p))
    with pytest.raises(ValueError,match="PROFILE_AUDIT_PROFILE_NOT_ON_CAPTURED_MATCH"):
        audit(tmp_path,DAY)

def test_profile_observed_after_kickoff_rejected(tmp_path):
    _,pp=build(tmp_path)
    p=json.loads(pp.read_text())
    p["profiles"][0]["observed_at_utc"]="2026-11-19T17:00:00Z"
    pp.write_text(json.dumps(p))
    with pytest.raises(ValueError,match="PROFILE_AUDIT_PLAYER_OR_PIT_CONFLICT"):
        audit(tmp_path,DAY)

def test_duplicate_identity_cannot_create_two_observations(tmp_path):
    _,pp=build(tmp_path)
    p=json.loads(pp.read_text())
    p["profiles"].append(dict(p["profiles"][0]))
    pp.write_text(json.dumps(p))
    with pytest.raises(ValueError,match="PROFILE_AUDIT_DUPLICATE_PROFILE"):
        audit(tmp_path,DAY)

def test_pre_cut_history_must_precede_match(tmp_path):
    _,pp=build(tmp_path)
    p=json.loads(pp.read_text())
    p["profiles"][0]["original_match_research"]["pre_cut_latest_row_date"]=20261119
    pp.write_text(json.dumps(p))
    with pytest.raises(ValueError,match="PROFILE_AUDIT_PRECUT_HISTORY_NOT_PRECUT"):
        audit(tmp_path,DAY)


def test_legitimate_archived_original_detail_preserves_precut_provenance(tmp_path):
    dp,_=build(tmp_path)
    original=dp.read_bytes()
    archive=dp.parent/"archive"
    archive.mkdir()
    (archive/"MATRIX_TENNIS_SOURCE_DETAILS_ORIGINAL.json").write_bytes(original)
    dp.write_bytes(original+b" ")
    result=audit(tmp_path,DAY)
    assert result["archived_original_detail_used"] is True
    assert result["source_detail_path"].endswith(
        "archive/MATRIX_TENNIS_SOURCE_DETAILS_ORIGINAL.json")
    assert result["profiles_verified_against_match_details"]==1
    assert result["new_hard_holdout_observations"]==0
    assert result["new_clay_holdout_observations"]==0


def test_mismatched_archived_detail_never_substitutes_for_exact_sha(tmp_path):
    dp,_=build(tmp_path)
    archive=dp.parent/"archive"
    archive.mkdir()
    (archive/"MATRIX_TENNIS_SOURCE_DETAILS_WRONG.json").write_bytes(
        dp.read_bytes()+b"fake other detail")
    dp.write_bytes(dp.read_bytes()+b" ")
    with pytest.raises(ValueError,match="PROFILE_AUDIT_ORIGINAL_DETAIL_SHA_SNAPSHOT_UNAVAILABLE"):
        audit(tmp_path,DAY)


def test_unapproved_archive_names_cannot_be_used_for_forged_source(tmp_path):
    dp,_=build(tmp_path)
    archive=dp.parent/"archive"
    archive.mkdir()
    (archive/"unrelated_research.json").write_bytes(dp.read_bytes())
    dp.write_bytes(dp.read_bytes()+b" ")
    with pytest.raises(ValueError,match="PROFILE_AUDIT_ORIGINAL_DETAIL_SHA_SNAPSHOT_UNAVAILABLE"):
        audit(tmp_path,DAY)


def test_main_seals_original_detail_in_reconciliation_archive(tmp_path, monkeypatch):
    from tools.matrix_tennis_free_profile_source_binding_audit import main
    import sys
    dp,_=build(tmp_path)
    original=dp.read_bytes()
    digest=hashlib.sha256(original).hexdigest()
    monkeypatch.setattr(sys,"argv",["profile_audit","--date",DAY,"--root",str(tmp_path)])
    main()
    archive=tmp_path/"evidence/tennis_calendar_reconciliation"/DAY/"archive"/(
        "MATRIX_TENNIS_SOURCE_DETAILS_SHA256_"+digest+".json")
    assert archive.read_bytes()==original
    report=tmp_path/"evidence/tennis_calendar_reconciliation"/DAY/(
        "MATRIX_TENNIS_FREE_PROFILE_SOURCE_BINDING_AUDIT_LAST.json")
    recorded=json.loads(report.read_text())
    assert recorded["sealed_original_source_archive"].endswith(archive.name)
    assert recorded["new_hard_holdout_observations"]==0
    dp.write_bytes(original+b" ")
    recovered=audit(tmp_path,DAY)
    assert recovered["archived_original_detail_used"] is True
    assert recovered["profiles_verified_against_match_details"]==1


def test_original_archive_conflict_is_rejected_without_overwrite(tmp_path,monkeypatch):
    from tools.matrix_tennis_free_profile_source_binding_audit import main
    import sys
    dp,_=build(tmp_path)
    expected=hashlib.sha256(dp.read_bytes()).hexdigest()
    archive=tmp_path/"evidence/tennis_calendar_reconciliation"/DAY/"archive"
    archive.mkdir(parents=True)
    target=archive/("MATRIX_TENNIS_SOURCE_DETAILS_SHA256_"+expected+".json")
    target.write_text("tampered")
    monkeypatch.setattr(sys,"argv",["profile_audit","--date",DAY,"--root",str(tmp_path)])
    with pytest.raises(ValueError,match="PROFILE_AUDIT_IMMUTABLE_SOURCE_CONFLICT"):
        main()
    assert target.read_text()=="tampered"
