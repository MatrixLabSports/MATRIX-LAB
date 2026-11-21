from app.research.tennis.prospective_ledger import TennisProspectiveEvidenceLedger
from app.research.tennis.r251_world_pipeline import BASE12_FIELDS, WorldTennisEvent
from app.research.tennis.r251_r340_connector import (
    HIST8_FIELDS, Static4Snapshot, run_world_to_r251,
)

SHA="b"*64

def event():
    return WorldTennisEvent(
        event_id="e1", player1_id="p1", player2_id="p2",
        competition_id="c1", competition_name="C1", season_id="2026", round="QF",
        surface="Hard", environment="Outdoor", tour_level="C",
        event_start_utc="2026-09-28T15:00:00+00:00",
        source_provider="authority", source_reference="fixture/e1",
        source_snapshot_sha256=SHA,
    )

def static4(_):
    return (
        Static4Snapshot(100,600,24.0,"R","2026-09-27T10:00:00+00:00",SHA),
        Static4Snapshot(120,500,26.0,"L","2026-09-27T10:00:00+00:00",SHA),
    )

def hist8(_):
    return {f:0.1 for f in HIST8_FIELDS}

def test_complete_r340_plus_static4_reaches_r251(tmp_path):
    calls=[]
    result=run_world_to_r251(
        events=[event()], ledger=TennisProspectiveEvidenceLedger(tmp_path/"l.jsonl"),
        registered_at_utc="2026-09-27T09:00:00+00:00",
        static4_loader=static4, r340_hist8_loader=hist8,
        r251_scorer=lambda e,f: calls.append((e.event_id,tuple(f))) or {"p_matrix":0.61},
    )
    assert result["r251_scored"]==1
    assert result["rows"][0]["status"]=="R251_SCORED_READY_FOR_FREEZE"
    assert calls and len(calls[0][1])==12

def test_missing_r340_never_calls_r251(tmp_path):
    calls=[]
    bad=hist8(None); bad.pop(HIST8_FIELDS[0])
    def missing(_): return bad
    try:
        run_world_to_r251(
            events=[event()], ledger=TennisProspectiveEvidenceLedger(tmp_path/"l.jsonl"),
            registered_at_utc="2026-09-27T09:00:00+00:00",
            static4_loader=static4, r340_hist8_loader=missing,
            r251_scorer=lambda e,f: calls.append(1) or {"p_matrix":0.5},
        )
    except ValueError as exc:
        assert str(exc).startswith("R340_HIST8_MISSING:")
    assert calls==[]

def test_odds_key_from_scorer_is_forbidden(tmp_path):
    try:
        run_world_to_r251(
            events=[event()], ledger=TennisProspectiveEvidenceLedger(tmp_path/"l.jsonl"),
            registered_at_utc="2026-09-27T09:00:00+00:00",
            static4_loader=static4, r340_hist8_loader=hist8,
            r251_scorer=lambda e,f: {"p_matrix":0.5,"odds":2.0},
        )
    except ValueError as exc:
        assert str(exc)=="ODDS_TO_P_MATRIX_BOUNDARY_VIOLATION"
    else:
        raise AssertionError("odds boundary did not fail closed")
