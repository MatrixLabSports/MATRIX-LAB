"""Functional, offline collector-level eligibility checks; no bookmaker calls."""
from datetime import datetime, timedelta, timezone
from tools.matrix_selfhosted_browser_quote_collector import quote_eligibility

NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def candidate(p=0.70, kickoff=None):
    return {"p_matrix": p, "kickoff": (kickoff or NOW + timedelta(minutes=30)).isoformat()}


def test_valid_certified_prematch_quote_passes_collector_gate():
    assert quote_eligibility({"price": 1.60}, candidate(), "CERTIFIED_EXACT_OVER25", NOW) == (True, None)


def test_odds_floor_is_strict():
    assert quote_eligibility({"price": 1.50}, candidate(), "CERTIFIED_EXACT_OVER25", NOW) == (False, "ODDS_BELOW_MIN_1_50")


def test_negative_ev_is_blocked():
    assert quote_eligibility({"price": 1.60}, candidate(p=0.60), "CERTIFIED_EXACT_OVER25", NOW) == (False, "NO_SIGNAL_ECONOMIC_GATE")


def test_kickoff_and_missing_timezone_are_blocked():
    assert quote_eligibility({"price": 1.60}, candidate(kickoff=NOW), "CERTIFIED_EXACT_OVER25", NOW) == (False, "NO_SIGNAL_KICKOFF")
    assert quote_eligibility({"price": 1.60}, {"p_matrix": 0.70, "kickoff": "2026-10-30T13:00:00"}, "CERTIFIED_EXACT_OVER25", NOW) == (False, "NO_SIGNAL_KICKOFF")


def test_uncertified_adapter_never_emits():
    assert quote_eligibility({"price": 2.10}, candidate(), "CAPTURE_ONLY_PENDING_SELECTOR_CERTIFICATION", NOW) == (False, "BOOKMAKER_ADAPTER_NOT_CERTIFIED")


def test_missing_or_invalid_price_fails_closed():
    for price in (None, "invalid", float("nan"), float("inf")):
        assert quote_eligibility({"price": price}, candidate(), "CERTIFIED_EXACT_OVER25", NOW)[0] is False


def test_missing_probability_fails_closed():
    assert quote_eligibility({"price": 1.70}, {"kickoff": (NOW + timedelta(hours=1)).isoformat()}, "CERTIFIED_EXACT_OVER25", NOW) == (False, "NO_SIGNAL_ECONOMIC_GATE")
