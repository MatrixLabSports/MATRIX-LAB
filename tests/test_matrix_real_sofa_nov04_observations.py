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
