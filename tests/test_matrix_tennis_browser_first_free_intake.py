"""Hard/Clay browser intake must never call expired paid APIs or alter holdouts."""
import json
from pathlib import Path
import pytest
from tools.matrix_tennis_browser_first_free_intake import inventory,SCHEMA,ROOT,HARD,CLAY

D="2026-11-04"

def setup(root,missing=None):
    h=root/HARD;h.parent.mkdir(parents=True,exist_ok=True)
    h.write_text(json.dumps({"unique_calibration_observations":405,"metrics_opened":False}))
    c=root/CLAY;c.parent.mkdir(parents=True,exist_ok=True)
    c.write_text(json.dumps({"observation_count":3,"metrics_opened":False,
       "outcomes_read":0,"real_money":"BLOCKED"}))
    for source,name,domain,segment in (
        ("SOFASCORE","sofascore_opera_full_link_observations.json","www.sofascore.com","/tennis/match/"),
        ("FLASHSCORE","flashscore_opera_full_link_observations.json","www.flashscore.co","/partido/tenis/")):
        if source==missing:continue
        p=root/ROOT/D/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps({"schema":"MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1",
         "source":source,"target_date_bogota":D,
         "real_money":"BLOCKED","canonical_fixture_export_authorized":False,
         "probability_generation_authorized":False,"telegram_signals_authorized":False,
         "observed_link_count":1,
         "matches":[{"display_name":"player A — player B",
                     "url":f"https://{domain}{segment}example"}]}))
    return root

def test_real_link_snapshot_only_no_unearned_progress(tmp_path):
    root=setup(tmp_path)
    beforeh=(root/HARD).read_bytes();beforec=(root/CLAY).read_bytes()
    v=inventory(root,D)
    assert v["schema"]==SCHEMA
    assert v["status"]=="FREE_BROWSER_LINKS_CAPTURED_METADATA_NOT_YET_CERTIFIED"
    assert [r["links"] for r in v["source_observations"]]==[1,1]
    assert v["hard_original_unique_observations"]==405
    assert v["clay_original_prospective_observations"]==3
    assert v["hard_new_holdout_admissions"]==0
    assert v["clay_new_holdout_admissions"]==0
    assert v["paid_api_required"] is False
    assert v["telegram_signal_authorized"] is False
    assert (root/HARD).read_bytes()==beforeh
    assert (root/CLAY).read_bytes()==beforec

def test_missing_flashscore_is_not_silent_zero_certification(tmp_path):
    v=inventory(setup(tmp_path,missing="FLASHSCORE"),D)
    assert v["status"]=="AWAITING_AUTHENTIC_BROWSER_CAPTURE"
    assert v["source_observations"][1]["status"]=="MISSING_CAPTURE"
    assert v["canonical_fixture_export_authorized"] is False

def test_wrong_source_calendar_date_rejected(tmp_path):
    root=setup(tmp_path)
    p=root/ROOT/D/"sofascore_opera_full_link_observations.json"
    j=json.loads(p.read_text());j["target_date_bogota"]="2026-11-03"
    p.write_text(json.dumps(j))
    with pytest.raises(ValueError,match="UNTRUSTED_CALENDAR_CAPTURE"):
        inventory(root,D)

def test_untrusted_outside_source_url_rejected(tmp_path):
    root=setup(tmp_path)
    p=root/ROOT/D/"sofascore_opera_full_link_observations.json"
    j=json.loads(p.read_text());j["matches"][0]["url"]="https://attacker.example/tennis/match/fake"
    p.write_text(json.dumps(j))
    with pytest.raises(ValueError,match="UNEXPECTED_SOURCE_LINK"):
        inventory(root,D)
