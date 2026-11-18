"""Synthetic-unit cases only. They never generate real predictions, odds or alerts."""
import hashlib
from datetime import datetime, timezone

import pytest

from tools.matrix_football_free_six_league_crosscheck import (
    SCHEMA, LEAGUES, assemble, fetch_league, persist_raw, validate_provider
)

DAY = "2026-11-21"

def browser():
    return {
        "target_date_bogota": DAY,
        "research_candidates": [
            {
                "home_normalized": "fictitious home",
                "away_normalized": "fictitious away",
                "sofascore_event_id": "111",
                "flashscore_mid": "ABCDEFGH",
                "sofascore_visible_clock_unverified_timezone": "10:00",
            },
            {
                "home_normalized": "other club",
                "away_normalized": "rival club",
                "sofascore_event_id": "222",
                "flashscore_mid": "IJKL1234",
                "sofascore_visible_clock_unverified_timezone": "09:00",
            },
        ]
    }

def fake_event(**overrides):
    d = {
        "idEvent": "777001", "idLeague": "4328", "strSport": "Soccer",
        "dateEvent": DAY, "strHomeTeam": "Fictitious Home",
        "strAwayTeam": "Fictitious Away", "strStatus": "NS",
        "strTimestamp": "2026-11-21T15:00:00",
    }
    return {**d, **overrides}

def test_six_distinct_league_ids_are_only_research_namespace_hints():
    assert len(LEAGUES) == 6
    assert {x[0] for x in LEAGUES} == {"39", "61", "78", "135", "140", "239"}
    assert len({x[1] for x in LEAGUES}) == 6

def test_synthetic_future_match_does_not_authorize_any_model_or_signal():
    events = validate_provider(DAY, "4328", {"events": [fake_event()]})
    d = assemble(browser(), {"4328": events}, seen_at=datetime(2026, 11, 20, 10, tzinfo=timezone.utc),
                 receipts={"4328":{"status":"AUTHENTIC_FREE_LEAGUE_CAPTURE_RESEARCH_ONLY"}})
    assert d["schema"] == SCHEMA
    assert d["two_browser_candidates"] == 2
    assert d["league_scoped_name_matches"] == 1
    assert d["future_research_name_matches"] == 1
    assert d["rows"][0]["clock_matches_if_sofascore_displays_bogota"]
    assert d["rows"][0]["original_league_id_hint_not_fixture_certification"] == "39"
    assert d["kickoff_and_identity_certified"] == 0
    assert d["pit_certified"] == 0
    assert d["telegram_signal_authorized"] is False
    assert d["production_p_matrix_authorized"] is False
    assert d["automatic_wagering"] is False
    assert d["real_money"] == "BLOCKED"

def test_finished_game_is_never_prospective_candidate():
    e = fake_event(strStatus="FT")
    d = assemble(browser(), {"4328": [e]}, seen_at=datetime(2026, 11, 20, 10, tzinfo=timezone.utc),
                 receipts={})
    assert d["league_scoped_name_matches"] == 1
    assert d["future_research_name_matches"] == 0
    assert d["rows"][0]["reason"] == "PROVIDER_NOT_UNSTARTED_OR_TIMESTAMP_PAST"

def test_cross_league_duplicate_team_pair_is_quarantined():
    d = assemble(browser(), {"4328":[fake_event()], "4335":[fake_event(idLeague="4335",idEvent="777002")]},
                 seen_at=datetime(2026,11,20,10,tzinfo=timezone.utc),receipts={})
    assert d["league_scoped_name_matches"] == 0
    assert d["rows"][0]["reason"] == "SOURCE_NAME_AMBIGUITY"
    assert d["rows"][0]["thesportsdb_event_id_name_only"] is None

def test_no_naive_system_time():
    with pytest.raises(ValueError,match="TIMEZONE_AWARE"):
        assemble(browser(),{"4328":[fake_event()]},seen_at=datetime(2026,11,20,10),receipts={})

@pytest.mark.parametrize("change,reason",[
    ({"idLeague":"4335"}, "OUTSIDE_REQUESTED"),
    ({"dateEvent":"2026-11-22"}, "OUTSIDE_REQUESTED"),
    ({"strSport":"Cricket"}, "OUTSIDE_REQUESTED"),
    ({"idEvent":None}, "ID_MISSING"),
])
def test_bad_provider_row_fails_closed(change,reason):
    with pytest.raises(ValueError,match=reason):
        validate_provider(DAY,"4328",{"events":[fake_event(**change)]})

def test_duplicate_provider_ids_fail_closed():
    with pytest.raises(ValueError,match="DUPLICATE"):
        validate_provider(DAY,"4328",{"events":[fake_event(),fake_event()]})

def test_null_events_is_allowed_as_zero_returned_not_zero_worldwide():
    assert validate_provider(DAY,"4328",{"events":None}) == []

def test_raw_sha_and_archive_survives_two_provider_snapshots(tmp_path):
    a=b'{"events":[]}'
    b=b'{"events":null}'
    x=persist_raw(tmp_path,"4328",a)
    assert x["sha256"]==hashlib.sha256(a).hexdigest()
    assert (tmp_path/"MATRIX_THESPORTSDB_DAY_LEAGUE_4328_RAW.json").read_bytes()==a
    y=persist_raw(tmp_path,"4328",b)
    assert y["sha256"]==hashlib.sha256(b).hexdigest()
    previous=tmp_path/"archive"/("thesportsdb_league_4328_"+hashlib.sha256(a).hexdigest()+".json")
    assert previous.read_bytes()==a

def test_only_approved_league_ids_can_be_queried():
    with pytest.raises(ValueError,match="LEAGUE_NOT_IN_APPROVED_SIX"):
        fetch_league(DAY, "99999")
