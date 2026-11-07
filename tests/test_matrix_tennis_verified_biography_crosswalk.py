"""Real immutable evidence is the test fixture; tests cannot admit model rows."""
from copy import deepcopy
from pathlib import Path
import pytest

from tools import matrix_tennis_verified_biography_crosswalk as mod

ROOT = Path.cwd()
DAY = "2026-11-06"

def test_four_real_visible_player_bios_match_original_pre_cut_with_schedule_conflict():
    z = mod.verify(ROOT, DAY)
    assert z["schema"] == "MATRIX_TENNIS_RESEARCH_BIOGRAPHY_CROSSWALK_LAST_V1"
    assert z["biographical_id_triplets_matched"] == 4
    assert z["total_source_metadata_events"] == 2
    assert z["events_with_schedule_conflicts"] == 2
    assert z["events_with_match_page_clock_conflicts"] == 1
    assert z["events_with_match_page_clock_display_agreement"] == 1
    assert z["organizer_official_followed_by_schedule_events"] == 1
    assert z["organizer_official_exact_start_attested_count"] == 0
    official=next(e["official_order_of_play"] for e in z["events"] if e["sofascore_id"]=="17427360")
    assert official["clock_type"]=="FOLLOWED_BY_PREVIOUS_MATCH"
    assert official["exact_start_from_organizer_attested"] is False
    assert {e["sofascore_id"]: e["independent_match_page_clock"]["displayed_clock_agrees"] for e in z["events"]} == {"17427360": False, "17427540": True}
    assert {p["name"] for p in z["players"]} == {
        "Nishesh Basavareddy", "Jerome Kym", "Gonzalo Bueno", "Lautaro Midon"}
    assert {p["lane"] for p in z["players"]} == {"Hard", "Clay"}
    assert all(p["exact_name_birthdate_country_match"] for p in z["players"])
    assert all(not p["production_feature_equivalence_certified"] for p in z["players"])
    assert all(not e["prospective_model_admission_authorized"] for e in z["events"])
    assert z["new_hard_holdout_admissions"] == z["new_clay_holdout_admissions"] == 0
    assert z["telegram_signal_authorized"] is False
    assert z["paid_api_used"] is False
    assert z["real_money"] == "BLOCKED"

def test_month_and_birthdate_are_parsed_strictly():
    assert mod.spanish_birthday("29 de marzo de 2004") == "20040329"
    with pytest.raises(ValueError, match="VISIBLE_BIRTHDATE_INVALID"):
        mod.spanish_birthday("29 de mars de 2004")

def test_fake_biography_cannot_create_provider_crosswalk(monkeypatch):
    original = mod.file
    def corrupt(root, path):
        obj, digest = original(root, path)
        if path.name == "MATRIX_TENNIS_OPERA_BIOGRAPHY_VISIBLE_OBSERVATIONS.json":
            obj = deepcopy(obj)
            obj["profiles"][0]["birth_date_visible"] = "3 de mayo de 2005"
        return obj, digest
    monkeypatch.setattr(mod, "file", corrupt)
    with pytest.raises(ValueError, match="ORIGINAL_PROVIDER_PROFILE_BIOGRAPHY_NOT_UNIQUE"):
        mod.verify(ROOT, DAY)

def test_duplicate_native_profile_fails_closed(monkeypatch):
    original = mod.file
    def corrupt(root, path):
        obj, digest = original(root, path)
        if path.name == "MATRIX_TENNIS_OPERA_BIOGRAPHY_VISIBLE_OBSERVATIONS.json":
            obj = deepcopy(obj)
            obj["profiles"][1]["sofascore_player_id"] = obj["profiles"][0]["sofascore_player_id"]
            obj["profiles"][1]["url"] = obj["profiles"][0]["url"]
        return obj, digest
    monkeypatch.setattr(mod, "file", corrupt)
    with pytest.raises(ValueError, match="UNTRUSTED_OR_DUPLICATED_NATIVE_PROFILE"):
        mod.verify(ROOT, DAY)

def test_post_kickoff_biography_cannot_backfill_forecast(monkeypatch):
    original = mod.file
    def corrupt(root, path):
        obj, digest = original(root, path)
        if path.name == "MATRIX_TENNIS_OPERA_BIOGRAPHY_VISIBLE_OBSERVATIONS.json":
            obj = deepcopy(obj)
            obj["captured_at_utc"] = "2026-11-07T00:00:00Z"
        return obj, digest
    monkeypatch.setattr(mod, "file", corrupt)
    with pytest.raises(ValueError, match="NON_PROSPECTIVE_OR_UNTRUSTED_EVENT"):
        mod.verify(ROOT, DAY)

