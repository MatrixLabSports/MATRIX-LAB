from datetime import datetime,timezone
from pathlib import Path
import json
from tools.matrix_tennis_free_browser_daily_discovery import collect,canon

def test_free_browser_sources_do_not_promote_observations(tmp_path):
    folder=tmp_path/"evidence/tennis_calendar_physical/2026-11-04"
    folder.mkdir(parents=True)
    for source,name,url in [
      ("SOFASCORE","sofascore_opera_full_link_observations.json","https://www.sofascore.com/es/tennis/match/a-b/c#id:101"),
      ("FLASHSCORE","flashscore_opera_full_link_observations.json","https://www.flashscore.co/partido/tenis/player-a/player-b/?mid=AB")]:
        doc={"schema":"MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1",
          "source":source,"target_date_bogota":"2026-11-04",
          "collected_at_utc":"2026-11-04T12:00:00Z",
          "canonical_fixture_export_authorized":False,
          "probability_generation_authorized":False,"real_money":"BLOCKED",
          "matches":[{"url":url,"display_name":"Two Players"},
                     {"url":url,"display_name":"Duplicate"}]}
        (folder/name).write_bytes(canon(doc))
    r=collect(tmp_path,"2026-11-04",datetime(2026,11,4,14,tzinfo=timezone.utc))
    assert r["observed_source_links"]==2
    assert r["hard_new_prospective_observations"]==0
    assert r["clay_new_prospective_observations"]==0
    assert r["model_calibration_mutated"] is False
    assert r["telegram_signal_authorized"] is False

def test_missing_browser_capture_must_not_be_invented(tmp_path):
    r=collect(tmp_path,"2026-11-04",datetime(2026,11,4,14,tzinfo=timezone.utc))
    assert r["observed_source_links"]==0
    assert all(x["status"]=="NO_PERSISTED_OPERA_CAPTURE" for x in r["sources"])

def test_unsafe_source_declaring_production_is_rejected(tmp_path):
    p=tmp_path/"evidence/tennis_calendar_physical/2026-11-04/sofascore_opera_full_link_observations.json"
    p.parent.mkdir(parents=True)
    p.write_bytes(canon({"schema":"MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1",
         "source":"SOFASCORE","target_date_bogota":"2026-11-04",
         "canonical_fixture_export_authorized":True,
         "probability_generation_authorized":False,"real_money":"BLOCKED",
         "matches":[]}))
    r=collect(tmp_path,"2026-11-04",datetime(2026,11,4,14,tzinfo=timezone.utc))
    assert r["observed_source_links"]==0
    assert r["rejections"][0]["reason"]=="CAPTURE_GOVERNANCE_NOT_COMPATIBLE"

def test_future_dated_capture_is_rejected(tmp_path):
    p=tmp_path/"evidence/tennis_calendar_physical/2026-11-04/sofascore_opera_full_link_observations.json"
    p.parent.mkdir(parents=True)
    p.write_bytes(canon({"schema":"MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1",
      "source":"SOFASCORE","target_date_bogota":"2026-11-04",
      "collected_at_utc":"2026-11-05T00:00:00Z",
      "canonical_fixture_export_authorized":False,
      "probability_generation_authorized":False,"real_money":"BLOCKED","matches":[]}))
    r=collect(tmp_path,"2026-11-04",datetime(2026,11,4,14,tzinfo=timezone.utc))
    assert r["observed_source_links"]==0
    assert r["rejections"][0]["reason"]=="CAPTURE_TIMESTAMP_IN_FUTURE"
