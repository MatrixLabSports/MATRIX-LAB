"""Regression tests for the existing fail-closed bookmaker guardrails.

These tests do not extract odds, enable bookmaker adapters, or send bets.
"""
from datetime import datetime, timezone, timedelta
from tools.matrix_selfhosted_browser_quote_collector import quote_eligibility


NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def candidate(minutes=30, probability=0.7):
    return {"kickoff": (NOW + timedelta(minutes=minutes)).isoformat(), "p_matrix": probability}


def test_uncertified_adapter_rejected_even_with_high_ev():
    allowed, reason = quote_eligibility({"price": 2.5}, candidate(), "CAPTURE_ONLY_PENDING_SELECTOR_CERTIFICATION", NOW)
    assert (allowed, reason) == (False, "BOOKMAKER_ADAPTER_NOT_CERTIFIED")


def test_missing_exact_price_rejected():
    assert quote_eligibility(None, candidate(), "CERTIFIED_EXACT_OVER25", NOW) == (False, "EXACT_OVER25_NOT_FOUND")


def test_price_equal_to_minimum_rejected():
    assert quote_eligibility({"price": 1.5}, candidate(), "CERTIFIED_EXACT_OVER25", NOW) == (False, "ODDS_BELOW_MIN_1_50")


def test_started_event_rejected():
    assert quote_eligibility({"price": 2.0}, candidate(minutes=-1), "CERTIFIED_EXACT_OVER25", NOW) == (False, "NO_SIGNAL_KICKOFF")


def test_missing_timezone_rejected():
    row = {"kickoff": "2026-10-30T12:30:00", "p_matrix": 0.7}
    assert quote_eligibility({"price": 2.0}, row, "CERTIFIED_EXACT_OVER25", NOW) == (False, "NO_SIGNAL_KICKOFF")


def test_negative_expected_value_rejected():
    assert quote_eligibility({"price": 1.6}, candidate(probability=0.6), "CERTIFIED_EXACT_OVER25", NOW) == (False, "NO_SIGNAL_ECONOMIC_GATE")
