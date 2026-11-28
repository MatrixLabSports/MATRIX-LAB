"""Changed authentic Challenger clocks cannot be silently promoted from stale pages."""
from datetime import datetime,timezone
from pathlib import Path

import pytest

from tools.matrix_tennis_capture_temporal_drift_guard import compare,run,_load

ROOT=Path(__file__).resolve().parents[1]
DAY="2026-11-18"

def ev(mid="123", *, at="2026-11-18T15:00:00Z", pid1="101",pid2="102"):
    return {
        "sofascore_event_id":mid,"kickoff_utc":at,
        "players":[{"name":"Player Alpha","sofascore_player_id":pid1},
                   {"name":"Player Beta","sofascore_player_id":pid2}],
        "surface":"Hard","court_label":"Dura indoor"
    }

def doc(*events,status="VERIFIED_VISIBLE_CHALLENGER_METADATA_RESEARCH_ONLY",
        at="2026-11-17T20:00:00Z",orig_sha=None):
    d={"schema":"MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1",
       "target_date_bogota":DAY,
       "observed_at_utc":at,
       "real_money":"BLOCKED","new_model_observations_admitted":0,
       "telegram_signal_authorized":False,
       "capture_method":"AUTHORIZED_WINDOWS_CDP_SOFASCORE_VISIBLE_MATCH_PAGES",
       "calendar_backend_api_called":False,
       "status":status,
       "events":list(events)}
    if orig_sha is not None:d["preserved_original_detail_sha256"]=orig_sha
    return d

def test_authentic_archived_nov18_capture_shows_two_changed_visible_starts_and_one_unreobserved():
    # Immutable real browser evidence, not a mutable LAST report.
    base=ROOT/"evidence/tennis_calendar_physical"/DAY
    old,h1=_load(base/"archive"/(
        "MATRIX_TENNIS_SOURCE_DETAILS_GITBLOB_28a653980b5612d7f6ff0564094f88eff2867080.json"))
    later,h2=_load(base/"archive"/(
        "MATRIX_TENNIS_MATCH_DETAIL_CAPTURE_ATTEMPT_a188601845673a726e0da70699bc856515397f1063dc1a3ac7c9a8520ffd143e.json"))
    r=compare(old,later,h1,h2,now=datetime(2026,11,18,4,tzinfo=timezone.utc))
    assert r["old_verified_kickoff_changed_count"]==2
    assert r["old_verified_matches_quarantined"]==3
    assert r["original_verified_match_count"]==4
    assert r["later_verified_match_count"]==3
    by_id={row["sofascore_id"]:row for row in r["events"]}
    assert by_id["17537274"]["kickoff_change_minutes"]==510
    assert by_id["17537336"]["kickoff_change_minutes"]==70
    assert by_id["17537873"]["temporal_quarantined"] is False
    assert "NOT_REOBSERVED_IN_LATER_AUTHENTIC_CAPTURE" in by_id["17537333"]["blocked_reasons"]
    assert r["new_hard_holdout_admissions"]==r["new_clay_holdout_admissions"]==0
    assert r["real_money"]=="BLOCKED"

def test_one_changed_clock_is_blocked_not_reinterpreted_as_timezone():
    old=doc(ev())
    latest=doc(ev(at="2026-11-18T16:10:00Z"),at="2026-11-17T22:00:00Z")
    r=compare(old,latest,"a"*64,"b"*64,now=datetime(2026,11,18,tzinfo=timezone.utc))
    assert r["old_verified_matches_quarantined"]==1
    assert r["old_verified_kickoff_changed_count"]==1
    assert r["events"][0]["kickoff_change_minutes"]==70
    assert "KICKOFF_CHANGED_IN_LATER_AUTHENTIC_CAPTURE" in r["events"][0]["blocked_reasons"]
    assert r["independently_certified_correct_kickoff_utc"] is False

def test_unobserved_old_event_is_not_presented_as_latest_verified():
    r=compare(doc(ev()),doc(at="2026-11-17T22:00:00Z"),
              "a"*64,"b"*64,now=datetime(2026,11,18,tzinfo=timezone.utc))
    assert r["old_verified_matches_quarantined"]==1
    assert r["events"][0]["later_kickoff_utc"] is None

def test_identity_drift_is_quarantined_even_when_kickoff_same():
    r=compare(doc(ev()),doc(ev(pid1="998"),at="2026-11-17T22:00:00Z"),
              "a"*64,"b"*64,now=datetime(2026,11,18,tzinfo=timezone.utc))
    assert "VISIBLE_PLAYER_IDENTITY_CHANGED_IN_LATER_CAPTURE" in r["events"][0]["blocked_reasons"]
    assert r["old_verified_kickoff_changed_count"]==0

def test_failed_new_capture_must_be_exactly_bound_to_saved_original_sha():
    old=doc(ev())
    attempt=doc(ev(),status="REJECTED_REGRESSED_DETAILS_PRESERVED",
                at="2026-11-17T22:00:00Z",orig_sha="c"*64)
    with pytest.raises(ValueError,match="DRIFT_GUARD_SAVED_ORIGINAL_SHA_NOT_EQUAL"):
        compare(old,attempt,"a"*64,"b"*64,now=datetime(2026,11,18,tzinfo=timezone.utc))

def test_later_capture_must_not_have_future_timestamp():
    with pytest.raises(ValueError,match="DRIFT_GUARD_LATER_ATTEMPT_FROM_FUTURE"):
        compare(doc(ev()),doc(ev(),at="2026-11-19T22:00:00Z"),
                "a"*64,"b"*64,now=datetime(2026,11,18,tzinfo=timezone.utc))

def test_non_wagering_source_is_required():
    fake=doc(ev()); fake["real_money"]="ENABLED"
    with pytest.raises(ValueError,match="DRIFT_GUARD_UNTRUSTED_CAPTURE"):
        compare(fake,doc(ev(),at="2026-11-17T22:00:00Z"),
                "a"*64,"b"*64,now=datetime(2026,11,18,tzinfo=timezone.utc))