def test_altered_original_history_authority_fails_closed(monkeypatch):
    original = mod.file
    def corrupt(root, path):
        obj, digest = original(root, path)
        if path.name == "MATRIX_COR0203_IDENTITY_AUTHORITY_LAST.json":
            obj = deepcopy(obj)
            obj["outcomes_used"] = True
        return obj, digest
    monkeypatch.setattr(mod, "file", corrupt)
    with pytest.raises(ValueError, match="PRE_CUT_AUTHORITY_INVALID"):
        mod.verify(ROOT, DAY)

def test_falsified_flashscore_event_time_cannot_be_treated_as_agreement(monkeypatch):
    original = mod.file
    def corrupt(root, path):
        obj, digest = original(root, path)
        if path.name == "MATRIX_TENNIS_FLASHSCORE_MATCH_TIME_VISIBLE_OBSERVATIONS.json":
            obj = deepcopy(obj)
            obj["rows"][1]["visible_match_datetime_text"] = "06.11.2026 09:00"
        return obj, digest
    monkeypatch.setattr(mod, "file", corrupt)
    r = mod.verify(ROOT, DAY)
    assert r["events_with_match_page_clock_conflicts"] == 2
    assert r["events_with_match_page_clock_display_agreement"] == 0
    assert r["new_hard_holdout_admissions"] == r["new_clay_holdout_admissions"] == 0


def test_flashscore_clock_cannot_be_reassigned_to_wrong_native_fixture(monkeypatch):
    original = mod.file
    def corrupt(root, path):
        obj, digest = original(root, path)
        if path.name == "MATRIX_TENNIS_FLASHSCORE_MATCH_TIME_VISIBLE_OBSERVATIONS.json":
            obj = deepcopy(obj)
            obj["rows"][0]["flashscore_mid"] = "WRONG"
        return obj, digest
    monkeypatch.setattr(mod, "file", corrupt)
    with pytest.raises(ValueError, match="UNTRUSTED_OR_POSTMATCH_FLASHSCORE_CLOCK"):
        mod.verify(ROOT, DAY)


def test_flashscore_visible_calendar_day_not_same_fails_closed(monkeypatch):
    original = mod.file
    def corrupt(root, path):
        obj, digest = original(root, path)
        if path.name == "MATRIX_TENNIS_FLASHSCORE_MATCH_TIME_VISIBLE_OBSERVATIONS.json":
            obj = deepcopy(obj)
            obj["rows"][0]["visible_match_datetime_text"] = "07.11.2026 09:00"
        return obj, digest
    monkeypatch.setattr(mod, "file", corrupt)
    with pytest.raises(ValueError, match="FLASHSCORE_CLOCK_WRONG_TARGET_DAY"):
        mod.verify(ROOT, DAY)

def test_official_order_of_play_cannot_invent_exact_start(monkeypatch):
    original=mod.file
    def corrupt(root,path):
        obj,digest=original(root,path)
        if path.name=="MATRIX_TENNIS_BRATISLAVA_OFFICIAL_ORDER_OF_PLAY_RESEARCH.json":
            obj=deepcopy(obj)
            obj["official_target_match_exact_clock"]="14:00"
        return obj,digest
    monkeypatch.setattr(mod,"file",corrupt)
    with pytest.raises(ValueError,match="UNTRUSTED_OFFICIAL_ORDER_OF_PLAY_PROOF"):
        mod.verify(ROOT,DAY)


def test_forged_official_participant_list_blocks_match(monkeypatch):
    original=mod.file
    def corrupt(root,path):
        obj,digest=original(root,path)
        if path.name=="MATRIX_TENNIS_BRATISLAVA_OFFICIAL_ORDER_OF_PLAY_RESEARCH.json":
            obj=deepcopy(obj)
            obj["official_names"][0]="Someone Else"
        return obj,digest
    monkeypatch.setattr(mod,"file",corrupt)
    with pytest.raises(ValueError,match="OFFICIAL_ORDER_OF_PLAY_PLAYERS_DISAGREE"):
        mod.verify(ROOT,DAY)
