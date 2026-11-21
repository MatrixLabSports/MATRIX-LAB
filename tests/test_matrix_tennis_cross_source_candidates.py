import json
from tools.matrix_tennis_cross_source_candidates import (
    reconcile, sofa_tokens, flash_tokens, tokens,
)
from tools.matrix_tennis_calendar_reconciliation_gate import SOFA, FLASH

def test_normalization_handles_accents():
    assert "zarazua" in tokens("Zarazúa")

def test_cross_source_candidates_never_certify():
    sofa = {"source":"SOFASCORE","date_label":"2026-10-31",
            "records":[{"name":"31/10/26 12:00 A. Vallejo G. Dimitrov",
                        "url":"https://www.sofascore.com/es/tennis/match/adolfo-daniel-vallejo-grigor-dimitrov/abc#id:123"}]}
    flash = {"source":"FLASHSCORE","records":[
        {"name":"Adolfo Daniel Vallejo - Grigor Dimitrov","url":"https://www.flashscore.co/partido/tenis/abc/"}]}
    result = reconcile(sofa,flash,"2026-10-31")
    assert result["candidate_sofascore_events"] == 1
    assert result["cross_source_matches_certified"] == 0
    assert result["signals_authorized"] == 0
    assert result["candidates"][0]["status"] == "REVIEW_ONLY"

def test_real_capture_preserved_and_no_signals():
    sofa=json.loads(SOFA.read_text(encoding="utf-8"))
    flash=json.loads(FLASH.read_text(encoding="utf-8"))
    result=reconcile(sofa,flash,"2026-10-31")
    assert result["sofascore_raw"] == 190
    assert result["flashscore_raw"] == 259
    assert result["sofascore_validated"] == 183
    assert result["sofascore_rejected"] == 7
    assert result["sofascore_blocked"] == 1
    assert result["signals_authorized"] == 0
    assert result["cross_source_matches_certified"] == 0
    assert all(row["status"]=="REVIEW_ONLY" for row in result["candidates"])
