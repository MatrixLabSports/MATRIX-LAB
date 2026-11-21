"""Offline Challenger fixture drift regression tests; no model promotions."""
import hashlib
import json
from pathlib import Path
import pytest
from tools.matrix_tennis_cross_day_fixture_drift_audit import audit

def make(root, day, kickoff):
    folder=root/"evidence/tennis_calendar_reconciliation"/day
    folder.mkdir(parents=True)
    source=root/"evidence/tennis_calendar_physical"/day/"source_detail.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({
        "schema":"MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1",
        "target_date_bogota":day,"real_money":"BLOCKED",
        "provider_identity_equivalence_certified":False,
        "events":[{"sofascore_event_id":"17537333","kickoff_utc":kickoff,
                   "surface":"Hard","players":[{"name":"Alastair Gray"},{"name":"Bor Artnak"}]}]
    }))
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    folder.joinpath("MATRIX_TENNIS_FREE_PROFILE_SOURCE_BINDING_AUDIT_LAST.json").write_text(json.dumps({
        "schema":"MATRIX_TENNIS_FREE_PROFILE_SOURCE_BINDING_AUDIT_V1",
        "date_bogota":day,"real_money":"BLOCKED",
        "source_detail_path":str(source.relative_to(root)),
        "source_sha256":{"verified_match_details":sha},
        "new_hard_holdout_observations":0,"new_clay_holdout_observations":0,
        "rows":[{"sofascore_player_id":"222958","sofascore_event_id":"17537333"},
                {"sofascore_player_id":"386501","sofascore_event_id":"17537333"}]
    }))
    return source

def test_conflicting_actual_event_id_is_quarantined_not_double_counted(tmp_path):
    make(tmp_path,"2026-11-18","2026-11-18T16:00:00Z")
    make(tmp_path,"2026-11-19","2026-11-19T16:00:00Z")
    r=audit(tmp_path,("2026-11-18","2026-11-19"))
    assert r["source_day_event_instances"]==2
    assert r["unique_source_event_ids"]==1
    assert r["unique_visible_player_ids_across_days"]==2
    assert r["conflicting_source_event_ids"]==1
    assert r["conflicts"][0]["sofascore_event_id"]=="17537333"
    assert r["new_hard_holdout_observations"]==0
    assert r["original_model_pit_equivalence_certified"] is False
    assert r["real_money"]=="BLOCKED"

def test_same_match_and_kickoff_is_one_stable_research_event(tmp_path):
    make(tmp_path,"2026-11-18","2026-11-19T16:00:00Z")
    make(tmp_path,"2026-11-19","2026-11-19T16:00:00Z")
    r=audit(tmp_path,("2026-11-18","2026-11-19"))
    assert r["conflicting_source_event_ids"]==0
    assert r["unique_nonconflicting_event_ids_research_only"]==1
    assert r["new_hard_holdout_observations"]==0

def test_source_sha_change_fails_closed(tmp_path):
    source=make(tmp_path,"2026-11-18","2026-11-18T16:00:00Z")
    make(tmp_path,"2026-11-19","2026-11-19T16:00:00Z")
    source.write_bytes(source.read_bytes()+b" ")
    with pytest.raises(ValueError,match="CROSS_DAY_SOURCE_DETAIL_SHA_MISMATCH"):
        audit(tmp_path,("2026-11-18","2026-11-19"))

def test_repeating_day_is_invalid(tmp_path):
    with pytest.raises(ValueError,match="CROSS_DAY_REQUIRES_DISTINCT_DAYS"):
        audit(tmp_path,("2026-11-18","2026-11-18"))
