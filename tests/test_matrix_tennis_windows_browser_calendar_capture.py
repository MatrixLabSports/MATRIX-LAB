from datetime import datetime,timezone
import json
from pathlib import Path
import pytest
from tools.matrix_tennis_windows_browser_calendar_capture import (
    observed,day_visible,replace_if_not_regressed)
T=datetime(2026,11,4,16,tzinfo=timezone.utc)

def test_realistic_sofa_href_and_flash_href_are_parsed_without_fake_event_date():
    s=observed("2026-11-04","SOFASCORE",
      [{"url":"https://www.sofascore.com/es/tennis/match/nishesh-basavareddy-mika-brunold/mcVcsoTmd#id:17427368","name":"Nishesh Basavareddy - Mika Brunold"},
       {"url":"https://evil.example/es/tennis/match/a-b/z#id:123","name":"Fake"}],
       page_url="https://www.sofascore.com/es/tennis/2026-11-04",
       page_date_verified=True,now=T)
    assert s["observed_link_count"]==1
    assert s["matches"][0]["source_event_id"]=="17427368"
    assert s["canonical_fixture_export_authorized"] is False
    assert s["individual_match_date_verified"] is False
    f=observed("2026-11-04","FLASHSCORE",[
      {"url":"https://www.flashscore.co/partido/tenis/basavareddy-nishesh-rqtJueQt/brunold-mika-AqiRBgj5/?mid=jBPR6ne4","name":"BAS - BRU"}],
       page_url="https://www.flashscore.co/tenis/?d=2026-11-04",
       page_date_verified=True,now=T)
    assert f["observed_link_count"]==1
    assert f["matches"][0]["visible_mid_query"]=="jBPR6ne4"

def test_date_not_visible_is_never_accepted():
    assert day_visible("FLASHSCORE","2026-11-04","miércoles, 4 de noviembre de 2026") is True
    assert day_visible("SOFASCORE","2026-11-04","4/11/2026") is True
    assert day_visible("SOFASCORE","2026-11-04","3/11/2026") is False
    with pytest.raises(ValueError,match="TARGET_DATE"):
        observed("2026-11-04","SOFASCORE",[],
          page_url="https://www.sofascore.com/es/tennis/2026-11-04",
          page_date_verified=False,now=T)

def test_regressed_capture_does_not_delete_previous_authentic_events(tmp_path):
    day="2026-11-04"
    report=observed(day,"SOFASCORE",[
      {"url":"https://www.sofascore.com/es/tennis/match/nishesh-basavareddy-mika-brunold/mcVcsoTmd#id:17427368","name":"Nishesh - Mika"}],
      page_url="https://www.sofascore.com/es/tennis/2026-11-04",
      page_date_verified=True,now=T)
    first=replace_if_not_regressed(tmp_path,day,"SOFASCORE",report)
    assert first["status"]=="PERSISTED_VISIBLE_BROWSER_LINKS"
    p=tmp_path/"evidence/tennis_calendar_physical/2026-11-04/sofascore_opera_full_link_observations.json"
    original=p.read_bytes()
    smaller={**report,"matches":[],"observed_link_count":0}
    second=replace_if_not_regressed(tmp_path,day,"SOFASCORE",smaller)
    assert second["status"]=="REJECTED_EMPTY_OR_REGRESSED_BROWSER_RESULT"
    assert p.read_bytes()==original
