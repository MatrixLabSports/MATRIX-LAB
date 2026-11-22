import copy
from datetime import datetime, timezone, timedelta
import pytest
from tools.matrix_browser_first_research_quote_watchlist import build

AT=datetime(2026,11,22,4,0,tzinfo=timezone.utc)
EVENT="2026-11-22T05:30:00+00:00"

def sample():
    freeze={
        "schema":"MATRIX_ESPN_SIX_LEAGUE_RESEARCH_PROSPECTIVE_OVER25_V1",
        "telegram_signal_authorized":False,"real_money":"BLOCKED",
        "source_raw_provider_bytes_sha256_verified":False,
        "rows":[{"fixture_id":"12","kickoff_utc":EVENT,"home":"Barcelona",
                 "away":"Villarreal","research_probability_over25":0.55}],
    }
    browser={
        "schema":"MATRIX_BROWSER_FIRST_ESPN_SOFA_FLASH_PROSPECTIVE_RESEARCH_CROSSWALK_V1",
        "telegram_signal_authorized":False,"real_money":"BLOCKED",
        "odds_market_over_2_5_verified":False,
        "source_order":["SOFASCORE","FLASHSCORE","ESPN"],
        "created_from_read_at_utc":"2026-11-22T03:50:00+00:00",
        "sofascore_match_rows":[{
            "espn_fixture_id":"12","sofascore_event_id":"55",
            "kickoff_utc":EVENT,"home_espn":"Barcelona","away_espn":"Villarreal",
            "sofascore_url":"https://www.sofascore.com/es/football/match/a-b#id:55"}],
        "three_source_research_match":{
            "espn_fixture_id":"12","sofascore_event_id":"55",
            "flashscore_provider_match_url":"https://www.flashscore.co/partido/futbol/a-b/"}
    }
    return browser,freeze

def test_fresh_triple_source_in_window_research_only():
    report=build(*sample(),now=AT)
    row=report["watchlist"][0]
    assert report["watchlist_count"]==1
    assert report["research_quote_lookup_eligible"]==1
    assert row["authentic_over25_bookmaker_quote"] is None
    assert row["official_p_matrix"] is None
    assert row["telegram_signal_authorized"] is False
    assert report["real_money"]=="BLOCKED"

def test_stale_browser_refuses_quote_lookup():
    a,b=sample()
    a["created_from_read_at_utc"]="2026-11-22T03:40:00+00:00"
    report=build(a,b,now=AT)
    assert report["research_quote_lookup_eligible"]==0
    assert report["watchlist"][0]["quote_attempt_state"]=="WAITING_FRESH_BROWSER_REVALIDATION"

def test_outside_final_window_cannot_trigger_quote():
    a,b=sample()
    b["rows"][0]["kickoff_utc"]="2026-11-22T08:00:00Z"
    a["sofascore_match_rows"][0]["kickoff_utc"]="2026-11-22T08:00:00Z"
    report=build(a,b,now=AT)
    assert report["research_quote_lookup_eligible"]==0

def test_missing_flashscore_match_no_quote():
    a,b=sample()
    a["three_source_research_match"]={}
    report=build(a,b,now=AT)
    assert not report["watchlist"][0]["three_source_research_calendar_identity"]
    assert report["research_quote_lookup_eligible"]==0

def test_mismatch_kickoff_rejected():
    a,b=sample()
    a["sofascore_match_rows"][0]["kickoff_utc"]="2026-11-22T05:31:00Z"
    with pytest.raises(ValueError,match="BROWSER_FIXTURE_ID_OR_KICKOFF_MISMATCH"):
        build(a,b,now=AT)

def test_duplicate_provider_pair_fails():
    a,b=sample()
    a["sofascore_match_rows"].append(copy.deepcopy(a["sofascore_match_rows"][0]))
    with pytest.raises(ValueError,match="AMBIGUOUS_RESEARCH_EVENT_JOIN"):
        build(a,b,now=AT)

def test_untrusted_production_promotion_rejected():
    a,b=sample()
    b["telegram_signal_authorized"]=True
    with pytest.raises(ValueError,match="RESEARCH_SOURCE_GOVERNANCE_NOT_TRUSTED"):
        build(a,b,now=AT)

def test_postkickoff_not_backfilled():
    a,b=sample()
    r=build(a,b,now=datetime(2026,11,22,6,0,tzinfo=timezone.utc))
    assert r["watchlist_count"]==0
