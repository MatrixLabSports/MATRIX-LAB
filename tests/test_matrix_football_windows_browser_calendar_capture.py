"""Offline contracts for authorized football browser capture; zero model admission."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from tools.matrix_football_windows_browser_calendar_capture import (
    classify, displayed_date, persist,
)

NOW = datetime(2026, 11, 17, 2, 12, 0, tzinfo=timezone.utc)
DAY = "2026-11-21"
SOFA_URL = "https://www.sofascore.com/es/football/match/fulham-manchester-city/rsT#id:16363661"
FLASH_URL = "https://www.flashscore.co/partido/futbol/fulham-69ZiU2Om/manchester-city-Wtn9Stg0/?mid=Ab12Cd34"


def sofa_row():
    return {"url": SOFA_URL, "name": "21/11/26 7:30 Manchester City Fulham"}


def make(source, rows, *, when=NOW):
    return classify(DAY, source, rows, date_verified=True,
                    page_url="https://example.invalid/read-only-calendar",
                    collected_at=when)


def test_exact_date_labels_do_not_match_neighboring_days():
    assert displayed_date(DAY, "21/11/26 7:30") is True
    assert displayed_date(DAY, "21.11.2026 07:30") is True
    assert displayed_date(DAY, "2026-11-21") is True
    assert displayed_date(DAY, "12/11/26 7:30") is False


def test_sofa_authorized_visible_fixture_link_without_promotion():
    report = make("SOFASCORE", [sofa_row(), sofa_row()])
    assert report["observed_link_count"] == 1
    assert report["links"][0]["sofascore_event_id"] == "16363661"
    assert report["canonical_prematch_inputs_authorized"] is False
    assert report["model_probability_generated"] is False
    assert report["source_clock_timezone_certified"] is False
    assert report["real_money"] == "BLOCKED"


def test_sofa_wrong_day_and_untrusted_domain_are_rejected():
    rows = [
        {**sofa_row(), "name": "20/11/26 7:30 Manchester City Fulham"},
        {**sofa_row(), "url": SOFA_URL.replace("sofascore.com", "sofascore.com.evil.test")},
    ]
    assert make("SOFASCORE", rows)["observed_link_count"] == 0


def test_flashscore_sidebar_and_wrong_domain_not_counted():
    entries = [
        {"url": FLASH_URL, "name": "Manchester City - Fulham", "is_calendar_row": False},
        {"url": FLASH_URL.replace("flashscore.co", "flashscore.co.evil.test"),
         "name": "Manchester City - Fulham", "is_calendar_row": True},
    ]
    assert make("FLASHSCORE", entries)["observed_link_count"] == 0


def test_flashscore_calendar_mid_is_research_only():
    report=make("FLASHSCORE", [
        {"url": FLASH_URL, "name": "Manchester City - Fulham", "is_calendar_row": True},
        {"url": FLASH_URL.split("?")[0], "name": "Manchester City - Fulham", "is_calendar_row": True},
    ])
    assert report["observed_link_count"] == 2
    assert report["links"][0]["flashscore_mid"] == "Ab12Cd34"
    assert report["links"][1]["flashscore_mid"] is None
    assert report["independent_provider_crosswalk_certified"] is False
    assert report["telegram_signal_authorized"] is False


def test_missing_selected_day_fails_closed():
    with pytest.raises(ValueError, match="VISIBLE_SELECTED_DAY_NOT_CERTIFIED"):
        classify(DAY, "SOFASCORE", [sofa_row()], date_verified=False,
                 page_url="https://www.sofascore.com/es/football/2026-11-21",
                 collected_at=NOW)


def test_visible_capture_is_append_only_across_refreshes(tmp_path):
    first = make("SOFASCORE", [sofa_row()])
    assert persist(tmp_path, first)["status"] == "VISIBLE_RESEARCH_CAPTURE_PERSISTED"
    current = tmp_path/"evidence/football_calendar_physical"/DAY/"sofascore_visible_links.json"
    original = current.read_bytes()
    assert persist(tmp_path, first)["status"] == "OLDER_CAPTURE_REJECTED"
    second = make("SOFASCORE", [sofa_row()], when=NOW+timedelta(minutes=1))
    assert persist(tmp_path, second)["status"] == "VISIBLE_RESEARCH_CAPTURE_PERSISTED"
    prior=list((current.parent/"archive").glob("sofascore_*.json"))
    assert len(prior)==1
    assert prior[0].read_bytes()==original
    assert json.loads(current.read_text())["captured_at_utc"]==second["captured_at_utc"]


def test_no_empty_fake_browser_admission(tmp_path):
    assert persist(tmp_path, make("SOFASCORE", []))["status"] == "NO_ADMISSIBLE_VISIBLE_LINKS"
    assert not (tmp_path/"evidence/football_calendar_physical"/DAY/"sofascore_visible_links.json").exists()
