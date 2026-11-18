"""Research-only source clock must never imply actual independent UTC proof."""
from tools.matrix_tennis_flashscore_visible_clock_research import (
    SCHEMA, clock_from_visible, exact_match_page,
)
def test_one_real_style_flashscore_visible_clock_is_not_timezone_attestation():
    raw="""Champaign, Dura - 1/8 de final
Tarvet O.
18.11.2026 12:30
Baris O.
"""
    time, status=clock_from_visible(raw,"2026-11-18")
    assert time == "18.11.2026 12:30"
    assert status == "UNIQUE_VISIBLE_DATE_TIME_NO_TIMEZONE"
    assert SCHEMA.endswith("_RESEARCH_V1")

def test_two_distinct_clocks_fail_closed():
    t, status=clock_from_visible(
        "18.11.2026 11:00\n18.11.2026 12:30\n","2026-11-18")
    assert t is None
    assert status == "AMBIGUOUS_VISIBLE_MATCH_CLOCK"

def test_duplicate_same_clock_not_an_event_identity():
    t, status=clock_from_visible(
        "18.11.2026 11:00\n18.11.2026 11:00\n","2026-11-18")
    assert t == "18.11.2026 11:00"
    assert status == "UNIQUE_VISIBLE_DATE_TIME_NO_TIMEZONE"

def test_wrong_day_and_invalid_hour_do_not_get_backfilled():
    assert clock_from_visible("17.11.2026 11:00","2026-11-18")[0] is None
    assert clock_from_visible("18.11.2026 29:00","2026-11-18")[0] is None

def test_exact_verified_flashscore_match_url_only():
    assert exact_match_page(
        "https://www.flashscore.co/partido/tenis/baris-ozan-CI4P8u7o/tarvet-oliver-lYUiygo1/?mid=fHTaO9Is",
        "fHTaO9Is"
    )
    assert not exact_match_page(
        "https://www.flashscore.co/partido/tenis/baris-ozan-CI4P8u7o/tarvet-oliver-lYUiygo1/?mid=fHTaO9Is",
        "OTHERID"
    )
    assert not exact_match_page(
        "http://www.flashscore.co/partido/tenis/baris-ozan-CI4P8u7o/tarvet-oliver-lYUiygo1/?mid=fHTaO9Is",
        "fHTaO9Is"
    )
    assert not exact_match_page(
        "https://example.com/partido/tenis/baris-ozan-CI4P8u7o/tarvet-oliver-lYUiygo1/?mid=fHTaO9Is",
        "fHTaO9Is"
    )
