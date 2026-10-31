import json
import pytest
from tools.matrix_tennis_tomorrow_reconciliation import compare, FLASH_TOMORROW
from tools.matrix_tennis_calendar_reconciliation_gate import SOFA

def test_real_tomorrow_snapshot_review_only():
    sofa=json.loads(SOFA.read_text(encoding="utf-8"))
    flash=json.loads(FLASH_TOMORROW.read_text(encoding="utf-8"))
    result=compare(sofa,flash,"2026-10-31")
    assert result["sofascore_raw"] == 190
    assert result["flashscore_raw"] == 132
    assert result["sofascore_validated"] == 183
    assert result["sofascore_rejected"] == 7
    assert result["sofascore_blocked"] == 1
    assert result["capture_date_context_accepted"] is True
    assert result["individual_event_dates_verified"] is False
    assert result["matches_certified"] == 0
    assert result["signals_authorized"] == 0
    assert all(row["status"] == "REVIEW_ONLY" for row in result["candidates"])

def test_reject_wrong_calendar_page():
    with pytest.raises(ValueError, match="tomorrow"):
        compare({"source":"SOFASCORE","date_label":"2026-10-31","records":[]},
                {"source":"FLASHSCORE","source_page":"https://www.flashscore.co/tenis/",
                 "user_supplied_calendar_date":"2026-10-31","individual_event_dates_verified":False,"records":[]},
                "2026-10-31")

def test_reject_wrong_user_date():
    with pytest.raises(ValueError, match="mismatch"):
        compare({"source":"SOFASCORE","date_label":"2026-10-31","records":[]},
                {"source":"FLASHSCORE","source_page":"https://www.flashscore.co/tenis/manana/",
                 "user_supplied_calendar_date":"2026-11-01","individual_event_dates_verified":False,"records":[]},
                "2026-10-31")
