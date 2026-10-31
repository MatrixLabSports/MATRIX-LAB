import json
from pathlib import Path
import pytest
from tools.matrix_tennis_calendar_reconciliation_gate import readiness, SOFA, FLASH

def test_real_flashscore_capture_is_fail_closed():
    sofa = json.loads(SOFA.read_text(encoding="utf-8"))
    flash = json.loads(FLASH.read_text(encoding="utf-8"))
    result = readiness(sofa, flash)
    assert result["sofascore_raw"] == 190
    assert result["flashscore_raw"] == 259
    assert result["cross_source_matching_permitted"] is False
    assert result["cross_source_matches_certified"] == 0
    assert result["signals_authorized"] == 0
    assert result["block_reason"] == "FLASHSCORE_DATE_NOT_VERIFIED"

def test_date_mismatch_stays_blocked():
    result = readiness({"source":"SOFASCORE","date_label":"2026-10-31","records":[]},
                       {"source":"FLASHSCORE","source_page_date_verified":True,"calendar_date":"2026-10-30","records":[]})
    assert not result["cross_source_matching_permitted"]

def test_explicit_verified_date_allows_matching_not_signals():
    result = readiness({"source":"SOFASCORE","date_label":"2026-10-31","records":[]},
                       {"source":"FLASHSCORE","source_page_date_verified":True,"calendar_date":"2026-10-31","records":[]})
    assert result["cross_source_matching_permitted"]
    assert result["signals_authorized"] == 0
    assert result["cross_source_matches_certified"] == 0

def test_invalid_source_fails():
    with pytest.raises(ValueError):
        readiness({"source":"OTHER","date_label":"2026-10-31","records":[]},
                  {"source":"FLASHSCORE","records":[]})
