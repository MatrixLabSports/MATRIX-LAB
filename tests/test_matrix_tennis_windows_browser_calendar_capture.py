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
    assert date_evidence("SOFASCORE","2026-11-05",
        controls=[],visible_text=body)=="VISIBLE_BODY_FULL_YEAR_DATE"
    assert date_evidence("FLASHSCORE","2026-11-05",
        controls=[],visible_text=body) is None


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

def test_collection_captures_today_and_tomorrow_only_when_rendered_date_is_real(tmp_path,monkeypatch):
    import sys,types
    from tools.matrix_tennis_windows_browser_calendar_capture import run
    class Page:
        def __init__(self):
            self.url=""
            self.closed=False
        def goto(self,url,**kwargs):
            self.url=url
            return types.SimpleNamespace(status=200)
        def wait_for_timeout(self,ms):
            assert ms<=2000
        def evaluate(self,script):
            day="2026-11-06" if ("2026-11-06" in self.url or "/tenis/manana/" in self.url) else "2026-11-05"
            human="6" if day.endswith("06") else "5"
            if "sofascore.com" in self.url:
                link="https://www.sofascore.com/es/tennis/match/foo-bar/xyz123#id:12345"
            else:
                link="https://www.flashscore.co/partido/tenis/foo/bar/?mid=abc123"
            return {
                "text":"Page has tournament news and results",
                "dateControls":[f"jueves, {human} de noviembre de 2026"],
                "links":[{"url":link,"name":"Foo vs Bar"}],
            }
        def close(self):
            self.closed=True
    class Context:
        def new_page(self):
            return Page()
    class Browser:
        contexts=[Context()]
    class Playwright:
        chromium=types.SimpleNamespace(connect_over_cdp=lambda endpoint,timeout:Browser())
    class Manager:
        def __enter__(self):
            return Playwright()
        def __exit__(self,*args):
            return False
    fake=types.ModuleType("playwright.sync_api")
    fake.sync_playwright=lambda:Manager()
    fake.Error=RuntimeError
    monkeypatch.setitem(sys.modules,"playwright.sync_api",fake)
    x=run(tmp_path,"2026-11-05","http://127.0.0.1:9222")
    assert x["capture_dates_bogota"]==["2026-11-05","2026-11-06"]
    assert len(x["provider_results"])==4
    assert all(r["status"]=="PERSISTED_VISIBLE_BROWSER_LINKS" for r in x["provider_results"])
    assert x["paid_api_used"] is False
    assert x["holdout_admitted"]==0
    for day in x["capture_dates_bogota"]:
        for filename in ("sofascore_opera_full_link_observations.json",
                         "flashscore_opera_full_link_observations.json"):
            p=tmp_path/"evidence/tennis_calendar_physical"/day/filename
            j=json.loads(p.read_text())
            assert j["target_date_bogota"]==day
            assert j["observed_link_count"]==1
            assert j["individual_match_date_verified"] is False


def test_evidence_path_publisher_never_rebases_runner_or_stages_model_state():
    root=Path(__file__).resolve().parents[1]
    powershell=(root/"tools/windows/persist_matrix_tennis_browser_evidence.ps1").read_text()
    assert "git rebase" not in powershell
    assert "git worktree add --detach" in powershell
    assert "cherry-pick" in powershell
    assert "TENNIS_BROWSER_REAL_REMOTE_EVIDENCE_CONFLICT_FAIL_CLOSED" in powershell
    assert "tennis_calendar_(physical|reconciliation)" in powershell
    assert 'git add -- evidence/cor0203' not in powershell
    assert 'git add -- evidence/tennis_parallel_lanes' not in powershell


def test_flashscore_only_selected_day_control_can_certify_calendar():
    # Flashscore news and sidebar links may mention tomorrow while the
    # selected sports calendar is still on today. Never accept body text.
    assert date_evidence("FLASHSCORE","2026-11-06",
        controls=["jueves, 5 de noviembre de 2026"],
        visible_text="Noticias: viernes, 6 de noviembre de 2026") is None
    assert date_evidence("FLASHSCORE","2026-11-06",
        controls=["viernes, 6 de noviembre de 2026"],
        visible_text="Noticias del día anterior")=="VISIBLE_CALENDAR_CONTROL_FULL_YEAR"


def test_flashscore_capture_uses_selected_day_attribute_in_browser():
    from tools.matrix_tennis_windows_browser_calendar_capture import run
    import inspect
    code=inspect.getsource(run)
    assert '[aria-haspopup="listbox"]' in code
    assert "a.getAttribute('aria-label')" in code
    assert "www.flashscore.co/tenis/manana/" in code
    assert "selected_day_control_required" in code
