"""Real persisted 2026-11-04 Opera SofaScore evidence must match provider, never authorize signals."""
import json
from pathlib import Path
from tools.matrix_football_sofa_fixture_crosscheck import corroborate

FOLDER=Path("evidence/football_world_inventory/2026-11-04")

def test_two_observed_sofascore_fixtures_are_source_bound():
    intake=json.loads((FOLDER/"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").read_text(encoding="utf-8"))
    observed=json.loads((FOLDER/"MATRIX_SOFA_BROWSER_OBSERVATIONS.json").read_text(encoding="utf-8"))
    checked=corroborate(intake,observed)
    assert checked["status"]=="PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL"
    assert checked["matched_count"]==2
    assert checked["rejected_count"]==0
    assert {r["fixture_id"] for r in checked["matched"]}=={"575387","561925"}
    assert all(r["identity_time_and_teams_verified"] is True for r in checked["matched"])
    assert checked["signal_generation_authorized"] is False
    assert checked["over25_exact_quote_verified"] is False
    assert checked["real_money"]=="BLOCKED"
    assert observed["flashscore_corroborated"] is False

def test_one_real_flashscore_triple_source_identity_and_no_price():
    from tools.matrix_football_flashscore_fixture_crosscheck import check
    intake=json.loads((FOLDER/"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").read_text(encoding="utf-8"))
    obs=json.loads((FOLDER/"MATRIX_SOFA_BROWSER_OBSERVATIONS.json").read_text(encoding="utf-8"))
    flash=json.loads((FOLDER/"MATRIX_FLASH_BROWSER_OBSERVATIONS.json").read_text(encoding="utf-8"))
    sofa=corroborate(intake,obs)
    result=check(intake,sofa,flash)
    assert result["status"]=="PASS_THREE_SOURCE_FIXTURE_IDENTITY_ONLY_NO_QUOTES_OR_SIGNALS"
    assert result["matched_count"]==1
    assert result["rejected_count"]==0
    assert result["matched"][0]["source_fixture_id"]=="575387"
    assert result["matched"][0]["flashscore_mid"]=="E3VsH66d"
    assert result["odds_market_verified"] is False
    assert result["calibration_parity_verified"] is False
    assert result["signal_generation_authorized"] is False
    assert result["real_money"]=="BLOCKED"
