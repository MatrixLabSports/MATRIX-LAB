from datetime import datetime,timezone
import json
from pathlib import Path
import pytest
from tools.matrix_tennis_windows_browser_calendar_capture import (
    observed,day_visible,date_evidence,replace_if_not_regressed)
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


def test_full_year_rendered_calendar_control_is_evidence():
    assert date_evidence("FLASHSCORE","2026-11-05",
        controls=["jueves, 5 de noviembre de 2026"],
        visible_text="Other news")=="VISIBLE_CALENDAR_CONTROL_FULL_YEAR"
    assert date_evidence("SOFASCORE","2026-11-06",
        controls=["viernes, 6 de noviembre de 2026"],
        visible_text="Other news")=="VISIBLE_CALENDAR_CONTROL_FULL_YEAR"


def test_full_body_date_after_twelve_thousand_characters_is_not_lost():
    body="Other news "*1200+" jueves, 5 de noviembre de 2026"
    assert len(body)>12000
    assert date_evidence("FLASHSCORE","2026-11-05",
        controls=[],visible_text=body)=="VISIBLE_BODY_FULL_YEAR_DATE"


def test_no_url_only_or_wrong_date_admission():
    assert date_evidence("SOFASCORE","2026-11-05",
        controls=[],visible_text="https://www.sofascore.com/es/tennis?date=tomorrow") is None
    assert date_evidence("FLASHSCORE","2026-11-05",
        controls=["jueves 15 de noviembre de 2026"],
        visible_text="Today 15/11/2026") is None
    assert day_visible("FLASHSCORE","2026-11-05","15/11/2026") is False
    assert day_visible("FLASHSCORE","2026-11-05","05/11/2026") is True
    assert day_visible("SOFASCORE","2026-11-05","5/11/2026") is True
    assert day_visible("SOFASCORE","2026-11-05","5.11.2026") is True


def test_calendar_date_is_not_a_match_kickoff_or_surface_certificate():
    x=observed("2026-11-06","SOFASCORE",[
        {"url":"https://www.sofascore.com/es/tennis/match/foo-bar/aBcDe#id:123456789",
         "name":"Foo / Bar"}],
        page_url="https://www.sofascore.com/es/tennis/2026-11-06",
        page_date_verified=True,now=T)
    assert x["observed_link_count"]==1
    assert x["individual_match_date_verified"] is False
    assert x["surface_per_event_verified"] is False
    assert x["probability_generation_authorized"] is False
    assert x["telegram_signals_authorized"] is False
