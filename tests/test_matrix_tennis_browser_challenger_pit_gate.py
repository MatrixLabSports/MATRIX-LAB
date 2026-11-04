"""Exact browser-visible Challenger metadata is separate from model holdout admission."""
from datetime import datetime,timezone
from pathlib import Path
from tools.matrix_tennis_browser_challenger_pit_gate import evaluate

ROOT=Path.cwd()
DAY="2026-11-04"
T=lambda s:datetime.fromisoformat(s.replace("Z","+00:00"))

def test_two_real_4_nov_challenger_source_rows_pre_match():
    r=evaluate(ROOT,DAY,T("2026-11-04T16:00:00Z"))
    assert r["source_metadata_verified_before_kickoff"]==2
    assert r["hard_source_metadata_ready"]==1
    assert r["clay_source_metadata_ready"]==1
    assert r["new_hard_holdout_observations"]==0
    assert r["new_clay_holdout_observations"]==0
    assert all(x["official_holdout_admitted"] is False for x in r["events"])
    assert all(x["model_probability_computed"] is False for x in r["events"])
    assert r["real_money"]=="BLOCKED"
    hist={x["surface"]:x["historical_players_found"] for x in r["events"]}
    assert hist=={"Hard":2,"Clay":1}

def test_old_calendar_cannot_backdate_new_prematch_admission():
    r=evaluate(ROOT,DAY,T("2026-11-04T20:00:00Z"))
    assert r["source_metadata_verified_before_kickoff"]==0
    assert all("PROSPECTIVE_SCORE_WINDOW_CLOSED" in x["blocked"] for x in r["events"])
    assert r["new_hard_holdout_observations"]==0
    assert r["new_clay_holdout_observations"]==0
