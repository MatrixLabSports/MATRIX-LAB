"""Unit-only anti-admission contracts: no API calls, no Telegram, no model writes."""
import hashlib
import json
from datetime import datetime, timezone

import pytest

from tools.matrix_football_free_third_source_research import (
    normalize, research, source_research, SCHEMA,
)

def browser():
    return {
        "target_date_bogota": "2026-11-18",
        "research_candidates": [
            {"home_normalized":"coritiba","away_normalized":"santos",
             "sofascore_event_id":"15235658","flashscore_mid":"nFe3yH7c",
             "sofascore_visible_clock_unverified_timezone":"17:30"},
            {"home_normalized":"cruzeiro","away_normalized":"palmeiras",
             "sofascore_event_id":"15235656","flashscore_mid":"zySpJZiT",
             "sofascore_visible_clock_unverified_timezone":"18:30"},
            {"home_normalized":"corinthians","away_normalized":"botafogo",
             "sofascore_event_id":"15238243","flashscore_mid":"6ezUMHh4",
             "sofascore_visible_clock_unverified_timezone":"19:30"}
        ],
    }

def api():
    return {"events":[
        {"dateEvent":"2026-11-18","strSport":"Soccer","idEvent":"2398532",
         "strHomeTeam":"Coritiba","strAwayTeam":"Santos","strStatus":"NS",
         "strTimestamp":"2026-11-18T22:30:00","strLeague":"Brazilian Serie A"},
        {"dateEvent":"2026-11-18","strSport":"Soccer","idEvent":"2398533",
         "strHomeTeam":"Cruzeiro","strAwayTeam":"Palmeiras","strStatus":"NS",
         "strTimestamp":"2026-11-18T23:30:00","strLeague":"Brazilian Serie A"},
        {"dateEvent":"2026-11-18","strSport":"Soccer","idEvent":"2398534",
         "strHomeTeam":"Flamengo","strAwayTeam":"Athletico Paranaense","strStatus":"NS",
         "strTimestamp":"2026-11-18T23:30:00","strLeague":"Brazilian Serie A"},
    ]}

def run(b=None, p=None, when="2026-11-18T01:00:00+00:00"):
    return research(b or browser(), p or api(),
                    observed_at_utc=datetime.fromisoformat(when),
                    browser_sha256="a"*64, provider_sha256="b"*64)

def test_true_18nov_free_sample_has_two_matches_no_admission():
    d=run()
    assert d["schema"]==SCHEMA
    assert d["research_browser_candidate_count"]==3
    assert d["free_provider_returned_event_count"]==3
    assert d["provider_name_match_count"]==2
    assert d["provider_unique_unstarted_name_matches"]==2
    assert d["time_consistent_research_matches"]==2
    assert d["strict_triple_source_certified_count"]==0
    assert d["pit_complete_count"]==0
    assert not d["producer_authorized"] and not d["telegram_signal_authorized"]
    assert d["real_money"]=="BLOCKED" and d["automatic_wagering"] is False
    assert d["free_eventsday_globally_exhaustive"] is False
    assert d["sofascore_display_timezone_certified"] is False

def test_finished_event_not_prospective_even_when_names_match():
    p=api()
    p["events"][0]["strStatus"]="FT"
    d=run(p=p)
    assert d["provider_name_match_count"]==2
    assert d["provider_unique_unstarted_name_matches"]==1
    assert d["rows"][0]["reason"]=="PROVIDER_ALREADY_STARTED_OR_FINISHED"
    assert d["telegram_signal_authorized"] is False

def test_past_event_not_prospective_even_if_provider_still_says_ns():
    d=run(when="2026-11-19T00:00:00+00:00")
    assert d["provider_unique_unstarted_name_matches"]==0
    assert d["telegram_signal_authorized"] is False

def test_ambiguous_provider_names_do_not_select_arbitrary_fixture():
    p=api()
    p["events"].append(dict(p["events"][0],idEvent="7777777"))
    d=run(p=p)
    assert d["provider_name_match_count"]==1
    assert d["rows"][0]["thesportsdb_event_id_name_match_only"] is None
    assert d["rows"][0]["reason"]=="PROVIDER_DUPLICATE_NAME_MATCH"

def test_missing_provider_events_fails_closed():
    with pytest.raises(ValueError,match="FREE_PROVIDER_EVENTS_ARRAY_MISSING"):
        run(p={"events":None})

def test_naive_capture_time_fails_closed():
    with pytest.raises(ValueError,match="TIMESTAMP_HAS_NO_ZONE"):
        run(when="2026-11-17T20:00:00")

def test_normalized_aliases_are_stable():
    assert normalize("Gales")=="wales"
    assert normalize("UCRANIA")=="ukraine"
    assert normalize("Cruzeiro")=="cruzeiro"

def test_browser_hashes_are_bound_to_actual_capture_bytes(tmp_path):
    folder=tmp_path
    a=b'{"links":[],"source":"SOFASCORE"}'
    b=b'{"links":[],"source":"FLASHSCORE"}'
    (folder/"sofascore_visible_links.json").write_bytes(a)
    (folder/"flashscore_visible_links.json").write_bytes(b)
    d={
        "schema":"MATRIX_AUTHORIZED_FOOTBALL_DUAL_BROWSER_RESEARCH_LINKS_V1",
        "target_date_bogota":"2026-11-18",
        "status":"RESEARCH_TWO_SOURCE_CANDIDATES_ONLY_NOT_CALENDAR_CERTIFIED",
        "real_money":"BLOCKED", "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,"canonical_prematch_inputs_authorized":False,
        "research_candidates":[{"sofascore_event_id":"1","flashscore_mid":"ABC12345"}],
        "research_candidate_count":1,
        "source_capture_at_utc":{"sofascore":"2026-11-17T20:00:00+00:00",
                                 "flashscore":"2026-11-17T20:00:00+00:00"},
        "source_sha256":{"sofascore":hashlib.sha256(a).hexdigest(),
                         "flashscore":hashlib.sha256(b).hexdigest()},
    }
    (folder/"MATRIX_TWO_SOURCE_LINK_RESEARCH_LAST.json").write_text(json.dumps(d))
    got,_=source_research(folder,"2026-11-18")
    assert got["research_candidate_count"]==1
    (folder/"flashscore_visible_links.json").write_bytes(b+" ")
    with pytest.raises(ValueError,match="HASH_CHANGED"):
        source_research(folder,"2026-11-18")
