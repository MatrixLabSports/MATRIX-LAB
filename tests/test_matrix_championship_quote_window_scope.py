"""Read-only quote-window scopes; all odds provider calls are separate."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest

from tools.matrix_championship_quote_window_scope import scope

ROOT=Path(__file__).resolve().parents[1]/"evidence"/"football_world_inventory"/"2026-11-03"
FILES=[
    "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
    "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json",
    "MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION.json",
    "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json",
    "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json",
]

def originals():
    return [json.loads((ROOT/path).read_text(encoding="utf-8")) for path in FILES]

def test_real_archived_prospective_pre_match_window_has_six_only_research_targets():
    source,shadow,att,sofa,flash=originals()
    x,y,gate=scope(source,shadow,att,sofa,flash,
                   now=datetime(2026,11,3,18,30,tzinfo=timezone.utc))
    assert gate["research_only_eligible_count"]==6
    assert set(gate["research_only_ids"])=={
        "561917","561918","561921","561922","561924","561928"}
    assert x["fixture_count"]==6
    assert y["scored_count"]==6
    assert x["signal_generation_authorized"] is False
    assert y["market_signal_authorized"] is False
    assert gate["production_probability_authorized"] is False
    assert gate["telegram_signal_authorized"] is False
    assert gate["real_money"]=="BLOCKED"
    assert all("p_matrix" not in row for row in y["scored"])


def test_outside_two_hour_window_is_zero_and_never_price_eligible():
    d=originals()
    x,y,gate=scope(*d,now=datetime(2026,11,3,10,40,tzinfo=timezone.utc))
    assert gate["research_only_eligible_count"]==0
    assert x["fixtures"]==[]
    assert y["scored"]==[]


def test_started_fixture_never_eligible():
    d=originals()
    _,_,gate=scope(*d,now=datetime(2026,11,3,21,0,tzinfo=timezone.utc))
    assert gate["research_only_eligible_count"]==0


def test_incorrect_browser_kickoff_blocks_target():
    source,shadow,att,sofa,flash=originals()
    flash=deepcopy(flash)
    match=next(r for r in flash["matched"] if r["source_fixture_id"]=="561918")
    match["kickoff_utc"]="2026-11-03T20:00:00+00:00"
    _,_,gate=scope(source,shadow,att,sofa,flash,
                   now=datetime(2026,11,3,18,30,tzinfo=timezone.utc))
    assert "561918" not in gate["research_only_ids"]
    assert gate["research_only_eligible_count"]==5


def test_source_gov_change_fails_closed():
    source,shadow,att,sofa,flash=originals()
    source=deepcopy(source);source["real_money"]="ENABLED"
    with pytest.raises(ValueError,match="GOVERNANCE"):
        scope(source,shadow,att,sofa,flash,
              now=datetime(2026,11,3,18,30,tzinfo=timezone.utc))


def test_stale_source_fails_closed():
    source,shadow,att,sofa,flash=originals()
    source=deepcopy(source);source["generated_at_utc"]="2026-10-29T05:00:00+00:00"
    with pytest.raises(ValueError,match="STALE"):
        scope(source,shadow,att,sofa,flash,
              now=datetime(2026,11,3,18,30,tzinfo=timezone.utc))
